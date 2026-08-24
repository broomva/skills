import { readFileSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { type RunReceipt, renderReceipt } from "../artifact/receipt";
import type { ChannelMessage } from "../channel/conversation";
import { parseReply, renderProposal, resolveAccept } from "../channel/conversation";
import { h } from "../core/hash";
import { EventLog } from "../core/log";
import type { ContextSource, OntologyProposal } from "../core/ontology";
import { activate, proposeOntology, worldOf } from "../core/ontology";
import type { Certificate, Objective, Score, Trajectory } from "../core/ops";
import { certifyPolicy, rolloutCertified, score, traceHash } from "../core/ops";
import { fail, ok, type ParallaxError, type Result } from "../core/result";
import type { Violation } from "../core/types";
import { bindDomain, LEDGER_KEY, shieldedPolicy } from "./domain";
import type { HubState, OntologyRecord, ThreadRecord } from "./registry";
import { createState } from "./registry";
import { type StaticRoot, serveStatic, staticRoot } from "./static";
import { httpStatusFor } from "./status";

/**
 * The Parallax hub.
 *
 * One HTTP surface over the same functions the library exposes in-process. The
 * routes below add exactly two things to those functions: a way to name an
 * `ActiveOntology` that cannot be serialised (an id into a server-side
 * registry, see `registry.ts`), and a status code. They add no error
 * vocabulary, no second set of rules about when an ontology may run, and no
 * numbers of their own. Everything a human can reach here, an agent reaches the
 * same way, and gets the same typed values back.
 */

const HUB_HORIZON = 12;
const HUB_SEED = 42;
/** Trials for the policy certification probe. See `certifyPolicy` on its false-negative bound. */
const CERT_TRIALS = 3;

export interface HubOptions {
  /** Directory served as static content. Defaults to this runtime's `hub-static/`. */
  readonly landingDir?: string;
  /** The context that `propose` reads. Defaults to the process working directory. */
  readonly contextRoot?: string;
  readonly version?: string;
  readonly now?: () => number;
}

export interface Hub {
  readonly fetch: (req: Request) => Promise<Response>;
  readonly state: HubState;
  readonly version: string;
}

const HERE = fileURLToPath(new URL(".", import.meta.url));
// The product page is a Next export served by GitHub Pages; the hub serves its
// OWN front door instead. Two hosts serving the same marketing page out of two
// sources is a page that drifts, and this one has a job the Pages artifact
// cannot do: it reports the commit this instance is running.
const DEFAULT_LANDING = resolve(HERE, "..", "..", "hub-static");
const PKG = resolve(HERE, "..", "..", "package.json");

function readVersion(): string {
  try {
    const parsed: unknown = JSON.parse(readFileSync(PKG, "utf8"));
    if (typeof parsed === "object" && parsed !== null) {
      const v = (parsed as Record<string, unknown>).version;
      if (typeof v === "string") return v;
    }
  } catch {
    // A hub that cannot read its own package.json still serves; it just does
    // not know its version, and says so rather than guessing one.
  }
  return "unknown";
}

export function createHub(options: HubOptions = {}): Hub {
  const now = options.now ?? (() => Date.now());
  const version = options.version ?? readVersion();
  const contextRoot = resolve(options.contextRoot ?? process.cwd());
  const landing: StaticRoot = staticRoot(options.landingDir ?? DEFAULT_LANDING);
  const state = createState(now());

  async function handle(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const path = url.pathname;

    if (path === "/health") {
      if (req.method !== "GET" && req.method !== "HEAD") return methodNotAllowed("GET, HEAD");
      /**
       * `commit` is what makes this endpoint usable as a deploy check.
       *
       * `version` is a constant in the source, so a deploy that built but
       * silently kept serving the previous image answers 200 with a byte-identical
       * body. Polling that -- or the platform's own deploy status API -- confirms
       * a deploy was REPORTED, never that the code answering requests is the code
       * that was pushed. The only thing that settles it is a value only the new
       * build can emit.
       *
       * Render injects RENDER_GIT_COMMIT. Locally there is none, and "local" is
       * the honest answer rather than a fabricated sha.
       */
      return json({
        ok: true,
        version,
        commit: process.env.RENDER_GIT_COMMIT ?? "local",
        uptimeSeconds: Math.max(0, Math.floor((now() - state.startedAt) / 1000)),
      });
    }

    if (path.startsWith("/api/")) {
      if (req.method !== "POST") return methodNotAllowed("POST");
      const body = await readJson(req);
      if (!body.ok) return errorResponse(body.error);
      switch (path) {
        case "/api/ontology/propose":
          return handlePropose(body.value);
        case "/api/ontology/accept":
          return handleAccept(body.value);
        case "/api/run":
          return await handleRun(body.value, originOf(req));
        case "/api/whatsapp/turn":
          return await handleTurn(body.value, originOf(req));
        default:
          return errorResponse(unwrap(fail("UNKNOWN_ROUTE", `no endpoint at ${path}`, { path })));
      }
    }

    if (path.startsWith("/r/")) {
      if (req.method !== "GET" && req.method !== "HEAD") return methodNotAllowed("GET, HEAD");
      return handleReceipt(path.slice("/r/".length), req.method === "HEAD");
    }

    if (req.method !== "GET" && req.method !== "HEAD") return methodNotAllowed("GET, HEAD");
    const outcome = serveStatic(landing, req, path);
    if (outcome.kind === "file") return outcome.response;
    if (outcome.kind === "escape") {
      return errorResponse(
        unwrap(
          fail(
            "PATH_ESCAPES_ROOT",
            "this path resolves outside the directory the hub serves, so it is refused",
            outcome.detail,
          ),
        ),
      );
    }
    return errorResponse(unwrap(fail("NOT_FOUND", `nothing is served at ${path}`, { path })));
  }

  // ----------------------------------------------------------------- propose

  function handlePropose(body: Record<string, unknown>): Response {
    const source = readSource(body, contextRoot);
    if (!source.ok) return errorResponse(source.error);

    const proposed = proposeOntology(source.value.source);
    if (!proposed.ok) return errorResponse(proposed.error);

    const proposal = proposed.value;
    state.proposals.set(proposal.id, {
      proposal,
      proposedAt: now(),
      root: source.value.root,
    });
    return json({ proposal: onTheWire(proposal, contextRoot) });
  }

  // ------------------------------------------------------------------ accept

  function handleAccept(body: Record<string, unknown>): Response {
    const proposalId = requiredString(body, "proposalId");
    if (!proposalId.ok) return errorResponse(proposalId.error);
    const acceptedBy = requiredString(body, "acceptedBy");
    if (!acceptedBy.ok) return errorResponse(acceptedBy.error);
    const answers = readAnswers(body.answers);
    if (!answers.ok) return errorResponse(answers.error);

    const record = state.proposals.get(proposalId.value);
    if (record === undefined) {
      return errorResponse(
        unwrap(
          fail(
            "UNKNOWN_PROPOSAL",
            "this hub has no proposal with that id; propose again and accept the proposal you get back",
            { proposalId: proposalId.value },
          ),
        ),
      );
    }

    const accepted = acceptProposal(record.proposal, answers.value, acceptedBy.value, now());
    if (!accepted.ok) return errorResponse(accepted.error);
    state.ontologies.set(accepted.value.ontologyId, accepted.value);
    return json({
      ontologyId: accepted.value.ontologyId,
      world: { slug: accepted.value.world.slug, title: accepted.value.world.title },
      acceptedAt: accepted.value.acceptedAt,
    });
  }

  /**
   * Mint the ontology.
   *
   * The transition and the invariants come from `bindDomain`, which reads the
   * proposal's shape and nothing else. Nothing executable is ever taken from
   * the request: an accept body that could name a module to import would make
   * this endpoint remote code execution, and the fact that it would be
   * convenient is exactly why the door is nailed shut here rather than guarded
   * by a comment.
   */
  function acceptProposal(
    proposal: OntologyProposal,
    answers: Record<string, string>,
    acceptedBy: string,
    at: number,
  ): Result<OntologyRecord, ParallaxError<string>> {
    const blocking = new Set(proposal.openQuestions.filter((q) => q.blocking).map((q) => q.slot));
    const known = new Set(proposal.openQuestions.map((q) => q.slot));
    for (const slot of Object.keys(answers)) {
      if (!known.has(slot)) {
        return fail("UNKNOWN_QUESTION", `no open question at ${slot}`, {
          slot,
          openSlots: [...known],
        });
      }
    }

    const binding = bindDomain(proposal);
    const answered = Object.keys(answers).filter((slot) => blocking.has(slot));
    const active = activate(proposal, {
      transition: binding.transition,
      invariants: binding.invariants,
      answered,
      acceptedBy,
      at,
    });
    if (!active.ok) return active;
    const world = worldOf(active.value);
    if (!world.ok) return world;

    // The id names the DECISION, not the moment. Excluding the clock means the
    // same proposal, answered the same way by the same person, mints the same
    // id after a restart -- which is what makes a receipt URL regenerable on a
    // host with no persistent disk. `acceptedAt` is recorded, just not hashed.
    const ontologyId = h({
      proposalId: proposal.id,
      answers,
      acceptedBy,
      domain: binding.name,
    });
    return ok({
      ontologyId,
      active: active.value,
      world: world.value,
      binding,
      proposalId: proposal.id,
      answers,
      acceptedBy,
      acceptedAt: at,
    });
  }

  // --------------------------------------------------------------------- run

  async function handleRun(body: Record<string, unknown>, origin: string): Promise<Response> {
    const ontologyId = requiredString(body, "ontologyId");
    if (!ontologyId.ok) return errorResponse(ontologyId.error);
    const horizon = requiredInt(body, "horizon", 1, 500);
    if (!horizon.ok) return errorResponse(horizon.error);
    const seed = requiredInt(body, "seed", 0, 0xffffffff);
    if (!seed.ok) return errorResponse(seed.error);
    const governed = readBoolean(body.governed, true);
    if (!governed.ok) return errorResponse(governed.error);

    const record = state.ontologies.get(ontologyId.value);
    if (record === undefined) {
      return errorResponse(
        unwrap(
          fail(
            "UNKNOWN_ONTOLOGY",
            "this hub holds no accepted ontology with that id; accept a proposal to get one",
            { ontologyId: ontologyId.value },
          ),
        ),
      );
    }

    const run = await performRun(record, {
      horizon: horizon.value,
      seed: seed.value,
      governed: governed.value,
      origin,
    });
    if (!run.ok) return errorResponse(run.error);
    return json({
      runId: run.value.runId,
      url: run.value.url,
      violations: run.value.violations,
      branchClass: run.value.branchClass,
      scores: run.value.scores,
    });
  }

  interface RunOutcome {
    readonly runId: string;
    readonly url: string;
    readonly violations: Violation[];
    readonly branchClass: string;
    readonly scores: Score[];
    readonly baselineViolations: number;
  }

  /**
   * Roll the accepted model forward.
   *
   * `rolloutCertified`, never bare `rollout`. The difference is the whole
   * argument: bare `rollout` writes the class a policy DECLARES about itself
   * onto every event it appends, so the log ends up carrying a claim nobody
   * checked. Here `certifyPolicy` probes the policy first and the certificate's
   * demonstrated class is what enters the log -- a policy that cannot reproduce
   * itself is demoted in code however it describes itself. That filter has a
   * documented false-negative rate (see `certifyPolicy`); passing it is not a
   * proof of purity, only a failure to be caught, and the receipt says which
   * class was declared and which was demonstrated so a reader can see both.
   */
  async function performRun(
    record: OntologyRecord,
    opts: { horizon: number; seed: number; governed: boolean; origin: string },
  ): Promise<Result<RunOutcome, ParallaxError<string>>> {
    const world = record.world;
    const base = record.binding.policy();
    const baseCert = await certifyPolicy(
      base,
      { state: world.initial, seq: 0, seed: opts.seed },
      CERT_TRIALS,
    );
    if (!baseCert.ok) return baseCert;

    // One in-memory sqlite log per run. Bun collects it with the request; there
    // is no `close` on EventLog to call, and a run's log is not shared, so a
    // long-lived hub trades a little memory per run for not owning a handle it
    // cannot release. Worth knowing before this is pointed at a busy caller.
    const log = new EventLog();
    const baseline = await rolloutCertified(
      world,
      log,
      "main",
      base,
      baseCert.value,
      opts.horizon,
      opts.seed,
    );

    let branch = "main";
    let cert: Certificate = baseCert.value;
    let trajectory: Trajectory = baseline.trajectory;
    let violations: Violation[] = baseline.violations;

    if (opts.governed) {
      branch = "governed";
      log.fork(branch, "main", 0);
      const governor = shieldedPolicy(world, log, branch, record.binding.policy());
      const govCert = await certifyPolicy(
        governor,
        { state: world.initial, seq: 0, seed: opts.seed },
        CERT_TRIALS,
      );
      if (!govCert.ok) return govCert;
      const governedRun = await rolloutCertified(
        world,
        log,
        branch,
        governor,
        govCert.value,
        opts.horizon,
        opts.seed,
      );
      cert = govCert.value;
      trajectory = governedRun.trajectory;
      violations = governedRun.violations;
    }

    const scores: Score[] = [];
    for (const objective of OBJECTIVES) {
      const s = score(trajectory, objective);
      if (!s.ok) return s;
      scores.push(s.value);
    }

    // Content-derived, so the same request reproduces the same receipt URL.
    const runId = h({
      ontologyId: record.ontologyId,
      horizon: opts.horizon,
      seed: opts.seed,
      governed: opts.governed,
    });
    const receipt: RunReceipt = {
      runId,
      ontology: record.active,
      certificate: cert,
      trajectory,
      scores,
      traceHash: traceHash(log, branch),
      branchClass: log.branchClass(branch),
      ...(opts.governed
        ? {
            baseline: {
              traceHash: traceHash(log, "main"),
              violations: baseline.violations.length,
            },
          }
        : {}),
    };
    const html = renderReceipt(receipt);
    state.runs.set(runId, { runId, html, receipt, at: now() });

    return ok({
      runId,
      url: `${opts.origin}/r/${runId}`,
      violations,
      branchClass: receipt.branchClass,
      scores,
      baselineViolations: baseline.violations.length,
    });
  }

  // ----------------------------------------------------------------- receipt

  function handleReceipt(rawId: string, headOnly: boolean): Response {
    const id = rawId.replace(/\/+$/, "");
    const found = lookupRun(id);
    if (found === null) {
      return errorResponse(
        unwrap(
          fail(
            "UNKNOWN_RUN",
            "no receipt with that id is held by this process; receipts live in memory, so a redeploy or an idle spin-down loses them -- re-running the same ontology at the same horizon and seed rebuilds this exact id",
            { runId: id },
          ),
        ),
      );
    }
    const headers = {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-cache",
      "content-length": String(new TextEncoder().encode(found.html).length),
    };
    return new Response(headOnly ? null : found.html, { status: 200, headers });
  }

  function lookupRun(id: string): { html: string } | null {
    const exact = state.runs.get(id);
    if (exact !== undefined) return exact;
    // The demo links receipts by an 8-character prefix. Accept that, but only
    // when it names exactly one run -- an ambiguous prefix is not an id.
    if (id.length < 8) return null;
    const hits = [...state.runs.keys()].filter((k) => k.startsWith(id));
    const only = hits.length === 1 ? hits[0] : undefined;
    if (only === undefined) return null;
    return state.runs.get(only) ?? null;
  }

  // ---------------------------------------------------------------- whatsapp

  /**
   * The whole propose / accept / run conversation as one turn handler.
   *
   * The seam between a typed error and a message is deliberate: a failure the
   * CALLER can fix -- a missing field, a body that is not JSON, a context that
   * cannot be read -- comes back as a typed error with a status, because the
   * caller here is the channel adapter, not the human. A failure the HUMAN can
   * fix -- an unclear reply, a question still unanswered -- comes back as
   * messages, because that is a turn in the conversation and not a fault.
   *
   * Every message is composed by code from values the run produced. Nothing in
   * this handler restates a number in prose it authored.
   */
  async function handleTurn(body: Record<string, unknown>, origin: string): Promise<Response> {
    const from = requiredString(body, "from");
    if (!from.ok) return errorResponse(from.error);
    const text = requiredString(body, "text");
    if (!text.ok) return errorResponse(text.error);
    const threadId = requiredString(body, "threadId");
    if (!threadId.ok) return errorResponse(threadId.error);

    const thread: ThreadRecord = state.threads.get(threadId.value) ?? {
      stage: "IDLE",
      proposalId: null,
      answers: {},
      lastRunUrl: null,
    };
    state.threads.set(threadId.value, thread);

    const pending = thread.proposalId === null ? undefined : state.proposals.get(thread.proposalId);
    if (thread.stage === "PROPOSED" && pending === undefined) {
      // The pointer outlived the thing it pointed at -- a restart, nothing more.
      thread.stage = "IDLE";
      thread.proposalId = null;
    }

    if (thread.stage !== "PROPOSED" || pending === undefined) {
      const opened = openProposal(thread, thread.lastRunUrl);
      return opened.ok ? json({ messages: opened.value }) : errorResponse(opened.error);
    }

    const proposal = pending.proposal;
    const intent = parseReply(text.value, proposal.openQuestions);

    if (intent.kind === "reject") {
      thread.stage = "IDLE";
      thread.proposalId = null;
      thread.answers = {};
      return json({
        messages: [
          one(
            `Discarded. Nothing ran. Send another message when you want a fresh look at the context.`,
          ),
        ],
      });
    }

    if (intent.kind === "unclear") {
      return json({
        messages: [
          one(
            [
              `I could not read that as an answer.`,
              `Reply with the numbered answers, then ACCEPT to activate, or REJECT to discard.`,
              `ref ${proposal.id.slice(0, 12)}`,
            ].join("\n"),
          ),
        ],
      });
    }

    for (const [slot, value] of intent.answers) thread.answers[slot] = value;

    if (intent.kind === "answers") {
      const missing = proposal.openQuestions.filter(
        (q) => q.blocking && thread.answers[q.slot] === undefined,
      );
      return json({
        messages: [
          one(
            missing.length === 0
              ? `Recorded. Nothing runs until you reply ACCEPT.\nref ${proposal.id.slice(0, 12)}`
              : [
                  `Recorded. Still open (${String(missing.length)}):`,
                  ...missing.map((q, i) => `  ${String(i + 1)}. ${q.question}`),
                  `ref ${proposal.id.slice(0, 12)}`,
                ].join("\n"),
          ),
        ],
      });
    }

    // intent.kind === "accept". `resolveAccept` names exactly what is missing,
    // so the reply asks for the one thing it lacks rather than restarting.
    const merged: ReplyLike = {
      kind: "accept",
      answers: new Map(Object.entries(thread.answers)),
    };
    const resolved = resolveAccept(merged, proposal);
    if (!resolved.ok) {
      const questions = resolved.error.detail?.questions;
      const listed = Array.isArray(questions) ? questions.map((q) => String(q)) : [];
      return json({
        messages: [
          one(
            [
              resolved.error.reason,
              ...listed.map((q, i) => `  ${String(i + 1)}. ${q}`),
              `ref ${proposal.id.slice(0, 12)}`,
            ].join("\n"),
          ),
        ],
      });
    }

    const accepted = acceptProposal(proposal, { ...thread.answers }, from.value, now());
    if (!accepted.ok) return errorResponse(accepted.error);
    state.ontologies.set(accepted.value.ontologyId, accepted.value);

    const run = await performRun(accepted.value, {
      horizon: HUB_HORIZON,
      seed: HUB_SEED,
      governed: true,
      origin,
    });
    if (!run.ok) return errorResponse(run.error);

    thread.stage = "RAN";
    thread.proposalId = null;
    thread.answers = {};
    thread.lastRunUrl = run.value.url;

    return json({
      messages: [
        one(
          [
            `Accepted. The executable model adds one derived field, ${LEDGER_KEY}, so a conservation invariant has a second quantity to check against; everything else is what you were shown.`,
            ``,
            `Ran ${String(HUB_HORIZON)} steps at seed ${String(HUB_SEED)} under the governor.`,
            `Violations: ${String(run.value.violations.length)} (ungoverned baseline: ${String(run.value.baselineViolations)}).`,
            `Branch class: ${run.value.branchClass}.`,
            ...run.value.scores.map(
              (s) =>
                `${s.objective}: ${String(s.value)} (${s.admissible ? "admissible" : "inadmissible"}, ${s.origin})`,
            ),
            ``,
            `Receipt: ${run.value.url}`,
          ].join("\n"),
        ),
      ],
    });
  }

  function openProposal(
    thread: { stage: "IDLE" | "PROPOSED" | "RAN"; proposalId: string | null },
    lastRunUrl: string | null,
  ): Result<ChannelMessage[], ParallaxError<string>> {
    const proposed = proposeOntology({ kind: "agent-workspace", root: contextRoot });
    if (!proposed.ok) return proposed;
    const proposal = proposed.value;
    state.proposals.set(proposal.id, { proposal, proposedAt: now(), root: contextRoot });
    thread.stage = "PROPOSED";
    thread.proposalId = proposal.id;

    const messages = renderProposal(proposal);
    if (lastRunUrl === null) return ok(messages);
    // A fresh look at the context, with the previous run still reachable.
    const preamble = one(`Your last receipt is still at ${lastRunUrl}\nHere is a fresh reading:`);
    return ok(renumber([preamble, ...messages]));
  }

  return { fetch: handle, state, version };
}

// --------------------------------------------------------------------- shared

/** Objectives are server-fixed. A caller-supplied fold would be code from a request. */
const OBJECTIVES: Objective[] = [
  { name: "steps_applied", of: (t: Trajectory) => t.length },
  {
    name: "violations",
    of: (t: Trajectory) => t.reduce((n, s) => n + s.violations.length, 0),
    direction: "minimize",
  },
];

/** `resolveAccept` takes a ReplyIntent; this is the accept arm of it, rebuilt from stored answers. */
type ReplyLike = { kind: "accept"; answers: Map<string, string> };

function one(text: string): ChannelMessage {
  return { text, part: 1, of: 1 };
}

function renumber(messages: ChannelMessage[]): ChannelMessage[] {
  return messages.map((m, i) => ({ text: m.text, part: i + 1, of: messages.length }));
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

/**
 * The error body.
 *
 * The frozen contract describes error bodies two ways -- as the ParallaxError
 * shape itself, and as `{error:{code,reason,detail}}` -- so this emits both:
 * the fields at the top level and the same object under `error`. It is one
 * duplicated object in a failure response, and it means a client written
 * against either reading of the contract works. The VALUE is the library's
 * error, unchanged, either way.
 */
function errorResponse(error: ParallaxError<string>): Response {
  const body =
    error.detail === undefined
      ? { code: error.code, reason: error.reason }
      : { code: error.code, reason: error.reason, detail: error.detail };
  return json({ ...body, error: body }, httpStatusFor(error.code));
}

function methodNotAllowed(allow: string): Response {
  const error = {
    code: "METHOD_NOT_ALLOWED",
    reason: `this endpoint accepts ${allow}`,
    detail: { allow },
  };
  return new Response(JSON.stringify({ ...error, error }), {
    status: httpStatusFor(error.code),
    headers: { "content-type": "application/json; charset=utf-8", allow },
  });
}

/** `fail` returns an Err wrapper; these call sites want the error value itself. */
function unwrap<C extends string>(r: { ok: false; error: ParallaxError<C> }): ParallaxError<C> {
  return r.error;
}

async function readJson(
  req: Request,
): Promise<Result<Record<string, unknown>, ParallaxError<"MALFORMED_BODY">>> {
  let text: string;
  try {
    text = await req.text();
  } catch (e) {
    return fail("MALFORMED_BODY", "the request body could not be read", {
      cause: e instanceof Error ? e.message : String(e),
    });
  }
  if (text.trim().length === 0) {
    return fail("MALFORMED_BODY", "the request body is empty; a JSON object was expected");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    // A parse failure is a value, not a stack. The caller gets a code it can
    // branch on and a sentence it can show; it never gets our internals.
    return fail("MALFORMED_BODY", "the request body is not valid JSON", {
      cause: e instanceof Error ? e.message : String(e),
    });
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return fail("MALFORMED_BODY", "the request body must be a JSON object");
  }
  return ok(parsed as Record<string, unknown>);
}

function requiredString(
  body: Record<string, unknown>,
  field: string,
): Result<string, ParallaxError<"MISSING_FIELD" | "INVALID_FIELD">> {
  const v = body[field];
  if (v === undefined || v === null) {
    return fail("MISSING_FIELD", `${field} is required`, { field });
  }
  if (typeof v !== "string" || v.trim().length === 0) {
    return fail("INVALID_FIELD", `${field} must be a non-empty string`, {
      field,
      got: typeof v,
    });
  }
  return ok(v);
}

function requiredInt(
  body: Record<string, unknown>,
  field: string,
  min: number,
  max: number,
): Result<number, ParallaxError<"MISSING_FIELD" | "INVALID_FIELD">> {
  const v = body[field];
  if (v === undefined || v === null) {
    // No default. A run whose seed was silently chosen for it is not
    // reproducible by anyone who reads the request, which defeats the point.
    return fail("MISSING_FIELD", `${field} is required`, { field });
  }
  if (typeof v !== "number" || !Number.isInteger(v) || v < min || v > max) {
    return fail("INVALID_FIELD", `${field} must be an integer between ${min} and ${max}`, {
      field,
      min,
      max,
    });
  }
  return ok(v);
}

function readBoolean(
  v: unknown,
  fallback: boolean,
): Result<boolean, ParallaxError<"INVALID_FIELD">> {
  if (v === undefined || v === null) return ok(fallback);
  if (typeof v !== "boolean") {
    return fail("INVALID_FIELD", "governed must be a boolean", { field: "governed" });
  }
  return ok(v);
}

function readAnswers(v: unknown): Result<Record<string, string>, ParallaxError<"INVALID_FIELD">> {
  if (v === undefined || v === null) return ok({});
  if (typeof v !== "object" || Array.isArray(v)) {
    return fail("INVALID_FIELD", "answers must be an object of slot -> answer", {
      field: "answers",
    });
  }
  const out: Record<string, string> = {};
  for (const [slot, value] of Object.entries(v as Record<string, unknown>)) {
    if (typeof value !== "string" || value.trim().length === 0) {
      // An empty answer is not an answer, and letting one through would
      // satisfy a blocking question with nothing.
      return fail("INVALID_FIELD", `the answer for ${slot} must be a non-empty string`, {
        field: "answers",
        slot,
      });
    }
    out[slot] = value;
  }
  return ok(out);
}

/**
 * Read the requested context, confined to the root this hub was pointed at.
 *
 * `root` in the request is workspace-RELATIVE and stays inside. An HTTP
 * endpoint that reads any absolute path an anonymous caller names is a
 * filesystem oracle, and the fact that the library allows it is not a reason to
 * expose it here: `filesystem` with an arbitrary root belongs at a terminal,
 * where the person typing it already has the permissions it would use.
 */
function readSource(
  body: Record<string, unknown>,
  contextRoot: string,
): Result<
  { source: ContextSource; root: string },
  ParallaxError<"MISSING_FIELD" | "INVALID_FIELD" | "PATH_ESCAPES_ROOT">
> {
  const kind = body.kind;
  if (kind === undefined || kind === null) {
    return fail("MISSING_FIELD", "kind is required", { field: "kind" });
  }
  if (kind !== "filesystem" && kind !== "agent-workspace" && kind !== "business-data") {
    return fail("INVALID_FIELD", "kind must be filesystem, agent-workspace or business-data", {
      field: "kind",
      allowed: ["filesystem", "agent-workspace", "business-data"],
    });
  }

  if (kind === "business-data") {
    const tables = body.tables;
    if (!Array.isArray(tables)) {
      return fail("MISSING_FIELD", "tables is required when kind is business-data", {
        field: "tables",
      });
    }
    const parsed: Array<{ name: string; columns: string[] }> = [];
    for (const t of tables) {
      if (typeof t !== "object" || t === null) {
        return fail("INVALID_FIELD", "each table must be an object", { field: "tables" });
      }
      const row = t as Record<string, unknown>;
      const name = row.name;
      const columns = row.columns;
      if (typeof name !== "string" || name.trim().length === 0) {
        return fail("INVALID_FIELD", "each table needs a non-empty name", { field: "tables" });
      }
      if (!Array.isArray(columns) || columns.some((c) => typeof c !== "string")) {
        return fail("INVALID_FIELD", `table ${name} needs an array of column names`, {
          field: "tables",
          table: name,
        });
      }
      parsed.push({ name, columns: columns as string[] });
    }
    return ok({ source: { kind: "business-data", tables: parsed }, root: contextRoot });
  }

  const rawRoot = body.root;
  if (rawRoot === undefined || rawRoot === null) {
    return ok({ source: sourceFor(kind, contextRoot), root: contextRoot });
  }
  if (typeof rawRoot !== "string") {
    return fail("INVALID_FIELD", "root must be a string relative to the hub's context", {
      field: "root",
    });
  }
  if (isAbsolute(rawRoot)) {
    return fail(
      "PATH_ESCAPES_ROOT",
      "root must be relative to the context this hub serves; an absolute path is refused",
      { field: "root", got: rawRoot },
    );
  }
  const target = resolve(contextRoot, rawRoot);
  if (target !== contextRoot && !target.startsWith(contextRoot + sep)) {
    return fail("PATH_ESCAPES_ROOT", "root resolves outside the context this hub serves", {
      field: "root",
      got: rawRoot,
    });
  }
  return ok({ source: sourceFor(kind, target), root: target });
}

/**
 * Built by branch rather than by spreading a union-typed `kind`, so the two
 * source shapes stay distinguishable to the compiler as well as to a reader.
 */
function sourceFor(kind: "filesystem" | "agent-workspace", root: string): ContextSource {
  return kind === "filesystem" ? { kind: "filesystem", root } : { kind: "agent-workspace", root };
}

/**
 * The proposal as the wire sees it.
 *
 * Identical to the library's value except that `source.root` is made relative
 * to the hub's context. An absolute server path is not the caller's business,
 * and it is not part of the proposal's identity either -- `proposalId` hashes
 * slug, initial state and actions, so relativising the root cannot change the
 * id the caller will send back to accept.
 */
function onTheWire(p: OntologyProposal, contextRoot: string): OntologyProposal {
  if (p.source.kind === "business-data") return p;
  const root = p.source.root;
  const rel = root === undefined ? "." : relative(contextRoot, root) || ".";
  return { ...p, source: { ...p.source, root: rel } };
}

function originOf(req: Request): string {
  const u = new URL(req.url);
  const forwardedProto = firstValue(req.headers.get("x-forwarded-proto"));
  const forwardedHost = firstValue(req.headers.get("x-forwarded-host"));
  const proto =
    forwardedProto === "http" || forwardedProto === "https"
      ? forwardedProto
      : u.protocol.replace(":", "");
  // A forwarded host is attacker-controllable in general; only a plain
  // host[:port] is accepted, so nothing can be smuggled into the receipt URL.
  const host =
    forwardedHost !== null && /^[a-z0-9.[\]-]+(:[0-9]+)?$/.test(forwardedHost)
      ? forwardedHost
      : u.host;
  return `${proto}://${host}`;
}

function firstValue(header: string | null): string | null {
  if (header === null) return null;
  const first = header.split(",")[0];
  return first === undefined ? null : first.trim().toLowerCase();
}
