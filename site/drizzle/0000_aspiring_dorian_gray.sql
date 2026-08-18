CREATE TABLE `usage` (
	`scope` text NOT NULL,
	`day` text NOT NULL,
	`count` integer DEFAULT 0 NOT NULL,
	PRIMARY KEY(`scope`, `day`)
);
