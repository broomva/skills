import { mkdirSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import type { OntologyProposal } from "../core/ontology";
import { fail, ok, type ParallaxError, type Result } from "./errors";

/**
 * `.parallax/` -- everything a Parallax thread remembers between turns.
 *
 * There are two independent reasons this has to be bytes on disk rather than a
 * handle in memory, and either one alone would be sufficient:
 *
 *   1. `ActiveOntology` is branded with a module-private symbol that is checked
 *      at runtime. It deliberately does not survive a JSON round-trip, because
 *      trust cannot be serialised -- it has to be re-minted in the process that
 *      will execute it.
 *   2. The session that reads a WhatsApp message is a NEW OS process per turn.
 *      Anything held in a module-level `Map` works perfectly in a single-process
 *      test run and evaporates in production. That failure mode passes every
 *      test and presents as "it worked when I ran the demo".
 *
 * So an acceptance persists as a RECEIPT -- a description of what was accepted,
 * sufficient to re-derive the ontology and refuse if the world moved under it.
 *
 * Everything lives under a DOT directory on purpose. `proposeFromDirectory`
 * skips entries beginning with "." (src/core/ontology.ts), so Parallax's own
 * state is invisible to the proposer and writing it does not perturb the
 * proposal id. A non-dot directory would: `out/` adds an `out_count` field to
 * `initial`, which changes the id, which means running a simulation would
 * invalidate the acceptance that authorised it.
 */

export const STATE_DIR = ".parallax";

export function stateRoot(cwd: string = process.cwd()): string {
  return join(resolve(cwd), STATE_DIR);
}

/** Reads never create directories. Only writes do -- so a failed lookup leaves no trace. */
function ensureDirs(root: string): void {
  guardWrite(root, () => {
    for (const d of ["pending", "accepted", "rejected", "runs"]) {
      mkdirSync(join(root, d), { recursive: true });
    }
  });
}

/**
 * Raised when the workspace cannot be written to.
 *
 * A read-only workspace is a legitimate, expectable condition -- it is the
 * confinement posture this whole design assumes, and a tenant on a read-only
 * bind mount hits it on the first call. It was surfacing as UNEXPECTED, which
 * the CLI's own contract defines as "a defect, the backstop that should never
 * fire". So the operator was told Parallax is broken when the accurate answer
 * was that their directory is not writable, and the two have completely
 * different remedies.
 *
 * Carried as a distinct class rather than a raw fs error so the adapter layer
 * can map exactly this to a typed code and let every other throw keep going to
 * the backstop, where it belongs.
 */
export class WorkspaceNotWritableError extends Error {
  readonly root: string;
  readonly cause?: string;
  constructor(root: string, cause: string) {
    super(`the workspace is not writable: ${cause}`);
    this.name = "WorkspaceNotWritableError";
    this.root = root;
    this.cause = cause;
  }
}

/** Every write in this module goes through here, so the mapping cannot be bypassed. */
function guardWrite<T>(root: string, f: () => T): T {
  try {
    return f();
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code;
    if (code === "EACCES" || code === "EROFS" || code === "EPERM" || code === "ENOSPC") {
      throw new WorkspaceNotWritableError(root, e instanceof Error ? e.message : String(e));
    }
    throw e;
  }
}

/**
 * tmp + rename. A crash mid-write must not leave a truncated file that a lenient
 * reader silently accepts as a smaller version of the truth.
 */
function writeJson(path: string, value: unknown): void {
  guardWrite(path, () => {
    const tmp = `${path}.tmp-${process.pid}-${Date.now()}`;
    writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`);
    renameSync(tmp, path);
  });
}

function readJson<T>(path: string): T | null {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function listJson<T>(dir: string): T[] {
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch {
    return [];
  }
  const out: T[] = [];
  for (const n of names) {
    if (!n.endsWith(".json")) continue;
    const r = readJson<T>(join(dir, n));
    if (r !== null) out.push(r);
  }
  return out;
}

// ---------------------------------------------------------------- pending

export interface PendingRecord {
  readonly kind: "parallax.pending/v1";
  /**
   * The FULL proposal, including its open questions and its evidence. The
   * numbering a human saw is the numbering that binds them, so the stored copy
   * is the numbering authority -- never a freshly recomputed one.
   */
  readonly proposal: OntologyProposal;
  readonly proposedAt: number;
  /** The directory this was read from. Re-minting checks it has not moved. */
  readonly cwd: string;
  /** Answers recorded so far, keyed by question slot. Accumulates across turns. */
  readonly answers: Record<string, string>;
}

export function writePending(root: string, rec: PendingRecord): void {
  ensureDirs(root);
  // `invariants` is code and code never serialises. The proposers emit [] for it
  // unconditionally, so writing [] is not a lossy shortcut -- it is the value.
  const proposal = { ...rec.proposal, invariants: [] };
  writeJson(join(root, "pending", `${rec.proposal.id}.json`), { ...rec, proposal });
}

export function readPending(root: string, proposalId: string): PendingRecord | null {
  return readJson<PendingRecord>(join(root, "pending", `${proposalId}.json`));
}

export function listPending(root: string): PendingRecord[] {
  return listJson<PendingRecord>(join(root, "pending")).sort((a, b) => b.proposedAt - a.proposedAt);
}

export function readHead(root: string): string | null {
  try {
    const v = readFileSync(join(root, "pending", "HEAD"), "utf8").trim();
    return v.length > 0 ? v : null;
  } catch {
    return null;
  }
}

export function writeHead(root: string, proposalId: string | null): void {
  ensureDirs(root);
  const path = join(root, "pending", "HEAD");
  if (proposalId === null) {
    try {
      rmSync(path);
    } catch {
      // already absent; HEAD is a pointer, and a missing pointer is a valid state
    }
    return;
  }
  const tmp = `${path}.tmp-${process.pid}-${Date.now()}`;
  guardWrite(path, () => {
    writeFileSync(tmp, `${proposalId}\n`);
    renameSync(tmp, path);
  });
}

export interface RejectionRecord {
  readonly kind: "parallax.rejection/v1";
  readonly proposal: OntologyProposal;
  readonly reason: string;
  readonly at: number;
}

/** Rejection is archived, never deleted. What was refused is part of the audit trail. */
export function archiveRejected(root: string, rec: RejectionRecord): string {
  ensureDirs(root);
  const path = join(root, "rejected", `${rec.proposal.id}.json`);
  writeJson(path, { ...rec, proposal: { ...rec.proposal, invariants: [] } });
  try {
    rmSync(join(root, "pending", `${rec.proposal.id}.json`));
  } catch {
    // the pending file may already be gone; the archive is what matters
  }
  if (readHead(root) === rec.proposal.id) writeHead(root, null);
  return path;
}

export function listRejected(root: string): RejectionRecord[] {
  return listJson<RejectionRecord>(join(root, "rejected"));
}

// ---------------------------------------------------------------- acceptance

/**
 * The exact bytes that stand in for an acceptance between processes.
 *
 * `acceptedByAuthenticated` is a literal field rather than a comment because a
 * reader must not be able to mistake a claim for a proof. Parallax records who
 * the caller SAID they were; confining a thread to one workspace belongs to the
 * host, and this file cannot verify it.
 */
export interface AcceptanceRecord {
  readonly kind: "parallax.acceptance/v1";
  readonly ontologyId: string;
  readonly proposalId: string;
  readonly cwd: string;
  readonly slug: string;
  /**
   * The context the proposal was read from, stored verbatim so re-minting asks
   * the proposer the SAME question. Re-deriving it from cwd would silently
   * change the question whenever the caller's directory differs.
   */
  readonly source: OntologyProposal["source"];
  readonly answered: string[];
  readonly answers: Record<string, string>;
  /** Registry key, never a filesystem path. See handlers.ts for why. */
  readonly domain: string;
  readonly domainHash: string;
  readonly reconciliation: Reconciliation;
  readonly acknowledgedUnmapped: boolean;
  readonly proposerVersion: string;
  readonly acceptedBy: string;
  readonly acceptedByAuthenticated: false;
  readonly acceptedAt: number;
}

/**
 * What the human was shown, against what will actually execute.
 *
 * The proposal describes the context. The domain supplies the code. They are
 * not the same object, and the demo silently replaced one with the other --
 * which makes the accept gate theatre, because the human accepted a reading of
 * their workspace and a storefront ledger ran. Naming the gap is the fix.
 */
export interface Reconciliation {
  /** Fields present in both the accepted proposal and the executable domain. */
  readonly covered: string[];
  /** Fields the human was shown as read from their context that the domain ignores. */
  readonly unmappedFromContext: string[];
  /** Fields the domain introduces that were never in the proposal. */
  readonly domainOnly: string[];
}

export function writeAcceptance(root: string, rec: AcceptanceRecord): void {
  ensureDirs(root);
  writeJson(join(root, "accepted", `${rec.ontologyId}.json`), rec);
}

export function readAcceptance(root: string, ontologyId: string): AcceptanceRecord | null {
  return readJson<AcceptanceRecord>(join(root, "accepted", `${ontologyId}.json`));
}

export function listAcceptances(root: string): AcceptanceRecord[] {
  return listJson<AcceptanceRecord>(join(root, "accepted")).sort(
    (a, b) => b.acceptedAt - a.acceptedAt,
  );
}

// ---------------------------------------------------------------- runs

export interface RunRecord {
  readonly kind: "parallax.run/v1";
  readonly runId: string;
  readonly ontologyId: string;
  readonly at: number;
  readonly horizon: number;
  readonly seed: number;
  readonly governed: boolean;
  readonly trials: number;
  readonly branch: string;
  readonly branchClass: string;
  readonly certificate: Record<string, unknown>;
  readonly violations: { baseline: number; run: number };
  readonly diff: Array<{ key: string; from: unknown; to: unknown }>;
  readonly scores: Array<Record<string, unknown>>;
  readonly traceHash: { baseline: string; run: string };
  readonly steps: number;
  readonly origins: { observed: number; simulated: number };
  /** Carried here because RunReceipt has no field for it. See handlers.ts. */
  readonly reconciliation: Reconciliation;
  readonly receiptPath: string;
  readonly url: string;
}

export function writeRun(root: string, rec: RunRecord, html: string): void {
  ensureDirs(root);
  writeJson(join(root, "runs", `${rec.runId}.json`), rec);
  const path = join(root, "runs", `${rec.runId}.html`);
  const tmp = `${path}.tmp-${process.pid}-${Date.now()}`;
  guardWrite(path, () => {
    writeFileSync(tmp, html);
    renameSync(tmp, path);
  });
}

export function readRun(root: string, runId: string): RunRecord | null {
  return readJson<RunRecord>(join(root, "runs", `${runId}.json`));
}

export function listRuns(root: string): RunRecord[] {
  return listJson<RunRecord>(join(root, "runs")).sort((a, b) => b.at - a.at);
}

export function readRunHtml(root: string, runId: string): string | null {
  try {
    return readFileSync(join(root, "runs", `${runId}.html`), "utf8");
  } catch {
    return null;
  }
}

export function runReceiptPath(root: string, runId: string): string {
  return join(root, "runs", `${runId}.html`);
}

// ---------------------------------------------------------------- refs

export type RefError = ParallaxError<"NO_PENDING_PROPOSAL" | "UNKNOWN_REF" | "AMBIGUOUS_REF">;

/**
 * Resolve a `ref` the way a human uses one.
 *
 * Every rendered proposal prints `ref <first 12 hex>`, so a person replying
 * three messages later can name which proposal they mean. An omitted ref means
 * HEAD. HEAD is only a POINTER: a lost write leaves a stale pointer rather than
 * a corrupt record, and the explicit ref is always available as the override.
 *
 * There is no TTL anywhere in this module. Staleness is content-based -- the
 * proposal hash either still matches the workspace or it does not. A clock-based
 * expiry would be a policy nobody agreed to, in a product whose entire claim is
 * that nothing runs unagreed.
 */
export function resolvePendingRef(root: string, ref?: string): Result<PendingRecord, RefError> {
  const all = listPending(root);
  if (ref === undefined || ref.length === 0) {
    const head = readHead(root);
    if (head === null) {
      return fail("NO_PENDING_PROPOSAL", "no proposal is pending in this workspace", {
        pendingCount: all.length,
      });
    }
    const rec = readPending(root, head);
    if (rec === null) {
      return fail("NO_PENDING_PROPOSAL", "HEAD points at a proposal that is no longer on disk", {
        head,
      });
    }
    return ok(rec);
  }
  const matches = all.filter((p) => p.proposal.id.startsWith(ref));
  const first = matches[0];
  if (first === undefined) {
    return fail("UNKNOWN_REF", `no pending proposal starts with ${ref}`, {
      ref,
      known: all.map((p) => p.proposal.id.slice(0, 12)),
    });
  }
  if (matches.length > 1) {
    return fail("AMBIGUOUS_REF", `${matches.length} pending proposals start with ${ref}`, {
      ref,
      matches: matches.map((p) => p.proposal.id.slice(0, 12)),
    });
  }
  return ok(first);
}
