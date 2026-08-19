/** Cloudflare Worker entry point for the vinext-starter template. */
import { handleImageOptimization, DEFAULT_DEVICE_SIZES, DEFAULT_IMAGE_SIZES } from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";
import { handleApi, type AppEnv } from "./api";

interface Env extends AppEnv {
  ASSETS: Fetcher;
  MODAL_ENDPOINT: string;
  MODAL_RESULT_ENDPOINT: string;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

const PER_IP_DAILY_LIMIT = 3;
const GLOBAL_DAILY_LIMIT = 40;

const CREATE_USAGE_TABLE = `CREATE TABLE IF NOT EXISTS usage (
  scope TEXT NOT NULL,
  day TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (scope, day)
)`;

const TAKE_QUOTA = `INSERT INTO usage (scope, day, count)
VALUES (?, ?, 1)
ON CONFLICT(scope, day) DO UPDATE SET count = count + 1
WHERE count < ?
RETURNING count`;

async function hashIp(ip: string): Promise<string> {
  const bytes = new TextEncoder().encode(ip);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function json(body: object, status = 200): Response {
  return Response.json(body, {
    status,
    headers: { "cache-control": "no-store" },
  });
}

async function giveBackQuota(env: Env, scopes: string[], day: string) {
  await env.DB.batch(
    scopes.map((scope) =>
      env.DB.prepare("UPDATE usage SET count = MAX(0, count - 1) WHERE scope = ? AND day = ?")
        .bind(scope, day),
    ),
  );
}

async function generate(request: Request, env: Env): Promise<Response> {
  if (!env.DB || !env.MODAL_ENDPOINT || !env.MODAL_RESULT_ENDPOINT || !env.MODAL_KEY || !env.MODAL_SECRET) {
    return json({ error: "The demo is not configured yet." }, 503);
  }
  if (Number(request.headers.get("content-length") || 0) > 4_000) {
    return json({ error: "The request is too large." }, 413);
  }

  let input: { brief?: unknown; length?: unknown };
  try {
    input = await request.json();
  } catch {
    return json({ error: "Send a JSON brief." }, 400);
  }
  if (typeof input.brief !== "string" || input.brief.trim().length < 20 || input.brief.length > 1_200) {
    return json({ error: "Use a brief between 20 and 1,200 characters." }, 400);
  }
  if (input.length !== "short" && input.length !== "medium") {
    return json({ error: "Choose a short or medium draft." }, 400);
  }

  await env.DB.prepare(CREATE_USAGE_TABLE).run();
  const day = new Date().toISOString().slice(0, 10);
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  const ipScope = `ip:${await hashIp(ip)}`;
  const globalScope = "global";

  const personal = await env.DB.prepare(TAKE_QUOTA)
    .bind(ipScope, day, PER_IP_DAILY_LIMIT)
    .first<{ count: number }>();
  if (!personal) {
    return json({ error: "You’ve used today’s three demo runs. Try again tomorrow." }, 429);
  }
  const global = await env.DB.prepare(TAKE_QUOTA)
    .bind(globalScope, day, GLOBAL_DAILY_LIMIT)
    .first<{ count: number }>();
  if (!global) {
    await giveBackQuota(env, [ipScope], day);
    return json({ error: "The public demo has reached today’s budget. Try again tomorrow." }, 429);
  }

  try {
    const upstream = await fetch(env.MODAL_ENDPOINT, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "Modal-Key": env.MODAL_KEY,
        "Modal-Secret": env.MODAL_SECRET,
      },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(8 * 60 * 1_000),
    });
    const data = await upstream.json() as { call_id?: string; detail?: string };
    if (!upstream.ok || !data.call_id) {
      await giveBackQuota(env, [ipScope, globalScope], day);
      return json({ error: data.detail || "The model could not start that draft." }, 502);
    }
    return json({ jobId: data.call_id, remaining: PER_IP_DAILY_LIMIT - personal.count }, 202);
  } catch {
    await giveBackQuota(env, [ipScope, globalScope], day);
    return json({ error: "The model could not start. Your run was not charged." }, 504);
  }
}

async function poll(request: Request, env: Env): Promise<Response> {
  if (!env.MODAL_RESULT_ENDPOINT || !env.MODAL_KEY || !env.MODAL_SECRET) {
    return json({ error: "The demo is not configured yet." }, 503);
  }
  const callId = new URL(request.url).searchParams.get("job");
  if (!callId || !/^fc-[A-Za-z0-9_-]+$/.test(callId)) {
    return json({ error: "Invalid job id." }, 400);
  }
  try {
    const upstream = await fetch(env.MODAL_RESULT_ENDPOINT, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "Modal-Key": env.MODAL_KEY,
        "Modal-Secret": env.MODAL_SECRET,
      },
      body: JSON.stringify({ call_id: callId }),
      signal: AbortSignal.timeout(20_000),
    });
    const data = await upstream.json() as { drafts?: string[]; detail?: string; status?: string };
    if (upstream.status === 202) {
      return json({ status: "pending" }, 202);
    }
    if (!upstream.ok || !data.drafts?.length) {
      return json({ error: data.detail || "The model could not finish that draft." }, 502);
    }
    return json({ drafts: data.drafts });
  } catch {
    return json({ status: "pending" }, 202);
  }
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

// Image security config. SVG sources with .svg extension auto-skip the
// optimization endpoint on the client side (served directly, no proxy).
// To route SVGs through the optimizer (with security headers), set
// dangerouslyAllowSVG: true in next.config.js and uncomment below:
// const imageConfig: ImageConfig = { dangerouslyAllowSVG: true };

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    const apiResponse = await handleApi(request, env);
    if (apiResponse) return apiResponse;

    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      return handleImageOptimization(request, {
        fetchAsset: (path) => env.ASSETS.fetch(new Request(new URL(path, request.url))),
        transformImage: async (body, { width, format, quality }) => {
          const result = await env.IMAGES.input(body).transform(width > 0 ? { width } : {}).output({ format, quality });
          return result.response();
        },
      }, allowedWidths);
    }

    if (url.pathname === "/api/generate") {
      if (request.method === "POST") {
        return generate(request, env);
      }
      if (request.method === "GET") {
        return poll(request, env);
      }
      return json({ error: "Method not allowed." }, 405);
    }

    return handler.fetch(request, env, ctx);
  },
};

export default worker;
