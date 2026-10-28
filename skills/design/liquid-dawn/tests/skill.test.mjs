// Tests for the liquid-dawn skill: node --test tests/*.test.mjs
// The render E2E needs Playwright (LD_PLAYWRIGHT_DIR or the cwd). It skips without it unless LD_REQUIRE_RENDER=1,
// which CI sets, so a missing browser is a failure there rather than a false green.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readdirSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { colorVars, contrast, oklchToHex, parseOklch } from "../scripts/build_tokens.mjs";
import { loadPlaywright, parseArgs, render } from "../scripts/render.mjs";
import { resolveInside } from "../scripts/serve.mjs";

const SKILL = join(dirname(fileURLToPath(import.meta.url)), "..");
const KIT = join(SKILL, "assets/kit");
const tokens = JSON.parse(readFileSync(join(SKILL, "assets/tokens/tokens.json"), "utf8"));
const fields = await import(join(KIT, "fields.js"));
const shoal = await import(join(KIT, "shoal.js"));
const page = await import(join(KIT, "page.js"));

// ── frontmatter and release metadata ──
test("SKILL.md frontmatter names the directory and its version has a CHANGELOG section", () => {
  const md = readFileSync(join(SKILL, "SKILL.md"), "utf8");
  const fm = md.split("---")[1];
  assert.match(fm, /^name: liquid-dawn$/m);
  assert.match(fm, /^category: design$/m);
  const v = /version: "([^"]+)"/.exec(fm)[1];
  assert.match(readFileSync(join(SKILL, "CHANGELOG.md"), "utf8"), new RegExp(`## \\[${v.replaceAll(".", "\\.")}\\]`));
  assert.equal(tokens.version, v);
});

// ── tokens ──
test("tokens.css is generated from tokens.json and up to date", () => {
  execFileSync(process.execPath, [join(SKILL, "scripts/build_tokens.mjs"), "--check"], { stdio: "pipe" });
});

test("oklch → hex conversion is right on known colours", () => {
  assert.equal(oklchToHex("oklch(1 0 0)"), "#ffffff");
  assert.equal(oklchToHex("oklch(0 0 0)"), "#000000");
  assert.equal(oklchToHex("oklch(1 0 0 / 0.5)"), "#ffffff80");
  assert.throws(() => parseOklch("#fff"));
});

test("every text token passes 4.5:1 on paper and surface, in both modes", () => {
  for (const mode of ["dawn", "dusk"])
    for (const bg of ["paper", "surface"])
      for (const fg of ["ink", "ink2", "ink3", "tide"]) {
        const r = contrast(tokens.color[fg][mode], tokens.color[bg][mode]);
        assert.ok(r >= 4.5, `${fg} on ${bg} (${mode}) is ${r.toFixed(2)}:1`);
      }
});

test("DESIGN.md's contrast table matches the measured ratios", () => {
  const md = readFileSync(join(SKILL, "DESIGN.md"), "utf8");
  for (const fg of ["ink", "ink2", "ink3", "tide"]) {
    const row = new RegExp(`^\\| ${fg} \\| ([\\d.]+) \\| ([\\d.]+) \\| ([\\d.]+) \\| ([\\d.]+) \\|$`, "m").exec(md);
    assert.ok(row, `no contrast row for ${fg}`);
    const want = [
      ["dawn", "paper"],
      ["dawn", "surface"],
      ["dusk", "paper"],
      ["dusk", "surface"],
    ].map(([m, bg]) => contrast(tokens.color[fg][m], tokens.color[bg][m]));
    want.forEach((w, i) => assert.ok(Math.abs(w - Number(row[i + 1])) < 0.06, `${fg} col ${i}: doc ${row[i + 1]} vs measured ${w.toFixed(2)}`));
  }
});

test("no purple or magenta anywhere in the palette (hue 280-345 with real chroma)", () => {
  for (const [name, v] of colorVars(tokens))
    for (const mode of ["dawn", "dusk"]) {
      const { C, H } = parseOklch(v[mode]);
      assert.ok(!(C > 0.03 && H >= 280 && H <= 345), `${name} (${mode}) is purple/magenta: ${v[mode]}`);
    }
});

