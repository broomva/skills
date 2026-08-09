import React from "react";

/* Pill-shaped action button. Primary is ink fill (dark blue, never black);
   hover lightens one step or frosts blue. No scale, no transform. */
export function Button({ variant = "primary", size = "md", disabled = false, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const sizes = {
    sm: { height: 28, padding: "0 10px", fontSize: 12 },
    md: { height: "var(--bv-h-btn)", padding: "0 14px", fontSize: 14 },
    lg: { height: "var(--bv-h-btn-lg)", padding: "0 18px", fontSize: 14 },
  };
  const variants = {
    primary: {
      background: disabled ? "var(--bv-gray-300)" : hover ? "var(--bv-ink-hover)" : "var(--primary)",
      color: "var(--primary-foreground)",
      border: "1px solid transparent",
    },
    secondary: {
      background: hover ? "var(--bv-frost-4)" : "var(--card)",
      color: "var(--foreground)",
      border: "1px solid var(--bv-border-15)",
    },
    soft: {
      background: hover ? "var(--bv-frost-8)" : "var(--bv-canvas-soft)",
      color: "var(--foreground)",
      border: "1px solid transparent",
    },
    ghost: {
      background: hover ? "var(--bv-frost-8)" : "transparent",
      color: "var(--foreground)",
      border: "1px solid transparent",
    },
  };
  return (
    <button
      type="button"
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        borderRadius: "var(--bv-radius-full)",
        fontFamily: "inherit", fontWeight: 500, whiteSpace: "nowrap",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
        ...sizes[size], ...variants[variant], ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}
