// Liquid Dawn kit · nature fields. Every field is a PURE function of (x px, y px, t s) → 0..1 (or a small record),
// so a frame is reproducible and the tests can prove it. Calm is a number here, not an adjective:
//   - no field term advances faster than 0.2 rad/s (FIELD_SPEED_MAX), so nothing ever reads as rain or noise;
//   - every field is capped at CAP = .7, so the heaviest glyphs of a ramp stay reserved for subjects (shoals, ink);
//   - fields never flicker: there is no per-frame random draw anywhere in this file.
import { clamp, fbm, noise2, prng, smoothstep, TAU } from "./core.js";

export const CAP = 0.7;
export const FIELD_SPEED_MAX = 0.2;

/** Tide: water caustics seen through a shallow lagoon. An iterated domain warp (the classic caustic construction)
 *  run slowly: bright filaments form and dissolve over ~10 s. scale = px per caustic cell. */
export function tide(x, y, t, { scale = 520, speed = 0.11 } = {}) {
  const T = t * speed + 23;
  // The construction is 2π-periodic, so a plain grid would tile every `scale` px. A slow low-frequency domain warp
  // breaks the period. The far offset (as in the classic construction) keeps every 1/length term bounded (< .8).
  const wx = (fbm(x / (scale * 1.9), y / (scale * 1.9), 2, 5) - 0.5) * 5;
  const wy = (fbm(x / (scale * 1.9) + 9.1, y / (scale * 1.9) - 3.7, 2, 6) - 0.5) * 5;
  const px = (x / scale) * TAU + wx - 250;
  const py = (y / scale) * TAU + wy - 250;
  let ix = px;
  let iy = py;
  let c = 1;
  const inten = 0.005;
  for (let n = 0; n < 4; n++) {
    const tt = T * (1 - 3.5 / (n + 1));
    const nx = px + Math.cos(tt - ix) + Math.sin(tt + iy);
    const ny = py + Math.sin(tt - iy) + Math.cos(tt + ix);
    ix = nx;
    iy = ny;
    c += 1 / Math.hypot(px / (Math.sin(ix + tt) / inten), py / (Math.cos(iy + tt) / inten));
  }
  c /= 5;
  c = 1.17 - c ** 1.4;
  // depth: slow shallows (bright, busy) and deeps (quiet), so the water has places, not a uniform texture
  const depth = smoothstep(0.3, 0.72, fbm(x / (scale * 2.4) + t * 0.004, y / (scale * 2.4), 3, 41));
  return Math.min(CAP, smoothstep(0.2, 0.72, Math.abs(c) ** 8) * (0.08 + 0.92 * depth) * 1.15);
}

/** Breeze: wind moving through a meadow. Returns { v, lean } where lean is the blade angle from vertical (rad,
 *  + leans right). Gusts travel left→right at ~33 px/s; blades sway, never strobe. */
export function breeze(x, y, t, { speed = 0.2, seed = 3 } = {}) {
  const g = fbm(x * 0.0035, y * 0.009, 3, seed);
  const gust = Math.sin(x * 0.006 - t * speed * 2.6 + g * 4.2) * 0.5 + 0.5;
  const lean = -0.18 + 0.62 * gust ** 1.6 + (noise2(x * 0.05, y * 0.05, seed + 9) - 0.5) * 0.18;
  const v = smoothstep(0.32, 0.8, g) * (0.45 + 0.55 * gust);
  return { v: Math.min(CAP, v * 0.85), lean };
}

/** Cloud: soft cumulus drifting east at ~7 px/s. */
export function cloud(x, y, t, { speed = 0.02, seed = 7, scale = 1 } = {}) {
  const n = fbm((x * 0.0026) / scale - t * speed, (y * 0.0042) / scale + t * speed * 0.15, 5, seed);
  return Math.min(CAP, smoothstep(0.4, 0.66, n) * 0.85);
}

