// Liquid Dawn kit · type as a field. Two pieces built on @chenglou/pretext (vendored, MIT):
//   - lensPage: a page of real proportional text, laid out by pretext, whose glyphs are displaced by a lens:
//       "pebble" (default): a stone dropped into the page, rings travelling through the lines and fading;
//       "well": gravitational lensing, the black-hole reference, used sparingly: glyphs bend round an empty core.
//   - flowAround: text that reflows around moving obstacles (a glass orb, a leaf) every frame. Each row can have a
//     different free width, so this is layoutNextLineRange() — pretext's variable-width-per-row call — per segment.
// The warp maths is pure (pebbleWarp, wellWarp, freeSpans) and tested; the drawing takes any 2D context.
import { clamp, smoothstep } from "./core.js";
import { layoutNextLineRange, layoutWithLines, materializeLineRange, prepareWithSegments } from "./vendor/pretext.js";

export { prepareWithSegments };

/** Pebble: radial displacement of a glyph at distance d from the drop, at time `age` since the drop.
 *  Rings travel at `speed` px/s, wavelength `wl`, decaying with distance and age. Returns [dr, lift] in px / 0..1. */
export function pebbleWarp(d, age, { amp = 7, wl = 46, speed = 34, decay = 260, life = 9 } = {}) {
  if (age < 0) return [0, 0];
  const front = age * speed;
  const env = smoothstep(front + wl, front - wl * 0.5, d) * Math.exp(-d / decay) * (1 - clamp(age / life)) ** 1.5;
  const ph = ((d - front) / wl) * Math.PI * 2;
  const s = Math.sin(ph);
  return [s * amp * env, clamp(0.5 + 0.5 * s) * env];
}

/** Well: point-lens deflection. A glyph at distance d is seen at d + rs²/d (pushed outward into an Einstein ring);
 *  inside the horizon it is gone (null). swirl rotates by swirl·rs/d rad. Returns [newD, dTheta] or null. */
export function wellWarp(d, { rs = 60, horizon = 0.85, swirl = 0.35 } = {}) {
  if (d < rs * horizon) return null;
  return [d + (rs * rs) / Math.max(d, 1), (swirl * rs) / Math.max(d, rs)];
}

const widthCache = new Map();
function charWidth(cx, font, ch) {
  const k = `${font}|${ch}`;
  let v = widthCache.get(k);
  if (v === undefined) {
    cx.font = font;
    v = cx.measureText(ch).width;
    widthCache.set(k, v);
  }
  return v;
}

/** Lay a text out with pretext once: returns lines [{text, width}] for the page width. */
export function layoutPage(text, font, width, lineHeight) {
  const prepared = prepareWithSegments(text, font);
  return layoutWithLines(prepared, width, lineHeight).lines;
}

/**
 * lensPage(cx, { lines, font, x, y, lineHeight, color, lens: { x, y, kind, t0, rs } , t, alpha })
 * Draws every glyph of a pretext layout, displaced by the lens. Glyph x positions come from the line's own text,
 * measured per character (kerning ignored: displacement makes a per-pair error invisible).
 */
export function lensPage(cx, { lines, font, x, y, lineHeight, color, accent, lens, t, alpha = 1, warp = {} }) {
  const g0 = cx.globalAlpha;
  cx.font = font;
  cx.textBaseline = "middle";
  cx.textAlign = "left";
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li].text;
    let gx = x;
    const gy = y + li * lineHeight + lineHeight / 2;
    for (const ch of line) {
      const w = charWidth(cx, font, ch);
      if (ch !== " ") {
        const ox = gx + w / 2 - lens.x;
        const oy = gy - lens.y;
        const d = Math.hypot(ox, oy);
        let px = gx;
        let py = gy;
        let a = alpha;
        let lit = 0;
        if (lens.kind === "well") {
          const q = wellWarp(d, { rs: lens.rs, ...warp });
          if (!q) {
            gx += w;
            continue;
          }
          const th = Math.atan2(oy, ox) + q[1] + (warp.spin ?? 0) * (lens.rs / Math.max(d, lens.rs)) ** 2;
          px = lens.x + Math.cos(th) * q[0] - w / 2;
          py = lens.y + Math.sin(th) * q[0];
          lit = smoothstep(lens.rs * 2.6, lens.rs, d);
        } else {
          const [dr, l] = pebbleWarp(d, t - (lens.t0 ?? 0), warp);
          const k = d > 0.001 ? dr / d : 0;
          px = gx + ox * k;
          py = gy + oy * k;
          lit = l;
        }
        a *= 1 - 0.25 * lit;
        cx.globalAlpha = g0 * a;
        cx.fillStyle = lit > 0.55 && accent ? accent : color;
        cx.fillText(ch, px, py);
      }
      gx += w;
    }
  }
  cx.globalAlpha = g0;
}

/** Free horizontal spans of the row [rowTop, rowTop + lh) inside [x0, x1], minus circular obstacles {x, y, r}.
 *  Spans narrower than `min` are dropped. Pure; tested. */
export function freeSpans(x0, x1, rowTop, lh, obstacles, min = 48) {
  let spans = [[x0, x1]];
  for (const o of obstacles) {
    const nearest = rowTop <= o.y && o.y <= rowTop + lh ? 0 : Math.min(Math.abs(rowTop - o.y), Math.abs(rowTop + lh - o.y));
    if (nearest >= o.r) continue;
    const half = Math.sqrt(o.r * o.r - nearest * nearest);
    const a = o.x - half;
    const b = o.x + half;
    const next = [];
    for (const [s, e] of spans) {
      if (b <= s || a >= e) next.push([s, e]);
      else {
        if (a > s) next.push([s, a]);
        if (b < e) next.push([b, e]);
      }
    }
    spans = next;
  }
  return spans.filter(([s, e]) => e - s >= min);
}

/**
 * flowAround(cx, { prepared, font, x, y, w, h, lineHeight, obstacles, color, gap })
 * Re-flows a prepared paragraph around obstacles every frame: per row, per free span, one layoutNextLineRange().
 * Returns the number of rows drawn (the text stops when it runs out or the box is full).
 */
export function flowAround(cx, { prepared, font, x, y, w, h, lineHeight, obstacles = [], color, gap = 14, alpha = 1 }) {
  cx.font = font;
  cx.fillStyle = color;
  cx.textBaseline = "alphabetic";
  cx.textAlign = "left";
  const g0 = cx.globalAlpha;
  cx.globalAlpha = g0 * alpha;
  const padded = obstacles.map((o) => ({ ...o, r: o.r + gap }));
  let cursor;
  let rows = 0;
  for (let top = y; top + lineHeight <= y + h; top += lineHeight) {
    for (const [s, e] of freeSpans(x, x + w, top, lineHeight, padded)) {
      const range = layoutNextLineRange(prepared, e - s, cursor);
      if (!range) {
        cx.globalAlpha = g0;
        return rows;
      }
      cx.fillText(materializeLineRange(prepared, range).text, s, top + lineHeight * 0.72);
      cursor = range.end;
    }
    rows++;
  }
  cx.globalAlpha = g0;
  return rows;
}
