import type { CSSProperties, ReactNode } from "react";
import { interpolate, useCurrentFrame } from "remotion";

/**
 * The shared vocabulary for every composition on this site.
 *
 * The panels are dark in both page themes on purpose. They are readouts of a
 * running system rather than regions of the document, and a figure that
 * inverts with the theme is a figure that has to be authored twice and checked
 * twice. The hero made the same call.
 *
 * The stroke vocabulary is the product's, not decoration, and it matches the
 * proof page exactly:
 *   SOLID  = RECORDED    something that happened
 *   DOTTED = PINNED      reproducible under a fixed seed
 *   DASHED = STABLE      reproducible in distribution only
 */

export const FPS = 30;
export const W = 1600;
export const H = 1000;

export const C = {
  bg: "#0b0e12",
  grid: "oklch(0.97 0.004 265 / 0.05)",
  axis: "oklch(0.97 0.004 265 / 0.14)",
  rule: "oklch(0.97 0.004 265 / 0.09)",
  fg: "oklch(0.965 0.004 265)",
  dim: "oklch(0.965 0.004 265 / 0.72)",
  tag: "oklch(0.965 0.004 265 / 0.52)",
  faint: "oklch(0.965 0.004 265 / 0.28)",
  accent: "oklch(0.72 0.13 260)",
  accentSoft: "oklch(0.72 0.13 260 / 0.16)",
  ok: "oklch(0.78 0.16 152)",
  warn: "oklch(0.82 0.14 85)",
  crit: "oklch(0.72 0.18 27)",
} as const;

export const MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace';
export const SANS =
  'ui-sans-serif, -apple-system, BlinkMacSystemFont, system-ui, "Segoe UI", Helvetica, Arial, sans-serif';

/** A cut, not a crossfade: [0,1] over `len` frames starting at `from`. */
export const at = (frame: number, from: number, len = 12) =>
  interpolate(frame, [from, from + len], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

/** Ease-out over a window, for anything that travels rather than appears. */
export const ease = (frame: number, from: number, len: number) => {
  const t = at(frame, from, len);
  return 1 - (1 - t) ** 3;
};

export const Stage: React.FC<{ children: ReactNode }> = ({ children }) => (
  // The accessible name lives on the panel wrapper (components/MotionPanel.tsx
  // carries role="img" and the figure's full description). A <title> here would
  // announce the figure twice and say less than the description does.
  <svg
    viewBox={`0 0 ${W} ${H}`}
    width="100%"
    height="100%"
    aria-hidden="true"
    style={{ display: "block", background: C.bg }}
  >
    <defs>
      <pattern id="k-grid" width={80} height={80} patternUnits="userSpaceOnUse">
        <path d="M80 0H0v80" fill="none" stroke={C.grid} strokeWidth={1} />
      </pattern>
    </defs>
    <rect width={W} height={H} fill="url(#k-grid)" />
    {children}
  </svg>
);

/**
 * The uppercase micro label. One size, one tracking, everywhere.
 *
 * These three sizes are set for the size the panel is actually DISPLAYED at,
 * not for the composition's own coordinate space. The panel renders 1600px of
 * composition into roughly 740px of column, so a 21px label lands under 10px
 * on screen -- illegible, not merely small. Same failure the hero's portrait
 * breakpoint documents, and the same fix: size for the rendered pixel.
 */
export const Tag: React.FC<{
  x: number;
  y: number;
  children: ReactNode;
  fill?: string;
  anchor?: "start" | "middle" | "end";
  opacity?: number;
}> = ({ x, y, children, fill = C.tag, anchor = "start", opacity = 1 }) => (
  <text
    x={x}
    y={y}
    fill={fill}
    opacity={opacity}
    textAnchor={anchor}
    style={{ font: `400 30px ${MONO}`, letterSpacing: "0.16em" }}
  >
    {children}
  </text>
);

export const Mono: React.FC<{
  x: number;
  y: number;
  children: ReactNode;
  size?: number;
  fill?: string;
  anchor?: "start" | "middle" | "end";
  opacity?: number;
  weight?: number;
}> = ({ x, y, children, size = 34, fill = C.fg, anchor = "start", opacity = 1, weight = 400 }) => (
  <text
    x={x}
    y={y}
    fill={fill}
    opacity={opacity}
    textAnchor={anchor}
    style={{ font: `${weight} ${size}px ${MONO}`, letterSpacing: "0.01em" }}
  >
    {children}
  </text>
);

/**
 * The one line of plain language a panel is allowed.
 *
 * SVG text does not wrap. At 40px in this stack the stage fits roughly 62
 * characters before the line runs off the right edge, and it runs off silently
 * -- no overflow, no clip, no warning. Keep captions short enough to read in
 * one beat and they stay inside that budget on their own.
 */
export const Caption: React.FC<{
  y?: number;
  children: ReactNode;
  from: number;
}> = ({ y = H - 54, children, from }) => {
  const frame = useCurrentFrame();
  return (
    <text
      x={64}
      y={y}
      fill={C.dim}
      opacity={at(frame, from)}
      style={{ font: `400 40px ${SANS}`, letterSpacing: "-0.01em" }}
    >
      {children}
    </text>
  );
};

/** Header rail: which operator is running, and on what. */
export const Rail: React.FC<{ left: string; right?: string }> = ({ left, right }) => (
  <>
    <Tag x={64} y={78} fill={C.dim}>
      {left}
    </Tag>
    {right ? (
      <Tag x={W - 64} y={78} anchor="end" fill={C.faint}>
        {right}
      </Tag>
    ) : null}
    <line x1={64} y1={104} x2={W - 64} y2={104} stroke={C.rule} strokeWidth={1} />
  </>
);

export const panelStyle: CSSProperties = {
  width: "100%",
  height: "100%",
  background: C.bg,
};
