import React from "react";
import { Button } from "../core/Button.jsx";

/* Modal dialog — earned glass (.bv-glass-heavy) over the blue-black scrim.
   Title 18/600, body 14 muted, actions right-aligned. Esc/scrim close. */
export function Dialog({ open = true, title, children, actions, onClose, width = 440, style }) {
  React.useEffect(() => {
    if (!open || !onClose) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget && onClose) onClose(); }}
      style={{
        position: "fixed", inset: 0, zIndex: 60,
        background: "oklch(0.135 0.02 272 / 0.42)",
        backdropFilter: "blur(2px)", WebkitBackdropFilter: "blur(2px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 32,
      }}
    >
      <div
        role="dialog" aria-modal="true"
        className="bv-glass-heavy"
        style={{
          width: "min(" + width + "px, 100%)", maxHeight: "calc(100vh - 64px)",
          overflowY: "auto", padding: "22px 24px",
          display: "flex", flexDirection: "column", gap: 14, ...style,
        }}
      >
        {title && (
          <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em", color: "var(--foreground)" }}>
            {title}
          </div>
        )}
        <div style={{ fontSize: 14, lineHeight: 1.55, color: "var(--muted-foreground)" }}>
          {children}
        </div>
        {actions && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, paddingTop: 4 }}>
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}

/* Convenience: a confirm-shaped dialog. */
export function ConfirmDialog({ open, title, body, confirmLabel = "Approve", cancelLabel = "Cancel", onConfirm, onClose }) {
  return (
    <Dialog
      open={open} title={title} onClose={onClose}
      actions={
        <React.Fragment>
          <Button variant="ghost" onClick={onClose}>{cancelLabel}</Button>
          <Button variant="primary" onClick={onConfirm}>{confirmLabel}</Button>
        </React.Fragment>
      }
    >
      {body}
    </Dialog>
  );
}
