import React from "react";

/* 18px square, chip radius. Checked = ink fill with a white check.
   Hover frosts blue. Label is sentence case, 14px. */
export function Checkbox({ checked, defaultChecked = false, onChange, disabled = false, children, style, ...rest }) {
  const [inner, setInner] = React.useState(defaultChecked);
  const [hover, setHover] = React.useState(false);
  const isOn = checked !== undefined ? checked : inner;
  const toggle = () => {
    if (disabled) return;
    if (checked === undefined) setInner(!isOn);
    onChange && onChange(!isOn);
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
        type="button" role="checkbox" aria-checked={isOn} disabled={disabled}
        onClick={toggle}
        style={{
          width: 18, height: 18, flexShrink: 0, padding: 0,
          borderRadius: "var(--bv-radius-chip)",
          border: isOn ? "1px solid transparent" : "1px solid var(--bv-border-25)",
          background: isOn
            ? (disabled ? "var(--bv-gray-300)" : "var(--primary)")
            : (hover && !disabled ? "var(--bv-frost-8)" : "var(--card)"),
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          cursor: "inherit",
          transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
        }}
        {...rest}
      >
        {isOn && (
          <svg viewBox="0 0 24 24" fill="none" stroke="var(--primary-foreground)" strokeWidth="3"
            strokeLinecap="round" strokeLinejoin="round" style={{ width: 12, height: 12 }}>
            <path d="M20 6 9 17l-5-5"></path>
          </svg>
        )}
      </button>
      {children}
    </label>
  );
}