/** Ripple: a few pebbles dropped into still water, one ring pair every `period` seconds per pebble, staggered.
 *  Rings expand at 26 px/s and fade with age. `base` keeps a faint one-glyph lattice everywhere (the Claude FM
 *  halftone idea): rings modulate the lattice rather than appear from nothing. Deterministic from (seed, w, h). */
export function rippleField({ w, h, n = 4, period = 9.2, seed = 11, base = 0.06 }) {
  const r = prng(seed);
  const drops = Array.from({ length: n }, (_, i) => ({ x: (0.12 + 0.76 * r()) * w, y: (0.15 + 0.7 * r()) * h, phase: (i / n) * period + r() }));
  return (x, y, t) => {
    let v = 0;
    for (const d of drops) {
      const age = (((t + d.phase) % period) + period) % period;
      const R = age * 26;
      const dist = Math.hypot(x - d.x, y - d.y);
      const life = (1 - age / period) ** 1.2;
      for (let k = 0; k < 2; k++) {
        const rk = R - k * 20;
        if (rk <= 0) continue;
        const band = Math.exp(-((dist - rk) ** 2) / (2 * 3.6 ** 2));
        v += band * life * (1 - k * 0.35);
      }
    }
    return Math.min(CAP, base + v * 1.5);
  };
}

/** The clearing mask: 0 in an ellipse around (cx, cy), easing to 1 outside, so a hero's centre stays quiet. */
export function clearing(x, y, cx, cy, rx, ry, soft = 0.6) {
  const e = Math.hypot((x - cx) / rx, (y - cy) / ry);
  return smoothstep(1 - soft * 0.5, 1 + soft * 0.5, e);
}

/** Signed distance to a rounded rectangle {x, y, w, h, r} (negative inside). */
export function sdRoundRect(px, py, { x, y, w, h, r }) {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const rr = Math.min(r, w / 2, h / 2);
  const qx = Math.abs(px - cx) - (w / 2 - rr);
  const qy = Math.abs(py - cy) - (h / 2 - rr);
  return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - rr;
}

/** Refraction through a convex glass lens shaped as a rounded rect. Returns null outside the lens, else
 *  { sx, sy, edge } — the field coordinate to SAMPLE for the cell at (px, py), and edge ∈ [0, 1] (1 at the rim) for
 *  fringes. The body magnifies by `mag`; the bevel band bends the field outward, like the glass recorder capsule. */
export function refract(px, py, lens, { mag = 1.1, bevel = 0.24, bend = 0.85 } = {}) {
  const d = -sdRoundRect(px, py, lens);
  if (d < 0) return null;
  const b = Math.min(lens.w, lens.h) * bevel;
  const edge = 1 - smoothstep(0, b, d);
  const cx = lens.x + lens.w / 2;
  const cy = lens.y + lens.h / 2;
  // outward normal from the sdf gradient (central differences)
  const e = 0.75;
  const gx = sdRoundRect(px + e, py, lens) - sdRoundRect(px - e, py, lens);
  const gy = sdRoundRect(px, py + e, lens) - sdRoundRect(px, py - e, lens);
  const gl = Math.hypot(gx, gy) || 1;
  const k = edge * edge * b * bend;
  return {
    sx: cx + (px - cx) / mag + (gx / gl) * k,
    sy: cy + (py - cy) / mag + (gy / gl) * k,
    edge: clamp(edge),
  };
}

/** A pure ramp index for v ∈ 0..1 on a ramp of n glyphs; ≤ .02 is empty (-1). */
export function rampIndex(v, n) {
  if (!(v > 0.02)) return -1;
  return Math.min(n - 1, 1 + Math.floor(clamp(v) * (n - 1)));
}

/** The breeze glyph for a blade lean (rad from vertical): `|` upright, `/` right, `\` left, `'` `,` at low density. */
export function bladeGlyph(v, lean) {
  if (v < 0.12) return v < 0.05 ? "" : lean > 0.15 ? "," : "'";
  if (lean > 0.42) return "/";
  if (lean > 0.16) return v > 0.4 ? "/" : ")";
  if (lean < -0.12) return "\\";
  return v > 0.42 ? "|" : "!";
}
