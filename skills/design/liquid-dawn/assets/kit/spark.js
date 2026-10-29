// Liquid Dawn kit · spark orb: the agent's presence (the 2-5 reference). A sphere of short radial light streaks,
// densest at the shell, around a white core, slowly turning; when the agent is busy, streaks lengthen and pulse
// outward. Drawn additively on a dark ground, so it lives in a dark glass chip even on a Dawn page. Deterministic:
// the particle set comes from a seed, positions from t.
import { prng, TAU } from "./core.js";

/** The particle set: unit directions (Fibonacci sphere, jittered), shell radii, streak lengths, twinkle phases. Pure. */
export function sparkField(n = 900, seed = 25) {
  const r = prng(seed);
  const golden = Math.PI * (3 - Math.sqrt(5));
  return Array.from({ length: n }, (_, i) => {
    const y = 1 - (2 * (i + 0.5)) / n;
    const rr = Math.sqrt(1 - y * y);
    const th = golden * i + (r() - 0.5) * 0.4;
    return {
      d: [Math.cos(th) * rr, y, Math.sin(th) * rr],
      rad: 0.35 + 0.65 * Math.sqrt(r()),
      len: 0.04 + 0.16 * r() ** 2,
      ph: r() * TAU,
      w: 0.4 + r() * 0.9,
    };
  });
}

/**
 * sparkOrb(cx, field, { x, y, R, t, busy, tint })
 * busy ∈ [0, 1]: 0 at rest (a calm glowing sphere), 1 thinking (streaks lengthen, a pulse travels outward).
 */
export function sparkOrb(cx, field, { x, y, R, t, busy = 0, tint = [196, 220, 255], light = false }) {
  const g0 = cx.globalAlpha;
  const op = cx.globalCompositeOperation;
  if (light) {
    // Daylight glass mode: a soft pearl-lagoon aura so bright cobalt/tide & white streaks read with high contrast
    const aura = cx.createRadialGradient(x, y, 0, x, y, R * 1.45);
    aura.addColorStop(0, "rgba(18, 92, 118, 0.22)");
    aura.addColorStop(0.55, "rgba(38, 128, 165, 0.12)");
    aura.addColorStop(1, "rgba(38, 128, 165, 0)");
    cx.fillStyle = aura;
    cx.fillRect(x - R * 1.5, y - R * 1.5, R * 3, R * 3);
  }
  cx.globalCompositeOperation = light ? "source-over" : "lighter";
  // halo + core
  const halo = cx.createRadialGradient(x, y, 0, x, y, R * 1.6);
  halo.addColorStop(0, `rgba(${tint[0]},${tint[1]},${tint[2]},0.32)`);
  halo.addColorStop(0.35, `rgba(${tint[0]},${tint[1]},${tint[2]},0.08)`);
  halo.addColorStop(1, "rgba(0,0,0,0)");
  cx.fillStyle = halo;
  cx.fillRect(x - R * 1.6, y - R * 1.6, R * 3.2, R * 3.2);
  const rot = t * 0.35;
  const ca = Math.cos(rot);
  const sa = Math.sin(rot);
  const tilt = 0.35;
  const ct = Math.cos(tilt);
  const st = Math.sin(tilt);
  cx.lineCap = "round";
  for (const p of field) {
    // rotate about y, then tilt about x
    let [dx, dy, dz] = p.d;
    [dx, dz] = [dx * ca + dz * sa, -dx * sa + dz * ca];
    [dy, dz] = [dy * ct - dz * st, dy * st + dz * ct];
    const pulse = busy * Math.max(0, Math.sin(t * 2.4 - p.rad * 6 + p.ph * 0.2));
    const r1 = R * Math.min(1, p.rad + 0.06 * pulse);
    const r0 = r1 - R * (p.len * (1 + 1.6 * busy) + 0.05 * pulse);
    const depth = 0.35 + 0.65 * (dz * 0.5 + 0.5);
    const tw = 0.55 + 0.45 * Math.sin(t * p.w * 2 + p.ph);
    const a = depth * tw * (0.25 + 0.75 * p.rad ** 2) * (0.6 + 0.4 * busy + 0.5 * pulse);
    if (a < 0.03) continue;
    cx.globalAlpha = g0 * Math.min(1, a);
    cx.strokeStyle = `rgb(${tint[0]},${tint[1]},${tint[2]})`;
    cx.lineWidth = 0.6 + depth * 0.9;
    cx.beginPath();
    cx.moveTo(x + dx * r0, y + dy * r0);
    cx.lineTo(x + dx * r1, y + dy * r1);
    cx.stroke();
  }
  const core = cx.createRadialGradient(x, y, 0, x, y, R * 0.42);
  core.addColorStop(0, "rgba(255,255,255,0.95)");
  core.addColorStop(0.4, `rgba(${tint[0]},${tint[1]},${tint[2]},0.4)`);
  core.addColorStop(1, "rgba(0,0,0,0)");
  cx.globalAlpha = g0 * (0.75 + 0.25 * busy);
  cx.fillStyle = core;
  cx.fillRect(x - R, y - R, R * 2, R * 2);
  cx.globalAlpha = g0;
  cx.globalCompositeOperation = op;
}
