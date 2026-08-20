import { prepareCorpus, type CorpusDocument } from "./corpus";
import { ensureAppSchema } from "./schema";
import { planLightEdit, planSpanEdit, runWritingAssistant } from "./writing-assistant";
import { scoreStyle, type StyleProfile } from "./stylometry";

export interface AppEnv {
  DB: D1Database;
  FILES: R2Bucket;
  DEV_AUTH?: string;
  STRIPE_SECRET_KEY?: string;
  STRIPE_TRAINING_PRICE_ID?: string;
  STRIPE_CREDIT_PRICE_ID?: string;
  STRIPE_WEBHOOK_SECRET?: string;
  MODAL_KEY?: string;
  MODAL_SECRET?: string;
  HOSTED_TRAIN_ENDPOINT?: string;
  HOSTED_TRAIN_RESULT_ENDPOINT?: string;
  HOSTED_GENERATE_ENDPOINT?: string;
  HOSTED_GENERATE_RESULT_ENDPOINT?: string;
  RESEND_API_KEY?: string;
  EMAIL_FROM?: string;
  AI_GATEWAY_API_KEY?: string;
  ROUTER_MODEL?: string;
  ADMIN_EMAILS?: string;
  PROVIDER_CALLBACK_SECRET?: string;
  APP_URL?: string;
}

type User = { id: string; email: string; name: string | null; scopes: string[] };
type JsonObject = Record<string, unknown>;

const JSON_HEADERS = { "cache-control": "no-store", "content-type": "application/json" };
const MAX_ITEM_BYTES = 2_000_000;
const MAX_CORPUS_BYTES = 20_000_000;
const TRAINING_PRICE_CENTS = 2_000;
const CREDIT_PACK_SIZE = 20;

function response(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...headers } });
}

function failure(code: string, message: string, status: number, details?: JsonObject): Response {
  return response(
    { error: { code, message, request_id: `req_${crypto.randomUUID()}`, ...(details ? { details } : {}) } },
    status,
  );
}

function id(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
}

function now(): string {
  return new Date().toISOString();
}

async function digest(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function parseJson(request: Request, maxBytes = MAX_ITEM_BYTES): Promise<JsonObject> {
  const length = Number(request.headers.get("content-length") || 0);
  if (length > maxBytes) throw new Error("request_too_large");
  const body = (await request.json()) as unknown;
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("invalid_json");
  return body as JsonObject;
}

async function authenticate(request: Request, env: AppEnv, scopes: string[] = []): Promise<User | null> {
  const platformId = request.headers.get("oai-authenticated-user-id");
  const platformEmail = request.headers.get("oai-authenticated-user-email");
  if (platformId && platformEmail) {
    return { id: platformId, email: platformEmail, name: null, scopes: ["*"] };
  }

  const authorization = request.headers.get("authorization");
  if (authorization) {
    if (!authorization.startsWith("Bearer vp_")) return null;
    const keyHash = await digest(authorization.slice(7));
    const key = await env.DB.prepare(
      "SELECT owner_id, scopes FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
    ).bind(keyHash).first<{ owner_id: string; scopes: string }>();
    if (!key) return null;
    const granted = JSON.parse(key.scopes) as string[];
    if (scopes.some((scope) => !granted.includes(scope))) return null;
    await env.DB.prepare("UPDATE api_keys SET last_used_at = ? WHERE key_hash = ?")
      .bind(now(), keyHash).run();
    const account = await env.DB.prepare("SELECT email, name FROM users WHERE id = ?")
      .bind(key.owner_id).first<{ email: string; name: string | null }>();
    if (!account) return null;
    return { id: key.owner_id, email: account.email, name: account.name, scopes: granted };
  }

  if (env.DEV_AUTH === "1") {
    return { id: "dev_voiceprint_user", email: "beta@voiceprint.local", name: "Beta Writer", scopes: ["*"] };
  }
  return null;
}

async function upsertUser(env: AppEnv, user: User): Promise<void> {
  const timestamp = now();
  await env.DB.prepare(
    `INSERT INTO users (id, email, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET email = excluded.email, updated_at = excluded.updated_at`,
  ).bind(user.id, user.email, user.name, timestamp, timestamp).run();
}

async function requireUser(request: Request, env: AppEnv, scopes: string[] = []): Promise<User | Response> {
  const user = await authenticate(request, env, scopes);
  if (!user) return failure("unauthorized", "Sign in or provide a valid API key.", 401);
  await upsertUser(env, user);
  return user;
}

function isResponse(value: User | Response): value is Response {
  return value instanceof Response;
}

async function ownedCorpus(env: AppEnv, userId: string, corpusId: string) {
  return env.DB.prepare("SELECT * FROM corpora WHERE id = ? AND owner_id = ?")
    .bind(corpusId, userId).first<Record<string, unknown>>();
}

async function corpusDocuments(env: AppEnv, userId: string, corpusId: string): Promise<CorpusDocument[]> {
  const items = await env.DB.prepare(
    "SELECT name, storage_key FROM corpus_items WHERE corpus_id = ? AND owner_id = ? ORDER BY created_at",
  ).bind(corpusId, userId).all<{ name: string; storage_key: string }>();
  const documents: CorpusDocument[] = [];
  for (const item of items.results) {
    const object = await env.FILES.get(item.storage_key);
    if (object) documents.push({ name: item.name, text: await object.text() });
  }
  return documents;
}

async function inspectAndPersist(env: AppEnv, userId: string, corpusId: string) {
  const prepared = prepareCorpus(await corpusDocuments(env, userId, corpusId));
  const report = prepared.report;
  await env.DB.prepare(
    `UPDATE corpora SET status = ?, documents = ?, raw_words = ?, usable_words = ?,
     duplicate_words = ?, updated_at = ? WHERE id = ? AND owner_id = ?`,
  ).bind(
    report.status,
    report.documents,
    report.raw_words,
    report.usable_words,
    report.duplicate_words,
    now(),
    corpusId,
    userId,
  ).run();
  return prepared;
}

async function balance(env: AppEnv, userId: string): Promise<number> {
  const row = await env.DB.prepare(
    "SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE owner_id = ?",
  ).bind(userId).first<{ balance: number }>();
  return Number(row?.balance || 0);
}

async function handleProfile(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method === "GET") {
    const profile = await env.DB.prepare(
      "SELECT id, email, name, writing_goals, sample_notes, created_at FROM users WHERE id = ?",
    ).bind(user.id).first();
    return response({ user: profile, credits: await balance(env, user.id) });
  }
  if (request.method === "PUT") {
    const body = await parseJson(request, 20_000);
    const name = typeof body.name === "string" ? body.name.trim().slice(0, 120) : "";
    const goals = typeof body.writing_goals === "string" ? body.writing_goals.trim().slice(0, 1_000) : "";
    const notes = typeof body.sample_notes === "string" ? body.sample_notes.trim().slice(0, 1_000) : "";
    await env.DB.prepare(
      "UPDATE users SET name = ?, writing_goals = ?, sample_notes = ?, updated_at = ? WHERE id = ?",
    ).bind(name || null, goals || null, notes || null, now(), user.id).run();
    return response({ updated: true });
  }
  return failure("method_not_allowed", "Method not allowed.", 405);
}

