import {
  index,
  integer,
  primaryKey,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

export const usage = sqliteTable(
  "usage",
  {
    scope: text("scope").notNull(),
    day: text("day").notNull(),
    count: integer("count").notNull().default(0),
  },
  (table) => [primaryKey({ columns: [table.scope, table.day] })],
);

export const users = sqliteTable("users", {
  id: text("id").primaryKey(),
  email: text("email").notNull(),
  name: text("name"),
  writingGoals: text("writing_goals"),
  sampleNotes: text("sample_notes"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const corpora = sqliteTable(
  "corpora",
  {
    id: text("id").primaryKey(),
    ownerId: text("owner_id").notNull(),
    name: text("name").notNull(),
    status: text("status").notNull().default("draft"),
    documents: integer("documents").notNull().default(0),
    rawWords: integer("raw_words").notNull().default(0),
    usableWords: integer("usable_words").notNull().default(0),
    duplicateWords: integer("duplicate_words").notNull().default(0),
    createdAt: text("created_at").notNull(),
    updatedAt: text("updated_at").notNull(),
  },
  (table) => [index("idx_corpora_owner_updated").on(table.ownerId, table.updatedAt)],
);

export const corpusItems = sqliteTable(
  "corpus_items",
  {
    id: text("id").primaryKey(),
    corpusId: text("corpus_id").notNull(),
    ownerId: text("owner_id").notNull(),
    name: text("name").notNull(),
    contentType: text("content_type").notNull(),
    storageKey: text("storage_key").notNull(),
    bytes: integer("bytes").notNull(),
    rawWords: integer("raw_words").notNull(),
    createdAt: text("created_at").notNull(),
  },
  (table) => [index("idx_corpus_items_corpus").on(table.corpusId, table.createdAt)],
);

export const corpusRevisions = sqliteTable(
  "corpus_revisions",
  {
    id: text("id").primaryKey(),
    corpusId: text("corpus_id").notNull(),
    ownerId: text("owner_id").notNull(),
    checksum: text("checksum").notNull(),
    usableWords: integer("usable_words").notNull(),
    snapshotKey: text("snapshot_key").notNull(),
    createdAt: text("created_at").notNull(),
  },
  (table) => [
    uniqueIndex("idx_corpus_revisions_checksum").on(table.ownerId, table.corpusId, table.checksum),
  ],
);

export const models = sqliteTable(
  "models",
  {
    id: text("id").primaryKey(),
    ownerId: text("owner_id").notNull(),
    revisionId: text("revision_id").notNull(),
    name: text("name").notNull(),
    status: text("status").notNull().default("queued"),
    provider: text("provider").notNull().default("modal"),
    providerModel: text("provider_model").notNull().default("Qwen/Qwen2.5-14B-Instruct"),
    adapterPath: text("adapter_path"),
    styleProfile: text("style_profile"),
    trainedAt: text("trained_at"),
    createdAt: text("created_at").notNull(),
    updatedAt: text("updated_at").notNull(),
  },
  (table) => [index("idx_models_owner_updated").on(table.ownerId, table.updatedAt)],
);

export const jobs = sqliteTable(
  "jobs",
  {
    id: text("id").primaryKey(),
    ownerId: text("owner_id").notNull(),
    kind: text("kind").notNull(),
    status: text("status").notNull().default("queued"),
    resourceId: text("resource_id"),
    providerJobId: text("provider_job_id"),
    request: text("request"),
    result: text("result"),
    error: text("error"),
    idempotencyKey: text("idempotency_key"),
    createdAt: text("created_at").notNull(),
    updatedAt: text("updated_at").notNull(),
  },
  (table) => [
    index("idx_jobs_owner_updated").on(table.ownerId, table.updatedAt),
    uniqueIndex("idx_jobs_owner_idempotency").on(table.ownerId, table.idempotencyKey),
  ],
);

export const creditLedger = sqliteTable(
  "credit_ledger",
  {
    id: text("id").primaryKey(),
    ownerId: text("owner_id").notNull(),
    delta: integer("delta").notNull(),
    kind: text("kind").notNull(),
    referenceId: text("reference_id"),
    createdAt: text("created_at").notNull(),
  },
  (table) => [index("idx_credit_ledger_owner").on(table.ownerId, table.createdAt)],
);

export const entitlements = sqliteTable(
  "entitlements",
  {
    id: text("id").primaryKey(),
    ownerId: text("owner_id").notNull(),
    kind: text("kind").notNull(),
    status: text("status").notNull().default("available"),
    stripeSessionId: text("stripe_session_id"),
    consumedBy: text("consumed_by"),
    createdAt: text("created_at").notNull(),
    updatedAt: text("updated_at").notNull(),
  },
  (table) => [index("idx_entitlements_owner_status").on(table.ownerId, table.status)],
);

export const apiKeys = sqliteTable(
  "api_keys",
  {
    id: text("id").primaryKey(),
    ownerId: text("owner_id").notNull(),
    name: text("name").notNull(),
    prefix: text("prefix").notNull(),
    keyHash: text("key_hash").notNull(),
    scopes: text("scopes").notNull(),
    lastUsedAt: text("last_used_at"),
    revokedAt: text("revoked_at"),
    createdAt: text("created_at").notNull(),
  },
  (table) => [uniqueIndex("idx_api_keys_hash").on(table.keyHash)],
);

export const webhookEndpoints = sqliteTable(
  "webhook_endpoints",
  {
    id: text("id").primaryKey(),
    ownerId: text("owner_id").notNull(),
    url: text("url").notNull(),
    secretHash: text("secret_hash").notNull(),
    events: text("events").notNull(),
    disabledAt: text("disabled_at"),
    createdAt: text("created_at").notNull(),
  },
  (table) => [index("idx_webhooks_owner").on(table.ownerId)],
);

export const webhookDeliveries = sqliteTable(
  "webhook_deliveries",
  {
    id: text("id").primaryKey(),
    endpointId: text("endpoint_id").notNull(),
    eventType: text("event_type").notNull(),
    payload: text("payload").notNull(),
    status: text("status").notNull().default("pending"),
    attempts: integer("attempts").notNull().default(0),
    nextAttemptAt: text("next_attempt_at"),
    createdAt: text("created_at").notNull(),
  },
  (table) => [index("idx_webhook_deliveries_pending").on(table.status, table.nextAttemptAt)],
);
