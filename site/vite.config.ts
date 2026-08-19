import vinext from "vinext";
import { defineConfig } from "vite";
import hostingConfig from "./.openai/hosting.json" with { type: "json" };
import { sites } from "./build/sites-vite-plugin.ts";

const SITE_CREATOR_PLACEHOLDER_DATABASE_ID =
  "00000000-0000-4000-8000-000000000000";

const { d1, r2 } = hostingConfig;

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

const localBindingConfig = {
  main: "./worker/index.ts",
  compatibility_flags: ["nodejs_compat"],
  vars: {
    DEV_AUTH: process.env.VOICEPRINT_DEV_AUTH ?? "0",
    ADMIN_EMAILS: process.env.VOICEPRINT_ADMIN_EMAILS ?? "",
    PROVIDER_CALLBACK_SECRET: process.env.VOICEPRINT_PROVIDER_CALLBACK_SECRET ?? "",
    APP_URL: process.env.VOICEPRINT_APP_URL ?? "",
    STRIPE_SECRET_KEY: process.env.VOICEPRINT_STRIPE_SECRET_KEY ?? "",
    STRIPE_TRAINING_PRICE_ID: process.env.VOICEPRINT_STRIPE_TRAINING_PRICE_ID ?? "",
    STRIPE_WEBHOOK_SECRET: process.env.VOICEPRINT_STRIPE_WEBHOOK_SECRET ?? "",
    MODAL_KEY: process.env.VOICEPRINT_MODAL_KEY ?? "",
    MODAL_SECRET: process.env.VOICEPRINT_MODAL_SECRET ?? "",
    MODAL_ENDPOINT: process.env.VOICEPRINT_MODAL_ENDPOINT ?? "",
    MODAL_RESULT_ENDPOINT: process.env.VOICEPRINT_MODAL_RESULT_ENDPOINT ?? "",
    HOSTED_TRAIN_ENDPOINT: process.env.VOICEPRINT_HOSTED_TRAIN_ENDPOINT ?? "",
    HOSTED_TRAIN_RESULT_ENDPOINT: process.env.VOICEPRINT_HOSTED_TRAIN_RESULT_ENDPOINT ?? "",
    HOSTED_GENERATE_ENDPOINT: process.env.VOICEPRINT_HOSTED_GENERATE_ENDPOINT ?? "",
    HOSTED_GENERATE_RESULT_ENDPOINT: process.env.VOICEPRINT_HOSTED_GENERATE_RESULT_ENDPOINT ?? "",
    RESEND_API_KEY: process.env.VOICEPRINT_RESEND_API_KEY ?? "",
    EMAIL_FROM: process.env.VOICEPRINT_EMAIL_FROM ?? "",
    AI_GATEWAY_API_KEY: process.env.VOICEPRINT_AI_GATEWAY_API_KEY ?? "",
    ROUTER_MODEL: process.env.VOICEPRINT_ROUTER_MODEL ?? "",
  },
  d1_databases: d1
    ? [
        {
          binding: d1,
          database_name: "site-creator-d1",
          database_id: SITE_CREATOR_PLACEHOLDER_DATABASE_ID,
        },
      ]
    : [],
  r2_buckets: r2
    ? [
        {
          binding: r2,
          bucket_name: "site-creator-r2",
        },
      ]
    : [],
};

export default defineConfig(async () => {
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
        config: localBindingConfig,
      }),
    ],
  };
});
