// Liquid Midnight render kit · ASCII text shader: a glyph atlas per (size, colour, set) and a field function,
// one drawImage per lit cell. Used for the liquid-metal background, glyph trails behind orbs and act-breaker pieces.
// Extracted from broomva/agent-workspaces deck/index.html @187972f, lines 1548-1567 and 1641-1647 (Apache-2.0).
import { clamp, ctx, FONT, MOTION, use } from "./core.js";

/** density ramp, light → heavy. Do not add characters: the ramp IS the look. */
export const RAMP = " .·:-=+*%#@";
export const BLOCK = " ░▒▓█";
const atlasCache = {};

/** Glyph atlas baked at the target canvas's own scale so glyphs are copied 1:1 (no resampling: frames stay byte-identical). */
export function atlas(fs, color, set = RAMP) {
  const S = Math.max(0.25, Math.round(ctx.getTransform().a * 4) / 4);
  const key = `${fs}|${color}|${set}|${S}`;
  if (atlasCache[key]) return atlasCache[key];
  const cw = Math.ceil(fs * 0.62);
  const ch = Math.ceil(fs * 1.2);
  const chars = [...set];
  const cv = document.createElement("canvas");
  cv.width = Math.ceil(cw * chars.length * S);
  cv.height = Math.ceil(ch * S);
  const x = cv.getContext("2d");
  x.scale(S, S);
  x.font = `500 ${fs}px ${FONT.m}`;
  x.fillStyle = color;
  x.textBaseline = "middle";
  x.textAlign = "center";
  chars.forEach((s, i) => {
    x.fillText(s, i * cw + cw / 2, ch / 2);
  });
  atlasCache[key] = { cv, cw, ch, S, n: chars.length };
  return atlasCache[key];
}
/** Drop every baked atlas (call after fonts load or the theme changes). */
export function resetAtlases() {
  for (const k in atlasCache) delete atlasCache[k];
}
/** Load the faces before baking: hidden content never requests a face, so fonts.ready can resolve too early. */
export const fontsReady = () =>
  Promise.all(['500 11px "JetBrains Mono"', "300 76px Raleway", "400 16px Inter", "500 16px Inter"].map((f) => document.fonts?.load(f).catch(() => null))).then(
    resetAtlases,
  );

/** draw glyph i of atlas A at (X, Y); pixel-snapped unless the context is rotated */
export function glyph(A, i, X, Y) {
  const m = ctx.getTransform();
  const rot = Math.abs(m.b) > 1e-6;
  ctx.imageSmoothingEnabled = rot;
  ctx.drawImage(
    A.cv,
    Math.round(i * A.cw * A.S),
    0,
    Math.round(A.cw * A.S),
    Math.round(A.ch * A.S),
    rot ? X : Math.round(X),
    rot ? Y : Math.round(Y),
    A.cw,
    A.ch,
  );
  ctx.imageSmoothingEnabled = true;
}

/** Fill a rect with glyphs: fn(X, Y, col, row) → 0..1 picks the ramp index; ≤ .02 leaves the cell empty. */
export function asciiField(x0, y0, w, h, cell, A, fn) {
  const cols = Math.floor(w / cell);
  const rows = Math.floor(h / cell);
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      const X = x0 + c * cell;
      const Y = y0 + r * cell;
      const v = fn(X, Y, c, r);
      if (v <= 0.02) continue;
      const i = Math.min(A.n - 1, 1 + Math.floor(clamp(v, 0, 1) * (A.n - 1)));
      glyph(A, i, X, Y);
    }
}

/** The liquid-metal flow: a product of two domain-warped sines, sharpened (pow 2.2) and capped at .72 so it never
 *  reaches the heaviest glyphs. Slow on purpose: it must read as moving metal, never as rain or noise. */
export const metalFlow = (X, Y, t) => {
  const f = Math.sin(X * 0.011 + Math.sin(Y * 0.008 + t * 0.19) * 1.7 + t * 0.13) * 0.5 + 0.5;
  const g = Math.sin(Y * 0.015 - t * 0.11 + Math.sin(X * 0.005 + t * 0.07) * 2.2) * 0.5 + 0.5;
  return Math.min(0.72, (f * g) ** 2.2 * 1.25);
};

