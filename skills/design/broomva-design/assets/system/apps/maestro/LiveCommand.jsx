// Live ⌘K command palette (V3). Opens over the real app, anchored under the
// top-bar command field, type-to-filter, full keyboard nav, and the jump-to
// rows actually navigate (History / Knowledge / Settings / Account / Feedback).
// On-standard glass via command.css. Uses the global McIcon (from WorkData).

const Ck = {
  search: (p) => <McIcon {...p}><circle cx="11" cy="11" r="7"></circle><path d="m21 21-4.3-4.3"></path></McIcon>,
  clock: (p) => <McIcon {...p}><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></McIcon>,
  doc: (p) => <McIcon {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"></path><path d="M14 3v5h5M9 13h6M9 17h4"></path></McIcon>,
  code: (p) => <McIcon {...p}><path d="m9 9-3 3 3 3M15 9l3 3-3 3M13 7l-2 10"></path></McIcon>,
  run: (p) => <McIcon {...p}><circle cx="12" cy="12" r="9"></circle><path d="m10 9 5 3-5 3Z"></path></McIcon>,
  folder: (p) => <McIcon {...p}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"></path></McIcon>,
  spark: (p) => <McIcon {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"></path><circle cx="12" cy="12" r="2.4"></circle></McIcon>,
  wake: (p) => <McIcon {...p}><path d="M13 2 4.5 13H11l-1 9 8.5-11H12Z"></path></McIcon>,
  gate: (p) => <McIcon {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"></path><path d="m9 12 2 2 4-4"></path></McIcon>,
  person: (p) => <McIcon {...p}><circle cx="12" cy="8" r="4"></circle><path d="M5 21a7 7 0 0 1 14 0"></path></McIcon>,
  history: (p) => <McIcon {...p}><path d="M3 12a9 9 0 1 0 3-6.7L3 8"></path><path d="M3 3v5h5M12 7v5l4 2"></path></McIcon>,
  book: (p) => <McIcon {...p}><path d="M4 19V5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2Z"></path><path d="M19 17H6a2 2 0 0 0-2 2"></path></McIcon>,
  settings: (p) => <McIcon {...p}><circle cx="12" cy="12" r="3"></circle><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1l2.1-2.1M17 7l2.1-2.1"></path></McIcon>,
  msg: (p) => <McIcon {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"></path></McIcon>,
};

// ── Data (illustrative, on-product) ───────────────────────────────────────
const CMDK_RECENT_SEARCHES = ["relay protocol handoff", "NDJSON phase machine", "linear missing scope"];
const CMDK_ARTIFACTS = [
  { id: "a1", title: "relay-protocol.md", meta: "hawthorne-core · spec · 12m ago", icon: "doc" },
  { id: "a2", title: "run/7c2f1a", meta: "judged clean · 14 tests · at your gate", icon: "run", state: "done" },
  { id: "a3", title: "projection.ts", meta: "genesis / projection · live session", icon: "code", state: "live" },
  { id: "a4", title: "api-decisions.md", meta: "hawthorne-core · doc", icon: "doc" },
];
const CMDK_COMMANDS = [
  { id: "c1", title: "Start a session…", meta: "dispatch work on the current folder", icon: "spark", kbd: "S", accent: true },
  { id: "c2", title: "Wake maestro now", meta: "run the next tick early", icon: "wake", kbd: "W" },
  { id: "c3", title: "Approve at the gate", meta: "1 run waiting on you", icon: "gate" },
  { id: "c4", title: "New spec / brief", meta: "write work for the loop to pick up", icon: "doc", kbd: "N" },
];
const CMDK_JUMP = [
  { id: "j1", title: "History", meta: "312 sessions", icon: "history", nav: "history" },
  { id: "j2", title: "Knowledge", meta: "the loop's memory", icon: "book", nav: "knowledge" },
  { id: "j3", title: "Settings", meta: "the engine room", icon: "settings", nav: "settings" },
  { id: "j4", title: "Account · Ana Diaz", meta: "your autonomy score", icon: "person", nav: "user" },
  { id: "j5", title: "Feedback", meta: "hand it to the loop", icon: "msg", nav: "feedback" },
];

// Contextual primaries · what ⌘K searches FIRST depends on where you are.
const CMDK_HISTORY = [
  { id: "h1", title: "Persist run transcripts on the Run record", meta: "hawthorne-core · 12m ago · judged clean", icon: "run", state: "done" },
  { id: "h2", title: "Reduce the NDJSON stream to a phase machine", meta: "genesis / projection · running now", icon: "run", state: "live" },
  { id: "h3", title: "Import Linear cycles into the object model", meta: "hawthorne-db · stuck · missing scope", icon: "run" },
  { id: "h4", title: "Reconcile May invoices", meta: "bookkeeping · 2h ago", icon: "run", state: "done" },
  { id: "h5", title: "Draft the relay protocol handoff", meta: "you · yesterday", icon: "run", state: "done" },
];
const CMDK_GRAPH = [
  { id: "g1", title: "relay protocol", meta: "concept · 6 links · genesis", icon: "spark" },
  { id: "g2", title: "NDJSON phase machine", meta: "pattern · 4 links", icon: "code" },
  { id: "g3", title: "Run record", meta: "primitive · 9 links", icon: "doc" },
  { id: "g4", title: "the conversation bridge", meta: "tool · writes to Obsidian", icon: "folder" },
  { id: "g5", title: "hawthorne-core", meta: "folder node · 12 inside", icon: "folder" },
];

// context id → primary dataset + the language it searches in.
const CMDK_PRIMARY = {
  history: { noun: "history", recentLabel: "Recent in history", hitLabel: "Sessions", scopeMeta: "all 312 sessions", data: CMDK_HISTORY },
  knowledge: { noun: "the graph", recentLabel: "In the knowledge graph", hitLabel: "Nodes", scopeMeta: "every node", data: CMDK_GRAPH },
};
const CMDK_PLACEHOLDER = {
  history: "Search history…",
  knowledge: "Search the knowledge graph…",
  app: "Ask, find, or start work…",
};

// Highlight the matched substring
function ckMark(text, q) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return <>{text.slice(0, i)}<em>{text.slice(i, i + q.length)}</em>{text.slice(i + q.length)}</>;
}
function ckHit(item, q) { return (item.title + " " + (item.meta || "")).toLowerCase().includes(q.toLowerCase()); }

function CkDot({ state }) {
  if (state === "live") return <span className="mcc-dot-tide" style={{ width: 11, height: 11 }}></span>;
  if (state === "done") return <span className="mc-chip-dot" style={{ width: 8, height: 8, background: "var(--bv-success)" }}></span>;
  return null;
}

function MccCommandPalette({ open, onClose, onNav, context = "app" }) {
  const [q, setQ] = React.useState("");
  const [active, setActive] = React.useState(0);
  const [rect, setRect] = React.useState(null);
  const inputRef = React.useRef(null);

  // Position under the real command field; fall back to top-center if the
  // current page has no command field mounted (e.g. config pages).
  const place = React.useCallback(() => {
    const anchor = document.querySelector("[data-cmdk-anchor]");
    if (anchor) {
      const r = anchor.getBoundingClientRect();
      const width = Math.max(r.width, 440);
      let left = r.left + (r.width - width) / 2;
      left = Math.max(10, Math.min(left, window.innerWidth - width - 10));
      setRect({ left, top: r.bottom + 6, width });
    } else {
      const width = 480;
      setRect({ left: (window.innerWidth - width) / 2, top: 66, width });
    }
  }, []);

  React.useEffect(() => {
    if (!open) return;
    setQ(""); setActive(0); place();
    const t = setTimeout(() => inputRef.current && inputRef.current.focus(), 50);
    const onResize = () => place();
    window.addEventListener("resize", onResize, true);
    window.addEventListener("scroll", onResize, true);
    return () => { clearTimeout(t); window.removeEventListener("resize", onResize, true); window.removeEventListener("scroll", onResize, true); };
  }, [open, place]);

  // Build the grouped, filtered model · contextual: the page you're on
  // decides what ⌘K searches first.
  const groups = React.useMemo(() => {
    const query = q.trim();
    const prim = CMDK_PRIMARY[context];
    const g = [];
    if (query) {
      const leadTitle = prim
        ? <span>Search “<em>{query}</em>” in {prim.noun}</span>
        : <span>Search “<em>{query}</em>” across all folders</span>;
      g.push({ label: prim ? "Find in " + prim.noun : "Find in workspace", items: [
        { id: "find", title: leadTitle, meta: prim ? prim.scopeMeta : "everywhere", icon: "search", accent: true, kind: "find" },
      ] });
      if (prim) {
        const hits = prim.data.filter((it) => ckHit(it, query));
        if (hits.length) g.push({ label: prim.hitLabel, items: hits.map((it) => ({ ...it, kind: "ctx", titleNode: ckMark(it.title, query) })) });
      }
      const arts = CMDK_ARTIFACTS.filter((it) => ckHit(it, query));
      if (arts.length) g.push({ label: "Artifacts", items: arts.map((it) => ({ ...it, kind: "artifact", titleNode: ckMark(it.title, query) })) });
      if (context === "app") {
        const cmds = CMDK_COMMANDS.filter((it) => ckHit(it, query));
        if (cmds.length) g.push({ label: "Commands", items: cmds.map((it) => ({ ...it, kind: "command", titleNode: ckMark(it.title, query) })) });
      }
      const jumps = CMDK_JUMP.filter((it) => ckHit(it, query));
      if (jumps.length) g.push({ label: "Jump to", items: jumps.map((it) => ({ ...it, kind: "nav", titleNode: ckMark(it.title, query) })) });
    } else if (prim) {
      g.push({ label: prim.recentLabel, items: prim.data.map((it) => ({ ...it, kind: "ctx" })) });
      g.push({ label: "Recent searches", items: CMDK_RECENT_SEARCHES.map((s, i) => ({ id: "rs" + i, title: s, icon: "clock", kind: "search" })) });
      g.push({ label: "Jump to", items: CMDK_JUMP.map((it) => ({ ...it, kind: "nav" })) });
    } else {
      g.push({ label: "Recent searches", items: CMDK_RECENT_SEARCHES.map((s, i) => ({ id: "rs" + i, title: s, icon: "clock", kind: "search" })) });
      g.push({ label: "Recent artifacts", items: CMDK_ARTIFACTS.map((it) => ({ ...it, kind: "artifact" })) });
      g.push({ label: "Commands", items: CMDK_COMMANDS.map((it) => ({ ...it, kind: "command" })) });
      g.push({ label: "Jump to", items: CMDK_JUMP.map((it) => ({ ...it, kind: "nav" })) });
    }
    return g;
  }, [q, context]);

  const flat = React.useMemo(() => groups.flatMap((g) => g.items), [groups]);
  React.useEffect(() => { setActive((a) => Math.min(a, Math.max(0, flat.length - 1))); }, [flat.length]);

  if (!open) return null;

  const choose = (it) => {
    if (!it) return;
    if (it.kind === "search") { setQ(it.title); setActive(0); inputRef.current && inputRef.current.focus(); return; }
    if (it.kind === "nav") { onClose && onClose(); onNav && onNav(it.nav); return; }
    // find / artifact / command · illustrative: just close.
    onClose && onClose();
  };

  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, flat.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); choose(flat[active]); }
    else if (e.key === "Escape") { e.preventDefault(); onClose && onClose(); }
  };

  let idx = -1;
  const combo = (
    <>
      <div className="cmdk-scrim" onMouseDown={onClose}></div>
      <div className="cmdk-combo" style={rect ? { left: rect.left, top: rect.top, width: rect.width } : { left: -9999, top: 0 }}
        role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="cmdk-input-row">
          <Ck.search size={17} />
          <input ref={inputRef} className="cmdk-input" placeholder={CMDK_PLACEHOLDER[context] || CMDK_PLACEHOLDER.app}
            value={q} onChange={(e) => { setQ(e.target.value); setActive(0); }} onKeyDown={onKey} />
          <span className="cmdk-esc">esc</span>
        </div>
        <div className="cmdk-results">
          {flat.length === 0 && <div className="cmdk-empty">No matches. Press ↵ to search everywhere.</div>}
          {groups.map((grp) => (
            <React.Fragment key={grp.label}>
              <div className="cmdk-group-label">{grp.label}</div>
              {grp.items.map((it) => {
                idx += 1; const me = idx;
                const Icon = Ck[it.icon] || Ck.search;
                return (
                  <button key={it.id} type="button" className={"cmdk-item" + (active === me ? " is-active" : "")}
                    onMouseEnter={() => setActive(me)} onClick={() => choose(it)}>
                    <span className={"cmdk-ic" + (it.accent ? " cmdk-ic--accent" : "")}>
                      {it.state ? <CkDot state={it.state} /> : <Icon />}
                    </span>
                    <span className="cmdk-item-body">
                      <span className="cmdk-item-title">{it.titleNode || it.title}</span>
                      {it.meta && <span className="cmdk-item-meta">{it.meta}</span>}
                    </span>
                    <span className="cmdk-item-right">
                      {it.kbd && <span className="cmdk-kbd">{it.kbd}</span>}
                      <span className="cmdk-enter">↵</span>
                    </span>
                  </button>
                );
              })}
            </React.Fragment>
          ))}
        </div>
        <div className="cmdk-foot">
          <span className="cmdk-foot-hint"><span className="cmdk-foot-kbd">↑↓</span> navigate</span>
          <span className="cmdk-foot-hint"><span className="cmdk-foot-kbd">↵</span> open</span>
          <span className="cmdk-foot-hint"><span className="cmdk-foot-kbd">esc</span> close</span>
          <span className="cmdk-foot-spacer"></span>
          <span className="cmdk-foot-brand"><span className="mcc-dot-tide" style={{ width: 9, height: 9 }}></span> maestro</span>
        </div>
      </div>
    </>
  );

  return ReactDOM.createPortal(combo, document.body);
}

Object.assign(window, { MccCommandPalette });
