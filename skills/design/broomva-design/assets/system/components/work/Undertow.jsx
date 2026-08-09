import React from "react";

/* The Undertow — THE running signal. Wraps a matte card in the contained
   4px halo (breathing pools + counter-phase tide + faint 9s orbit) defined
   in tokens/motion.css. Presence, not progress. `active={false}` renders
   children bare, so running state can toggle without remounting. */
export function Undertow({ active = true, children, style }) {
  if (!active) return <React.Fragment>{children}</React.Fragment>;
  return (
    <div className="bv-undertow" style={style}>
      <span className="bv-undertow-orbit"></span>
      {children}
    </div>
  );
}
