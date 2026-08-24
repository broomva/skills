#!/usr/bin/env bun
/**
 * `keel audit` — the ε-audit. Keel's counter-metric, and the only number here
 * that is about Keel rather than about the target.
 *
 * A probe is cheap, deterministic and silent. That is the point of crystallizing
 * one, and it is also the failure mode: a `match` that over-generalizes will
 * mis-classify the same shape forever, and nothing about a probe run announces
 * that it went wrong. Cost per node falls, the report keeps printing, and the
 * verdicts quietly stop meaning anything. SKILL.md §4 answers that by sampling a
 * fraction of probe-decided nodes and re-deciding them agentically **with the
 * cached verdict hidden** — a measurement of the measurer, by something the
 * measurer cannot write to.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS IS A STEPPER AND NOT A FUNCTION
 * ---------------------------------------------------------------------------
 * The re-decision is a classification, and classification is agentic by
 * construction. A script that re-decided a node would be a second rule table
 * sitting in judgment on the first — the exact artifact Keel exists to detect,
 * and worse here than anywhere else, because it would be the thing certifying
 * that our judgment layer is sound. So this file is plumbing with the agent in
 * the loop, the same shape `corpus.ts` uses:
 *
 *   bun scripts/audit.ts <report.json> [--sample 0.1] [--seed N] [--all]
 *       draws a deterministic sample of the probe-decided verdicts, writes a
 *       BLIND payload to <report>.audit-pending.json, prints it, and STOPS.
 *
 *   ... the agent re-decides the printed nodes and writes the re-decisions ...
 *
 *   bun scripts/audit.ts record <pending.json> <redecisions.json> [--report r]
 *       merges them into `Verdict.audit` and prints the agreement rate with its
 *       denominator and its population.
 *
 * ---------------------------------------------------------------------------
 * FOUR PROPERTIES THAT ARE LOAD-BEARING
 * ---------------------------------------------------------------------------
 * 1. BLINDNESS IS STRUCTURAL, NOT POLITE. The payload is built from the `Node`
 *    and never from the `Verdict`: the cached class, the `probeId`, the
 *    confidence and the write-boundary argument have no path into either the
 *    printed text or `pending.json`. `record` re-opens the report to recover
 *    the cached class, which is why the pending file carries a report PATH and
 *    not a cached verdict. An auditor who can see the answer measures nothing,
 *    and "we asked the agent not to peek" is a self-referential control.
 *
 * 2. `agreed` IS DERIVED, NEVER ACCEPTED. The re-decision states a class; this
 *    file computes `agreed = agentClass === cachedClass`. A judging agent that
 *    tried to assert `agreed: true` would be setting the status field on the
 *    one number that exists to catch status fields being self-set. (`render.ts`
 *    independently refuses any audit block where those two disagree — see
 *    `auditIsWellFormed` — so a hand-edited report cannot slip one through the
 *    page either.)
 *
 * 3. THE RATE NEVER TRAVELS ALONE. Every printed agreement carries its
 *    denominator, its population and its coverage, and a run with zero
 *    comparisons prints no rate at all. `1.00` over three nodes and `1.00` over
 *    three hundred are different claims, and the first one is the one that gets
 *    quoted. A report with no probe-decided verdicts is a first-class outcome —
 *    "nothing to audit" — and never a ratio over an empty denominator.
 *
 * 4. NOTHING IS RETIRED HERE, AND NO CLASS IS CHANGED. On disagreement this
 *    prints the node, both classes, the agent's argument and the probe's id,
 *    and stops. Narrowing a `match` or retiring a probe is a human decision
 *    over a diff; a script that auto-retired on one disagreement would let a
 *    single sample delete a reviewed artifact, and one that auto-applied the
 *    agent's class would silently move the target's grounding ratio from inside
 *    our own quality loop. The audit annotates verdicts. It never re-writes
 *    them.
 *
 * A disagreement therefore exits 0. It is a measurement, not a build failure;
 * an audit that turns the pipeline red is an audit people stop running.
 */

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import type { GroundingClass, Node, Report, Verdict } from '../schemas/keel.ts';

const CLASSES: readonly GroundingClass[] = [
  'anchored',
  'self_referential',
  'unknown',
  'not_a_check',
];

