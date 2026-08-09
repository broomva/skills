import * as React from "react";

/**
 * Form row: sentence-case label, the control, and one hint or error line.
 */
export interface FieldProps {
  /** Sentence-case label above the control. */
  label?: React.ReactNode;
  /** Muted helper line below the control. */
  hint?: React.ReactNode;
  /** Replaces the hint; danger-colored text. The control itself never turns red. */
  error?: React.ReactNode;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Field(props: FieldProps): JSX.Element;
