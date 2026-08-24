#!/usr/bin/env bun
/**
 * keel probe-sandbox — the sandbox CHILD of the classify stage.
 *
 *   bun scripts/probe-sandbox.ts <nodes.json> [--probe-dir <dir>]...
 *
 * Probe code — INCLUDING LOADING, which executes the file — runs only here.
 * The parent (`classify.ts`) never imports a probe; it spawns this process once
 * per run and holds a wall-clock kill-timer on it. A synchronous `while(true)`
 * cannot be preempted in-process in JS, so an in-process "time guard" would be
 * fiction: the kill-timer must hold a process handle, and that handle lives in
 * the parent. One spawn per RUN, not per probe — a process per probe would wreck
 * the economics the crystallization curve measures.
 *
 * Output: `ClassifyOutput` JSON on STDOUT and nothing else. Diagnostics go to
 * stderr, or the parent cannot parse us.
 *
 * ---------------------------------------------------------------------------
 * SANDBOX POSTURE — claim only what is enforced.
 *
 * This is a product about honest verification, so the guarantee is stated as
 * mechanism, not as adjective. On macOS this process re-executes ITSELF under
 * `sandbox-exec` with a deny-default profile (see `buildProfile`) before it
 * touches a probe. Measured on darwin 25.5 / bun 1.x, that profile ENFORCES:
 *
 *   - no network of any kind          (`(deny network*)`; verified: fetch fails)
 *   - no filesystem writes, anywhere  (verified: writeFileSync -> EPERM)
 *   - no process exec except `bun`    (verified: spawning curl -> EPERM)
 *   - no credential reads             (~/.ssh, ~/.aws, ~/.gnupg, ~/.config/gh,
 *                                      ~/.netrc denied; verified: EPERM)
 *   - a stripped environment          (only PATH/HOME/TMPDIR/LANG/KEEL_* are
 *                                      forwarded — no API keys are inherited)
 *
 * It does NOT enforce, and we do not claim:
 *
 *   - read confinement. Beyond the credential denials above, a probe can read
 *     any file the invoking user can read. Narrowing `file-read*` to the target
 *     plus the probe dirs made bun abort at startup (SIGABRT), so it is not
 *     shipped rather than shipped-and-overclaimed.
 *   - exfiltration through the return value. Writes and network are closed, but
 *     a probe's verdict text lands in report.json; a hostile probe could smuggle
 *     bytes it read into that text.
 *   - CPU/memory bounds, and no timeout of any kind. A hang is the PARENT's
 *     problem, by design.
 *
 * FALLBACK — what "degrade" actually means, mechanically:
 *
 * Probe code NEVER runs in this process. Every path re-executes a child, and
 * every child gets `sanitizedEnv()`, so the stripped environment holds even
 * when the seatbelt does not. The paths are:
 *
 *   1. macOS + sandbox-exec  -> confined child, stripped env.       (full)
 *   2. no sandbox-exec (non-macOS, or KEEL_SANDBOX=0)
 *      OR the confined child exits without producing any stdout
 *      (a rejected/broken SBPL profile looks exactly like this)
 *                            -> UNCONFINED child, stripped env.     (degraded)
 *   3. the degraded child also produces nothing
 *                            -> a valid ClassifyOutput with every node pending.
 *
 * A child KILLED BY A SIGNAL is explicitly not case 2. It exits with zero bytes
 * of stdout, which looks identical to a kernel-rejected profile, but the cause is
 * the kill-timer firing on a hanging probe — and degrading there would re-run
 * that same probe with the seatbelt off. So a signal means: forward it, escalate
 * to SIGKILL, exit 143, and decide nothing. A hang is never a route out of the
 * sandbox, and this process dies of the signal rather than merely relaying it.
 *
 * In case 2 network access and filesystem writes are NOT confined: a probe can
 * do anything the invoking user can do, apart from reading the credential paths
 * denied above (which are denied by the profile, so they are not denied here
 * either — only the ENVIRONMENT is stripped). Case 2 and case 3 are reported on
 * stderr and in `warnings`, never silently. Firecracker is the year-two answer
 * for probes run against customer infrastructure; it is not this.
 *
 * The one caveat on "probe code never runs in this process", stated rather than
 * papered over: the parent/child branch is selected by `KEEL_SANDBOXED`, so an
 * actor who already controls this process's ENVIRONMENT can set `KEEL_SANDBOXED=1`
 * on the top-level invocation and make it take the child branch directly —
 * unconfined, with whatever env it was handed. That is not a hole this file can
 * close (an actor who can set your environment can also set your `PATH`), and
 * `sanitizedEnv` deliberately refuses to FORWARD `KEEL_SANDBOXED`/`KEEL_DEGRADED`
 * so the flag cannot be smuggled in from outside a legitimate run and a confined
 * child can never be handed a fabricated "not enforced" warning.
 * ---------------------------------------------------------------------------
 */

