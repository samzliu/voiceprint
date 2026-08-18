import { integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const usage = sqliteTable(
  "usage",
  {
    scope: text("scope").notNull(),
    day: text("day").notNull(),
    count: integer("count").notNull().default(0),
  },
  (table) => [primaryKey({ columns: [table.scope, table.day] })],
);