async function handleCorpora(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method === "GET") {
    const rows = await env.DB.prepare(
      "SELECT * FROM corpora WHERE owner_id = ? ORDER BY updated_at DESC",
    ).bind(user.id).all();
    return response({ data: rows.results });
  }
  if (request.method === "POST") {
    const body = await parseJson(request, 10_000);
    const name = typeof body.name === "string" ? body.name.trim().slice(0, 120) : "";
    if (!name) return failure("invalid_name", "Give the corpus a name.", 400);
    const corpusId = id("corpus");
    const timestamp = now();
    await env.DB.prepare(
      "INSERT INTO corpora (id, owner_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
    ).bind(corpusId, user.id, name, timestamp, timestamp).run();
    return response({ id: corpusId, name, status: "draft" }, 201, { location: `/v1/corpora/${corpusId}` });
  }
  return failure("method_not_allowed", "Method not allowed.", 405);
}

async function handleCorpus(
  request: Request,
  env: AppEnv,
  user: User,
  corpusId: string,
  action?: string,
): Promise<Response> {
  const corpus = await ownedCorpus(env, user.id, corpusId);
  if (!corpus) return failure("not_found", "Corpus not found.", 404);

  if (!action && request.method === "GET") {
    const items = await env.DB.prepare(
      "SELECT id, name, content_type, bytes, raw_words, created_at FROM corpus_items WHERE corpus_id = ? AND owner_id = ? ORDER BY created_at",
    ).bind(corpusId, user.id).all();
    return response({ ...corpus, items: items.results });
  }
  if (!action && request.method === "DELETE") {
    const items = await env.DB.prepare(
      "SELECT storage_key FROM corpus_items WHERE corpus_id = ? AND owner_id = ?",
    ).bind(corpusId, user.id).all<{ storage_key: string }>();
    for (const item of items.results) await env.FILES.delete(item.storage_key);
    await env.DB.batch([
      env.DB.prepare("DELETE FROM corpus_items WHERE corpus_id = ? AND owner_id = ?").bind(corpusId, user.id),
      env.DB.prepare("DELETE FROM corpora WHERE id = ? AND owner_id = ?").bind(corpusId, user.id),
    ]);
    return new Response(null, { status: 204 });
  }
  if (action === "text" && request.method === "POST") {
    const body = await parseJson(request);
    const name = typeof body.name === "string" ? body.name.trim().slice(0, 180) : "";
    const text = typeof body.text === "string" ? body.text : "";
    if (!name || !text.trim()) return failure("invalid_document", "A name and non-empty text are required.", 400);
    const bytes = new TextEncoder().encode(text).byteLength;
    if (bytes > MAX_ITEM_BYTES) return failure("document_too_large", "Each document must be under 2 MB.", 413);
    const usage = await env.DB.prepare(
      "SELECT COALESCE(SUM(bytes), 0) AS bytes FROM corpus_items WHERE corpus_id = ? AND owner_id = ?",
    ).bind(corpusId, user.id).first<{ bytes: number }>();
    if (Number(usage?.bytes || 0) + bytes > MAX_CORPUS_BYTES) {
      return failure("corpus_too_large", "A corpus may contain at most 20 MB of text.", 413);
    }
    const itemId = id("item");
    const storageKey = `corpora/${user.id}/${corpusId}/${itemId}.txt`;
    await env.FILES.put(storageKey, text, { httpMetadata: { contentType: "text/plain; charset=utf-8" } });
    await env.DB.batch([
      env.DB.prepare(
        "INSERT INTO corpus_items (id, corpus_id, owner_id, name, content_type, storage_key, bytes, raw_words, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
      ).bind(itemId, corpusId, user.id, name, "text/plain", storageKey, bytes, text.trim().split(/\s+/).length, now()),
      env.DB.prepare("UPDATE corpora SET status = 'draft', updated_at = ? WHERE id = ? AND owner_id = ?")
        .bind(now(), corpusId, user.id),
    ]);
    return response({ id: itemId, name, bytes }, 201);
  }
  if (action === "inspect" && request.method === "POST") {
    const prepared = await inspectAndPersist(env, user.id, corpusId);
    return response(prepared.report);
  }
  if (action === "revisions" && request.method === "POST") {
    const prepared = await inspectAndPersist(env, user.id, corpusId);
    if (!prepared.report.ready) {
      return failure("corpus_not_ready", "The corpus needs more usable prose before training.", 409, {
        usable_words: prepared.report.usable_words,
        minimum_words: prepared.report.minimum_words,
      });
    }
    const snapshot = JSON.stringify(prepared.chunks);
    const checksum = await digest(snapshot);
    const existing = await env.DB.prepare(
      "SELECT id FROM corpus_revisions WHERE owner_id = ? AND corpus_id = ? AND checksum = ?",
    ).bind(user.id, corpusId, checksum).first<{ id: string }>();
    if (existing) return response({ id: existing.id, checksum, reused: true });
    const revisionId = id("revision");
    const snapshotKey = `revisions/${user.id}/${revisionId}.json`;
    await env.FILES.put(snapshotKey, snapshot, { httpMetadata: { contentType: "application/json" } });
    await env.DB.prepare(
      "INSERT INTO corpus_revisions (id, corpus_id, owner_id, checksum, usable_words, snapshot_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    ).bind(revisionId, corpusId, user.id, checksum, prepared.report.usable_words, snapshotKey, now()).run();
    return response({ id: revisionId, checksum, usable_words: prepared.report.usable_words }, 201);
  }
  return failure("method_not_allowed", "Method not allowed.", 405);
}

async function handleApiKeys(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method === "GET") {
    const keys = await env.DB.prepare(
      "SELECT id, name, prefix, scopes, last_used_at, revoked_at, created_at FROM api_keys WHERE owner_id = ? ORDER BY created_at DESC",
    ).bind(user.id).all<{ id: string; name: string; prefix: string; scopes: string; last_used_at: string | null; revoked_at: string | null; created_at: string }>();
    return response({ data: keys.results.map((key) => ({ ...key, scopes: JSON.parse(String(key.scopes)) })) });
  }
  if (request.method === "POST") {
    const body = await parseJson(request, 10_000);
    const name = typeof body.name === "string" ? body.name.trim().slice(0, 80) : "";
    const requested = Array.isArray(body.scopes) ? body.scopes.filter((scope): scope is string => typeof scope === "string") : [];
    const allowed = ["corpora:read", "corpora:write", "models:read", "models:write", "generate", "scores:write"];
    const scopes = requested.filter((scope) => allowed.includes(scope));
    if (!name || !scopes.length) return failure("invalid_key", "A key name and at least one valid scope are required.", 400);
    const secret = `vp_live_${crypto.randomUUID().replaceAll("-", "")}${crypto.randomUUID().replaceAll("-", "")}`;
    const keyId = id("key");
    await env.DB.prepare(
      "INSERT INTO api_keys (id, owner_id, name, prefix, key_hash, scopes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    ).bind(keyId, user.id, name, secret.slice(0, 16), await digest(secret), JSON.stringify(scopes), now()).run();
    return response({ id: keyId, key: secret, prefix: secret.slice(0, 16), scopes }, 201);
  }
  return failure("method_not_allowed", "Method not allowed.", 405);
}

async function handleApiKey(request: Request, env: AppEnv, user: User, keyId: string): Promise<Response> {
  if (request.method !== "DELETE") return failure("method_not_allowed", "Method not allowed.", 405);
  await env.DB.prepare("UPDATE api_keys SET revoked_at = ? WHERE id = ? AND owner_id = ?")
    .bind(now(), keyId, user.id).run();
  return new Response(null, { status: 204 });
}

async function handleModels(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method !== "GET") return failure("method_not_allowed", "Method not allowed.", 405);
  const models = await env.DB.prepare(
    "SELECT id, revision_id, name, status, provider, provider_model, trained_at, created_at, updated_at FROM models WHERE owner_id = ? AND status != 'deleted' ORDER BY updated_at DESC",
  ).bind(user.id).all();
  return response({ data: models.results });
}

