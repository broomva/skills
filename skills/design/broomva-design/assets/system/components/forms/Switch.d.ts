import * as React from "react";

/**
 * 38×22 toggle (the Maestro settings switch). On = ai-blue, off = gray track; the thumb slides, never bounces.
 */
export interface SwitchProps {
  /** Controlled on/off state. Omit to use internal state. */
  checked?: boolean;
  defaultChecked?: boolean;
  /** Called with the next boolean value. */
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  style?: React.CSSProperties;
}

export declare function Switch(props: SwitchProps): JSX.Element;
