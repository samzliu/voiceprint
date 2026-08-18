# Voiceprint demo

The public, rate-limited demo for [Voiceprint](https://github.com/samzliu/voiceprint).

It is a vinext application deployed on Sites. The Worker at `worker/index.ts`
enforces both per-IP and global daily quotas in D1, then calls an authenticated
Modal endpoint. Modal credentials live in the hosting environment, never in the
browser or repository.

## Develop

Requires Node.js 22.13 or newer.

```bash
npm ci
npm run dev
```

The live generation route also needs these local environment variables:

- `MODAL_ENDPOINT`
- `MODAL_KEY`
- `MODAL_SECRET`

## Verify

```bash
npm run lint
npm test
```

`npm test` builds the production Worker and verifies the server-rendered page.
