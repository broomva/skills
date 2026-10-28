// Liquid Midnight render kit · core: maths, seeded PRNG, springs, béziers, colour helpers, canvas primitives.
// Extracted from broomva/agent-workspaces deck/index.html @187972f, lines 1368-1421 (Apache-2.0).
// Change from the deck: the deck kept `ctx`, `C` and `MOTION` as page globals; here they are module state set through
// use(), readColors() and setMotion(), so the kit runs on any canvas in any framework.

/** The 2D context every draw call targets. Swap it with use(ctx) (the deck swapped it the same way for the background). */
export let ctx = null;
export function use(c) {
  const prev = ctx;
  ctx = c;
  return prev;
}

/** Resolved colour tokens for canvas use. Call readColors() after the theme changes. */
export const C = {};
export function readColors(el = document.documentElement) {
  const s = getComputedStyle(el);
  for (const k of ["t1", "t2", "t3", "line", "line2", "ai", "blue", "green", "violet", "cyan", "warm", "coral", "gold", "deep", "surface", "elev"])
    C[k] = s.getPropertyValue(`--lm-${k}`).trim();
  for (const k of ["steel", "shine", "fringeA", "fringeB", "fringeC"])
    C[k] = s.getPropertyValue(`--lm-metal-${k.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`).trim();
  // nearest mode wins: a night region nested in a day page reads as night
  C.day = (el.closest?.("[data-lm-mode]")?.dataset.lmMode ?? "night") === "day";
  return C;
}

/** Reduced motion: springs snap to target, the rim angle and ASCII flow freeze. */
const RMQ = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
export let MOTION = RMQ ? !RMQ.matches : true;
let motionPinned = false;
/** Pin motion on or off (overrides the OS setting until setMotion(null) hands control back to it). */
export function setMotion(on) {
  motionPinned = on !== null && on !== undefined;
  MOTION = motionPinned ? !!on : RMQ ? !RMQ.matches : true;
}
RMQ?.addEventListener?.("change", (e) => {
  if (!motionPinned) MOTION = !e.matches;
});

export const TAU = Math.PI * 2;
export const lerp = (a, b, t) => a + (b - a) * t;
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const smooth = (t) => t * t * (3 - 2 * t);
export const easeOutCubic = (t) => 1 - (1 - t) ** 3;
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
/** A beat: 0→1 over [t0, t0+d], eased. Use for time-addressed reveals: alpha = beat(t, 2.0, .6). */
export const beat = (t, t0, d, ease = easeOutCubic) => ease(clamp((t - t0) / d, 0, 1));

/* seeded PRNG (mulberry32): reseed per scene so every frame is a pure function of t */
let SEED = 0x5eed;
export function reseed(v) {
  SEED = v >>> 0;
}
export function R0() {
  SEED = (SEED + 0x6d2b79f5) | 0;
  let t = Math.imul(SEED ^ (SEED >>> 15), 1 | SEED);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
export const rnd = (a = 1, b) => (b === undefined ? R0() * a : a + R0() * (b - a));

export const FONT = {
  s: "Inter,ui-sans-serif,system-ui,sans-serif",
  d: 'Raleway,"Avenir Next",ui-sans-serif,sans-serif',
  m: '"JetBrains Mono",ui-monospace,Menlo,monospace',
};

/* springs settle at ±1e-25 and the canvas ignores out-of-range alpha (keeping the previous one), so clamp at the source */
let alphaClamped = false;
export function installAlphaClamp() {
  if (alphaClamped || typeof CanvasRenderingContext2D === "undefined") return;
  alphaClamped = true;
  const d = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, "globalAlpha");
  Object.defineProperty(CanvasRenderingContext2D.prototype, "globalAlpha", {
    get() {
      return d.get.call(this);
    },
    set(v) {
      d.set.call(this, clamp(+v || 0, 0, 1));
    },
  });
}

