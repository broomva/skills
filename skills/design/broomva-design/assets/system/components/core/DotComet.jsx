import React from "react";

/* The tidepool dot — the running signal at dot scale. The Undertow's
   blue → ice weather drifts inside the circle: one motion language at every
   scale. For list rows, status lines, chips, and the bench in the chrome.
   Requires styles.css (tokens/motion.css). */
export function DotComet({ size = 15, style, ...rest }) {
  return (
    <span
      className="bv-dot-live"
      style={{ width: size, height: size, ...style }}
      aria-hidden="true"
      {...rest}
    />
  );
}
