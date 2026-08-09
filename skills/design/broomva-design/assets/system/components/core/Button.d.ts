import * as React from "react";

/**
 * Pill-shaped action button. Primary = ink fill; hover lightens or frosts blue.
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style. Default "primary". */
  variant?: "primary" | "secondary" | "soft" | "ghost";
  /** Height step: 28 / 36 / 44px. Default "md". */
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  children?: React.ReactNode;
}

export declare function Button(props: ButtonProps): JSX.Element;
