// Liquid Dawn kit · glyph mosaic: any picture becomes a grid of small greyscale tiles, each carrying one glyph,
// with the edges dissolving into loose dots (the haj shark reference). The picture is painted at cell resolution on a
// scratch canvas (one pixel per cell), read back once, and every opaque cell becomes a tile whose grey and glyph follow
// the pixel's luminance. Pure parts (tileFor, edgeKeep, sharkOutline) are tested.
import { clamp, smoothstep, TAU } from "./core.js";

/** Glyphs light → dark, as in the reference. */
export const MOSAIC_GLYPHS = ":;t%SX#8@";

/** Deterministic per-cell hash in [0, 1). */
export function cellHash(c, r, seed = 0) {
  let h = Math.imul(c | 0, 0x27d4eb2d) ^ Math.imul(r | 0, 0x165667b1) ^ Math.imul(seed | 0, 0x9e3779b1);
  h = Math.imul(h ^ (h >>> 15), 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** A tile for a cell of luminance `l` (0 dark .. 1 light): its grey (0..1) and glyph. Dark cells get dark tiles and
 *  heavy glyphs; light cells pale tiles and light glyphs. Pure. */
export function tileFor(l, h = 0.5) {
  const L = clamp(l);
  const grey = 0.36 + 0.56 * L + (h - 0.5) * 0.06;
  const g = MOSAIC_GLYPHS[Math.min(MOSAIC_GLYPHS.length - 1, Math.floor((1 - L) * MOSAIC_GLYPHS.length))];
  return { grey: clamp(grey), glyph: g };
}

/** White-ground key: full opacity below `key − .14`, fading to none at `key`. Pure. */
export function keyAlpha(l, key = 0.93) {
  return 1 - smoothstep(key - 0.14, key, l);
}

/** Paint a photograph (an <img>, canvas or video frame) into a cell-resolution scratch context: centred at (x, y),
 *  `len` cells along its long side, rotated by `ang`, optionally mirrored. Pair with mosaic({ keyLight }). */
export function paintImage(cx, img, { x, y, len, ang = 0, flip = false }) {
  const iw = img.naturalWidth || img.videoWidth || img.width;
  const ih = img.naturalHeight || img.videoHeight || img.height;
  if (!iw || !ih) return;
  const k = len / Math.max(iw, ih);
  cx.save();
  cx.translate(x, y);
  cx.rotate(ang);
  cx.scale(k * (flip ? -1 : 1), k);
  cx.drawImage(img, -iw / 2, -ih / 2);
  cx.restore();
}

/** Edge dissolve: an opaque-enough cell is a full tile; a fringe cell (alpha .08..0.55) survives as a loose dot with a
 *  probability that falls with its alpha, so silhouettes fray into the paper. Returns "tile" | "dot" | null. Pure. */
export function edgeKeep(alpha, h) {
  if (alpha >= 0.55) return h < 0.04 + (1 - alpha) * 0.5 ? "dot" : "tile";
  if (alpha >= 0.08) return h < alpha * 0.9 ? "dot" : null;
  return null;
}

/**
 * mosaic(cx, src, { x, y, cell, gap, seed, ink, paper, tint })
 * src: a canvas painted at one pixel per cell (its width × height = cols × rows). Draws the tiles at (x, y).
 * tint: optional (h) => [r, g, b] | null to colour a few tiles faintly (the reference keeps colour rare).
 * Returns false (and draws nothing) when `src` is tainted by cross-origin media; true otherwise.
 * keyLight: for photographs on a white ground (a cut-out): luminance above this keys out to transparent, so only the
 *   subject becomes tiles. Leave null for canvases with real alpha.
 */
export function mosaic(cx, src, { x = 0, y = 0, cell = 10, gap = 1, seed = 1, ink = [40, 42, 46], dot = [120, 124, 130], tint = null, font = '600 8px "JetBrains Mono", monospace', alpha = 1, keyLight = null } = {}) {
  const sx = src.getContext("2d", { willReadFrequently: true });
  const { width: cols, height: rows } = src;
  let px;
  try {
    px = sx.getImageData(0, 0, cols, rows).data;
  } catch {
    return false; // a cross-origin picture without CORS taints the scratch canvas: draw nothing rather than throw
  }
  const s = cell - gap;
  const g0 = cx.globalAlpha;
  cx.font = font;
  cx.textAlign = "center";
  cx.textBaseline = "middle";
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      const i = (r * cols + c) * 4;
      let a = px[i + 3] / 255;
      if (keyLight !== null) a *= keyAlpha((0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]) / 255, keyLight);
      if (a < 0.08) continue;
      const h = cellHash(c, r, seed);
      const kind = edgeKeep(a, h);
      if (!kind) continue;
      const X = x + c * cell;
      const Y = y + r * cell;
      const l = (0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]) / 255;
      if (kind === "dot") {
        cx.globalAlpha = g0 * alpha * (0.35 + 0.4 * h);
        cx.fillStyle = `rgb(${dot[0]},${dot[1]},${dot[2]})`;
        cx.fillText(h < 0.5 ? "·" : h < 0.8 ? "-" : "'", X + cell / 2, Y + cell / 2);
        continue;
      }
      const t = tileFor(l, h);
      const v = Math.round(t.grey * 255);
      const tc = tint?.(h, l);
      cx.globalAlpha = g0 * alpha * Math.min(1, 0.5 + a);
      cx.fillStyle = tc ? `rgb(${tc[0]},${tc[1]},${tc[2]})` : `rgb(${v},${v},${Math.min(255, v + 3)})`;
      cx.fillRect(X, Y, s, s);
      if (h < 0.06) continue; // a few tiles carry no glyph, as in the reference
      const dark = t.grey < 0.55;
      cx.fillStyle = dark ? `rgba(245,245,243,${0.9 - t.grey * 0.5})` : `rgba(${ink[0]},${ink[1]},${ink[2]},${0.55 + (1 - t.grey) * 0.45})`;
      cx.fillText(t.glyph, X + s / 2, Y + s / 2 + 0.5);
    }
  cx.globalAlpha = g0;
  return true;
}

