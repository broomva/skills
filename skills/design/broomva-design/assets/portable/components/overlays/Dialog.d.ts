import * as React from "react";

interface DialogBaseProps {
  open?: boolean;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  onClose?: () => void;
  width?: number;
  style?: React.CSSProperties;
}

type DialogTitle = string | number | React.ReactElement;

type DialogName =
  | { title: DialogTitle; ariaLabel?: string }
  | { title?: undefined; ariaLabel: string };

/** Modal dialog requiring either a visible title or an explicit accessible name. */
export type DialogProps = DialogBaseProps & DialogName;

export declare function Dialog(props: DialogProps): React.JSX.Element;

export interface ConfirmDialogProps {
  open?: boolean;
  title: DialogTitle;
  body?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  onClose?: () => void;
}

export declare function ConfirmDialog(props: ConfirmDialogProps): React.JSX.Element;
