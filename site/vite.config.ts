import vinext from "vinext";
import { defineConfig } from "vite";
import hostingConfig from "./.openai/hosting.json" with { type: "json" };
import { sites } from "./build/sites-vite-plugin.ts";

const { d1, r2 } = hostingConfig;

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

// Full application environment, sourced from VOICEPRINT_*-prefixed vars. Used
// ONLY for local dev (`npm run dev`). In production these are Cloudflare
// secrets set with `wrangler secret put`, NOT plaintext vars — so they must not
// be declared as vars in the deployed config (a secret cannot share a name with
// a var). See `deployVars` below.
const devVars = {
  DEV_AUTH: process.env.VOICEPRINT_DEV_AUTH ?? "0",
  ADMIN_EMAILS: process.env.VOICEPRINT_ADMIN_EMAILS ?? "",
  PROVIDER_CALLBACK_SECRET: process.env.VOICEPRINT_PROVIDER_CALLBACK_SECRET ?? "",
  APP_URL: process.env.VOICEPRINT_APP_URL ?? "",
  STRIPE_SECRET_KEY: process.env.VOICEPRINT_STRIPE_SECRET_KEY ?? "",
  STRIPE_TRAINING_PRICE_ID: process.env.VOICEPRINT_STRIPE_TRAINING_PRICE_ID ?? "",
  STRIPE_CREDIT_PRICE_ID: process.env.VOICEPRINT_STRIPE_CREDIT_PRICE_ID ?? "",
  STRIPE_WEBHOOK_SECRET: process.env.VOICEPRINT_STRIPE_WEBHOOK_SECRET ?? "",
  MODAL_KEY: process.env.VOICEPRINT_MODAL_KEY ?? "",
  MODAL_SECRET: process.env.VOICEPRINT_MODAL_SECRET ?? "",
  MODAL_ENDPOINT: process.env.VOICEPRINT_MODAL_ENDPOINT ?? "",
  MODAL_RESULT_ENDPOINT: process.env.VOICEPRINT_MODAL_RESULT_ENDPOINT ?? "",
  HOSTED_TRAIN_ENDPOINT: process.env.VOICEPRINT_HOSTED_TRAIN_ENDPOINT ?? "",
  HOSTED_TRAIN_RESULT_ENDPOINT: process.env.VOICEPRINT_HOSTED_TRAIN_RESULT_ENDPOINT ?? "",
  HOSTED_GENERATE_ENDPOINT: process.env.VOICEPRINT_HOSTED_GENERATE_ENDPOINT ?? "",
  HOSTED_GENERATE_RESULT_ENDPOINT: process.env.VOICEPRINT_HOSTED_GENERATE_RESULT_ENDPOINT ?? "",
  POSTMARK_SERVER_TOKEN: process.env.VOICEPRINT_POSTMARK_SERVER_TOKEN ?? "",
  EMAIL_FROM: process.env.VOICEPRINT_EMAIL_FROM ?? "",
  AI_GATEWAY_API_KEY: process.env.VOICEPRINT_AI_GATEWAY_API_KEY ?? "",
  ROUTER_MODEL: process.env.VOICEPRINT_ROUTER_MODEL ?? "",
};

// Only genuinely non-secret vars are declared in the deployed config. Everything
// else is a Cloudflare secret.
const deployVars = {
  DEV_AUTH: "0",
  ROUTER_MODEL: process.env.VOICEPRINT_ROUTER_MODEL ?? "",
};

const localBindingConfig = {
  main: "./worker/index.ts",
  compatibility_flags: ["nodejs_compat"],
  d1_databases: d1
    ? [
        {
          binding: d1,
          database_name: "voiceprint",
          database_id: "1839056e-7670-4d5d-9c51-96c1b69a341d",
        },
      ]
    : [],
  r2_buckets: r2
    ? [
        {
          binding: r2,
          bucket_name: "voiceprint-files",
        },
      ]
    : [],
};

export default defineConfig(async ({ command }) => {
  // Dev serves the full VOICEPRINT_* env for local testing; build/deploy declares
  // only non-secret vars so `wrangler secret put` can own the sensitive names.
  const vars = command === "build" ? deployVars : devVars;
  // Keep Wrangler and Miniflare state project-local. These are non-secret tool
  // settings; application environment belongs in ignored `.env*` files.
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

  // Wrangler snapshots its log path while the Cloudflare plugin is imported.
  const { cloudflare } = await import("@cloudflare/vite-plugin");

  return {
    server: isCodexSeatbeltSandbox
      ? { watch: { useFsEvents: false, usePolling: true } }
      : undefined,
    plugins: [
      vinext(),
      sites(),
      cloudflare({
        viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
        config: { ...localBindingConfig, vars },
      }),
    ],
  };
});
