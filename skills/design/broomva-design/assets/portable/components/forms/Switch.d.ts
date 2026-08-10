import * as React from "react";

/** Compact immediate on/off setting. Provide an ARIA name or associate a visible label. */
export type SwitchProps = Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  "onChange"
> & {
  checked?: boolean;
  defaultChecked?: boolean;
  onChange?: (checked: boolean) => void;
};

export declare function Switch(props: SwitchProps): React.JSX.Element;
