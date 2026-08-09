import * as React from "react";

/** One row in the palette. */
export interface CommandPaletteItem {
  id: string;
  title: React.ReactNode;
  /** Muted second line. */
  meta?: React.ReactNode;
  /** 15px lucide icon element. */
  icon?: React.ReactNode;
  /** Shortcut hint, e.g. "⌘K". */
  kbd?: string;
}

/**
 * The command palette combobox — earned glass, grouped results, kbd hints.
 * Static: pass filtered groups; render inside a scrim for the overlay form.
 */
export interface CommandPaletteProps {
  query?: string;
  placeholder?: string;
  groups?: Array<{ label?: string; items: CommandPaletteItem[] }>;
  /** id of the keyboard-active row. */
  activeId?: string;
  onQuery?: (query: string) => void;
  onPick?: (item: CommandPaletteItem) => void;
  /** Show the navigate/open footer. Default true. */
  footer?: boolean;
  style?: React.CSSProperties;
}

export declare function CommandPalette(props: CommandPaletteProps): JSX.Element;
