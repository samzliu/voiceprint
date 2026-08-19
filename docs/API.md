# Voiceprint API

This is the beta contract for the hosted Voiceprint service. The browser app, guided assistant,
and public API call the same capability layer. A capability must not have different validation,
billing, or authorization behavior depending on which surface invoked it.

The hosted API is implemented in the Sites worker. Provider credentials and production bindings
must be configured before training, generation, checkout, email, and the guided assistant become
available on a deployment. The local MCP tools and CLI remain supported interfaces.

## Authentication

Browser requests use the signed-in user's session. Programmatic requests use a personal API key:

```http
Authorization: Bearer vp_live_...
```

Keys are shown once, stored hashed, revocable, and scoped. Initial scopes are `corpora:read`,
`corpora:write`, `models:read`, `models:write`, `generate`, `jobs:read`, and `scores:write`.

Payment checkout stays in the browser during the beta. API clients may inspect and consume an
account's existing entitlements but cannot initiate a purchase.

## Capability map

| Capability | HTTP endpoint | Notes |
| --- | --- | --- |
| `corpus.create` | `POST /v1/corpora` | Creates metadata only |
| `corpus.add_text` | `POST /v1/corpora/{id}/text` | Adds pasted text |
| `corpus.inspect` | `POST /v1/corpora/{id}/inspect` | Deterministic; never starts a GPU |
| `corpus.create_revision` | `POST /v1/corpora/{id}/revisions` | Freezes the accepted training input |
| `corpus.delete_item` | `DELETE /v1/corpora/{id}/items/{item_id}` | Re-runs readiness after deletion |
| `training.quote` | `POST /v1/training-quotes` | Returns the current price and entitlement |
| `training.start` | `POST /v1/training-jobs` | Requires a ready immutable revision |
| `job.status` | `GET /v1/jobs/{id}` | Training or generation job status |
| `models.list` | `GET /v1/models` | Models are independent from corpora |
| `models.delete` | `DELETE /v1/models/{id}` | Explicit confirmation required |
| `generate.write` | `POST /v1/generations` | `operation=write` |
| `generate.continue` | `POST /v1/generations` | `operation=continue` |
| `generate.rewrite` | `POST /v1/generations` | `operation=rewrite` |
| `assistant.prepare` | `POST /v1/assistant` | Tool-using planner; never writes prose or spends a credit |
| `score.final` | `POST /v1/scores` | Scores the exact supplied artifact |
| `billing.balance` | `GET /v1/credits` | Read-only during beta |
| `billing.buy_credits` | `POST /v1/checkout/credits` | Browser session only; buys 20-credit increments |

## Corpus readiness

Inspection happens before checkout. The paid hosted gate currently requires 1,000 usable words and
recommends 2,000. These values are versioned policy and will be calibrated against model quality.

```json
{
  "status": "warning",
  "ready": true,
  "documents": 7,
  "usable_documents": 6,
  "raw_words": 2314,
  "usable_words": 1842,
  "chunks": 9,
  "duplicate_chunks": 1,
  "duplicate_words": 203,
  "minimum_words": 1000,
  "recommended_words": 2000,
  "reasons": [],
  "warnings": [
    "1842 usable words passed, but 2000+ usually produces a stronger voice.",
    "Removed 1 duplicate passage totaling 203 words."
  ]
}
```

`status=blocked` prevents revision creation, checkout, and training. Warnings are visible but do
not block the user. The service never edits corpus prose.

## Asynchronous jobs

Training and cold generation return `202 Accepted` with a resource ID and `Location` header.
Clients poll the returned `Location` URL. Signed outbound webhooks are intentionally deferred
until delivery retries and secret encryption are implemented; the beta does not expose a partial
webhook contract.

Every job-creating or credit-consuming request accepts an `Idempotency-Key`. Retrying the same key
returns the original resource and never consumes another entitlement.

## Delivery modes

Generation defaults to `raw`. Raw adapter prose is returned verbatim with warnings outside the
artifact. `edited` permits only factual corrections, spelling, grammar, broken syntax, and
accidental repetition. The exact final artifact is scored after any edit; a score from an earlier
candidate is never reused.

## Error shape

```json
{
  "error": {
    "code": "corpus_not_ready",
    "message": "The corpus needs more usable prose before training.",
    "request_id": "req_01...",
    "details": {
      "usable_words": 640,
      "minimum_words": 1000
    }
  }
}
```

Expected invalid input is a typed `4xx` response, not a failed training job. Infrastructure errors
are retried internally; failed generation does not consume a credit, and failed training preserves
the purchased entitlement.
