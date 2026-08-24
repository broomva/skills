import * as React from "react";

/**
 * Native select styled to the input recipe: rounded-md, gray edge, ai-blue focus ring.
 */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  /** Option list: strings or { value, label } pairs. */
  options?: Array<string | { value: string; label: string }>;
  /** Disabled first option shown until a value is picked. */
  placeholder?: string;
}

export declare function Select(props: SelectProps): JSX.Element;
