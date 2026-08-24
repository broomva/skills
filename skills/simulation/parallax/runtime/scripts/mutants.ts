/**
 * Mutation testing for the guarantees this project actually sells.
 *
 * A passing suite is not a testing suite. Every mutant below deletes one
 * specific promise -- the accept brand, idempotent acceptance, "the newest
 * acceptance", answer-value identity -- and asks whether anything goes red. A
 * mutant that SURVIVES means the promise is asserted by prose and by nothing
 * else.
 *
 * Three things this harness does on purpose, because each is a way a mutation
 * report lies:
 *
 *   1. It refuses to run against a dirty tree -- this directory's, not the whole
 *      monorepo's. Reverting is `git checkout --`, which would silently destroy
 *      uncommitted work, and every mutant after the first would then be patching
 *      an already-reverted file.
 *   2. Every anchor must appear EXACTLY ONCE. A stale anchor that matches
 *      nothing is a no-op mutation, and a no-op mutation always "survives" --
 *      which reads as a finding when it is really a broken harness.
 *   3. It runs two controls in both polarities. A must-kill control that
 *      survives means the harness cannot see red; a must-survive control that
 *      dies means it reports noise as signal. Either invalidates the run.
 *
 * Run with: bun run mutants
 */
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = join(import.meta.dir, "..");
const only = process.argv.includes("--only")
  ? process.argv[process.argv.indexOf("--only") + 1]
  : undefined;

interface Mutant {
  readonly name: string;
  readonly file: string;
  readonly find: string;
  readonly replace: string;
  /** What breaks in the world if nothing catches this. */
  readonly promise: string;
  readonly control?: "must-kill" | "must-survive";
}

const MUTANTS: Mutant[] = [
  {
    name: "control/must-kill",
    file: "src/core/ops.ts",
    // A RUNTIME break, not a type break. The first version of this control was a
    // broken signature and it SURVIVED -- because `bun test` does not typecheck.
    // The control was measuring the wrong thing, which is the exact failure it
    // exists to detect.
    find: "  return h(\n    log.read(branch).map((e) => ({ a: e.actor, n: e.action, p: e.params, d: e.derivation })),\n  );",
    replace: '  return "mutant-constant-trace-hash";',
    promise:
      "CONTROL: replay collapses to a constant. If this survives, the harness cannot see red.",
    control: "must-kill",
  },
  {
    name: "control/must-survive",
    file: "src/core/ontology.ts",
    find: "/** Runtime predicate for the accept brand.",
    replace: "/** (mutation-harness control comment) Runtime predicate for the accept brand.",
    promise:
      "CONTROL: a comment-only edit. If this is killed, the harness reports noise as signal.",
    control: "must-survive",
  },
  {
    name: "brand/isActive-always-true",
    file: "src/core/ontology.ts",
    find: "(value as Record<PropertyKey, unknown>)[ACCEPTED] === true &&",
    replace: "true &&",
    promise: "An ontology nobody accepted can run. The accept gate is the whole trust pitch.",
  },
  {
    name: "accept/idempotent-flag-inverted",
    file: "src/tools/handlers.ts",
    find: "return ok({ ...acceptanceView(existing), idempotent: true });",
    replace: "return ok({ ...acceptanceView(existing), idempotent: false });",
    promise: "A retry reports itself as a fresh acceptance.",
  },
  {
    name: "accept/dedupe-ignores-answer-values",
    file: "src/tools/handlers.ts",
    find: "h(a.answers ?? {}) === answersKey,",
    replace: "true,",
    promise:
      "Two acceptances differing in what the human actually said collide. This is the exact defect 09e12d0 fixed.",
  },
  {
    name: "accept/dedupe-ignores-who-accepted",
    file: "src/tools/handlers.ts",
    find: "a.acceptedBy === input.acceptedBy &&",
    replace: "true &&",
    promise: "One person's acceptance is reused for another person.",
  },
  {
    name: "find/newest-becomes-oldest",
    file: "src/tools/handlers.ts",
    // `const newest = all[0]` appears twice (findAcceptance and findRun), so the
    // anchor carries the line above it to stay unique.
    find: "  if (ontologyId === undefined || ontologyId.length === 0) {\n    const newest = all[0];",
    replace:
      "  if (ontologyId === undefined || ontologyId.length === 0) {\n    const newest = all[all.length - 1];",
    promise: "`run` with no --ontology silently uses the FIRST acceptance ever made.",
  },
];

