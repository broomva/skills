import * as React from "react";

export interface TabItem {
  id?: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  count?: number;
  /** ID of the associated role="tabpanel" element. */
  panelId?: string;
}

export interface TabsProps {
  tabs?: Array<string | TabItem>;
  active?: number;
  defaultActive?: number;
  onChange?: (index: number) => void;
  /** Accessible name for the tab list. Default "Sections". */
  ariaLabel?: string;
  style?: React.CSSProperties;
}

export declare function Tabs(props: TabsProps): JSX.Element;
