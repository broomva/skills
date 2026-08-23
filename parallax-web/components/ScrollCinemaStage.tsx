"use client";

import { useEffect, useRef, useState } from "react";
import { createScrollCinema, type ScrollCinema } from "../lib/scroll-cinema";
import { RealityMap } from "./RealityMap";

/**
 * Veo footage as the ground, the reality map as the argument.
 *
 * The map reads its own scroll position rather than taking it from the
 * scrubber. That is deliberate: `createScrollCinema` throws when the browser
 * will not give us a decoder, and a page whose diagram disappears with the
 * video would lose the whole claim to a codec. Here the footage can fail
 * completely and the argument still runs.
 *
 * The copy lives in the DOM, never in the generated pixels. A diffusion model
 * cannot be trusted to render a word or a number, and every claim on this page
 * is one we have to stand behind.
 */

export type Beat = { id: string; title: string; body: string };

export function ScrollCinemaStage({
  beats,
  clips,
  posters,
}: {
  beats: Beat[];
  clips: string[];
  posters: string[];
}) {
  const stage = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const map = useRef<HTMLDivElement>(null);
  const [scene, setScene] = useState(0);
  const [step, setStep] = useState(0);
  const [reduced, setReduced] = useState(false);

  // the film
  useEffect(() => {
    const st = stage.current;
    const tr = track.current;
    if (!st || !tr) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    let cinema: ScrollCinema | undefined;
    try {
      cinema = createScrollCinema({
        clips,
        posters,
        stage: st,
        track: tr,
        reducedMotion: mq.matches,
      });
    } catch {
      // No decoder is not a broken page: the poster is under the video layer
      // and the map above it never needed either.
      return;
    }
    return () => cinema?.destroy();
  }, [clips, posters]);

  // the map — one number, read straight off the track
  useEffect(() => {
    const host = map.current;
    const tr = track.current;
    if (!host || !tr) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    host.style.setProperty("--p", "0");
    let queued = false;
    const paint = () => {
      queued = false;
      const r = tr.getBoundingClientRect();
      const span = Math.max(1, r.height - window.innerHeight);
      const p = Math.min(1, Math.max(0, -r.top / span));
      host.style.setProperty("--p", p.toFixed(4));
      setScene(Math.min(beats.length - 1, Math.floor(p * beats.length)));
      setStep(Math.round(p * 12));
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
  }, [beats.length]);

  const current = beats[Math.min(scene, beats.length - 1)];

  return (
    <section className="sc" aria-labelledby="sc-h">
      <h1 className="vh" id="sc-h">
        Parallax — one recorded trunk, eight simulated branches, and the one that held
      </h1>

      <div className="sc-stage" ref={stage} aria-hidden="true" />
      <div className="sc-veil" aria-hidden="true" />

      <div className="sc-map" ref={map}>
        <RealityMap />
      </div>

      {/* chrome: the run this page is describing, in the vocabulary the
          product actually uses rather than invented telemetry */}
      <div className="sc-chrome tl" aria-hidden="true">
        <p>{"REALITY MAP // PARALLEL BRANCHES"}</p>
        <p>
          TRUNK: <b>RECORDED</b> · OBSERVED
        </p>
        <p>
          BRANCHES: <b>8 SIMULATED</b> · <em>PINNED</em>
        </p>
      </div>
      <div className="sc-chrome bl" aria-hidden="true">
        <p>SEED 42 · HORIZON 12</p>
        <p className="sc-step">STEP {String(Math.min(step, 12)).padStart(2, "0")} / 12</p>
      </div>
      <p className="sc-cue" aria-hidden="true">
        SCROLL
      </p>

      <div className="sc-copy" data-reduced={reduced ? "true" : undefined}>
        <p className="sc-n">
          {String(scene + 1).padStart(2, "0")}
          <span> / {String(beats.length).padStart(2, "0")}</span>
        </p>
        <p className="sc-t">{current.title}</p>
        <p className="sc-b">{current.body}</p>
      </div>

      {/* Every beat's words are in the served HTML in reading order, whatever
          the decoder does and whether or not JavaScript ran. */}
      <ol className="vh">
        {beats.map((b) => (
          <li key={b.id}>
            <b>{b.title}</b> <span>{b.body}</span>
          </li>
        ))}
      </ol>

      <div className="sc-track" ref={track} />
    </section>
  );
}