/** printed raw is capped so one 4 kB config cannot bury the batch — disclosed inline. */
const RAW_PRINT_LIMIT = 2000;

const DEFAULT_FRACTION = 0.1;
const DEFAULT_SEED = 1;

// ---------------------------------------------------------------------------
// Shapes owned by this script (the frozen schema owns Report / Verdict / Node)
// ---------------------------------------------------------------------------

/**
 * What the judging agent is allowed to see about a node.
 *
 * This is deliberately a copy of `Node` and not a reference to the verdict that
 * decided it. Building it field by field — rather than by spreading something
 * that happens to be in scope — is what makes blindness a property of the code
 * instead of a promise in a comment: there is no expression anywhere in
 * `buildPending` that reads a `Verdict`, so there is nothing to leak.
 */
export interface AuditPayloadNode {
  id: string;
  kind: Node['kind'];
  name: string;
  source: string;
  raw: string;
  hints?: Record<string, string>;
}

export interface AuditPending {
  /** where the cached verdicts live. A path, not a class — `record` re-opens it. */
  reportPath: string;
  target: string;
  revision: string;
  sampledAt: string;
  seed: number;
  /** the fraction asked for, or `null` when --all was used. */
  fraction: number | null;
  all: boolean;
  /** probe-decided verdicts eligible for the draw. */
  population: number;
  /** how many of that population already carry an audit block from an earlier run. */
  alreadyAudited: number;
  nodes: AuditPayloadNode[];
  warnings: string[];
}

/** One re-decision, as the agent writes it. Only `class` is stored; see below. */
export interface Redecision {
  nodeId: string;
  class: GroundingClass;
  /**
   * The causal path. `Verdict.audit` is frozen at `{agentClass, agreed, at}`, so
   * this is printed on disagreement rather than stored — which is where it is
   * actually read anyway: "the probe says not_a_check, the agent says anchored"
   * is unusable without the sentence that says why.
   */
  argument: string;
}

export interface Disagreement {
  nodeId: string;
  probeId: string | null;
  cached: GroundingClass;
  agent: GroundingClass;
  argument: string;
}

export interface AuditResult {
  target: string;
  revision: string;
  /** probe-decided verdicts in the report. */
  population: number;
  /** nodes this audit drew. */
  sampled: number;
  /** sampled nodes that came back re-decided. */
  compared: number;
  agreed: number;
  disagreed: number;
  /** sampled nodes with no re-decision. Reported, never counted as agreement. */
  pending: number;
  /** null whenever `compared` is 0 — an empty denominator gets no rate. */
  rate: number | null;
  disagreements: Disagreement[];
  warnings: string[];
}

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, 'utf8')) as T;
}

/**
 * Write via a sibling temp file and rename.
 *
 * `record` writes the report back over itself by default, and a crash halfway
 * through `writeFileSync` on the artifact that holds every verdict of a run
 * costs the whole run. Rename is atomic within a directory, so the report is
 * either the old one or the new one.
 */
function writeJson(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp-${process.pid}`;
  writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`);
  renameSync(tmp, path);
}

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function isClass(v: unknown): v is GroundingClass {
  return typeof v === 'string' && (CLASSES as readonly string[]).includes(v);
}

/**
 * A parsed JSON document, if it is the kind of thing this script can read.
 *
 * `JSON.parse` is happy to return `null`, `7` or `[]`, and every one of those
 * reaches `report.nodes` as a TypeError from inside a helper — a stack trace
 * where every other bad-input path in this file prints a sentence naming the
 * file and what was expected. A crash is not an error message.
 */
function asObject<T>(v: unknown): T | null {
  return v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as T) : null;
}

/** What the file actually held, for the message that says it was the wrong shape. */
function jsonShape(v: unknown): string {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'an array';
  return `a ${typeof v}`;
}

/**
 * The value that follows an option.
 *
 * A dangling `-o` used to yield `''`, which is not nullish, so it survived every
 * `??` downstream and surfaced as an ENOENT from inside `renameSync` — after the
 * temp file had already been written, leaving a stray `*.tmp-<pid>` in the user's
 * directory. An absent value and an empty one are the same mistake.
 */
function optValue(argv: string[], i: number): string | null {
  const v = argv[i];
  return typeof v === 'string' && v.trim() !== '' ? v : null;
}