async function handleModel(request: Request, env: AppEnv, user: User, modelId: string): Promise<Response> {
  if (request.method !== "DELETE") return failure("method_not_allowed", "Method not allowed.", 405);
  const active = await env.DB.prepare(
    "SELECT id FROM jobs WHERE owner_id = ? AND resource_id = ? AND status IN ('queued', 'running') LIMIT 1",
  ).bind(user.id, modelId).first();
  if (active) return failure("model_busy", "Wait for the active job before deleting this model.", 409);
  await env.DB.prepare("UPDATE models SET status = 'deleted', updated_at = ? WHERE id = ? AND owner_id = ?")
    .bind(now(), modelId, user.id).run();
  return new Response(null, { status: 204 });
}

async function callModal(url: string, env: AppEnv, body: JsonObject): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(env.MODAL_KEY ? { "Modal-Key": env.MODAL_KEY } : {}),
      ...(env.MODAL_SECRET ? { "Modal-Secret": env.MODAL_SECRET } : {}),
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(60_000),
  });
}

async function handleCheckout(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method !== "POST") return failure("method_not_allowed", "Method not allowed.", 405);
  if (env.DEV_AUTH === "1" && (!env.STRIPE_SECRET_KEY || !env.STRIPE_TRAINING_PRICE_ID)) {
    const entitlementId = id("entitlement");
    const timestamp = now();
    await env.DB.batch([
      env.DB.prepare(
        "INSERT INTO entitlements (id, owner_id, kind, status, created_at, updated_at) VALUES (?, ?, 'training', 'available', ?, ?)",
      ).bind(entitlementId, user.id, timestamp, timestamp),
      env.DB.prepare(
        "INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) VALUES (?, ?, 20, 'training_bundle', ?, ?)",
      ).bind(id("credit"), user.id, entitlementId, timestamp),
    ]);
    return response({ granted: true, entitlement_id: entitlementId, generation_credits: 20 });
  }
  if (!env.STRIPE_SECRET_KEY || !env.STRIPE_TRAINING_PRICE_ID) {
    return failure("billing_unavailable", "Training checkout is not configured yet.", 503);
  }
  const origin = new URL(request.url).origin;
  const form = new URLSearchParams({
    mode: "payment",
    "line_items[0][price]": env.STRIPE_TRAINING_PRICE_ID,
    "line_items[0][quantity]": "1",
    success_url: `${origin}/beta?checkout=success`,
    cancel_url: `${origin}/beta?checkout=cancelled`,
    client_reference_id: user.id,
    "metadata[owner_id]": user.id,
    "metadata[kind]": "training",
  });
  const stripe = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: { authorization: `Bearer ${env.STRIPE_SECRET_KEY}`, "content-type": "application/x-www-form-urlencoded" },
    body: form,
  });
  const result = await stripe.json() as { url?: string; error?: { message?: string } };
  if (!stripe.ok || !result.url) return failure("checkout_failed", result.error?.message || "Checkout could not start.", 502);
  return response({ url: result.url });
}

