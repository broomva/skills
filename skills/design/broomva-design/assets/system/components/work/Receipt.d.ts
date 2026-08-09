import * as React from "react";

/** One evidence line: branch, diffstat, judge verdict… */
export interface ReceiptRowProps {
  /** 13px lucide icon element. */
  icon?: React.ReactNode;
  /** Plain-voice label, e.g. "judge:". */
  label?: React.ReactNode;
  /** Mono machine fact, e.g. "run/7c2f · +214 −38". */
  code?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * Receipt block — evidence over claims. Replaces progress bars everywhere.
 */
export interface ReceiptProps {
  rows?: ReceiptRowProps[];
  style?: React.CSSProperties;
}

export declare function Receipt(props: ReceiptProps): JSX.Element;
export declare function ReceiptRow(props: ReceiptRowProps): JSX.Element;
