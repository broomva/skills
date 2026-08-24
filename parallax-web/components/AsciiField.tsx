"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A text run used as the rasterizer: the glyph is the mark, not the pixel.
 * The architecture is the typographic-shader prototype's (BRO-2186) and the
 * idiom deliberately is not -- that prototype's palette and 6px lattice were
 * measured off the Claude FM stream and are that stream's optical signature.
 * Halftone and ASCII rasterisation are prior art by a century and by decades
 * respectively; the look is not.
 *
 * What changed here is the FIELD. That prototype rasterised a travelling wave
 * crest. This one rasterises the thing this project is about: a single recorded
 * past, a fork, and a fan of simulated futures of which exactly one is ever
 * taken. The observed world is the still underneath, dim and unmoving, because
 * it already happened. The trajectories over it are the only part that moves,
 * because they are the only part that hasn't.
 *
 * Two layers, not one. A single <pre> can carry one colour, and the whole point
 * is that observed and simulated are different KINDS of value and must not be
 * confusable. So the ground is rendered once into a static layer and the paths
 * are painted each frame into a transparent layer above it, on the same lattice
 * so the two register exactly.
 *
 * The part worth keeping verbatim from the prototype: the ramp is MEASURED, not
 * assumed. Each glyph is drawn to a scratch canvas and its coverage summed, so
 * the ordering is a property of the font that actually resolved rather than a
 * guess baked in at authoring time. A hand-written ramp is wrong the moment the
 * font falls back.
 */

const RAMP_CHARS = " .,:;-~+=*oOxX#%@&8BM";

/** Ink coverage of one glyph in [0,1], measured by rendering it. */
function coverage(ch: string, font: string, ctx: CanvasRenderingContext2D): number {
  ctx.clearRect(0, 0, 32, 32);
  ctx.fillStyle = "#fff";
  ctx.font = font;
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  ctx.fillText(ch, 16, 16);
  const d = ctx.getImageData(0, 0, 32, 32).data;
  let sum = 0;
  for (let i = 3; i < d.length; i += 4) sum += d[i];
  return sum / (32 * 32 * 255);
}

/** Where the recorded trunk stops and the branches start, in [0,1] across. */
const FORK = 0.3;
/** Candidate trajectories in the fan. Odd, so one of them runs dead straight. */
const PATHS = 9;
/** Seconds for one fan-out → choose → reset cycle. */
const PERIOD = 11;

