// node --test tests/   (Node >= 18). Render E2E runs when Playwright is resolvable (LM_PLAYWRIGHT_DIR or cwd);
// LM_REQUIRE_RENDER=1 turns a missing Playwright into a failure (CI).
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { lint } from "../scripts/check_style.mjs";
import { install, manifest, selection, verify } from "../scripts/materialize.mjs";
import { parseArgs } from "../scripts/render.mjs";
import { resolveSafe } from "../scripts/serve.mjs";
import { buildManifest, sha256, walk } from "../scripts/sync_from_repo.mjs";

const SKILL = join(dirname(fileURLToPath(import.meta.url)), "..");
const ASSETS = join(SKILL, "assets");
const tmp = () => mkdtempSync(join(tmpdir(), "lm-skill-"));

test("vendored assets match the manifest exactly (no drift, no unlisted files)", () => {
  const m = manifest();
  const now = buildManifest(m.source);
  now.files["../DESIGN.md"] = sha256(join(SKILL, "DESIGN.md"));
  assert.deepEqual(Object.keys(now.files).sort(), Object.keys(m.files).sort());
  for (const [f, h] of Object.entries(m.files)) assert.equal(now.files[f], h, `drift: ${f}`);
  assert.match(m.source.commit, /^[0-9a-f]{7,}$/);
});

test("install copies core assets, writes a receipt, and verify passes", () => {
  const d = tmp();
  const r = install(d, { withList: ["templates"] });
  assert.ok(r.ok);
  for (const f of ["tokens/tokens.css", "css/materials.css", "kit/index.js", "kit/orb.js", "fonts/Inter-400.woff2", "templates/scene.html", "LIQUID_MIDNIGHT.json"])
    assert.ok(existsSync(join(d, "liquid-midnight", f)), f);
  assert.ok(!existsSync(join(d, "liquid-midnight", "specimen")), "optional parts only on request");
  assert.equal(verify(d).ok, true);
  rmSync(d, { recursive: true });
});

test("verify detects modified and missing files; install refuses to clobber edits unless --force", () => {
  const d = tmp();
  install(d);
  const css = join(d, "liquid-midnight/css/materials.css");
  writeFileSync(css, `${readFileSync(css, "utf8")}\n/* local edit */`);
  rmSync(join(d, "liquid-midnight/kit/loop.js"));
  const v = verify(d);
  assert.equal(v.ok, false);
  assert.deepEqual(v.modified, ["css/materials.css"]);
  assert.deepEqual(v.missing, ["kit/loop.js"]);
  assert.equal(install(d).ok, false);
  assert.equal(install(d, { force: true }).ok, true);
  assert.equal(verify(d).ok, true);
  rmSync(d, { recursive: true });
});

test("dry run writes nothing; unknown --with values are rejected", () => {
  const d = tmp();
  const r = install(d, { dryRun: true });
  assert.ok(r.copied.length > 10);
  assert.ok(!existsSync(join(d, "liquid-midnight")));
  assert.throws(() => selection(["bogus"]), /unknown --with/);
  rmSync(d, { recursive: true });
});

test("CLI: install + verify exit codes", () => {
  const d = tmp();
  const cli = join(SKILL, "scripts/materialize.mjs");
  assert.equal(spawnSync(process.execPath, [cli, "install", d]).status, 0);
  assert.equal(spawnSync(process.execPath, [cli, "verify", d]).status, 0);
  writeFileSync(join(d, "liquid-midnight/kit/core.js"), "// tampered");
  assert.equal(spawnSync(process.execPath, [cli, "verify", d]).status, 1);
  assert.equal(spawnSync(process.execPath, [cli, "nope"]).status, 2);
  rmSync(d, { recursive: true });
});

test("check_style flags the rejected looks", () => {
  const codes = (t) => lint(t).map((f) => f.code);
  assert.deepEqual(codes(".x{background:oklch(0.55 0.2 300)}"), ["LM001"]);
  assert.deepEqual(codes(".x{color:#8b5cf6}"), ["LM001"]);
  assert.deepEqual(codes("import 'arcan-glass/globals.css'"), ["LM002"]);
  assert.deepEqual(codes(".p{backdrop-filter:blur(20px)}"), ["LM003"]);
  assert.deepEqual(codes(".hero-orb{background:radial-gradient(circle,#54a5fc,transparent)}"), ["LM004"]);
  assert.deepEqual(codes("h1 em{font-style:italic}"), ["LM005"]);
});