/**
 * Shell-quote a path for the copy-pasteable `THEN:` line.
 *
 * The whole point of that line is that it can be pasted, and a report under
 * `~/My Projects/` turned it into two broken arguments. Quoted only when it has
 * to be, so the common case stays readable.
 */
export function shellQuote(s: string): string {
  return s !== '' && /^[A-Za-z0-9_@%+=:,./-]+$/.test(s)
    ? s
    : `'${s.replace(/'/g, `'\\''`)}'`;
}

// ---------------------------------------------------------------------------
// The population.
//
// Probe-decided verdicts only, and that is not an oversight. The number SKILL.md
// §4 names is the PROBE LIBRARY's agreement rate: it exists because probe
// judgment is cached, cheap and unwatched. Re-deciding an agent-decided node
// measures judgment repeatability instead — a real number, and a different one,
// which `corpus.ts --repeat` already produces and labels separately. Pooling
// them would let a growing probe library borrow the agent's stability, or the
// reverse, and neither figure would mean what its name says.
// ---------------------------------------------------------------------------

export function probeDecided(report: Report): Verdict[] {
  return (report.verdicts ?? []).filter((v) => v.decidedBy === 'probe');
}

// ---------------------------------------------------------------------------
// Sampling — deterministic, seeded, and re-derivable by a reviewer.
//
// Rank by sha256(`${seed}:${nodeId}`) and take the lowest k digests. Two
// properties matter more than elegance here:
//
//   REPRODUCIBLE. Same report, same seed, same draw — in a later process, on
//   another machine, by a reviewer who wants to know why THOSE nodes. A
//   Math.random() sample makes the audit unreviewable: nobody can tell a lucky
//   draw from a chosen one.
//
//   ORDER-INDEPENDENT. The chosen SET is a function of the node ids alone, so
//   re-ordering verdicts in the report — which a re-run of the gatherer can do
//   for free — does not change which nodes get audited. A shuffle-sensitive
//   sample would look reproducible in a test and drift in the field.
//
// k = ceil(fraction * n), so a non-empty population with a positive fraction
// never rounds down to auditing nothing. The alternative is a run that reports
// "0 compared" on a healthy report and looks like it did something.
// ---------------------------------------------------------------------------

export function selectionKey(seed: number, nodeId: string): string {
  return createHash('sha256').update(`${seed}:${nodeId}`).digest('hex');
}

export function sampleIds(
  ids: string[],
  opts: { fraction: number; seed: number; all: boolean },
): string[] {
  if (opts.all) return [...ids];
  if (ids.length === 0) return [];
  const k = Math.min(ids.length, Math.ceil(ids.length * opts.fraction));
  const keyed = ids.map((id) => ({ id, key: selectionKey(opts.seed, id) }));
  keyed.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.id < b.id ? -1 : 1));
  const chosen = new Set(keyed.slice(0, k).map((e) => e.id));
  // Restored to report order for printing. The SET is what the seed fixes; the
  // ORDER is only about a human reading the payload top to bottom.
  return ids.filter((id) => chosen.has(id));
}

// ---------------------------------------------------------------------------
// The blind payload
// ---------------------------------------------------------------------------

export function buildPending(
  report: Report,
  reportPath: string,
  opts: { fraction: number; seed: number; all: boolean },
): AuditPending {
  const warnings: string[] = [];
  const nodeById = new Map((report.nodes ?? []).map((n) => [n.id, n]));
  const candidates = probeDecided(report);

  // A verdict whose node is missing cannot be audited: there is nothing to show
  // the agent except the verdict itself, and showing the verdict is the one
  // thing this stage may not do. Dropped before the draw, and said out loud —
  // a silently shrunken population is a shrunken denominator.
  const eligible: Verdict[] = [];
  for (const v of candidates) {
    if (nodeById.has(v.nodeId)) eligible.push(v);
    else
      warnings.push(
        `${v.nodeId}: probe-decided but no node in the report — excluded from the audit population (re-run the measurement; a verdict without its node cannot be re-judged blind)`,
      );
  }

  const alreadyAudited = eligible.filter((v) => v.audit !== undefined).length;
  const selected = sampleIds(
    eligible.map((v) => v.nodeId),
    opts,
  );

  const nodes: AuditPayloadNode[] = [];
  for (const id of selected) {
    const n = nodeById.get(id);
    if (!n) continue; // unreachable: `eligible` was filtered on this map.
    // Field by field, from the NODE. Nothing in this expression can reach a
    // verdict — that is the blindness guarantee, stated as code.
    nodes.push({
      id: n.id,
      kind: n.kind,
      name: n.name,
      source: n.source,
      raw: n.raw,
      ...(n.hints ? { hints: n.hints } : {}),
    });
  }

  return {
    reportPath: resolve(reportPath),
    target: report.target,
    revision: report.revision,
    sampledAt: new Date().toISOString(),
    seed: opts.seed,
    fraction: opts.all ? null : opts.fraction,
    all: opts.all,
    population: eligible.length,
    alreadyAudited,
    nodes,
    warnings,
  };
}

export function redecisionsPathFor(reportPath: string): string {
  return join(dirname(reportPath), `${baseName(reportPath)}.audit-redecisions.json`);
}

export function pendingPathFor(reportPath: string): string {
  return join(dirname(reportPath), `${baseName(reportPath)}.audit-pending.json`);
}

function baseName(path: string): string {
  const b = path.split('/').pop() ?? path;
  return b.endsWith('.json') ? b.slice(0, -5) : b;
}

/**
 * The printed payload.
 *
 * The four class names appear here exactly once, in the shared instruction
 * block, as the vocabulary every node is judged in. That is not a leak: it is
 * identical for every node and says nothing about any of them. What must never
 * appear is a class attached to a NODE — which is why the node section below
 * renders only fields of `AuditPayloadNode`, and why the test slices this text
 * between the two markers and asserts no class name survives in between.
 */
export function renderPayload(
  pending: AuditPending,
  pendingPath: string,
  redecisionsPath: string,
): string {
  const L: string[] = [];
  const rev = pending.revision ? pending.revision.slice(0, 12) : '(no revision)';

  L.push('');
  L.push('='.repeat(78));
  L.push(`ε-AUDIT PAYLOAD · ${pending.target} @ ${rev}`);
  L.push('='.repeat(78));
  L.push(
    `population: ${pending.population} probe-decided verdicts · drawing ${pending.nodes.length}` +
      (pending.all ? ' (--all)' : ` (--sample ${pending.fraction}, --seed ${pending.seed})`),
  );
  if (!pending.all) {
    L.push(
      'draw rule: rank by sha256("<seed>:<nodeId>"), lowest digests first — re-derivable.',
    );
  }
  if (pending.alreadyAudited > 0) {
    L.push(
      `${pending.alreadyAudited} of the population already carry an audit block; a redrawn one is re-compared and overwritten.`,
    );
  }
  for (const w of pending.warnings) L.push(`warning: ${w}`);
  L.push('');
  L.push('You are re-deciding these nodes BLIND. The cached class, the probe that');
  L.push('produced it, its confidence and its write-boundary argument are absent from');
  L.push(`this text and from ${pendingPath} on purpose.`);
  L.push('Do not open the report to look them up: an auditor who can see the answer');
  L.push('measures nothing, and this number is the only evidence the probe library has');
  L.push('that it still means what it meant when each probe was reviewed.');
  L.push('');
  L.push('The only question: what actually produces this signal, and can the actor');
  L.push('being verified write to it?  anchored = cannot · self_referential = can ·');
  L.push('unknown = fork point not established (fails closed, counts against the ratio) ·');
  L.push('not_a_check = asserts nothing about correctness (excluded from the ratio, so');
  L.push('it is the shoppable class — if you reach for it because a node is HARD, the');
  L.push('honest answer is unknown).');
  L.push('');
  L.push('-'.repeat(78));
  L.push(`NODES TO RE-DECIDE · ${pending.nodes.length}`);
  L.push('-'.repeat(78));

  for (const n of pending.nodes) {
    L.push('');
    L.push(`id:     ${n.id}`);
    L.push(`kind:   ${n.kind}`);
    L.push(`name:   ${n.name}`);
    L.push(`source: ${n.source}`);
    if (n.hints) L.push(`hints:  ${JSON.stringify(n.hints)}`);
    L.push('raw:');
    const raw = n.raw ?? '';
    const shown = raw.length > RAW_PRINT_LIMIT ? raw.slice(0, RAW_PRINT_LIMIT) : raw;
    for (const line of shown.split('\n')) L.push(`  | ${line}`);
    if (raw.length > RAW_PRINT_LIMIT) {
      L.push(`  | [TRUNCATED for printing — ${raw.length - RAW_PRINT_LIMIT} more chars.`);
      L.push(`  |  Full literal text is in ${pendingPath}]`);
    }
  }

  L.push('');
  L.push('-'.repeat(78));
  L.push(`WRITE RE-DECISIONS TO: ${redecisionsPath}`);
  L.push('-'.repeat(78));
  L.push('A JSON array. One entry per node above:');
  L.push('  { "nodeId": "<exact id>",');
  L.push('    "class": "anchored" | "self_referential" | "unknown" | "not_a_check",');
  L.push('    "argument": "the causal path — what produces the signal, and who can write to it" }');
  L.push('');
  L.push('Do NOT write an "agreed" field: agreement is computed by comparing your class');
  L.push('to the cached one, and a claim of agreement made by the thing being audited');
  L.push('would be the self-set status field this whole number exists to catch.');
  L.push('A node you leave out stays PENDING and is reported as such — it is never');
  L.push('counted as agreement.');
  L.push('');
  L.push(
    `THEN: bun scripts/audit.ts record ${shellQuote(pendingPath)} ${shellQuote(redecisionsPath)}`,
  );
  L.push('');
  return L.join('\n');
}

// ---------------------------------------------------------------------------
// `record` — merge, compare, report
// ---------------------------------------------------------------------------

export function readRedecisions(
  raw: unknown,
  allowedIds: Set<string>,
): { decisions: Redecision[]; problems: string[] } {
  const list = Array.isArray(raw) ? raw : (raw as { redecisions?: unknown })?.redecisions;
  if (!Array.isArray(list)) {
    return {
      decisions: [],
      problems: [
        'file must be a JSON array of { nodeId, class, argument } (or { "redecisions": [...] })',
      ],
    };
  }

  const problems: string[] = [];
  const decisions: Redecision[] = [];
  const seen = new Set<string>();

  list.forEach((item, i) => {
    const o = (item ?? {}) as Record<string, unknown>;
    const where = `redecision[${i}]${typeof o.nodeId === 'string' ? ` (${o.nodeId})` : ''}`;
    if (typeof o.nodeId !== 'string') return problems.push(`${where}: missing nodeId`);
    if (!allowedIds.has(o.nodeId)) {
      return problems.push(
        `${where}: not in this audit's sample — the comparison is only defined for the nodes that were drawn (re-run the sample stage if you want this node in)`,
      );
    }
    if (seen.has(o.nodeId)) return problems.push(`${where}: duplicate re-decision for this node`);
    if (!isClass(o.class)) {
      return problems.push(`${where}: class must be one of ${CLASSES.join(' | ')}`);
    }
    // A full Verdict pasted in is tolerated: `writeBoundary.argument` is the
    // same sentence under a different key, and rejecting it would punish the
    // agent for being more thorough than asked.
    const wb = o.writeBoundary as { argument?: unknown } | undefined;
    const argument =
      typeof o.argument === 'string' && o.argument.trim()
        ? o.argument.trim()
        : typeof wb?.argument === 'string' && wb.argument.trim()
          ? wb.argument.trim()
          : '';
    if (!argument) {
      return problems.push(
        `${where}: argument is required — a re-decision with no causal path is not a judgment, and on disagreement it is the only thing a reviewer has to decide the probe's fate with`,
      );
    }
    seen.add(o.nodeId);
    decisions.push({ nodeId: o.nodeId, class: o.class, argument });
  });

  return { decisions, problems };
}

