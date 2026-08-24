import * as React from "react";

/**
 * Popover menu on glass. Compose with MenuItem and MenuDivider; position it yourself.
 */
export interface MenuProps {
  children?: React.ReactNode;
  /** Default 180. */
  minWidth?: number;
  style?: React.CSSProperties;
}

export declare function Menu(props: MenuProps): JSX.Element;

export interface MenuItemProps {
  /** 15px lucide icon element. */
  icon?: React.ReactNode;
  /** Shortcut hint, e.g. "⌘D". */
  kbd?: string;
  /** Danger-colored destructive item. */
  danger?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function MenuItem(props: MenuItemProps): JSX.Element;

export declare function MenuDivider(): JSX.Element;
