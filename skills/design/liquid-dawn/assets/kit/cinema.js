// Liquid Dawn kit · cinema: the ASCII shader running ON a scroll-scrubbed film (scroll-cinema), so the film and the
// fields are one material. Inside a section the film stays photographic; at a page break (a seam between clips, or the
// film's end) the frame dissolves into type, cell by cell in a tide-shaped order, and the next picture resolves out of
// it. The pure parts (seamDissolve, cellDissolve, dissolveThresholds, glyphForLuma) are tested; sampleFrame and
// filmType touch the DOM.
import { clamp, smoothstep } from "./core.js";
import { tide } from "./fields.js";

/** Light → heavy. On a paper backing, dark parts of the frame get the heavy glyphs. */
export const FILM_RAMP = " .·:-~=+*#";

/**
 * How much of the frame is type at scroll progress p ∈ [0, 1].
 *  seams: progress positions of page breaks (clip seams, chapter breaks); each makes a bump of half-width `width`.
 *  end:   from `end` to 1 the frame dissolves fully and stays type (the hand-off to the paper sections).
 *  base:  the resting veil inside sections (0 = pure photograph).
 */
export function seamDissolve(p, { seams = [], width = 0.07, end = 0.9, base = 0 } = {}) {
  let d = base;
  for (const s of seams) d = Math.max(d, 1 - smoothstep(0, width, Math.abs(p - s)));
  d = Math.max(d, smoothstep(end, 1, p));
  return clamp(d);
}

/** Per-cell dissolve: a cell turns at its own threshold, softly, so the whole frame never flips at once. */
export function cellDissolve(d, threshold, soft = 0.14) {
  return smoothstep(threshold - soft, threshold + soft, d * (1 + 2 * soft) - soft);
}

/** Thresholds shaped by the tide field, so the dissolve spreads like water across the frame, then rank-normalised to
 *  a uniform spread over [0.08, 0.92]: cells turn evenly through the whole dissolve, in the field's order.
 *  Deterministic for (cols, rows, seed). */
export function dissolveThresholds(cols, rows, { seed = 0, scale = 9 } = {}) {
  const n = cols * rows;
  const raw = new Float32Array(n);
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) raw[r * cols + c] = tide(c * scale + seed * 131, r * scale, 4, { scale: 360 }) + (((c * 7 + r * 13 + seed) % 17) / 16) * 0.08;
  const order = Array.from({ length: n }, (_, i) => i).sort((a, b) => raw[a] - raw[b] || a - b);
  const th = new Float32Array(n);
  order.forEach((i, rank) => {
    th[i] = 0.08 + (0.84 * rank) / Math.max(1, n - 1);
  });
  return th;
}

/** Glyph index for a luminance in 0..1 (dark → heavy). */
export function glyphForLuma(l, n = FILM_RAMP.length) {
  return Math.min(n - 1, Math.max(1, Math.round((1 - clamp(l)) * (n - 1))));
}

/** Stretch a frame's luminance between its 4th and 96th percentiles, so a pale dawn frame still spans the whole
 *  ramp (otherwise everything maps to the lightest glyphs and the picture's structure is lost). Pure. */
export function normaliseLuma(lum) {
  const s = Float32Array.from(lum).sort();
  const lo = s[Math.floor(s.length * 0.04)];
  const hi = s[Math.floor(s.length * 0.96)];
  const span = Math.max(1e-3, hi - lo);
  return lum.map((v) => clamp((v - lo) / span));
}

/** object-fit: cover — the part of a (sw × sh) source that a (dw × dh) box shows, centred (object-position 50% 50%).
 *  Returns the source rect { x, y, w, h }. Pure. */
export function coverRect(sw, sh, dw, dh) {
  const s = Math.max(dw / sw, dh / sh);
  const w = dw / s;
  const h = dh / s;
  return { x: (sw - w) / 2, y: (sh - h) / 2, w, h };
}

/** Sample the visible frame of a scroll-cinema stage into a cols × rows grid: the most visible ready <video>, else the
 *  most visible poster <img>, cropped as object-fit: cover crops it. Returns { lum, rgb, cols, rows }, or null when
 *  nothing is drawable yet or the media is cross-origin without CORS (a tainted canvas). */
