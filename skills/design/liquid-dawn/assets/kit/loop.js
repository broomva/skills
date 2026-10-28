// Liquid Dawn kit · the frame loop and the render contract (the same contract as Liquid Midnight and motion-lab):
// every frame is a pure function of t. Integrating state advances in fixed 1/60 s steps from t = 0 after reseed(),
// so window.renderAt(t) paints the same pixels on every machine and a headless browser can render any frame.
// It also drives the CSS side from t: --ua (the pearl rim angle) and --ld-b1..3 (the wash breathing on the
// non-commensurate 7.2 / 11.6 / 18.8 s periods from tokens.json motion.breath, so the light never visibly repeats).
import { MOTION, reseed } from "./core.js";

export const STEP = 1 / 60;
export const MAX_T = 3600;
export const BREATH = [7.2, 11.6, 18.8];

/** Pearl speed from the token (--ld-ua-speed); 24°/s if unset. */
export function uaSpeed(el = document.documentElement) {
  const v = Number.parseFloat(getComputedStyle(el).getPropertyValue("--ld-ua-speed"));
  return Number.isFinite(v) ? v : 24;
}

/** Set the CSS clock for time t: --ua and the three breath phases (each in −1..1). Under reduced motion the pearl
 *  holds at 0° (an inline value would otherwise override the stylesheet's freeze). */
export function setClock(t, el = document.documentElement, degPerSecond = uaSpeed(el)) {
  el.style.setProperty("--ua", `${MOTION ? ((t * degPerSecond) % 360).toFixed(2) : "0.00"}deg`);
  BREATH.forEach((p, i) => el.style.setProperty(`--ld-b${i + 1}`, Math.sin((t / p) * Math.PI * 2).toFixed(4)));
}

export function checkTime(t) {
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0 || n > MAX_T) throw new RangeError(`renderAt: t must be a finite number in [0, ${MAX_T}], got ${t}`);
  return n;
}

/**
 * createLoop({ init, step, paint, seed, still })
 *  init()        reset scene state (t = 0, and before every backwards seek)
 *  step(dt, t)   advance integrating state one fixed step
 *  paint(t)      draw frame t (pure: state + t)
 *  still         the settled frame shown under reduced motion (default 6 s)
 * Returns { start(), stop(), renderAt(t), invalidate(), t }.
 */
export function createLoop({ init = () => {}, step = () => {}, paint = () => {}, seed = 0xda3e, still = 6 } = {}) {
  let t = 0;
  let n = 0;
  let raf = 0;
  let last = 0;
  let acc = 0;
  let speed = 24;
  let dirty = true;
  const reset = () => {
    reseed(seed);
    t = 0;
    n = 0;
    acc = 0;
    init();
  };
  const frame = (tt) => {
    setClock(tt, document.documentElement, speed);
    paint(tt);
  };
  const seek = (target) => {
    const N = Math.round(checkTime(target) / STEP);
    if (N < n) reset();
    while (n < N) {
      step(STEP, t);
      n++;
      t = n * STEP;
    }
  };
  const L = {
    get t() {
      return t;
    },
    renderAt(target) {
      speed = uaSpeed();
      seek(target);
      frame(t);
    },
    invalidate() {
      dirty = true;
    },
    start() {
      if (raf) return;
      reset();
      speed = uaSpeed();
      if (!MOTION) seek(still);
      dirty = true;
      let wasMoving = MOTION;
      last = performance.now();
      const tick = (now) => {
        const dt = Math.min(0.1, (now - last) / 1000);
        last = now;
        if (MOTION !== wasMoving) {
          // the OS preference changed mid-run: settle on the still frame when motion stops, and repaint either way
          if (!MOTION) seek(still);
          wasMoving = MOTION;
          dirty = true;
        }
        if (MOTION) {
          acc += dt;
          while (acc >= STEP) {
            step(STEP, t);
            n++;
            t = n * STEP;
            acc -= STEP;
          }
        }
        if (MOTION || dirty) {
          frame(t);
          dirty = false;
        }
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

/** Size a canvas to its CSS box at ≤ 2× DPR; returns its 2D context with the transform set. Only resizes on change
 *  (assigning width clears the canvas). */
export function fitCanvas(cv) {
  const d = Math.min(2, globalThis.devicePixelRatio || 1);
  const w = cv.clientWidth;
  const h = cv.clientHeight;
  if (cv.width !== Math.round(w * d) || cv.height !== Math.round(h * d)) {
    cv.width = Math.round(w * d);
    cv.height = Math.round(h * d);
  }
  const cx = cv.getContext("2d");
  cx.setTransform(d, 0, 0, d, 0, 0);
  return { cx, w, h };
}

/** Pointer sheen: keep --mx/--my on every .ld-glass under root in step with the pointer (live preview only). */
export function sheen(root = document) {
  root.addEventListener?.("pointermove", (e) => {
    for (const el of root.querySelectorAll(".ld-glass, .ld-lens")) {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${e.clientX - r.left}px`);
      el.style.setProperty("--my", `${e.clientY - r.top}px`);
    }
  });
}
