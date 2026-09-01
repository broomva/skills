#!/usr/bin/env node
// Mutation proof: a green suite means nothing until you show it can go red.
//
// Each mutant breaks ONE real behaviour. The suite must fail for every one.
// Runs the UNIT suite only -- the MCP integration tests spawn a subprocess per
// call and would make this minutes long; every mutant below is reachable from
// unit tests by construction.
//
// Guards learned the hard way:
//   - refuse to run on a dirty tree (revert-to-HEAD destroys uncommitted work)
//   - assert each anchor appears EXACTLY once (a stale anchor silently no-ops
//     and reports a false SURVIVED)
import { execSync, spawnSync } from "node:child_process";
import * as nfs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const run = (cmd) => execSync(cmd, { cwd: ROOT, encoding: "utf8" });

const dirty = run("git -c core.fsmonitor=false status --porcelain -- .").trim();
if (dirty) {
  console.error("REFUSING: working tree is dirty. Commit first -- this script reverts to HEAD.\n" + dirty);
  process.exit(1);
}

const MUTANTS = [
  ["M1 symlinks not captured", "scripts/fs-snapshot.mjs",
    "links.push({ path: p, target: await fs.readlink(p), mode: st.mode });", "void 0;"],
  ["M2 snapshot prefix ignored", "scripts/fs-snapshot.mjs",
    '.filter((p) => p === prefix || p.startsWith(prefix + "/"))', ".filter(() => true)"],
  ["M3 hardlinks not grouped", "scripts/fs-snapshot.mjs",
    "if (key && byIdentity.has(key)) {", "if (key && false) {"],
  ["M4 directories not restored", "scripts/fs-snapshot.mjs",
    "if (!(await fs.exists(d.path))) await fs.mkdir(d.path, { recursive: true });", "void 0;"],
  ["M5 cwd not replayed", "scripts/persistent-shell.mjs",
    "      this.cwd = cwd;", "      this.cwd = this.cwd;"],
  ["M6 env not replayed", "scripts/persistent-shell.mjs",
    "if (Object.keys(next).length) this.env = next;", "void 0;"],
  ["M7 turns never increment", "scripts/world.mjs", "this.turns += 1;", "this.turns += 0;"],
  ["M8 world saves wrong subtree", "scripts/world.mjs",
    "fs: await snapshot(this.fs, this.prefix),", 'fs: await snapshot(this.fs, "/nowhere"),'],
  // Mutants for the defects the P20 cross-model review found. Without these the
  // fixes are asserted only by tests written alongside them.
  ["M9 fork reuses an existing dest inode", "scripts/world.mjs",
    "nfs.unlinkSync(destPath);", "void 0;"],
  ["M10 ANSI-C env values dropped", "scripts/persistent-shell.mjs",
    "next[ansi[1]] = unescapeAnsiC(ansi[2]); continue;", 'next[ansi[1]] = ""; continue;'],
  ["M11 env names unvalidated", "scripts/persistent-shell.mjs",
    ".filter(([k]) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(k))", ".filter(() => true)"],
  ["M12 CLI seed decodes as utf8", "scripts/vbash.mjs",
    "files[guest] = new Uint8Array(nfs.readFileSync(host));", 'files[guest] = nfs.readFileSync(host, "utf8");'],
  ["M13 dest existence follows links", "scripts/world.mjs",
    "try { destEntry = nfs.lstatSync(destPath); } catch { /* genuinely absent */ }",
    "destEntry = nfs.existsSync(destPath) ? {} : null;"],
  ["M14 save writes in place", "scripts/world.mjs",
    "const tmp = `${this.path}.tmp-${process.pid}`;\n    nfs.writeFileSync(tmp, payload);\n    nfs.renameSync(tmp, this.path);",
    "nfs.writeFileSync(this.path, payload);"],
  // (the former M15 targeted a redundant token check; the per-call mark in M17
  //  is what actually detects a skipped epilogue, so that mutant was deleted)
  ["M16 octal escapes mis-decoded", "scripts/persistent-shell.mjs",
    'if (/^[0-7]+$/.test(c)) return String.fromCharCode(parseInt(c, 8) & 0xff);', "void 0;"],
  ["M17 delimiter not per-call", "scripts/persistent-shell.mjs",
    "const mark = `${MARK}${token}`;", "const mark = MARK;"],
  ["M18 cwd read via shadowable pwd", "scripts/persistent-shell.mjs",
    "builtin pwd; echo ${sq(mark)}", "pwd; echo ${sq(mark)}"],
  ["M19 octal grammar too greedy", "scripts/persistent-shell.mjs",
    "|[0-7]{1,3}|", "|0[0-7]{0,3}|[1-7][0-7]{0,2}|"],
  // NB: mutate a VALUE here, not the loop's exit path -- a mutant that leaves the
  // loop unable to make progress hangs the runner instead of failing it.
  ["M20 output never trimmed to the cap", "scripts/vbash-server.mjs",
    "while (build().length > MAX_OUTPUT) {", "while (build().length > MAX_OUTPUT * 10) {"],
  ["M21 stderr exempt from trimming", "scripts/vbash-server.mjs",
    "    else err = err.slice(0, Math.max(0, err.length - over));", "    else break;"],
  ["M22 cap accepted unvalidated", "scripts/vbash-server.mjs",
    "if (!Number.isInteger(MAX_OUTPUT) || MAX_OUTPUT < MIN_OUTPUT) {", "if (false) {"],
  ["M23 env cannot be cleared", "scripts/persistent-shell.mjs",
    "      this.env = next;", "      if (Object.keys(next).length) this.env = next;"],
];