/** Background layer: a full-viewport canvas drawing metalFlow at 11 px glyphs on a 15 px cell, alpha .15 night / .12 day.
 *  Returns { fit(), draw(t) }. Put the canvas under every glass surface (class lm-ascii-bg). */
export function asciiBackground(cv, { day = () => false, color } = {}) {
  const BG = { cv, cx: null, w: 0, h: 0, d: 0 };
  BG.fit = (w = innerWidth, h = innerHeight) => {
    const d = Math.min(2, devicePixelRatio || 1);
    if (BG.cx && BG.w === w && BG.h === h && BG.d === d) return; // assigning width clears the canvas; resize only on change
    Object.assign(BG, { w, h, d });
    cv.width = w * d;
    cv.height = h * d;
    BG.cx = cv.getContext("2d");
    BG.cx.setTransform(d, 0, 0, d, 0, 0);
  };
  BG.draw = (t) => {
    if (!BG.cx) BG.fit();
    const prev = use(BG.cx);
    const isDay = day();
    BG.cx.clearRect(0, 0, BG.w, BG.h);
    const A = atlas(11, color || (isDay ? "oklch(0.45 0.05 245)" : "oklch(0.78 0.06 245)"));
    BG.cx.globalAlpha = isDay ? 0.12 : 0.15;
    const tt = MOTION ? t : 0;
    asciiField(0, 0, BG.w, BG.h, 15, A, (X, Y) => metalFlow(X, Y, tt));
    BG.cx.globalAlpha = 1;
    use(prev);
  };
  return BG;
}

/** Glyph trail behind a moving object: at(k) returns the [x, y] the object occupied k steps ago (k = 1..n).
 *  Glyphs step down 'Oo+:.' and fade linearly; the deck uses n = 12 at 0.028 rad per step on orbiting orbs. */
export function glyphTrail(at, color, n = 12, fs = 14) {
  const TR = atlas(fs, color, "Oo+:.");
  const g = ctx.globalAlpha;
  for (let k = 1; k <= n; k++) {
    const [x, y] = at(k);
    ctx.globalAlpha = g * (1 - k / (n + 1)) * 0.85;
    glyph(TR, Math.min(4, Math.floor((k - 1) / 2.6)), x - 4, y - 8);
  }
  ctx.globalAlpha = g;
}

/** A dotted ASCII ellipse (orbit guides, act-breaker rings). */
export function dotRing(cx, cy, rx, ry, color, n = 180, a = 0.55, phase = 0) {
  const D = atlas(12, color, "·");
  const g = ctx.globalAlpha;
  ctx.globalAlpha = g * a;
  for (let k = 0; k < n; k++) {
    const t = (k / n) * Math.PI * 2 + phase;
    glyph(D, 0, cx + Math.cos(t) * rx - 3, cy + Math.sin(t) * ry - 8);
  }
  ctx.globalAlpha = g;
}

/** Text streamed around a circle, each glyph rotated to the tangent, brightened by a sweep that travels at sweep rad/s. */
export function ringText(txt, cx, cy, R, t, color, { fs = 20, speed = 0.12, sweep = 0.7 } = {}) {
  const map = [...new Set(txt)];
  const A = atlas(fs, color, map.join(""));
  const str = txt.repeat(3);
  const n = str.length;
  const step = (Math.PI * 2) / n;
  const g = ctx.globalAlpha;
  for (let i = 0; i < n; i++) {
    const th = i * step + t * speed - Math.PI / 2;
    const ch = str[i];
    if (ch === " ") continue;
    const v = 0.28 + 0.72 * (0.5 + 0.5 * Math.cos(th - t * sweep)) ** 6;
    ctx.save();
    ctx.translate(cx + Math.cos(th) * R, cy + Math.sin(th) * R);
    ctx.rotate(th + Math.PI / 2);
    ctx.globalAlpha = g * v;
    glyph(A, map.indexOf(ch), -fs * 0.3, -fs * 0.6);
    ctx.restore();
  }
  ctx.globalAlpha = g;
}
