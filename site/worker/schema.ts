export const APP_SCHEMA = [
  `CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT, writing_goals TEXT, sample_notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS corpora (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', documents INTEGER NOT NULL DEFAULT 0, raw_words INTEGER NOT NULL DEFAULT 0, usable_words INTEGER NOT NULL DEFAULT 0, duplicate_words INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS idx_corpora_owner_updated ON corpora(owner_id, updated_at)`,
  `CREATE TABLE IF NOT EXISTS corpus_items (id TEXT PRIMARY KEY, corpus_id TEXT NOT NULL, owner_id TEXT NOT NULL, name TEXT NOT NULL, content_type TEXT NOT NULL, storage_key TEXT NOT NULL, bytes INTEGER NOT NULL, raw_words INTEGER NOT NULL, created_at TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS idx_corpus_items_corpus ON corpus_items(corpus_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS corpus_revisions (id TEXT PRIMARY KEY, corpus_id TEXT NOT NULL, owner_id TEXT NOT NULL, checksum TEXT NOT NULL, usable_words INTEGER NOT NULL, snapshot_key TEXT NOT NULL, created_at TEXT NOT NULL)`,
  `CREATE UNIQUE INDEX IF NOT EXISTS idx_corpus_revisions_checksum ON corpus_revisions(owner_id, corpus_id, checksum)`,
  `CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, revision_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', provider TEXT NOT NULL DEFAULT 'modal', provider_model TEXT NOT NULL DEFAULT 'Qwen/Qwen2.5-14B', adapter_path TEXT, style_profile TEXT, trained_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS idx_models_owner_updated ON models(owner_id, updated_at)`,
  `CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', resource_id TEXT, provider_job_id TEXT, request TEXT, result TEXT, error TEXT, idempotency_key TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS idx_jobs_owner_updated ON jobs(owner_id, updated_at)`,
  `CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_owner_idempotency ON jobs(owner_id, idempotency_key)`,
  `CREATE TABLE IF NOT EXISTS credit_ledger (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, delta INTEGER NOT NULL, kind TEXT NOT NULL, reference_id TEXT, created_at TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS idx_credit_ledger_owner ON credit_ledger(owner_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS entitlements (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'available', stripe_session_id TEXT, consumed_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS idx_entitlements_owner_status ON entitlements(owner_id, status)`,
  `CREATE TABLE IF NOT EXISTS api_keys (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL, prefix TEXT NOT NULL, key_hash TEXT NOT NULL, scopes TEXT NOT NULL, last_used_at TEXT, revoked_at TEXT, created_at TEXT NOT NULL)`,
  `CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)`,
  `CREATE TABLE IF NOT EXISTS webhook_endpoints (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, url TEXT NOT NULL, secret_hash TEXT NOT NULL, events TEXT NOT NULL, disabled_at TEXT, created_at TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS idx_webhooks_owner ON webhook_endpoints(owner_id)`,
  `CREATE TABLE IF NOT EXISTS webhook_deliveries (id TEXT PRIMARY KEY, endpoint_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT, created_at TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_pending ON webhook_deliveries(status, next_attempt_at)`,
];

export async function ensureAppSchema(db: D1Database): Promise<void> {
  await db.batch(APP_SCHEMA.map((statement) => db.prepare(statement)));
}