// The MCP suite is included because mutants in the server (M20) are unreachable
// from the unit tests; a mutant no suite can observe reports a spurious SURVIVED.
const SUITE = ["tests/unit/fs-snapshot.test.mjs", "tests/unit/persistent-shell.test.mjs",
               "tests/unit/world.test.mjs", "tests/unit/cli.test.mjs",
               "tests/integration/mcp.test.mjs"];

/** Run the unit suite with a PINNED reporter. Node <=22 defaults to tap and >=23 to
 *  spec, so an unpinned parse silently reads every mutant as inconclusive. */
function runSuite() {
  const r = spawnSync(process.execPath, ["--test", "--test-reporter=tap", ...SUITE],
    { cwd: ROOT, encoding: "utf8", shell: false });
  const out = `${r.stdout ?? ""}${r.stderr ?? ""}`;
  const num = (re) => { const m = re.exec(out); return m ? Number(m[1]) : NaN; };
  return { status: r.status, out, tests: num(/^# tests (\d+)$/m), fail: num(/^# fail (\d+)$/m) };
}

// Green baseline. Without it, a suite that is broken for every mutant would report a
// perfect kill score.
const baseline = runSuite();
if (!(baseline.tests > 0) || baseline.fail !== 0) {
  console.error(`baseline is not green: ${baseline.tests} tests, ${baseline.fail} failing`);
  console.error(baseline.out.slice(-1500));
  process.exit(1);
}
console.log(`baseline: ${baseline.tests} tests, 0 failing\n`);

let inFlight = null;   // { file, src } while a mutant is applied
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    // A `finally` block does not run when the process is signalled, which would
    // leave production source mutated. Scratch copies would be more robust still.
    if (inFlight) { try { nfs.writeFileSync(inFlight.file, inFlight.src); } catch {} }
    process.exit(130);
  });
}

let killed = 0;
const survivors = [];
console.log("mutant                            verdict");
console.log("-".repeat(56));
for (const [name, rel, anchor, repl] of MUTANTS) {
  const file = path.join(ROOT, rel);
  const src = nfs.readFileSync(file, "utf8");
  const n = src.split(anchor).length - 1;
  if (n !== 1) {
    console.log(`${name.padEnd(34)}STALE ANCHOR (x${n}) -- fix this script`);
    survivors.push(name);
    continue;
  }
  let verdict;
  try {
    inFlight = { file, src };
    nfs.writeFileSync(file, src.replace(anchor, repl));
    const res = runSuite();
    // A nonzero exit alone is not a kill: the runner also exits nonzero when a test
    // file fails to LOAD (a syntax error reports `fail 1` too), which would score an
    // infrastructure failure as a passing mutation proof. Require a failing assertion
    // AND the same number of tests as the green baseline -- a load failure changes it.
    if (res.tests !== baseline.tests) {
      verdict = `*** INCONCLUSIVE *** ${res.tests} tests ran, baseline ${baseline.tests} (load failure?)`;
    } else if (res.fail > 0) {
      verdict = `KILLED (${res.fail} failing)`;
    } else {
      verdict = "*** SURVIVED ***";
    }
  } finally {
    // Restore the EXACT bytes we captured. `git checkout --` would also revert any
    // unrelated uncommitted edit in this file.
    nfs.writeFileSync(file, src);
    inFlight = null;
  }
  console.log(`${name.padEnd(34)}${verdict}`);
  if (verdict.startsWith("KILLED")) killed++; else survivors.push(name);
}
console.log("-".repeat(56));
console.log(`killed ${killed}/${MUTANTS.length}`);
const after = run("git -c core.fsmonitor=false status --porcelain -- .").trim();
if (after) { console.error("TREE NOT RESTORED:\n" + after); process.exit(1); }
if (survivors.length) { console.error("SURVIVORS (behaviour no test covers): " + survivors.join(", ")); process.exit(1); }
console.log("tree restored clean");