// ── fields: calm is a number ──
const sample = (f, w = 1440, h = 900, step = 15) => {
  const a = [];
  for (let y = 0; y < h; y += step) for (let x = 0; x < w; x += step) a.push(f(x, y));
  return a;
};

test("fields are pure, bounded by CAP and deterministic", () => {
  const r1 = fields.rippleField({ w: 400, h: 300, seed: 3 });
  const r2 = fields.rippleField({ w: 400, h: 300, seed: 3 });
  for (const t of [0, 3.7, 12]) {
    for (const [x, y] of [
      [10, 20],
      [333, 41],
      [900, 700],
    ]) {
      assert.equal(fields.tide(x, y, t), fields.tide(x, y, t));
      assert.equal(fields.cloud(x, y, t), fields.cloud(x, y, t));
      assert.deepEqual(fields.breeze(x, y, t), fields.breeze(x, y, t));
      assert.equal(r1(x, y, t), r2(x, y, t));
    }
    for (const f of [(x, y) => fields.tide(x, y, t), (x, y) => fields.cloud(x, y, t), (x, y) => fields.breeze(x, y, t).v, (x, y) => r1(x, y, t)])
      for (const v of sample(f, 600, 400, 20)) assert.ok(v >= 0 && v <= fields.CAP + 1e-12, `out of range ${v}`);
  }
});

test("no per-frame randomness in the kit (Math.random, Date.now, performance.now outside the live loop)", () => {
  for (const f of readdirSync(KIT).filter((f) => f.endsWith(".js"))) {
    const src = readFileSync(join(KIT, f), "utf8");
    assert.doesNotMatch(src, /Math\.random|Date\.now/, `${f} uses wall-clock or unseeded randomness`);
    if (f !== "loop.js") assert.doesNotMatch(src, /performance\.now/, `${f} reads the wall clock`);
  }
});

test("default field speeds stay at or under FIELD_SPEED_MAX", () => {
  const src = readFileSync(join(KIT, "fields.js"), "utf8");
  for (const m of src.matchAll(/speed = ([\d.]+)/g)) assert.ok(Number(m[1]) <= fields.FIELD_SPEED_MAX, `default speed ${m[1]}`);
});

test("tide is neither empty nor a uniform texture: it has quiet water and busy shallows", () => {
  const a = sample((x, y) => fields.tide(x, y, 6));
  const lit = a.filter((v) => v > 0.02).length / a.length;
  assert.ok(lit > 0.15 && lit < 0.75, `lit fraction ${lit.toFixed(2)}`);
  // compare 8 vertical bands: a uniform texture has near-equal band means
  const bands = Array.from({ length: 8 }, (_, i) => sample((x, y) => fields.tide(x + i * 180, y, 6), 180, 900, 15));
  const means = bands.map((b) => b.reduce((s, v) => s + v, 0) / b.length);
  assert.ok(Math.max(...means) > 2 * Math.min(...means), `band means too even: ${means.map((m) => m.toFixed(3))}`);
});

test("tide does not tile at its own scale (the 2π period is broken by the warp)", () => {
  let same = 0;
  const pts = sample((x, y) => [x, y], 520, 520, 26);
  for (const [x, y] of pts) if (Math.abs(fields.tide(x, y, 6) - fields.tide(x + 520, y, 6)) < 1e-6) same++;
  assert.ok(same / pts.length < 0.6, `tide repeats at x+scale: ${same}/${pts.length}`);
});

test("ripple rings reach the heavy dot and the lattice stays faint between rings", () => {
  const r = fields.rippleField({ w: 294, h: 338, n: 3, seed: 13 });
  const a = sample((x, y) => r(x, y, 6), 294, 338, 4);
  const heavy = a.filter((v) => fields.rampIndex(v, 3) === 2).length / a.length;
  assert.ok(heavy > 0.01 && heavy < 0.3, `heavy-dot fraction ${heavy.toFixed(3)}`);
});

test("clearing is 0 at the centre and 1 far away", () => {
  assert.equal(fields.clearing(500, 400, 500, 400, 200, 100), 0);
  assert.equal(fields.clearing(1500, 400, 500, 400, 200, 100), 1);
});

