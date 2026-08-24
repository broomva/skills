import * as React from "react";

/**
 * Modal dialog on earned glass over the blue-black scrim. Esc and scrim-click close.
 */
export interface DialogProps {
  open?: boolean;
  /** Sentence-case title, 18/600. */
  title?: React.ReactNode;
  /** Body copy, 14px muted. */
  children?: React.ReactNode;
  /** Right-aligned action buttons. */
  actions?: React.ReactNode;
  onClose?: () => void;
  /** Card width in px. Default 440. */
  width?: number;
  style?: React.CSSProperties;
}

export declare function Dialog(props: DialogProps): JSX.Element;

/** Confirm-shaped dialog: ghost cancel + primary confirm. */
export interface ConfirmDialogProps {
  open?: boolean;
  title?: React.ReactNode;
  body?: React.ReactNode;
  /** Default "Approve". */
  confirmLabel?: string;
  /** Default "Cancel". */
  cancelLabel?: string;
  onConfirm?: () => void;
  onClose?: () => void;
}

export declare function ConfirmDialog(props: ConfirmDialogProps): JSX.Element;
