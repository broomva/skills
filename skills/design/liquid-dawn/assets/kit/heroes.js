// Liquid Dawn kit · hero recipes. A hero background is a recipe: a CSS ground (materials.css,
// `.ld-hero-bg[data-recipe=<name>]`), an optional soft canvas (`.ld-field.ld-soft`, blurred by CSS into light), and a
// sharp canvas for glyphs and tiles. Every recipe is pure in t and its seed, keeps a clearing behind the hero copy,
// and, where it draws a field under the hero's lens (the composer or CTA glass), refracts that field through it:
// dawn, caustic, lagoon and tide refract; horizon refracts only the water band; currents draws no field under the lens.
// Owner-chosen directions (2026-10-28): caustic light, currents, lagoon, horizon; "dawn" blends the first three and is
// the default. "tide" is the first hero, kept as a recipe.
import { clearing, cloud, tide } from "./fields.js";
import { field, RAMP, tiles } from "./ascii.js";
import { prng, smoothstep } from "./core.js";
import { createIslands, createShoal } from "./shoal.js";

export const HERO_RECIPES = ["dawn", "caustic", "currents", "lagoon", "horizon", "tide"];
export const HERO_DEFAULT = "dawn";

/** Which canvases a recipe paints: soft (blurred light) and/or sharp (glyphs, tiles). */
export const HERO_LAYERS = { dawn: ["soft", "sharp"], caustic: ["soft", "sharp"], currents: ["sharp"], lagoon: ["sharp"], horizon: ["sharp"], tide: ["sharp"] };

/**
 * createHero(name, { w, h, colors, seed, calm }) → { name, layers, paint({ soft, sharp }, t, lens) }
 *  soft / sharp: { cx, w, h } from fitCanvas (soft may be omitted when the recipe has no soft layer).
 *  lens: { x, y, w, h, r, opts } in canvas px, the glass the copy sits in (refracted by the field), or null.
 *  calm: { cx, cy, rx, ry } the clearing behind the copy (defaults to the centre, 470 × 210 px).
 */
