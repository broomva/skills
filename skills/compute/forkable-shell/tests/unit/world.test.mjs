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

test("REGRESSION: forking over a pre-existing dest lands on a fresh inode", async () => {
  const d = tmp(), trunk = path.join(d, "t.json"), dst = path.join(d, "b.json");
  const t = await World.open(trunk);
  await t.exec("echo trunk > /work/t.txt");
  nfs.writeFileSync(dst, "stale content");          // plain pre-existing file
  const beforeTrunk = nfs.readFileSync(trunk, "utf8");
  World.fork(trunk, dst);
  assert.notEqual(nfs.statSync(trunk).ino, nfs.statSync(dst).ino, "branch shares the trunk's inode");
  const b = await World.open(dst);
  await b.exec("echo branch > /work/branch.txt");
  assert.equal(nfs.readFileSync(trunk, "utf8"), beforeTrunk, "branch mutated the trunk");
});

test("REGRESSION: save is atomic and leaves no temp file behind", async () => {
  const d = tmp(), p = path.join(d, "w.json");
  const w = await World.open(p);
  await w.exec("echo x > /work/a.txt");
  const strays = nfs.readdirSync(d).filter((f) => f.includes(".tmp-"));
  assert.deepEqual(strays, [], `temp files left behind: ${strays}`);
  assert.doesNotThrow(() => JSON.parse(nfs.readFileSync(p, "utf8")));
});
