import React from "react";

/* Hover tooltip — a small glass chip (popovers earn glass). 12px, no arrow,
   no delay theatrics; fades in 150ms. */
export function Tooltip({ label, side = "top", children, style }) {
  const [show, setShow] = React.useState(false);
  const pos = {
    top:    { bottom: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)" },
    bottom: { top: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)" },
    left:   { right: "calc(100% + 6px)", top: "50%", transform: "translateY(-50%)" },
    right:  { left: "calc(100% + 6px)", top: "50%", transform: "translateY(-50%)" },
  };
  return (
    <span
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
      style={{ position: "relative", display: "inline-flex", ...style }}
    >
      {children}
      <span
        role="tooltip"
        className="bv-glass"
        style={{
          position: "absolute", zIndex: 70, ...pos[side],
          padding: "4px 9px", borderRadius: "var(--bv-radius-lg)",
          fontSize: 12, fontWeight: 500, color: "var(--foreground)",
          whiteSpace: "nowrap", pointerEvents: "none",
          opacity: show ? 1 : 0,
          transition: "opacity var(--bv-dur-fast) var(--bv-ease-standard)",
        }}
      >
        {label}
      </span>
    </span>
  );
}
