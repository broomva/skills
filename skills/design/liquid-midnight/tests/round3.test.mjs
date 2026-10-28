// Regression tests for the P20 round-3 findings (starters, linter coverage, CLI arguments, server safety, template).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { lint } from "../scripts/check_style.mjs";
import { install, verify } from "../scripts/materialize.mjs";
import { startServer } from "../scripts/serve.mjs";
import { request } from "node:http";

/* fetch() cannot override Host (undici treats it as forbidden), so send raw requests for that case */
const raw = (port, path, headers) =>
  new Promise((ok, bad) => {
    const r = request({ host: "127.0.0.1", port, path, headers }, (res) => {
      res.resume();
      ok(res.statusCode);
    });
    r.on("error", bad);
    r.end();
  });

const SKILL = join(dirname(fileURLToPath(import.meta.url)), "..");
const ASSETS = join(SKILL, "assets");
const tmp = () => mkdtempSync(join(tmpdir(), "lm-skill-r3-"));
const codes = (t) => lint(t).map((f) => f.code);

test("templates are starters: edit in place, verify stays green, re-install keeps them unless --force", () => {
  const d = tmp();
  install(d, { withList: ["templates"] });
  const scene = join(d, "liquid-midnight/templates/scene.html");
  writeFileSync(scene, readFileSync(scene, "utf8").replace("Primer", "My scene"));
  assert.equal(verify(d).ok, true, "editing a starter does not fail verify");
  const again = install(d, { withList: ["templates"] });
  assert.ok(again.ok);
  assert.deepEqual(again.kept, ["templates/scene.html"]);
  assert.match(readFileSync(scene, "utf8"), /My scene/);
  install(d);
  assert.equal(verify(d).ok, true, "a later install without --with keeps the receipt valid");
  assert.ok(JSON.parse(readFileSync(join(d, "liquid-midnight/LIQUID_MIDNIGHT.json"), "utf8")).starters.includes("templates/scene.html"));
  install(d, { withList: ["templates"], force: true });
  assert.doesNotMatch(readFileSync(scene, "utf8"), /My scene/);
  rmSync(d, { recursive: true });
});

test("LM001 catches purple in Tailwind, hsl, rgb, named colours and 4/8-digit hex", () => {
  for (const t of [
    '<div class="bg-gradient-to-r from-purple-600 to-violet-900">',
    ".x{color:hsl(275 70% 45%)}",
    ".x{color:rgb(124,58,237)}",
    ".x{background:rebeccapurple}",
    ".x{color:#7c3aedcc}",
    ".x{color:#83fc}",
  ])
    assert.ok(codes(t).includes("LM001"), t);
});

test("LM004 catches inline and canvas glow orbs, not orbits or kit users", () => {
  assert.ok(codes('<div class="orb" style="background:radial-gradient(circle,#54a5fc,transparent)">').includes("LM004"));
  assert.ok(codes("const g = ctx.createRadialGradient(0,0,0,0,0,9); // orb glow").includes("LM004"));
  assert.deepEqual(lint(".orbit-ring{background:radial-gradient(circle,#54a5fc,transparent)}"), []);
  assert.deepEqual(lint("import { orb, ORB } from '../kit/index.js'; ctx.createRadialGradient(0,0,0,0,0,9);"), []);
});

test("ID selectors are not colours", () => {
  assert.deepEqual(lint("#a0f-section{padding:4px} #a3f{margin:0} #a3f, #b4e {color:#54a5fc}"), []);
  assert.ok(codes(".x{color:#a3f}").includes("LM001"), "the same hex as a value is a purple");
  assert.deepEqual(lint('<a href="#a3f">jump</a> <use xlink:href="#a3f"/> <label for="#a3f">'), [], "fragment references are not colours");
});

test("CLI: --with without a value fails cleanly; list hides internal entries", () => {
  const cli = join(SKILL, "scripts/materialize.mjs");
  const d = tmp();
  const r = spawnSync(process.execPath, [cli, "install", d, "--with"], { encoding: "utf8" });
  assert.equal(r.status, 2);
  assert.match(r.stderr, /--with needs a value/);
  assert.doesNotMatch(spawnSync(process.execPath, [cli, "list"], { encoding: "utf8" }).stdout, /\.\.\/DESIGN/);
  rmSync(d, { recursive: true });
});