async function handleCreditCheckout(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method !== "POST") return failure("method_not_allowed", "Method not allowed.", 405);
  const body = await parseJson(request, 10_000);
  const packs = Number(body.packs);
  if (![1, 2, 5].includes(packs)) return failure("invalid_credit_pack", "Choose 20, 40, or 100 credits.", 400);
  const credits = packs * CREDIT_PACK_SIZE;
  if (env.DEV_AUTH === "1" && (!env.STRIPE_SECRET_KEY || !env.STRIPE_CREDIT_PRICE_ID)) {
    const referenceId = id("credit_purchase");
    await env.DB.prepare(
      "INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) VALUES (?, ?, ?, 'credit_purchase', ?, ?)",
    ).bind(id("credit"), user.id, credits, referenceId, now()).run();
    return response({ granted: true, generation_credits: credits });
  }
  if (!env.STRIPE_SECRET_KEY || !env.STRIPE_CREDIT_PRICE_ID) {
    return failure("billing_unavailable", "Generation-credit checkout is not configured yet.", 503);
  }
  const origin = new URL(request.url).origin;
  const form = new URLSearchParams({
    mode: "payment",
    "line_items[0][price]": env.STRIPE_CREDIT_PRICE_ID,
    "line_items[0][quantity]": String(packs),
    success_url: `${origin}/beta?checkout=credits-success`,
    cancel_url: `${origin}/beta?checkout=cancelled`,
    client_reference_id: user.id,
    "metadata[owner_id]": user.id,
    "metadata[kind]": "credits",
    "metadata[credits]": String(credits),
  });
  const stripe = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: { authorization: `Bearer ${env.STRIPE_SECRET_KEY}`, "content-type": "application/x-www-form-urlencoded" },
    body: form,
  });
  const result = await stripe.json() as { url?: string; error?: { message?: string } };
  if (!stripe.ok || !result.url) return failure("checkout_failed", result.error?.message || "Checkout could not start.", 502);
  return response({ url: result.url });
}

async function handleTraining(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method !== "POST") return failure("method_not_allowed", "Method not allowed.", 405);
  const body = await parseJson(request, 20_000);
  const revisionId = typeof body.revision_id === "string" ? body.revision_id : "";
  const name = typeof body.name === "string" ? body.name.trim().slice(0, 80) : "";
  const revision = await env.DB.prepare(
    "SELECT snapshot_key FROM corpus_revisions WHERE id = ? AND owner_id = ?",
  ).bind(revisionId, user.id).first<{ snapshot_key: string }>();
  if (!revision || !name) return failure("invalid_training", "Choose a ready corpus revision and model name.", 400);
  const entitlement = await env.DB.prepare(
    "SELECT id FROM entitlements WHERE owner_id = ? AND kind = 'training' AND status = 'available' ORDER BY created_at LIMIT 1",
  ).bind(user.id).first<{ id: string }>();
  if (!entitlement) return failure("payment_required", "Purchase a $20 training entitlement first.", 402);

  const idempotencyKey = request.headers.get("idempotency-key");
  if (idempotencyKey) {
    const existing = await env.DB.prepare(
      "SELECT id, status, resource_id FROM jobs WHERE owner_id = ? AND idempotency_key = ?",
    ).bind(user.id, idempotencyKey).first();
    if (existing) return response(existing, 200);
  }

  const modelId = id("model");
  const jobId = id("job");
  const timestamp = now();
  let providerJobId: string | null = null;
  let modelStatus = "queued";
  const snapshot = await env.FILES.get(revision.snapshot_key);
  if (!snapshot) return failure("revision_missing", "The immutable corpus revision could not be loaded.", 500);
  const chunks = await snapshot.json<unknown[]>();

  if (env.HOSTED_TRAIN_ENDPOINT) {
    const callbackUrl = env.PROVIDER_CALLBACK_SECRET
      ? `${new URL(request.url).origin}/v1/provider/training-complete`
      : undefined;
    const upstream = await callModal(env.HOSTED_TRAIN_ENDPOINT, env, {
      name: modelId,
      chunks,
      model: "Qwen/Qwen2.5-14B",
      job_id: jobId,
      ...(callbackUrl ? { callback_url: callbackUrl, callback_secret: env.PROVIDER_CALLBACK_SECRET } : {}),
    });
    const result = await upstream.json() as { call_id?: string; detail?: string };
    if (!upstream.ok || !result.call_id) return failure("training_unavailable", result.detail || "Training could not be queued.", 502);
    providerJobId = result.call_id;
  } else if (env.DEV_AUTH === "1") {
    modelStatus = "ready";
  } else {
    return failure("training_unavailable", "The training provider is not configured.", 503);
  }

  await env.DB.batch([
    env.DB.prepare(
      "INSERT INTO models (id, owner_id, revision_id, name, status, provider, provider_model, adapter_path, trained_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'modal', 'Qwen/Qwen2.5-14B', ?, ?, ?, ?)",
    ).bind(modelId, user.id, revisionId, name, modelStatus, modelStatus === "ready" ? `/voices/${modelId}` : null, modelStatus === "ready" ? timestamp : null, timestamp, timestamp),
    env.DB.prepare(
      "INSERT INTO jobs (id, owner_id, kind, status, resource_id, provider_job_id, request, idempotency_key, created_at, updated_at) VALUES (?, ?, 'training', ?, ?, ?, ?, ?, ?, ?)",
    ).bind(jobId, user.id, modelStatus === "ready" ? "completed" : "queued", modelId, providerJobId, JSON.stringify({ revision_id: revisionId, name }), idempotencyKey, timestamp, timestamp),
    env.DB.prepare("UPDATE entitlements SET status = 'consumed', consumed_by = ?, updated_at = ? WHERE id = ? AND owner_id = ?")
      .bind(jobId, timestamp, entitlement.id, user.id),
  ]);
  return response({ id: jobId, status: modelStatus === "ready" ? "completed" : "queued", model_id: modelId }, 202, { location: `/v1/jobs/${jobId}` });
}

