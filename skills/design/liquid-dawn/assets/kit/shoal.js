// Liquid Dawn kit · shoals: creatures and islands built from glyph tiles that drift through a field (the shark
// references). Each creature is an ASCII mask; every non-space character is one tile, and the character picks the
// tone. Positions are pure functions of t and snap to the tile lattice, so creatures move the way the references do:
// in calm lattice steps, never smeared. Static data comes from prng(seed), so a scene is reproducible.
import { fbm, prng, TAU } from "./core.js";

/** Masks: a = body, b = light body, c = belly or wing light, e = eye, s = accent. Facing right. */
export const MASKS = {
  fish: ["     aa      ", "a  aaaaaaa   ", "aaabbbbbbbaa ", " aabbbbbbbbea", "aaabbccccccaa", "a   accccc   "],
  minnow: ["a aab ", " abbbe", "a acc "],
  ray: ["      aa      ", "   aaaaaaaa   ", "aaabbbbbbbbaaa", "   abccccba   ", "      ss      ", "      s       ", "       s      "],
  bird: ["a       a", " aa   aa ", "   abba  ", "    bb   "],
  leaf: ["    ab", "   abb", "  abb ", " abc  ", "abc   ", "s     "],
  pebble: [" aab ", "abbbc", " acc "],
};

/** Tone maps per kind: which palette slots each mask letter uses. Values are token keys from readColors(). */
const TONES = {
  fish: { a: "lagoon", b: "sky", c: "surface", e: "ink", s: "sand" },
  minnow: { a: "stone", b: "sky", c: "surface" },
  ray: { a: "sky", b: "lagoon", c: "surface", s: "stone" },
  bird: { a: "stone", b: "sky" },
  leaf: { a: "moss", b: "sand", c: "surface", s: "stone" },
  pebble: { a: "stone", b: "sunk", c: "surface" },
  coral: { a: "coral", b: "sand", c: "surface", e: "ink", s: "sand" },
};
const GLYPHS = { fish: "~≈-", minnow: "-~", ray: "≈~", bird: "^v", leaf: "/'", pebble: "o·", coral: "~*" };

/**
 * createShoal({ w, h, seed, kinds, count, cell }) → { at(t) → cells[] } for ascii.tiles().
 *  kinds: mask names from MASKS (repeat a name to weight it); an unknown name throws. coral: true recolours the
 *  first creature coral, so a scene has exactly one. Creatures cross the width at 8-22 px/s and bob ≤ 1.5 cells,
 *  wrapping fully off-screen (the margin is the creature's own width plus a cell); facing follows direction.
 */
export function createShoal({ w, h, seed = 21, kinds = ["fish", "minnow", "minnow", "ray"], count = 7, cell = 12, coral = true, colors }) {
  if (!kinds.length) throw new Error("createShoal: kinds is empty");
  for (const k of kinds) if (!MASKS[k]) throw new Error(`createShoal: unknown kind "${k}" (one of ${Object.keys(MASKS).join(", ")})`);
  const r = prng(seed);
  const C = colors;
  const list = Array.from({ length: count }, (_, i) => {
    const kind = kinds[Math.floor(r() * kinds.length)];
    const dir = r() < 0.6 ? 1 : -1;
    const tone = coral && i === 0 ? "coral" : kind;
    return {
      kind,
      tone,
      dir,
      mask: MASKS[kind],
      speed: (8 + r() * 14) * dir,
      x0: r() * w,
      y0: (0.08 + r() * 0.84) * h,
      bob: (0.4 + r() * 1.1) * cell,
      bobW: 0.18 + r() * 0.2,
      ph: r() * TAU,
      seed: Math.floor(r() * 1e9),
    };
  });
  for (const k of [...list]) {
    if (k.kind !== "minnow") continue;
    const m = 2 + Math.floor(r() * 3);
    for (let j = 1; j <= m; j++)
      list.push({ ...k, tone: "minnow", x0: k.x0 - k.dir * j * (5 + r() * 3) * cell, y0: k.y0 + (r() - 0.5) * 6 * cell, ph: k.ph + j * 0.6, seed: Math.floor(r() * 1e9) });
  }
  return {
    list,
    at(t) {
      const out = [];
      list.forEach((k, id) => {
        const margin = (k.mask[0].length + 1) * cell;
        const span = w + 2 * margin;
        const raw = k.x0 + k.speed * t;
        const x = ((((raw + margin) % span) + span) % span) - margin;
        const y = k.y0 + Math.sin(t * k.bobW + k.ph) * k.bob;
        const sx = Math.round(x / cell) * cell;
        const sy = Math.round(y / cell) * cell;
        const tones = TONES[k.tone];
        const gl = GLYPHS[k.tone] ?? GLYPHS[k.kind];
        const rr = prng(k.seed);
        k.mask.forEach((row, j) => {
          [...row].forEach((ch, i) => {
            if (ch === " ") return;
            const col = k.dir > 0 ? i : row.length - 1 - i;
            const pick = rr();
            out.push({
              id,
              row: j - (k.mask.length - 1) / 2,
              x: sx + col * cell,
              y: sy + j * cell,
              fill: C[tones[ch]] ?? C.stone,
              ink: ch === "c" ? C.ink3 : C.surface,
              ch: ch === "e" ? "o" : pick < 0.55 ? gl[Math.floor(pick * 10) % gl.length] : "",
              a: 0.92,
            });
          });
        });
      });
      return out;
    },
  };
}

/**
 * createIslands({ w, h, seed, n, cell }) → { at(t) → cells[] }: archipelago tiles from a thresholded noise blob per
 * island (sand rim, moss interior, a few `t` trees), drifting together at 3 px/s like a slow camera over the sea.
 */
export function createIslands({ w, h, seed = 5, n = 4, cell = 12, colors, drift = 3 }) {
  const r = prng(seed);
  const C = colors;
  const isl = Array.from({ length: n }, () => ({
    cx: r() * w,
    cy: r() * h,
    rx: (4 + r() * 6) * cell,
    ry: (3 + r() * 5) * cell,
    s: Math.floor(r() * 1000),
  }));
  return {
    at(t) {
      const out = [];
      for (const I of isl) {
        const margin = I.rx + 4 * cell;
        const span = w + 2 * margin;
        const ox = ((((I.cx + drift * t + margin) % span) + span) % span) - margin;
        const bx = Math.round(ox / cell) * cell;
        const by = Math.round(I.cy / cell) * cell;
        for (let j = -Math.ceil(I.ry / cell) - 2; j <= Math.ceil(I.ry / cell) + 2; j++)
          for (let i = -Math.ceil(I.rx / cell) - 2; i <= Math.ceil(I.rx / cell) + 2; i++) {
            const e = Math.hypot((i * cell) / I.rx, (j * cell) / I.ry);
            const n2 = fbm(i * 0.35 + I.s, j * 0.35, 3, I.s);
            const v = 1 - e + (n2 - 0.5) * 0.9;
            if (v < 0) continue;
            const inner = v > 0.32;
            const tree = inner && n2 > 0.62;
            out.push({
              x: bx + i * cell,
              y: by + j * cell,
              fill: tree ? C.moss : inner ? C.moss : C.sand,
              ink: tree ? C.ink : C.ink3,
              ch: tree ? "t" : inner ? (n2 > 0.5 ? "%" : "") : n2 > 0.55 ? "·" : "",
              a: inner ? 0.82 : 0.9,
            });
          }
      }
      return out;
    },
  };
}
