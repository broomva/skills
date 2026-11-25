import assert from "node:assert/strict";
import { test } from "node:test";
import { ArgsError, checkForwardedConfig, hostConfig, parseArgs, resolveCommand } from "../src/args.js";

test("flags take --name=value; launch noise is skipped", () => {
  const { flags, positional } = parseArgs([
    "install",
    "./app",
    "--home=/h",
    "--max-tier=2",
    "--selftest",
    "-psn_0_12345",
    "-AppleLanguages",
    "(en)",
  ]);
  assert.deepEqual(flags, { home: "/h", "max-tier": "2", selftest: true });
  assert.deepEqual(positional, ["install", "./app"]);
});

test("space-separated or unknown flags are errors, not silent booleans", () => {
  assert.throws(() => parseArgs(["--home", "/tmp/x"]), ArgsError);
  assert.throws(() => parseArgs(["--home="]), ArgsError);
  assert.throws(() => parseArgs(["--selftest=yes"]), ArgsError);
  assert.throws(() => parseArgs(["--evil=1"]), /Unknown flag/);
});

test("hostConfig validates the ceiling and resolves paths", () => {
  const c = hostConfig({ home: "/h", "max-tier": "2" }, { defaultHome: "/d", defaultAppsDir: "/a" });
  assert.deepEqual(c, { home: "/h", appsDir: "/a", maxTier: 2, selftest: false });
  assert.throws(
    () => hostConfig({ "max-tier": "low" }, { defaultHome: "/d", defaultAppsDir: "/a" }),
    /max-tier/,
  );
});

test("install paths are made absolute against the caller's cwd before forwarding", () => {
  assert.deepEqual(resolveCommand(["install", "my-app"], "/work"), ["install", "/work/my-app"]);
  assert.deepEqual(resolveCommand([], "/work"), ["serve"]);
  assert.throws(() => resolveCommand(["uninstall"], "/work"), /needs an app id/);
  assert.throws(() => resolveCommand(["rm", "-rf"], "/work"), /Unknown command/);
});

test("checkForwardedConfig refuses stricter --max-tier or different --apps-dir on a running host", () => {
  const running = { maxTier: 3, appsDir: "/Apps" };
  assert.equal(checkForwardedConfig(running, { maxTier: 1 }).ok, false);
  assert.equal(checkForwardedConfig(running, { maxTier: 3 }).ok, true);
  assert.equal(checkForwardedConfig(running, { appsDir: "/Other" }).ok, false);
  assert.equal(checkForwardedConfig(running, { appsDir: "/Apps" }).ok, true);
  assert.equal(checkForwardedConfig(running, {}).ok, true);
});
