import React from "react";

/* Matte content container with an optional blue-tinted hover lift. Domain
   extensions may wrap it with their own semantic state treatment. */
export function Card({ interactive = false, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
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
}
