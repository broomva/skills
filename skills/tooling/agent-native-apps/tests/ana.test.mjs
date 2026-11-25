import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  checkApp,
  doctor,
  lintHtml,
  main,
  parseCli,
  parseVersion,
  scaffold,
  scaffoldManifest,
  UsageError,
  versionAtLeast,
} from "../scripts/ana.mjs";

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function tmp(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ana-test-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test("parseCli reads --name value, --name=value and boolean flags", () => {
  const { flags, positional } = parseCli(["new", "./x", "--name", "My App", "--harness=t3", "--json"]);
  assert.deepEqual(flags, { name: "My App", harness: "t3", json: true });
  assert.deepEqual(positional, ["new", "./x"]);
  assert.throws(() => parseCli(["--name"]), UsageError);
  assert.throws(() => parseCli(["--json=1"]), UsageError);
});

test("version comparison", () => {
  assert.deepEqual(parseVersion("v45.5.0-beta.1"), [45, 5, 0]);
  assert.equal(parseVersion("latest"), null);
  assert.ok(versionAtLeast([45, 3, 0], [45, 3, 0]));
  assert.ok(versionAtLeast([46, 0, 0], [45, 3, 0]));
  assert.ok(!versionAtLeast([45, 2, 9], [45, 3, 0]));
  assert.ok(!versionAtLeast([44, 99, 0], [45, 3, 0]));
});

test("a t3 scaffold declares agent-edit; a scaffold the host would refuse is a usage error", () => {
  assert.deepEqual(scaffoldManifest({ name: "Pad" }), {
    name: "Pad",
    permissions: ["agent", "agent-edit"],
    agent: { harness: "t3" },
  });
  assert.deepEqual(scaffoldManifest({ name: "Pad", harness: "claude" }).permissions, ["agent"]);
  assert.throws(() => scaffoldManifest({ name: "Pad", harness: "gpt" }), UsageError);
  assert.throws(() => scaffoldManifest({ name: "<bad>" }), UsageError);
  assert.throws(() => scaffoldManifest({ name: "Pad", permissions: ["root"] }), UsageError);
  assert.throws(() => scaffoldManifest({ name: "Pad", harness: "t3", permissions: ["agent"] }), /agent-edit/);
  assert.throws(() => scaffoldManifest({ name: "Pad", harness: "t3", provider: "claudeAgent" }), /needs a model/);
});

test("lintHtml reports what the CSP will block and nothing else", () => {
  const clean = '<link rel="stylesheet" href="style.css"><script src="app.js"></script><img src="logo.png">';
  assert.deepEqual(lintHtml("index.html", clean), []);
  const bad = [
    "<script>alert(1)</script>",
    '<script src="https://cdn.example.com/x.js"></script>',
    '<script src="//cdn.example.com/x.js"></script>',
    '<link rel="stylesheet" href="https://fonts.example.com/a.css">',
    '<img src="http://example.com/a.png">',
    '<iframe src="x.html"></iframe>',
    '<button onclick="go()">x</button>',
  ];
  for (const html of bad) assert.equal(lintHtml("index.html", html).length, 1, html);
});

test("the scaffold is a valid app, and check agrees with the host's own rules", (t) => {
  const dir = path.join(tmp(t), "my-app");
  const manifest = scaffold(dir, { name: "My App", harness: "t3" });
  assert.equal(manifest.name, "My App");
  assert.ok(fs.readFileSync(path.join(dir, "index.html"), "utf8").includes("<title>My App</title>"));
  const result = checkApp(dir);
  assert.deepEqual(result.problems, []);
  assert.equal(result.ok, true);
  assert.equal(result.version.length, 32);
  assert.deepEqual(result.files, ["app.js", "app.json", "index.html", "style.css"]);
  assert.throws(() => scaffold(dir, { name: "Again" }), /not empty/);
});

test("check fails on symlinks, inline scripts, a missing index.html and a t3 app without agent-edit", (t) => {
  const dir = path.join(tmp(t), "app");
  scaffold(dir, { name: "App", harness: "claude" });
  fs.symlinkSync("/etc/hosts", path.join(dir, "hosts"));
  assert.match(checkApp(dir).problems[0].problem, /symlink/);
  fs.unlinkSync(path.join(dir, "hosts"));

  fs.appendFileSync(path.join(dir, "index.html"), "<script>evil()</script>");
  assert.match(checkApp(dir).problems[0].problem, /inline <script>/);

  const t3 = path.join(tmp(t), "t3");
  scaffold(t3, { name: "T", harness: "claude" });
  fs.writeFileSync(path.join(t3, "app.json"), JSON.stringify({ name: "T", permissions: ["agent"], agent: { harness: "t3" } }));
  assert.ok(checkApp(t3).problems.some((p) => /agent-edit/.test(p.problem)));

  fs.rmSync(path.join(t3, "index.html"));
  assert.ok(checkApp(t3).problems.some((p) => /no index.html/.test(p.problem)));
});

test("check warns that node_modules is not served, and about tier 3", (t) => {
  const dir = path.join(tmp(t), "app");
  scaffold(dir, { name: "App" });
  fs.mkdirSync(path.join(dir, "node_modules"));
  const result = checkApp(dir);
  assert.equal(result.ok, true);
  assert.ok(result.warnings.some((w) => /node_modules/.test(w)));
  assert.ok(result.warnings.some((w) => /tier 3/.test(w)));
});

test("doctor reports a missing kit as a required failure with a fix", (t) => {
  const report = doctor(path.join(tmp(t), "no-kit"));
  const kit = report.checks.find((c) => c.name === "host kit");
  assert.equal(kit.ok, false);
  assert.equal(kit.fix, "Run: ana setup");
  assert.equal(report.ok, false);
});

test("the CLI: new, then check, exit codes", async (t) => {
  const dir = path.join(tmp(t), "cli-app");
  const silent = t.mock.method(console, "log", () => {});
  assert.equal(await main(["new", dir, "--name", "CLI App", "--harness", "codex"]), 0);
  assert.equal(await main(["check", dir]), 0);
  fs.rmSync(path.join(dir, "index.html"));
  assert.equal(await main(["check", dir, "--json"]), 1);
  await assert.rejects(() => main(["frobnicate"]), UsageError);
  await assert.rejects(() => main(["new", dir]), UsageError);
  silent.mock.restore();
});

test("every file SKILL.md tells an agent to run or read exists", () => {
  const text = fs.readFileSync(path.join(SKILL, "SKILL.md"), "utf8");
  const refs = [...text.matchAll(/(?<![\w./-])((?:scripts|assets|references)\/[\w./-]+\.[a-z]+)/g)].map((m) => m[1]);
  assert.ok(refs.length > 3);
  for (const ref of new Set(refs)) assert.ok(fs.existsSync(path.join(SKILL, ref)), `${ref} is referenced but missing`);
});
