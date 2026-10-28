// Liquid Midnight render kit · liquid metal: a specular band that travels along paths and around rings,
// with spectral fringes (cyan, magenta, gold) at the highlights.
// Extracted from broomva/agent-workspaces deck/index.html @187972f, lines 1422-1446 (Apache-2.0).
import { C, clamp, clear, ctx, lerp, TAU } from "./core.js";

/** Global switch: when false, ribbons fall back to a plain two-colour gradient (the deck's "no metal" comparison). */
export let METAL = true;
export function setMetal(on) {
  METAL = !!on;
}

/* Sweep phase along a path: one pass every 1.3/0.21 ≈ 6.2 s, offset per path by its seed so sweeps never sync. */
const phase = (t, seed) => ((((t * 0.21 + seed * 0.1373) % 1.3) + 1.3) % 1.3) - 0.15;

/** steel → shine → steel band travelling from p0 to p3, tinted by the edge colours cA → cB */
export function metalGrad(p, cA, cB, t, seed = 0) {
  const g = ctx.createLinearGradient(p[0][0], p[0][1], p[3][0], p[3][1]);
  const ph = phase(t, seed);
  const w = 0.1;
  let lo = 0;
  for (const [o, c] of [
    [0, cA],
    [ph - w * 1.9, cA],
    [ph - w * 0.55, C.steel],
    [ph, C.shine],
    [ph + w * 0.45, C.steel],
    [ph + w * 1.7, cB],
    [1, cB],
  ]) {
    const oo = clamp(Math.max(lo, o), 0, 1);
    g.addColorStop(oo, c);
    lo = oo;
  }
  return g;
}

/** a narrow band of colour c riding the same sweep (used for the fringe passes) */
export function fringe(p, c, t, seed) {
  const g = ctx.createLinearGradient(p[0][0], p[0][1], p[3][0], p[3][1]);
  const ph = phase(t, seed);
  let lo = 0;
  for (const [o, k] of [
    [0, 0],
    [ph - 0.08, 0],
    [ph, 1],
    [ph + 0.08, 0],
    [1, 0],
  ]) {
    const oo = clamp(Math.max(lo, o), 0, 1);
    g.addColorStop(oo, k ? c : clear(c));
    lo = oo;
  }
  return g;
}

/** Multi-strand ribbon along bézier p: n strands spreading from s0 to s1 px, breathing by amp px.
 *  In metal mode the strands carry the travelling specular, a bright core fringe and ±1.2 px spectral fringes. */
export function ribbon(p, n, s0, s1, cA, cB, a, t, amp = 5, lw = 1, dash) {
  if (a <= 0.004) return;
  const g0 = ctx.globalAlpha; // the caller's alpha: everything below multiplies it and it is restored at the end
  a *= g0;
  const dx = p[3][0] - p[0][0];
  const dy = p[3][1] - p[0][1];
  const L = Math.hypot(dx, dy) || 1;
  const nx = -dy / L;
  const ny = dx / L;
  const seed = (p[0][0] * 0.013 + p[0][1] * 0.007) % 7;
  const path = (o0, o1, o2, o3) => {
    ctx.beginPath();
    ctx.moveTo(p[0][0] + nx * o0, p[0][1] + ny * o0);
    ctx.bezierCurveTo(p[1][0] + nx * o1, p[1][1] + ny * o1, p[2][0] + nx * o2, p[2][1] + ny * o2, p[3][0] + nx * o3, p[3][1] + ny * o3);
  };
  if (METAL && !dash) ctx.strokeStyle = metalGrad(p, cA, cB, t, seed);
  else {
    const g = ctx.createLinearGradient(p[0][0], p[0][1], p[3][0], p[3][1]);
    g.addColorStop(0, cA);
    g.addColorStop(1, cB);
    ctx.strokeStyle = g;
  }
  ctx.lineWidth = lw;
  ctx.globalAlpha = a;
  if (dash) ctx.setLineDash(dash);
  for (let i = 0; i < n; i++) {
    const k = n === 1 ? 0 : i / (n - 1) - 0.5;
    const w = Math.sin(t * 0.7 + i * 0.45) * amp * k * 2;
    const o0 = k * s0;
    const o3 = k * s1;
    path(o0, lerp(o0, o3, 0.33) + w, lerp(o0, o3, 0.67) - w, o3);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  if (METAL && !dash) {
    ctx.strokeStyle = fringe(p, C.shine, t, seed);
    ctx.globalAlpha = Math.min(1, a * 2.6);
    ctx.lineWidth = lw * 1.7;
    path(0, 0, 0, 0);
    ctx.stroke();
    ctx.lineWidth = lw;
  }
  if (METAL && !dash && lw >= 0.8) {
    const op = ctx.globalCompositeOperation;
    ctx.globalCompositeOperation = C.day ? "source-over" : "lighter";
    ctx.lineWidth = Math.max(0.8, lw * 0.9);
    for (const [c, off] of [
      [C.fringeA, 1.2],
      [C.fringeB, -1.2],
    ]) {
      ctx.strokeStyle = fringe(p, c, t, seed);
      ctx.globalAlpha = a * 0.55;
      path(off, off, off, off);
      ctx.stroke();
    }
    ctx.globalCompositeOperation = op;
  }
  ctx.globalAlpha = g0;
}

/** Liquid-metal ring (ellipse R × ry) with two travelling speculars (cos^10 and cos^16 lobes, the second at 0.63×
 *  speed) and spectral dispersion where a highlight is bright (v > 0.18). spd is radians per second. */
export function metalRing(x, y, R, t, lw = 2, a = 1, ry = R, spd = 0.9) {
  const g = ctx.globalAlpha;
  const S = 160;
  const op = ctx.globalCompositeOperation;
  ctx.lineWidth = lw;
  ctx.globalAlpha = g * a * 0.85;
  ctx.strokeStyle = C.steel;
  ctx.beginPath();
  ctx.ellipse(x, y, R, ry, 0, 0, TAU);
  ctx.stroke();
  for (let i = 0; i < S; i++) {
    const a0 = (i / S) * TAU;
    const a1 = ((i + 1.25) / S) * TAU;
    const v = (0.5 + 0.5 * Math.cos(a0 - t * spd)) ** 10 + 0.6 * (0.5 + 0.5 * Math.cos(a0 + 2.6 - t * spd * 0.63)) ** 16;
    if (v < 0.03) continue;
    ctx.globalAlpha = g * a * Math.min(1, v);
    ctx.strokeStyle = C.shine;
    ctx.beginPath();
    ctx.ellipse(x, y, R, ry, 0, a0, a1);
    ctx.stroke();
    if (v > 0.18) {
      ctx.globalCompositeOperation = C.day ? "source-over" : "lighter";
      ctx.lineWidth = lw * 0.7;
      for (const [c, d] of [
        [C.fringeA, -lw * 0.95],
        [C.fringeB, lw * 0.95],
        [C.fringeC, lw * 1.9],
      ]) {
        ctx.globalAlpha = g * a * v * 0.55;
        ctx.strokeStyle = c;
        ctx.beginPath();
        ctx.ellipse(x, y, R + d, ry + (d * ry) / R, 0, a0, a1);
        ctx.stroke();
      }
      ctx.globalCompositeOperation = op;
      ctx.lineWidth = lw;
    }
  }
  ctx.globalAlpha = g;
}
