"use client";

import type { PlayerRef } from "@remotion/player";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { MOTION, MOTION_FPS, MOTION_H, MOTION_W, type MotionId } from "../remotion/registry";

/**
 * The Player touches the DOM at module scope, and this site is exported to
 * static files at build time, so it is loaded client-side only. What ships in
 * the HTML is the panel chrome and the figure's description -- and every claim
 * a figure makes is also written in the prose beside it, so a reader with no
 * JavaScript loses the animation and none of the argument.
 */
const Player = dynamic(() => import("@remotion/player").then((m) => m.Player), { ssr: false });
const Thumbnail = dynamic(() => import("@remotion/player").then((m) => m.Thumbnail), {
  ssr: false,
});

export function MotionPanel({
  id,
  alt,
  className = "",
}: {
  id: MotionId;
  alt: string;
  className?: string;
}) {
  const spec = MOTION[id];
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<PlayerRef>(null);
  const [inView, setInView] = useState(false);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  // Four compositions on one page is four render loops. Only the one a reader
  // is looking at should be running.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.25 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    const p = player.current;
    if (!p || reduced) return;
    if (inView) {
      // restart from the top so a reader who scrolls to it sees the first beat
      // rather than joining halfway through
      p.seekTo(0);
      p.play();
    } else {
      p.pause();
    }
  }, [inView, reduced]);

  return (
    <div className={`panel ${className}`.trim()} ref={host}>
      <div className="chrome" aria-hidden="true">
        <span className="op">{spec.op}</span>
        <span className="spacer" />
        <span>{spec.meta}</span>
      </div>
      <div className="screen" role="img" aria-label={alt}>
        {reduced ? (
          <Thumbnail
            component={spec.component}
            compositionWidth={MOTION_W}
            compositionHeight={MOTION_H}
            frameToDisplay={spec.still}
            durationInFrames={spec.duration}
            fps={MOTION_FPS}
            style={{ width: "100%", height: "100%" }}
          />
        ) : (
          <Player
            ref={player}
            component={spec.component}
            durationInFrames={spec.duration}
            compositionWidth={MOTION_W}
            compositionHeight={MOTION_H}
            fps={MOTION_FPS}
            loop
            clickToPlay={false}
            doubleClickToFullscreen={false}
            style={{ width: "100%", height: "100%" }}
          />
        )}
      </div>
    </div>
  );
}