async function handleGeneration(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method !== "POST") return failure("method_not_allowed", "Method not allowed.", 405);
  const body = await parseJson(request, 100_000);
  const idempotencyKey = request.headers.get("idempotency-key");
  if (idempotencyKey) {
    const existing = await env.DB.prepare(
      "SELECT id, status, result FROM jobs WHERE owner_id = ? AND idempotency_key = ?",
    ).bind(user.id, idempotencyKey).first<{ id: string; status: string; result: string | null }>();
    if (existing) return response({ id: existing.id, status: existing.status, ...(existing.result ? { result: JSON.parse(existing.result) } : {}) });
  }
  const modelId = typeof body.model_id === "string" ? body.model_id : "";
  const operations = ["write", "continue", "rewrite", "edit_span", "revoice"];
  const operation = operations.includes(String(body.operation)) ? String(body.operation) : "write";
  const mode = body.mode === "edited" || operation === "edit_span" ? "edited" : "raw";
  const corrections = Array.isArray(body.corrections)
    ? body.corrections.filter((item): item is string => typeof item === "string").slice(0, 20)
    : [];
  const notes = Array.isArray(body.notes) ? body.notes.filter((note): note is string => typeof note === "string" && Boolean(note.trim())).slice(0, 12) : [];
  const text = typeof body.text === "string" ? body.text : "";
  const precedingText = typeof body.preceding_text === "string" ? body.preceding_text : "";
  if (operation === "write" && !notes.length) return failure("invalid_generation", "Write requires at least one factual note.", 400);
  if (operation === "continue" && !notes.length && !precedingText.trim()) return failure("invalid_generation", "Continue requires notes or preceding text.", 400);
  if ((operation === "rewrite" || operation === "revoice") && !text.trim()) return failure("invalid_generation", `${operation} requires source text.`, 400);
  const selectionStart = body.selection_start;
  const selectionEnd = body.selection_end;
  const instruction = typeof body.instruction === "string" ? body.instruction.trim() : "";
  if (operation === "edit_span" && (
    !Number.isInteger(selectionStart)
    || !Number.isInteger(selectionEnd)
    || Number(selectionStart) < 0
    || Number(selectionEnd) <= Number(selectionStart)
    || Number(selectionEnd) > text.length
    || !instruction
  )) return failure("invalid_generation", "Edit span requires text, a non-empty instruction, and valid selection_start/selection_end offsets.", 400);
  const model = await env.DB.prepare(
    "SELECT id, adapter_path, provider_model, style_profile FROM models WHERE id = ? AND owner_id = ? AND status = 'ready'",
  ).bind(modelId, user.id).first<{ id: string; adapter_path: string; provider_model: string; style_profile: string | null }>();
  if (!model) return failure("model_not_ready", "Choose a ready model.", 409);
  if (await balance(env, user.id) < 1) return failure("credits_required", "Add generation credits before writing.", 402);

  const jobId = id("job");
  const timestamp = now();
  let providerJobId: string | null = null;
  let result: JsonObject | null = null;
  if (env.HOSTED_GENERATE_ENDPOINT) {
    const providerBody: JsonObject = { ...body, operation, mode };
    try {
      if (operation === "edit_span") {
        providerBody.text_before = text.slice(0, Number(selectionStart));
        providerBody.text_after = text.slice(Number(selectionEnd));
        providerBody.replacement_draft = await planSpanEdit(
          env,
          user,
          text.slice(Number(selectionStart), Number(selectionEnd)),
          instruction,
        );
      } else if ((operation === "rewrite" || operation === "revoice") && mode === "edited") {
        providerBody.text = await planLightEdit(env, user, text, corrections);
        providerBody.operation = "revoice";
      }
    } catch (error) {
      return failure("edit_planning_unavailable", error instanceof Error ? error.message : "The edit could not be planned.", 503);
    }
    const upstream = await callModal(env.HOSTED_GENERATE_ENDPOINT, env, {
      ...providerBody,
      adapter_path: model.adapter_path,
      provider_model: model.provider_model,
      style_profile: model.style_profile ? JSON.parse(model.style_profile) : null,
    });
    const data = await upstream.json() as { call_id?: string; detail?: string };
    if (!upstream.ok || !data.call_id) return failure("generation_unavailable", data.detail || "Generation could not be queued.", 502);
    providerJobId = data.call_id;
  } else if (env.DEV_AUTH === "1") {
    const rawDraft = `${notes.join(" ") || "A blank page is only blank until you decide what belongs on it."}\n\nThis is a local beta preview. The deployed model will return raw adapter prose here.`;
    const finalDraft = operation === "edit_span"
      ? `${text.slice(0, Number(selectionStart))}${text.slice(Number(selectionStart), Number(selectionEnd))}${text.slice(Number(selectionEnd))}`
      : operation === "rewrite" || operation === "revoice"
        ? text
        : rawDraft;
    result = {
      drafts: [finalDraft],
      ...(mode === "edited" && operation !== "edit_span" ? { raw_draft: rawDraft } : {}),
      mode,
      operation,
      warning: mode === "raw" ? "Raw adapter output; verify facts and grammar." : "Voiceprint wrote the final edited text; verify facts and re-score this exact artifact.",
      final_writer: "development_stub",
      finalized_by_adapter: false,
    };
  } else {
    return failure("generation_unavailable", "The generation provider is not configured.", 503);
  }

  await env.DB.batch([
    env.DB.prepare(
      "INSERT INTO jobs (id, owner_id, kind, status, resource_id, provider_job_id, request, result, idempotency_key, created_at, updated_at) VALUES (?, ?, 'generation', ?, ?, ?, ?, ?, ?, ?, ?)",
    ).bind(jobId, user.id, result ? "completed" : "queued", modelId, providerJobId, JSON.stringify({ ...body, replacement_draft: undefined, operation, mode }), result ? JSON.stringify(result) : null, idempotencyKey, timestamp, timestamp),
    env.DB.prepare(
      "INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) VALUES (?, ?, -1, 'generation', ?, ?)",
    ).bind(id("credit"), user.id, jobId, timestamp),
  ]);
  return response({ id: jobId, status: result ? "completed" : "queued", ...(result ? { result } : {}) }, result ? 200 : 202, { location: `/v1/jobs/${jobId}` });
}

async function handleAssistant(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method !== "POST") return failure("method_not_allowed", "Method not allowed.", 405);
  try {
    return response(await runWritingAssistant(env, user, await parseJson(request, 20_000)));
  } catch (error) {
    const message = error instanceof Error ? error.message : "The assistant could not prepare that request.";
    const status = message.includes("not configured") ? 503 : 400;
    return failure(status === 503 ? "assistant_unavailable" : "invalid_request", message, status);
  }
}

async function handleScore(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method !== "POST") return failure("method_not_allowed", "Method not allowed.", 405);
  const body = await parseJson(request, 120_000);
  const modelId = typeof body.model_id === "string" ? body.model_id : "";
  const text = typeof body.text === "string" ? body.text.trim() : "";
  if (!modelId || !text) return failure("invalid_score", "A model_id and exact non-empty text are required.", 400);
  const model = await env.DB.prepare(
    "SELECT style_profile FROM models WHERE id = ? AND owner_id = ? AND status = 'ready'",
  ).bind(modelId, user.id).first<{ style_profile: string | null }>();
  if (!model?.style_profile) return failure("profile_unavailable", "That model does not have a style profile.", 409);
  try {
    return response({
      scorer: "stylometry",
      score: Number(scoreStyle(JSON.parse(model.style_profile) as StyleProfile, text).toFixed(4)),
      meaning: "style_similarity",
      artifact_sha256: await digest(text),
      exact_artifact: true,
    });
  } catch (error) {
    return failure("profile_invalid", error instanceof Error ? error.message : "The style profile is invalid.", 500);
  }
}

