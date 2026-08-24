"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Hands-free reading. The page can drive itself through its own length in a
 * fixed three minutes, so a reader can watch it rather than scroll it.
 *
 * The naive version scrolls at a constant rate, which is wrong in both
 * directions at once: it races past the sections with the most to read and
 * crawls through the film, where nothing is being read at all. So the timeline
 * is built from the document itself.
 *
 *   film      -> one continuous scrub; it is a camera move, not a paragraph
 *   travel    -> short, fixed; getting between ideas is not an idea
 *   dwell     -> proportional to the READING TIME of the section's own text
 *
 * A section taller than the viewport is read by scrolling slowly through it
 * across its dwell rather than being pinned at its top with the end off-screen.
 * Whatever the natural durations sum to, they are then scaled to hit the target
 * exactly, which preserves the relative weighting while landing on the budget.
 *
 * Any real scroll input hands control straight back to the human: a reader who
 * reaches for the trackpad has decided to take over, and fighting them for the
 * scroll position is the one behaviour that would make this unusable.
 */

/** Characters per second. Spanish prose at ~180wpm, ~5.5 chars a word. */
const CPS = 17;
/** Nobody reads a heading in under this. */
const MIN_DWELL = 2.6;
/** Seconds of travel between two sections, before scaling. */
const TRAVEL = 1.1;
/** The film's natural share: five clips, unhurried. */
const FILM_NATURAL = 34;

type Leg =
  | { kind: "scrub"; from: number; to: number; secs: number }
  | { kind: "hold"; at: number; secs: number };

const easeInOut = (p: number) => (p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2);

/**
 * How much of a section is actually PROSE a reader reads.
 *
 * This is not a nicety. The ascii figure is two <pre> layers of ~6,190
 * characters each, so counting a section's raw text made one caption read as
 * 12,380 characters of reading — 728 seconds of natural dwell against a
 * 180-second budget. Everything else got scaled into nothing: the film went
 * past in 8 seconds and the timeline then parked on that one section for over
 * half a minute. Measured, not reasoned about — the symptom was visible only
 * once it actually ran.
 *
 * So: drop what is decorative (aria-hidden), what exists only for screen
 * readers (.vh), and any preformatted block. What is left is the words.
 */
function readableChars(el: HTMLElement): number {
  const c = el.cloneNode(true) as HTMLElement;
  for (const n of c.querySelectorAll('[aria-hidden="true"], .vh, pre, script, style')) n.remove();
  return (c.textContent || "").replace(/\s+/g, " ").trim().length;
}

