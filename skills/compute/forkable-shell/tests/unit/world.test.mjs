import { test } from "node:test";
import assert from "node:assert/strict";
import * as nfs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { World } from "../../scripts/world.mjs";

const tmp = () => nfs.mkdtempSync(path.join(os.tmpdir(), "world-"));

test("a new world persists across a fresh open", async () => {
  const d = tmp(), p = path.join(d, "w.json");
  const w = await World.open(p);
  await w.exec("echo hello > /work/a.txt");
  const again = await World.open(p);            // re-read from disk
  assert.equal(await again.fs.readFile("/work/a.txt"), "hello\n");
});

test("seeded files land in the world", async () => {
  const d = tmp(), p = path.join(d, "w.json");
  const w = await World.open(p, { files: { "/work/data/x.csv": "a,b\n1,2\n" } });
  assert.equal(await w.fs.readFile("/work/data/x.csv"), "a,b\n1,2\n");
});

test("fork produces a byte-identical world", async () => {
  const d = tmp(), a = path.join(d, "a.json"), b = path.join(d, "b.json");
  const w = await World.open(a);
  await w.exec("echo seed > /work/seed.txt");
  World.fork(a, b);
  assert.equal(nfs.readFileSync(a, "utf8"), nfs.readFileSync(b, "utf8"));
});

test("a branch cannot mutate its trunk", async () => {
  const d = tmp(), trunk = path.join(d, "t.json"), br = path.join(d, "b.json");
  const t = await World.open(trunk);
  await t.exec("echo shared > /work/shared.txt");
  const beforeTurns = World.info(trunk).turns;
  const beforeBytes = nfs.readFileSync(trunk, "utf8");

  World.fork(trunk, br);
  const b = await World.open(br);
  await b.exec("echo branch-only > /work/branch.txt");
  await b.exec("rm -f /work/shared.txt");        // destructive on the branch

  assert.equal(nfs.readFileSync(trunk, "utf8"), beforeBytes, "trunk bytes changed");
  assert.equal(World.info(trunk).turns, beforeTurns, "trunk turn count changed");
  const trunkFiles = World.info(trunk).files.map((f) => f.path);
  assert.ok(trunkFiles.includes("/work/shared.txt"), "branch deletion reached the trunk");
  assert.ok(!trunkFiles.includes("/work/branch.txt"), "branch file leaked into the trunk");
  assert.ok(World.info(br).files.map((f) => f.path).includes("/work/branch.txt"));
});

test("two branches from one trunk cannot see each other", async () => {
  const d = tmp(), trunk = path.join(d, "t.json");
  await (await World.open(trunk)).exec("echo base > /work/base.txt");
  const paths = [path.join(d, "A.json"), path.join(d, "B.json")];
  for (const p of paths) World.fork(trunk, p);
  const [A, B] = await Promise.all(paths.map((p) => World.open(p)));
  await A.exec("echo from-a > /work/a-only.txt");
  await B.exec("echo from-b > /work/b-only.txt");
  const aFiles = World.info(paths[0]).files.map((f) => f.path);
  const bFiles = World.info(paths[1]).files.map((f) => f.path);
  assert.ok(aFiles.includes("/work/a-only.txt") && !aFiles.includes("/work/b-only.txt"));
  assert.ok(bFiles.includes("/work/b-only.txt") && !bFiles.includes("/work/a-only.txt"));
});

test("turns increment per exec and shell state persists across reopen", async () => {
  const d = tmp(), p = path.join(d, "w.json");
  const w = await World.open(p);
  await w.exec("mkdir -p /work/sub && cd /work/sub && export K=v");
  assert.equal(World.info(p).turns, 1);
  const again = await World.open(p);
  assert.equal((await again.exec('echo "$K@$(pwd)"')).stdout.trim(), "v@/work/sub");
  assert.equal(World.info(p).turns, 2);
});

test("forking a missing world throws rather than creating one", () => {
  const d = tmp();
  assert.throws(() => World.fork(path.join(d, "nope.json"), path.join(d, "x.json")), /no such world/);
});

// --- regressions from the P20 cross-model review -----------------------------

