import React from "react";

/* The autonomy scoreboard — keep score in unsupervised hours, never
   percentages of "done". Blue segments are unsupervised stretches, accent
   notches are human looks, the live segment is the run happening now. */
export function AutonomyScoreboard({ label = "unsupervised today", hours, sub, segments = [], notches = [], children, style, ...rest }) {
  return (
    <div
      style={{
        margin: "0 2px", padding: "9px 10px",
        border: "1px solid var(--bv-border-5)", borderRadius: "var(--bv-radius-lg)",
        background: "var(--card)", display: "flex", flexDirection: "column", gap: 6,
        ...style,
      }}
      {...rest}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", fontSize: 11, color: "var(--muted-foreground)" }}>
        <span>{label}</span>
        <b style={{ fontSize: 12.5, fontWeight: 500, color: "var(--foreground)", fontVariantNumeric: "tabular-nums" }}>{hours}</b>
      </div>
      <div style={{ position: "relative", height: 4, borderRadius: 99, background: "var(--bv-border-5)", overflow: "visible" }}>
        {segments.map((s, i) => (
          <span key={"s" + i} style={{
            position: "absolute", top: 0, bottom: 0, borderRadius: 99,
            left: s.start + "%", width: s.width + "%",
            background: s.live
              ? "linear-gradient(90deg, var(--bv-blue), oklch(0.82 0.09 230))"
              : "var(--bv-blue)",
            opacity: s.live ? 1 : 0.55,
          }}></span>
        ))}
        {notches.map((n, i) => (
          <i key={"n" + i} style={{
            position: "absolute", top: -2.5, width: 1.5, height: 9, borderRadius: 1,
            left: n + "%", background: "var(--bv-blue-accent)",
          }}></i>
        ))}
      </div>
      {sub && <div style={{ fontSize: 10.5, color: "var(--muted-foreground)" }}>{sub}</div>}
      {children}
    </div>
  );
}