/**
 * Merge the re-decisions into `Verdict.audit`, in place, and count.
 *
 * The verdict's own `class` is not touched here and must not be: an audit
 * records that two judgments differ, it does not settle which one is right. The
 * moment this file promoted the agent's class into the verdict, the ε-audit
 * would be moving the target's grounding ratio — a quality loop editing the
 * measurement it is checking, which is the shape of the failure Keel names.
 */
export function applyAudit(
  report: Report,
  pending: AuditPending,
  decisions: Redecision[],
  at: string,
): AuditResult {
  const byId = new Map((report.verdicts ?? []).map((v) => [v.nodeId, v]));
  const sampledIds = pending.nodes.map((n) => n.id);
  const warnings = [...pending.warnings];
  const disagreements: Disagreement[] = [];
  let agreed = 0;
  let compared = 0;

  for (const d of decisions) {
    const v = byId.get(d.nodeId);
    if (!v) {
      warnings.push(
        `${d.nodeId}: re-decided, but the report no longer carries a verdict for it — not compared`,
      );
      continue;
    }
    // Derived, never accepted from the file. See property 2 in the header.
    const isAgreed = d.class === v.class;
    v.audit = { agentClass: d.class, agreed: isAgreed, at };
    compared += 1;
    if (isAgreed) agreed += 1;
    else {
      disagreements.push({
        nodeId: d.nodeId,
        probeId: v.probeId ?? null,
        cached: v.class,
        agent: d.class,
        argument: d.argument,
      });
    }
  }

  return {
    target: report.target,
    revision: report.revision,
    population: pending.population,
    sampled: sampledIds.length,
    compared,
    agreed,
    disagreed: compared - agreed,
    pending: sampledIds.length - compared,
    rate: compared === 0 ? null : agreed / compared,
    disagreements,
    warnings,
  };
}

