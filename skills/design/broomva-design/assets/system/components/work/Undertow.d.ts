import * as React from "react";

/**
 * The Undertow — the running signal. Wraps a matte card in the breathing halo.
 * Requires styles.css (tokens/motion.css) on the page.
 */
export interface UndertowProps {
  /** false renders children bare — toggle running state without remounting. Default true. */
  active?: boolean;
  /** The matte card being wrapped. */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

export declare function Undertow(props: UndertowProps): JSX.Element;