/**
 * The outline of a swimming shark in its own frame (nose at +x, length 1), as an array of [x, y] points, for time t.
 * The body is a centreline that undulates more toward the tail, widened by a fusiform profile; dorsal, pectoral and
 * caudal fins are attached at fixed stations. Pure; tested.
 */
export function sharkOutline(t, { phase = 0, beat = 1.4, amp = 0.045 } = {}) {
  const N = 40;
  const wave = (s) => amp * (1 - s) ** 2 * Math.sin(TAU * (beat * t * 0.25 + phase) - (1 - s) * 5.2);
  // half-thickness: blunt nose, widest at s ≈ .62, thin peduncle near the tail
  const half = (s) => 0.17 * Math.sin(Math.PI * s ** 0.9) ** 0.85 * (0.35 + 0.65 * smoothstep(0.05, 0.45, s));
  const X = (s) => s - 0.5;
  const top = [];
  const bot = [];
  for (let k = 0; k <= N; k++) {
    const s = k / N; // 0 tail .. 1 nose
    const c = wave(s);
    top.push([X(s), c - half(s)]);
    bot.push([X(s), c + half(s) * 0.92]);
  }
  const at = (s) => [X(s), wave(s)];
  // dorsal fin (top, s ≈ .55), pectoral fin (bottom, s ≈ .62), caudal fin (tail fork)
  const [dx, dy] = at(0.55);
  const dorsal = [[dx - 0.07, dy - half(0.55) + 0.01], [dx - 0.02, dy - half(0.55) - 0.15], [dx + 0.07, dy - half(0.55) + 0.005]];
  const [px, py] = at(0.62);
  const pect = [[px + 0.05, py + half(0.62) * 0.8], [px - 0.09, py + half(0.62) + 0.13], [px - 0.03, py + half(0.62) * 0.9]];
  const [tx, ty] = at(0);
  const tw = wave(0.05) - wave(0);
  const caudal = [[tx + 0.03, ty - 0.01], [tx - 0.11, ty - 0.17 + tw], [tx - 0.06, ty + 0.0], [tx - 0.1, ty + 0.13 + tw], [tx + 0.03, ty + 0.012]];
  return { top, bot, dorsal, pect, caudal };
}

/** Paint a shaded shark into `cx` centred at (x, y), `len` long, heading `ang` rad, at time t. Grey dark back, pale
 *  belly, a little mottling, so the mosaic has a picture to read. */
export function paintShark(cx, { x, y, len, ang = 0, t = 0, phase = 0, flip = false }) {
  const o = sharkOutline(t, { phase });
  cx.save();
  cx.translate(x, y);
  cx.rotate(ang);
  cx.scale(len * (flip ? -1 : 1), len);
  const poly = (pts) => {
    cx.beginPath();
    pts.forEach(([a, b], i) => (i ? cx.lineTo(a, b) : cx.moveTo(a, b)));
    cx.closePath();
    cx.fill();
  };
  const g = cx.createLinearGradient(0, -0.13, 0, 0.12);
  g.addColorStop(0, "rgb(52,56,64)");
  g.addColorStop(0.45, "rgb(118,124,134)");
  g.addColorStop(0.62, "rgb(196,200,206)");
  g.addColorStop(1, "rgb(232,234,236)");
  cx.fillStyle = "rgb(70,74,82)";
  poly(o.dorsal);
  poly(o.caudal);
  cx.fillStyle = "rgb(150,156,164)";
  poly(o.pect);
  cx.fillStyle = g;
  poly([...o.top, ...o.bot.slice().reverse()]);
  // mottling along the back and flank: a photograph has texture, so the mosaic gets tonal variety
  cx.save();
  cx.clip();
  for (let i = 0; i < 26; i++) {
    const u = ((i * 0.618034) % 1) - 0.5;
    const v = (((i * 0.414214) % 1) - 0.5) * 0.2;
    cx.fillStyle = i % 3 ? "rgba(30,32,38,.22)" : "rgba(255,255,255,.18)";
    cx.beginPath();
    cx.ellipse(u, v, 0.05 + (i % 4) * 0.015, 0.02 + (i % 3) * 0.01, 0.3, 0, TAU);
    cx.fill();
  }
  cx.restore();
  // gills and an eye: a few darker strokes the mosaic picks up as heavy glyphs
  cx.fillStyle = "rgb(36,38,44)";
  cx.beginPath();
  cx.arc(0.36, -0.02, 0.012, 0, TAU);
  cx.fill();
  cx.restore();
}
