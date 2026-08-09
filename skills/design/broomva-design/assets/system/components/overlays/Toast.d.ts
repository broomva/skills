import * as React from "react";

/**
 * Floating glass notice: status dot, one line, optional action. No celebration.
 */
export interface ToastProps {
  /** Dot color. Default "info". */
  status?: "success" | "info" | "warning" | "danger" | "neutral";
  /** Sentence-case message. */
  title: React.ReactNode;
  /** Muted second line. */
  meta?: React.ReactNode;
  /** Action label, e.g. "Open". */
  action?: React.ReactNode;
  onAction?: () => void;
  /** Shows the × button when provided. */
  onDismiss?: () => void;
  style?: React.CSSProperties;
}

export declare function Toast(props: ToastProps): JSX.Element;
