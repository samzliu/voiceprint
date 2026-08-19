# Voiceprint site

The public demo and protected 25-writer beta for [Voiceprint](https://github.com/samzliu/voiceprint).

It is a vinext application deployed on Sites. The Worker at `worker/index.ts`
enforces public-demo quotas and the beta capability API in D1. Corpora and immutable
training revisions live in R2. Modal credentials and all other secrets live in the
hosting environment, never in the browser or repository.

## Develop

Requires Node.js 22.13 or newer.

```bash
npm ci
VOICEPRINT_DEV_AUTH=1 npm run dev
```

`VOICEPRINT_DEV_AUTH=1` creates an isolated local beta writer. Production must never
set `DEV_AUTH=1`.

For local provider testing, prefix each production binding with `VOICEPRINT_`
(for example, `VOICEPRINT_PROVIDER_CALLBACK_SECRET`). These values are passed only
to the local Worker runtime; `.env*` files remain ignored.

Production bindings and secrets:

- D1 binding `DB` and R2 binding `FILES`
- public demo: `MODAL_ENDPOINT`, `MODAL_RESULT_ENDPOINT`, `MODAL_KEY`, `MODAL_SECRET`
- beta training: `HOSTED_TRAIN_ENDPOINT`, `HOSTED_TRAIN_RESULT_ENDPOINT`
- beta generation: `HOSTED_GENERATE_ENDPOINT`, `HOSTED_GENERATE_RESULT_ENDPOINT`
- signed training completion: `PROVIDER_CALLBACK_SECRET` (16+ random characters), `APP_URL`
- checkout: `STRIPE_SECRET_KEY`, `STRIPE_TRAINING_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`
- guided requests and edited mode: `AI_GATEWAY_API_KEY`; optional `ROUTER_MODEL`
- completion email: `RESEND_API_KEY`, `EMAIL_FROM`
- operations: comma-separated `ADMIN_EMAILS`

The current verified default router is `openai/gpt-5.6-luna`. Override it with a
current AI Gateway model ID without changing application code.

## Verify

```bash
npm run lint
npm test
npx tsc --noEmit
```

`npm test` builds the production Worker and verifies all server-rendered routes.
`npm audit --omit=dev` should report zero production advisories. The remaining
development-only audit entries originate in `drizzle-kit`'s legacy code-generation
loader; it is not bundled into the Worker.
