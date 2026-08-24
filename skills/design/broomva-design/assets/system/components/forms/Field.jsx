import React from "react";

/* Label + control + hint/error. Labels are sentence case, 13px medium.
   Errors use --bv-danger text only; the control never turns red. */
export function Field({ label, hint, error, children, style }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, ...style }}>
      {label && (
        <span style={{ fontSize: 13, fontWeight: 500, color: "var(--foreground)" }}>{label}</span>
      )}
      {children}
      {error ? (
        <span style={{ fontSize: 12, color: "var(--bv-danger)" }}>{error}</span>
      ) : hint ? (
        <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{hint}</span>
      ) : null}
    </div>
  );
}
