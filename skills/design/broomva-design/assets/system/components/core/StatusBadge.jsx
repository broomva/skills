import React from "react";

/* Status pill: soft gray capsule + colored dot + sentence-case label. */
export function StatusBadge({ status = "info", pulse = false, children, style, ...rest }) {
  const colors = {
    success: "var(--bv-success)",
    info: "var(--bv-info)",
    warning: "var(--bv-warning)",
    danger: "var(--bv-danger)",
    neutral: "var(--bv-gray-400)",
  };
  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: 7,
        height: 26, padding: "0 12px",
        borderRadius: "var(--bv-radius-full)",
        background: "var(--bv-canvas-soft)",
        fontSize: 12, fontWeight: 500, color: "var(--foreground)",
        ...style,
      }}
      {...rest}
    >
      <style>{`@keyframes bv-pulse { 0%,100% { opacity: 0.45; transform: scale(1); } 50% { opacity: 1; transform: scale(1.08); } }`}</style>
      <span style={{
        width: 8, height: 8, borderRadius: 99, flexShrink: 0,
        background: colors[status] || colors.info,
        animation: pulse ? "bv-pulse 1s ease-in-out infinite" : "none",
      }} />
      {children}
    </span>
  );
}