import { existsSync, mkdtempSync, statSync, writeFileSync, readFileSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type {
  ClassifyOutput,
  GroundingClass,
  Node,
  Probe,
  Verdict,
} from '../schemas/keel.ts';

const SELF = fileURLToPath(import.meta.url);
const HERE = dirname(SELF);

/**
 * How a REJECTED seatbelt profile identifies itself, as opposed to probe code
 * that merely exited early.
 *
 * Measured on this machine: feeding `sandbox-exec` a malformed profile gives
 * exit 65 and `sandbox-exec: syntax error: ...` on stderr, while a clean child
 * exit gives 0 and says nothing. Only the first is evidence about the sandbox;
 * the second is under the probe's control, and treating it as evidence would
 * let hostile probe code request its own unconfined re-run.
 */
const SANDBOX_REJECTED = /^\s*sandbox[-_]exec:/im;

/** Classes a probe is allowed to assert. `unknown` is deliberately absent. */
const PROBE_CLASSES: ReadonlySet<string> = new Set<GroundingClass>([
  'anchored',
  'self_referential',
  'not_a_check',
]);

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

// ---------------------------------------------------------------------------
// Sandbox. Exported because mint-probe.ts validates freshly-minted probe code
// the same way: by executing it, and executing it only in here.
// ---------------------------------------------------------------------------

/**
 * A deny-default seatbelt profile. Kept short on purpose — a sandbox nobody can
 * read is a sandbox nobody can check.
 */
export function buildProfile(): string {
  const home = homedir();
  const bun = process.execPath;
  return [
    '(version 1)',
    '(deny default)',
    '(deny network*)',
    '(allow process-fork)',
    `(allow process-exec (literal ${JSON.stringify(bun)}))`,
    '(allow signal (target self))',
    '(allow sysctl-read mach-lookup ipc-posix-shm)',
    '(allow file-read*)',
    `(deny file-read* (subpath ${JSON.stringify(join(home, '.ssh'))})`,
    `               (subpath ${JSON.stringify(join(home, '.aws'))})`,
    `               (subpath ${JSON.stringify(join(home, '.gnupg'))})`,
    `               (subpath ${JSON.stringify(join(home, '.config/gh'))})`,
    `               (literal ${JSON.stringify(join(home, '.netrc'))}))`,
    '',
  ].join('\n');
}

/**
 * Variables this file sets on a child to describe the child's OWN situation.
 * They are never forwarded from the ambient environment, or an outside actor
 * could hand a fully-confined run a fabricated "sandbox not enforced" warning
 * (or suppress a real one).
 */
const INTERNAL_KEEL_VARS: ReadonlySet<string> = new Set([
  'KEEL_SANDBOXED',
  'KEEL_DEGRADED',
  'KEEL_NOTICE',
]);

/**
 * Dotenv files Bun loads automatically from the process cwd, in its load order.
 * We only ever read the KEY NAMES out of these — never the values.
 */
const DOTENV_FILES = ['.env', '.env.development', '.env.test', '.env.production', '.env.local'];

/**
 * ---------------------------------------------------------------------------
 * The measured repository does not get to configure its own measurement.
 * ---------------------------------------------------------------------------
 *
 * Bun auto-loads `.env` from the process cwd, before any line of this file
 * runs. During a normal run the cwd IS THE TARGET REPOSITORY — that is what
 * SKILL.md and README tell users to do ("point your agent at a target"). So a
 * repository under measurement can define any environment variable it likes in
 * the Keel process, and two of ours are security-critical: `KEEL_SANDBOX`
 * selects whether the seatbelt is applied at all, and `KEEL_PROBE_DIR` selects
 * WHICH DIRECTORY OF EXECUTABLE CODE gets loaded. Loading a probe runs it.
 *
 * A hostile target carrying nothing but
 *
 *     .env                 KEEL_SANDBOX=0
 *                          KEEL_PROBE_DIR=${PWD}/.keel-probes
 *     .keel-probes/x.v1.ts <anything at all>
 *
 * therefore gets arbitrary code execution as the invoking user, on macOS too —
 * the one platform where confinement would otherwise apply. `${PWD}` expansion
 * makes it self-contained: no absolute paths, no user opt-in, no flags.
 *
 * The defect is not either variable. It is that a value which arrived from a
 * file in the current directory is treated as an operator's configuration
 * choice. It is not one: it is input from wherever the process happens to be
 * standing. So we read the dotenv files ourselves, and any `KEEL_*` name they
 * define is removed from the environment before anything reads it.
 *
 * This keeps every documented behaviour intact. `KEEL_PROBE_DIR` is a real
 * feature (SKILL.md:124, the fan-out contract in docs/plans/00-orchestration.md)
 * and an operator exporting it in their own shell is unaffected — the shell is
 * outside the target's write boundary and a dotenv in the target is not. Which
 * is, exactly, the predicate this whole project is built on.
 */
export function dotenvInjectedKeelVars(cwd: string = process.cwd()): string[] {
  const found = new Set<string>();
  for (const file of DOTENV_FILES) {
    let text: string;
    try {
      text = readFileSync(join(cwd, file), 'utf8');
    } catch {
      continue; // absent or unreadable — nothing to distrust
    }
    for (const line of text.split('\n')) {
      // KEY=..., optionally `export KEY=...`. Values are never parsed: we are
      // deciding what to DELETE, so the name is the whole question.
      const m = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=/.exec(line);
      const key = m?.[1];
      if (key?.startsWith('KEEL_')) found.add(key);
    }
  }
  return [...found].sort();
}

/**
 * Delete dotenv-injected `KEEL_*` variables from this process's environment.
 * Returns a warning line when anything was removed, else null.
 *
 * MUST run before argument parsing and before any config read. `--no-sandbox`
 * sets `KEEL_SANDBOX` AFTER this point, so an operator's explicit flag still
 * works while an injected value is already gone.
 */
export function scrubInjectedEnv(cwd: string = process.cwd()): string | null {
  const injected = dotenvInjectedKeelVars(cwd);
  if (injected.length === 0) return null;
  for (const k of injected) delete process.env[k];
  return (
    `ignored ${injected.length} KEEL_* variable(s) defined by a dotenv file in the working ` +
    `directory (${injected.join(', ')}): the target under measurement does not configure its ` +
    `own measurement. Export them in your shell if you meant them.`
  );
}

/** Only these travel into the sandbox. Nothing that looks like a credential. */
export function sanitizedEnv(extra: Record<string, string> = {}): Record<string, string> {
  const keep = ['PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER'];
  const env: Record<string, string> = {};
  for (const k of keep) {
    const v = process.env[k];
    if (v) env[k] = v;
  }
  for (const [k, v] of Object.entries(process.env)) {
    if (k.startsWith('KEEL_') && v && !INTERNAL_KEEL_VARS.has(k)) env[k] = v;
  }
  return { ...env, ...extra };
}

/**
 * Wrap a bun invocation in the seatbelt. Returns the argv to spawn plus whether
 * confinement is actually in force, so callers can REPORT the difference rather
 * than assume it.
 */
export function sandboxCommand(bunArgs: string[]): {
  cmd: string[];
  sandboxed: boolean;
  reason?: string;
} {
  if (process.env.KEEL_SANDBOX === '0') {
    return { cmd: [process.execPath, ...bunArgs], sandboxed: false, reason: 'KEEL_SANDBOX=0' };
  }
  if (process.platform !== 'darwin' || !existsSync('/usr/bin/sandbox-exec')) {
    return {
      cmd: [process.execPath, ...bunArgs],
      sandboxed: false,
      reason: `no sandbox-exec on ${process.platform}`,
    };
  }
  try {
    const dir = mkdtempSync(join(tmpdir(), 'keel-sb-'));
    const profile = join(dir, 'probe.sb');
    writeFileSync(profile, buildProfile(), 'utf8');
    return {
      cmd: ['/usr/bin/sandbox-exec', '-f', profile, process.execPath, ...bunArgs],
      sandboxed: true,
    };
  } catch (e) {
    return { cmd: [process.execPath, ...bunArgs], sandboxed: false, reason: msg(e) };
  }
}

/**
 * Re-exec THIS script as a child — confined or not, always with a stripped env,
 * because probe code must never run in a process that inherited credentials.
 *
 * stdout is CAPTURED rather than inherited so the caller can tell "the child
 * ran and said nothing" from "the child ran and produced a ClassifyOutput".
 * That distinction is the whole fallback trigger: a seatbelt profile the kernel
 * rejects exits non-zero with zero bytes of stdout, and inheriting stdout would
 * make that indistinguishable from success at the byte level.
 *
 * Signals: the grandparent's kill-timer sends SIGTERM to us, and we do TWO
 * things with it, both necessary and neither sufficient alone.
 *
 *  1. Forward it to the child, then escalate to SIGKILL, so probe code cannot
 *     outlive the run as an orphan.
 *  2. DIE OF IT OURSELVES. Registering a SIGTERM listener in Node/Bun suppresses
 *     the default disposition, so a handler that only forwarded would make this
 *     process unkillable by the very timer that owns its lifetime — the "a hang
 *     is the PARENT's problem" contract would be a comment rather than a
 *     mechanism. Measured: with forward-only handlers, `timeout 12 bun
 *     scripts/probe-sandbox.ts … --probe-dir <a probe that spins at load>` was
 *     still alive at 2 minutes.
 *
 * `signalled` is reported back for a reason that is a security property, not a
 * tidiness one: a child killed by a signal also exits with zero bytes of stdout,
 * which is the exact shape of a kernel-rejected seatbelt profile. Without the
 * distinction the caller degrades — and re-runs the same hanging, hostile probe
 * code UNCONFINED. A hang must never be a route out of the sandbox.
 */
async function runChild(
  cmd: string[],
  env: Record<string, string>,
): Promise<{ code: number; stdout: string; stderr: string; signalled: boolean }> {
  // stderr is PIPED rather than inherited so the caller can read sandbox-exec's
  // own rejection diagnostic — the one signal a confined probe cannot forge, and
  // therefore the only safe basis for deciding whether to degrade. It is teed
  // straight back out to the parent's stderr, so diagnostics still reach the
  // operator exactly as before.
  const child = Bun.spawn([...cmd], {
    env,
    stdin: 'inherit',
    stdout: 'pipe',
    stderr: 'pipe',
  });
  let signalled = false;
  const term = (sig: number) => {
    try {
      child.kill(15);
    } catch {
      /* already gone */
    }
    if (sig === 0) return; // process 'exit' cleanup, not a signal we received
    signalled = true;
    // A synchronous `while(true)` in the child may ignore SIGTERM entirely.
    // Escalate, then exit with the conventional 128+signal status.
    const t = setTimeout(() => {
      try {
        child.kill(9);
      } catch {
        /* already gone */
      }
      process.exit(128 + sig);
    }, 500);
    (t as { unref?: () => void }).unref?.();
  };
  const onTerm = () => term(15);
  const onInt = () => term(2);
  const onExit = () => term(0);
  process.on('SIGTERM', onTerm);
  process.on('SIGINT', onInt);
  process.on('exit', onExit);
  try {
    const [stdout, stderr, code] = await Promise.all([
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
      child.exited,
    ]);
    if (stderr.length > 0) process.stderr.write(stderr);
    return { code, stdout, stderr, signalled: signalled || child.signalCode != null };
  } finally {
    // Two children can run in one process (confined, then degraded); leaving the
    // first child's handlers installed would have the second run kill a corpse.
    process.off('SIGTERM', onTerm);
    process.off('SIGINT', onInt);
    process.off('exit', onExit);
  }
}

// ---------------------------------------------------------------------------
// Probe loading. `loadProbes` lives in probe-loader.ts (W1·A). It is imported
// dynamically: this file must run — and typecheck — before that file exists,
// and the specifier is computed so the compiler does not bind to it.
// ---------------------------------------------------------------------------

type LoadProbes = (dirs: string[]) => Promise<{ probes: Probe[]; warnings: string[] }>;

async function resolveLoadProbes(): Promise<{ load: LoadProbes | null; warnings: string[] }> {
  // The path is fixed and computed, never taken from the environment. An
  // env-overridable loader would let anyone who can set a variable substitute
  // the module that loads and executes probe code.
  const spec = join(HERE, 'probe-loader.ts');
  if (!existsSync(spec)) {
    return {
      load: null,
      warnings: [`probe loader not found at ${spec}: 0 probes loaded, every node is pending`],
    };
  }
  try {
    const mod = (await import(spec)) as Record<string, unknown>;
    const fn = mod.loadProbes;
    if (typeof fn !== 'function') {
      return { load: null, warnings: [`${spec} does not export loadProbes(dirs)`] };
    }
    return { load: fn as LoadProbes, warnings: [] };
  } catch (e) {
    return { load: null, warnings: [`probe loader failed to import: ${msg(e)}`] };
  }
}

/**
 * Orchestrator ruling: `--probe-dir` REPLACES the default set (fan-out
 * isolation requires the ability to exclude the user's home probes entirely).
 * With no flag: shipped probes first, then the runtime-minted dir.
 * A missing dir is "no probes", never an error.
 */
export function resolveProbeDirs(flagDirs: string[]): string[] {
  const dirs = flagDirs.length
    ? flagDirs
    : [
        resolve(HERE, '..', 'probes'),
        process.env.KEEL_PROBE_DIR ?? join(homedir(), '.config', 'keel', 'probes'),
      ];
  const seen = new Set<string>();
  return dirs.map((d) => resolve(d)).filter((d) => (seen.has(d) ? false : (seen.add(d), true)));
}

/**
 * Dirs the CALLER named on purpose: `--probe-dir`, or `KEEL_PROBE_DIR` when no
 * flag was given. The two implicit defaults (the shipped dir and
 * `~/.config/keel/probes`) are not in here — they are usually absent and
 * warning about them would be noise.
 */
function namedProbeDirs(flagDirs: string[]): string[] {
  if (flagDirs.length) return flagDirs;
  const env = process.env.KEEL_PROBE_DIR?.trim();
  return env ? [env] : [];
}

/**
 * A probe dir the caller NAMED and that is not readable is a different fact
 * from "the library is empty", and the crystallization curve reads the two
 * very differently: one says probes cost nothing yet, the other says a typo
 * silently disabled the library. `loadProbes` treats both as "no probes" by
 * design (a broken dir must not fail a run), so the distinction has to be
 * drawn here, where we still know the dir was explicit.
 */
export function missingNamedDirWarnings(flagDirs: string[]): string[] {
  const out: string[] = [];
  for (const d of namedProbeDirs(flagDirs)) {
    const p = resolve(d);
    try {
      if (!statSync(p).isDirectory()) {
        out.push(`probe dir ${p} was named explicitly but is not a directory — 0 probes loaded from it`);
      }
    } catch (e) {
      out.push(
        `probe dir ${p} was named explicitly but could not be read (${msg(e)}) — 0 probes loaded from it, so an empty probe library here means NOT FOUND, not empty`,
      );
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Verdict validation — schema only. NOTHING here classifies anything.
// ---------------------------------------------------------------------------

/**
 * Belt-and-braces at ASSESS-CALL TIME. `ProbeVerdict` excludes `unknown` at the
 * type level, but a probe can be plain JS and lie to the compiler, and this is
 * the only point in the system where a probe's return value exists. A probe
 * that asserts `unknown` is a DEFECT, not a verdict: `unknown` is a claim about
 * the world and only the agent makes it. Returns a defect string, or null.
 */
function probeVerdictDefect(v: unknown): string | null {
  if (typeof v !== 'object' || v === null) return `assess() returned ${typeof v}, expected an object or null`;
  const r = v as Record<string, unknown>;
  if (r.class === 'unknown') {
    return "assess() returned class 'unknown' — a probe may never assert unknown; abstain (return null) instead";
  }
  if (typeof r.class !== 'string' || !PROBE_CLASSES.has(r.class)) {
    return `assess() returned class ${JSON.stringify(r.class)}, expected one of ${[...PROBE_CLASSES].join(', ')}`;
  }
  const wb = r.writeBoundary as Record<string, unknown> | undefined;
  if (typeof wb !== 'object' || wb === null) return 'assess() returned no writeBoundary';
  if (typeof wb.producer !== 'string' || !wb.producer.trim()) {
    return 'assess() returned a writeBoundary with no producer';
  }
  if (typeof wb.argument !== 'string' || !wb.argument.trim()) {
    return 'assess() returned a writeBoundary with no argument';
  }
  if (!(typeof wb.actorCanWrite === 'boolean' || wb.actorCanWrite === null)) {
    return 'assess() returned writeBoundary.actorCanWrite that is neither boolean nor null';
  }
  if (!Array.isArray(r.evidence) || r.evidence.some((e) => typeof e !== 'string')) {
    return 'assess() returned evidence that is not string[]';
  }
  if (typeof r.confidence !== 'number' || !(r.confidence >= 0 && r.confidence <= 1)) {
    return 'assess() returned confidence outside 0..1';
  }
  return null;
}

// ---------------------------------------------------------------------------
// The run.
// ---------------------------------------------------------------------------

function readNodes(path: string): Node[] {
  const parsed: unknown = JSON.parse(readFileSync(path, 'utf8'));
  const arr = Array.isArray(parsed)
    ? parsed
    : (parsed as { nodes?: unknown })?.nodes;
  if (!Array.isArray(arr)) throw new Error(`${path} is not a Node[] (nor { nodes: Node[] })`);
  return arr as Node[];
}

export async function runSandbox(
  nodesPath: string,
  flagDirs: string[],
  seedWarnings: string[] = [],
): Promise<ClassifyOutput> {
  const warnings = [...seedWarnings];
  const nodes = readNodes(nodesPath);
  const dirs = resolveProbeDirs(flagDirs);
  warnings.push(...missingNamedDirWarnings(flagDirs));

  const { load, warnings: loaderWarnings } = await resolveLoadProbes();
  warnings.push(...loaderWarnings);

  let probes: Probe[] = [];
  if (load) {
    try {
      const res = await load(dirs);
      probes = Array.isArray(res?.probes) ? res.probes : [];
      warnings.push(...(res?.warnings ?? []));
    } catch (e) {
      // Loading EXECUTES probe files. One bad file must not cost the run.
      warnings.push(`loadProbes threw, 0 probes loaded: ${msg(e)}`);
    }
  }

  const decided: Verdict[] = [];
  const pending: Node[] = [];
  /** A probe that throws or lies is retired for the rest of the run, once. */
  const disabled = new Set<string>();
  const label = (p: Probe, i: number) => `${p?.id ?? `probe#${i}`} v${p?.version ?? '?'}`;

  for (const node of nodes) {
    let verdict: Verdict | null = null;

    for (let i = 0; i < probes.length && !verdict; i++) {
      const probe = probes[i] as Probe;
      const name = label(probe, i);
      if (disabled.has(name)) continue;

      let matched = false;
      try {
        matched = probe.match(node) === true;
      } catch (e) {
        disabled.add(name);
        warnings.push(`probe ${name}: match() threw, skipped for the rest of this run: ${msg(e)}`);
        continue;
      }
      if (!matched) continue;

      let raw: unknown;
      try {
        raw = probe.assess(node);
      } catch (e) {
        disabled.add(name);
        warnings.push(`probe ${name}: assess() threw on ${node.id}, skipped for the rest of this run: ${msg(e)}`);
        continue;
      }
      if (raw === null || raw === undefined) continue; // abstention — falls through to the agent

      const defect = probeVerdictDefect(raw);
      if (defect) {
        disabled.add(name);
        warnings.push(`probe ${name}: ${defect} (on ${node.id}); skipped for the rest of this run`);
        continue;
      }

      const pv = raw as {
        class: Exclude<GroundingClass, 'unknown'>;
        writeBoundary: Verdict['writeBoundary'];
        evidence: string[];
        confidence: number;
      };
      verdict = {
        nodeId: node.id,
        class: pv.class,
        writeBoundary: pv.writeBoundary,
        evidence: pv.evidence,
        confidence: pv.confidence,
        decidedBy: 'probe',
        probeId: probe.id,
      };
    }

    // No verdict is `pending`, never a class. Nothing here can default to
    // `anchored`; the absence of a decision is an absence, and the agent judges it.
    if (verdict) decided.push(verdict);
    else pending.push(node);
  }

  return { decided, pending, warnings };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv: string[]): { nodesPath?: string; dirs: string[] } {
  const dirs: string[] = [];
  let nodesPath: string | undefined;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === '--probe-dir') {
      const v = argv[++i];
      if (v) dirs.push(v);
    } else if (a.startsWith('--probe-dir=')) {
      dirs.push(a.slice('--probe-dir='.length));
    } else if (a === '--no-sandbox') {
      process.env.KEEL_SANDBOX = '0';
    } else if (!a.startsWith('-') && !nodesPath) {
      nodesPath = a;
    }
  }
  return { nodesPath, dirs };
}

if (import.meta.main) {
  // FIRST, before argument parsing and before any config read: drop KEEL_* that
  // a dotenv in the working directory injected. Only the PARENT does this — the
  // child is re-exec'd with sanitizedEnv() from an already-clean parent, and it
  // is spawned with a cwd of our own choosing, so re-scrubbing there would only
  // risk deleting what the parent deliberately passed down.
  const injectedWarning =
    process.env.KEEL_SANDBOXED === '1' ? null : scrubInjectedEnv();
  if (injectedWarning) console.error(`keel: ${injectedWarning}`);

  const argv = process.argv.slice(2);
  const { nodesPath, dirs } = parseArgs(argv);
  if (!nodesPath || !existsSync(nodesPath)) {
    console.error('usage: bun scripts/probe-sandbox.ts <nodes.json> [--probe-dir <dir>]...');
    process.exit(2);
  }

  /** Every node pending, plus why. The honest floor: never a class. */
  const allPending = (why: string[]): string => {
    let nodes: Node[] = [];
    try {
      nodes = readNodes(nodesPath);
    } catch {
      /* unreadable input — pending stays empty and the warning says why */
    }
    // The scrub notice leads: it explains a run that ignored part of its own
    // configuration, which changes how every line below it should be read.
    const warnings = injectedWarning ? [injectedWarning, ...why] : why;
    return `${JSON.stringify({ decided: [], pending: nodes, warnings } satisfies ClassifyOutput, null, 2)}\n`;
  };

  if (process.env.KEEL_SANDBOXED !== '1') {
    // PARENT SIDE. Probe code does not run here, and never will: both branches
    // below re-exec a child with sanitizedEnv(), so the environment is stripped
    // whether or not the seatbelt is available.
    const { cmd, sandboxed, reason } = sandboxCommand([SELF, ...argv]);
    let degradedBecause: string | null = sandboxed ? null : (reason ?? 'sandbox-exec unavailable');

    /**
     * Carried to the child so the scrub lands in `warnings` and therefore in the
     * artifact, not only on this terminal. A run that silently ignored part of
     * its own configuration must say so where the numbers are read.
     */
    const notice: Record<string, string> = injectedWarning
      ? { KEEL_NOTICE: injectedWarning }
      : {};

    /**
     * We were killed while the child ran. Say so and die — do NOT treat the
     * child's empty stdout as evidence of a broken sandbox, because degrading
     * here would re-run the same probe code with the seatbelt off, turning a
     * hanging probe into an unconfined one. Nothing is printed on stdout: the
     * parent's kill-timer already owns what a timed-out run means.
     */
    const dieIfSignalled = (run: { signalled: boolean }): void => {
      if (!run.signalled) return;
      console.error(
        'keel: probe child was terminated by a signal (the kill-timer fired, or ^C) — ' +
          'no probe verdicts, and NOT degrading to an unconfined re-run',
      );
      process.exit(143);
    };

    if (sandboxed) {
      const run = await runChild(cmd, sanitizedEnv({ ...notice, KEEL_SANDBOXED: '1' }));
      dieIfSignalled(run);
      if (run.stdout.length > 0) {
        process.stdout.write(run.stdout);
        process.exitCode = run.code;
      } else if (run.code !== 0 && SANDBOX_REJECTED.test(run.stderr)) {
        // A profile the kernel rejects exits non-zero having printed nothing on
        // stdout, AND names itself on stderr (measured: exit 65 plus a
        // `sandbox-exec: ...` diagnostic). SBPL is a private interface; a macOS
        // change can do this to us without warning, and silently dispatching
        // zero probes is not an option.
        //
        // BOTH conditions are required, and that is a security property rather
        // than belt-and-braces. Empty stdout ALONE is under the probe's control:
        // a probe that calls `process.exit(0)` at module load produces exactly
        // zero bytes with code 0, and degrading on that signature lets hostile
        // probe code select its own unconfined re-run — reading credentials and
        // reaching the network on the second pass. The discriminator must be
        // something the confined code cannot forge, so it is sandbox-exec's own
        // rejection diagnostic, not the absence of output.
        degradedBecause = `the sandbox-exec re-exec exited ${run.code} and reported a profile error`;
      } else {
        // Confined, produced nothing, and the seatbelt did not complain: the
        // probe code itself exited early. That is a probe defect, never evidence
        // about the sandbox. Fail closed — every node pends.
        const why =
          `the confined probe child exited ${run.code} without producing any output, and ` +
          `sandbox-exec reported no profile error — treating this as a probe defect, NOT as a ` +
          `broken sandbox, so there is no unconfined re-run. No node was decided by a probe.`;
        console.error(`keel: ${why}`);
        process.stdout.write(allPending([why]));
        process.exit(0);
      }
    }

    if (degradedBecause !== null) {
      const warn =
        `sandbox NOT enforced (${degradedBecause}): probe code ran in a child process with a stripped ` +
        `environment — no inherited credentials — under the parent's kill-timer, but network access and ` +
        `filesystem writes were NOT confined`;
      console.error(`keel: ${warn}`);
      const run = await runChild(
        [process.execPath, SELF, ...argv],
        sanitizedEnv({ ...notice, KEEL_SANDBOXED: '1', KEEL_DEGRADED: warn }),
      );
      dieIfSignalled(run);
      if (run.stdout.length > 0) {
        process.stdout.write(run.stdout);
        process.exitCode = run.code;
      } else {
        const why = `the probe child exited ${run.code} without producing any output; no node was decided by a probe`;
        console.error(`keel: ${why}`);
        process.stdout.write(allPending([warn, why]));
      }
    }
  } else {
    // CHILD SIDE. This is the only process that loads and runs probe code.
    const seed: string[] = [];
    const notice = process.env.KEEL_NOTICE?.trim();
    if (notice) seed.push(notice);
    const degraded = process.env.KEEL_DEGRADED?.trim();
    if (degraded) seed.push(degraded);

    try {
      const out = await runSandbox(nodesPath, dirs, seed);
      console.error(
        `keel probe-sandbox: ${out.decided.length} decided by probe, ${out.pending.length} pending, ${out.warnings.length} warnings`,
      );
      process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
    } catch (e) {
      // Even total failure yields a valid ClassifyOutput: the run stays honest
      // by handing every node to the agent, never by inventing a class.
      process.stdout.write(
        allPending([...seed, `probe-sandbox failed, no node was decided by a probe: ${msg(e)}`]),
      );
    }
  }
}