async function handleJob(request: Request, env: AppEnv, user: User, jobId: string): Promise<Response> {
  if (request.method !== "GET") return failure("method_not_allowed", "Method not allowed.", 405);
  const job = await env.DB.prepare("SELECT * FROM jobs WHERE id = ? AND owner_id = ?")
    .bind(jobId, user.id).first<Record<string, unknown>>();
  if (!job) return failure("not_found", "Job not found.", 404);
  if (job.status === "completed" || job.status === "failed") {
    return response({ ...job, request: job.request ? JSON.parse(String(job.request)) : null, result: job.result ? JSON.parse(String(job.result)) : null });
  }
  const resultEndpoint = job.kind === "training" ? env.HOSTED_TRAIN_RESULT_ENDPOINT : env.HOSTED_GENERATE_RESULT_ENDPOINT;
  if (!resultEndpoint || !job.provider_job_id) return response({ ...job }, 202);
  const upstream = await callModal(resultEndpoint, env, { call_id: job.provider_job_id });
  if (upstream.status === 202) return response({ ...job, status: "running" }, 202);
  const result = await upstream.json() as JsonObject & { detail?: string; adapter_path?: string; profile?: JsonObject };
  if (!upstream.ok) {
    const timestamp = now();
    const statements = [
      env.DB.prepare("UPDATE jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ? AND owner_id = ?")
        .bind(result.detail || "Provider job failed.", timestamp, jobId, user.id),
    ];
    if (job.kind === "generation") {
      statements.push(env.DB.prepare(
        "INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) VALUES (?, ?, 1, 'generation_refund', ?, ?)",
      ).bind(id("credit"), user.id, jobId, timestamp));
    }
    await env.DB.batch(statements);
    return failure("job_failed", result.detail || "The job failed and any credit was restored.", 502);
  }
  const timestamp = now();
  if (job.kind === "generation") {
    const generationRequest = job.request ? JSON.parse(String(job.request)) as JsonObject : {};
    const drafts = Array.isArray(result.drafts) ? result.drafts.filter((item): item is string => typeof item === "string") : [];
    if (result.final_writer !== "voiceprint" || result.finalized_by_adapter !== true) {
      await env.DB.batch([
        env.DB.prepare("UPDATE jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ? AND owner_id = ?")
          .bind("The provider did not attest that Voiceprint wrote the final output.", timestamp, jobId, user.id),
        env.DB.prepare(
          "INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) VALUES (?, ?, 1, 'generation_refund', ?, ?)",
        ).bind(id("credit"), user.id, jobId, timestamp),
      ]);
      return failure("final_writer_unverified", "Generation was rejected because Voiceprint was not the verified final writer. The credit was restored.", 502);
    }
    const requestedOperation = typeof generationRequest.operation === "string" ? generationRequest.operation : "write";
    const needsFinalPass = generationRequest.mode === "edited"
      && (requestedOperation === "write" || requestedOperation === "continue")
      && generationRequest.finalization_stage !== "voiceprint";
    if (needsFinalPass && drafts[0]) {
      const corrections = Array.isArray(generationRequest.corrections)
        ? generationRequest.corrections.filter((item): item is string => typeof item === "string").slice(0, 20)
        : [];
      const rawDraft = drafts[0];
      try {
        if (!env.HOSTED_GENERATE_ENDPOINT) throw new Error("The Voiceprint finalization endpoint is not configured.");
        const model = await env.DB.prepare(
          "SELECT adapter_path, provider_model, style_profile FROM models WHERE id = ? AND owner_id = ? AND status = 'ready'",
        ).bind(String(job.resource_id), user.id).first<{ adapter_path: string; provider_model: string; style_profile: string | null }>();
        if (!model) throw new Error("The Voiceprint model is no longer ready.");
        const correctionDraft = await planLightEdit(env, user, rawDraft, corrections);
        const upstream = await callModal(env.HOSTED_GENERATE_ENDPOINT, env, {
          operation: "revoice",
          mode: "edited",
          length: generationRequest.length || "medium",
          text: correctionDraft,
          notes: [],
          adapter_path: model.adapter_path,
          provider_model: model.provider_model,
          style_profile: model.style_profile ? JSON.parse(model.style_profile) : null,
        });
        const queued = await upstream.json() as { call_id?: string; detail?: string };
        if (!upstream.ok || !queued.call_id) throw new Error(queued.detail || "Voiceprint finalization could not be queued.");
        const nextRequest = {
          ...generationRequest,
          finalization_stage: "voiceprint",
          raw_draft: rawDraft,
        };
        await env.DB.prepare("UPDATE jobs SET status = 'queued', provider_job_id = ?, request = ?, updated_at = ? WHERE id = ? AND owner_id = ?")
          .bind(queued.call_id, JSON.stringify(nextRequest), timestamp, jobId, user.id).run();
        return response({ ...job, status: "queued", finalization: "voiceprint" }, 202);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Voiceprint finalization failed.";
        await env.DB.batch([
          env.DB.prepare("UPDATE jobs SET status = 'failed', error = ?, updated_at = ? WHERE id = ? AND owner_id = ?")
            .bind(message, timestamp, jobId, user.id),
          env.DB.prepare(
            "INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) VALUES (?, ?, 1, 'generation_refund', ?, ?)",
          ).bind(id("credit"), user.id, jobId, timestamp),
        ]);
        return failure("finalization_failed", `${message} The credit was restored.`, 502);
      }
    }
    if (generationRequest.finalization_stage === "voiceprint") {
      result.raw_draft = generationRequest.raw_draft;
      result.warning = "Voiceprint wrote the final edited text; verify facts and re-score this exact artifact.";
    }
    result.operation = requestedOperation;
    result.mode = generationRequest.mode === "edited" ? "edited" : "raw";
  }
  if (job.kind === "training" && job.resource_id) {
    const claimed = await env.DB.prepare(
      "UPDATE jobs SET status = 'completed', result = ?, updated_at = ? WHERE id = ? AND owner_id = ? AND status != 'completed'",
    ).bind(JSON.stringify(result), timestamp, jobId, user.id).run();
    await env.DB.prepare(
      "UPDATE models SET status = 'ready', adapter_path = ?, style_profile = ?, trained_at = ?, updated_at = ? WHERE id = ? AND owner_id = ?",
    ).bind(result.adapter_path || `/voices/${job.resource_id}`, result.profile ? JSON.stringify(result.profile) : null, timestamp, timestamp, job.resource_id, user.id).run();
    if (claimed.meta.changes > 0) {
      await sendTrainingEmail(env, user.email, String(job.resource_id), new URL(request.url).origin);
    }
  } else {
    await env.DB.prepare("UPDATE jobs SET status = 'completed', result = ?, updated_at = ? WHERE id = ? AND owner_id = ?")
      .bind(JSON.stringify(result), timestamp, jobId, user.id).run();
  }
  return response({ ...job, status: "completed", result });
}