test("refract: null outside, magnifies about the centre, bends at the rim", () => {
  const L = { x: 100, y: 100, w: 400, h: 100, r: 20 };
  assert.equal(fields.refract(50, 50, L), null);
  const c = fields.refract(300, 150, L);
  assert.ok(Math.abs(c.sx - 300) < 1e-9 && Math.abs(c.sy - 150) < 1e-9 && c.edge === 0);
  const rim = fields.refract(300, 101, L);
  assert.ok(rim.edge > 0.9, `edge ${rim.edge}`);
  assert.ok(rim.sy < 101, "the bevel bends the field outward (upward at the top rim)");
  const mid = fields.refract(200, 150, L);
  assert.ok(mid.sx > 200, "the body magnifies: a point left of centre samples closer to the centre");
});

test("rampIndex leaves faint cells empty and never reaches past the ramp", () => {
  assert.equal(fields.rampIndex(0.01, 6), -1);
  assert.equal(fields.rampIndex(Number.NaN, 6), -1);
  assert.equal(fields.rampIndex(0.7, 6), 4);
  assert.equal(fields.rampIndex(5, 6), 5);
});

test("bladeGlyph follows the lean", () => {
  assert.equal(fields.bladeGlyph(0.6, 0.6), "/");
  assert.equal(fields.bladeGlyph(0.6, -0.3), "\\");
  assert.equal(fields.bladeGlyph(0.6, 0), "|");
  assert.equal(fields.bladeGlyph(0.02, 0), "");
});

// ── shoals ──
const colors = Object.fromEntries(["stone", "sky", "lagoon", "moss", "sand", "coral", "surface", "sunk", "ink", "ink3"].map((k) => [k, k]));

test("shoals are deterministic, lattice-snapped, schooling, with exactly one coral creature", () => {
  const a = shoal.createShoal({ w: 1440, h: 900, seed: 21, count: 9, colors });
  const b = shoal.createShoal({ w: 1440, h: 900, seed: 21, count: 9, colors });
  assert.deepEqual(a.at(5.5), b.at(5.5));
  for (const c of a.at(5.5)) {
    assert.ok(c.x % 12 === 0 && c.y % 12 === 0, `off-lattice tile at ${c.x},${c.y}`); // === so -0 counts
  }
  assert.equal(a.list.filter((k) => k.tone === "coral").length, 1);
  assert.ok(a.list.length > 9, "minnows spawn followers");
  const none = shoal.createShoal({ w: 1440, h: 900, seed: 21, count: 9, colors, coral: false });
  assert.equal(none.list.filter((k) => k.tone === "coral").length, 0);
  assert.notDeepEqual(a.at(0), a.at(10), "creatures move");
});

test("creatures drift calmly: no creature moves more than 25 px/s", () => {
  const s = shoal.createShoal({ w: 1440, h: 900, seed: 9, count: 12, colors });
  for (const k of s.list) assert.ok(Math.abs(k.speed) <= 25, `speed ${k.speed}`);
});

test("islands are deterministic and drift", () => {
  const i = shoal.createIslands({ w: 1440, h: 900, seed: 8, colors });
  assert.deepEqual(i.at(3), shoal.createIslands({ w: 1440, h: 900, seed: 8, colors }).at(3));
  assert.notDeepEqual(i.at(0), i.at(20));
});

// ── type as a field ──
test("pebbleWarp is still before the drop and after its life, and moves in between", () => {
  assert.deepEqual(page.pebbleWarp(50, -1), [0, 0]);
  assert.ok(Math.abs(page.pebbleWarp(50, 9)[0]) < 1e-9);
  const moving = [10, 30, 60, 90].some((d) => Math.abs(page.pebbleWarp(d, 1.5)[0]) > 1);
  assert.ok(moving);
});

test("wellWarp empties the core and pushes the rest outward", () => {
  assert.equal(page.wellWarp(20, { rs: 60 }), null);
  const [d] = page.wellWarp(120, { rs: 60 });
  assert.equal(d, 150);
});

