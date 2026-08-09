import React from "react";
import { Button } from "../core/Button.jsx";
import { Receipt } from "./Receipt.jsx";
import { WorkState } from "./WorkState.jsx";

/* The look — the gate's run card. Compresses a session to:
   what changed · what it decided · what it asks. Approve / Send back
   are the only controls. A fast, confident look earns the next longer
   unsupervised run. */
export function RunCard({ state = "needs-you", agent, duration, title, decided, asks, receipts = [], onApprove, onSendBack, style }) {
  return (
    <div style={{
      border: "1px solid var(--bv-border-5)",
      borderRadius: "var(--bv-radius-xl)",
      background: "var(--card)",
      boxShadow: "var(--bv-shadow-edge)",
      padding: "14px 16px",
      display: "flex", flexDirection: "column", gap: 12,
      maxWidth: "100%", ...style,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--muted-foreground)" }}>
        <WorkState state={state} />
        {agent && <span>· {agent}</span>}
        {duration && <span style={{ marginLeft: "auto" }}>{duration} unsupervised</span>}
      </div>
      {title && (
        <div style={{ fontSize: 15, fontWeight: 500, lineHeight: 1.4, color: "var(--foreground)" }}>{title}</div>
      )}
      {decided && (
        <div style={{ fontSize: 13, lineHeight: 1.55, color: "var(--muted-foreground)" }}>
          <span style={{ fontWeight: 500, color: "var(--foreground)" }}>Decided</span> — {decided}
        </div>
      )}
      {asks && (
        <div style={{ fontSize: 13, lineHeight: 1.55, color: "var(--muted-foreground)" }}>
          <span style={{ fontWeight: 500, color: "var(--foreground)" }}>Asks</span> — {asks}
        </div>
      )}
      {receipts.length > 0 && <Receipt rows={receipts} />}
      {(onApprove || onSendBack) && (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {onApprove && <Button variant="primary" size="sm" onClick={onApprove}>Approve</Button>}
          {onSendBack && <Button variant="ghost" size="sm" onClick={onSendBack}>Send back</Button>}
        </div>
      )}
    </div>
  );
}
