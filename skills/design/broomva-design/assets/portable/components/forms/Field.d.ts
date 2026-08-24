import * as React from "react";

type FieldControlProps = {
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: React.AriaAttributes["aria-invalid"];
};

/** Accessible form row binding one persistent label and one hint or error to one control. */
export interface FieldProps {
  /** Explicit control ID. Generated automatically when omitted; a child ID takes precedence. */
  id?: string;
  /** Optional stable ID for the hint text. */
  hintId?: string;
  /** Optional stable ID for the error text. */
  errorId?: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
  /** Replaces the hint and marks the control aria-invalid. */
  error?: React.ReactNode;
  children: React.ReactElement<FieldControlProps>;
  style?: React.CSSProperties;
}

export declare function Field(props: FieldProps): React.JSX.Element;
