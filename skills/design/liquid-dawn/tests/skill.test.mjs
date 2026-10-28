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

// ── type themes ──
test("every type theme is complete, emitted in tokens.css, and its faces are vendored with an OFL licence", () => {
  const css = readFileSync(join(SKILL, "assets/tokens/tokens.css"), "utf8");
  const materials = readFileSync(join(SKILL, "assets/css/materials.css"), "utf8");
  assert.ok(tokens.typeThemes[tokens.typeDefault], "the default theme exists");
  for (const [name, th] of Object.entries(tokens.typeThemes)) {
    for (const k of ["display", "text", "mono", "displayWeight", "displayTracking"]) assert.ok(th[k] !== undefined, `${name}.${k}`);
    for (const k of ["font", "weight", "style", "scale"]) assert.ok(th.em[k] !== undefined, `${name}.em.${k}`);
    assert.notEqual(th.em.font, "inherit", "a custom property set to `inherit` inherits the property, not a value");
    assert.match(css, new RegExp(`\\[data-ld-type="${name}"\\]`));
    // every family the theme names first must have an @font-face whose file exists
    for (const fam of [th.display, th.text, th.mono, th.em.font.startsWith("var(") ? th.display : th.em.font].map((f) => f.split(",")[0].replace(/"/g, "").trim())) {
      const faces = [...materials.matchAll(/@font-face\s*\{[^}]*font-family:\s*"?([^";]+)"?;[^}]*url\("\.\.\/fonts\/([^"]+)"\)/g)].filter((m) => m[1] === fam);
      assert.ok(faces.length, `no @font-face for ${fam} (${name})`);
      for (const m of faces) assert.ok(readFileSync(join(SKILL, "assets/fonts", m[2])).length > 1000, `${m[2]} missing`);
    }
  }
  for (const f of readdirSync(join(SKILL, "assets/fonts")).filter((f) => f.endsWith(".woff2"))) {
    const family = f.replace(/-(wght|400|400-italic)\.woff2$/, "");
    assert.ok(readdirSync(join(SKILL, "assets/fonts")).includes(`${family}-OFL.txt`), `${f} has no ${family}-OFL.txt`);
    assert.match(readFileSync(join(SKILL, "assets/fonts", `${family}-OFL.txt`), "utf8"), /SIL Open Font License/);
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

test("tide: speed is its only time scale, and the default fastest term is under FIELD_SPEED_MAX", () => {
  // the default equals an explicit .18 …
  for (const [x, y, t] of [[10, 20, 3], [700, 400, 11.5]]) assert.equal(fields.tide(x, y, t), fields.tide(x, y, t, { speed: 0.18 }));
  assert.ok(0.18 <= fields.FIELD_SPEED_MAX);
  // … the clock divisor is the fastest iteration factor (2.5 for n = 0) …
  assert.equal(Math.max(...fields.TIDE_FACTORS), 2.5);
  // … and time enters only through speed·t, so halving speed is the same field at twice the time
  for (const [x, y, t] of [[10, 20, 3], [700, 400, 11.5], [1300, 800, 40]])
    assert.ok(Math.abs(fields.tide(x, y, t, { speed: 0.09 }) - fields.tide(x, y, t / 2)) < 1e-9);
});

test("breeze gusts travel at most 40 px/s (measured by cross-correlating the smoothed lean profile 2 s apart)", () => {
  const corr = (a, b) => {
    const n = a.length;
    const ma = a.reduce((s, v) => s + v, 0) / n;
    const mb = b.reduce((s, v) => s + v, 0) / n;
    let c = 0;
    let va = 0;
    let vb = 0;
    for (let i = 0; i < n; i++) {
      c += (a[i] - ma) * (b[i] - mb);
      va += (a[i] - ma) ** 2;
      vb += (b[i] - mb) ** 2;
    }
    return c / Math.sqrt(va * vb);
  };
  const smoothRow = (y, t) => {
    const raw = Array.from({ length: 2000 }, (_, i) => fields.breeze(i, y, t).lean);
    return raw.map((_, i) => {
      let s = 0;
      let n = 0;
      for (let j = Math.max(0, i - 40); j <= Math.min(raw.length - 1, i + 40); j++, n++) s += raw[j];
      return s / n;
    });
  };
  for (const y of [100, 300, 600]) {
    const a = smoothRow(y, 10);
    const b = smoothRow(y, 12);
    let best = [-1, 0];
    for (let s = 0; s <= 250; s += 2) {
      const c = corr(a.slice(300, 1500), b.slice(300 + s, 1500 + s));
      if (c > best[0]) best = [c, s / 2];
    }
    assert.ok(best[1] > 5 && best[1] <= 40, `row ${y}: gusts at ${best[1]} px/s`);
  }
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

test("an unknown creature kind is a clear error, not a crash in at()", () => {
  assert.throws(() => shoal.createShoal({ w: 800, h: 600, kinds: ["coral"], coral: false, colors }), /unknown kind "coral"/);
  assert.throws(() => shoal.createShoal({ w: 800, h: 600, kinds: [], colors }), /kinds is empty/);
});

test("creatures and islands wrap fully off-screen: no tile pops in or out at the edge", () => {
  const visible = (cells, w, cell) => cells.some((c) => c.x + cell / 2 > 0 && c.x - cell / 2 < w);
  const check = (make, w, cell, dt, T) => {
    let prev = make.at(0);
    for (let t = dt; t <= T; t += dt) {
      const cur = make.at(t);
      const jump = Math.abs(Math.min(...cur.map((c) => c.x)) - Math.min(...prev.map((c) => c.x))) > w / 2;
      if (jump) assert.ok(!visible(prev, w, cell) && !visible(cur, w, cell), `visible across a wrap at t=${t.toFixed(2)}`);
      prev = cur;
    }
  };
  for (const seed of [0, 1, 2, 3, 4, 5])
    for (const kind of ["fish", "ray", "minnow"]) {
      // a minnow school wraps member by member, so check each creature on its own (at() reads the live list)
      const s = shoal.createShoal({ w: 1440, h: 900, seed, count: 1, kinds: [kind], coral: false, colors });
      for (const k of [...s.list]) {
        s.list.splice(0, s.list.length, k);
        check(s, 1440, 12, 0.1, 220);
      }
    }
  for (const seed of [0, 1, 2]) check(shoal.createIslands({ w: 1440, h: 900, seed, n: 1, colors }), 1440, 12, 1, 700);
});

test("shoal tiles carry their creature id and a mask row centred on the creature", () => {
  const s = shoal.createShoal({ w: 1440, h: 900, seed: 5, count: 3, kinds: ["fish"], coral: false, colors });
  const cells = s.at(2);
  assert.deepEqual([...new Set(cells.map((c) => c.id))].sort(), [0, 1, 2]);
  const rows = cells.filter((c) => c.id === 0).map((c) => c.row);
  assert.equal(Math.min(...rows), -Math.max(...rows), "rows are centred on the creature");
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

// ── hero recipes and cinema ──
const heroes = await import(join(KIT, "heroes.js"));
const cine = await import(join(KIT, "cinema.js"));

test("hero recipes: every listed recipe has layers, the default is listed, unknown names are clear errors", () => {
  assert.deepEqual(Object.keys(heroes.HERO_LAYERS).sort(), [...heroes.HERO_RECIPES].sort());
  assert.ok(heroes.HERO_RECIPES.includes(heroes.HERO_DEFAULT));
  assert.throws(() => heroes.createHero("meadow", { w: 100, h: 100, colors }), /unknown recipe "meadow"/);
  const h = heroes.createHero("dawn", { w: 1440, h: 900, colors });
  assert.deepEqual(h.layers, ["soft", "sharp"]);
  assert.equal(typeof h.paint, "function");
});

test("seamDissolve: photographic inside sections, full type at a seam, and type to the end after `end`", () => {
  const o = { seams: [0.5], width: 0.08, end: 0.86 };
  assert.equal(cine.seamDissolve(0.2, o), 0);
  assert.equal(cine.seamDissolve(0.5, o), 1);
  assert.ok(cine.seamDissolve(0.46, o) > 0 && cine.seamDissolve(0.46, o) < 1);
  assert.equal(cine.seamDissolve(1, o), 1);
  assert.equal(cine.seamDissolve(0.2, { ...o, base: 0.3 }), 0.3);
});

test("dissolve thresholds are deterministic, uniformly spread, and turn cells progressively", () => {
  const a = cine.dissolveThresholds(40, 22, { seed: 3 });
  assert.deepEqual(a, cine.dissolveThresholds(40, 22, { seed: 3 }));
  assert.notDeepEqual(a, cine.dissolveThresholds(40, 22, { seed: 4 }));
  const s = Float32Array.from(a).sort();
  assert.ok(Math.abs(s[0] - 0.08) < 1e-6 && Math.abs(s.at(-1) - 0.92) < 1e-6);
  const turned = (d) => [...a].filter((x) => cine.cellDissolve(d, x) > 0.5).length / a.length;
  assert.equal(turned(0), 0);
  assert.equal(turned(1), 1);
  assert.ok(turned(0.25) < turned(0.5) && turned(0.5) < turned(0.75));
  assert.ok(Math.abs(turned(0.5) - 0.5) < 0.1, "half the frame is type at d = .5");
});

test("normaliseLuma stretches a pale frame across the ramp; glyphForLuma maps dark to heavy", () => {
  const pale = Float32Array.from({ length: 200 }, (_, i) => 0.8 + (i / 199) * 0.15);
  const n = cine.normaliseLuma(pale);
  assert.ok(Math.min(...n) === 0 && Math.max(...n) === 1);
  assert.equal(cine.glyphForLuma(0), cine.FILM_RAMP.length - 1);
  assert.equal(cine.glyphForLuma(1), 1);
});

// ── loop: reduced motion ──
test("reduced motion holds the still frame with the pearl at 0°, also when motion stops mid-run", async () => {
  const core = await import(join(KIT, "core.js"));
  const props = {};
  let scheduled;
  globalThis.document = { documentElement: { style: { setProperty: (k, v) => (props[k] = v) }, dataset: {} } };
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => "24" });
  globalThis.requestAnimationFrame = (cb) => ((scheduled = cb), 1);
  globalThis.cancelAnimationFrame = () => {};
  try {
    const { createLoop } = await import(join(KIT, "loop.js"));
    const painted = [];
    core.setMotion(false);
    const loop = createLoop({ paint: (t) => painted.push(t) });
    loop.start();
    scheduled(16);
    assert.equal(props["--ua"], "0.00deg");
    assert.ok(Math.abs(painted.at(-1) - 6) < 1e-9, `still frame at ${painted.at(-1)}`);
    const n = painted.length;
    scheduled(32);
    assert.equal(painted.length, n, "nothing repaints while held");
    core.setMotion(true);
    for (let k = 1; k <= 120; k++) scheduled(32 + k * 16.67);
    assert.ok(painted.at(-1) > 7, "motion resumes from the still");
    assert.notEqual(props["--ua"], "0.00deg");
    core.setMotion(false);
    scheduled(32 + 121 * 16.67);
    assert.ok(Math.abs(painted.at(-1) - 6) < 1e-9, "stopping motion mid-run settles on the still and repaints");
    assert.equal(props["--ua"], "0.00deg");
    loop.stop();
  } finally {
    core.setMotion(null);
    delete globalThis.document;
    delete globalThis.getComputedStyle;
    delete globalThis.requestAnimationFrame;
    delete globalThis.cancelAnimationFrame;
  }
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
  assert.throws(() => parseArgs(["a", "b", "--t", "Infinity"]), /not a time/);
  assert.throws(() => parseArgs(["a", "b", "--t", "4000"]), /not a time/);
  assert.throws(() => parseArgs(["a", "b", "--shots", "hero; rm"]), /--shots/);
  assert.throws(() => parseArgs(["a", "b", "--width", "10"]), /--width/);
  assert.throws(() => parseArgs(["a", "b", "--t", ","]), /at least one time/);
  assert.throws(() => parseArgs(["a", "b", "--mode", ","]), /at least one of dawn, dusk/);
});

test("a failing browser launch still closes the preview server", async () => {
  let server;
  const pw = { chromium: { launch: () => Promise.reject(new Error("no browser")) } };
  await assert.rejects(render(parseArgs([join(SKILL, "assets"), "specimen/index.html"]), { pw, onServer: (s) => (server = s) }), /no browser/);
  assert.ok(server, "the server was started");
  await new Promise((ok) => setImmediate(ok));
  assert.equal(server.listening, false, "and closed again");
});

test("followOS resolves the mode attribute from the OS and follows changes", async () => {
  const core = await import(join(KIT, "core.js"));
  let listener;
  const mq = { matches: true, addEventListener: (_, f) => (listener = f), removeEventListener: () => (listener = null) };
  globalThis.matchMedia = () => mq;
  try {
    const el = { dataset: {} };
    const seen = [];
    const off = core.followOS(el, (m) => seen.push(m));
    assert.equal(el.dataset.ldMode, "dusk");
    mq.matches = false;
    listener();
    assert.equal(el.dataset.ldMode, "dawn");
    assert.deepEqual(seen, ["dusk", "dawn"]);
    off();
    assert.equal(listener, null);
  } finally {
    delete globalThis.matchMedia;
  }
});

test("tokens.css has no CSS-only auto mode (materials key Dusk on the literal attribute)", () => {
  assert.doesNotMatch(readFileSync(join(SKILL, "assets/tokens/tokens.css"), "utf8"), /data-ld-mode="auto"/);
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
  const paper = await render({ root: join(SKILL, "assets"), page: "specimen/paper.html", width: "1440", shots: "hero,lens,footer", t: ["6"], mode: ["dawn"], out: join(out, "p") });
  assert.equal(paper.length, 3, "the paper page renders its hero, lens and footer without page errors");
  await assert.rejects(render({ ...opts, shots: "nope", t: ["0"], mode: ["dawn"], out: join(out, "d") }), /no \[data-shot\] element named: nope/);
});
