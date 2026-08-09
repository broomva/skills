import * as React from "react";

/** The Undertow miniaturized onto a status dot: a 1.8s comet orbiting the
 *  state core. Marks running work in rows, chips and status lines, and the
 *  orchestrator's presence chip in the chrome. */
export interface DotCometProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Outer diameter in px. Default 15. */
  size?: number;
  /** Core color. Default var(--bv-info). */
  color?: string;
}

export declare function DotComet(props: DotCometProps): JSX.Element;
