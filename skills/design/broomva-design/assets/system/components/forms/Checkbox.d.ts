import * as React from "react";

/**
 * 18px checkbox, chip radius. Checked = ink fill + white check; hover frosts blue.
 */
export interface CheckboxProps {
  /** Controlled checked state. Omit to use internal state. */
  checked?: boolean;
  defaultChecked?: boolean;
  /** Called with the next boolean value. */
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  /** Label text (sentence case). */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Checkbox(props: CheckboxProps): JSX.Element;
