import * as React from "react";

/**
 * Frost-pill tab strip (the mission-control pattern). Active = frost-12 fill; no underlines.
 */
export interface TabsProps {
  /** Tab list: strings or { label, icon?, count? }. */
  tabs?: Array<string | { label: React.ReactNode; icon?: React.ReactNode; count?: number }>;
  /** Controlled active index. Omit to use internal state. */
  active?: number;
  defaultActive?: number;
  /** Called with the picked index. */
  onChange?: (index: number) => void;
  style?: React.CSSProperties;
}

export declare function Tabs(props: TabsProps): JSX.Element;
