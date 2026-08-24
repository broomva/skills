import React from "react";

/* Segmented control — the Maestro settings pattern (.mcc-seg): a bordered
   pill holding frost-pill options. Active wears frost-12. For 2–4 short,
   mutually exclusive choices; use Tabs for view switching, Select for long lists. */
export function Segmented({ options = [], value, onChange, style }) {
  return (
    <div style={{
      display: "inline-flex", gap: 2, padding: 3, flexShrink: 0,
      border: "1px solid var(--bv-border-15)",
      borderRadius: "var(--bv-radius-full)",
      ...style,
    }}>
      {options.map((o) => {
        const opt = typeof o === "string" ? { value: o, label: o } : o;
        return (
          <SegBtn key={opt.value} active={opt.value === value} onClick={() => onChange && onChange(opt.value)}>
            {opt.icon}{opt.label}
          </SegBtn>
        );
      })}
    </div>
  );
}

function SegBtn({ active, onClick, children }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button" aria-pressed={active} onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        height: 26, padding: "0 12px",
        border: "none", borderRadius: 99,
        background: active ? "var(--bv-frost-12)" : hover ? "var(--bv-frost-8)" : "transparent",
        font: "inherit", fontSize: 12.5,
        color: active ? "var(--foreground)" : "var(--muted-foreground)",
        cursor: "pointer",
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
      }}
    >
      {children}
    </button>
  );
}
