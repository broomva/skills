// The CLI is the user-facing surface; it must not decode bytes as text.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as nfs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const CLI = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "scripts", "vbash.mjs");
const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const run = (...args) => execFileSync(process.execPath, [CLI, ...args], { cwd: ROOT });

test("REGRESSION: --seed and cat round-trip binary without corruption", () => {
  const d = nfs.mkdtempSync(path.join(os.tmpdir(), "cli-"));
  const bin = Buffer.from([0, 1, 2, 255, 254, 0x80, 0x81, 0x0a, 0x00]);
  const host = path.join(d, "in.bin"), world = path.join(d, "w.json");
  nfs.writeFileSync(host, bin);
  run("init", world, "--seed", `${host}:/work/b.dat`);
  const out = run("cat", world, "/work/b.dat");
  assert.equal(out.toString("hex"), bin.toString("hex"), "CLI corrupted binary content");
});

test("fork via the CLI isolates the branch from the trunk", () => {
  const d = nfs.mkdtempSync(path.join(os.tmpdir(), "cli-"));
  const t = path.join(d, "t.json"), b = path.join(d, "b.json");
  run("init", t);
  run("exec", t, "echo base > /work/base.txt");
  run("fork", t, b);
  run("exec", b, "echo only > /work/branch.txt");
  const info = run("info", t).toString();
  assert.match(info, /base\.txt/);
  assert.ok(!info.includes("branch.txt"), "branch file leaked into the trunk");
});

test("REGRESSION: the CLI warns when shell state was not captured", () => {
  const d = nfs.mkdtempSync(path.join(os.tmpdir(), "cli-"));
  const world = path.join(d, "w.json");
  run("init", world);
  run("exec", world, "mkdir -p /work/s");
  let stderr = "";
  try { run("exec", world, "cd /work/s; set -e; false"); }
  catch (e) { stderr = String(e.stderr ?? ""); }
  assert.match(stderr, /NOT captured/, "a discarded cd/export was not reported to the user");
});
