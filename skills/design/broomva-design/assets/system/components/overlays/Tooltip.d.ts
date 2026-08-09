import * as React from "react";

/**
 * Hover tooltip — a small glass chip, 12px, no arrow. Wraps its trigger inline.
 */
export interface TooltipProps {
  /** Tooltip text, sentence case. */
  label: React.ReactNode;
  /** Placement. Default "top". */
  side?: "top" | "bottom" | "left" | "right";
  /** The trigger element. */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Tooltip(props: TooltipProps): JSX.Element;
