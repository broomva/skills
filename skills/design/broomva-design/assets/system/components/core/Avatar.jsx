import React from "react";

/* Circular avatar: initials or glyph over a tinted accent. */
export function Avatar({ name = "", color = "var(--bv-blue)", size = 22, src, style, ...rest }) {
  const initials = name.trim().split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
  return (
    <span
      title={name}
      style={{
        width: size, height: size, borderRadius: size / 2,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        background: src ? "transparent" : color,
        color: "var(--bv-white)",
        fontSize: Math.max(9, size * 0.42), fontWeight: 600,
        flexShrink: 0, overflow: "hidden", userSelect: "none",
        ...style,
      }}
      {...rest}
    >
      {src ? <img src={src} alt={name} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : initials}
    </span>
  );
}
