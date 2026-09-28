import { test } from "node:test";
import assert from "node:assert/strict";
import { InMemoryFs } from "just-bash";
import { snapshot, restore } from "../../scripts/fs-snapshot.mjs";

const ALL_BYTES = new Uint8Array(256);
for (let i = 0; i < 256; i++) ALL_BYTES[i] = i;
const UTF8 = "héllo 世界 🚀 é \u{1F469}‍\u{1F4BB}";
const FIXED = new Date("2021-03-04T05:06:07.000Z");

async function roundTrip(build) {
  const fs = new InMemoryFs();
  await fs.mkdir("/work", { recursive: true });
  await build(fs);
  const snap = JSON.parse(JSON.stringify(await snapshot(fs, "/work")));  // must be JSON-safe
  return { before: fs, after: await restore(snap), snap };
}

test("file content, mode and mtime survive", async () => {
  const { after } = await roundTrip(async (fs) => {
    await fs.writeFile("/work/a.txt", "hello\n");
    await fs.chmod("/work/a.txt", 0o700);
    await fs.utimes("/work/a.txt", FIXED, FIXED);
  });
  assert.equal(await after.readFile("/work/a.txt"), "hello\n");
  const st = await after.stat("/work/a.txt");
  assert.equal(st.mode & 0o777, 0o700);
  assert.equal(st.mtime.getTime(), FIXED.getTime());
});

test("binary content survives all 256 byte values", async () => {
  const { after } = await roundTrip((fs) => fs.writeFile("/work/b.dat", ALL_BYTES));
  const got = new Uint8Array(await after.readFileBuffer("/work/b.dat"));
  assert.equal(Buffer.from(got).toString("hex"), Buffer.from(ALL_BYTES).toString("hex"));
});

test("utf8 multibyte, empty files and odd filenames survive", async () => {
  const { after } = await roundTrip(async (fs) => {
    await fs.writeFile("/work/u.txt", UTF8);
    await fs.writeFile("/work/empty.txt", "");
    await fs.writeFile("/work/two words.txt", "sp\n");
    await fs.writeFile("/work/ev\nil.txt", "nl\n");
  });
  assert.equal(await after.readFile("/work/u.txt"), UTF8);
  assert.equal((await after.readFileBuffer("/work/empty.txt")).length, 0);
  assert.equal(await after.readFile("/work/two words.txt"), "sp\n");
  assert.equal(await after.readFile("/work/ev\nil.txt"), "nl\n");
});

test("EMPTY directories survive (constructor initialFiles cannot express them)", async () => {
  const { after } = await roundTrip((fs) => fs.mkdir("/work/empty/deeper", { recursive: true }));
  assert.equal((await after.stat("/work/empty")).isDirectory, true);
  assert.equal((await after.stat("/work/empty/deeper")).isDirectory, true);
});

test("symlinks survive: absolute, relative, to-dir and broken", async () => {
  const { after } = await roundTrip(async (fs) => {
    await fs.writeFile("/work/t.txt", "tgt\n");
    await fs.mkdir("/work/d", { recursive: true });
    await fs.writeFile("/work/d/in.txt", "in\n");
    await fs.symlink("/work/t.txt", "/work/abs");
    await fs.symlink("t.txt", "/work/rel");
    await fs.symlink("/work/d", "/work/dlink");
    await fs.symlink("/work/nope", "/work/broken");
  });
  assert.equal((await after.lstat("/work/abs")).isSymbolicLink, true);
  assert.equal(await after.readlink("/work/abs"), "/work/t.txt");
  assert.equal(await after.readlink("/work/rel"), "t.txt", "relative target must not be rewritten");
  assert.equal(await after.readFile("/work/dlink/in.txt"), "in\n");
  assert.equal((await after.lstat("/work/broken")).isSymbolicLink, true, "a broken link is still a link");
});

test("hardlinked paths are recorded as a group, not duplicated payloads", async () => {
  const { snap, after } = await roundTrip(async (fs) => {
    await fs.writeFile("/work/h1.txt", "orig\n");
    await fs.link("/work/h1.txt", "/work/h2.txt");
  });
  const linked = snap.files.find((f) => f.hardlinkTo);
  assert.ok(linked, "one path must be stored as a hardlink reference");
  assert.equal(linked.path, "/work/h2.txt");
  assert.equal(linked.hardlinkTo, "/work/h1.txt");
  assert.equal(snap.files.filter((f) => f.b64).length, 1, "payload must not be duplicated");
  assert.equal(await after.readFile("/work/h2.txt"), "orig\n");
});

test("snapshot is scoped: the ~180 synthetic /bin,/usr,/dev,/proc entries are excluded", async () => {
  const { Bash } = await import("just-bash");
  const fs = new InMemoryFs();
  new Bash({ fs });                                   // populates the standard layout
  await fs.mkdir("/work", { recursive: true });
  await fs.writeFile("/work/only.txt", "x\n");
  const snap = await snapshot(fs, "/work");
  const all = [...snap.files, ...snap.dirs, ...snap.links].map((e) => e.path);
  assert.ok(all.length < 10, `expected a small scoped set, got ${all.length}`);
  assert.ok(!all.some((p) => p.startsWith("/bin") || p.startsWith("/usr") || p.startsWith("/proc")),
    `synthetic layout leaked into the snapshot: ${all.filter((p) => !p.startsWith("/work"))}`);
  assert.ok(all.includes("/work/only.txt"));
});