function run(cmd: string[]): number {
  const p = Bun.spawnSync(cmd, { cwd: ROOT, env: process.env, stdout: "pipe", stderr: "pipe" });
  return p.exitCode ?? 1;
}

function gitStatus(): string {
  // Scoped to this directory with `-- .`. Without the pathspec this reports the
  // whole monorepo, so an unrelated edit anywhere in broomva/skills refuses the
  // run at preflight and, past that, fires REVERT FAILED after the first mutant.
  const p = Bun.spawnSync(
    ["git", "-c", "core.fsmonitor=false", "status", "--porcelain", "--", "."],
    { cwd: ROOT, env: process.env, stdout: "pipe", stderr: "pipe" },
  );
  return new TextDecoder().decode(p.stdout).trim();
}

// ------------------------------------------------------------------ preflight
const dirty = gitStatus();
if (dirty !== "") {
  console.error("refusing to run: the tree is not clean.\n");
  console.error(dirty);
  console.error("\nreverting a mutant is `git checkout --`, which would destroy this work.");
  process.exit(1);
}
if (run(["bun", "test"]) !== 0) {
  console.error("refusing to run: the suite is already red, so nothing below would mean anything.");
  process.exit(1);
}

// ------------------------------------------------------------------ mutate
const results: Array<{ m: Mutant; killed: boolean }> = [];
const selected = MUTANTS.filter((m) => only === undefined || m.name.includes(only));

for (const m of selected) {
  const path = join(ROOT, m.file);
  const before = readFileSync(path, "utf8");
  const hits = before.split(m.find).length - 1;
  if (hits !== 1) {
    console.error(`\n  ANCHOR ${m.name}: matched ${hits}x in ${m.file}, expected exactly 1.`);
    console.error("  A no-op mutation always 'survives'. Fix the anchor before trusting this run.");
    process.exit(1);
  }
  writeFileSync(path, before.replace(m.find, m.replace));
  const killed = run(["bun", "test"]) !== 0;
  writeFileSync(path, before); // exact bytes back, no git needed
  if (gitStatus() !== "") {
    console.error(`\n  REVERT FAILED after ${m.name}. Stopping before the next mutant.`);
    process.exit(1);
  }
  results.push({ m, killed });
  process.stdout.write(`  ${killed ? "killed  " : "SURVIVED"}  ${m.name}\n`);
}

// ------------------------------------------------------------------ controls
const ctlKill = results.find((r) => r.m.control === "must-kill");
const ctlLive = results.find((r) => r.m.control === "must-survive");
let invalid = false;
if (ctlKill !== undefined && !ctlKill.killed) {
  console.error("\n  INVALID RUN: the must-kill control survived. The harness cannot see red.");
  invalid = true;
}
if (ctlLive !== undefined && ctlLive.killed) {
  console.error("\n  INVALID RUN: the must-survive control was killed. The harness reports noise.");
  invalid = true;
}

const real = results.filter((r) => r.m.control === undefined);
const survivors = real.filter((r) => !r.killed);
console.log(`\n  ${real.length - survivors.length}/${real.length} mutants killed`);
for (const s of survivors) {
  console.log(`\n  SURVIVED  ${s.m.name}`);
  console.log(`            ${s.m.promise}`);
}
if (invalid) process.exit(1);
process.exit(survivors.length === 0 ? 0 : 1);
