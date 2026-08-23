"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The opening, moved across from the single-file landing unchanged in
 * substance: one number, --p, is driven by scroll position and every reveal in
 * the figure is a clamp() over it in CSS. Nothing tweens, so the drawing and
 * the words cannot drift apart.
 *
 * The six scene texts are rendered into the document rather than held in a JS
 * array, so they exist for a reader with no JavaScript and for anything that
 * reads the served HTML. --p defaults to 1 (the @property initial value), so
 * no-JS and reduced-motion both land on the finished diagram.
 */

const SCENES: Array<[string, string]> = [
  [
    "Every operating decision is taken once.",
    "You choose, the world moves, and the alternative is never observed.",
  ],
  [
    "Parallax gives you the one you did not take.",
    "Point it at a context. It proposes a model of what is actually in there, and hands it to you before anything runs.",
  ],
  [
    "You accept it, or nothing happens.",
    "A model nobody reviewed should not be able to produce numbers that look authoritative. While a blocking question is open, it refuses to activate.",
  ],
  [
    "Then fork the history and change one decision.",
    "Same initial state, same seed, one policy different. The log is append-only, so a branch costs nothing to create.",
  ],
  [
    "Two lines out of one baseline.",
    "The angle between them is the measurement. That is what the word parallax means.",
  ],
  [
    "And every number says how much of it was real.",
    "Typed observed or simulated at birth, carried into the receipt and into the API.",
  ],
];

