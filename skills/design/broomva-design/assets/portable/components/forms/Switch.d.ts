import * as React from "react";

/** Compact immediate on/off setting with a sliding thumb. */
export interface SwitchProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  checked?: boolean;
  defaultChecked?: boolean;
  onChange?: (checked: boolean) => void;
}

export declare function Switch(props: SwitchProps): JSX.Element;
