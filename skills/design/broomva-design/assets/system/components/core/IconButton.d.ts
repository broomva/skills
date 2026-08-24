import * as React from "react";

/** 36px square ghost button holding one 20px Lucide icon. */
export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible name (becomes aria-label + title). Required. */
  label: string;
  /** The icon element (Lucide, 20px, stroke 2, currentColor). */
  children?: React.ReactNode;
}

export declare function IconButton(props: IconButtonProps): JSX.Element;