async function sendTrainingEmail(env: AppEnv, email: string, modelId: string, requestOrigin: string): Promise<void> {
  if (!env.RESEND_API_KEY || !env.EMAIL_FROM) return;
  const appUrl = (env.APP_URL || requestOrigin).replace(/\/$/, "");
  await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
      to: [email],
      subject: "Your Voiceprint model is ready",
      html: `<p>Your model is ready to write.</p><p><a href="${appUrl}/beta?model=${encodeURIComponent(modelId)}">Open Voiceprint</a></p>`,
    }),
  });
}

async function handleTrainingCallback(request: Request, env: AppEnv): Promise<Response> {
  if (request.method !== "POST") return failure("method_not_allowed", "Method not allowed.", 405);
  if (!env.PROVIDER_CALLBACK_SECRET) return failure("callback_unavailable", "Provider callback is not configured.", 503);
  const authorization = request.headers.get("authorization") || "";
  const expected = await digest(`Bearer ${env.PROVIDER_CALLBACK_SECRET}`);
  const supplied = await digest(authorization);
  if (!timingSafeEqual(expected, supplied)) return failure("unauthorized", "Invalid callback signature.", 401);

  const body = await parseJson(request, 1_000_000);
  const jobId = typeof body.job_id === "string" ? body.job_id : "";
  const result = body.result && typeof body.result === "object" && !Array.isArray(body.result)
    ? body.result as JsonObject
    : null;
  if (!jobId || !result) return failure("invalid_callback", "A job_id and result are required.", 400);
  const job = await env.DB.prepare(
    "SELECT owner_id, resource_id, status FROM jobs WHERE id = ? AND kind = 'training'",
  ).bind(jobId).first<{ owner_id: string; resource_id: string; status: string }>();
  if (!job) return failure("not_found", "Training job not found.", 404);
  if (job.status === "completed") return response({ received: true, duplicate: true });

  const account = await env.DB.prepare("SELECT email FROM users WHERE id = ?")
    .bind(job.owner_id).first<{ email: string }>();
  const timestamp = now();
  const claimed = await env.DB.prepare(
    "UPDATE jobs SET status = 'completed', result = ?, error = NULL, updated_at = ? WHERE id = ? AND status != 'completed'",
  ).bind(JSON.stringify(result), timestamp, jobId).run();
  if (claimed.meta.changes === 0) return response({ received: true, duplicate: true });
  await env.DB.prepare(
    "UPDATE models SET status = 'ready', adapter_path = ?, style_profile = ?, trained_at = ?, updated_at = ? WHERE id = ? AND owner_id = ?",
  ).bind(result.adapter_path || `/voices/${job.resource_id}`, result.profile ? JSON.stringify(result.profile) : null, timestamp, timestamp, job.resource_id, job.owner_id).run();
  if (account) await sendTrainingEmail(env, account.email, job.resource_id, new URL(request.url).origin);
  return response({ received: true });
}

