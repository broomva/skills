import React from "react";

/* The lifecycle rail — the inspector's horizontal stage tracker
   (proposed → queued → running → review → done). Passed and current
   stages carry ai-blue; a warn stage carries warning. Never a progress bar. */
export function LifecycleRail({ stages = [], style }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", padding: "4px 0 0", ...style }}>
      {stages.map((st, i) => {
        const state = st.state || "upcoming";
        const passed = state === "passed";
        const current = state === "current";
        const warn = state === "warn";
        const lit = passed || current || warn;
        return (
          <div key={i} style={{
            flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
            gap: 6, position: "relative", minWidth: 0,
          }}>
            {i > 0 && (
              <span style={{
                position: "absolute", top: 4.5, left: "-50%", right: "50%", height: 1.5,
                background: passed || current ? "oklch(0.60 0.12 260 / 0.45)" : "var(--bv-border-15)",
              }}></span>
            )}
            <span style={{
              width: 10, height: 10, borderRadius: 99, position: "relative", zIndex: 1,
              background: warn ? "var(--bv-warning)" : lit ? "var(--bv-blue)" : "var(--background)",
              border: "1.5px solid " + (warn ? "var(--bv-warning)" : lit ? "var(--bv-blue)" : "var(--bv-border-25)"),
              boxShadow: current ? "0 0 0 4px var(--bv-frost-12)"
                : warn ? "0 0 0 4px oklch(0.76 0.15 85 / 0.18)" : "none",
            }}></span>
            <span style={{
              fontSize: 11, textAlign: "center",
              color: current ? "var(--foreground)" : "var(--muted-foreground)",
              fontWeight: current ? 500 : 400,
            }}>{st.name}</span>
            {st.note && (
              <span style={{ fontSize: 11.5, color: "var(--muted-foreground)", textAlign: "center", paddingTop: 2 }}>
                {st.note}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
