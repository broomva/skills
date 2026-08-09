import React from "react";

/* 36px square ghost button for a single icon. Hover = frosted blue fill. */
export function IconButton({ label, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: "var(--bv-h-icon)", height: "var(--bv-h-icon)",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        borderRadius: "var(--bv-radius-lg)", border: "none",
        background: hover ? "var(--bv-frost-8)" : "transparent",
        color: "var(--bv-gray-700)", cursor: "pointer", flexShrink: 0,
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}
