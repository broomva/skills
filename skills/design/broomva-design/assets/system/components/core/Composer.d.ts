import * as React from "react";

/**
 * The chat composer: rounded-28 glass capsule with the signature frosted-blue halo.
 */
export interface ComposerProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  /** Input placeholder. Default "Message Broomva". */
  placeholder?: string;
  /** Controlled value (optional; uncontrolled if omitted). */
  value?: string;
  onChange?: (value: string) => void;
  /** Called with trimmed text on Enter or send click. */
  onSend?: (text: string) => void;
  /** Optional leading element (e.g. attach IconButton). */
  leading?: React.ReactNode;
}

export declare function Composer(props: ComposerProps): JSX.Element;
