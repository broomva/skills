import React from "react";

/* Toast — a floating glass notice (floating surfaces earn glass).
   Status dot instead of big icons; one optional action; no celebration. */
export function Toast({ status = "info", title, meta, action, onAction, onDismiss, style }) {
  const colors = {
    success: "var(--bv-success)",
    info: "var(--bv-info)",
    warning: "var(--bv-warning)",
    danger: "var(--bv-danger)",
    neutral: "var(--bv-gray-400)",
  };
  return (
    <div
      role="status"
      className="bv-glass"
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "10px 12px", width: "min(360px, 100%)",
        boxShadow: "var(--bv-shadow-card-hover)", ...style,
      }}
    >
      <span style={{
        width: 8, height: 8, borderRadius: 99, flexShrink: 0,
        background: colors[status] || colors.info,
      }}></span>
      <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
        <span style={{ fontSize: 13.5, fontWeight: 500, color: "var(--foreground)" }}>{title}</span>
        {meta && <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{meta}</span>}
      </span>
      {action && (
        <button
          type="button" onClick={onAction}
          style={{
            flexShrink: 0, border: "none", background: "transparent",
            font: "inherit", fontSize: 12.5, fontWeight: 500,
            color: "var(--bv-blue)", cursor: "pointer", padding: "4px 6px",
            borderRadius: "var(--bv-radius-lg)",
          }}
        >{action}</button>
      )}
      {onDismiss && (
        <button
          type="button" onClick={onDismiss} aria-label="Dismiss"
          style={{
            flexShrink: 0, width: 22, height: 22, border: "none",
            background: "transparent", color: "var(--muted-foreground)",
            cursor: "pointer", borderRadius: "var(--bv-radius-lg)",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" style={{ width: 13, height: 13 }}>
            <path d="M18 6 6 18"></path><path d="m6 6 12 12"></path>
          </svg>
        </button>
      )}
    </div>
  );
}
