"use client";

import { useEffect, useRef, useState } from "react";
import { createScrollCinema, type ScrollCinema } from "../lib/scroll-cinema";

/**
 * The film half of /demo. Scroll position is the camera: `createScrollCinema`
 * maps the track's progress onto a frame of a dense-GOP clip, so the reader is
 * scrubbing footage rather than triggering animations. Nothing here tweens on a
 * timer, which is why the words and the picture cannot drift apart.
 *
 * The copy lives in the DOM, never in the generated pixels. That is a hard rule
 * for this page: a diffusion model cannot be trusted to render a number or a
 * word, and every claim on this page is one we have to stand behind. So the
 * footage carries the room, and the document carries the argument.
 */

export type Scene = { id: string; title: string; body: string; alt: string };

export function DemoCinema({
  scenes,
  clips,
  posters,
}: {
  scenes: Scene[];
  clips: string[];
  posters: string[];
}) {
  const stage = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const [scene, setScene] = useState(0);
  const [reduced, setReduced] = useState(false);
  const [past, setPast] = useState(false);

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
        onScene: setScene,
        reducedMotion: mq.matches,
      });
    } catch {
      // A decoder the browser will not give us is not a reason to serve a
      // broken page: the posters are already in the DOM underneath, and the
      // copy has never depended on the video.
      return;
    }
    return () => cinema?.destroy();
  }, [clips, posters]);

  // The stage is fixed, so it stays behind the document forever by design --
  // scroll back up and the film is still there. The copy over it is fixed too
  // and has to get out of the way once the argument starts, or it sits on top
  // of the first act.
  useEffect(() => {
    const first = document.getElementById("reduccion");
    if (!first) return;
    const io = new IntersectionObserver(([e]) => setPast(e.isIntersecting), { threshold: 0.02 });
    io.observe(first);
    return () => io.disconnect();
  }, []);

  const hidden = { opacity: past ? 0 : 1 };
  const current = scenes[Math.min(scene, scenes.length - 1)];

  return (
    <section className="film" aria-labelledby="film-h">
      <h2 className="vh" id="film-h">
        The whole idea, in six shots
      </h2>

      <div className="film-stage" ref={stage} aria-hidden="true" />

      {/* The poster of the scene the reader is on is the reduced-motion and
          no-JS experience in full: six stills and six captions tell the story
          without a single byte of video. */}
      <noscript>
        <div className="film-fallback">
          {scenes.map((s, i) => (
            <figure key={s.id}>
              {/* biome-ignore lint/performance/noImgElement: static export, no loader */}
              <img alt={s.alt} src={posters[i]} />
              <figcaption>
                <b>{s.title}</b>
                <span>{s.body}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </noscript>

      <div className="film-copy" data-reduced={reduced ? "true" : undefined} style={hidden}>
        <p className="film-n">
          {String(scene + 1).padStart(2, "0")}
          <span> / {String(scenes.length).padStart(2, "0")}</span>
        </p>
        <p className="film-t">{current.title}</p>
        <p className="film-b">{current.body}</p>
      </div>

      <p className="film-cue" aria-hidden="true" style={hidden}>
        scroll — estás moviendo la cámara
      </p>

      {/* Every scene's words exist in the served HTML regardless of what the
          decoder does, in reading order, for anything that is not a browser. */}
      <ol className="vh">
        {scenes.map((s) => (
          <li key={s.id}>
            <b>{s.title}</b> <span>{s.body}</span>
          </li>
        ))}
      </ol>

      <div className="film-track" ref={track} />
    </section>
  );
}