export function sampleFrame(stage, cols, rows, scratch) {
  const opacity = (el) => {
    const cs = getComputedStyle(el);
    return cs.display === "none" || cs.visibility === "hidden" ? 0 : Number.parseFloat(cs.opacity);
  };
  // the most visible decoded layer: a ready <video>, else the most visible loaded poster <img>
  let src = null;
  let best = 0.05;
  for (const v of stage.querySelectorAll("video")) {
    const o = opacity(v);
    if (v.readyState >= 2 && o > best) {
      best = o;
      src = v;
    }
  }
  if (!src) {
    best = 0.05;
    for (const i of stage.querySelectorAll("img")) {
      const o = opacity(i);
      if (i.complete && i.naturalWidth && o > best) {
        best = o;
        src = i;
      }
    }
  }
  if (!src) return null;
  const sw = src.videoWidth || src.naturalWidth;
  const sh = src.videoHeight || src.naturalHeight;
  const box = src.getBoundingClientRect();
  if (!sw || !sh || !box.width || !box.height) return null;
  // sample what the viewer sees: the cover-cropped part of the source, not the whole squeezed frame
  const r = coverRect(sw, sh, box.width, box.height);
  scratch.width = cols;
  scratch.height = rows;
  const x = scratch.getContext("2d", { willReadFrequently: true });
  let px;
  try {
    x.drawImage(src, r.x, r.y, r.w, r.h, 0, 0, cols, rows);
    px = x.getImageData(0, 0, cols, rows).data; // throws SecurityError on cross-origin media without CORS
  } catch {
    return null;
  }
  const lum = new Float32Array(cols * rows);
  const rgb = new Uint8ClampedArray(cols * rows * 3);
  for (let i = 0; i < cols * rows; i++) {
    const R = px[i * 4];
    const G = px[i * 4 + 1];
    const B = px[i * 4 + 2];
    rgb.set([R, G, B], i * 3);
    lum[i] = (0.2126 * R + 0.7152 * G + 0.0722 * B) / 255;
  }
  return { lum: normaliseLuma(lum), rgb, cols, rows };
}

/**
 * filmType(cx, frame, { w, h, d, thresholds, paper, ink, font, lens })
 * Paints the frame as type over the video: each cell, as it dissolves, gets a paper backing (hiding the photograph)
 * and the glyph for its luminance, coloured by the frame's own colour pulled toward `ink` for legibility.
 * `back`: a second context for the paper backing; put it on a CSS-blurred canvas and the photograph frosts into
 * paper before the type sharpens over it (the backing defaults to the glyph canvas: hard cells).
 * Under `lens` (a glass rect) the veil holds at `lensVeil` even inside a section: the glass shows the type within.
 */
export function filmType(cx, frame, { w, h, d, thresholds, paper, ink = [24, 35, 42], font = '500 13px "JetBrains Mono", monospace', lens = null, lensVeil = 0.85, inkPull = 0.45, backing = 0.9, back = cx }) {
  const { lum, rgb, cols, rows } = frame;
  const cw = w / cols;
  const ch = h / rows;
  cx.clearRect(0, 0, w, h);
  if (back !== cx) back.clearRect(0, 0, w, h);
  cx.font = font;
  cx.textAlign = "center";
  cx.textBaseline = "middle";
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      const X = c * cw;
      const Y = r * ch;
      const inLens = lens && X + cw > lens.x && X < lens.x + lens.w && Y + ch > lens.y && Y < lens.y + lens.h;
      const k = Math.max(cellDissolve(d, thresholds[i], 0.22), inLens ? lensVeil : 0);
      if (k <= 0.01) continue;
      back.globalAlpha = k * k * backing * (inLens ? 0.55 : 1);
      back.fillStyle = paper;
      back.fillRect(X - 1, Y - 1, cw + 2, ch + 2);
      const g = glyphForLuma(lum[i]);
      const m = (a, b) => Math.round(a + (b - a) * inkPull);
      cx.globalAlpha = k;
      cx.fillStyle = `rgb(${m(rgb[i * 3], ink[0])},${m(rgb[i * 3 + 1], ink[1])},${m(rgb[i * 3 + 2], ink[2])})`;
      cx.fillText(FILM_RAMP[g], X + cw / 2, Y + ch / 2);
    }
  cx.globalAlpha = 1;
  back.globalAlpha = 1;
}