test("serve refuses foreign Host headers, non-GET methods and symlink escapes", async () => {
  const d = tmp();
  mkdirSync(join(d, "site"));
  writeFileSync(join(d, "site/index.html"), "ok");
  writeFileSync(join(d, "secret.txt"), "secret");
  symlinkSync(join(d, "secret.txt"), join(d, "site/link.txt"));
  const s = await startServer(join(d, "site"), 0);
  try {
    const base = `http://127.0.0.1:${s.port}`;
    assert.equal((await fetch(`${base}/`)).status, 200);
    assert.equal((await fetch(`${base}/link.txt`)).status, 404);
    assert.equal(await raw(s.port, "/", { host: "evil.example" }), 404);
    assert.equal(await raw(s.port, "/", { host: `localhost:${s.port}` }), 200);
    assert.equal((await fetch(`${base}/`, { method: "POST" })).status, 404);
  } finally {
    s.stop();
    rmSync(d, { recursive: true });
  }
});

test("render reports a wrong page path instead of a bare timeout", () => {
  const d = tmp();
  writeFileSync(join(d, "index.html"), "<p>no renderAt here</p>");
  const r = spawnSync(process.execPath, [join(SKILL, "scripts/render.mjs"), d, "missing.html", "--t", "0", "--mode", "night", "--out", join(d, "o")], {
    encoding: "utf8",
    env: { ...process.env, LM_PLAYWRIGHT_DIR: process.env.LM_PLAYWRIGHT_DIR ?? "" },
    timeout: 60000,
  });
  if (r.status === 3) return; // Playwright not available here; covered in CI by LM_REQUIRE_RENDER
  assert.equal(r.status, 1);
  assert.match(r.stderr, /HTTP 404/);
  rmSync(d, { recursive: true });
});

test("the template ships the metal icon gradients and pins motion in capture", () => {
  const html = readFileSync(join(ASSETS, "templates/scene.html"), "utf8");
  assert.match(html, /id="lm-metal"/);
  assert.match(html, /id="lm-metal-day"/);
  assert.match(html, /setMotion\(Q\.get\("motion"\) !== "0"\)/);
});

test("round 4: gradient and shadow purples are values, not selectors", () => {
  assert.ok(codes(".x{background:linear-gradient(#7c3aed, #0b1020)}").includes("LM001"));
  assert.ok(codes(".x{box-shadow:0 0 8px #a855f7, 0 0 2px #000}").includes("LM001"));
  assert.deepEqual(lint("@media (min-width:1px){ #a3f, #b4e { color:#54a5fc } }"), [], "ID selectors inside @media");
});

test("round 4: LM004 stays linear on long prose", () => {
  const prose = "The orb is a WebGL sphere. ".repeat(2000);
  const t0 = performance.now();
  lint(prose);
  assert.ok(performance.now() - t0 < 1000, "lint of ~50 KB prose stays well under a second");
});

test("round 4: re-install keeps optional sets installed earlier", () => {
  const d = tmp();
  install(d, { withList: ["specimen"] });
  const sp = join(d, "liquid-midnight/specimen/index.html");
  writeFileSync(sp, `${readFileSync(sp, "utf8")}<!-- edit -->`);
  assert.equal(install(d).ok, false, "the edited specimen is still tracked, so an update refuses to clobber it");
  assert.deepEqual(verify(d).modified, ["specimen/index.html"]);
  rmSync(d, { recursive: true });
});

test("round 4: serve and render fail cleanly on a bad root", async () => {
  await assert.rejects(() => startServer("/nonexistent-lm-root", 0), /not a readable directory/);
  const r = spawnSync(process.execPath, [join(SKILL, "scripts/serve.mjs"), "/nonexistent-lm-root", "0"], { encoding: "utf8", timeout: 10000 });
  assert.equal(r.status, 2);
  assert.match(r.stderr, /not a readable directory/);
  assert.doesNotMatch(r.stderr, /at .*\(/, "no stack trace");
});
