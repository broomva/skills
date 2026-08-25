import { Database } from "bun:sqlite";
import type { Item } from "./parse.ts";

/** Local price history. Nothing leaves the machine. */
const DB_PATH = () => `${process.env.HOME}/.config/cub-cli/history.sqlite`;

export type WatchRow = { productId: string; name: string; targetCents: number | null };

export function open(path = DB_PATH()): Database {
  const db = new Database(path, { create: true });
  db.run(`CREATE TABLE IF NOT EXISTS price_history (
    product_id TEXT NOT NULL,
    observed_at INTEGER NOT NULL,
    price_cents INTEGER,
    full_price_cents INTEGER,
    offer_label TEXT,
    name TEXT,
    PRIMARY KEY (product_id, observed_at)
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS watches (
    product_id TEXT PRIMARY KEY,
    name TEXT,
    target_cents INTEGER
  )`);
  return db;
}

export function record(db: Database, items: Item[], now = Date.now()): number {
  const stmt = db.prepare(
    `INSERT OR REPLACE INTO price_history
     (product_id, observed_at, price_cents, full_price_cents, offer_label, name)
     VALUES (?, ?, ?, ?, ?, ?)`,
  );
  const tx = db.transaction((rows: Item[]) => {
    for (const i of rows) {
      stmt.run(i.productId, now, i.priceCents, i.fullPriceCents, i.offerLabel, i.name);
    }
  });
  tx(items);
  return items.length;
}

export function addWatch(db: Database, productId: string, name: string, targetCents: number | null) {
  db.prepare(`INSERT OR REPLACE INTO watches (product_id, name, target_cents) VALUES (?, ?, ?)`)
    .run(productId, name, targetCents);
}

export function listWatches(db: Database): WatchRow[] {
  return db
    .prepare(`SELECT product_id AS productId, name, target_cents AS targetCents FROM watches`)
    .all() as WatchRow[];
}

/** Watches whose latest observed price is at or below their target. */
export function triggered(db: Database): { productId: string; name: string; priceCents: number; targetCents: number }[] {
  return db
    .prepare(
      `SELECT w.product_id AS productId, w.name AS name,
              h.price_cents AS priceCents, w.target_cents AS targetCents
       FROM watches w
       JOIN price_history h ON h.product_id = w.product_id
       WHERE h.observed_at = (SELECT MAX(observed_at) FROM price_history WHERE product_id = w.product_id)
         AND w.target_cents IS NOT NULL
         AND h.price_cents IS NOT NULL
         AND h.price_cents <= w.target_cents`,
    )
    .all() as any;
}