/**
 * The number, with everything that makes it readable.
 *
 * `rate === null` prints no rate. There is exactly one way to report an
 * agreement over zero comparisons and it is in words.
 */
export function renderResult(r: AuditResult): string {
  const L: string[] = [];
  const rev = r.revision ? r.revision.slice(0, 12) : '(no revision)';
  L.push('');
  L.push(`ε-audit · ${r.target} @ ${rev}`);
  if (r.rate === null) {
    L.push('  no re-decisions were recorded — nothing was compared, so there is no rate.');
  } else {
    const pct =
      r.population > 0 ? ` = ${Math.round((r.compared / r.population) * 100)}% of it` : '';
    L.push(
      `  agreement ${r.rate.toFixed(2)} over ${r.compared} compared node${r.compared === 1 ? '' : 's'}` +
        ` (${r.agreed} agreed · ${r.disagreed} disagreed)`,
    );
    L.push(`  population: ${r.population} probe-decided verdicts · ${r.compared} audited${pct}`);
  }
  L.push(
    `  sampled ${r.sampled} · re-judged ${r.compared} · still pending re-judgment: ${r.pending}`,
  );
  for (const w of r.warnings) L.push(`  warning: ${w}`);

  if (r.disagreements.length) {
    L.push('');
    L.push('  disagreements — the probe is NAMED, not retired. Narrowing a `match` or');
    L.push('  retiring a probe is a human decision over a diff; one sample is evidence,');
    L.push('  not a verdict on the probe. No class was changed by this audit.');
    for (const d of r.disagreements) {
      L.push('');
      L.push(`    node:  ${d.nodeId}`);
      L.push(`    probe: ${d.probeId ?? '(none recorded)'}`);
      L.push(`    cached ${d.cached}  →  agent ${d.agent}`);
      L.push(`    agent's argument: ${d.argument}`);
    }
  }
  L.push('');
  return L.join('\n');
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const USAGE = `keel audit — the ε-audit: re-decide probe-classified nodes blind

  bun scripts/audit.ts <report.json> [options]
      draw a deterministic sample of the probe-decided verdicts, write a BLIND
      payload (no cached class, no probeId, no confidence, no argument), print
      it, and stop.

  bun scripts/audit.ts record <pending.json> <redecisions.json> [options]
      merge the re-decisions into Verdict.audit and print the agreement rate
      with its denominator and its population.

options
  --sample <f>   fraction of the probe-decided population to draw (default ${DEFAULT_FRACTION})
  --seed <n>     seed for the draw (default ${DEFAULT_SEED}); the same seed redraws the same nodes
  --all          draw every probe-decided verdict (small reports)
  -o, --out <p>  where to write the pending payload (default <report>.audit-pending.json),
                 or, for \`record\`, where to write the updated report (default: in place)
  --report <p>   the report to merge into (default: the path recorded in pending.json)
  --json         print the result as JSON as well
`;

interface Args {
  cmd: 'sample' | 'record';
  positional: string[];
  fraction: number;
  seed: number;
  all: boolean;
  out: string | null;
  report: string | null;
  json: boolean;
}

export function parseArgs(argv: string[]): Args | { error: string } {
  const out: Args = {
    cmd: 'sample',
    positional: [],
    fraction: DEFAULT_FRACTION,
    seed: DEFAULT_SEED,
    all: false,
    out: null,
    report: null,
    json: false,
  };
  const rest: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '--sample': {
        const v = optValue(argv, ++i);
        if (v === null) return { error: '--sample needs a fraction, e.g. --sample 0.1' };
        out.fraction = Number(v);
        break;
      }
      case '--seed': {
        const v = optValue(argv, ++i);
        if (v === null) return { error: '--seed needs a number, e.g. --seed 1' };
        out.seed = Number(v);
        break;
      }
      case '--all':
        out.all = true;
        break;
      case '-o':
      case '--out': {
        const v = optValue(argv, ++i);
        if (v === null) return { error: `${a} needs a path to write to` };
        out.out = v;
        break;
      }
      case '--report': {
        const v = optValue(argv, ++i);
        if (v === null) return { error: '--report needs a path to the report to merge into' };
        out.report = v;
        break;
      }
      case '--json':
        out.json = true;
        break;
      case '-h':
      case '--help':
        return { error: '' };
      default:
        if (a?.startsWith('-')) return { error: `unknown option ${a}` };
        rest.push(a as string);
    }
  }
  if (rest[0] === 'record') {
    out.cmd = 'record';
    out.positional = rest.slice(1);
  } else {
    out.positional = rest;
  }
  if (!Number.isFinite(out.seed)) return { error: '--seed must be a number' };
  if (!out.all && (!Number.isFinite(out.fraction) || out.fraction <= 0 || out.fraction > 1)) {
    return {
      error:
        '--sample must be a fraction in (0,1] — 0 draws nothing, and an audit nobody ran is not an audit; use --all for everything',
    };
  }
  return out;
}

