// Liquid Dawn kit · core: maths, seeded PRNG, value noise, springs, the motion switch.
// Pure and DOM-free except the motion switch, which reads matchMedia when it exists, so it imports in Node for tests.
// Pattern lineage: Liquid Midnight's kit/core.js (same spring and render contract); rewritten for this system.

export const TAU = Math.PI * 2;
export const lerp = (a, b, t) => a + (b - a) * t;
export const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
export const smooth = (t) => t * t * (3 - 2 * t);
export const smoothstep = (a, b, v) => smooth(clamp((v - a) / (b - a)));
export const easeOutCubic = (t) => 1 - (1 - t) ** 3;
/** A beat: 0→1 over [t0, t0+d], eased. Use for time-addressed reveals: alpha = beat(t, 1.2, .8). */
export const beat = (t, t0, d, ease = easeOutCubic) => ease(clamp((t - t0) / d));

/* ── seeded PRNG (mulberry32). reseed() at t = 0 so every frame is a pure function of t ── */
let SEED = 0xda3e;
export function reseed(v = 0xda3e) {
  SEED = v >>> 0;
}
export function R0() {
  SEED = (SEED + 0x6d2b79f5) | 0;
  let t = Math.imul(SEED ^ (SEED >>> 15), 1 | SEED);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
export const rnd = (a = 1, b) => (b === undefined ? R0() * a : a + R0() * (b - a));
/** A private generator (does not touch the shared stream): build static scene data from a seed. */
export function prng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ── value noise: stateless integer hash, smooth-interpolated. Same input → same output on every machine. ── */
function hash2(ix, iy, seed) {
  let h = Math.imul(ix, 0x27d4eb2d) ^ Math.imul(iy, 0x165667b1) ^ Math.imul(seed | 0, 0x9e3779b1);
  h = Math.imul(h ^ (h >>> 15), 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
/** 2D value noise in [0, 1]. */
export function noise2(x, y, seed = 0) {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = smooth(x - ix);
  const fy = smooth(y - iy);
  const a = hash2(ix, iy, seed);
  const b = hash2(ix + 1, iy, seed);
  const c = hash2(ix, iy + 1, seed);
  const d = hash2(ix + 1, iy + 1, seed);
  return lerp(lerp(a, b, fx), lerp(c, d, fx), fy);
}
/** Fractal noise, `oct` octaves, normalised to [0, 1]. */
export function fbm(x, y, oct = 4, seed = 0) {
  let v = 0;
  let amp = 0.5;
  let norm = 0;
  for (let i = 0; i < oct; i++) {
    v += amp * noise2(x, y, seed + i * 17);
    norm += amp;
    x = x * 2.03 + 11.7;
    y = y * 2.03 - 7.3;
    amp *= 0.5;
  }
  return v / norm;
}

/* ── motion switch: reduced motion freezes the clock, springs snap ── */
const RMQ = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
export let MOTION = RMQ ? !RMQ.matches : true;
let pinned = false;
function reflect() {
  if (typeof document !== "undefined" && document.documentElement?.dataset) document.documentElement.dataset.ldMotion = MOTION ? "on" : "off";
}
/** Pin motion on/off (capture pages pin it on); setMotion(null) hands control back to the OS setting. */
export function setMotion(on) {
  pinned = on !== null && on !== undefined;
  MOTION = pinned ? !!on : RMQ ? !RMQ.matches : true;
  reflect();
}
reflect();
RMQ?.addEventListener?.("change", (e) => {
  if (!pinned) MOTION = !e.matches;
  reflect();
});

/** Spring with Apple-style parameters: response r (s per cycle), damping ratio z (1 = critical). Interruptible:
 *  it animates from the live value. Integrated in ≤ 8 ms substeps. */
export class Sp {
  constructor(v = 0) {
    this.v = v;
    this.t = v;
    this.d = 0;
  }
  set(t) {
    this.t = t;
    return this;
  }
  snap(v) {
    this.v = this.t = v;
    this.d = 0;
    return this;
  }
  step(dt, r = 0.5, z = 1) {
    if (!MOTION || dt === 0) {
      if (!MOTION) this.snap(this.t);
      return this.v;
    }
    const w = TAU / r;
    let n = Math.ceil(dt / 0.008) || 1;
    const h = dt / n;
    while (n--) {
      this.d += (-w * w * (this.v - this.t) - 2 * z * w * this.d) * h;
      this.v += this.d * h;
    }
    return this.v;
  }
}

/** Follow the OS colour scheme: sets data-ld-mode to "dawn" or "dusk" on el now and on every change, then calls
 *  onChange(mode) (re-read colours, rebuild atlases, invalidate the loop there). Returns an unsubscribe function.
 *  This is the only "auto" mode: the CSS keys Dusk on the literal attribute, so the attribute is always resolved. */
export function followOS(el = document.documentElement, onChange = () => {}) {
  const mq = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
  const apply = () => {
    el.dataset.ldMode = mq?.matches ? "dusk" : "dawn";
    onChange(el.dataset.ldMode);
  };
  apply();
  mq?.addEventListener?.("change", apply);
  return () => mq?.removeEventListener?.("change", apply);
}

/** Resolve the --ld-* colour tokens for canvas use. Call again after a mode switch. */
export const C = {};
export function readColors(el = document.documentElement) {
  const s = getComputedStyle(el);
  for (const k of ["paper", "surface", "sunk", "ink", "ink2", "ink3", "line", "line2", "tide", "shadow", "sky", "lagoon", "moss", "sand", "stone", "coral"])
    C[k] = s.getPropertyValue(`--ld-${k}`).trim();
  for (const k of ["steel", "shine", "glint", "fringe-a", "fringe-b", "fringe-c"]) C[`metal-${k}`] = s.getPropertyValue(`--ld-metal-${k}`).trim();
  C.dusk = (el.closest?.("[data-ld-mode]")?.dataset.ldMode ?? "dawn") === "dusk";
  return C;
}

export const FONT = {
  display: 'Manrope,"SF Pro Display",ui-sans-serif,system-ui,sans-serif',
  text: 'Inter,"SF Pro Text",ui-sans-serif,system-ui,sans-serif',
  mono: '"JetBrains Mono",ui-monospace,Menlo,monospace',
};
