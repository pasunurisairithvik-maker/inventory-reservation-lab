import { integer,sqliteTable,text } from 'drizzle-orm/sqlite-core';
export const workspaces=sqliteTable('demo_workspaces',{
 id:text('id').primaryKey(),
 state:text('state').notNull(),
 version:integer('version').notNull().default(0),
 updated:integer('updated').notNull(),
});
