import * as React from "react";

/** One stage on the rail. */
export interface LifecycleStage {
  /** Stage name, e.g. "running". */
  name: React.ReactNode;
  /** "passed" | "current" | "warn" | "upcoming". Default "upcoming". */
  state?: "passed" | "current" | "warn" | "upcoming";
  /** Small note under the current stage, e.g. "since 09:14". */
  note?: React.ReactNode;
}

/**
 * The lifecycle rail: horizontal stage tracker for the work-item inspector.
 * Evidence of position in the lifecycle — never a progress bar.
 */
export interface LifecycleRailProps {
  stages?: LifecycleStage[];
  style?: React.CSSProperties;
}

export declare function LifecycleRail(props: LifecycleRailProps): JSX.Element;
