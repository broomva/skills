// Drawing tests: recipes, mosaic, orb and frame sampling run against a recording 2D context, so "paints", "is
// deterministic in t" and "moves with t" are checked without a browser.
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const KIT = join(dirname(fileURLToPath(import.meta.url)), "../assets/kit");

/** A 2D context that records every call and property write; getImageData returns `pixels` if given. */
function fakeContext(pixels) {
  const log = [];
  const state = { globalAlpha: 1 };
  const ctx = new Proxy(
    {},
    {
      get(_, k) {
        if (k === "log") return log;
        if (k in state) return state[k];
        if (k === "getTransform") return () => ({ a: 1, b: 0 });
        if (k === "createLinearGradient" || k === "createRadialGradient") return () => ({ addColorStop() {} });
        if (k === "measureText") return (s) => ({ width: 6 * String(s).length });
        if (k === "getImageData") return (x, y, w, h) => ({ data: pixels ? pixels(w, h) : new Uint8ClampedArray(w * h * 4) });
        if (k === "createImageData") return (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h });
        return (...args) => {
          log.push([k, ...args.map((a) => (typeof a === "number" ? Math.round(a * 1000) / 1000 : typeof a))]);
        };
      },
      set(_, k, v) {
        state[k] = v;
        log.push([`=${String(k)}`, typeof v === "number" ? Math.round(v * 1000) / 1000 : String(v)]);
        return true;
      },
    },
  );
  return ctx;
}
// the ASCII atlas bakes glyphs on an OffscreenCanvas; give Node one that records into a throwaway context
globalThis.OffscreenCanvas ??= class {
  constructor() {
    this.width = 1;
    this.height = 1;
  }
  getContext() {
    return fakeContext();
  }
};

const colors = Object.fromEntries(
  ["paper", "surface", "sunk", "ink", "ink2", "ink3", "line", "line2", "tide", "shadow", "sky", "lagoon", "moss", "sand", "stone", "coral", "metal-fringe-a", "metal-fringe-b"].map((k) => [k, `#${k.length}${k.length}${k.length}`]),
);
const heroes = await import(join(KIT, "heroes.js"));
const lens = { x: 500, y: 400, w: 420, h: 120, r: 22, opts: { mag: 1.12, bevel: 0.3, bend: 0.9 } };
const layer = () => ({ cx: fakeContext(), w: 1000, h: 640 });
const run = (name, t) => {
  const L = { soft: layer(), sharp: layer() };
  heroes.createHero(name, { w: 1000, h: 640, colors }).paint(L, t, lens);
  return [...L.soft.cx.log, ...L.sharp.cx.log];
};

for (const name of heroes.HERO_RECIPES)
  test(`hero recipe "${name}" paints, is deterministic in t, and moves with t`, () => {
    const a = run(name, 6);
    assert.ok(a.filter(([k]) => ["fillText", "fillRect", "drawImage", "fill"].includes(k)).length > 20, `${name} drew almost nothing`);
    assert.deepEqual(a, run(name, 6), "same t, same drawing");
    assert.notDeepEqual(a, run(name, 14), "the picture moves");
  });

test("recipes that put a field under the lens refract it: their output changes when the lens moves", () => {
  for (const name of heroes.HERO_RECIPES) {
    const L1 = { soft: layer(), sharp: layer() };
    const L2 = { soft: layer(), sharp: layer() };
    const h = heroes.createHero(name, { w: 1000, h: 640, colors });
    h.paint(L1, 6, lens);
    // horizon's lens sits on its water band; for every other recipe move the lens anywhere
    h.paint(L2, 6, name === "horizon" ? { ...lens, y: 560, h: 60 } : { ...lens, y: lens.y + 140, x: lens.x + 60 });
    if (name === "horizon") h.paint(L1, 6, { ...lens, y: 520, h: 60 });
    assert.notDeepEqual(L1.sharp.cx.log, L2.sharp.cx.log, `${name} ignores its lens`);
  }
});

