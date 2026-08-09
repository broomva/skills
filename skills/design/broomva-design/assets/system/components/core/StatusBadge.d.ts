import * as React from "react";

/** Status pill: soft capsule, colored dot, sentence-case label. */
export interface StatusBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Dot color. Default "info". */
  status?: "success" | "info" | "warning" | "danger" | "neutral";
  /** Pulses the dot (active/running). Default false. */
  pulse?: boolean;
  children?: React.ReactNode;
}

export declare function StatusBadge(props: StatusBadgeProps): JSX.Element;
