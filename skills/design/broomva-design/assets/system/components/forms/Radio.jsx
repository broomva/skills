import React from "react";

/* 18px circle. Checked = ink ring with an ink core. Hover frosts blue. */
export function Radio({ checked, defaultChecked = false, onChange, disabled = false, children, style, ...rest }) {
  const [inner, setInner] = React.useState(defaultChecked);
  const [hover, setHover] = React.useState(false);
  const isOn = checked !== undefined ? checked : inner;
  const pick = () => {
    if (disabled || isOn) return;
    if (checked === undefined) setInner(true);
    onChange && onChange(true);
  };
  return (
    <label
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex", alignItems: "center", gap: 8,
        fontSize: 14, color: disabled ? "var(--bv-gray-400)" : "var(--foreground)",
        cursor: disabled ? "not-allowed" : "pointer", userSelect: "none", ...style,
      }}
    >
      <button
        type="button" role="radio" aria-checked={isOn} disabled={disabled}
        onClick={pick}
        style={{
          width: 18, height: 18, flexShrink: 0, padding: 0,
          borderRadius: "var(--bv-radius-full)",
          border: isOn
            ? "5.5px solid " + (disabled ? "var(--bv-gray-300)" : "var(--primary)")
            : "1px solid var(--bv-border-25)",
          background: isOn
            ? "var(--primary-foreground)"
            : (hover && !disabled ? "var(--bv-frost-8)" : "var(--card)"),
          cursor: "inherit",
          transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
        }}
        {...rest}
      ></button>
      {children}
    </label>
  );
}
