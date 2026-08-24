import {
  readdirSync,
  readFileSync,
  realpathSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { isAbsolute, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { eagerAgent, governedAgent } from "../actors/policies";
import { renderReceipt } from "../artifact/receipt";
import {
  parseReply,
  renderProposal,
  resolveAccept,
  WHATSAPP_CHUNK_CHARS,
} from "../channel/conversation";
import { h } from "../core/hash";
import { EventLog } from "../core/log";
import {
  type ActiveOntology,
  activate,
  type ContextSource,
  type OntologyProposal,
  proposeOntology,
  worldOf,
} from "../core/ontology";
import {
  certifyPolicy,
  check,
  diff,
  type Objective,
  observe,
  type Policy,
  rolloutCertified,
  score,
  step,
  traceHash,
} from "../core/ops";
import { splitOrigins } from "../core/provenance";
import type { Event, TypeRecord } from "../core/types";
import { DEFAULT_DOMAIN, DOMAIN_KEYS, domainHash, resolveDomain } from "./domains";
import { type AnyErrorCode, fail, ok, type ParallaxError, type Result } from "./errors";
import {
  type AcceptanceRecord,
  archiveRejected,
  listAcceptances,
  listPending,
  listRuns,
  type Reconciliation,
  type RunRecord,
  readAcceptance,
  readHead,
  readRun,
  readRunHtml,
  resolvePendingRef,
  runReceiptPath,
  stateRoot,
  writeAcceptance,
  writeHead,
  writePending,
  writeRun,
} from "./state";

/**
 * The capabilities, once.
 *
 * Every adapter in this directory is thin on purpose: the AI SDK tools, the CLI
 * and (when it lands) the HTTP hub all call THESE functions and forward THESE
 * values. A capability that exists only behind one transport is a feature of the
 * transport, and a second implementation behind a second transport is two
 * products that disagree under load.
 *
 * Nothing here throws. Every failure is a `Result` carrying `{code, reason,
 * detail?}` -- the same shape `src/core/result.ts` returns, with library codes
 * forwarded unchanged rather than re-worded. An adapter's `try/catch` is a
 * backstop that should never fire, not the error mechanism.
 */

export type HandlerError = ParallaxError<AnyErrorCode>;

const now = (): number => Date.now();

/**
 * A stamp over the proposer's own source.
 *
 * Every stored acceptance is a dependency of that code: the questions a human
 * answered and the id they were bound to are OUTPUTS of `proposeOntology`. If
 * the proposer's heuristic changes, the honest answer is to ask again, not to
 * silently re-derive. The stamp is coarse -- any edit to that file, including a
 * comment, invalidates every acceptance -- because a narrow stamp that misses a
 * semantic change fails SILENTLY, and a coarse one fails loudly.
 */
function proposerVersion(): string {
  try {
    const path = fileURLToPath(new URL("../core/ontology.ts", import.meta.url));
    return `ontology:${h(readFileSync(path, "utf8"))}`;
  } catch {
    return "ontology:unreadable";
  }
}

// ---------------------------------------------------------------------------
// propose
// ---------------------------------------------------------------------------

export interface ProposeInput {
  readonly kind?: "agent-workspace" | "filesystem" | "business-data";
  /** Relative sub-path INSIDE the workspace. Never absolute, never escaping it. */
  readonly within?: string;
  /**
   * An absolute root. Reachable from a human's terminal (`--kind filesystem
   * --root ...`) and deliberately absent from every tool schema. At a terminal
   * the person choosing the path is the confinement; in a sandboxed session a
   * derived path is DENIED, and a denied read surfaces as an EMPTY DIRECTORY
   * rather than an error -- so it reads as "your workspace is empty" and the
   * mistake never announces itself.
   */
  readonly root?: string;
  readonly tables?: Array<{ name: string; columns: string[] }>;
  readonly chunkChars?: number;
}

export interface ProposeValue {
  readonly ref: string;
  readonly proposalId: string;
  readonly slug: string;
  readonly title: string;
  readonly source: string;
  readonly stateFields: Array<{ key: string; value: unknown; from: string | null }>;
  readonly actions: Array<{ name: string; actor: string; params: string[] }>;
  readonly blockingQuestions: Array<{ n: number; slot: string; question: string }>;
  readonly advisoryQuestions: Array<{ slot: string; question: string }>;
  readonly text: string;
  readonly messages: Array<{ text: string; part: number; of: number }>;
  readonly pendingPath: string;
}

export function propose(input: ProposeInput = {}): Result<ProposeValue, HandlerError> {
  const kind = input.kind ?? "agent-workspace";
  const cwd = resolve(process.cwd());
  const root = stateRoot(cwd);

  let source: ContextSource;
  if (kind === "business-data") {
    const tables = input.tables ?? [];
    if (tables.length === 0) {
      return fail("TABLES_REQUIRED", "business-data needs at least one table with its columns", {
        given: tables.length,
      });
    }
    source = { kind: "business-data", tables };
  } else {
    if (kind === "agent-workspace" && input.root !== undefined) {
      return fail(
        "ROOT_NOT_ALLOWED",
        "agent-workspace never takes a root: it reads the working directory the session was given",
        { given: input.root, cwd },
      );
    }
    const base = input.root === undefined ? cwd : resolve(input.root);
    const contained = confine(base, input.within);
    if (!contained.ok) return contained;
    const target = contained.value;
    // When the target IS the working directory, call the library with NO root so
    // its own default is the code path that executes -- not a path we rebuilt.
    source =
      kind === "agent-workspace"
        ? target === cwd
          ? { kind: "agent-workspace" }
          : { kind: "agent-workspace", root: target }
        : { kind: "filesystem", root: target };
  }

  const proposed = proposeOntology(source);
  if (!proposed.ok) return disambiguateEmpty(proposed.error, source);

  const p = proposed.value;
  const at = now();
  writePending(root, {
    kind: "parallax.pending/v1",
    proposal: p,
    proposedAt: at,
    cwd,
    answers: {},
  });
  writeHead(root, p.id);
  return ok(viewProposal(p, input.chunkChars ?? WHATSAPP_CHUNK_CHARS, root));
}

/**
 * Relative-only, escape-checked. The only path arithmetic in this module.
 *
 * Checked TWICE, lexically and then physically, because the lexical check alone
 * is not a containment guarantee. `path.resolve` never follows symlinks, so a
 * symlink placed inside the workspace produces a target that starts with the
 * base and points anywhere on the filesystem. The first version of this function
 * stopped at the lexical check, and `ln -s /etc ws/data` then read /etc into a
 * proposal whose evidence lines were rendered into the message sent to the human
 * and persisted in the pending record.
 *
 * That matters more here than it would elsewhere: the surrounding sandbox
 * confines WRITES but not READS, so a lexical-only guard is the difference
 * between a proposal describing the tenant's own workspace and one describing
 * whatever the tenant pointed a link at.
 *
 * The base is realpath'd too. On macOS /tmp is itself a symlink to /private/tmp,
 * so comparing a resolved target against an unresolved base fails on ordinary
 * paths and would push someone to loosen the check for the wrong reason.
 */
function confine(base: string, within?: string): Result<string, HandlerError> {
  let realBase: string;
  try {
    realBase = realpathSync(base);
  } catch {
    // The workspace itself is unreadable. Not an escape; report it as itself.
    return fail("WORKSPACE_UNREADABLE", "the workspace directory could not be resolved", { base });
  }
  if (within === undefined || within.length === 0) return ok(realBase);
  if (isAbsolute(within)) {
    return fail("PATH_ABSOLUTE", "`within` is a relative sub-path, never an absolute path", {
      given: within,
      base: realBase,
    });
  }

  // Lexical first: catches `../` and friends before touching the filesystem.
  const lexical = resolve(realBase, within);
  if (lexical !== realBase && !lexical.startsWith(realBase + sep)) {
    return fail("PATH_ESCAPES_WORKSPACE", "`within` resolves outside the workspace", {
      given: within,
      resolved: lexical,
      base: realBase,
    });
  }

  // Physical second: this is the check a symlink defeats.
  let realTarget: string;
  try {
    realTarget = realpathSync(lexical);
  } catch {
    return fail("PATH_NOT_FOUND", "`within` does not exist inside the workspace", {
      given: within,
      resolved: lexical,
      base: realBase,
    });
  }
  if (realTarget !== realBase && !realTarget.startsWith(realBase + sep)) {
    return fail("PATH_ESCAPES_WORKSPACE", "`within` is a link that leaves the workspace", {
      given: within,
      resolved: realTarget,
      base: realBase,
    });
  }
  return ok(realTarget);
}

/**
 * SOURCE_EMPTY is ambiguous and the ambiguity is the dangerous part.
 *
 * A denied directory and a genuinely fresh workspace both read as "no entries".
 * Re-statting separates the two cases that CAN be separated -- a throw means
 * denial, a clean read of zero entries means emptiness -- and the residual (a
 * sandbox that presents a denied mount as readable-and-empty) is stated in the
 * detail rather than guessed at, because no code inside the process can resolve
 * it.
 */
function disambiguateEmpty(
  error: ParallaxError<AnyErrorCode>,
  source: ContextSource,
): Result<never, HandlerError> {
  if (error.code !== "SOURCE_EMPTY" || source.kind === "business-data") {
    return { ok: false, error };
  }
  const root = source.root ?? process.cwd();
  try {
    statSync(root);
    const entries = readdirSync(root);
    return fail("SOURCE_EMPTY", error.reason, {
      root,
      entries: entries.length,
      hint: "this directory is readable and contains nothing. If you expected content, the workspace mount is the thing to check, not the path.",
    });
  } catch (e) {
    return fail("WORKSPACE_DENIED", `${root} cannot be read`, {
      root,
      cause: e instanceof Error ? e.message : String(e),
    });
  }
}

function viewProposal(p: OntologyProposal, chunkChars: number, root: string): ProposeValue {
  const messages = renderProposal(p, chunkChars);
  const blocking = p.openQuestions.filter((q) => q.blocking);
  return {
    ref: p.id.slice(0, 12),
    proposalId: p.id,
    slug: p.slug,
    title: p.title,
    source: p.source.kind,
    stateFields: Object.entries(p.initial).map(([key, value]) => ({
      key,
      value,
      from: p.evidence.find((e) => e.slot === `state.${key}`)?.from ?? null,
    })),
    actions: p.actions.map((a) => ({
      name: a.name,
      actor: a.actor,
      params: Object.keys(a.params),
    })),
    blockingQuestions: blocking.map((q, i) => ({ n: i + 1, slot: q.slot, question: q.question })),
    advisoryQuestions: p.openQuestions
      .filter((q) => !q.blocking)
      .map((q) => ({ slot: q.slot, question: q.question })),
    text: messages.map((m) => m.text).join("\n"),
    messages: messages.map((m) => ({ text: m.text, part: m.part, of: m.of })),
    pendingPath: `${root}/pending/${p.id}.json`,
  };
}

// ---------------------------------------------------------------------------
// render a stored proposal again
// ---------------------------------------------------------------------------

export interface RenderInput {
  readonly ref?: string;
  readonly chunkChars?: number;
}

/**
 * "Send it again" must be a RE-RENDER, never a re-summary. A paraphrased
 * proposal that a human then accepts is an acceptance of the paraphrase.
 */
export function render(input: RenderInput = {}): Result<ProposeValue, HandlerError> {
  const root = stateRoot();
  const pending = resolvePendingRef(root, input.ref);
  if (!pending.ok) return pending;
  return ok(viewProposal(pending.value.proposal, input.chunkChars ?? WHATSAPP_CHUNK_CHARS, root));
}

// ---------------------------------------------------------------------------
// read a human reply
// ---------------------------------------------------------------------------

export interface ParseReplyInput {
  readonly text: string;
  readonly ref?: string;
}

export interface ParseReplyValue {
  readonly ref: string;
  readonly intent: "accept" | "reject" | "answers" | "unclear";
  readonly answers: Array<{ n: number; slot: string; text: string }>;
  readonly stillOpen: Array<{ n: number; slot: string; question: string }>;
  readonly canAccept: boolean;
  readonly reason: string | null;
}

/**
 * Classify a reply against a STORED proposal. Read-only: it records nothing, so
 * calling it twice is never destructive.
 *
 * The rules are not the ones a reader would apply from the text alone, which is
 * exactly why this is a capability rather than a judgement: a reply containing
 * any rejection word is a REJECTION even when it also contains an acceptance
 * word, and a bare "no" anywhere in the message is a rejection word. The safe
 * reading is the one that does not start running things.
 */
export function classifyReply(input: ParseReplyInput): Result<ParseReplyValue, HandlerError> {
  const root = stateRoot();
  const pending = resolvePendingRef(root, input.ref);
  if (!pending.ok) return pending;
  const p = pending.value.proposal;
  if (input.text.trim().length === 0) {
    return fail("EMPTY_REPLY", "an empty reply carries no intent", { ref: p.id.slice(0, 12) });
  }

  const blocking = p.openQuestions.filter((q) => q.blocking);
  const intent = parseReply(input.text, p.openQuestions);
  const given = new Map<string, string>(Object.entries(pending.value.answers));
  if (intent.kind === "accept" || intent.kind === "answers") {
    for (const [slot, text] of intent.answers) given.set(slot, text);
  }

  const answers = blocking
    .map((q, i) => ({ n: i + 1, slot: q.slot, text: given.get(q.slot) ?? "" }))
    .filter((a) => a.text.length > 0);
  const stillOpen = blocking
    .map((q, i) => ({ n: i + 1, slot: q.slot, question: q.question }))
    .filter((q) => !given.has(q.slot));

  // canAccept is answered by resolveAccept, never by counting here: the module
  // that owns the gate is the module that decides whether it is open.
  const canAccept =
    intent.kind === "accept" && resolveAccept({ kind: "accept", answers: given }, p).ok;

  return ok({
    ref: p.id.slice(0, 12),
    intent: intent.kind,
    answers,
    stillOpen,
    canAccept,
    reason: intent.kind === "reject" ? intent.reason : null,
  });
}

// ---------------------------------------------------------------------------
// record answers
// ---------------------------------------------------------------------------

export interface AnswerInput {
  readonly ref?: string;
  readonly answers: Array<{ n?: number; slot?: string; text: string }>;
}

export interface AnswerValue {
  readonly ref: string;
  readonly recorded: Array<{ n: number; slot: string; text: string }>;
  readonly stillOpen: Array<{ n: number; slot: string; question: string }>;
  readonly canAccept: boolean;
}

/**
 * Record answers without accepting, so a person can answer question 2 today and
 * question 1 on Thursday. `n` indexes the STORED proposal's blocking questions,
 * never a freshly computed list -- the numbering a human saw is the numbering
 * that binds them.
 */
export function answer(input: AnswerInput): Result<AnswerValue, HandlerError> {
  const root = stateRoot();
  const pending = resolvePendingRef(root, input.ref);
  if (!pending.ok) return pending;
  const rec = pending.value;
  const merged = mergeAnswers(rec.proposal, rec.answers, input.answers);
  if (!merged.ok) return merged;
  writePending(root, { ...rec, answers: merged.value });
  const stillOpen = stillOpenView(rec.proposal, merged.value);
  return ok({
    ref: rec.proposal.id.slice(0, 12),
    recorded: recordedView(rec.proposal, merged.value),
    stillOpen,
    canAccept: stillOpen.length === 0,
  });
}

function mergeAnswers(
  p: OntologyProposal,
  existing: Record<string, string>,
  incoming: Array<{ n?: number; slot?: string; text: string }>,
): Result<Record<string, string>, HandlerError> {
  const blocking = p.openQuestions.filter((q) => q.blocking);
  const out: Record<string, string> = { ...existing };
  for (const a of incoming) {
    let slot = a.slot;
    if (slot === undefined) {
      const n = a.n ?? 0;
      const q = blocking[n - 1];
      if (q === undefined) {
        return fail("QUESTION_OUT_OF_RANGE", `there is no blocking question ${n}`, {
          n,
          blockingCount: blocking.length,
        });
      }
      slot = q.slot;
    } else if (!blocking.some((q) => q.slot === slot)) {
      return fail("UNKNOWN_QUESTION", `no open blocking question at ${slot}`, {
        slot,
        slots: blocking.map((q) => q.slot),
      });
    }
    out[slot] = a.text;
  }
  return ok(out);
}

function recordedView(
  p: OntologyProposal,
  answers: Record<string, string>,
): Array<{ n: number; slot: string; text: string }> {
  return p.openQuestions
    .filter((q) => q.blocking)
    .map((q, i) => ({ n: i + 1, slot: q.slot, text: answers[q.slot] ?? "" }))
    .filter((a) => a.text.length > 0);
}

function stillOpenView(
  p: OntologyProposal,
  answers: Record<string, string>,
): Array<{ n: number; slot: string; question: string }> {
  return p.openQuestions
    .filter((q) => q.blocking)
    .map((q, i) => ({ n: i + 1, slot: q.slot, question: q.question }))
    .filter((q) => (answers[q.slot] ?? "").length === 0);
}

// ---------------------------------------------------------------------------
// accept
// ---------------------------------------------------------------------------

export interface AcceptInput {
  readonly ref?: string;
  readonly acceptedBy: string;
  readonly domain?: string;
  readonly answers?: Array<{ n?: number; slot?: string; text: string }>;
  readonly acknowledgeUnmapped?: boolean;
}

export interface AcceptValue {
  readonly ontologyId: string;
  readonly proposalId: string;
  readonly ref: string;
  readonly slug: string;
  readonly domain: string;
  readonly domainHash: string;
  readonly reconciliation: Reconciliation;
  readonly acceptedBy: string;
  readonly acceptedByAuthenticated: false;
  readonly acceptedAt: number;
  readonly idempotent: boolean;
}

export function accept(input: AcceptInput): Result<AcceptValue, HandlerError> {
  const root = stateRoot();
  const pending = resolvePendingRef(root, input.ref);
  if (!pending.ok) return pending;
  const rec = pending.value;
  const p = rec.proposal;

  const merged = mergeAnswers(p, rec.answers, input.answers ?? []);
  if (!merged.ok) return merged;
  const answers = merged.value;

  /**
   * Persist the merged answers BEFORE any gate can refuse.
   *
   * Every refusal below is a two-call flow: the tool description tells the agent
   * to relay something to the human and call again. Previously the merged
   * answers were held only in this local and the record was written solely on
   * the success path, so answers supplied on the call that got refused were
   * discarded. An agent following the documented flow verbatim would answer
   * every question, be refused for an unrelated reason, call again with the
   * acknowledgement, and be told BLOCKING_QUESTIONS_OPEN -- telling the human
   * they answered nothing immediately after they answered everything.
   *
   * Writing here makes answering monotonic: a refusal never costs the human
   * work they already did.
   */
  if (Object.keys(answers).length !== Object.keys(rec.answers).length) {
    writePending(root, { ...rec, answers });
  }

  const key = input.domain ?? DEFAULT_DOMAIN;
  const domain = resolveDomain(key);
  if (!domain.ok) return domain;
  const world = domain.value;

  // The open-questions gate runs FIRST, and `activate` owns it: the module that
  // defines the gate is the module that decides whether it is open. Only once a
  // proposal could legitimately activate is it worth telling the human what the
  // executable domain will ignore.
  const answered = Object.keys(answers);
  const acceptedAt = now();
  const active = activate(p, {
    transition: world.transition,
    invariants: world.invariants,
    answered,
    acceptedBy: input.acceptedBy,
    at: acceptedAt,
  });
  if (!active.ok) return active;

  const reconciliation = reconcile(p, world);
  if (reconciliation.unmappedFromContext.length > 0 && input.acknowledgeUnmapped !== true) {
    return fail(
      "RECONCILIATION_UNACKNOWLEDGED",
      `the executable domain "${key}" ignores ${reconciliation.unmappedFromContext.length} field(s) the human was shown as read from their own context; they have to be told before this can be accepted`,
      { ...reconciliation, domain: key },
    );
  }

  const dHash = domainHash(world);
  /**
   * The idempotency key covers the answer VALUES, not just which slots were
   * answered.
   *
   * Keying on slot names alone conflates "the same acceptance, retried" with "a
   * different acceptance of the same questions". A human correcting an answer --
   * `kilos` to `units` -- fills the same slots, so the corrected call matched an
   * existing record, returned `idempotent: true` with the OLD ontologyId, and
   * left the acceptance record permanently carrying the superseded value while
   * reporting success. The acceptance record is the audit artifact; an audit
   * artifact that silently keeps the wrong answer is worse than no record.
   */
  const answersKey = h(answers);
  const existing = listAcceptances(root).find(
    (a) =>
      a.proposalId === p.id &&
      a.domainHash === dHash &&
      a.acceptedBy === input.acceptedBy &&
      h(a.answers ?? {}) === answersKey,
  );
  if (existing !== undefined) {
    // A retry on a channel with no delivery receipts must not mint twice.
    return ok({ ...acceptanceView(existing), idempotent: true });
  }

  const record: AcceptanceRecord = {
    kind: "parallax.acceptance/v1",
    // Identity covers the answer VALUES, not only which slots were filled --
    // two acceptances that differ in what the human actually said are different
    // acceptances, and must not collide.
    ontologyId: h({
      proposalId: p.id,
      domainHash: dHash,
      answers,
      acceptedBy: input.acceptedBy,
      acceptedAt,
    }),
    proposalId: p.id,
    cwd: rec.cwd,
    slug: p.slug,
    source: p.source,
    answered,
    answers,
    domain: key,
    domainHash: dHash,
    reconciliation,
    acknowledgedUnmapped: input.acknowledgeUnmapped === true,
    proposerVersion: proposerVersion(),
    acceptedBy: input.acceptedBy,
    acceptedByAuthenticated: false,
    acceptedAt,
  };
  writeAcceptance(root, record);
  writeHead(root, null);
  return ok({ ...acceptanceView(record), idempotent: false });
}

function acceptanceView(a: AcceptanceRecord): Omit<AcceptValue, "idempotent"> {
  return {
    ontologyId: a.ontologyId,
    proposalId: a.proposalId,
    ref: a.proposalId.slice(0, 12),
    slug: a.slug,
    domain: a.domain,
    domainHash: a.domainHash,
    reconciliation: a.reconciliation,
    acceptedBy: a.acceptedBy,
    acceptedByAuthenticated: false,
    acceptedAt: a.acceptedAt,
  };
}

/**
 * What the human was shown, against what will actually execute.
 *
 * Computed ABOVE `activate` so `src/core/ontology.ts` and its tests stay
 * untouched, and disclosed rather than applied silently. Without this the accept
 * gate is theatre: a person accepts a reading of their workspace and a different
 * object runs.
 */
function reconcile(p: OntologyProposal, world: TypeRecord): Reconciliation {
  const fromContext = Object.keys(p.initial);
  const fromDomain = Object.keys(world.initial);
  return {
    covered: fromContext.filter((k) => fromDomain.includes(k)),
    unmappedFromContext: fromContext.filter((k) => !fromDomain.includes(k)),
    domainOnly: fromDomain.filter((k) => !fromContext.includes(k)),
  };
}

// ---------------------------------------------------------------------------
// reject
// ---------------------------------------------------------------------------

export interface RejectInput {
  readonly ref?: string;
  readonly reason: string;
}

export interface RejectValue {
  readonly ref: string;
  readonly rejectedAt: number;
  readonly archivedPath: string;
}

export function reject(input: RejectInput): Result<RejectValue, HandlerError> {
  const root = stateRoot();
  const pending = resolvePendingRef(root, input.ref);
  if (!pending.ok) return pending;
  const at = now();
  const archivedPath = archiveRejected(root, {
    kind: "parallax.rejection/v1",
    proposal: pending.value.proposal,
    reason: input.reason,
    at,
  });
  return ok({ ref: pending.value.proposal.id.slice(0, 12), rejectedAt: at, archivedPath });
}

// ---------------------------------------------------------------------------
// re-mint
// ---------------------------------------------------------------------------

export interface Minted {
  readonly active: ActiveOntology;
  readonly world: TypeRecord;
  readonly reconciliation: Reconciliation;
}

/**
 * Re-derive an ActiveOntology from an acceptance receipt, in THIS process.
 *
 * `ActiveOntology` is branded with a module-private symbol checked at runtime,
 * so it cannot cross a process boundary: what round-trips is DATA, and the
 * ontology is re-minted where it will execute. Seven ordered steps, each with
 * its own code, run on EVERY execution. There is deliberately no cross-call
 * cache anywhere in this module -- a `Map<ontologyId, ActiveOntology>` passes
 * every local test, because a test run is one process, and evaporates in
 * production, because a session is a new process per turn. The symptom is "it
 * worked when I ran the demo".
 *
 * Each refusal is a real one. An acceptance is bound to a reading of the world;
 * when the world moved, asking again is the honest answer and re-deriving
 * silently is the failure this system exists to refuse.
 */
export function mint(rec: AcceptanceRecord): Result<Minted, HandlerError> {
  // 1. the workspace is the same workspace
  if (resolve(rec.cwd) !== resolve(process.cwd())) {
    return fail("WORKSPACE_MOVED", "this acceptance was made in a different directory", {
      acceptedIn: rec.cwd,
      runningIn: process.cwd(),
    });
  }
  // 2. the proposer that produced the questions is the proposer running now
  const version = proposerVersion();
  if (version !== rec.proposerVersion) {
    return fail("PROPOSER_CHANGED", "the proposer changed since this was accepted", {
      acceptedUnder: rec.proposerVersion,
      runningUnder: version,
    });
  }
  // 3. the context still hashes to what was accepted
  const proposed = proposeOntology(rec.source);
  if (!proposed.ok) return { ok: false, error: proposed.error };
  const p = proposed.value;
  if (p.id !== rec.proposalId) {
    return fail("PROPOSAL_STALE", "the context changed since this ontology was accepted", {
      was: rec.proposalId,
      now: p.id,
      openSlotsNow: p.openQuestions.filter((q) => q.blocking).map((q) => q.slot),
      answeredThen: rec.answered,
    });
  }
  // 4. the domain is registered and valid
  const domain = resolveDomain(rec.domain);
  if (!domain.ok) return domain;
  const world = domain.value;
  // 5. and it is the same domain, code included -- otherwise "accepted" would
  //    name something mutable
  const dHash = domainHash(world);
  if (dHash !== rec.domainHash) {
    return fail("DOMAIN_CHANGED", `domain "${rec.domain}" changed since this was accepted`, {
      was: rec.domainHash,
      now: dHash,
    });
  }
  // 6. mint through the one function that can mint
  const active = activate(p, {
    transition: world.transition,
    invariants: world.invariants,
    answered: rec.answered,
    acceptedBy: rec.acceptedBy,
    at: rec.acceptedAt,
  });
  if (!active.ok) return active;
  // 7. read the world out through the runtime brand check, then apply the
  //    reconciliation that was disclosed and acknowledged at acceptance time
  const w = worldOf(active.value);
  if (!w.ok) return w;
  return ok({
    active: active.value,
    world: { ...w.value, initial: world.initial, actions: world.actions },
    reconciliation: rec.reconciliation,
  });
}

// ---------------------------------------------------------------------------
// run
// ---------------------------------------------------------------------------

export interface RunInput {
  readonly ontologyId?: string;
  readonly horizon?: number;
  readonly seed?: number;
  readonly governed?: boolean;
  readonly trials?: number;
  readonly policy?: string;
}

export interface RunValue {
  readonly runId: string;
  readonly url: string;
  readonly receiptPath: string;
  readonly ontologyId: string;
  readonly horizon: number;
  readonly seed: number;
  readonly governed: boolean;
  readonly branch: string;
  readonly branchClass: string;
  readonly certificate: {
    policy: string;
    declared: string;
    effective: string;
    demoted: boolean;
    trials: number;
    reason: string;
  };
  readonly violations: { baseline: number; run: number };
  readonly diff: Array<{ key: string; from: unknown; to: unknown }>;
  readonly scores: Array<{ objective: string; value: number; admissible: boolean; origin: string }>;
  readonly traceHash: { baseline: string; run: string };
  readonly steps: number;
  readonly origins: { observed: number; simulated: number };
  readonly reconciliation: Reconciliation;
  readonly text: string;
}

const POLICIES: Record<string, () => Policy> = {
  eager: () => eagerAgent("PINNED"),
};

/** Domain-general folds. Nothing here knows what a storefront or a clinic is. */
const OBJECTIVES: Objective[] = [
  { name: "steps", of: (t) => t.length },
  {
    name: "violations",
    of: (t) => t.reduce((n, s) => n + s.violations.length, 0),
    direction: "minimize",
  },
];

export async function run(input: RunInput = {}): Promise<Result<RunValue, HandlerError>> {
  const root = stateRoot();
  const found = findAcceptance(root, input.ontologyId);
  if (!found.ok) return found;
  const rec = found.value;

  const minted = mint(rec);
  if (!minted.ok) return minted;
  const world = minted.value.world;

  const horizon = input.horizon ?? 12;
  const seed = input.seed ?? 42;
  const governed = input.governed ?? true;
  const trials = input.trials ?? 3;
  const policyKey = input.policy ?? "eager";
  const make = POLICIES[policyKey];
  if (make === undefined) {
    return fail("UNKNOWN_POLICY", `no policy registered as "${policyKey}"`, {
      given: policyKey,
      known: Object.keys(POLICIES),
    });
  }

  const probe = { state: world.initial, seq: 0, seed };
  const baseCert = await certifyPolicy(make(), probe, trials);
  if (!baseCert.ok) return baseCert;

  const log = new EventLog();
  const base = await rolloutCertified(world, log, "main", make(), baseCert.value, horizon, seed);
  const baseState = observe(world, log, "main");

  let branch = "main";
  let cert = baseCert.value;
  let primary = base;
  if (governed) {
    branch = "governed";
    log.fork(branch, "main", 0);
    const shield = (e: Omit<Event, "seq" | "branch">) =>
      check(world, step(world, observe(world, log, branch), { ...e, seq: -1, branch }), -1).length >
      0;
    const gov = governedAgent(make(), shield);
    const govCert = await certifyPolicy(gov, probe, trials);
    if (!govCert.ok) return govCert;
    cert = govCert.value;
    primary = await rolloutCertified(world, log, branch, gov, cert, horizon, seed);
  }

  const scores = OBJECTIVES.map((o) => score(primary.trajectory, o))
    .filter((s) => s.ok)
    .map((s) => s.value);
  const origins = splitOrigins(primary.trajectory.map((s) => s.origin));
  // A run id over its own INPUTS, so the same ontology at the same seed and
  // horizon is the same run. That is what lets a lost receipt be regenerated
  // instead of mourned.
  const runId = h({
    ontologyId: rec.ontologyId,
    horizon,
    seed,
    governed,
    trials,
    policy: policyKey,
  });
  const branchClass = log.branchClass(branch);
  const runTrace = traceHash(log, branch);
  const baseTrace = traceHash(log, "main");

  const html = renderReceipt({
    runId,
    ontology: minted.value.active,
    certificate: cert,
    trajectory: primary.trajectory,
    scores,
    traceHash: runTrace,
    branchClass,
    ...(governed ? { baseline: { traceHash: baseTrace, violations: base.violations.length } } : {}),
  });

  const record: RunRecord = {
    kind: "parallax.run/v1",
    runId,
    ontologyId: rec.ontologyId,
    at: now(),
    horizon,
    seed,
    governed,
    trials,
    branch,
    branchClass,
    certificate: { ...cert },
    violations: { baseline: base.violations.length, run: primary.violations.length },
    diff: diff(baseState, observe(world, log, branch)),
    scores: scores.map((s) => ({ ...s })),
    traceHash: { baseline: baseTrace, run: runTrace },
    steps: primary.trajectory.length,
    origins,
    // `RunReceipt` has no field for this, so the disclosure that the executed
    // model ignored part of what the human was shown lives here.
    reconciliation: minted.value.reconciliation,
    receiptPath: runReceiptPath(root, runId),
    url: `/r/${runId}`,
  };
  writeRun(root, record, html);

  const value: RunValue = {
    runId,
    url: record.url,
    receiptPath: record.receiptPath,
    ontologyId: rec.ontologyId,
    horizon,
    seed,
    governed,
    branch,
    branchClass,
    certificate: {
      policy: cert.policy,
      declared: cert.declared,
      effective: cert.effective,
      demoted: cert.demoted,
      trials: cert.trials,
      reason: cert.reason,
    },
    violations: record.violations,
    diff: record.diff,
    scores: scores.map((s) => ({
      objective: s.objective,
      value: s.value,
      admissible: s.admissible,
      origin: s.origin,
    })),
    traceHash: record.traceHash,
    steps: record.steps,
    origins,
    reconciliation: minted.value.reconciliation,
    text: "",
  };
  return ok({ ...value, text: summarise(value, world.title) });
}

/**
 * The sentence a channel sends. Built from the run's own values by CODE, so the
 * agent relaying it has no reason to author a number itself -- a restated number
 * is an invented number the moment it is wrong.
 */
function summarise(v: RunValue, title: string): string {
  const lines = [
    title,
    `${v.steps} steps on branch ${v.branch}, horizon ${v.horizon}, seed ${v.seed}.`,
    `violations: ${v.violations.baseline} ungoverned -> ${v.violations.run} here.`,
    `trace ${v.traceHash.run.slice(0, 16)} -- replay is a hash comparison, not a claim.`,
    `policy ${v.certificate.policy}: declared ${v.certificate.declared}, demonstrated ${v.certificate.effective}${v.certificate.demoted ? " (DEMOTED)" : ""} over ${v.certificate.trials} trials.`,
    `branch class ${v.branchClass}. ${v.origins.observed} observed / ${v.origins.simulated} simulated.`,
  ];
  if (v.reconciliation.unmappedFromContext.length > 0) {
    lines.push(
      `the executable domain ignored ${v.reconciliation.unmappedFromContext.length} field(s) read from the context: ${v.reconciliation.unmappedFromContext.join(", ")}.`,
    );
  }
  lines.push(
    `a policy that passes certification has not been proven pure; it failed to be caught in ${v.certificate.trials} trials.`,
    `receipt ${v.url}`,
  );
  return lines.join("\n");
}

function findAcceptance(root: string, ontologyId?: string): Result<AcceptanceRecord, HandlerError> {
  const all = listAcceptances(root);
  // "the id you named is unknown" and "nothing has ever been accepted here" are
  // different problems and lead to different next actions, so they get different
  // codes rather than one message that covers both badly.
  if (all.length === 0) {
    return fail("NO_ACCEPTED_ONTOLOGY", "nothing has been accepted in this workspace yet", {
      ...(ontologyId === undefined || ontologyId.length === 0 ? {} : { asked: ontologyId }),
    });
  }
  if (ontologyId === undefined || ontologyId.length === 0) {
    const newest = all[0];
    if (newest === undefined) {
      return fail("NO_ACCEPTED_ONTOLOGY", "nothing has been accepted in this workspace yet");
    }
    return ok(newest);
  }
  const exact = readAcceptance(root, ontologyId);
  if (exact !== null) return ok(exact);
  const matches = all.filter((a) => a.ontologyId.startsWith(ontologyId));
  const first = matches[0];
  if (first === undefined) {
    return fail("UNKNOWN_ONTOLOGY", `no accepted ontology starts with ${ontologyId}`, {
      given: ontologyId,
      known: all.map((a) => a.ontologyId.slice(0, 12)),
    });
  }
  if (matches.length > 1) {
    return fail("AMBIGUOUS_REF", `${matches.length} accepted ontologies start with ${ontologyId}`, {
      given: ontologyId,
      matches: matches.map((a) => a.ontologyId.slice(0, 12)),
    });
  }
  return ok(first);
}

// ---------------------------------------------------------------------------
// receipt
// ---------------------------------------------------------------------------

export interface ReceiptInput {
  readonly runId?: string;
  readonly out?: string;
}

export interface ReceiptValue {
  readonly runId: string;
  readonly url: string;
  readonly receiptPath: string;
  readonly bytes: number;
  readonly regenerated: boolean;
  readonly writtenTo: string | null;
  readonly html: string;
}

/**
 * Hand back the proof for a run.
 *
 * If the rendered page is gone -- an ephemeral filesystem, a redeploy, a wiped
 * workspace -- it is REGENERATED from the recorded parameters rather than
 * reported as missing. The ops layer is deterministic, so the same ontology at
 * the same seed and horizon reproduces the same trajectory and the same trace
 * hash. The receipt is a function of the run, not a file that has to survive.
 */
export async function receipt(
  input: ReceiptInput = {},
): Promise<Result<ReceiptValue, HandlerError>> {
  const root = stateRoot();
  const found = findRun(root, input.runId);
  if (!found.ok) return found;
  const rec = found.value;

  let html = readRunHtml(root, rec.runId);
  let regenerated = false;
  if (html === null) {
    const again = await run({
      ontologyId: rec.ontologyId,
      horizon: rec.horizon,
      seed: rec.seed,
      governed: rec.governed,
      trials: rec.trials,
    });
    if (!again.ok) return again;
    html = readRunHtml(root, rec.runId);
    regenerated = true;
    if (html === null) {
      return fail("UNKNOWN_RUN", `the receipt for ${rec.runId} could not be regenerated`, {
        runId: rec.runId,
      });
    }
  }

  let writtenTo: string | null = null;
  if (input.out !== undefined && input.out.length > 0) {
    const target = resolve(input.out);
    const tmp = `${target}.tmp-${process.pid}`;
    writeFileSync(tmp, html);
    renameSync(tmp, target);
    writtenTo = target;
  }

  return ok({
    runId: rec.runId,
    url: rec.url,
    receiptPath: rec.receiptPath,
    // Buffer.byteLength, not String.length: the receipt contains non-ASCII, so
    // the two differ, and reporting one as the other is exactly the class of
    // quietly-wrong number this product exists to refuse.
    bytes: Buffer.byteLength(html, "utf8"),
    regenerated,
    writtenTo,
    html,
  });
}

function findRun(root: string, runId?: string): Result<RunRecord, HandlerError> {
  const all = listRuns(root);
  if (runId === undefined || runId.length === 0) {
    const newest = all[0];
    if (newest === undefined) return fail("UNKNOWN_RUN", "no run has been recorded here yet");
    return ok(newest);
  }
  const exact = readRun(root, runId);
  if (exact !== null) return ok(exact);
  const matches = all.filter((r) => r.runId.startsWith(runId));
  const first = matches[0];
  if (first === undefined) {
    return fail("UNKNOWN_RUN", `no run starts with ${runId}`, {
      given: runId,
      known: all.map((r) => r.runId.slice(0, 12)),
    });
  }
  if (matches.length > 1) {
    return fail("AMBIGUOUS_REF", `${matches.length} runs start with ${runId}`, {
      given: runId,
      matches: matches.map((r) => r.runId.slice(0, 12)),
    });
  }
  return ok(first);
}

// ---------------------------------------------------------------------------
// status
// ---------------------------------------------------------------------------

export type ThreadState = "IDLE" | "PROPOSED" | "PARTIAL" | "READY" | "ACCEPTED" | "RAN";

export interface StatusValue {
  readonly cwd: string;
  readonly stateDir: string;
  readonly readable: boolean;
  readonly entryCount: number;
  readonly state: ThreadState;
  readonly domains: readonly string[];
  readonly head: null | {
    ref: string;
    proposalId: string;
    slug: string;
    title: string;
    proposedAt: number;
    answersRecorded: number;
    blockingRemaining: Array<{ n: number; slot: string; question: string }>;
  };
  readonly pending: Array<{ ref: string; slug: string; proposedAt: number }>;
  readonly accepted: Array<{
    ontologyId: string;
    proposalId: string;
    slug: string;
    domain: string;
    acceptedBy: string;
    acceptedAt: number;
    mintable: boolean;
    mintError: { code: string; reason: string } | null;
  }>;
  readonly runs: Array<{
    runId: string;
    ontologyId: string;
    at: number;
    violations: number;
    branchClass: string;
    url: string;
  }>;
}

/**
 * Where this thread stands, read from disk.
 *
 * An unreadable working directory is reported as `readable: false`, not as a
 * failure -- the caller asked where things stand and that IS where things stand.
 * `mintable` is computed by actually running the re-mint (which reads and hashes
 * but executes nothing), so status never claims an acceptance is usable without
 * having checked.
 */
export function status(): Result<StatusValue, HandlerError> {
  const cwd = resolve(process.cwd());
  const root = stateRoot(cwd);
  let readable = true;
  let entryCount = 0;
  try {
    entryCount = readdirSync(cwd).length;
  } catch {
    readable = false;
  }

  const pending = listPending(root);
  const headId = readHead(root);
  const headRec = pending.find((p) => p.proposal.id === headId) ?? null;
  const accepted = listAcceptances(root);
  const runs = listRuns(root);

  let state: ThreadState = "IDLE";
  if (headRec !== null) {
    const open = stillOpenView(headRec.proposal, headRec.answers);
    state =
      open.length === 0
        ? "READY"
        : Object.keys(headRec.answers).length > 0
          ? "PARTIAL"
          : "PROPOSED";
  } else if (runs.length > 0) {
    state = "RAN";
  } else if (accepted.length > 0) {
    state = "ACCEPTED";
  }

  return ok({
    cwd,
    stateDir: root,
    readable,
    entryCount,
    state,
    domains: DOMAIN_KEYS,
    head:
      headRec === null
        ? null
        : {
            ref: headRec.proposal.id.slice(0, 12),
            proposalId: headRec.proposal.id,
            slug: headRec.proposal.slug,
            title: headRec.proposal.title,
            proposedAt: headRec.proposedAt,
            answersRecorded: Object.keys(headRec.answers).length,
            blockingRemaining: stillOpenView(headRec.proposal, headRec.answers),
          },
    pending: pending.map((p) => ({
      ref: p.proposal.id.slice(0, 12),
      slug: p.proposal.slug,
      proposedAt: p.proposedAt,
    })),
    accepted: accepted.map((a) => {
      const m = mint(a);
      return {
        ontologyId: a.ontologyId,
        proposalId: a.proposalId,
        slug: a.slug,
        domain: a.domain,
        acceptedBy: a.acceptedBy,
        acceptedAt: a.acceptedAt,
        mintable: m.ok,
        mintError: m.ok ? null : { code: m.error.code, reason: m.error.reason },
      };
    }),
    runs: runs.map((r) => ({
      runId: r.runId,
      ontologyId: r.ontologyId,
      at: r.at,
      violations: r.violations.run,
      branchClass: r.branchClass,
      url: r.url,
    })),
  });
}
