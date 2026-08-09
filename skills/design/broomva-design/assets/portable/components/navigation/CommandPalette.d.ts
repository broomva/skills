import * as React from "react";

export interface CommandPaletteItem {
  id: string;
  title: React.ReactNode;
  meta?: React.ReactNode;
  icon?: React.ReactNode;
  kbd?: string;
}

export interface CommandPaletteProps {
  query?: string;
  /** Persistent visible label. Default "Commands". */
  label?: string;
  placeholder?: string;
  groups?: Array<{ label?: string; items: CommandPaletteItem[] }>;
  activeId?: string;
  onActiveChange?: (id: string) => void;
  onQuery?: (query: string) => void;
  onPick?: (item: CommandPaletteItem) => void;
  onEscape?: () => void;
  footer?: boolean;
  style?: React.CSSProperties;
}

export declare function CommandPalette(props: CommandPaletteProps): JSX.Element;
