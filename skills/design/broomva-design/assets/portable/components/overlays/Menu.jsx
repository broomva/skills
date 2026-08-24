import React from "react";

export function Menu({
  children, minWidth = 180, ariaLabel = "Actions", autoFocus = true,
  "aria-label": nativeAriaLabel,
  onEscape, onKeyDown: onExternalKeyDown, style, ...rest
}) {
  const menuRef = React.useRef(null);

  const enabledItems = () => (
    [...(menuRef.current?.querySelectorAll('[role="menuitem"]:not([disabled])') || [])]
  );

  React.useEffect(() => {
    if (autoFocus) enabledItems()[0]?.focus();
  }, [autoFocus]);

  const onKeyDown = (event) => {
    onExternalKeyDown?.(event);
    if (event.defaultPrevented) return;
    const items = enabledItems();
    if (!items.length) return;
    const current = items.indexOf(document.activeElement);
    let next;
    if (event.key === "ArrowDown") next = (current + 1) % items.length;
    else if (event.key === "ArrowUp") next = (current - 1 + items.length) % items.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else if (event.key === "Escape" && onEscape) {
      event.preventDefault();
      onEscape();
      return;
    } else return;
    event.preventDefault();
    items[next].focus();
  };

  return (
    <div
      {...rest}
      ref={menuRef}
      className="bv-glass"
      role="menu"
      aria-label={nativeAriaLabel || ariaLabel}
      onKeyDown={onKeyDown}
      style={{
        display: "inline-flex", flexDirection: "column",
        padding: 5, minWidth, ...style,
      }}
    >
      {children}
    </div>
  );
}

export function MenuItem({
  icon, kbd, danger = false, disabled = false, children, style,
  onMouseEnter, onMouseLeave, ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      {...rest}
      type="button"
      role="menuitem"
      tabIndex={-1}
      disabled={disabled}
      onMouseEnter={(event) => {
        onMouseEnter?.(event);
        if (!event.defaultPrevented) setHover(true);
      }}
      onMouseLeave={(event) => {
        onMouseLeave?.(event);
        if (!event.defaultPrevented) setHover(false);
      }}
      style={{
        display: "flex", alignItems: "center", gap: 9, width: "100%",
        textAlign: "left", padding: "7px 9px", borderRadius: "var(--bv-radius-lg)",
        border: "none", background: hover && !disabled ? "var(--bv-frost-8)" : "transparent",
        font: "inherit", fontSize: 13,
        color: disabled ? "var(--bv-gray-400)" : danger ? "var(--bv-danger)" : "var(--foreground)",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
        ...style,
      }}
    >
      {icon && (
        <span aria-hidden="true" style={{
          display: "inline-flex", flexShrink: 0,
          color: danger ? "var(--bv-danger)" : "var(--bv-gray-600)",
        }}>
          {icon}
        </span>
      )}
      <span style={{ flex: 1, minWidth: 0 }}>{children}</span>
      {kbd && (
        <span aria-hidden="true" style={{
          flexShrink: 0, fontSize: 10.5, color: "var(--muted-foreground)",
          fontFamily: "var(--bv-font-mono, monospace)",
        }}>
          {kbd}
        </span>
      )}
    </button>
  );
}

export function MenuDivider() {
  return (
    <div
      role="separator"
      style={{ height: 1, margin: "4px 6px", background: "var(--bv-border-5)" }}
    />
  );
}
