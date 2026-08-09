import React from "react";

/* Matte card. rounded-12, whisper border, edge shadow at rest, blue-tinted
   lift on hover (when interactive). When running, the card stays matte and
   wears the Undertow: a contained 4px halo frame (breathing pools, counter-
   phase tide, faint 9s orbit). Requires styles.css (tokens/motion.css). */
export function Card({ interactive = false, running = false, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const inner = (
    <div
      onMouseEnter={interactive ? () => setHover(true) : undefined}
      onMouseLeave={interactive ? () => setHover(false) : undefined}
      style={{
        background: "var(--card)",
        border: "1px solid var(--bv-border-5)",
        borderRadius: "var(--bv-radius-xl)",
        boxShadow: hover ? "var(--bv-shadow-card-hover)" : "var(--bv-shadow-edge)",
        padding: "12px 14px",
        display: "flex", flexDirection: "column", gap: 8,
        cursor: interactive ? "pointer" : "default",
        transition: "box-shadow var(--bv-dur-fast) var(--bv-ease-standard)",
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
  if (!running) return inner;
  return (
    <div className="bv-undertow">
      <span className="bv-undertow-orbit" />
      {inner}
    </div>
  );
}