test("check_style passes the style's own colours and honours suppressions", () => {
  const ok = [".x{color:oklch(0.71 0.15 252)}", ".x{color:oklch(0.72 0.19 350)}", ".x{color:#54a5fc}", ".x{color:#f86ab5}", ".x{color:#a6bfce}", ".g{backdrop-filter:blur(9px)} .g::after{background:conic-gradient(from var(--ua,0deg),red,blue)}"];
  for (const t of ok) assert.deepEqual(lint(t), [], t);
  assert.deepEqual(lint(".x{color:#8b5cf6} /* lm-ignore */"), []);
  assert.deepEqual(lint("- ✕ The arcan-glass look."), []);
});

test("the shipped assets, template and DESIGN.md are lint-clean", () => {
  const out = execFileSync(process.execPath, [join(SKILL, "scripts/check_style.mjs"), ASSETS, join(SKILL, "DESIGN.md"), "--json"], { encoding: "utf8" });
  assert.deepEqual(JSON.parse(out), []);
});

test("serve refuses dotfiles, traversal and malformed escapes", () => {
  const root = resolve(SKILL);
  assert.ok(resolveSafe(root, "/assets/templates/scene.html").endsWith("scene.html"));
  for (const p of ["/.git/config", "/assets/.hidden", "/../etc/passwd", "/%2e%2e/secret", "/assets/%E0%A4%A"]) assert.equal(resolveSafe(root, p), null, p);
});

test("the template only references files the install provides", () => {
  const html = readFileSync(join(ASSETS, "templates/scene.html"), "utf8");
  const refs = [...html.matchAll(/(?:href="|src="|url\(|from ")(\.\.\/[^"')]+)/g)].map((m) => m[1]);
  assert.ok(refs.length >= 6);
  for (const r of refs) assert.ok(existsSync(join(ASSETS, "templates", r)), r);
});

test("render validates its time arguments", () => {
  assert.throws(() => parseArgs(["root", "p.html", "--t", "Infinity"]), /seconds/);
  assert.throws(() => parseArgs(["root", "p.html", "--t", "-1"]), /seconds/);
  assert.deepEqual(parseArgs(["root", "p.html", "--t", "0,2", "--format", "reel"]).format, ["reel"]);
});

function playwright() {
  for (const b of [process.env.LM_PLAYWRIGHT_DIR, process.cwd()].filter(Boolean)) {
    try {
      return createRequire(join(resolve(b), "noop.js"))("playwright");
    } catch {}
  }
  return null;
}

test("render E2E: the installed template paints night and day, keynote and reel, without page errors", { timeout: 180000 }, (t) => {
  if (!playwright()) {
    if (process.env.LM_REQUIRE_RENDER === "1") assert.fail("Playwright required (LM_REQUIRE_RENDER=1) but not found");
    t.skip("Playwright not available");
    return;
  }
  const d = tmp();
  install(d, { withList: ["templates"] });
  const out = join(d, "renders");
  const r = spawnSync(process.execPath, [join(SKILL, "scripts/render.mjs"), join(d, "liquid-midnight"), "templates/scene.html", "--t", "3", "--format", "keynote,reel", "--mode", "night,day", "--out", out], { encoding: "utf8", env: process.env });
  assert.equal(r.status, 0, r.stderr + r.stdout);
  for (const f of ["keynote-night", "keynote-day", "reel-night", "reel-day"]) {
    const png = join(out, `templates-scene-${f}-t3.png`);
    assert.ok(existsSync(png), png);
    assert.ok(readFileSync(png).length > 50000, `${f} render looks empty`);
  }
  rmSync(d, { recursive: true });
});

test("manifest and receipts store hashes as {path, sha256} lists (no token-keyed hex that trips secret scanners)", () => {
  const raw = JSON.parse(readFileSync(join(ASSETS, "manifest.json"), "utf8"));
  assert.ok(Array.isArray(raw.files) && raw.files.every((e) => typeof e.path === "string" && /^[0-9a-f]{64}$/.test(e.sha256)));
  const d = tmp();
  install(d);
  const rec = JSON.parse(readFileSync(join(d, "liquid-midnight/LIQUID_MIDNIGHT.json"), "utf8"));
  assert.ok(Array.isArray(rec.files));
  assert.ok(!/"[^"]*token[^"]*":\s*"[0-9a-f]{20,}"/i.test(JSON.stringify(rec, null, 2)));
  rmSync(d, { recursive: true });
});