function cmdSample(a: Args): number {
  const reportPath = a.positional[0];
  if (!reportPath) {
    console.error('audit: needs a report.json — see --help');
    return 1;
  }
  if (!existsSync(reportPath)) {
    console.error(`audit: no report at ${reportPath}`);
    return 1;
  }
  let parsedReport: unknown;
  try {
    parsedReport = readJson<unknown>(reportPath);
  } catch (e) {
    console.error(`audit: ${reportPath} is not valid JSON: ${errText(e)}`);
    return 1;
  }
  const report = asObject<Report>(parsedReport);
  if (!report) {
    console.error(
      `audit: ${reportPath} is valid JSON but not a keel report — expected an object with "nodes" and "verdicts", got ${jsonShape(parsedReport)}`,
    );
    return 1;
  }

  const pending = buildPending(report, reportPath, {
    fraction: a.fraction,
    seed: a.seed,
    all: a.all,
  });

  // The first-class empty outcome. A report whose every verdict was decided by
  // the agent has no probe library to audit, and saying "agreement 0.00" or
  // "1.00" about it would both be inventions. Exit 0: nothing is wrong.
  if (pending.population === 0) {
    for (const w of pending.warnings) console.error(`audit: warning: ${w}`);
    // Three different worlds produce an empty population, and only one of them
    // is "every verdict was agent-decided". Printing that sentence over a report
    // with no verdicts at all states a fact the data does not contain — on the
    // one command whose subject is claims that outrun their evidence.
    const verdicts = report.verdicts ?? [];
    const probes = probeDecided(report);
    const reason =
      verdicts.length === 0
        ? 'this report carries no verdicts at all, so nothing in it could have\n  been probe-decided'
        : probes.length === 0
          ? 'every verdict in this report was agent-decided, so there is\n  no cached probe judgment to re-decide'
          : `all ${probes.length} probe-decided verdict(s) were excluded because their nodes are\n  missing from the report (see the warnings above)`;
    const rev = (report.revision ?? '').slice(0, 12) || '(no revision)';
    console.log(
      `\nε-audit · ${report.target ?? '(no target recorded)'} @ ${rev}\n` +
        `  nothing to audit — ${reason}. No rate is reported (a rate over an\n` +
        '  empty denominator is not a small number, it is not a number).\n',
    );
    if (a.json) {
      console.log(JSON.stringify({ population: 0, sampled: 0, compared: 0, rate: null }, null, 2));
    }
    return 0;
  }

  const pendingPath = a.out ?? pendingPathFor(resolve(reportPath));
  const redecisionsPath = redecisionsPathFor(resolve(reportPath));
  writeJson(pendingPath, pending);
  console.log(renderPayload(pending, pendingPath, redecisionsPath));
  console.log(`pending payload written to ${pendingPath}`);
  return 0;
}

