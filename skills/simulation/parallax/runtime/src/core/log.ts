import { Database } from "bun:sqlite";
import type { Klass } from "./hash";
import type { Event } from "./types";

/**
 * Append-only event log. Past = this log, present = a projection of it,
 * future = the same log projected forward under a policy. One substrate,
 * three views.
 */
export class EventLog {
  private db: Database;

  constructor(path = ":memory:") {
    this.db = new Database(path);
    this.db.run(`
      CREATE TABLE IF NOT EXISTS events (
        seq        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts         INTEGER NOT NULL,
        branch     TEXT NOT NULL,
        actor      TEXT NOT NULL,
        action     TEXT NOT NULL,
        params     TEXT NOT NULL,
        derivation TEXT,
        klass      TEXT NOT NULL
      )`);
    this.db.run(`CREATE INDEX IF NOT EXISTS ix_branch ON events(branch, seq)`);
    this.db.run(`
      CREATE TABLE IF NOT EXISTS branches (
        name      TEXT PRIMARY KEY,
        parent    TEXT,
        forked_at INTEGER
      )`);
    this.db.run(`INSERT OR IGNORE INTO branches VALUES ('main', NULL, NULL)`);
  }

  append(e: Omit<Event, "seq">): Event {
    const row = this.db
      .query(
        `INSERT INTO events (ts, branch, actor, action, params, derivation, klass)
         VALUES (?,?,?,?,?,?,?) RETURNING seq`,
      )
      .get(e.ts, e.branch, e.actor, e.action, JSON.stringify(e.params), e.derivation, e.klass) as {
      seq: number;
    };
    return { ...e, seq: row.seq };
  }

  /** Events visible on a branch = its own events, plus its parent's up to the fork point. */
  read(branch: string): Event[] {
    const b = this.db
      .query(`SELECT parent, forked_at FROM branches WHERE name = ?`)
      .get(branch) as { parent: string | null; forked_at: number | null } | null;
    if (!b) throw new Error(`unknown branch: ${branch}`);
    const inherited =
      b.parent === null ? [] : this.read(b.parent).filter((e) => e.seq <= (b.forked_at ?? 0));
    const own = this.db
      .query(`SELECT * FROM events WHERE branch = ? ORDER BY seq`)
      .all(branch) as Array<Omit<Event, "params"> & { params: string }>;
    return [...inherited, ...own.map((r) => ({ ...r, params: JSON.parse(r.params) }))];
  }

  /** Fork at a point in history. This is the whole counterfactual mechanism. */
  fork(name: string, from: string, atSeq: number): void {
    this.db.run(`INSERT INTO branches (name, parent, forked_at) VALUES (?,?,?)`, [
      name,
      from,
      atSeq,
    ]);
  }

  head(branch: string): number {
    const events = this.read(branch);
    return events.length === 0 ? 0 : (events.at(-1)?.seq ?? 0);
  }

  /** Worst reproducibility class present on a branch -- the taint answer. */
  branchClass(branch: string): Klass {
    const classes = this.read(branch).map((e) => e.klass);
    if (classes.includes("RECORDED")) return "RECORDED";
    if (classes.includes("STABLE")) return "STABLE";
    return "PINNED";
  }
}
