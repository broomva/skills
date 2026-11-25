import assert from "node:assert/strict";
import { test } from "node:test";
import { decide, METHODS, PERMISSIONS, parseMaxTier, requiredPermission } from "../src/capabilities.js";

const ctx = (declared = [], granted = [], maxTier = 3) => ({
  declared: new Set(declared),
  granted: new Set(granted),
  maxTier,
});

test("tier 1 needs no declaration or grant", () => {
  assert.deepEqual(decide({ module: "dock", method: "setBadge" }, ctx()), {
    ok: true,
    permission: null,
    tier: 1,
  });
});

test("an unknown method is ENOSYS, including prototype names", () => {
  assert.equal(decide({ module: "fs", method: "rm" }, ctx(["full-access"], ["full-access"])).code, "ENOSYS");
  assert.equal(decide({ module: "__proto__", method: "x" }, ctx()).code, "ENOSYS");
  assert.equal(decide({ module: "constructor", method: "name" }, ctx()).code, "ENOSYS");
});

test("tier 2 is refused until declared, then until granted", () => {
  const call = { module: "notification", method: "show" };
  assert.equal(decide(call, ctx()).code, "ENOTDECLARED");
  assert.equal(decide(call, ctx(["notifications"])).code, "EPERM");
  assert.equal(decide(call, ctx(["notifications"], ["notifications"])).ok, true);
});

test("a grant without a declaration does not count", () => {
  assert.equal(decide({ module: "tray", method: "set" }, ctx([], ["menu-bar"])).code, "ENOTDECLARED");
});

test("every agent run is tier 3; edit and the t3 harness need agent-edit", () => {
  assert.equal(PERMISSIONS.agent, 3, "a harness can read outside the app folder: it acts as the user");
  assert.equal(requiredPermission("agent", "run", [{ prompt: "x", harness: "claude" }]), "agent");
  assert.equal(requiredPermission("agent", "run", [{ prompt: "x", edit: true }]), "agent-edit");
  assert.equal(requiredPermission("agent", "run", [{ prompt: "x", harness: "t3" }]), "agent-edit");
  const t3 = { module: "agent", method: "run", args: [{ prompt: "x", harness: "t3" }] };
  assert.equal(decide(t3, ctx(["agent"], ["agent"])).code, "ENOTDECLARED");
  assert.equal(decide(t3, ctx(["agent", "agent-edit"], ["agent"])).code, "EPERM");
  assert.equal(decide(t3, ctx(["agent", "agent-edit"], ["agent", "agent-edit"])).tier, 3);
  assert.equal(
    decide({ module: "agent", method: "run", args: [{ prompt: "x" }] }, ctx(["agent"], ["agent"], 2)).code,
    "EPOLICY",
  );
});

test("the policy ceiling refuses higher tiers even when granted, and fails closed on NaN", () => {
  const call = { module: "fs", method: "readFile" };
  assert.equal(decide(call, ctx(["full-access"], ["full-access"], 2)).code, "EPOLICY");
  const notify = { module: "notification", method: "show" };
  assert.equal(decide(notify, ctx(["notifications"], ["notifications"], 1)).code, "EPOLICY");
  assert.equal(decide(notify, ctx(["notifications"], ["notifications"], Number.NaN)).code, "EPOLICY");
  const noCeiling = { declared: new Set(["notifications"]), granted: new Set(["notifications"]) };
  assert.equal(decide(notify, noCeiling).code, "EPOLICY", "a missing ceiling refuses");
});

test("parseMaxTier accepts 1, 2, 3 only", () => {
  assert.equal(parseMaxTier("2"), 2);
  assert.equal(parseMaxTier(3), 3);
  for (const bad of ["low", "", "0", "4", "2.5", undefined, null])
    assert.throws(() => parseMaxTier(bad), /max-tier/);
});

test("every method maps to a known permission or none", () => {
  for (const [key, permission] of Object.entries(METHODS)) {
    assert.ok(permission === null || Object.hasOwn(PERMISSIONS, permission), key);
  }
});
