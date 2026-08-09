import React from "react";

/* Popover menu — glass (popovers earn glass). Items 13px, hover frost-8,
   danger items in --bv-danger. Static positioning is the caller's job. */
export function Menu({ children, minWidth = 180, style }) {
  return (
    <div
      className="bv-glass"
      role="menu"
      style={{
        display: "inline-flex", flexDirection: "column",
        padding: 5, minWidth, ...style,
      }}
    >
      {children}
    </div>
  );
}

export function MenuItem({ icon, kbd, danger = false, disabled = false, onClick, children, style }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button" role="menuitem" disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", alignItems: "center", gap: 9, width: "100%", textAlign: "left",
        padding: "7px 9px", borderRadius: "var(--bv-radius-lg)", border: "none",
        background: hover && !disabled ? "var(--bv-frost-8)" : "transparent",
        font: "inherit", fontSize: 13,
        color: disabled ? "var(--bv-gray-400)" : danger ? "var(--bv-danger)" : "var(--foreground)",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
        ...style,
      }}
    >
      {icon && (
        <span style={{ display: "inline-flex", flexShrink: 0, color: danger ? "var(--bv-danger)" : "var(--bv-gray-600)" }}>
          {icon}
        </span>
      )}
      <span style={{ flex: 1, minWidth: 0 }}>{children}</span>
      {kbd && (
        <span style={{
          flexShrink: 0, fontSize: 10.5, color: "var(--muted-foreground)",
          fontFamily: "var(--bv-font-mono, monospace)",
        }}>{kbd}</span>
      )}
    </button>
  );
}

export function MenuDivider() {
  return <div style={{ height: 1, margin: "4px 6px", background: "var(--bv-border-5)" }}></div>;
}
