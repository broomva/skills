import * as React from "react";

/** Matte content card; optional hover lift and the Undertow running halo. */
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Lifts with a blue-tinted shadow on hover. Default false. */
  interactive?: boolean;
  /** Wraps the card in the Undertow halo (contained 4px frame: pools, tide,
   *  faint orbit). The card itself stays matte. Default false. */
  running?: boolean;
  children?: React.ReactNode;
}

export declare function Card(props: CardProps): JSX.Element;
