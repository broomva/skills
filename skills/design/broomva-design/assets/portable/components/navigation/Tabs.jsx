import React from "react";

/* Compact tab strip with roving focus and standard arrow-key behavior. */
export function Tabs({
  tabs = [], active, defaultActive = 0, onChange,
  ariaLabel = "Sections", style,
}) {
  const [inner, setInner] = React.useState(defaultActive);
  const current = active !== undefined ? active : inner;
  const buttons = React.useRef([]);
  const baseId = React.useId();

  const pick = (index, focus = false) => {
    if (active === undefined) setInner(index);
    onChange?.(index);
    if (focus) buttons.current[index]?.focus();
  };

  const onKeyDown = (event) => {
    let next = current;
    if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    pick(next, true);
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      style={{ display: "flex", alignItems: "center", gap: 3, ...style }}
    >
      {tabs.map((item, index) => {
        const tab = typeof item === "string" ? { label: item } : item;
        const selected = index === current;
        const tabId = tab.id || `${baseId}-tab-${index}`;
        return (
          <button
            key={tab.id || (typeof tab.label === "string" ? tab.label : index)}
            ref={(node) => { buttons.current[index] = node; }}
            id={tabId}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={tab.panelId}
            tabIndex={selected ? 0 : -1}
            onClick={() => pick(index)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 7,
              height: 28, padding: "0 10px", border: "none",
              borderRadius: "var(--bv-radius-lg)",
              background: selected ? "var(--bv-frost-12)" : "transparent",
              font: "inherit", fontSize: 12.5, fontWeight: selected ? 500 : 400,
              color: selected ? "var(--foreground)" : "var(--muted-foreground)",
              cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0,
              transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
            }}
          >
            {tab.icon}
            {tab.label}
            {tab.count !== undefined && (
              <span style={{ fontSize: 11, color: "var(--muted-foreground)" }}>
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
