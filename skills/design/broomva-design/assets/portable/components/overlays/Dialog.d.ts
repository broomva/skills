import * as React from "react";

export interface DialogProps {
  open?: boolean;
  title?: React.ReactNode;
  /** Required when title is omitted. */
  ariaLabel?: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  onClose?: () => void;
  width?: number;
  style?: React.CSSProperties;
}

export declare function Dialog(props: DialogProps): JSX.Element;

export interface ConfirmDialogProps {
  open?: boolean;
  title?: React.ReactNode;
  body?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  onClose?: () => void;
}

export declare function ConfirmDialog(props: ConfirmDialogProps): JSX.Element;
