import * as React from "react";

/**
 * 18px radio. Checked = thick ink ring; hover frosts blue.
 */
export interface RadioProps {
  /** Controlled checked state. Omit to use internal state. */
  checked?: boolean;
  defaultChecked?: boolean;
  /** Called with true when this radio is picked. */
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  /** Label text (sentence case). */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Radio(props: RadioProps): JSX.Element;
