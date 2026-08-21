import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { pathToFileURL } from "node:url";
import { build } from "esbuild";

let handleApi;
let env;
let temporaryDirectory;

class MemoryStatement {
  constructor(database, sql) {
    this.database = database;
    this.sql = sql;
    this.values = [];
  }

  bind(...values) {
    this.values = values;
    return this;
  }

  run() { return this.database.execute(this.sql, this.values, "run"); }
  first() { return this.database.execute(this.sql, this.values, "first"); }
  all() { return this.database.execute(this.sql, this.values, "all"); }
}

class MemoryD1 {
  constructor() {
    this.users = new Map();
    this.credits = [];
  }

  prepare(sql) { return new MemoryStatement(this, sql); }
  async batch(statements) { return Promise.all(statements.map((statement) => statement.run())); }

  async execute(sql, values, operation) {
    if (/^CREATE (?:UNIQUE )?(TABLE|INDEX)/.test(sql)) return { success: true, meta: { changes: 0 } };
    if (sql.startsWith("INSERT INTO users")) {
      this.users.set(values[0], { id: values[0], email: values[1], name: values[2] });
      return { success: true, meta: { changes: 1 } };
    }
    if (sql.includes("SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger")) {
      return { balance: this.credits.filter((entry) => entry.ownerId === values[0]).reduce((sum, entry) => sum + entry.delta, 0) };
    }
    if (sql.startsWith("INSERT INTO credit_ledger") && sql.includes("'credit_purchase'")) {
      const selectedInsert = sql.includes("SELECT ?, ?, ?, 'credit_purchase'");
      const entry = {
        id: values[0],
        ownerId: values[1],
        delta: Number(values[2]),
        kind: "credit_purchase",
        referenceId: values[3],
      };
      const duplicate = selectedInsert && this.credits.some((candidate) =>
        candidate.ownerId === entry.ownerId && candidate.kind === entry.kind && candidate.referenceId === entry.referenceId,
      );
      if (!duplicate) this.credits.push(entry);
      return { success: true, meta: { changes: duplicate ? 0 : 1 } };
    }
    throw new Error(`Unexpected ${operation} query in credit checkout test: ${sql}`);
  }
}

before(async () => {
  temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), "voiceprint-api-test-"));
  const outfile = path.join(temporaryDirectory, "api.cjs");
  await build({ entryPoints: ["worker/api.ts"], bundle: true, format: "cjs", platform: "node", outfile });
  ({ handleApi } = await import(pathToFileURL(outfile).href));

  env = {
    DB: new MemoryD1(),
    FILES: {},
    DEV_AUTH: "1",
  };
});

after(async () => {
  if (temporaryDirectory) await rm(temporaryDirectory, { recursive: true, force: true });
});

async function post(pathname, body, targetEnv = env) {
  return handleApi(new Request(`https://voiceprint.test${pathname}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }), targetEnv);
}

async function balance() {
  const response = await handleApi(new Request("https://voiceprint.test/v1/credits"), env);
  return (await response.json()).balance;
}

async function stripeSignature(secret, timestamp, raw) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${timestamp}.${raw}`));
  return Array.from(new Uint8Array(signature), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sendWebhook(event, secret = "test_webhook_secret") {
  const raw = JSON.stringify(event);
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = await stripeSignature(secret, timestamp, raw);
  return handleApi(new Request("https://voiceprint.test/v1/webhooks/stripe", {
    method: "POST",
    headers: { "content-type": "application/json", "stripe-signature": `t=${timestamp},v1=${signature}` },
    body: raw,
  }), { ...env, STRIPE_WEBHOOK_SECRET: secret });
}

test("development checkout grants a flat top-up in dev mode", async () => {
  const startingBalance = await balance();
  const response = await post("/v1/checkout/credits", {});
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { granted: true, amount_cents: 1000 });
  assert.equal(await balance(), startingBalance + 1000);
});

test("Stripe credit checkout uses a sliding-scale price with quantity 1", async () => {
  const originalFetch = globalThis.fetch;
  let submitted;
  globalThis.fetch = async (_url, options) => {
    submitted = new URLSearchParams(options.body);
    return Response.json({ url: "https://checkout.stripe.test/session" });
  };
  try {
    const response = await post("/v1/checkout/credits", {}, {
      ...env,
      STRIPE_SECRET_KEY: "sk_test",
      STRIPE_CREDIT_PRICE_ID: "price_credits",
    });
    assert.equal(response.status, 200);
    assert.equal((await response.json()).url, "https://checkout.stripe.test/session");
    assert.equal(submitted.get("line_items[0][quantity]"), "1");
    assert.equal(submitted.get("metadata[kind]"), "credits");
    assert.equal(submitted.get("metadata[credits]"), null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("webhooks grant the paid amount once and ignore unpaid sessions", async () => {
  const startingBalance = await balance();
  const paid = {
    type: "checkout.session.completed",
    data: { object: { id: "cs_paid_once", payment_status: "paid", amount_total: 4000, metadata: {
      owner_id: "dev_voiceprint_user", kind: "credits",
    } } },
  };
  assert.equal((await sendWebhook(paid)).status, 200);
  assert.equal((await sendWebhook(paid)).status, 200);
  assert.equal(await balance(), startingBalance + 4000);

  const unpaid = {
    type: "checkout.session.completed",
    data: { object: { id: "cs_unpaid", payment_status: "unpaid", amount_total: 10000, metadata: {
      owner_id: "dev_voiceprint_user", kind: "credits",
    } } },
  };
  assert.equal((await sendWebhook(unpaid)).status, 200);
  assert.equal(await balance(), startingBalance + 4000);

  const delayed = {
    type: "checkout.session.async_payment_succeeded",
    data: { object: { id: "cs_delayed", payment_status: "paid", amount_total: 2000, metadata: {
      owner_id: "dev_voiceprint_user", kind: "credits",
    } } },
  };
  assert.equal((await sendWebhook(delayed)).status, 200);
  assert.equal(await balance(), startingBalance + 6000);
});
