#!/usr/bin/env bun
/**
 * keel classify — stage 2 dispatch: try the probe cache, hand the rest to the
 * agent.
 *
 *   bun scripts/classify.ts <nodes.json> [options]
 *
 * This file is DISPATCH PLUMBING. It contains no judgment and must never grow
 * any: the moment a script maps "check name → class" it has become the exact
 * ungrounded artifact Keel exists to detect. Probes judge (crystallized, and
 * reviewable as code); the agent judges everything else, over `raw`.
 *
 * ---------------------------------------------------------------------------
 * The sandbox contract (docs/plans/00-orchestration.md — orchestrator-owned)
 * ---------------------------------------------------------------------------
 * Probe code — INCLUDING LOADING, which executes the file — runs only inside
 * one sandboxed child process per run. A synchronous `while(true)` cannot be
 * preempted in JS, so an in-process "time guard" is fiction: the kill-timer
 * must hold a PROCESS HANDLE. This file is the parent that holds it.
 *
 *   parent (here)          spawns `bun scripts/probe-sandbox.ts <nodes.json>
 *                          --probe-dir <dir> ...`, holds a wall-clock
 *                          kill-timer over the whole batch, parses the child's
 *                          `ClassifyOutput` from stdout.
 *   child (probe-sandbox)  imports probe-loader, runs match/assess per node,
 *                          writes `ClassifyOutput` JSON to stdout.
 *
 * `classify.ts` NEVER imports `probe-loader.ts`. Importing it would execute
 * probe code in the process that is supposed to be able to kill it.
 *
 * ---------------------------------------------------------------------------
 * Invariants this file exists to hold
 * ---------------------------------------------------------------------------
 *  - The zero-probe path is complete. Empty library, missing child, dead
 *    child, hung child: every node lands in `pending`, a warning is recorded,
 *    and classify EXITS 0. Probes are a cache; the pure-agentic path is the
 *    product.
 *  - `pending` is COMPUTED as "every node without a valid verdict", never
 *    taken on trust from the child. So absence of a verdict is structurally
 *    `pending` — it cannot become a class, least of all `anchored`.
 *  - Verdicts arriving from the child are validated against the schema before
 *    they count. A verdict claiming `unknown` from a probe is a contract
 *    violation (`ProbeVerdict` excludes it at the type level, and a probe can
 *    still be plain JS and lie to the compiler): it is dropped, warned about,
 *    and its node falls back to `pending`. Fails closed, never open.
 *  - `ClassifyOutput.pending` is a flat `Node[]` on the wire. Batching for
 *    judgment (10–20 nodes per call) is a CALLER concern — `--batches` prints
 *    the grouping, the JSON wire shape stays flat.
 */

