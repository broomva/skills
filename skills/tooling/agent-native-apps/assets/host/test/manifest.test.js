import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import {
  isServedSegment,
  ManifestError,
  readManifest,
  resolveInside,
  servableFile,
  servedFiles,
  validateManifest,
  versionOf,
} from "../src/manifest.js";

function tmpApp(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ana-manifest-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.writeFileSync(path.join(dir, "app.json"), JSON.stringify({ name: "Pad", permissions: ["agent"] }));
  fs.writeFileSync(path.join(dir, "index.html"), "<title>Pad</title>");
  return dir;
}

test("validateManifest normalizes defaults", () => {
  assert.deepEqual(validateManifest({ name: "Agent Pad" }), {
    name: "Agent Pad",
    permissions: [],
    icon: "A",
    agent: { harness: "claude", harnesses: ["claude"], model: undefined, provider: undefined },
  });
});

test("validateManifest refuses unknown permissions, bad names, harnesses, models and providers", () => {
  assert.throws(() => validateManifest({ name: "x", permissions: ["root"] }), ManifestError);
  assert.throws(() => validateManifest({ name: "<script>" }), ManifestError);
  assert.throws(() => validateManifest({ name: ".hidden" }), ManifestError);
  assert.throws(() => validateManifest({ name: "x", agent: { harness: "gpt" } }), ManifestError);
  assert.throws(
    () => validateManifest({ name: "x", agent: { harnesses: ["claude", "gpt"] } }),
    ManifestError,
  );
  assert.throws(() => validateManifest({ name: "x", agent: { model: "--dangerously-skip" } }), ManifestError);
  assert.throws(
    () => validateManifest({ name: "x", agent: { harness: "t3", provider: "claudeAgent" } }),
    /needs a model/,
  );
  assert.throws(() => validateManifest([]), ManifestError);
  const t3 = validateManifest({
    name: "x",
    agent: { harness: "t3", provider: "claudeAgent", model: "claude-haiku-5-5" },
  });
  assert.deepEqual(t3.agent.harnesses, ["t3"]);
});

test("any served-file edit is a new version; an identical tree is the same version", (t) => {
  const dir = tmpApp(t);
  const v1 = versionOf(dir);
  assert.equal(v1.length, 32);
  assert.equal(versionOf(dir), v1);
  fs.writeFileSync(path.join(dir, "index.html"), "<title>Pad v2</title>");
  const v2 = versionOf(dir);
  assert.notEqual(v2, v1);
  fs.mkdirSync(path.join(dir, "lib"));
  fs.writeFileSync(path.join(dir, "lib", "x.js"), "1");
  assert.notEqual(versionOf(dir), v2);
  assert.equal(readManifest(dir).name, "Pad");
});

test("a file rename is a new version even with the same bytes", (t) => {
  const dir = tmpApp(t);
  fs.writeFileSync(path.join(dir, "a.js"), "same");
  const v1 = versionOf(dir);
  fs.renameSync(path.join(dir, "a.js"), path.join(dir, "b.js"));
  assert.notEqual(versionOf(dir), v1);
});

test("the hash is unambiguous: file bytes cannot imitate a second file's frame", (t) => {
  // If file bytes went into the tree hash raw, this one file would produce the
  // same byte stream as the two files below: its content carries the 8-byte
  // length prefix and the name of a "next file".
  const frameOf = (name) => {
    const length = Buffer.alloc(8);
    length.writeBigUInt64BE(BigInt(name.length));
    return Buffer.concat([length, Buffer.from(name)]);
  };
  const one = tmpApp(t);
  fs.writeFileSync(
    path.join(one, "zz.dat"),
    Buffer.concat([Buffer.from("x"), frameOf("zz.js"), Buffer.from("payload")]),
  );
  const two = tmpApp(t);
  fs.writeFileSync(path.join(two, "zz.dat"), "x");
  fs.writeFileSync(path.join(two, "zz.js"), "payload");
  assert.notEqual(versionOf(one), versionOf(two));
});

test("the served set and the hashed set are the same set", (t) => {
  const dir = tmpApp(t);
  const v1 = versionOf(dir);
  for (const hidden of ["node_modules", ".git", ".claude"]) {
    fs.mkdirSync(path.join(dir, hidden), { recursive: true });
    fs.writeFileSync(path.join(dir, hidden, "logic.js"), "evil()");
    assert.equal(versionOf(dir), v1, `${hidden} is not hashed`);
    assert.equal(servableFile(dir, `/${hidden}/logic.js`), null, `${hidden} is not served`);
  }
  // Case-insensitive macOS must not serve node_modules through uppercase casing.
  assert.equal(resolveInside(dir, "/NODE_MODULES/logic.js"), null);
  assert.equal(servableFile(dir, "/NODE_MODULES/logic.js"), null);
  assert.equal(servableFile(dir, "/Node_Modules/logic.js"), null);
  fs.writeFileSync(path.join(dir, ".env"), "SECRET=1");
  assert.equal(servableFile(dir, "/.env"), null);
  assert.deepEqual(
    servedFiles(dir).map((f) => path.relative(dir, f)),
    ["app.json", "index.html"],
  );
  assert.ok(
    isServedSegment("app.js") &&
      !isServedSegment(".git") &&
      !isServedSegment("node_modules") &&
      !isServedSegment("NODE_MODULES"),
  );
});

test("a symlink in an app folder is refused, so the version covers every served byte", (t) => {
  const dir = tmpApp(t);
  fs.symlinkSync("/etc/hosts", path.join(dir, "hosts.txt"));
  assert.throws(() => versionOf(dir), /symlink/);
});

test("servableFile follows real paths: a symlinked file or parent cannot lead out", (t) => {
  const dir = tmpApp(t);
  const outside = fs.mkdtempSync(path.join(os.tmpdir(), "ana-outside-"));
  t.after(() => fs.rmSync(outside, { recursive: true, force: true }));
  fs.writeFileSync(path.join(outside, "secret.txt"), "secret");
  fs.symlinkSync(path.join(outside, "secret.txt"), path.join(dir, "leak.txt"));
  fs.symlinkSync(outside, path.join(dir, "sub"));
  fs.symlinkSync(path.join(dir, "index.html"), path.join(dir, "alias.html"));
  assert.equal(servableFile(dir, "/leak.txt"), null);
  assert.equal(servableFile(dir, "/sub/secret.txt"), null);
  assert.equal(servableFile(dir, "/alias.html"), null, "in-folder symlink is refused too");
  assert.equal(servableFile(dir, "/missing.js"), null);
  assert.equal(servableFile(dir, "/%E0%A4%A"), null, "a malformed escape is not a crash");
  assert.equal(servableFile(dir, "/index.html"), fs.realpathSync(path.join(dir, "index.html")));
});

test("resolveInside refuses traversal out of the app folder", () => {
  const dir = "/tmp/app";
  assert.equal(resolveInside(dir, "/index.html"), "/tmp/app/index.html");
  assert.equal(resolveInside(dir, "/"), "/tmp/app/index.html");
  assert.equal(resolveInside(dir, "/../etc/passwd"), null);
  assert.equal(resolveInside(dir, "/%2e%2e/etc/passwd"), null);
  assert.equal(resolveInside(dir, "/../app-evil/x"), null);
});
