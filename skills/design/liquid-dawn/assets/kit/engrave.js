// Liquid Dawn kit · print treatments for pictures: ENGRAVING (the scenic-footer reference: cobalt line-work on cream,
// tone carried by line thickness) and DITHER (the 3-7 / Wafer references: an ordered dither between two inks, so a
// photograph reads as print). Both take a luminance function L(x, y) → 0 dark .. 1 light, so they work on any
// picture: a sampled image, a video frame or a procedural scene. coastScene() is a procedural coastal landscape (sky,
// clouds, mountains, sea, a headland) so the treatments have a subject with no external assets.
import { clamp, fbm, noise2, smoothstep } from "./core.js";

/** 4×4 Bayer matrix, normalised to (0, 1). */
export const BAYER4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16);

/** Ordered dither: ink (1) or paper (0) for luminance l at pixel (x, y). Pure. */
export function ditherBit(l, x, y) {
  return l < BAYER4[(y & 3) * 4 + (x & 3)] ? 1 : 0;
}

/** Engraving coverage at (x, y): horizontal lines every `pitch` px, wobbling slightly, whose thickness grows as the
 *  picture darkens; a second, diagonal hatch joins in the deepest shadows. Returns ink coverage 0..1. Pure. */
export function engraveInk(l, x, y, { pitch = 4, wobble = 0.35, seed = 0 } = {}) {
  // lines follow the picture's own contours a little (a slow wobble), never a regular wave
  const v = y / pitch + (noise2(x * 0.006, y * 0.012, seed) - 0.5) * 1.6 * wobble;
  const f = Math.abs((((v % 1) + 1) % 1) - 0.5) * 2; // 0 on the line's centre, 1 between lines
  // tone → line width, with a toe: the lightest tones carry no line at all (paper shows), as in a real engraving
  const w = clamp(((1 - l) - 0.06) * 1.15);
  let ink = (1 - smoothstep(w - 0.1, w + 0.1, f)) * smoothstep(0.015, 0.09, w);
  if (l < 0.32) {
    const u = (x + y) / (pitch * 1.4);
    const g = Math.abs((u % 1) - 0.5) * 2;
    ink = Math.max(ink, (1 - smoothstep(0.25, 0.55, g)) * smoothstep(0.32, 0.1, l));
  }
  return ink;
}

/**
 * coastScene(w, h, t) → L(x, y): a coastal view in the toile manner. Pale sky with drifting cumulus (t moves them),
 * layered ridges fading with distance, a calm sea with reflected streaks, and a dark wooded headland on the right.
 */
export function coastScene(w, h, t = 0, { seed = 9 } = {}) {
  const hz = h * 0.68;
  const ridge = (x, k, base, amp, s) => base - amp * fbm(x / (w * k), s, 4, seed + s);
  return (x, y) => {
    // sky
    if (y < hz) {
      let l = 0.99 - 0.06 * (y / hz);
      const c = fbm(x / 260 - t * 0.012, y / 120, 5, seed);
      const cloud = smoothstep(0.5, 0.75, c) * smoothstep(hz * 0.95, hz * 0.2, y);
      // clouds: lit tops stay paper, their shaded undersides take fine lines
      const under = smoothstep(0.55, 0.85, fbm(x / 260 - t * 0.012, (y + 26) / 120, 5, seed));
      l = l - cloud * under * 0.42 * (0.6 + 0.4 * noise2(x / 40, y / 40, seed + 3));
      // a mountain with a real silhouette (a broad peak + rough ridgeline), lit from the left: the sunward slope
      // stays pale, the far slope takes heavier lines; then a lower, nearer ridge
      const px = (x / w - 0.42) / 0.22;
      const peak = Math.exp(-px * px) * h * 0.3 + h * 0.035 * fbm(x / (w * 0.08), 3.1, 4, seed + 1);
      const r1 = hz - peak;
      if (y > r1) {
        const slope = Math.tanh(px * 1.4); // −1 sunward .. +1 shaded
        l = Math.min(l, 0.74 - 0.2 * slope - 0.08 * ((y - r1) / Math.max(1, hz - r1)) + 0.08 * fbm(x / 30, y / 14, 3, seed + 4));
      }
      const r2 = hz - h * 0.05 - h * 0.05 * fbm(x / (w * 0.12), 7.7, 3, seed + 2);
      if (y > r2) l = Math.min(l, 0.5 + 0.16 * fbm(x / 40, y / 20, 3, seed + 5));
      // headland on the right
      const head = hz - h * 0.42 * smoothstep(w * 0.55, w * 0.85, x) + h * 0.06 * fbm(x / 50, 1, 3, seed + 6);
      if (y > head) l = Math.min(l, 0.12 + 0.5 * fbm(x / 18, y / 18, 4, seed + 7) ** 1.4);
      return clamp(l);
    }
    // sea: a darker band near the shore, horizontal reflections, the headland's reflection
    // sea: pale at the horizon (it reflects the sky), deepening toward the viewer, with long sparkle gaps
    let l = 0.92 - 0.32 * ((y - hz) / (h - hz)) ** 0.8;
    l += 0.16 * (fbm(x / 220, (y - hz) / 5 + t * 0.05, 3, seed + 8) - 0.5);
    const head = smoothstep(w * 0.55, w * 0.85, x) * (1 - smoothstep(hz, hz + h * 0.2, y));
    l -= head * 0.35;
    // rocks along the shore at the right
    const rock = smoothstep(0.6, 0.72, fbm(x / 30, y / 18, 4, seed + 10)) * smoothstep(w * 0.45, w * 0.95, x) * smoothstep(hz, h, y);
    l -= rock * 0.5;
    return clamp(l);
  };
}

