import * as React from "react";
import { ReceiptRowProps } from "./Receipt";

/**
 * The look — the gate's run card: what changed · what it decided · what it asks.
 * Approve / Send back are the only controls. Never a progress bar.
 */
export interface RunCardProps {
  /** Canon work state for the header. Default "needs-you". */
  state?: "queued" | "running" | "stuck" | "needs-you" | "done" | "standing";
  /** Agent name, e.g. "claude". */
  agent?: React.ReactNode;
  /** Unsupervised duration, e.g. "3h 40m". */
  duration?: React.ReactNode;
  /** What changed — one sentence. */
  title?: React.ReactNode;
  /** What it decided. */
  decided?: React.ReactNode;
  /** What it asks. */
  asks?: React.ReactNode;
  /** Evidence rows (branch, diffstat, judge verdict). */
  receipts?: ReceiptRowProps[];
  /** Renders the primary Approve button. */
  onApprove?: () => void;
  /** Renders the ghost Send back button. */
  onSendBack?: () => void;
  style?: React.CSSProperties;
}

export declare function RunCard(props: RunCardProps): JSX.Element;
