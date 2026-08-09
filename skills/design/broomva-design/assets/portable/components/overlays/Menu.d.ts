import * as React from "react";

export interface MenuProps extends React.HTMLAttributes<HTMLDivElement> {
  minWidth?: number;
  /** Accessible name for the menu. Default "Actions". */
  ariaLabel?: string;
  /** Focus the first enabled item when mounted. Default true. */
  autoFocus?: boolean;
  onEscape?: () => void;
}

export declare function Menu(props: MenuProps): JSX.Element;

export interface MenuItemProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: React.ReactNode;
  kbd?: string;
  danger?: boolean;
}

export declare function MenuItem(props: MenuItemProps): JSX.Element;
export declare function MenuDivider(): JSX.Element;
