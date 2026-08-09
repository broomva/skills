import React from "react";

/* Multiline input: same recipe as Input, vertical resize only. */
export function Textarea({ style, ...rest }) {
  return (
    <textarea
      rows={3}
      style={{
        padding: "8px 12px", minHeight: 72,
        borderRadius: "var(--bv-radius-md)",
        border: "1px solid var(--input)",
        background: "var(--card)", color: "var(--foreground)",
        font: "inherit", fontSize: 14, lineHeight: 1.5, outline: "none",
        resize: "vertical", width: "100%", boxSizing: "border-box",
        ...style,
      }}
      {...rest}
    ></textarea>
  );
}
