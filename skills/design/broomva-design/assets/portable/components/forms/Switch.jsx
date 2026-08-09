import React from "react";

/* Compact immediate on/off setting. Blue means enabled; the neutral track
   handles the off state in both themes. The thumb slides without bounce. */
export function Switch({
  checked, defaultChecked = false, onChange, onClick, disabled = false, style, ...rest
}) {
  const [inner, setInner] = React.useState(defaultChecked);
  const isOn = checked !== undefined ? checked : inner;
  const toggle = (event) => {
    if (disabled) return;
    if (checked === undefined) setInner(!isOn);
    onChange && onChange(!isOn);
    onClick?.(event);
  };
  return (
    <button
      {...rest}
      type="button" role="switch" aria-checked={isOn} disabled={disabled}
      onClick={toggle}
      style={{
        position: "relative", width: 38, height: 22, flexShrink: 0,
        borderRadius: 99, border: "none", padding: 0,
        background: isOn ? "var(--bv-blue)" : "var(--bv-switch-off, var(--bv-gray-300))",
        opacity: disabled ? 0.55 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
        ...style,
      }}
    >
      <span style={{
        position: "absolute", top: 2, left: 2,
        width: 18, height: 18, borderRadius: 99,
        background: "var(--bv-white)",
        boxShadow: "0 1px 2px oklch(0.2 0.04 265 / 0.25)",
        transform: isOn ? "translateX(16px)" : "translateX(0)",
        transition: "transform var(--bv-dur-fast) var(--bv-ease-standard)",
      }}></span>
    </button>
  );
}
