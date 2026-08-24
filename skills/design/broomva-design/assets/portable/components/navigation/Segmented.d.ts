import * as React from "react";

/** Segmented control for 2–4 short, mutually exclusive options. */
export interface SegmentedProps {
  options?: Array<string | { value: string; label?: React.ReactNode; icon?: React.ReactNode }>;
  value?: string;
  onChange?: (value: string) => void;
  style?: React.CSSProperties;
}

export declare function Segmented(props: SegmentedProps): React.JSX.Element;
