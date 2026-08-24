import React from "react";

/* The command palette combobox — earned glass (.bv-glass-heavy from
   tokens/glass.css). Input row + grouped results + kbd hints + footer.
   Render it inside a fixed scrim (blue-black, never gray) or standalone
   in a card for specimens. Static: filtering is the caller's job. */
export function CommandPalette({ query = "", placeholder = "Type a command or search…", groups = [], activeId, onQuery, onPick, footer = true, style }) {
  return (
    <div
      className="bv-glass-heavy"
      style={{
        width: "min(560px, 100%)", display: "flex", flexDirection: "column",
        overflow: "hidden", ...style,
      }}
    >
      <div style={{
        flexShrink: 0, display: "flex", alignItems: "center", gap: 10,
        height: 40, padding: "0 13px", borderBottom: "1px solid var(--bv-border-5)",
      }}>
        <svg viewBox="0 0 24 24" fill="none" stroke="var(--bv-blue)" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" style={{ width: 15, height: 15, flexShrink: 0 }}>
          <circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path>
        </svg>
        <input
          value={query} placeholder={placeholder}
          onChange={(e) => onQuery && onQuery(e.target.value)}
          style={{
            flex: 1, minWidth: 0, border: "none", background: "transparent",
            outline: "none", font: "inherit", fontSize: 14, color: "var(--foreground)",
          }}
        />
        <span style={{
          flexShrink: 0, fontSize: 10.5, fontWeight: 500, color: "var(--muted-foreground)",
          padding: "2px 7px", border: "1px solid var(--bv-border-15)", borderRadius: 5,
        }}>esc</span>
      </div>
      <div style={{ overflowY: "auto", padding: 6, display: "flex", flexDirection: "column", maxHeight: "52vh" }}>
        {groups.length === 0 && (
          <div style={{ padding: "26px 12px", textAlign: "center", fontSize: 13, color: "var(--muted-foreground)" }}>
            Nothing matches
          </div>
        )}
        {groups.map((g, gi) => (
          <React.Fragment key={gi}>
            {g.label && (
              <div style={{ fontSize: 11, fontWeight: 500, color: "var(--muted-foreground)", padding: "9px 10px 5px" }}>
                {g.label}
              </div>
            )}
            {g.items.map((it) => (
              <PaletteItem key={it.id} item={it} active={it.id === activeId} onPick={onPick} />
            ))}
          </React.Fragment>
        ))}
      </div>
      {footer && (
        <div style={{
          flexShrink: 0, display: "flex", alignItems: "center", gap: 14,
          padding: "9px 14px", borderTop: "1px solid var(--bv-border-5)",
          fontSize: 11, color: "var(--muted-foreground)",
        }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><Kbd>↑↓</Kbd> navigate</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><Kbd>↵</Kbd> open</span>
        </div>
      )}
    </div>
  );
}

function Kbd({ children }) {
  return (
    <span style={{
      fontFamily: "var(--bv-font-mono, monospace)", fontSize: 10, padding: "1px 5px",
      border: "1px solid var(--bv-border-15)", borderRadius: 4,
    }}>{children}</span>
  );
}

function PaletteItem({ item, active, onPick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button"
      onClick={() => onPick && onPick(item)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", alignItems: "center", gap: 11, width: "100%", textAlign: "left",
        padding: "8px 10px", borderRadius: 10, border: "none",
        background: active ? "var(--bv-frost-8)" : hover ? "var(--bv-frost-4)" : "transparent",
        font: "inherit", cursor: "pointer", position: "relative",
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
      }}
    >
      {active && (
        <span style={{
          position: "absolute", left: 0, top: 9, bottom: 9, width: 2.5,
          borderRadius: 2, background: "var(--bv-blue)",
        }}></span>
      )}
      {item.icon && (
        <span style={{
          width: 28, height: 28, flexShrink: 0, borderRadius: 8,
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          background: active ? "var(--bv-frost-12)" : "var(--bv-canvas-soft)",
          color: active ? "var(--bv-blue)" : "var(--bv-gray-600)",
        }}>{item.icon}</span>
      )}
      <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
        <span style={{
          fontSize: 13.5, fontWeight: 500, color: "var(--foreground)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>{item.title}</span>
        {item.meta && (
          <span style={{
            fontSize: 11.5, color: "var(--muted-foreground)",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>{item.meta}</span>
        )}
      </span>
      {item.kbd && (
        <span style={{
          flexShrink: 0, fontSize: 10.5, fontWeight: 500, color: "var(--muted-foreground)",
          padding: "2px 6px", border: "1px solid var(--bv-border-15)", borderRadius: 5,
          background: "var(--card)", fontFamily: "var(--bv-font-mono, monospace)",
        }}>{item.kbd}</span>
      )}
    </button>
  );
}