const cine = await import(join(KIT, "cinema.js"));
test("coverRect crops like object-fit: cover", () => {
  assert.deepEqual(cine.coverRect(1600, 900, 1600, 900), { x: 0, y: 0, w: 1600, h: 900 });
  const r = cine.coverRect(1600, 900, 390, 844); // a phone-shaped stage shows a centred vertical slice
  assert.equal(r.h, 900);
  assert.ok(Math.abs(r.w - (390 / 844) * 900) < 1e-6 && Math.abs(r.x - (1600 - r.w) / 2) < 1e-6);
  const s = cine.coverRect(900, 1600, 1600, 900); // a portrait source in a landscape box: a horizontal slice
  assert.equal(s.w, 900);
  assert.ok(s.y > 0);
});

function fakeStage(layers) {
  globalThis.getComputedStyle = (el) => ({ opacity: String(el.opacity ?? 1), display: el.display ?? "block", visibility: "visible" });
  return { querySelectorAll: (sel) => layers.filter((l) => l.tag === sel) };
}
const box = (w, h) => () => ({ width: w, height: h });

test("sampleFrame takes the most visible layer and crops it as cover", () => {
  const calls = [];
  const scratch = { width: 0, height: 0, getContext: () => ({ drawImage: (...a) => calls.push(a), getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(w * h * 4).fill(128) }) }) };
  const hidden = { tag: "img", complete: true, naturalWidth: 1600, naturalHeight: 900, opacity: 0, getBoundingClientRect: box(390, 844), id: "first" };
  const shown = { tag: "img", complete: true, naturalWidth: 1600, naturalHeight: 900, opacity: 1, getBoundingClientRect: box(390, 844), id: "second" };
  const f = cine.sampleFrame(fakeStage([hidden, shown]), 20, 40, scratch);
  assert.ok(f);
  assert.equal(calls[0][0].id, "second", "the visible poster, not the first complete one");
  const [, sx, , sw, sh] = calls[0];
  assert.equal(sh, 900);
  assert.ok(Math.abs(sw - (390 / 844) * 900) < 1e-6 && sx > 0, "cropped, not squeezed");
  delete globalThis.getComputedStyle;
});

test("sampleFrame returns null (not a throw) for tainted media", () => {
  const scratch = { getContext: () => ({ drawImage() {}, getImageData() { throw new Error("SecurityError"); } }) };
  const v = { tag: "video", readyState: 4, videoWidth: 1600, videoHeight: 900, opacity: 1, getBoundingClientRect: box(1440, 900) };
  assert.equal(cine.sampleFrame(fakeStage([v]), 10, 10, scratch), null);
  delete globalThis.getComputedStyle;
});

const mosaic = await import(join(KIT, "mosaic.js"));
test("mosaic: tiles where the picture is, dots at its edge, nothing on empty paper; keyLight keys a white ground", () => {
  // 10 × 4 source: col 0-3 opaque dark, col 4 half-alpha, rest transparent; row 3 is opaque white
  const px = (w, h) => {
    const d = new Uint8ClampedArray(w * h * 4);
    for (let r = 0; r < h; r++)
      for (let c = 0; c < w; c++) {
        const o = (r * w + c) * 4;
        const white = r === 3;
        d.set(white ? [255, 255, 255, 255] : [60, 60, 60, c < 4 ? 255 : c === 4 ? 70 : 0], o);
      }
    return d;
  };
  const src = { width: 10, height: 4, getContext: () => fakeContext(px) };
  const cx = fakeContext();
  mosaic.mosaic(cx, src, { cell: 10, seed: 3 });
  const rects = cx.log.filter(([k]) => k === "fillRect");
  assert.ok(rects.length >= 12, "opaque cells become tiles");
  assert.ok(rects.every(([, x, y]) => x % 10 === 0 && y % 10 === 0), "tiles lie on the lattice");
  const keyed = fakeContext();
  mosaic.mosaic(keyed, src, { cell: 10, seed: 3, keyLight: 0.93 });
  const keyedRows = keyed.log.filter(([k]) => k === "fillRect").map(([, , y]) => y);
  assert.ok(!keyedRows.includes(30), "the white row is keyed out");
  assert.ok(rects.map(([, , y]) => y).includes(30), "without keyLight the white row is tiled");
});

