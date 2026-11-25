import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { Registry, RegistryError } from "../src/registry.js";

function tmpHome(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ana-registry-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test("grants are bound to a version and to a valid one", (t) => {
  const r = new Registry(tmpHome(t));
  r.put({ id: "a", bundlePath: "/x/A.app" });
  r.grant("a", "v1", ["notifications"]);
  assert.deepEqual([...r.grantedFor("a", "v1")], ["notifications"]);
  assert.equal(r.grantedFor("a", "v2").size, 0);
  assert.equal(r.grantedFor("a", null).size, 0);
  assert.throws(() => r.grant("a", null, ["notifications"]), RegistryError);
  assert.equal(r.grantedFor("__proto__", "v1").size, 0);
});

test("the registry file is private and survives a reload", (t) => {
  const home = tmpHome(t);
  const r = new Registry(home);
  r.put({ id: "a", bundlePath: "/x/A.app", cdhash: "ab" });
  assert.equal(fs.statSync(path.join(home, "registry.json")).mode & 0o777, 0o600);
  assert.equal(new Registry(home).get("a").cdhash, "ab");
  assert.equal(fs.readdirSync(home).filter((f) => f.endsWith(".tmp")).length, 0);
});

test("a corrupt registry is moved aside and refused, never silently emptied", (t) => {
  const home = tmpHome(t);
  fs.writeFileSync(path.join(home, "registry.json"), "{not json");
  assert.throws(() => new Registry(home), /not valid JSON/);
  assert.ok(fs.readdirSync(home).some((f) => f.startsWith("registry.json.corrupt-")));
});

test("bundleOwner finds another app that holds a bundle path", (t) => {
  const r = new Registry(tmpHome(t));
  r.put({ id: "a", bundlePath: "/x/Pad.app" });
  assert.equal(r.bundleOwner("/x/Pad.app", "b").id, "a");
  assert.equal(r.bundleOwner("/x/Pad.app", "a"), undefined);
  r.update("a", { t3ThreadId: "mcp:1" });
  assert.equal(r.get("a").t3ThreadId, "mcp:1");
});

test("a registry entry with no version grants nothing, even to an app with no version", (t) => {
  const home = tmpHome(t);
  fs.writeFileSync(
    path.join(home, "registry.json"),
    JSON.stringify({ apps: {}, grants: { a: { version: null, permissions: ["full-access"] } } }),
  );
  assert.equal(new Registry(home).grantedFor("a", null).size, 0);
});