import { type ChildProcess, spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import type { ClassifyOutput, GroundingClass, Node, Verdict } from '../schemas/keel.ts';
import { coverageByKind } from '../schemas/keel.ts';
// A pure function over the filesystem — it loads no probe and executes nothing.
// Safe here despite the rule above: `probe-loader.ts` is reached from
// `probe-sandbox.ts` through a DYNAMIC import inside a function (see
// probe-sandbox.ts:382-390), so importing this module puts nothing that touches
// probe code into classify's module graph. The alternative — a second copy of
// the scrub — is worse: duplicated security logic drifts, and this is the one
// function whose whole job is to be applied consistently.
import { scrubInjectedEnv } from './probe-sandbox.ts';

const SKILL_ROOT = resolve(import.meta.dir, '..');

const DEFAULT_TIMEOUT_MS = 10_000;
/** 10–20 nodes per judgment call; one node per call does not survive a corpus night. */
const DEFAULT_BATCH_SIZE = 15;

const CLASSES: readonly GroundingClass[] = [
  'anchored',
  'self_referential',
  'unknown',
  'not_a_check',
];

// ---------------------------------------------------------------------------
// Probe directory resolution
// ---------------------------------------------------------------------------

/**
 * With no `--probe-dir`, the default set is [shipped, user]. With one or more
 * `--probe-dir` flags the set is EXACTLY those, in the given order — the flag
 * REPLACES rather than appends, because isolating a run from the user's home
 * probe library is impossible with an append-only flag, and that isolation is
 * what keeps one run's probes out of another run's economics.
 *
 * Returning `[]` means "pass no `--probe-dir` to the child, let it use its own
 * defaults". That is deliberate, and it is about WARNINGS, not about paths: the
 * child treats every dir it is handed as one the caller NAMED, and warns when a
 * named dir is unreadable. Forwarding `~/.config/keel/probes` — a dir most
 * users have never created — would turn that useful warning into boilerplate on
 * every fresh install. So the parent forwards a dir only when somebody actually
 * asked for it (`--probe-dir`, a caller-supplied `probeDirs`, or
 * `KEEL_PROBE_DIR`), and stays silent otherwise.
 */
function defaultProbeDirs(): string[] {
  const user = process.env.KEEL_PROBE_DIR?.trim();
  if (!user) return [];
  return [join(SKILL_ROOT, 'probes'), user];
}

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------

/**
 * What a CALLER may pass to `classify()`. Everything but the input path is
 * optional; `classify()` runs `resolveOptions` on whatever it is handed, so
 * every default is applied on BOTH entry points rather than only in `parseArgs`
 * — a default that exists only on the CLI path is not a default, it is a
 * coincidence. (It cost real damage once: an in-repo consumer built
 * `{probeDirs, nodesPath, json, sandbox}` by hand, `timeoutMs` came through
 * `undefined`, `setTimeout(NaN)` collapsed to 1ms, and every node in every repo
 * of a corpus run pended against a warning reading "exceeded its undefinedms
 * budget". Zero probe coverage, reported as a probe timeout.)
 */
export interface ClassifyOptions {
  nodesPath: string;
  /** Resolved against the CALLER's cwd. Empty/omitted → the child's defaults. */
  probeDirs?: string[];
  sandbox?: string;
  timeoutMs?: number;
  batchSize?: number;
  json?: boolean;
  batches?: boolean;
}

/** `ClassifyOptions` with every default applied. Internal to this file. */
interface Options {
  nodesPath: string;
  probeDirs: string[];
  sandbox: string;
  timeoutMs: number;
  batchSize: number;
  json: boolean;
  batches: boolean;
}

/**
 * Apply defaults, and — the part that matters — resolve probe dirs HERE, in the
 * parent, where the user's cwd is still known. The child runs with
 * `cwd: SKILL_ROOT`, so a relative `--probe-dir probes` handed through verbatim
 * silently means `<skill>/probes` rather than `./probes`: not a wrong verdict
 * (it fails closed to pending), but a dead probe cache and a flat
 * crystallization curve.
 */
export function resolveOptions(o: ClassifyOptions): Options {
  const dirs = o.probeDirs && o.probeDirs.length > 0 ? o.probeDirs : defaultProbeDirs();
  const timeoutMs =
    typeof o.timeoutMs === 'number' && Number.isFinite(o.timeoutMs) && o.timeoutMs > 0
      ? o.timeoutMs
      : DEFAULT_TIMEOUT_MS;
  const batchSize =
    typeof o.batchSize === 'number' && Number.isFinite(o.batchSize) && o.batchSize >= 1
      ? Math.min(50, Math.floor(o.batchSize))
      : DEFAULT_BATCH_SIZE;
  return {
    nodesPath: o.nodesPath,
    probeDirs: dirs.map((d) => resolve(d)),
    sandbox: o.sandbox ?? join(SKILL_ROOT, 'scripts', 'probe-sandbox.ts'),
    timeoutMs,
    batchSize,
    json: o.json === true,
    batches: o.batches === true,
  };
}

const USAGE = `usage: bun scripts/classify.ts <nodes.json> [options]

  --json                 emit ClassifyOutput as JSON on stdout
  --batches              emit pending grouped into judgment batches (Node[][])
  --batch-size <n>       nodes per judgment batch (default ${DEFAULT_BATCH_SIZE}, clamped 1..50)
  --probe-dir <dir>      REPLACES the default probe dirs; repeatable, order kept
  --timeout-ms <n>       wall-clock kill-timer on the sandbox child (default ${DEFAULT_TIMEOUT_MS})
  --sandbox <path>       path to the sandbox child (default <skill>/scripts/probe-sandbox.ts)`;

function parseArgs(argv: string[]): Options | { error: string } {
  let nodesPath = '';
  const probeDirs: string[] = [];
  // Left undefined so `resolveOptions` is the single place a default is applied.
  let sandbox: string | undefined;
  let timeoutMs: number | undefined;
  let batchSize: number | undefined;
  let json = false;
  let batches = false;

  const need = (i: number, flag: string): string | { error: string } => {
    const v = argv[i + 1];
    if (v === undefined || v.startsWith('--')) return { error: `${flag} requires a value` };
    return v;
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') json = true;
    else if (a === '--batches') batches = true;
    else if (a === '--probe-dir') {
      const v = need(i, a);
      if (typeof v !== 'string') return v;
      probeDirs.push(v);
      i++;
    } else if (a === '--sandbox') {
      const v = need(i, a);
      if (typeof v !== 'string') return v;
      sandbox = v;
      i++;
    } else if (a === '--timeout-ms') {
      const v = need(i, a);
      if (typeof v !== 'string') return v;
      const n = Number(v);
      if (!Number.isFinite(n) || n <= 0) return { error: `--timeout-ms must be a positive number` };
      timeoutMs = n;
      i++;
    } else if (a === '--batch-size') {
      const v = need(i, a);
      if (typeof v !== 'string') return v;
      const n = Number(v);
      if (!Number.isFinite(n) || n < 1) return { error: `--batch-size must be >= 1` };
      batchSize = Math.min(50, Math.floor(n));
      i++;
    } else if (a.startsWith('--')) {
      return { error: `unknown flag: ${a}` };
    } else if (nodesPath === '') {
      nodesPath = a;
    } else {
      return { error: `unexpected argument: ${a}` };
    }
  }

  if (nodesPath === '') return { error: 'missing <nodes.json>' };

  // One resolver for both entry points. The CLI has no defaults of its own.
  return resolveOptions({ nodesPath, probeDirs, sandbox, timeoutMs, batchSize, json, batches });
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

function readNodes(path: string): Node[] | { error: string } {
  let text: string;
  try {
    text = readFileSync(path, 'utf8');
  } catch (e) {
    return { error: `cannot read ${path}: ${e instanceof Error ? e.message : String(e)}` };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    return { error: `${path} is not valid JSON: ${e instanceof Error ? e.message : String(e)}` };
  }
  if (!Array.isArray(parsed)) return { error: `${path} must contain a Node[] array` };
  for (const n of parsed) {
    if (typeof n !== 'object' || n === null || typeof (n as Node).id !== 'string') {
      return { error: `${path} contains an entry without a string \`id\`` };
    }
  }
  return parsed as Node[];
}

// ---------------------------------------------------------------------------
// The sandbox child
// ---------------------------------------------------------------------------

interface SandboxResult {
  /** null whenever the child produced nothing usable — every node then pends. */
  output: ClassifyOutput | null;
  warnings: string[];
}

/**
 * Pull a JSON object out of the child's stdout. Strict first; then the widest
 * balanced-looking slice, so a stray log line does not cost the whole batch.
 */
function parseChildJson(stdout: string): unknown | undefined {
  const trimmed = stdout.trim();
  if (trimmed === '') return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    /* fall through */
  }
  const start = trimmed.indexOf('{');
  const end = trimmed.lastIndexOf('}');
  if (start === -1 || end <= start) return undefined;
  try {
    return JSON.parse(trimmed.slice(start, end + 1));
  } catch {
    return undefined;
  }
}

function tail(s: string, n = 400): string {
  const t = s.trim();
  return t.length <= n ? t : `…${t.slice(-n)}`;
}

interface ChildOutcome {
  stdout: string;
  stderr: string;
  code: number | null;
  /** the kill-timer fired */
  timedOut: boolean;
  /** the child exited but a descendant was still holding its stdout */
  orphaned: boolean;
  elapsedMs: number;
}

/** How long to wait, after the child exits, for its pipes to reach EOF. */
const PIPE_DRAIN_GRACE_MS = 400;

/**
 * Spawn the sandbox child in ITS OWN PROCESS GROUP and kill the group.
 *
 * Two things force this, and both were found by running it rather than
 * reading it:
 *
 *  1. The child may re-exec itself under a confinement wrapper
 *     (`sandbox-exec` on macOS). SIGKILL is uncatchable by design, so the
 *     child cannot forward it, and killing only the direct child leaves the
 *     confined GRANDCHILD spinning forever. A kill-timer that kills one
 *     process out of a tree is not a kill-timer.
 *  2. That grandchild inherits the stdout pipe. Waiting for stdout to reach
 *     EOF therefore waits on a process we just tried to kill — the parent
 *     hangs indefinitely with a fired timer, which is the exact failure the
 *     timer exists to prevent. So liveness is keyed to the child's EXIT plus
 *     a short drain grace, never to EOF.
 *
 * `detached: true` makes the child a group leader; `kill(-pid)` reaches every
 * descendant that did not deliberately leave the group.
 *
 * The cost of `detached: true` is that the child LEAVES the parent's process
 * group, so a Ctrl-C or a harness `SIGTERM` aimed at the parent no longer
 * reaches it. The child, by its own contract, has no timeout of any kind — a
 * hang is the parent's problem — so nothing else would ever stop it: killing
 * the parent mid-run used to leave a probe spinning at 100% of a core forever.
 * The parent therefore makes its own death fatal to the group (`exit`, plus
 * `SIGINT`/`SIGTERM`/`SIGHUP` re-raised after the group is gone), and detaches
 * those handlers again as soon as the run settles.
 */
function spawnSandbox(
  args: string[],
  timeoutMs: number,
): Promise<ChildOutcome | { spawnError: string }> {
  // `resolveOptions` guarantees a finite positive budget; this is the guard for
  // callers who bypass it. `setTimeout(NaN)` silently collapses to 1ms, which
  // reads downstream as a genuine probe timeout rather than a bad argument.
  const budgetMs =
    Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : DEFAULT_TIMEOUT_MS;
  return new Promise((settleOuter) => {
    let child: ChildProcess;
    try {
      child = spawn(process.execPath, args, {
        cwd: SKILL_ROOT,
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: true,
        env: process.env,
      });
    } catch (e) {
      settleOuter({ spawnError: e instanceof Error ? e.message : String(e) });
      return;
    }

    const startedAt = Date.now();
    let stdout = '';
    let stderr = '';
    let code: number | null = null;
    let timedOut = false;
    let closedNaturally = false;
    let settled = false;
    let graceTimer: ReturnType<typeof setTimeout> | undefined;

    const killGroup = () => {
      try {
        if (child.pid !== undefined) process.kill(-child.pid, 'SIGKILL');
      } catch {
        try {
          child.kill('SIGKILL');
        } catch {
          /* already gone */
        }
      }
    };

    // Parent death is fatal to the group. Registered before the timers so no
    // window exists in which the child is alive and unreachable.
    const PARENT_SIGNALS: NodeJS.Signals[] = ['SIGINT', 'SIGTERM', 'SIGHUP'];
    const detachParentHandlers = () => {
      process.off('exit', onParentExit);
      for (const s of PARENT_SIGNALS) process.off(s, onParentSignal);
    };
    function onParentExit() {
      killGroup();
    }
    function onParentSignal(sig: NodeJS.Signals) {
      killGroup();
      // Re-raise with our handler gone so the default action (terminate) — or
      // whatever the embedding harness installed — still happens. Swallowing
      // the signal here would make the parent itself unkillable.
      detachParentHandlers();
      process.kill(process.pid, sig);
    }
    process.on('exit', onParentExit);
    for (const s of PARENT_SIGNALS) process.on(s, onParentSignal);

    const killTimer = setTimeout(() => {
      timedOut = true;
      killGroup();
    }, budgetMs);

    // Backstop: even a child that never exits cannot hold the run. Nothing
    // downstream of here may depend on the child being cooperative.
    const hardTimer = setTimeout(() => {
      timedOut = true;
      killGroup();
      settle();
    }, budgetMs + PIPE_DRAIN_GRACE_MS * 4);

    const settle = () => {
      if (settled) return;
      settled = true;
      clearTimeout(killTimer);
      clearTimeout(hardTimer);
      if (graceTimer) clearTimeout(graceTimer);
      detachParentHandlers();
      // Anything still holding the pipes after the child is gone is an orphan.
      if (!closedNaturally) killGroup();
      settleOuter({
        stdout,
        stderr,
        code,
        timedOut,
        orphaned: !closedNaturally && !timedOut,
        elapsedMs: Date.now() - startedAt,
      });
    };

    child.stdout?.setEncoding('utf8');
    child.stdout?.on('data', (d: string) => {
      stdout += d;
    });
    child.stderr?.setEncoding('utf8');
    child.stderr?.on('data', (d: string) => {
      stderr += d;
    });
    child.stdout?.on('error', () => {});
    child.stderr?.on('error', () => {});

    child.on('error', (e) => {
      stderr += `\n${e instanceof Error ? e.message : String(e)}`;
      code = code ?? -1;
      settle();
    });
    child.on('exit', (c) => {
      code = c;
      graceTimer = setTimeout(settle, PIPE_DRAIN_GRACE_MS);
    });
    child.on('close', (c) => {
      // Both the process and its pipes are done — the clean path.
      code = code ?? c;
      closedNaturally = true;
      settle();
    });
  });
}

async function runSandbox(opts: Options, nodeCount: number): Promise<SandboxResult> {
  const warnings: string[] = [];

  if (nodeCount === 0) {
    // Nothing to judge. Spawning a child to say so would be theatre.
    return { output: { decided: [], pending: [], warnings: [] }, warnings };
  }

  if (!existsSync(opts.sandbox)) {
    warnings.push(
      `probe sandbox not found at ${opts.sandbox} — no probes were run; all ${nodeCount} nodes fall through to agent judgment`,
    );
    return { output: null, warnings };
  }

  const args = [opts.sandbox, resolve(opts.nodesPath)];
  for (const d of opts.probeDirs) args.push('--probe-dir', d);

  const run = await spawnSandbox(args, opts.timeoutMs);
  if ('spawnError' in run) {
    warnings.push(
      `probe sandbox failed to spawn (${run.spawnError}) — all ${nodeCount} nodes fall through to agent judgment`,
    );
    return { output: null, warnings };
  }
  const { stdout, stderr, code, timedOut, orphaned, elapsedMs } = run;

  if (orphaned) {
    warnings.push(
      `probe sandbox exited but left a descendant holding its stdout; the process group was killed — probe output may be truncated`,
    );
  }

  if (timedOut) {
    warnings.push(
      `probe sandbox exceeded its ${opts.timeoutMs}ms wall-clock budget and its process group was killed after ${elapsedMs}ms — all ${nodeCount} nodes fall through to agent judgment${stderr.trim() ? `; child stderr: ${tail(stderr)}` : ''}`,
    );
    return { output: null, warnings };
  }

  if (code !== 0) {
    warnings.push(
      `probe sandbox exited ${code} — all ${nodeCount} nodes fall through to agent judgment${stderr.trim() ? `; child stderr: ${tail(stderr)}` : ''}`,
    );
    return { output: null, warnings };
  }

  const parsed = parseChildJson(stdout);
  if (parsed === undefined || typeof parsed !== 'object' || parsed === null) {
    warnings.push(
      `probe sandbox produced no parseable ClassifyOutput on stdout — all ${nodeCount} nodes fall through to agent judgment`,
    );
    return { output: null, warnings };
  }

  const o = parsed as Partial<ClassifyOutput>;
  if (!Array.isArray(o.decided) || !Array.isArray(o.pending)) {
    warnings.push(
      `probe sandbox output is not a ClassifyOutput (missing \`decided\`/\`pending\` arrays) — all ${nodeCount} nodes fall through to agent judgment`,
    );
    return { output: null, warnings };
  }
  // Child stderr is surfaced only on the failure paths above. On success the
  // child has a `warnings` field for anything the operator needs to see, and
  // promoting its progress chatter to a warning would make "warnings" mean
  // "the child said something" rather than "something went wrong".

  return {
    output: {
      decided: o.decided as Verdict[],
      pending: o.pending as Node[],
      warnings: Array.isArray(o.warnings) ? (o.warnings as string[]).map(String) : [],
    },
    warnings,
  };
}

// ---------------------------------------------------------------------------
// Verdict validation — the parent does not trust the child
// ---------------------------------------------------------------------------

/**
 * Every field of a `Verdict` the parent is willing to carry out of the sandbox.
 * Anything else the child emitted is dropped on reconstruction — "validated"
 * has to mean "reconstructed from checked fields", not "checked and then passed
 * through", or an unchecked field rides along on the strength of the checked
 * ones. `audit` is deliberately absent: see `verdictProblems`.
 */
const VERDICT_FIELDS: readonly string[] = [
  'nodeId',
  'class',
  'writeBoundary',
  'evidence',
  'confidence',
  'decidedBy',
  'probeId',
];

/**
 * Reasons a verdict does not count. Every rejection sends its node back to
 * `pending`: the failure mode of this function is "ask the agent", never
 * "assume a class".
 */
function verdictProblems(v: unknown, knownIds: Set<string>): string[] {
  if (typeof v !== 'object' || v === null) return ['not an object'];
  const o = v as Record<string, unknown>;
  const problems: string[] = [];

  if (typeof o.nodeId !== 'string' || o.nodeId === '') problems.push('missing `nodeId`');
  else if (!knownIds.has(o.nodeId)) problems.push(`\`nodeId\` "${o.nodeId}" was not in the input`);

  if (typeof o.class !== 'string' || !CLASSES.includes(o.class as GroundingClass)) {
    problems.push(`\`class\` "${String(o.class)}" is not a GroundingClass`);
  } else if (o.class === 'unknown') {
    // Belt and braces over `ProbeVerdict`'s type-level exclusion: `unknown` is
    // a claim about the world and only the agent makes it. A probe that cannot
    // tell abstains. A probe asserting `unknown` is a broken probe, and a
    // broken probe must not get to spend the agent's most honest verdict.
    problems.push('a probe may never return `unknown` — it must abstain (`null`) instead');
  }

  if (o.decidedBy !== 'probe') {
    problems.push(`\`decidedBy\` must be "probe" in sandbox output, got "${String(o.decidedBy)}"`);
  }

  // A probe verdict that cannot be attributed cannot be audited or retired: the
  // ε-audit picks probe verdicts by `probeId`, and a bad probe is withdrawn by
  // id. `decidedBy: 'probe'` without one is an anonymous claim, and an anonymous
  // claim is exactly what this project refuses to count.
  if (typeof o.probeId !== 'string' || o.probeId.trim() === '') {
    problems.push('`decidedBy` is "probe" but `probeId` is missing — a probe verdict must name its probe');
  }

  // Only the ε-audit writes `audit`, and the audit agreement rate is Keel's
  // published counter-metric ON its own probe library. A sandbox-supplied
  // `audit: {agreed: true}` would let the measured thing grade its own agreement
  // rate without any audit having run.
  if ('audit' in o) {
    problems.push(
      '`audit` may not come from the sandbox — agreement is written by the ε-audit, never claimed by the probe being audited',
    );
  }

  const wb = o.writeBoundary as Record<string, unknown> | undefined;
  if (typeof wb !== 'object' || wb === null) problems.push('missing `writeBoundary`');
  else {
    if (typeof wb.producer !== 'string' || wb.producer.trim() === '') {
      problems.push('`writeBoundary.producer` is empty');
    }
    if (typeof wb.argument !== 'string' || wb.argument.trim() === '') {
      problems.push('`writeBoundary.argument` is empty');
    }
    if (typeof wb.actorCanWrite !== 'boolean' && wb.actorCanWrite !== null) {
      problems.push('`writeBoundary.actorCanWrite` must be boolean or null');
    }
  }

  if (!Array.isArray(o.evidence) || o.evidence.some((e) => typeof e !== 'string')) {
    problems.push('`evidence` must be string[]');
  }
  if (typeof o.confidence !== 'number' || !(o.confidence >= 0 && o.confidence <= 1)) {
    problems.push('`confidence` must be a number in 0..1');
  }

  return problems;
}

/**
 * Batching is a caller concern — the wire shape stays a flat `Node[]`. This is
 * exported so a caller assembling judgment payloads groups them the same way
 * `--batches` prints them.
 */
export function batchPending(pending: Node[], size = DEFAULT_BATCH_SIZE): Node[][] {
  const n = Math.max(1, Math.floor(size));
  const out: Node[][] = [];
  for (let i = 0; i < pending.length; i += n) out.push(pending.slice(i, i + n));
  return out;
}

// ---------------------------------------------------------------------------
// The dispatch itself
// ---------------------------------------------------------------------------

/**
 * Accepts a PARTIAL options object and applies every default itself, so the
 * in-process entry point behaves exactly like the CLI one (see
 * `ClassifyOptions`). `resolveOptions` is idempotent, so the CLI passing an
 * already-resolved object through costs nothing.
 */
export async function classify(opts: ClassifyOptions, nodes: Node[]): Promise<ClassifyOutput> {
  const o = resolveOptions(opts);
  const { output, warnings } = await runSandbox(o, nodes.length);
  const allWarnings = [...warnings, ...(output?.warnings ?? [])];

  const knownIds = new Set(nodes.map((n) => n.id));

  // Accounting is positional, diagnosis is by id. A `Verdict` addresses its node
  // by id alone, so two input nodes sharing an id are indistinguishable to any
  // verdict — but they must still both be ACCOUNTED for. Claiming an INDEX (not
  // an id) is what makes `decided + pending === nodes` hold unconditionally;
  // filtering pending by an id set used to delete both twins from pending while
  // deciding only one, so a node vanished from the run entirely and the
  // denominator silently shrank. That is the no-silent-caps rule applied to our
  // own plumbing.
  const firstIndexById = new Map<string, number>();
  const duplicatedIds: string[] = [];
  for (let i = 0; i < nodes.length; i++) {
    const id = nodes[i].id;
    if (firstIndexById.has(id)) {
      if (!duplicatedIds.includes(id)) duplicatedIds.push(id);
    } else {
      firstIndexById.set(id, i);
    }
  }
  if (duplicatedIds.length > 0) {
    const extra = nodes.length - firstIndexById.size;
    allWarnings.push(
      `input has ${extra} node${extra === 1 ? '' : 's'} sharing an already-used id (${duplicatedIds.slice(0, 8).join(', ')}${duplicatedIds.length > 8 ? `, +${duplicatedIds.length - 8} more` : ''}) — a Verdict addresses its node by id alone, so only the first node with each id can ever be decided and the rest can only land in pending; every node is still accounted for, but the gatherer's id derivation is losing information`,
    );
  }

  const claimed: boolean[] = new Array(nodes.length).fill(false);
  const decided: Verdict[] = [];
  const decidedIds = new Set<string>();

  for (const raw of output?.decided ?? []) {
    const problems = verdictProblems(raw, knownIds);
    // The child's `decided` is typed `Verdict[]` only because JSON.parse said
    // so. It is untrusted input; read it as a bag of unknown fields.
    const seen = ((raw ?? {}) as unknown) as Record<string, unknown>;
    const nodeIdLabel = typeof seen.nodeId === 'string' ? seen.nodeId : '<no nodeId>';
    if (problems.length > 0) {
      allWarnings.push(
        `verdict rejected for "${nodeIdLabel}"${typeof seen.probeId === 'string' && seen.probeId !== '' ? ` from probe "${seen.probeId}"` : ''}: ${problems.join('; ')} — node falls through to agent judgment`,
      );
      continue;
    }
    const nodeId = seen.nodeId as string;
    if (decidedIds.has(nodeId)) {
      allWarnings.push(
        `duplicate verdict for "${nodeId}" ignored (first one kept) — probe library may have two probes claiming one node`,
      );
      continue;
    }

    // Reconstruct from validated fields only. Passing the child's object through
    // verbatim is how an unvalidated field survives on the credibility of the
    // validated ones — the whole point of this section is that the parent does
    // not trust the child, and "does not trust" has to include "does not copy".
    const wb = seen.writeBoundary as Record<string, unknown>;
    const v: Verdict = {
      nodeId,
      class: seen.class as GroundingClass,
      writeBoundary: {
        producer: wb.producer as string,
        actorCanWrite: wb.actorCanWrite as boolean | null,
        argument: wb.argument as string,
      },
      evidence: (seen.evidence as string[]).slice(),
      confidence: seen.confidence as number,
      decidedBy: 'probe',
      probeId: seen.probeId as string,
    };

    const unexpected = Object.keys(seen).filter((k) => !VERDICT_FIELDS.includes(k));
    if (unexpected.length > 0) {
      // Not fatal — the verdict itself checks out — but never silent: an extra
      // field means the child and the frozen schema have drifted apart, and the
      // operator should learn that from a warning rather than from a missing
      // column in a report.
      allWarnings.push(
        `verdict for "${nodeId}" carried field(s) outside the Verdict schema (${unexpected.join(', ')}); the parent forwards only validated fields, so they were dropped`,
      );
    }

    decidedIds.add(nodeId);
    claimed[firstIndexById.get(nodeId) as number] = true;
    decided.push(v);
  }

  // Pending is a set difference, not a field we trust. This is the invariant:
  // a node without a valid verdict cannot land anywhere but `pending`.
  const pending = nodes.filter((_, i) => !claimed[i]);

  if (output && output.pending.length !== pending.length) {
    allWarnings.push(
      `probe sandbox reported ${output.pending.length} pending, parent computed ${pending.length} — parent's set difference wins`,
    );
  }

  // Totality is structural above; this says so out loud if it ever stops being.
  // A node that is neither decided nor pending is an invisible node, and an
  // invisible node is a silently smaller denominator.
  if (decided.length + pending.length !== nodes.length) {
    allWarnings.push(
      `INTERNAL: ${nodes.length} nodes in, ${decided.length} decided + ${pending.length} pending out — ${nodes.length - decided.length - pending.length} node(s) unaccounted for; treat this run's ratio as invalid and report the bug`,
    );
  }

  return { decided, pending, warnings: allWarnings };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function human(out: ClassifyOutput, nodes: Node[], opts: Options): string {
  const lines: string[] = [];
  if (nodes.length === 0) {
    // Zero gathered nodes is "nothing gathered", never a clean bill of health.
    lines.push('classify: nothing gathered — 0 candidate verification edges in the input.');
    lines.push('There is nothing to classify, and that is not a passing result.');
    if (out.warnings.length > 0) for (const w of out.warnings) lines.push(`    ! ${w}`);
    return lines.join('\n');
  }
  lines.push(`classify: ${nodes.length} nodes`);
  lines.push(`  decided by probe   ${String(out.decided.length).padStart(4)}`);
  lines.push(`  pending (agent)    ${String(out.pending.length).padStart(4)}`);

  if (out.decided.length > 0) {
    const byClass = out.decided.reduce<Record<string, number>>((a, v) => {
      a[v.class] = (a[v.class] ?? 0) + 1;
      return a;
    }, {});
    lines.push('');
    lines.push('  probe verdicts by class');
    for (const c of CLASSES) {
      if (byClass[c]) lines.push(`    ${String(byClass[c]).padStart(4)}  ${c}`);
    }
  }

  if (out.pending.length > 0) {
    const cov = coverageByKind(out.pending);
    lines.push('');
    lines.push('  pending by kind');
    for (const [k, v] of Object.entries(cov).sort((a, b) => b[1] - a[1])) {
      lines.push(`    ${String(v).padStart(4)}  ${k}`);
    }
    const batches = batchPending(out.pending, opts.batchSize);
    lines.push('');
    lines.push(
      `  ${batches.length} judgment batch${batches.length === 1 ? '' : 'es'} of up to ${opts.batchSize} nodes`,
    );
  }

  if (out.warnings.length > 0) {
    lines.push('');
    lines.push(`  warnings (${out.warnings.length})`);
    for (const w of out.warnings) lines.push(`    ! ${w}`);
  }

  lines.push('');
  lines.push(
    out.pending.length > 0
      ? 'pending nodes are NOT classified. Judge them over `raw` — nothing here defaults to a class.'
      : 'every node was decided from the probe cache. Audit a sample of these (SKILL.md §4).',
  );
  return lines.join('\n');
}

if (import.meta.main) {
  // Before anything reads configuration: a repository under measurement does not
  // get to configure its own measurement. `defaultProbeDirs()` below reads
  // KEEL_PROBE_DIR, and the child is spawned with `env: process.env` — so a
  // dotenv-injected value would otherwise select which executable code loads.
  const injectedWarning = scrubInjectedEnv();
  if (injectedWarning) console.error(`classify: ${injectedWarning}`);

  const parsed = parseArgs(process.argv.slice(2));
  if ('error' in parsed) {
    console.error(`classify: ${parsed.error}\n\n${USAGE}`);
    process.exit(1);
  }
  const opts = parsed;

  const nodes = readNodes(opts.nodesPath);
  if (!Array.isArray(nodes)) {
    console.error(`classify: ${nodes.error}`);
    process.exit(1);
  }

  const out = await classify(opts, nodes);
  // Leads the list: it explains a run that ignored part of its own configuration,
  // which changes how everything below it should be read. On stderr AND in the
  // artifact — a warning that only reaches the terminal does not survive being
  // saved, emailed, or published.
  if (injectedWarning) out.warnings.unshift(injectedWarning);

  if (opts.batches) {
    console.log(JSON.stringify(batchPending(out.pending, opts.batchSize), null, 2));
  } else if (opts.json) {
    console.log(JSON.stringify(out, null, 2));
  } else {
    console.log(human(out, nodes, opts));
  }

  // A dead, hung or hostile probe library is a degraded run, not a failed one.
  // Exit 0 — the pending path is the product.
  process.exit(0);
}