test("tileFor: darker → darker tile and heavier glyph; edgeKeep frays only the fringe", () => {
  const dark = mosaic.tileFor(0.1, 0.5);
  const light = mosaic.tileFor(0.9, 0.5);
  assert.ok(dark.grey < light.grey);
  assert.ok(mosaic.MOSAIC_GLYPHS.indexOf(dark.glyph) > mosaic.MOSAIC_GLYPHS.indexOf(light.glyph));
  assert.equal(mosaic.edgeKeep(0.02, 0.1), null);
  assert.equal(mosaic.edgeKeep(1, 0.5), "tile");
  assert.equal(mosaic.edgeKeep(0.3, 0.1), "dot");
  assert.equal(mosaic.edgeKeep(0.3, 0.9), null);
  assert.equal(mosaic.keyAlpha(1), 0);
  assert.equal(mosaic.keyAlpha(0.5), 1);
});

test("sharkOutline: deterministic, nose at +x, the tail sways with t and the nose barely moves", () => {
  const a = mosaic.sharkOutline(1);
  assert.deepEqual(a, mosaic.sharkOutline(1));
  const b = mosaic.sharkOutline(2.3);
  const tailMove = Math.abs(a.top[0][1] - b.top[0][1]);
  const noseMove = Math.abs(a.top.at(-1)[1] - b.top.at(-1)[1]);
  assert.ok(tailMove > 4 * noseMove, `tail ${tailMove} vs nose ${noseMove}`);
  assert.ok(Math.max(...a.top.map(([x]) => x)) <= 0.5 + 1e-9);
});

const lensMod = await import(join(KIT, "lens.js"));
test("lensRefract: the centre magnifies, the rim bends outward, and channels part only toward the rim", () => {
  assert.equal(lensMod.lensRefract(0), 0);
  assert.ok(lensMod.lensRefract(0.3) < 0.3, "centre samples nearer the middle: magnified");
  assert.ok(lensMod.lensRefract(1) > 1, "rim samples beyond the edge: bent");
  const split = (d) => lensMod.lensRefract(d, { channel: 1 }) - lensMod.lensRefract(d, { channel: -1 });
  assert.ok(split(0.95) > 10 * split(0.3), "dispersion lives at the rim");
});

const spark = await import(join(KIT, "spark.js"));
test("sparkField is deterministic, on the unit sphere, and sparkOrb paints more when busy", () => {
  const f = spark.sparkField(200, 3);
  assert.deepEqual(f, spark.sparkField(200, 3));
  for (const p of f) assert.ok(Math.abs(Math.hypot(...p.d) - 1) < 1e-9 && p.rad > 0 && p.rad <= 1);
  const strokes = (busy) => {
    const cx = fakeContext();
    spark.sparkOrb(cx, f, { x: 100, y: 100, R: 60, t: 3, busy });
    return cx.log.filter(([k]) => k === "stroke").length;
  };
  assert.ok(strokes(1) >= strokes(0));
  assert.ok(strokes(0) > 50);
});

const eng = await import(join(KIT, "engrave.js"));
test("engraving: paper stays bare, darker tones carry more ink; dither is a threshold on Bayer", () => {
  const ink = (l) => {
    let s = 0;
    for (let y = 0; y < 40; y++) for (let x = 0; x < 40; x++) s += eng.engraveInk(l, x, y);
    return s / 1600;
  };
  assert.ok(ink(0.99) < 0.01, `the lightest tone leaves paper bare (${ink(0.99)})`);
  assert.ok(ink(0.8) < ink(0.5) && ink(0.5) < ink(0.15));
  const bits = (l) => {
    let s = 0;
    for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) s += eng.ditherBit(l, x, y);
    return s;
  };
  assert.equal(bits(0), 16);
  assert.equal(bits(1), 0);
  assert.equal(bits(0.5), 8);
  const L = eng.coastScene(800, 400, 2);
  for (const [x, y] of [[10, 10], [400, 300], [790, 390], [600, 200]]) {
    const v = L(x, y);
    assert.ok(v >= 0 && v <= 1);
    assert.equal(v, eng.coastScene(800, 400, 2)(x, y));
  }
});

