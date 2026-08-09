import * as React from "react";

/**
 * Plain-voice work state: dot + label. Running wears the tidepool dot; standing pulses.
 * Canon vocabulary only — never render system enums (Todo, InProgress, Blocked, InReview).
 */
export interface WorkStateProps {
  /** Canon state. "needs-you" owns accent-blue. Default "queued". */
  state?: "queued" | "running" | "stuck" | "needs-you" | "done" | "standing";
  /** "inline" (bare dot + label) or "chip" (soft capsule). Default "inline". */
  variant?: "inline" | "chip";
  /** Override the label; defaults to the canon plain-voice word. */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function WorkState(props: WorkStateProps): JSX.Element;
