import React from "react";
import { Button } from "../core/Button.jsx";

const FOCUSABLE = [
  "a[href]", "button:not([disabled])", "input:not([disabled])",
  "select:not([disabled])", "textarea:not([disabled])", "[tabindex]:not([tabindex='-1'])",
].join(",");

export function Dialog({
  open = true, title, ariaLabel, children, actions, onClose, width = 440, style,
}) {
  const dialogRef = React.useRef(null);
  const previousFocus = React.useRef(null);
  const titleId = React.useId();

  React.useEffect(() => {
    if (!open) return undefined;
    previousFocus.current = document.activeElement;
    const dialog = dialogRef.current;
    const first = dialog?.querySelector(FOCUSABLE);
    (first || dialog)?.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape" && onClose) {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = [...dialog.querySelectorAll(FOCUSABLE)];
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const firstItem = focusable[0];
      const lastItem = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousFocus.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      onClick={(event) => {
        if (event.target === event.currentTarget && onClose) onClose();
      }}
      style={{
        position: "fixed", inset: 0, zIndex: 60,
        background: "oklch(0.135 0.02 272 / 0.42)",
        backdropFilter: "blur(2px)", WebkitBackdropFilter: "blur(2px)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 32,
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={!title ? (ariaLabel || "Dialog") : undefined}
        tabIndex={-1}
        className="bv-glass-heavy"
        style={{
          width: `min(${width}px, 100%)`, maxHeight: "calc(100vh - 64px)",
          overflowY: "auto", padding: "22px 24px",
          display: "flex", flexDirection: "column", gap: 14, ...style,
        }}
      >
        {title && (
          <div id={titleId} style={{
            fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em",
            color: "var(--foreground)",
          }}>
            {title}
          </div>
        )}
        <div style={{ fontSize: 14, lineHeight: 1.55, color: "var(--muted-foreground)" }}>
          {children}
        </div>
        {actions && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "flex-end",
            gap: 8, paddingTop: 4,
          }}>
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open, title, body, confirmLabel = "Confirm", cancelLabel = "Cancel",
  onConfirm, onClose,
}) {
  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      actions={(
        <React.Fragment>
          <Button variant="ghost" onClick={onClose}>{cancelLabel}</Button>
          <Button variant="primary" onClick={onConfirm}>{confirmLabel}</Button>
        </React.Fragment>
      )}
    >
      {body}
    </Dialog>
  );
}
