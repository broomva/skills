import * as React from "react";

/** One unsupervised stretch on the bar (percent units). */
export interface AutonomySegment {
  /** Left edge, 0–100. */
  start: number;
  /** Width, 0–100. */
  width: number;
  /** The stretch running right now (full-opacity blue→ice gradient). */
  live?: boolean;
}

/**
 * The autonomy scoreboard: unsupervised hours + a bar of stretches with a
 * notch per human look. Never a completion percentage.
 */
export interface AutonomyScoreboardProps {
  /** Default "unsupervised today". */
  label?: React.ReactNode;
  /** The headline duration, e.g. "6h 24m". */
  hours: React.ReactNode;
  /** Footnote, e.g. "2 looks · longest run 3h 50m". */
  sub?: React.ReactNode;
  segments?: AutonomySegment[];
  /** Human looks as percent positions, 0–100. */
  notches?: number[];
  /** Extra content rendered inside the card (e.g. an anchored popover). */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function AutonomyScoreboard(props: AutonomyScoreboardProps): JSX.Element;
