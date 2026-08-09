import * as React from "react";

/** Circular avatar — initials over an accent, or an image. */
export interface AvatarProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Full name; initials derived from it. */
  name?: string;
  /** Accent fill behind initials. Default ai-blue. */
  color?: string;
  /** Diameter in px. Default 22. */
  size?: number;
  /** Optional image URL (replaces initials). */
  src?: string;
}

export declare function Avatar(props: AvatarProps): JSX.Element;
