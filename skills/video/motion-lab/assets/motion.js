// motion.js — one tokens file, imported everywhere, no inline numbers.
// Hand it to the model with: "use only these tokens, no inline numbers".

// Easing (cubic-bezier control points; names follow easings.net).
export const EASE = {
  enter: 'cubic-bezier(0.16, 1, 0.3, 1)',   // ease-out-expo: text and logo reveals
  premium: 'cubic-bezier(0.22, 1, 0.36, 1)', // ease-out-quint: premium entrances
  move: 'cubic-bezier(0.76, 0, 0.24, 1)',    // ease-in-out-quart: moves, camera pushes
  exit: 'cubic-bezier(0.7, 0, 0.84, 0)',     // ease-in-expo: fast exits
  pop: 'cubic-bezier(0.34, 1.56, 0.64, 1)',  // ease-out-back: playful overshoot
};

// Durations in ms. Exits are 40-50% shorter than entrances.
export const MS = { feedback: 150, move: 400, hero: 750, exit: 240 };

// Stagger in ms. Start the next element when the previous one is 30-50% done.
export const STAGGER = { letter: 30, word: 90, item: 60 };

// Convert ms to frames at a frame rate (round half up).
export const frames = (ms, fps) => Math.floor((ms * fps) / 1000 + 0.5);

// Damping ratio from any library's numbers: zeta = c / (2 sqrt(k m)).
// Remotion default (m 1, c 10, k 100) = 0.5. react-spring (tension 170, friction 26) ~ 1.0.
export const dampingRatio = (k, c, m = 1) => c / (2 * Math.sqrt(k * m));

// A spring as a pure function of time: progress 0 -> 1, no simulation, so any
// frame renders on its own. zeta: 1 no bounce, 0.7-0.85 premium, 0.4-0.6 playful.
// f: natural frequency in Hz (speed). Position and size may bounce; opacity and
// colour never should.
export function spring(t, zeta = 0.7, f = 2) {
  if (t <= 0) return 0;
  const w = 2 * Math.PI * f;
  if (zeta >= 1) return 1 - Math.exp(-w * t) * (1 + w * t);
  const wd = w * Math.sqrt(1 - zeta * zeta);
  return 1 - Math.exp(-zeta * w * t) * (Math.cos(wd * t) + ((zeta * w) / wd) * Math.sin(wd * t));
}

// Seeded PRNG (mulberry32). Reseed inside renderAt so noise is a function of t.
export function mulberry32(seed) {
  let a = seed | 0;
  return function () {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Loop phase from a frame: drive every periodic value from this, with whole cycles.
export const phase = (frame, N) => (((frame % N) + N) % N) / N;
