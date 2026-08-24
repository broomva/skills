import React from "react";

/* Native select styled like Input: rounded-md, gray edge, ai-blue focus
   ring via :focus-visible, lucide chevron in currentColor. */
export function Select({ options = [], placeholder, style, ...rest }) {
  return (
    <span style={{ position: "relative", display: "inline-flex", ...style }}>
      <select
        defaultValue={rest.value === undefined && placeholder ? "" : undefined}
        style={{
          height: "var(--bv-h-btn)", padding: "0 32px 0 12px",
          borderRadius: "var(--bv-radius-md)",
          border: "1px solid var(--input)",
          background: "var(--card)", color: "var(--foreground)",
          font: "inherit", fontSize: 14, outline: "none",
          appearance: "none", WebkitAppearance: "none",
          cursor: "pointer", width: "100%",
        }}
        {...rest}
      >
        {placeholder && <option value="" disabled>{placeholder}</option>}
        {options.map((o) => {
          const opt = typeof o === "string" ? { value: o, label: o } : o;
          return <option key={opt.value} value={opt.value}>{opt.label}</option>;
        })}
      </select>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round"
        style={{ width: 16, height: 16, position: "absolute", right: 10, top: "50%",
          transform: "translateY(-50%)", pointerEvents: "none", color: "var(--bv-gray-500)" }}>
        <path d="m6 9 6 6 6-6"></path>
      </svg>
    </span>
  );
}