test("REGRESSION: fork refuses a destination aliased to the trunk", async () => {
  const d = tmp(), trunk = path.join(d, "t.json"), alias = path.join(d, "alias.json");
  const t = await World.open(trunk);
  await t.exec("echo trunk > /work/t.txt");
  nfs.linkSync(trunk, alias);                       // dest pre-exists, SAME inode
  const before = nfs.readFileSync(trunk, "utf8");
  assert.throws(() => World.fork(trunk, alias), /same file as the trunk/);
  assert.equal(nfs.readFileSync(trunk, "utf8"), before);
});

test("REGRESSION: forking over a pre-existing dest does not write THROUGH it", async () => {
  // The dest is hardlinked to an unrelated third file. copyFileSync opens an
  // existing dest with O_TRUNC and keeps its inode, so without an unlink the copy
  // lands in `bystander` too. Comparing trunk-vs-dest inodes would NOT catch this:
  // those are always different, which made the first version of this test vacuous
  // (mutant M9 survived it).
  const d = tmp(), trunk = path.join(d, "t.json");
  const dst = path.join(d, "b.json"), bystander = path.join(d, "unrelated.json");
  const t = await World.open(trunk);
  await t.exec("echo trunk > /work/t.txt");

  nfs.writeFileSync(bystander, "UNRELATED");
  nfs.linkSync(bystander, dst);                     // dest shares bystander's inode
  const dstInodeBefore = nfs.statSync(dst).ino;
  const beforeTrunk = nfs.readFileSync(trunk, "utf8");

  World.fork(trunk, dst);

  assert.equal(nfs.readFileSync(bystander, "utf8"), "UNRELATED",
    "fork wrote through the destination into an unrelated hardlinked file");
  assert.notEqual(nfs.statSync(dst).ino, dstInodeBefore,
    "destination kept its old inode instead of being replaced");

  const b = await World.open(dst);
  await b.exec("echo branch > /work/branch.txt");
  assert.equal(nfs.readFileSync(trunk, "utf8"), beforeTrunk, "branch mutated the trunk");
  assert.equal(nfs.readFileSync(bystander, "utf8"), "UNRELATED", "branch mutated the bystander");
});

test("REGRESSION: save writes via a temp file and never truncates the world in place", async () => {
  // Asserting only "valid JSON, no strays" passes under a direct in-place write too,
  // which is exactly the implementation this test exists to forbid. Instead, block
  // the temp path: a write-then-rename save MUST fail and leave the world intact,
  // whereas a direct write would happily clobber it.
  const d = tmp(), p = path.join(d, "w.json");
  const w = await World.open(p);
  await w.exec("echo original > /work/a.txt");
  const good = nfs.readFileSync(p, "utf8");

  nfs.mkdirSync(`${p}.tmp-${process.pid}`);        // temp path is now un-writable
  await assert.rejects(async () => {
    await w.exec("echo clobbered > /work/a.txt");
  }, "save must fail rather than write the world in place");
  assert.equal(nfs.readFileSync(p, "utf8"), good, "the previous world was destroyed");

  nfs.rmdirSync(`${p}.tmp-${process.pid}`);
  await w.exec("echo after > /work/a.txt");
  assert.doesNotThrow(() => JSON.parse(nfs.readFileSync(p, "utf8")));
  assert.deepEqual(nfs.readdirSync(d).filter((f) => f.includes(".tmp-")), []);
});

test("REGRESSION: fork onto a DANGLING symlink dest does not write to its target", async () => {
  // existsSync() follows symlinks and returns false for a dangling one, so an
  // existence-gated guard is skipped and copyFileSync then follows the link.
  const d = tmp(), trunk = path.join(d, "t.json");
  const target = path.join(d, "victim.json"), dst = path.join(d, "dangling.json");
  const t0 = await World.open(trunk);
  await t0.exec("echo trunk > /work/t.txt");

  nfs.symlinkSync(target, dst);                     // dangling: target does not exist
  assert.equal(nfs.existsSync(dst), false, "precondition: a dangling link looks absent");

  World.fork(trunk, dst);

  // The link must be REPLACED, not followed. If it is followed, the copy lands at
  // an attacker-chosen path that fork was never asked to write.
  assert.equal(nfs.existsSync(target), false,
    "fork followed a dangling symlink and created a file at its target");
  assert.equal(nfs.lstatSync(dst).isSymbolicLink(), false, "dest should be a real file now");
  assert.doesNotThrow(() => JSON.parse(nfs.readFileSync(dst, "utf8")));
});