export function AutoScroll({ totalSeconds = 180 }: { totalSeconds?: number }) {
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const legs = useRef<Leg[]>([]);
  const raf = useRef(0);
  const elapsed = useRef(0);
  const lastTs = useRef(0);
  /** Set while WE are scrolling, so our own scroll events are not mistaken
   *  for the human taking over. */
  const selfScroll = useRef(false);

  /** Build the timeline from the live document, at play time. */
  const plan = useCallback(() => {
    const vh = window.innerHeight;
    const docTop = (el: Element) => window.scrollY + el.getBoundingClientRect().top;
    const maxY = document.documentElement.scrollHeight - vh;

    const out: Array<Leg & { natural: number }> = [];
    const track = document.querySelector(".film-track");
    const acts = [...document.querySelectorAll<HTMLElement>("main.demo section.act")];

    if (track) {
      const end = docTop(track) + track.getBoundingClientRect().height - vh;
      out.push({ kind: "scrub", from: 0, to: Math.max(0, end), secs: 0, natural: FILM_NATURAL });
    }

    for (const act of acts) {
      const top = Math.min(maxY, docTop(act));
      const h = act.getBoundingClientRect().height;
      // Reading time from the section's own text. `innerText` rather than
      // textContent so visually-hidden copy -- which exists on this page for
      // screen readers -- is not counted as something to be read aloud.
      const dwell = Math.max(MIN_DWELL, readableChars(act) / CPS);

      const prev = out.at(-1);
      const from = prev ? (prev.kind === "scrub" ? prev.to : prev.at) : 0;
      out.push({ kind: "scrub", from, to: top, secs: 0, natural: TRAVEL });

      const overflow = h - vh;
      if (overflow > 40) {
        // taller than the screen: read it by moving through it
        out.push({
          kind: "scrub",
          from: top,
          to: Math.min(maxY, top + overflow),
          secs: 0,
          natural: dwell,
        });
      } else {
        out.push({ kind: "hold", at: top, secs: 0, natural: dwell });
      }
    }

    const natural = out.reduce((s, l) => s + l.natural, 0) || 1;
    const scale = totalSeconds / natural;
    legs.current = out.map(({ natural: n, ...l }) => ({ ...l, secs: n * scale }) as Leg);
  }, [totalSeconds]);

  const stop = useCallback(() => {
    cancelAnimationFrame(raf.current);
    setPlaying(false);
  }, []);

  const toggle = useCallback(() => {
    setPlaying((p) => {
      if (p) {
        cancelAnimationFrame(raf.current);
        return false;
      }
      // Replan every time: the film's geometry depends on the viewport, and a
      // plan built at mount is wrong after a rotate or a resize.
      plan();
      if (elapsed.current >= legs.current.reduce((s, l) => s + l.secs, 0)) elapsed.current = 0;
      lastTs.current = 0;
      return true;
    });
  }, [plan]);

  useEffect(() => {
    if (!playing) return;

    const total = legs.current.reduce((s, l) => s + l.secs, 0);

    const tick = (ts: number) => {
      if (!lastTs.current) lastTs.current = ts;
      const dt = Math.min(0.25, (ts - lastTs.current) / 1000);
      lastTs.current = ts;
      elapsed.current += dt;

      if (elapsed.current >= total) {
        setProgress(1);
        stop();
        return;
      }
      setProgress(elapsed.current / total);

      let t = elapsed.current;
      let y: number | undefined;
      for (const leg of legs.current) {
        if (t > leg.secs) {
          t -= leg.secs;
          continue;
        }
        if (leg.kind === "hold") y = leg.at;
        else {
          // ease each leg so a section arrives and settles rather than
          // slamming to a stop
          const p = leg.secs > 0 ? t / leg.secs : 1;
          y = leg.from + (leg.to - leg.from) * (leg.kind === "scrub" ? easeInOut(p) : p);
        }
        break;
      }

      if (y !== undefined) {
        selfScroll.current = true;
        window.scrollTo(0, y);
        // cleared on the next frame, after the scroll event has fired
        requestAnimationFrame(() => {
          selfScroll.current = false;
        });
      }
      raf.current = requestAnimationFrame(tick);
    };

    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [playing, stop]);

  // Any deliberate input is the human taking over. Note this listens for the
  // INPUT, not for scroll events: our own scrollTo fires those too, and
  // distinguishing them by a flag alone is a race we would lose sometimes.
  useEffect(() => {
    if (!playing) return;
    const yield_ = () => stop();
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End"].includes(e.key)) stop();
    };
    window.addEventListener("wheel", yield_, { passive: true });
    window.addEventListener("touchmove", yield_, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("wheel", yield_);
      window.removeEventListener("touchmove", yield_);
      window.removeEventListener("keydown", onKey);
    };
  }, [playing, stop]);

  // Space toggles, because that is what it does in every other player.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && ["INPUT", "TEXTAREA", "BUTTON", "A"].includes(el.tagName)) return;
      if (e.code === "Space") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  const total = totalSeconds;
  const left = Math.max(0, Math.round(total - progress * total));
  const mmss = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;

  return (
    <div className="auto">
      <button
        aria-label={playing ? "Pausar el recorrido" : "Reproducir el recorrido de tres minutos"}
        className="auto-btn"
        onClick={toggle}
        type="button"
      >
        {/* Drawn, not typed. A literal ▶/❚❚ is a font glyph: its weight, its
            baseline and its very presence vary by platform, and on the one
            machine that lacks it the control renders as a tofu box. Two paths
            cost nothing and look the same everywhere. */}
        <svg
          aria-hidden="true"
          className="auto-ico"
          fill="currentColor"
          height="10"
          viewBox="0 0 10 10"
          width="10"
        >
          {playing ? (
            <>
              <rect height="10" width="3" x="0.5" y="0" />
              <rect height="10" width="3" x="6.5" y="0" />
            </>
          ) : (
            <path d="M1 0 L10 5 L1 10 Z" />
          )}
        </svg>
        <span className="auto-t">{playing ? mmss : "3:00"}</span>
      </button>
      <div className="auto-bar">
        <i style={{ transform: `scaleX(${progress})` }} />
      </div>
    </div>
  );
}
