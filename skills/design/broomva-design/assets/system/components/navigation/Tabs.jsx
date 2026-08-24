import React from "react";

/* Frost-pill tab strip — the mission-control tab pattern. Active tab wears
   frost-12; hover frost-8. No underlines, no borders. */
export function Tabs({ tabs = [], active, defaultActive = 0, onChange, style }) {
  const [inner, setInner] = React.useState(defaultActive);
  const current = active !== undefined ? active : inner;
  const pick = (i) => {
    if (active === undefined) setInner(i);
    onChange && onChange(i);
  };
  return (
    <div role="tablist" style={{ display: "flex", alignItems: "center", gap: 3, ...style }}>
      {tabs.map((t, i) => {
        const tab = typeof t === "string" ? { label: t } : t;
        return (
          <TabPill key={i} active={i === current} onClick={() => pick(i)}>
            {tab.icon}
            {tab.label}
            {tab.count !== undefined && (
              <span style={{ fontSize: 11, color: "var(--muted-foreground)" }}>{tab.count}</span>
            )}
          </TabPill>
        );
      })}
    </div>
  );
}

function TabPill({ active, onClick, children }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button" role="tab" aria-selected={active} onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex", alignItems: "center", gap: 7,
        height: 28, padding: "0 10px",
        border: "none", borderRadius: "var(--bv-radius-lg)",
        background: active ? "var(--bv-frost-12)" : hover ? "var(--bv-frost-8)" : "transparent",
        font: "inherit", fontSize: 12.5, fontWeight: active ? 500 : 400,
        color: active ? "var(--foreground)" : "var(--muted-foreground)",
        cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0,
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
      }}
    >
      {children}
    </button>
  );
}