export function AsciiField({ src, alt, cols = 150 }: { src: string; alt: string; cols?: number }) {
  const [ground, setGround] = useState<string>("");
  const paths = useRef<HTMLPreElement>(null);
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let raf = 0;
    let visible = true;

    const run = async () => {
      const scratch = document.createElement("canvas");
      scratch.width = 32;
      scratch.height = 32;
      const sctx = scratch.getContext("2d", { willReadFrequently: true });
      if (!sctx) return;

      const font = `24px ${getComputedStyle(document.body).getPropertyValue("--mono") || "monospace"}`;
      const ramp = RAMP_CHARS.split("").map((ch) => ({
        ch,
        cov: ch === " " ? 0 : coverage(ch, font, sctx),
      }));
      const max = Math.max(...ramp.map((e) => e.cov)) || 1;
      for (const e of ramp) e.cov /= max;
      ramp.sort((a, b) => a.cov - b.cov);

      /** Nearest glyph by measured coverage. */
      const glyph = (v: number) => {
        let lo = 0;
        let hi = ramp.length - 1;
        while (lo < hi) {
          const m = (lo + hi) >> 1;
          if (ramp[m].cov < v) lo = m + 1;
          else hi = m;
        }
        return ramp[lo].ch;
      };

      const img = new Image();
      img.decoding = "async";
      img.src = src;
      try {
        await img.decode();
      } catch {
        return; // no still, no ground; the paths and the caption still stand
      }
      if (cancelled) return;

      // A monospace cell is about twice as tall as it is wide, so the row count
      // divides by that or the picture comes out stretched vertically.
      const rows = Math.max(1, Math.round((cols * img.height) / img.width / 2.05));

      const c = document.createElement("canvas");
      c.width = cols;
      c.height = rows;
      const cctx = c.getContext("2d", { willReadFrequently: true });
      if (!cctx) return;
      cctx.drawImage(img, 0, 0, cols, rows);
      const px = cctx.getImageData(0, 0, cols, rows).data;

      // --- the observed layer, rendered once ------------------------------
      const g: string[] = [];
      for (let y = 0; y < rows; y++) {
        let line = "";
        for (let x = 0; x < cols; x++) {
          const i = (y * cols + x) * 4;
          // Rec. 709 luma. The footage is dark, so a flat average would crush
          // the whole frame into the bottom three glyphs.
          const l = (0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]) / 255;
          line += glyph(l);
        }
        g.push(line);
      }
      if (cancelled) return;
      setGround(g.join("\n"));

      // --- the simulated layer, repainted per frame ------------------------
      const y0 = rows / 2;
      const buf = new Float32Array(cols * rows);
      const line: string[] = new Array(cols);

      /**
       * One frame of the field. `prog` walks the branches out from the fork,
       * then `pick` raises exactly one of them and drops the rest — a fan of
       * candidates collapsing to the single path that actually gets taken.
       */
      const paint = (t: number) => {
        buf.fill(0);
        const cycle = t / PERIOD;
        const phase = cycle - Math.floor(cycle);
        // Deterministic per cycle: no Math.random, so a reload looks the same
        // and a screenshot is reproducible.
        const chosen =
          Math.floor(Math.abs(Math.sin(Math.floor(cycle) * 12.9898) * 43758.5453)) % PATHS;
        const prog = Math.min(1, phase / 0.55);
        const pick = Math.max(0, Math.min(1, (phase - 0.62) / 0.18));
        const fade = phase > 0.9 ? 1 - (phase - 0.9) / 0.1 : 1;

        // the recorded trunk: solid, and it predates the frame, so it fades in
        // from the left edge rather than starting there
        const forkX = Math.round(FORK * cols);
        for (let x = 0; x < forkX; x++) {
          const a = Math.min(1, x / (forkX * 0.55));
          for (let dy = -1; dy <= 1; dy++) {
            const y = Math.round(y0) + dy;
            if (y < 0 || y >= rows) continue;
            buf[y * cols + x] = Math.max(buf[y * cols + x], a * (dy === 0 ? 1 : 0.42));
          }
        }

        // the branches
        const span = cols - forkX;
        for (let k = 0; k < PATHS; k++) {
          const lane = (k / (PATHS - 1)) * 2 - 1; // -1 .. 1
          const amp = lane * rows * 0.42;
          const isChosen = k === chosen;
          // chosen rises to full while the rest are pulled down toward nothing
          const bright = (isChosen ? 0.55 + 0.45 * pick : 0.55 * (1 - 0.82 * pick)) * fade;
          if (bright <= 0.02) continue;
          const reach = forkX + span * prog;
          for (let x = forkX; x < cols; x++) {
            if (x > reach) break;
            const s = (x - forkX) / span;
            // ease so the fan opens slowly at the fork and separates later —
            // near the fork the futures are still nearly indistinguishable
            const yF = y0 + amp * s ** 1.45 + Math.sin(s * 9 + t * 0.8 + k * 1.7) * rows * 0.012;
            // the leading tip is brighter: this is the frontier of the rollout
            const tip = 1 - Math.min(1, (reach - x) / 14);
            for (let dy = -2; dy <= 2; dy++) {
              const y = Math.round(yF) + dy;
              if (y < 0 || y >= rows) continue;
              const w = Math.exp(-(dy * dy) / 1.6);
              const v = bright * w * (0.62 + 0.38 * tip);
              const i = y * cols + x;
              if (v > buf[i]) buf[i] = v;
            }
          }
        }

        let out = "";
        for (let y = 0; y < rows; y++) {
          for (let x = 0; x < cols; x++) {
            const v = buf[y * cols + x];
            line[x] = v < 0.06 ? " " : glyph(Math.min(1, v));
          }
          out += line.join("");
          if (y < rows - 1) out += "\n";
        }
        if (paths.current) paths.current.textContent = out;
      };

      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduced) {
        // One frame, at the moment the choice has been made. The figure reads
        // the same; it just does not move.
        paint(PERIOD * 0.8);
        return;
      }

      // Four compositions already run on this page. A field nobody is looking
      // at should not be one of them.
      const io = new IntersectionObserver(
        ([e]) => {
          visible = e.isIntersecting;
        },
        { threshold: 0.05 },
      );
      if (host.current) io.observe(host.current);

      const t0 = performance.now();
      let last = 0;
      const loop = (now: number) => {
        raf = requestAnimationFrame(loop);
        if (!visible) return;
        // 24fps: this is a film, and it halves the string building.
        if (now - last < 41) return;
        last = now;
        paint((now - t0) / 1000);
      };
      raf = requestAnimationFrame(loop);

      cleanup = () => {
        io.disconnect();
        cancelAnimationFrame(raf);
      };
    };

    let cleanup: (() => void) | undefined;
    run();
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      cleanup?.();
    };
  }, [src, cols]);

  return (
    <div className="ascii" ref={host}>
      <div className="ascii-stack">
        <pre aria-hidden="true" className="ascii-ground">
          {ground}
        </pre>
        <pre aria-hidden="true" className="ascii-paths" ref={paths} />
      </div>
      <p className="vh">{alt}</p>
    </div>
  );
}
