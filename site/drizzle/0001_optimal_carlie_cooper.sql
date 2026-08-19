CREATE TABLE `api_keys` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`name` text NOT NULL,
	`prefix` text NOT NULL,
	`key_hash` text NOT NULL,
	`scopes` text NOT NULL,
	`last_used_at` text,
	`revoked_at` text,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_api_keys_hash` ON `api_keys` (`key_hash`);--> statement-breakpoint
CREATE TABLE `corpora` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`name` text NOT NULL,
	`status` text DEFAULT 'draft' NOT NULL,
	`documents` integer DEFAULT 0 NOT NULL,
	`raw_words` integer DEFAULT 0 NOT NULL,
	`usable_words` integer DEFAULT 0 NOT NULL,
	`duplicate_words` integer DEFAULT 0 NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_corpora_owner_updated` ON `corpora` (`owner_id`,`updated_at`);--> statement-breakpoint
CREATE TABLE `corpus_items` (
	`id` text PRIMARY KEY NOT NULL,
	`corpus_id` text NOT NULL,
	`owner_id` text NOT NULL,
	`name` text NOT NULL,
	`content_type` text NOT NULL,
	`storage_key` text NOT NULL,
	`bytes` integer NOT NULL,
	`raw_words` integer NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_corpus_items_corpus` ON `corpus_items` (`corpus_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `corpus_revisions` (
	`id` text PRIMARY KEY NOT NULL,
	`corpus_id` text NOT NULL,
	`owner_id` text NOT NULL,
	`checksum` text NOT NULL,
	`usable_words` integer NOT NULL,
	`snapshot_key` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_corpus_revisions_checksum` ON `corpus_revisions` (`owner_id`,`corpus_id`,`checksum`);--> statement-breakpoint
CREATE TABLE `credit_ledger` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`delta` integer NOT NULL,
	`kind` text NOT NULL,
	`reference_id` text,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_credit_ledger_owner` ON `credit_ledger` (`owner_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `entitlements` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`kind` text NOT NULL,
	`status` text DEFAULT 'available' NOT NULL,
	`stripe_session_id` text,
	`consumed_by` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_entitlements_owner_status` ON `entitlements` (`owner_id`,`status`);--> statement-breakpoint
CREATE TABLE `jobs` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`kind` text NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`resource_id` text,
	`provider_job_id` text,
	`request` text,
	`result` text,
	`error` text,
	`idempotency_key` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_jobs_owner_updated` ON `jobs` (`owner_id`,`updated_at`);--> statement-breakpoint
CREATE UNIQUE INDEX `idx_jobs_owner_idempotency` ON `jobs` (`owner_id`,`idempotency_key`);--> statement-breakpoint
CREATE TABLE `models` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`revision_id` text NOT NULL,
	`name` text NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`provider` text DEFAULT 'modal' NOT NULL,
	`provider_model` text DEFAULT 'Qwen/Qwen2.5-14B' NOT NULL,
	`adapter_path` text,
	`style_profile` text,
	`trained_at` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_models_owner_updated` ON `models` (`owner_id`,`updated_at`);--> statement-breakpoint
CREATE TABLE `users` (
	`id` text PRIMARY KEY NOT NULL,
	`email` text NOT NULL,
	`name` text,
	`writing_goals` text,
	`sample_notes` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `webhook_deliveries` (
	`id` text PRIMARY KEY NOT NULL,
	`endpoint_id` text NOT NULL,
	`event_type` text NOT NULL,
	`payload` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`attempts` integer DEFAULT 0 NOT NULL,
	`next_attempt_at` text,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_webhook_deliveries_pending` ON `webhook_deliveries` (`status`,`next_attempt_at`);--> statement-breakpoint
CREATE TABLE `webhook_endpoints` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_id` text NOT NULL,
	`url` text NOT NULL,
	`secret_hash` text NOT NULL,
	`events` text NOT NULL,
	`disabled_at` text,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_webhooks_owner` ON `webhook_endpoints` (`owner_id`);