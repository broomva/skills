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
    "this.cwd = pwd.trim() || this.cwd;", "this.cwd = this.cwd;"],
  ["M6 env not replayed", "scripts/persistent-shell.mjs",
    "if (Object.keys(next).length) this.env = next;", "void 0;"],
  ["M7 turns never increment", "scripts/world.mjs", "this.turns += 1;", "this.turns += 0;"],
  ["M8 world saves wrong subtree", "scripts/world.mjs",
    "fs: await snapshot(this.fs, this.prefix),", 'fs: await snapshot(this.fs, "/nowhere"),'],
];

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
  nfs.writeFileSync(file, src.replace(anchor, repl));
  const r = spawnSync(process.execPath, ["--test", "tests/unit/fs-snapshot.test.mjs", "tests/unit/persistent-shell.test.mjs", "tests/unit/world.test.mjs"], { cwd: ROOT, encoding: "utf8", shell: false });
  const died = r.status !== 0;
  console.log(`${name.padEnd(34)}${died ? "KILLED" : "*** SURVIVED ***"}`);
  if (died) killed++; else survivors.push(name);
  run(`git checkout -- ${rel}`);
}
console.log("-".repeat(56));
console.log(`killed ${killed}/${MUTANTS.length}`);
const after = run("git -c core.fsmonitor=false status --porcelain -- .").trim();
if (after) { console.error("TREE NOT RESTORED:\n" + after); process.exit(1); }
if (survivors.length) { console.error("SURVIVORS (behaviour no test covers): " + survivors.join(", ")); process.exit(1); }
console.log("tree restored clean");