/** Spring with Apple-style parameters: response r (seconds per cycle) and damping ratio z (1 = critical).
 *  Animates from the live value, so it is interruptible. Integrated in ≤8 ms substeps. */
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
  step(dt, r = 0.42, z = 1) {
    if (!MOTION) {
      this.v = this.t;
      this.d = 0;
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

/* cubic béziers as [p0, c1, c2, p3] */
export const bz = (p, t) => {
  const u = 1 - t;
  return [
    u * u * u * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t * t * t * p[3][0],
    u * u * u * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t * t * t * p[3][1],
  ];
};
/** horizontal S-curve between two points */
export const hc = (a, b, k = 0.5) => {
  const d = (b[0] - a[0]) * k;
  return [a, [a[0] + d, a[1]], [b[0] - d, b[1]], b];
};
/** vertical S-curve */
export const vc = (a, b, k = 0.5) => {
  const d = (b[1] - a[1]) * k;
  return [a, [a[0], a[1] + d], [b[0], b[1] - d], b];
};
/** arc bent sideways by s (fraction of the chord) */
export const bend = (a, b, s) => {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const nx = -dy * s;
  const ny = dx * s;
  return [a, [a[0] + dx * 0.33 + nx, a[1] + dy * 0.33 + ny], [a[0] + dx * 0.67 + nx, a[1] + dy * 0.67 + ny], b];
};
/** point on a path, pushed sideways along the chord normal (to follow a ribbon's spread) */
export function along(p, u, off = 0) {
  u = clamp(u, 0, 1);
  const [x, y] = bz(p, u);
  const dx = p[3][0] - p[0][0];
  const dy = p[3][1] - p[0][1];
  const L = Math.hypot(dx, dy) || 1;
  return [x - (dy / L) * off, y + (dx / L) * off];
}

/* colour with alpha. Handles oklch() (the canonical tokens) and the #rgb / #rrggbb / #rrggbbaa hex fallbacks, so the kit
   keeps its alpha stops in browsers that only get the hex tokens. Anything else is returned unchanged (alpha ignored). */
function hexAlpha(c, a) {
  let h = c.slice(1);
  if (h.length === 3 || h.length === 4) h = [...h].map((x) => x + x).join("");
  if (!/^[0-9a-f]{6}([0-9a-f]{2})?$/i.test(h)) return null;
  const n = (i) => Number.parseInt(h.slice(i, i + 2), 16);
  const base = h.length === 8 ? n(6) / 255 : 1;
  return `rgba(${n(0)}, ${n(2)}, ${n(4)}, ${+(base * a).toFixed(4)})`;
}
export const al = (c, a) => {
  if (c.startsWith("oklch(") && !c.includes("/")) return c.replace(/\)$/, ` / ${a})`);
  if (c.startsWith("#")) return hexAlpha(c, a) ?? c;
  return c;
};
/* fade to the same hue at zero alpha: 'transparent' is black and greys out halos on light surfaces */
export const clear = (c) => {
  const z = al(c, 0);
  return z === c ? "transparent" : z;
};

export function glow(x, y, r, c, a = 0.4) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, c);
  g.addColorStop(1, clear(c));
  const o = ctx.globalAlpha;
  ctx.globalAlpha = o * a;
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TAU);
  ctx.fill();
  ctx.globalAlpha = o;
}
export function dot(x, y, r, c, g = 0) {
  if (g) glow(x, y, r * g, c, 0.35);
  ctx.fillStyle = c;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TAU);
  ctx.fill();
}
/** text: T('label', x, y, {s: size, w: weight, f: FONT.d, c: colour, a: alpha, al: 'center', ls: letterSpacingPx}) */
export function T(s, x, y, o = {}) {
  ctx.font = `${o.w || 500} ${o.s || 16}px ${o.f || FONT.m}`;
  ctx.fillStyle = o.c || C.t1;
  const g = ctx.globalAlpha;
  ctx.globalAlpha = g * (o.a ?? 1);
  ctx.textAlign = o.al || "left";
  ctx.textBaseline = o.bl || "middle";
  ctx.letterSpacing = `${o.ls ?? (o.f ? 0 : 0.6)}px`;
  ctx.fillText(s, x, y);
  ctx.letterSpacing = "0px";
  ctx.globalAlpha = g;
}
/** marching dashes: reserved for the active / build route */
export function march(p, c, a, t, lw = 1.6, speed = 28) {
  if (a <= 0.004) return;
  const g = ctx.globalAlpha;
  ctx.strokeStyle = c;
  ctx.globalAlpha = g * a;
  ctx.lineWidth = lw;
  ctx.setLineDash([6, 8]);
  ctx.lineDashOffset = -t * speed;
  ctx.beginPath();
  ctx.moveTo(...p[0]);
  ctx.bezierCurveTo(...p[1], ...p[2], ...p[3]);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.lineDashOffset = 0;
  ctx.globalAlpha = g;
}
export function rrect(x, y, w, h, r, stroke, fill, lw = 1.3) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lw;
    ctx.stroke();
  }
}
/** glass drawn in canvas, for frames that must stay crisp: frosted fill, top sheen, rim */
export function gpanel(x, y, w, h, r, a = 1, tint) {
  const g = ctx.globalAlpha;
  ctx.fillStyle = tint || C.surface;
  ctx.globalAlpha = g * a * 0.6;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  ctx.fill();
  const s = ctx.createLinearGradient(x, y, x, y + h * 0.5);
  s.addColorStop(0, "oklch(1 0 0 / .07)");
  s.addColorStop(1, "oklch(1 0 0 / 0)");
  ctx.globalAlpha = g * a;
  ctx.fillStyle = s;
  ctx.fill();
  const rg = ctx.createLinearGradient(x, y, x + w, y + h);
  rg.addColorStop(0, "oklch(1 0 0 / .32)");
  rg.addColorStop(0.35, "oklch(1 0 0 / .06)");
  rg.addColorStop(0.7, "oklch(1 0 0 / .04)");
  rg.addColorStop(1, "oklch(1 0 0 / .16)");
  ctx.strokeStyle = C.day ? C.line2 : rg;
  ctx.lineWidth = 1.2;
  ctx.stroke();
  ctx.globalAlpha = g;
}