async function handleStripeWebhook(request: Request, env: AppEnv): Promise<Response> {
  if (!env.STRIPE_WEBHOOK_SECRET) return failure("webhook_unavailable", "Stripe webhook is not configured.", 503);
  const signature = request.headers.get("stripe-signature") || "";
  const parts = Object.fromEntries(signature.split(",").map((part) => part.split("=", 2)));
  const timestamp = Number(parts.t);
  const supplied = parts.v1;
  const raw = await request.text();
  if (!timestamp || !supplied || Math.abs(Date.now() / 1000 - timestamp) > 300) return failure("invalid_signature", "Invalid webhook signature.", 400);
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.STRIPE_WEBHOOK_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signed = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${timestamp}.${raw}`));
  const expected = Array.from(new Uint8Array(signed), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (expected.length !== supplied.length || !timingSafeEqual(expected, supplied)) return failure("invalid_signature", "Invalid webhook signature.", 400);
  const event = JSON.parse(raw) as {
    type?: string;
    data?: { object?: { id?: string; payment_status?: string; metadata?: Record<string, string> } };
  };
  if (["checkout.session.completed", "checkout.session.async_payment_succeeded"].includes(event.type || "")) {
    const session = event.data?.object;
    const ownerId = session?.metadata?.owner_id;
    if (ownerId && session?.id && session.payment_status === "paid") {
      const timestampNow = now();
      if (session.metadata?.kind === "training") {
        await env.DB.batch([
          env.DB.prepare(
            "INSERT INTO entitlements (id, owner_id, kind, status, stripe_session_id, created_at, updated_at) SELECT ?, ?, 'training', 'available', ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM entitlements WHERE stripe_session_id = ?)",
          ).bind(id("entitlement"), ownerId, session.id, timestampNow, timestampNow, session.id),
          env.DB.prepare(
            "INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) SELECT ?, ?, 20, 'training_bundle', ?, ? WHERE NOT EXISTS (SELECT 1 FROM credit_ledger WHERE owner_id = ? AND kind = 'training_bundle' AND reference_id = ?)",
          ).bind(id("credit"), ownerId, session.id, timestampNow, ownerId, session.id),
        ]);
      } else if (session.metadata?.kind === "credits") {
        const credits = Number(session.metadata.credits);
        if ([20, 40, 100].includes(credits)) {
          await env.DB.prepare(
            "INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) SELECT ?, ?, ?, 'credit_purchase', ?, ? WHERE NOT EXISTS (SELECT 1 FROM credit_ledger WHERE owner_id = ? AND kind = 'credit_purchase' AND reference_id = ?)",
          ).bind(id("credit"), ownerId, credits, session.id, timestampNow, ownerId, session.id).run();
        }
      }
    }
  }
  return response({ received: true });
}

async function handleAdmin(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (request.method !== "GET") return failure("method_not_allowed", "Method not allowed.", 405);
  const allowed = (env.ADMIN_EMAILS || "").split(",").map((email) => email.trim().toLowerCase()).filter(Boolean);
  if (!allowed.includes(user.email.toLowerCase())) return failure("forbidden", "Admin access required.", 403);
  const [users, models, jobs, credits] = await Promise.all([
    env.DB.prepare("SELECT COUNT(*) AS value FROM users").first<{ value: number }>(),
    env.DB.prepare("SELECT status, COUNT(*) AS value FROM models GROUP BY status").all(),
    env.DB.prepare("SELECT id, owner_id, kind, status, resource_id, error, created_at, updated_at FROM jobs ORDER BY updated_at DESC LIMIT 100").all(),
    env.DB.prepare("SELECT COALESCE(SUM(delta), 0) AS value FROM credit_ledger").first<{ value: number }>(),
  ]);
  return response({ users: Number(users?.value || 0), models: models.results, jobs: jobs.results, outstanding_credits: Number(credits?.value || 0) });
}

function requiredScopes(pathname: string, method: string): string[] {
  if (pathname.startsWith("/v1/corpora")) return [method === "GET" ? "corpora:read" : "corpora:write"];
  if (pathname === "/v1/models") return ["models:read"];
  if (/^\/v1\/models\//.test(pathname) || pathname === "/v1/training-jobs") return ["models:write"];
  if (pathname === "/v1/generations" || pathname === "/v1/assistant") return ["generate"];
  if (pathname === "/v1/scores") return ["scores:write"];
  if (/^\/v1\/jobs\//.test(pathname)) return ["jobs:read"];
  return [];
}

function timingSafeEqual(left: string, right: string): boolean {
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) mismatch |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return mismatch === 0;
}

async function handleDevSeed(request: Request, env: AppEnv, user: User): Promise<Response> {
  if (env.DEV_AUTH !== "1") return failure("not_found", "Not found.", 404);
  const timestamp = now();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO credit_ledger (id, owner_id, delta, kind, reference_id, created_at) VALUES (?, ?, 25, 'beta_seed', NULL, ?)")
      .bind(id("credit"), user.id, timestamp),
    env.DB.prepare("INSERT INTO entitlements (id, owner_id, kind, status, created_at, updated_at) VALUES (?, ?, 'training', 'available', ?, ?)")
      .bind(id("entitlement"), user.id, timestamp, timestamp),
  ]);
  return response({ seeded: true, credits: await balance(env, user.id) });
}

export async function handleApi(request: Request, env: AppEnv): Promise<Response | null> {
  const url = new URL(request.url);
  if (!url.pathname.startsWith("/v1/")) return null;
  if (!env.DB || !env.FILES) return failure("not_configured", "Storage is not configured.", 503);
  await ensureAppSchema(env.DB);

  if (url.pathname === "/v1/webhooks/stripe" && request.method === "POST") {
    return handleStripeWebhook(request, env);
  }
  if (url.pathname === "/v1/provider/training-complete") {
    return handleTrainingCallback(request, env);
  }

  const authenticated = await requireUser(request, env, requiredScopes(url.pathname, request.method));
  if (isResponse(authenticated)) return authenticated;
  const user = authenticated;

  if (["/v1/me", "/v1/checkout/training", "/v1/checkout/credits", "/v1/api-keys", "/v1/admin/overview", "/v1/dev/seed"].includes(url.pathname) && !user.scopes.includes("*")) {
    return failure("session_required", "Use the signed-in workspace for this endpoint.", 403);
  }

  if (url.pathname === "/v1/me") return handleProfile(request, env, user);
  if (url.pathname === "/v1/corpora") return handleCorpora(request, env, user);
  if (url.pathname === "/v1/models") return handleModels(request, env, user);
  if (url.pathname === "/v1/credits" && request.method === "GET") return response({ balance: await balance(env, user.id) });
  if (url.pathname === "/v1/training-quotes" && request.method === "POST") return response({ currency: "usd", amount: TRAINING_PRICE_CENTS, includes_generation_credits: 20 });
  if (url.pathname === "/v1/checkout/training") return handleCheckout(request, env, user);
  if (url.pathname === "/v1/checkout/credits") return handleCreditCheckout(request, env, user);
  if (url.pathname === "/v1/training-jobs") return handleTraining(request, env, user);
  if (url.pathname === "/v1/generations") return handleGeneration(request, env, user);
  if (url.pathname === "/v1/assistant") return handleAssistant(request, env, user);
  if (url.pathname === "/v1/scores") return handleScore(request, env, user);
  if (url.pathname === "/v1/api-keys") return handleApiKeys(request, env, user);
  if (url.pathname === "/v1/admin/overview") return handleAdmin(request, env, user);
  if (url.pathname === "/v1/dev/seed" && request.method === "POST") return handleDevSeed(request, env, user);

  const corpusMatch = url.pathname.match(/^\/v1\/corpora\/([^/]+)(?:\/(text|inspect|revisions))?$/);
  if (corpusMatch) return handleCorpus(request, env, user, corpusMatch[1], corpusMatch[2]);
  const itemMatch = url.pathname.match(/^\/v1\/corpora\/([^/]+)\/items\/([^/]+)$/);
  if (itemMatch && request.method === "DELETE") {
    const item = await env.DB.prepare("SELECT storage_key FROM corpus_items WHERE id = ? AND corpus_id = ? AND owner_id = ?")
      .bind(itemMatch[2], itemMatch[1], user.id).first<{ storage_key: string }>();
    if (!item) return failure("not_found", "Corpus item not found.", 404);
    await env.FILES.delete(item.storage_key);
    await env.DB.prepare("DELETE FROM corpus_items WHERE id = ? AND corpus_id = ? AND owner_id = ?")
      .bind(itemMatch[2], itemMatch[1], user.id).run();
    await inspectAndPersist(env, user.id, itemMatch[1]);
    return new Response(null, { status: 204 });
  }
  const modelMatch = url.pathname.match(/^\/v1\/models\/([^/]+)$/);
  if (modelMatch) return handleModel(request, env, user, modelMatch[1]);
  const keyMatch = url.pathname.match(/^\/v1\/api-keys\/([^/]+)$/);
  if (keyMatch) {
    if (!user.scopes.includes("*")) return failure("session_required", "Use the signed-in workspace for this endpoint.", 403);
    return handleApiKey(request, env, user, keyMatch[1]);
  }
  const jobMatch = url.pathname.match(/^\/v1\/jobs\/([^/]+)$/);
  if (jobMatch) return handleJob(request, env, user, jobMatch[1]);
  return failure("not_found", "Endpoint not found.", 404);
}
