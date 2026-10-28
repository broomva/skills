// Liquid Dawn kit · ASCII text shader. A glyph atlas per (size, colour, set, scale) and a cell field, one drawImage
// per lit cell. Two Dawn-specific moves beyond Liquid Midnight's ASCII background:
//   1. lenses — cells under a glass lens sample the field through refract(), so the glass BENDS the field it sits on
//      (magnified body, outward-bent bevel, lagoon/sand fringes at the rim) instead of only blurring it;
//   2. tiles — the glyph-tile mosaic of the shark references: a rounded tile per cell, a glyph inside, a soft shadow
//      tile cast down-right onto the water.
import { clamp, FONT } from "./core.js";
import { rampIndex, refract } from "./fields.js";

/** Ramps, light → heavy. Each is part of the look: do not extend them casually. */
export const RAMP = {
  water: " ·-~≈=",
  cloud: " ·.:°o",
  dots: " ·•",
  blades: " ',!|)/\\",
  general: " .·:-~=+*",
};

const cache = new Map();
/** Glyph atlas baked at the canvas's device scale so glyphs copy 1:1 (frames stay byte-identical). */
export function atlas(cx, fs, color, set = RAMP.general, weight = 400) {
  const S = Math.max(0.25, Math.round(cx.getTransform().a * 4) / 4);
  const key = `${fs}|${color}|${set}|${S}|${weight}`;
  let A = cache.get(key);
  if (A) return A;
  const cw = Math.ceil(fs * 0.64);
  const ch = Math.ceil(fs * 1.25);
  const chars = [...set];
  const cv = (typeof OffscreenCanvas === "function" ? new OffscreenCanvas(1, 1) : document.createElement("canvas"));
  cv.width = Math.ceil(cw * chars.length * S);
  cv.height = Math.ceil(ch * S);
  const x = cv.getContext("2d");
  x.scale(S, S);
  x.font = `${weight} ${fs}px ${FONT.mono}`;
  x.fillStyle = color;
  x.textBaseline = "middle";
  x.textAlign = "center";
  chars.forEach((s, i) => x.fillText(s, i * cw + cw / 2, ch / 2));
  A = { cv, cw, ch, S, n: chars.length, chars, index: new Map(chars.map((c, i) => [c, i])) };
  cache.set(key, A);
  return A;
}
/** Drop baked atlases (after fonts load, or a mode switch). */
export function resetAtlases() {
  cache.clear();
}
/** Load the faces before baking: hidden text never requests a face, so fonts.ready can resolve too early. */
export const fontsReady = () =>
  Promise.all(
    ['400 11px "JetBrains Mono"', '500 11px "JetBrains Mono"', "300 64px Manrope", "400 64px Manrope", "400 16px Inter"].map((f) =>
      typeof document !== "undefined" ? document.fonts?.load(f).catch(() => null) : null,
    ),
  ).then(resetAtlases);

/** Draw glyph i of atlas A centred in the cell at (X, Y). */
export function glyph(cx, A, i, X, Y) {
  cx.drawImage(A.cv, Math.round(i * A.cw * A.S), 0, Math.round(A.cw * A.S), Math.round(A.ch * A.S), Math.round(X - A.cw / 2), Math.round(Y - A.ch / 2), A.cw, A.ch);
}

/**
 * field(cx, opts) — fill a rect with glyphs from a scalar field.
 *  fn(X, Y) → number 0..1 (a ramp index) or a string (a glyph that must be in `ramp`); ≤ .02 or "" leaves it empty.
 *  lenses: [{x, y, w, h, r}] in the same px space. Cells inside sample fn through refract(); the rim adds fringes.
 *  mask(X, Y) → 0..1 multiplies the field (use fields.clearing for a quiet hero centre).
 */
export function field(
  cx,
  { x = 0, y = 0, w, h, cell = 14, fs = 11, ramp = RAMP.general, color, alpha = 0.5, fn, lenses = [], lensAlpha = 1.45, fringe = [], mask, weight = 400 },
) {
  const A = atlas(cx, fs, color, ramp, weight);
  const F = fringe.map((c) => atlas(cx, fs, c, ramp, weight));
  const cols = Math.ceil(w / cell);
  const rows = Math.ceil(h / cell);
  const g0 = cx.globalAlpha;
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      const X = x + c * cell + cell / 2;
      const Y = y + r * cell + cell / 2;
      let sx = X;
      let sy = Y;
      let edge = 0;
      let inLens = false;
      for (const L of lenses) {
        const q = refract(X, Y, L, L.opts);
        if (q) {
          sx = q.sx;
          sy = q.sy;
          edge = q.edge;
          inLens = true;
          break;
        }
      }
      let v = fn(sx, sy);
      const m = mask && !inLens ? mask(X, Y) : 1;
      let i;
      if (typeof v === "string") {
        if (!v || m < 0.5) continue;
        i = A.index.get(v);
        if (i === undefined) continue;
        v = 0.6;
      } else {
        v *= m;
        i = rampIndex(v, A.n);
        if (i < 0) continue;
      }
      const a = clamp(alpha * (inLens ? lensAlpha : 1) * (0.3 + 0.7 * clamp(v / 0.7)));
      if (inLens && edge > 0.3 && F.length) {
        cx.globalAlpha = g0 * a * edge * 0.75;
        glyph(cx, F[0], i, X - 1.4 * edge, Y);
        if (F[1]) glyph(cx, F[1], i, X + 1.4 * edge, Y);
      }
      cx.globalAlpha = g0 * a;
      glyph(cx, A, i, X, Y);
    }
  cx.globalAlpha = g0;
}

/**
 * tiles(cx, cells, opts) — the glyph-tile mosaic. cells: [{x, y, fill, ink, ch, a}] in px (cell centres).
 * A tile is a rounded square (size cell − gap) with its glyph; a shadow tile in `shadow` is cast at (dx, dy) first.
 */
export function tiles(cx, cells, { cell = 12, gap = 1.5, radius = 2, shadow, shadowAlpha = 0.16, dx = 3, dy = 4, fs = 9 } = {}) {
  const s = cell - gap;
  const g0 = cx.globalAlpha;
  if (shadow) {
    cx.fillStyle = shadow;
    for (const t of cells) {
      cx.globalAlpha = g0 * shadowAlpha * (t.a ?? 1);
      rr(cx, t.x - s / 2 + dx, t.y - s / 2 + dy, s, s, radius);
      cx.fill();
    }
  }
  for (const t of cells) {
    cx.globalAlpha = g0 * (t.a ?? 1);
    cx.fillStyle = t.fill;
    rr(cx, t.x - s / 2, t.y - s / 2, s, s, radius);
    cx.fill();
  }
  cx.font = `500 ${fs}px ${FONT.mono}`;
  cx.textAlign = "center";
  cx.textBaseline = "middle";
  for (const t of cells) {
    if (!t.ch) continue;
    cx.globalAlpha = g0 * (t.a ?? 1) * 0.85;
    cx.fillStyle = t.ink;
    cx.fillText(t.ch, t.x, t.y + 0.5);
  }
  cx.globalAlpha = g0;
}

function rr(cx, x, y, w, h, r) {
  cx.beginPath();
  cx.roundRect ? cx.roundRect(x, y, w, h, r) : cx.rect(x, y, w, h);
}