/** A soft sky of clouds for the dither card: L(x, y). */
export function cloudSky(w, h, t = 0, { seed = 4 } = {}) {
  return (x, y) => {
    const c = fbm(x / 180 - t * 0.01, y / 110, 5, seed);
    const cl = smoothstep(0.42, 0.78, c);
    const base = 0.42 + 0.3 * (y / h);
    return clamp(base + cl * 0.5 * (0.7 + 0.3 * noise2(x / 30, y / 30, seed + 1)));
  };
}

const lerp3 = (a, b, k) => [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];

/**
 * printInto(cx, L, { x, y, w, h, mode, ink, paper, pitch, scale, grain, resolution }) — render L as "engrave" or
 * "dither": two inks, plus a faint paper grain (±grain/2 per channel; grain: 0 for strictly two colours). `scale` > 1
 * coarsens the dither grain (3-7's visible print grain). L is a function; for a picture use imageLuma(img, w, h).
 */
export function printInto(cx, L, { x = 0, y = 0, w, h, mode = "engrave", ink = [42, 82, 190], paper = [242, 236, 222], pitch = 4, scale = 1, seed = 0, grain = 8, resolution = 1 }) {
  // printed at `resolution` × CSS px (default 1, not the device ratio: a print's grain is coarse anyway, and 1× costs a
  // quarter of the work at 2× DPR), then copied up with smoothing off so the lines and dots stay crisp
  const d = resolution;
  const W = Math.round(w * d);
  const H = Math.round(h * d);
  const img = cx.createImageData(W, H);
  const px = img.data;
  for (let j = 0; j < H; j++)
    for (let i = 0; i < W; i++) {
      const X = i / d;
      const Y = j / d;
      const l = L(X, Y);
      let k;
      if (mode === "dither") {
        const gx = Math.floor(i / (scale * d));
        const gy = Math.floor(j / (scale * d));
        k = ditherBit(l, gx, gy);
      } else k = engraveInk(l, X, Y, { pitch, seed });
      const gr = grain ? (noise2(i * 0.9, j * 0.9, 77) - 0.5) * grain : 0;
      const c = lerp3(paper, ink, k);
      const o = (j * W + i) * 4;
      px[o] = c[0] + gr;
      px[o + 1] = c[1] + gr;
      px[o + 2] = c[2] + gr;
      px[o + 3] = 255;
    }
  const dev = cx.getTransform().a || 1;
  if (Math.abs(dev - d) < 1e-6 || typeof document === "undefined") {
    cx.putImageData(img, Math.round(x * dev), Math.round(y * dev));
    return;
  }
  const off = document.createElement("canvas");
  off.width = W;
  off.height = H;
  off.getContext("2d").putImageData(img, 0, 0);
  const smooth = cx.imageSmoothingEnabled;
  cx.imageSmoothingEnabled = false;
  cx.drawImage(off, x, y, w, h);
  cx.imageSmoothingEnabled = smooth;
}

/**
 * imageLuma(img, w, h) → L(x, y) | null: turn a picture (<img>, <video>, canvas) into the luminance function the
 * printers take, cropped as object-fit: cover to a w × h box and sampled bilinearly. Returns null for cross-origin
 * media without CORS (the canvas would be tainted).
 */
export function imageLuma(img, w, h, { res = 0.5 } = {}) {
  const sw = img.naturalWidth || img.videoWidth || img.width;
  const sh = img.naturalHeight || img.videoHeight || img.height;
  if (!sw || !sh) return null;
  const W = Math.max(2, Math.round(w * res));
  const H = Math.max(2, Math.round(h * res));
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const x = c.getContext("2d", { willReadFrequently: true });
  const s = Math.max(w / sw, h / sh);
  const cw = w / s;
  const ch = h / s;
  let px;
  try {
    x.drawImage(img, (sw - cw) / 2, (sh - ch) / 2, cw, ch, 0, 0, W, H);
    px = x.getImageData(0, 0, W, H).data;
  } catch {
    return null;
  }
  const lum = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) lum[i] = (0.2126 * px[i * 4] + 0.7152 * px[i * 4 + 1] + 0.0722 * px[i * 4 + 2]) / 255;
  return lumaSampler(lum, W, H, w, h);
}

/** Bilinear sampler over a W × H luminance grid spanning a w × h box. Pure; tested. */
export function lumaSampler(lum, W, H, w, h) {
  return (x, y) => {
    const fx = clamp((x / w) * W - 0.5, 0, W - 1);
    const fy = clamp((y / h) * H - 0.5, 0, H - 1);
    const x0 = Math.floor(fx);
    const y0 = Math.floor(fy);
    const x1 = Math.min(W - 1, x0 + 1);
    const y1 = Math.min(H - 1, y0 + 1);
    const tx = fx - x0;
    const ty = fy - y0;
    const a = lum[y0 * W + x0] * (1 - tx) + lum[y0 * W + x1] * tx;
    const b = lum[y1 * W + x0] * (1 - tx) + lum[y1 * W + x1] * tx;
    return a * (1 - ty) + b * ty;
  };
}

/** A duotone ramp for dither cards that keeps both ends in the image: shadows in `lo`, lights in `hi`. Returns L and
 *  the two inks to hand to printInto. */
export const DUOTONES = {
  cobalt: { ink: [38, 78, 186], paper: [243, 238, 226] },
  teal: { ink: [26, 70, 84], paper: [236, 190, 132] },
  slate: { ink: [52, 60, 72], paper: [232, 234, 236] },
};
