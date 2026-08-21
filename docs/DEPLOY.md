# Deploying Voiceprint

Two independent tiers. Deploy Modal first (the site needs its endpoint URLs).

- **GPU tier — Modal** (`voiceprint/modal_app.py`): training + generation.
- **Web tier — Cloudflare Workers** (`site/`): vinext app, D1 database, R2 storage.
  Deployed directly with `wrangler` (no OpenAI Sites).

External services: **Stripe** (billing), **Postmark** (email), **Vercel AI Gateway** (model router).

---

## 1. Modal (GPU tier)

```bash
cd /Users/samzliu/code/voiceprint
uv sync                       # or: pip install -e .
modal token new               # one-time browser auth
modal deploy voiceprint/modal_app.py
```

`modal deploy` prints the web endpoint URLs. Map them to the site secrets:
train kickoff -> HOSTED_TRAIN_ENDPOINT, result -> HOSTED_TRAIN_RESULT_ENDPOINT,
generate -> HOSTED_GENERATE_ENDPOINT / HOSTED_GENERATE_RESULT_ENDPOINT, and the
public-demo pair -> MODAL_ENDPOINT / MODAL_RESULT_ENDPOINT. MODAL_KEY/MODAL_SECRET
come from Modal dashboard -> Settings -> API Tokens.

## 2. Cloudflare resources (one-time)

```bash
cd site
npx wrangler login

# D1 database — copy the printed database_id into wrangler.jsonc (<<<CLOUDFLARE_D1_DATABASE_ID>>>)
npx wrangler d1 create voiceprint

# R2 bucket — name must match wrangler.jsonc ("voiceprint-files")
npx wrangler r2 bucket create voiceprint-files
```

The app self-creates its tables at runtime (`ensureAppSchema`), so migrations are
optional. To apply them explicitly:

```bash
npx wrangler d1 migrations apply voiceprint --remote
```

## 3. Authentication (magic-link email)

Users sign in with a one-time email link (no passwords, no third-party IdP).
`POST /v1/auth/request {email}` -> emailed link -> `GET /v1/auth/callback` sets a
30-day HttpOnly session cookie. Sessions and login tokens live in D1.

Implications:
- **Postmark is now required for production sign-in**, not just completion emails.
  Verify the sender domain in Postmark and set `EMAIL_FROM` to an address on it (e.g. voiceprint@joinstash.ai).
- `APP_URL` must be the real public origin — the magic link is built from it.
- If Postmark is unset, `/v1/auth/request` returns the link in its JSON response
  (`dev_link`) so local testing works without email. This is disabled the moment
  `POSTMARK_SERVER_TOKEN` + `EMAIL_FROM` are set.

## 4. Stripe (TEST MODE while under test)

Use test keys (`sk_test_...`) — a separate/related product must not share another
product's live key or its checkouts/webhooks commingle into that account.

1. Create two Prices in the Stripe dashboard (test mode): one for training, one
   for the generation-credit pack. Copy the `price_...` IDs.
2. Add a webhook endpoint -> `https://<APP_URL>/v1/webhooks/stripe`, events
   `checkout.session.completed` and `checkout.session.async_payment_succeeded`.
   Copy the signing secret (`whsec_...`).

## 5. Secrets

```bash
cd site
for KEY in APP_URL ADMIN_EMAILS PROVIDER_CALLBACK_SECRET \
  STRIPE_SECRET_KEY STRIPE_TRAINING_PRICE_ID STRIPE_CREDIT_PRICE_ID STRIPE_WEBHOOK_SECRET \
  MODAL_KEY MODAL_SECRET MODAL_ENDPOINT MODAL_RESULT_ENDPOINT \
  HOSTED_TRAIN_ENDPOINT HOSTED_TRAIN_RESULT_ENDPOINT \
  HOSTED_GENERATE_ENDPOINT HOSTED_GENERATE_RESULT_ENDPOINT \
  POSTMARK_SERVER_TOKEN EMAIL_FROM AI_GATEWAY_API_KEY ROUTER_MODEL; do
    npx wrangler secret put "$KEY"
done
```

`PROVIDER_CALLBACK_SECRET`: generate with `openssl rand -hex 24`. Never set
`DEV_AUTH=1` in production.

## 6. Build & deploy the web tier

```bash
cd site
npm ci
npm run build          # emits ./dist (Worker + client assets)
npx wrangler deploy    # uses site/wrangler.jsonc
```

## 7. Post-deploy checks

- `curl https://<APP_URL>/` returns 200.
- Sign in: request a link at /beta, click the email, land signed-in.
- Trigger a test Stripe checkout; confirm the webhook records an entitlement.
- Run one beta training + generation end-to-end against Modal.
