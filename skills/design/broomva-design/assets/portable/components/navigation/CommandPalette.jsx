import React from "react";

export function CommandPalette({
  query = "", label = "Commands", placeholder = "Search commands",
  groups = [], activeId, onActiveChange, onQuery, onPick, onEscape,
  footer = true, style,
}) {
  const items = React.useMemo(() => groups.flatMap((group) => group.items), [groups]);
  const [innerActive, setInnerActive] = React.useState(items[0]?.id);
  const selectedId = activeId !== undefined ? activeId : innerActive;
  const baseId = React.useId();
  const inputId = `${baseId}-input`;
  const listId = `${baseId}-listbox`;
  const activeIndex = items.findIndex((item) => item.id === selectedId);

  React.useEffect(() => {
    if (activeId === undefined && !items.some((item) => item.id === innerActive)) {
      setInnerActive(items[0]?.id);
    }
  }, [activeId, innerActive, items]);

  const select = (index) => {
    const item = items[index];
    if (!item) return;
    if (activeId === undefined) setInnerActive(item.id);
    onActiveChange?.(item.id);
  };

  const onInputKeyDown = (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const start = activeIndex < 0 ? (direction > 0 ? -1 : 0) : activeIndex;
      select((start + direction + items.length) % items.length);
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      onPick?.(items[activeIndex]);
    } else if (event.key === "Escape" && onEscape) {
      event.preventDefault();
      onEscape();
    }
  };

  return (
    <div
      className="bv-glass-heavy"
      style={{
        width: "min(560px, 100%)", display: "flex", flexDirection: "column",
        overflow: "hidden", ...style,
      }}
    >
      <div style={{
        flexShrink: 0, display: "flex", flexDirection: "column", gap: 5,
        padding: "9px 13px 8px", borderBottom: "1px solid var(--bv-border-5)",
      }}>
        <label htmlFor={inputId} style={{
          fontSize: 11, fontWeight: 500, color: "var(--muted-foreground)",
        }}>
          {label}
        </label>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <svg
            viewBox="0 0 24 24" fill="none" stroke="var(--bv-blue)" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round"
            style={{ width: 15, height: 15, flexShrink: 0 }} aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.3-4.3"></path>
          </svg>
          <input
            id={inputId}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={
              activeIndex >= 0 ? `${baseId}-option-${activeIndex}` : undefined
            }
            value={query}
            placeholder={placeholder}
            onChange={(event) => onQuery?.(event.target.value)}
            onKeyDown={onInputKeyDown}
            style={{
              flex: 1, minWidth: 0, border: "none", background: "transparent",
              outline: "none", font: "inherit", fontSize: 14,
              color: "var(--foreground)",
            }}
          />
          {onEscape && (
            <span style={{
              flexShrink: 0, fontSize: 10.5, fontWeight: 500,
              color: "var(--muted-foreground)", padding: "2px 7px",
              border: "1px solid var(--bv-border-15)", borderRadius: 5,
            }}>
              esc
            </span>
          )}
        </div>
      </div>
      <div
        id={listId}
        role="listbox"
        aria-label={`${label} results`}
        style={{
          overflowY: "auto", padding: 6, display: "flex",
          flexDirection: "column", maxHeight: "52vh",
        }}
      >
        {groups.length === 0 && (
          <div role="status" style={{
            padding: "26px 12px", textAlign: "center", fontSize: 13,
            color: "var(--muted-foreground)",
          }}>
            Nothing matches
          </div>
        )}
        {groups.map((group, groupIndex) => (
          <React.Fragment key={group.label || groupIndex}>
            {group.label && (
              <div aria-hidden="true" style={{
                fontSize: 11, fontWeight: 500, color: "var(--muted-foreground)",
                padding: "9px 10px 5px",
              }}>
                {group.label}
              </div>
            )}
            {group.items.map((item) => {
              const index = items.findIndex((candidate) => candidate.id === item.id);
              return (
                <PaletteItem
                  key={item.id}
                  id={`${baseId}-option-${index}`}
                  item={item}
                  active={item.id === selectedId}
                  onPick={onPick}
                  onActive={() => select(index)}
                />
              );
            })}
          </React.Fragment>
        ))}
      </div>
      {footer && (
        <div style={{
          flexShrink: 0, display: "flex", alignItems: "center", gap: 14,
          padding: "9px 14px", borderTop: "1px solid var(--bv-border-5)",
          fontSize: 11, color: "var(--muted-foreground)",
        }}>
          <span><Kbd>↑↓</Kbd> navigate</span>
          <span><Kbd>↵</Kbd> open</span>
        </div>
      )}
    </div>
  );
}

function Kbd({ children }) {
  return (
    <span style={{
      fontFamily: "var(--bv-font-mono, monospace)", fontSize: 10,
      padding: "1px 5px", border: "1px solid var(--bv-border-15)", borderRadius: 4,
    }}>
      {children}
    </span>
  );
}

function PaletteItem({ id, item, active, onPick, onActive }) {
  return (
    <button
      id={id}
      type="button"
      role="option"
      aria-selected={active}
      tabIndex={-1}
      onMouseEnter={onActive}
      onClick={() => onPick?.(item)}
      style={{
        display: "flex", alignItems: "center", gap: 11, width: "100%",
        textAlign: "left", padding: "8px 10px", borderRadius: 10, border: "none",
        background: active ? "var(--bv-frost-8)" : "transparent",
        font: "inherit", cursor: "pointer", position: "relative",
        transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
      }}
    >
      {active && <span aria-hidden="true" style={{
        position: "absolute", left: 0, top: 9, bottom: 9, width: 2.5,
        borderRadius: 2, background: "var(--bv-blue)",
      }}></span>}
      {item.icon && <span aria-hidden="true" style={{
        width: 28, height: 28, flexShrink: 0, borderRadius: 8,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        background: active ? "var(--bv-frost-12)" : "var(--bv-canvas-soft)",
        color: active ? "var(--bv-blue)" : "var(--bv-gray-600)",
      }}>{item.icon}</span>}
      <span style={{
        flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1,
      }}>
        <span style={{
          fontSize: 13.5, fontWeight: 500, color: "var(--foreground)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>{item.title}</span>
        {item.meta && <span style={{
          fontSize: 11.5, color: "var(--muted-foreground)", overflow: "hidden",
          textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>{item.meta}</span>}
      </span>
      {item.kbd && <span aria-hidden="true" style={{
        flexShrink: 0, fontSize: 10.5, fontWeight: 500,
        color: "var(--muted-foreground)", padding: "2px 6px",
        border: "1px solid var(--bv-border-15)", borderRadius: 5,
        background: "var(--card)", fontFamily: "var(--bv-font-mono, monospace)",
      }}>{item.kbd}</span>}
    </button>
  );
}
