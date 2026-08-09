import * as React from "react";

/**
 * Segmented control: bordered pill of 2–4 mutually exclusive options (the Maestro settings pattern).
 * Active option wears frost-12. Use Tabs for view switching, Select for long lists.
 */
export interface SegmentedProps {
  /** Options: strings or { value, label, icon? }. */
  options?: Array<string | { value: string; label?: React.ReactNode; icon?: React.ReactNode }>;
  /** The selected option's value. */
  value?: string;
  /** Called with the picked value. */
  onChange?: (value: string) => void;
  style?: React.CSSProperties;
}

export declare function Segmented(props: SegmentedProps): JSX.Element;