test("freeSpans splits a row round an obstacle and drops slivers", () => {
  assert.deepEqual(page.freeSpans(0, 1000, 0, 20, []), [[0, 1000]]);
  const s = page.freeSpans(0, 1000, 90, 20, [{ x: 500, y: 100, r: 50 }]);
  assert.deepEqual(s, [
    [0, 450],
    [550, 1000],
  ]);
  assert.deepEqual(page.freeSpans(0, 1000, 300, 20, [{ x: 500, y: 100, r: 50 }]), [[0, 1000]]);
  assert.deepEqual(page.freeSpans(0, 1000, 90, 20, [{ x: 20, y: 100, r: 50 }]), [[70, 1000]]);
});

test("pretext is vendored with its licence and exposes the calls the kit uses", async () => {
  const src = readFileSync(join(KIT, "vendor/pretext.js"), "utf8");
  assert.match(src.slice(0, 300), /@chenglou\/pretext 1\.0\.0 \(MIT/);
  assert.match(readFileSync(join(KIT, "vendor/pretext.LICENSE"), "utf8"), /MIT License/);
  const pt = await import(join(KIT, "vendor/pretext.js"));
  for (const k of ["prepareWithSegments", "layoutWithLines", "layoutNextLineRange", "materializeLineRange"]) assert.equal(typeof pt[k], "function", k);
});

// ── scripts ──
test("serve resolves only files inside the root", () => {
  const root = mkdtempSync(join(tmpdir(), "ld-serve-"));
  writeFileSync(join(root, "a.html"), "x");
  writeFileSync(join(root, ".env"), "secret");
  const outside = mkdtempSync(join(tmpdir(), "ld-out-"));
  writeFileSync(join(outside, "s.txt"), "s");
  symlinkSync(join(outside, "s.txt"), join(root, "link.txt"));
  assert.ok(resolveInside(root, "/a.html"));
  assert.equal(resolveInside(root, "/.env"), null);
  assert.equal(resolveInside(root, "/../../etc/passwd"), null);
  assert.equal(resolveInside(root, "/%2e%2e/%2e%2e/etc/passwd"), null);
  assert.equal(resolveInside(root, "/link.txt"), null);
  assert.equal(resolveInside(root, "/%E0%A4%A"), null);
});

test("render parseArgs validates its options", () => {
  const o = parseArgs(["assets", "specimen/index.html", "--t", "0,6", "--mode", "dusk"]);
  assert.deepEqual(o.t, ["0", "6"]);
  assert.deepEqual(o.mode, ["dusk"]);
  assert.throws(() => parseArgs(["assets"]));
  assert.throws(() => parseArgs(["a", "b", "--mode", "night"]), /dawn or dusk/);
  assert.throws(() => parseArgs(["a", "b", "--t", "x"]), /not a time/);
  assert.throws(() => parseArgs(["a", "b", "--bogus", "1"]), /unknown option/);
  assert.throws(() => parseArgs(["a", "b", "--t"]), /needs a value/);
});

// ── render E2E ──
const pw = loadPlaywright();
const required = process.env.LD_REQUIRE_RENDER === "1";
test("specimen renders in both modes, deterministically, and moves over time", { skip: !pw && !required && "Playwright not installed" }, async () => {
  assert.ok(pw, "LD_REQUIRE_RENDER=1 but Playwright is missing");
  const out = mkdtempSync(join(tmpdir(), "ld-render-"));
  const opts = { root: join(SKILL, "assets"), page: "specimen/index.html", width: "1440", shots: "hero,pages" };
  const a = await render({ ...opts, t: ["6"], mode: ["dawn", "dusk"], out: join(out, "a") });
  const b = await render({ ...opts, t: ["6"], mode: ["dawn"], out: join(out, "b") });
  const c = await render({ ...opts, t: ["0"], mode: ["dawn"], out: join(out, "c") });
  assert.equal(a.length, 4);
  const h = (f) => createHash("sha256").update(readFileSync(f)).digest("hex");
  const pick = (list, s) => list.find((f) => f.endsWith(s));
  assert.equal(h(pick(a, "dawn-t6-hero.png")), h(pick(b, "dawn-t6-hero.png")), "same t, same pixels");
  assert.notEqual(h(pick(a, "dawn-t6-hero.png")), h(pick(c, "dawn-t0-hero.png")), "the hero moves between t=0 and t=6");
  assert.notEqual(h(pick(a, "dawn-t6-hero.png")), h(pick(a, "dusk-t6-hero.png")), "dusk differs from dawn");
});
