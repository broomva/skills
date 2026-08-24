import * as React from "react";

/** Matte content container with an optional hover lift. */
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Lifts with a blue-tinted shadow on hover. Default false. */
  interactive?: boolean;
  children?: React.ReactNode;
}

export declare function Card(props: CardProps): React.JSX.Element;