export function Cinema() {
  const svg = useRef<SVGSVGElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const [scene, setScene] = useState(0);
  const [past, setPast] = useState(false);

  useEffect(() => {
    const el = svg.current;
    const tr = track.current;
    if (!el || !tr) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    el.style.setProperty("--p", "0");
    let queued = false;
    const paint = () => {
      queued = false;
      const r = tr.getBoundingClientRect();
      const span = Math.max(1, r.height - window.innerHeight);
      const p = Math.min(1, Math.max(0, -r.top / span));
      el.style.setProperty("--p", p.toFixed(4));
      setScene(Math.min(SCENES.length - 1, Math.floor(p * SCENES.length)));
    };
    const onScroll = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(paint);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    paint();
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  // Once the reader is into the document, the opening gets out of the way.
  useEffect(() => {
    const after = document.querySelector(".after");
    if (!after) return;
    const io = new IntersectionObserver(([e]) => setPast(e.isIntersecting), { threshold: 0.02 });
    io.observe(after);
    return () => io.disconnect();
  }, []);

  const hide = { opacity: past ? 0 : 1, transition: "opacity 500ms" };
  const [title, body] = SCENES[scene] ?? SCENES[SCENES.length - 1];

  return (
    <>
      <a className="skip" href="#main">
        Skip the opening sequence
      </a>

      <div id="stage" style={hide}>
        <svg
          ref={svg}
          id="cine"
          viewBox="0 0 1600 900"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-labelledby="cine-t cine-d"
        >
          <title id="cine-t">A recorded trunk, a fork at now, and two simulated branches</title>
          <desc id="cine-d">
            A solid line runs left to right and stops at a point marked NOW. The solid stroke is the
            RECORDED class: it is what actually happened, tagged observed. At NOW a bar stands
            across the line — nothing runs until a human accepts. Past NOW the line forks into two
            dotted rays that share that one baseline. Dotted is the PINNED class: byte-identical on
            replay. One ray, named main, rises to more violations; the other, named governed, stays
            flat on zero. Both are tagged simulated. The angle between the two rays, marked at the
            fork, is the measurement — which is what the word parallax means.
          </desc>

          <defs>
            <clipPath id="cine-clip" clipPathUnits="userSpaceOnUse">
              <rect className="cine-sweep" y="0" height="900" />
            </clipPath>
            <linearGradient id="cine-fade" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="#fff" stopOpacity="0" />
              <stop offset="0.22" stopColor="#fff" stopOpacity="1" />
            </linearGradient>
            {/* userSpaceOnUse is load-bearing: a horizontal line has a
                ZERO-HEIGHT bounding box, and a mask defaults to
                objectBoundingBox units, so the mask region would collapse to
                zero height and hide the trunk entirely. */}
            <mask
              id="cine-past"
              maskUnits="userSpaceOnUse"
              x="280"
              y="560"
              width="700"
              height="160"
            >
              <rect x="280" y="560" width="700" height="160" fill="url(#cine-fade)" />
            </mask>
          </defs>

          <g className="cine-grid">
            <line x1="300" y1="470" x2="1380" y2="470" />
            <line x1="300" y1="630" x2="1380" y2="630" />
            <line x1="300" y1="790" x2="1380" y2="790" />
          </g>

          {/* the recorded past, faded at its left edge so it reads as
              continuing off-frame: the history predates the view */}
          <g className="b-trunk">
            <path className="cine-trunk" d="M 300 630 L 920 630" mask="url(#cine-past)" />
            <text className="cine-tag b-rec" x="700" y="676">
              RECORDED
            </text>
            <text className="cine-meta b-typed" x="700" y="702">
              observed · it happened
            </text>
          </g>

          <g className="b-now">
            <line className="cine-nowline" x1="920" y1="356" x2="920" y2="800" />
            <text className="cine-tag" x="920" y="340" textAnchor="middle">
              NOW
            </text>
            <circle className="cine-ring" cx="920" cy="630" r="13" />
            <circle className="cine-dot" cx="920" cy="630" r="5.5" />
          </g>

          <g className="b-gate">
            <line className="cine-gate-halo" x1="920" y1="582" x2="920" y2="678" />
            <line className="cine-gate" x1="920" y1="582" x2="920" y2="678" />
            <text className="cine-meta" x="952" y="716">
              nothing runs until you accept
            </text>
          </g>

          <g clipPath="url(#cine-clip)">
            <path className="cine-wedge b-angle" d="M 920 630 L 1380 470 L 1380 630 Z" />
            <line className="cine-ray main b-fork" x1="920" y1="630" x2="1380" y2="470" />
            <line className="cine-ray gov b-fork" x1="920" y1="630" x2="1380" y2="630" />
            <path className="cine-arc b-angle" d="M 1090 630 A 170 170 0 0 0 1080.56 574.15" />
            <circle className="cine-end b-fork" cx="1380" cy="470" r="6" />
            <circle className="cine-end gov b-fork" cx="1380" cy="630" r="6" />
          </g>

          <g className="b-fork">
            <text className="cine-name" x="1400" y="464">
              main
            </text>
            <text className="cine-name gov" x="1400" y="624">
              governed
            </text>
          </g>
          <g className="b-typed">
            <text className="cine-meta" x="1400" y="488">
              PINNED · simulated
            </text>
            <text className="cine-meta" x="1400" y="648">
              PINNED · simulated
            </text>
          </g>
          <text className="cine-delta b-angle" x="1136" y="556">
            Δ the measurement
          </text>
        </svg>
      </div>

      <div className="veil" aria-hidden="true" style={hide} />

      <div className="cine-brand" style={hide}>
        <span className="w">Parallax</span>
        <span className="id">run bef312a9 · class PINNED</span>
      </div>
      <p className="scrollcue" style={hide}>
        scroll — you are scrubbing a log
      </p>
      <a className="jump" href="#main" style={{ ...hide, pointerEvents: past ? "none" : "auto" }}>
        Skip to the product
      </a>

      {/* the copy the figure is illustrating, in the document either way */}
      <div className="copy" aria-hidden="true">
        <p className="n">
          {String(scene + 1).padStart(2, "0")} / {String(SCENES.length).padStart(2, "0")}
        </p>
        <p className="ct">{title}</p>
        <p className="b">{body}</p>
      </div>
      <ol className="vh">
        {SCENES.map(([t, b]) => (
          <li key={t}>
            <b>{t}</b>
            <span>{b}</span>
          </li>
        ))}
      </ol>

      <div id="track" ref={track} />
    </>
  );
}