/** Edge particles {u, v}: alpha follows sin(πu) so they appear and vanish on the edge; recycled at u ≥ 1.
 *  Seeded so a still frame is never empty. fade: 'full' | 'soft' (stays visible through a node) | 'none'. */
export class Flow {
  constructor(rate, mk, seed = 0, fade = "full") {
    this.p = [];
    this.acc = 0;
    this.rate = rate;
    this.mk = mk;
    this.fade = fade;
    for (let i = 0; i < seed; i++) {
      const q = mk();
      if (q) {
        q.u = R0();
        this.p.push(q);
      }
    }
  }
  /* spawn tolerance: n × (1/60) at rate 60 sums to 0.99999… in floating point, which would lose a spawn */
  /** integrate only (fixed-step loops): spawn by rate, move by v, recycle at u ≥ 1 unless end(q) returns false */
  advance(dt, end) {
    this.acc += dt * this.rate;
    while (this.acc >= 1 - 1e-9) {
      this.acc--;
      const q = this.mk();
      if (q) this.p.push(q);
    }
    for (const q of this.p) {
      q.u += q.v * dt;
      if (q.u >= 1) q.dead = !(end && end(q) === false);
    }
    this.p = this.p.filter((q) => !q.dead);
  }
  /** paint only: pure in the particle state */
  draw(path, draw) {
    for (const q of this.p) {
      const p = path(q);
      if (!p) continue;
      const g = ctx.globalAlpha;
      const s = Math.sin(Math.PI * clamp(q.u, 0, 1));
      ctx.globalAlpha = g * (this.fade === "full" ? s : this.fade === "soft" ? 0.35 + 0.65 * s : 1);
      draw(q, p);
      ctx.globalAlpha = g;
    }
  }
  /** the deck's combined form: integrate and paint in one call */
  run(dt, path, draw, end) {
    this.acc += dt * this.rate;
    while (this.acc >= 1 - 1e-9) {
      this.acc--;
      const q = this.mk();
      if (q) this.p.push(q);
    }
    for (const q of this.p) {
      q.u += q.v * dt;
      if (q.u >= 1) {
        q.dead = !(end && end(q) === false);
        if (q.dead) continue;
      }
      const p = path(q);
      if (!p) {
        q.dead = 1;
        continue;
      }
      const g = ctx.globalAlpha;
      const s = Math.sin(Math.PI * clamp(q.u, 0, 1));
      ctx.globalAlpha = g * (this.fade === "full" ? s : this.fade === "soft" ? 0.35 + 0.65 * s : 1);
      draw(q, p);
      ctx.globalAlpha = g;
    }
    this.p = this.p.filter((q) => !q.dead);
  }
}
