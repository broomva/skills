import React from "react";

/* Receipts — evidence blocks that stand in for progress bars.
   Branch, diffstat, judge verdict; mono for machine facts.
   The branch is the receipt: never fake percentages. */
export function Receipt({ rows = [], style }) {
  return (
    <div style={{
      border: "1px solid var(--bv-border-5)",
      borderRadius: "var(--bv-radius-lg)",
      background: "var(--bv-canvas-soft)",
      padding: "10px 12px",
      display: "flex", flexDirection: "column", gap: 7,
      fontSize: 12.5, ...style,
    }}>
      {rows.map((r, i) => <ReceiptRow key={i} {...r} />)}
    </div>
  );
}

export function ReceiptRow({ icon, label, code, style }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--muted-foreground)", ...style }}>
      {icon && <span style={{ display: "inline-flex", flexShrink: 0, width: 13, height: 13 }}>{icon}</span>}
      {label && <span>{label}</span>}
      {code && (
        <code style={{
          fontFamily: "var(--bv-font-mono, ui-monospace, monospace)",
          fontSize: 11.5, color: "var(--foreground)",
        }}>{code}</code>
      )}
    </div>
  );
}
