// Liquid Midnight render kit · the frame loop and the render contract.
// Contract (from the keynote's capture mode, deck/index.html @187972f lines 2760 and 2810-2822): every frame is a pure
// function of t. State that integrates (springs, particles) is advanced in fixed 1/60 s steps from t = 0, the PRNG is
// reseeded at t = 0, and the rim angle is derived from t, so window.renderAt(t) paints the same pixels on every machine
// and a headless browser can render any frame to video.
// Reduced motion (deck lines 2786-2800): the live loop seeks once to a settled still frame (`still`, 5 s by default) and
// then holds t there. It keeps calling step(0, t) every frame, so springs (which snap when MOTION is off) still follow
// interaction (a clicked segment, a toggled mode) while nothing animates. renderAt still seeks: a capture asks for a frame.
// Captures are machine-independent only with motion ON: a page in capture mode (?t=) should setMotion(true) unless the
// capture explicitly asks for the reduced-motion still (the specimen and the skill's template do this).
import { MOTION, reseed } from "./core.js";

export const STEP = 1 / 60;
/** Longest seek renderAt accepts (s). A seek replays every fixed step from 0, so an unbounded t never returns. */
export const MAX_T = 3600;

/** Rim speed from the token (--lm-ua-speed, generated from tokens.json motion.ua.degPerSecond); 40°/s if unset. */
export function uaSpeed(el = document.documentElement) {
  const v = Number.parseFloat(getComputedStyle(el).getPropertyValue("--lm-ua-speed"));
  return Number.isFinite(v) ? v : 40;
}

/** Set the travelling liquid-metal angle for every .lm-glass / .lm-capsule / .lm-ring rim. */
export function setUA(t, el = document.documentElement, degPerSecond = uaSpeed(el)) {
  el.style.setProperty("--ua", `${((t * degPerSecond) % 360).toFixed(1)}deg`);
}

/** Validate a requested time: finite, ≥ 0, ≤ MAX_T. Throws otherwise. */
export function checkTime(t) {
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0 || n > MAX_T) throw new RangeError(`renderAt: t must be a finite number in [0, ${MAX_T}], got ${t}`);
  return n;
}

/**
 * createLoop({ init, step, paint, seed, still })
 *  init()           reset scene state (called at t = 0 and before every backwards seek)
 *  step(dt, t)      advance integrating state by one fixed step (springs, flows)
 *  paint(t)         draw the frame for time t (pure: reads state + t)
 *  still            the settled time shown under reduced motion (default 5 s)
 * Returns { start(), stop(), renderAt(t), t }.
 */
export function createLoop({ init = () => {}, step = () => {}, paint = () => {}, seed = 0x5eed, still = 5 } = {}) {
  let t = 0;
  let n = 0;
  let raf = 0;
  let last = 0;
  let acc = 0;
  const reset = () => {
    reseed(seed);
    t = 0;
    n = 0;
    acc = 0;
    init();
  };
  let speed = 40;
  const frame = (tt) => {
    setUA(MOTION ? tt : 0, document.documentElement, speed);
    paint(tt);
  };
  const seek = (target) => {
    const N = Math.round(checkTime(target) / STEP);
    if (N < n) reset();
    while (n < N) {
      step(STEP, t);
      t += STEP;
      n++;
    }
  };
  const L = {
    get t() {
      return t;
    },
    /** deterministic seek: replays fixed steps from 0 when going backwards */
    renderAt(target) {
      speed = uaSpeed();
      seek(target);
      frame(t);
    },
    /** real-time preview: same fixed steps, driven by requestAnimationFrame; the clock holds under reduced motion */
    start() {
      if (raf) return;
      reset();
      speed = uaSpeed(); // read the token once per start, not per frame
      if (!MOTION) seek(still);
      last = performance.now();
      const tick = (now) => {
        const dt = Math.min(0.1, (now - last) / 1000);
        last = now;
        if (MOTION) {
          acc += dt;
          while (acc >= STEP) {
            step(STEP, t);
            t += STEP;
            n++;
            acc -= STEP;
          }
        } else step(0, t); // springs snap to their targets; nothing advances in time
        frame(t);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    },
    stop() {
      cancelAnimationFrame(raf);
      raf = 0;
    },
  };
  reset();
  return L;
}
