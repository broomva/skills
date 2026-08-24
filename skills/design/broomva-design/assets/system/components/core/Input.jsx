import React from "react";

/* Text input: rounded-md, gray edge, ai-blue focus ring (via :focus-visible). */
export function Input({ style, ...rest }) {
  return (
    <input
      style={{
        height: "var(--bv-h-btn)", padding: "0 12px",
        borderRadius: "var(--bv-radius-md)",
        border: "1px solid var(--input)",
        background: "var(--card)", color: "var(--foreground)",
        font: "inherit", fontSize: 14, outline: "none",
        ...style,
      }}
      {...rest}
    />
  );
}