export function createHero(name, { w, h, colors: C, seed = 21, calm } = {}) {
  if (!HERO_LAYERS[name]) throw new Error(`createHero: unknown recipe "${name}" (one of ${HERO_RECIPES.join(", ")})`);
  const K = { cx: w / 2, cy: h / 2 - 60, rx: Math.min(470, w * 0.36), ry: 210, ...calm };
  const quiet = (x, y, grow = 1) => clearing(x, y, K.cx, K.cy, K.rx * grow, K.ry * grow, 0.9);
  const ink = () => (C.dusk ? C.lagoon : C.tide);
  const shade = () => (C.dusk ? C.paper : C.shadow);
  const fringe = () => [C["metal-fringe-a"], C["metal-fringe-b"]];
  const out = (cells) => cells.filter((c) => quiet(c.x, c.y, 1.12) > 0.5);

  const r = prng(seed);
  const streams = Array.from({ length: 7 }, (_, i) => ({
    y0: h * (0.12 + i * 0.125) + (r() - 0.5) * 40,
    A: 18 + r() * 30,
    k: 0.0025 + r() * 0.002,
    ph: r() * 6.28,
    w: 0.05 + r() * 0.06,
    pulse: 0.12 + i * 0.01,
  }));
  const S = {
    fish: createShoal({ w, h, seed: seed + 10, count: 7, kinds: ["fish", "minnow", "ray"], colors: C }),
    riders: createShoal({ w, h, seed: seed + 23, kinds: ["minnow", "fish"], count: 3, coral: true, colors: C }),
    birds: createShoal({ w, h: h * 0.5, seed: seed + 3, kinds: ["bird"], count: 4, coral: false, colors: C }),
    islands: createIslands({ w, h, seed: seed - 13, n: 4, colors: C }),
    shoal: createShoal({ w, h, seed, count: 9, colors: C }),
  };

  /** soft pool-floor light: big white cells that CSS blurs into caustic light; `fade(y)` shapes where it falls */
  const causticLight = (L, t, fade = () => 1, gain = 1) => {
    const { cx } = L;
    cx.clearRect(0, 0, L.w, L.h);
    cx.fillStyle = C.dusk ? "oklch(0.85 0.08 200)" : "oklch(1 0 0)";
    for (let y = 0; y < L.h; y += 10)
      for (let x = 0; x < L.w; x += 10) {
        const v = tide(x, y, t, { scale: 380 }) * fade(y);
        if (v < 0.04) continue;
        cx.globalAlpha = Math.min(1, v * (C.dusk ? 0.55 : 1.1) * gain);
        cx.fillRect(x, y, 10, 10);
      }
    cx.globalAlpha = 1;
  };
  /** type that exists only inside the glass */
  const lensType = (L, t, lens) => {
    if (!lens) return;
    field(L.cx, {
      x: lens.x - 20, y: lens.y - 20, w: lens.w + 40, h: lens.h + 40, cell: 9, fs: 10, ramp: RAMP.water, color: ink(), alpha: 0.75,
      fn: (x, y) => (x > lens.x && x < lens.x + lens.w && y > lens.y && y < lens.y + lens.h ? 0.1 + tide(x, y, t, { scale: 380 }) : 0),
      lenses: [lens], lensAlpha: 1, fringe: fringe(),
    });
  };
  /** glyph streamlines with pulses travelling along them */
  const currents = (L, t, alpha = 1) => {
    const { cx } = L;
    cx.font = `400 13px "JetBrains Mono", ui-monospace, Menlo, monospace`;
    cx.textAlign = "center";
    cx.textBaseline = "middle";
    streams.forEach((c, i) => {
      for (let x = 6; x < w; x += 13) {
        const y = c.y0 + Math.sin(x * c.k + t * c.w + c.ph) * c.A;
        const pulse = smoothstep(0.55, 1, 0.5 + 0.5 * Math.sin(x * 0.004 - t * c.pulse + c.ph));
        const a = (0.12 + 0.6 * pulse) * quiet(x, y) * alpha;
        if (a < 0.04) continue;
        const slope = Math.cos(x * c.k + t * c.w + c.ph) * c.A * c.k;
        cx.globalAlpha = a;
        cx.fillStyle = i % 3 === 1 ? C.moss : ink();
        cx.fillText(pulse > 0.7 ? "≈" : Math.abs(slope) > 0.05 ? (slope > 0 ? "\\" : "/") : "~", x, y);
      }
    });
    cx.globalAlpha = 1;
  };
  /** fish riding two of the streams, snapped to the 12 px tile lattice */
  const riders = (L, t) => {
    // each creature (cell.id) rides one stream; its tiles follow the stream's curve, offset by their mask row
    const cells = S.riders.at(t).map((cell) => {
      const c = streams[cell.id % 2 === 0 ? 1 : 5];
      return { ...cell, y: Math.round((c.y0 + Math.sin(cell.x * c.k + t * c.w + c.ph) * c.A + cell.row * 12) / 12) * 12 };
    });
    tiles(L.cx, out(cells), { cell: 12, shadow: shade(), shadowAlpha: 0.14 });
  };

  const recipes = {
    dawn({ soft, sharp }, t, lens) {
      causticLight(soft, t, (y) => smoothstep(h * 0.2, h * 0.85, y), 0.9);
      sharp.cx.clearRect(0, 0, w, h);
      currents(sharp, t, 0.85);
      riders(sharp, t);
      lensType(sharp, t, lens);
    },
    caustic({ soft, sharp }, t, lens) {
      causticLight(soft, t);
      sharp.cx.clearRect(0, 0, w, h);
      lensType(sharp, t, lens);
    },
    currents({ sharp }, t) {
      sharp.cx.clearRect(0, 0, w, h);
      currents(sharp, t);
      riders(sharp, t);
    },
    lagoon({ sharp }, t, lens) {
      const { cx } = sharp;
      cx.clearRect(0, 0, w, h);
      field(cx, {
        w, h, cell: 9, fs: 11, ramp: RAMP.dots, color: C.dusk ? C.lagoon : "oklch(0.99 0.01 200)", alpha: 1, weight: 500,
        fn: (x, y) => Math.min(0.7, 0.1 + tide(x, y, t, { scale: 460 }) * 1.4), mask: (x, y) => 0.3 + 0.7 * quiet(x, y),
        lenses: lens ? [lens] : [], fringe: fringe(),
      });
      tiles(cx, out(S.fish.at(t)), { cell: 12, shadow: C.dusk ? "oklch(0.1 0.03 228)" : "oklch(0.45 0.08 215)", shadowAlpha: 0.22 });
    },
    horizon({ sharp }, t, lens) {
      const { cx } = sharp;
      cx.clearRect(0, 0, w, h);
      const hz = h * 0.76;
      const sx = w * 0.76;
      field(cx, {
        w, h: hz - 20, cell: 12, fs: 12, ramp: RAMP.cloud, color: C.dusk ? C.sky : C.stone, alpha: 0.7,
        fn: (x, y) => cloud(x, y, t, { scale: 1.1 }) * smoothstep(hz, hz * 0.45, y), mask: (x, y) => quiet(x, y, 0.9),
      });
      field(cx, {
        x: sx - 180, y: hz - 180, w: 360, h: 180, cell: 7, fs: 9, weight: 500, ramp: RAMP.dots, color: C.dusk ? C.sand : "oklch(0.72 0.11 70)", alpha: 0.85,
        fn: (x, y) => {
          const d = Math.hypot(x - sx, y - hz);
          return d > 150 ? 0 : 0.12 + 0.55 * (0.5 + 0.5 * Math.cos(d * 0.16 - t * 0.18)) ** 3;
        },
      });
      field(cx, {
        y: hz + 8, w, h: h - hz - 8, cell: 12, fs: 12, ramp: RAMP.water, color: ink(), alpha: 0.75,
        fn: (x, y) => {
          const v = tide(x, (y - hz) * 3.2 + hz, t, { scale: 420 }) * 0.9;
          const col = Math.exp(-(((x - sx + Math.sin(y * 0.05 - t * 0.2) * 14) / (90 + (y - hz) * 0.5)) ** 2));
          return Math.min(0.7, v + col * 0.5 * smoothstep(h, hz, y));
        },
        lenses: lens ? [lens] : [], fringe: fringe(),
      });
      cx.fillStyle = C.line2;
      cx.fillRect(0, hz, w, 1);
      tiles(cx, S.birds.at(t).filter((c) => quiet(c.x, c.y, 0.9) > 0.5), { cell: 9, fs: 7, shadow: shade(), shadowAlpha: 0.08 });
    },
    tide({ sharp }, t, lens) {
      const { cx } = sharp;
      cx.clearRect(0, 0, w, h);
      field(cx, {
        w, h, cell: 14, fs: 13, ramp: RAMP.water, color: ink(), alpha: C.dusk ? 0.55 : 0.68,
        fn: (x, y) => tide(x, y, t), lenses: lens ? [lens] : [], fringe: fringe(), mask: (x, y) => quiet(x, y),
      });
      tiles(cx, S.islands.at(t), { cell: 12, shadow: shade(), shadowAlpha: C.dusk ? 0.45 : 0.14 });
      tiles(cx, out(S.shoal.at(t)), { cell: 12, shadow: shade(), shadowAlpha: C.dusk ? 0.45 : 0.16 });
    },
  };
  return { name, layers: HERO_LAYERS[name], paint: recipes[name] };
}