test("filmType: no type at d = 0, a paper backing and glyphs when dissolving, the glass veil only inside the lens", () => {
  const cols = 8;
  const rows = 4;
  const frame = { lum: new Float32Array(cols * rows).fill(0.3), rgb: new Uint8ClampedArray(cols * rows * 3).fill(120), cols, rows };
  const th = cine.dissolveThresholds(cols, rows);
  const draw = (d, lensRect) => {
    const cx = fakeContext();
    const back = fakeContext();
    cine.filmType(cx, frame, { w: 80, h: 40, d, thresholds: th, paper: "#eee", lens: lensRect, back });
    return { glyphs: cx.log.filter(([k]) => k === "fillText").length, backing: back.log.filter(([k]) => k === "fillRect").length };
  };
  assert.deepEqual(draw(0), { glyphs: 0, backing: 0 });
  const full = draw(1);
  assert.equal(full.glyphs, cols * rows);
  assert.equal(full.backing, cols * rows, "the backing goes on the backing context");
  // 10 px cells: a 20 × 10 lens at the origin covers exactly cells (0,0) and (1,0)
  assert.equal(draw(0, { x: 0, y: 0, w: 20, h: 10 }).glyphs, 2, "inside a section only the lens cells show type");
});

test("printInto: two inks, a pure function of L; grain 0 leaves exactly two colours", () => {
  const out = () => {
    let img;
    const cx = new Proxy(fakeContext(), {
      get(t, k) {
        if (k === "putImageData") return (i) => (img = i);
        if (k === "getTransform") return () => ({ a: 1 });
        return t[k];
      },
    });
    eng.printInto(cx, (x) => x / 40, { w: 40, h: 8, mode: "dither", ink: [10, 20, 30], paper: [240, 230, 220], grain: 0 });
    return img.data;
  };
  const a = out();
  assert.deepEqual(a, out());
  const colours = new Set();
  for (let i = 0; i < a.length; i += 4) colours.add(`${a[i]},${a[i + 1]},${a[i + 2]}`);
  assert.deepEqual([...colours].sort(), ["10,20,30", "240,230,220"]);
  const inkLeft = [...Array(8)].reduce((n, _, y) => n + (a[(y * 40 + 1) * 4] === 10), 0);
  const inkRight = [...Array(8)].reduce((n, _, y) => n + (a[(y * 40 + 38) * 4] === 10), 0);
  assert.ok(inkLeft > inkRight, "the dark side carries more ink");
});

test("lumaSampler interpolates bilinearly and clamps at the edges", () => {
  const L = eng.lumaSampler(Float32Array.from([0, 1, 0, 1]), 2, 2, 100, 100);
  assert.equal(L(0, 50), 0);
  assert.equal(L(100, 50), 1);
  assert.ok(Math.abs(L(50, 50) - 0.5) < 1e-6);
  assert.equal(L(-50, -50), 0);
});

test("mosaic returns false and draws nothing when its source is tainted", () => {
  const src = { width: 4, height: 4, getContext: () => ({ getImageData() { throw new Error("SecurityError"); } }) };
  const cx = fakeContext();
  assert.equal(mosaic.mosaic(cx, src, { cell: 10 }), false);
  assert.equal(cx.log.filter(([k]) => k === "fillRect").length, 0);
});

test("currents draws nothing unrefracted inside the glass: every glyph in the lens sits on the lens's own grid", () => {
  const L = { sharp: layer() };
  // outside the hero's quiet clearing (centred at 500,260), where the streams at y ≈ 477 and 557 are fully drawn
  const box = { x: 20, y: 440, w: 300, h: 160, r: 22, opts: { mag: 1.12, bevel: 0.3, bend: 0.9 } };
  heroes.createHero("currents", { w: 1000, h: 640, colors }).paint(L, 6, box);
  const inside = L.sharp.cx.log.filter(([k, , x, y]) => k === "fillText" && x > box.x && x < box.x + box.w && y > box.y && y < box.y + box.h);
  assert.ok(inside.length > 0, "the streams continue through the glass");
  for (const [, , x, y] of inside) assert.ok((x - box.x - 6) % 12 === 0 && (y - box.y - 6) % 12 === 0, `glyph at ${x},${y} is not a refracted cell`);
});