function cmdRecord(a: Args): number {
  const pendingPath = a.positional[0];
  const redecisionsPath = a.positional[1];
  if (!pendingPath || !redecisionsPath) {
    console.error('audit: record needs <pending.json> <redecisions.json> — see --help');
    return 1;
  }
  if (!existsSync(pendingPath)) {
    console.error(`audit: no pending payload at ${pendingPath} — run the sample stage first`);
    return 1;
  }
  if (!existsSync(redecisionsPath)) {
    console.error(
      `audit: no re-decisions at ${redecisionsPath} — judge the printed payload and write them there first`,
    );
    return 1;
  }

  let parsedPending: unknown;
  let rawDecisions: unknown;
  try {
    parsedPending = readJson<unknown>(pendingPath);
  } catch (e) {
    console.error(`audit: ${pendingPath} is not valid JSON: ${errText(e)}`);
    return 1;
  }
  const pending = asObject<AuditPending>(parsedPending);
  if (!pending || !Array.isArray(pending.nodes)) {
    console.error(
      `audit: ${pendingPath} is not an audit payload — expected the object written by the sample stage, with a "nodes" array (got ${pending ? 'an object with no "nodes" array' : jsonShape(parsedPending)})`,
    );
    return 1;
  }
  try {
    rawDecisions = readJson<unknown>(redecisionsPath);
  } catch (e) {
    console.error(`audit: ${redecisionsPath} is not valid JSON: ${errText(e)}`);
    return 1;
  }

  const reportPath = a.report ?? pending.reportPath;
  if (!existsSync(reportPath)) {
    console.error(
      `audit: no report at ${reportPath} — pass --report if it moved since the sample stage`,
    );
    return 1;
  }
  let parsedReport: unknown;
  try {
    parsedReport = readJson<unknown>(reportPath);
  } catch (e) {
    console.error(`audit: ${reportPath} is not valid JSON: ${errText(e)}`);
    return 1;
  }
  const report = asObject<Report>(parsedReport);
  if (!report) {
    console.error(
      `audit: ${reportPath} is valid JSON but not a keel report — expected an object with "nodes" and "verdicts", got ${jsonShape(parsedReport)}`,
    );
    return 1;
  }

  // A report that moved under the audit invalidates the comparison: the cached
  // class being compared against would be from a different revision than the
  // one the agent judged. Refuse rather than silently compare across it.
  if (pending.revision && report.revision && pending.revision !== report.revision) {
    console.error(
      `audit: ${reportPath} is at revision ${report.revision.slice(0, 12)} but the sample was drawn at ${pending.revision.slice(0, 12)} — re-run the sample stage; comparing a re-decision against a verdict from another revision measures nothing`,
    );
    return 1;
  }

  const allowed = new Set(pending.nodes.map((n) => n.id));
  const { decisions, problems } = readRedecisions(rawDecisions, allowed);
  if (problems.length) {
    console.error('audit: re-decisions rejected — nothing was recorded.');
    for (const p of problems) console.error(`  ${p}`);
    return 1;
  }

  const result = applyAudit(report, pending, decisions, new Date().toISOString());
  writeJson(a.out ?? reportPath, report);
  console.log(renderResult(result));
  console.log(`report written to ${a.out ?? reportPath}`);
  if (a.json) console.log(JSON.stringify(result, null, 2));
  return 0;
}

export function run(argv: string[]): number {
  const parsed = parseArgs(argv);
  if ('error' in parsed) {
    if (parsed.error) console.error(`audit: ${parsed.error}`);
    console.log(USAGE);
    return parsed.error ? 1 : 0;
  }
  return parsed.cmd === 'record' ? cmdRecord(parsed) : cmdSample(parsed);
}

if (import.meta.main) {
  if (process.argv.length <= 2) {
    console.log(USAGE);
    process.exit(0);
  }
  process.exit(run(process.argv.slice(2)));
}
