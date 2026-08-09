// KnowledgeApp.jsx · the full Knowledge page + its flows, built on the scope
// graph (KG_SCOPES) and KgGraph. The search field here IS the app-wide layout
// search: it opens a command palette (entities · folders · sessions · pages,
// all KG-enriched) AND, because the Knowledge view is under the same layout, it
// live-drives the graph (dim + auto-frame) and can "ask the graph". Other
// surfaces: type-filter chips, graph⇄list toggle, a slide-over detail drawer
// with a neighbourhood mini-graph, hover previews, a minimap, and a right rail
// of recently-viewed · pinned · what's-new.

const IcPin = (p) => <McIcon {...p}><path d="M12 17v5"></path><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"></path></McIcon>;


// freshly-bookkept entities (the "what's new" feed) · {scopeId, nodeId, when}
const KG_FRESH = [
  { scopeId: "hawthorne-core", nodeId: "drun", when: "12m" },
  { scopeId: "broomva", nodeId: "nous", when: "1h" },
  { scopeId: "genesis", nodeId: "uimsg", when: "3h" },
  { scopeId: "bookkeeping", nodeId: "reconciled", when: "5h" },
  { scopeId: "broomva", nodeId: "rcs", when: "1d" },
];
const KG_NAV_PAGES = [
  { id: "needs", label: "Needs you", hint: "2 at your gate", icon: "needs" },
  { id: "mc", label: "Maestro", hint: "the plane", icon: "board" },
  { id: "history", label: "History", hint: "every session", icon: "history" },
];

function kgFlatIndex() {
  const out = [];
  Object.values(KG_SCOPES).forEach((sc) => sc.nodes.forEach((n) => out.push({ scopeId: sc.id, scope: sc, node: n })));
  return out;
}

// ── The global search + command palette ────────────────────────────────────
function BvKgSearch({ query, setQuery, scope, onPickEntity, onNavigate, onAsk }) {
  const [open, setOpen] = React.useState(false);
  const [hi, setHi] = React.useState(0);
  const inputRef = React.useRef(null);
  const wrapRef = React.useRef(null);
  const all = React.useMemo(() => kgFlatIndex(), []);
  const q = query.trim().toLowerCase();

  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); inputRef.current && inputRef.current.focus(); setOpen(true); }
      if (e.key === "Escape") { setOpen(false); inputRef.current && inputRef.current.blur(); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  React.useEffect(() => {
    const off = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", off, true);
    return () => document.removeEventListener("pointerdown", off, true);
  }, []);

  const match = (n) => (n.label + " " + (n.claim || "") + " " + n.type).toLowerCase().includes(q);
  const here = q ? scope.nodes.filter((n) => !n.scopeRef && match(n)).slice(0, 5) : [];
  const folders = q ? all.filter((x) => x.node.scopeRef && match(x.node)).slice(0, 4) : [];
  const elsewhere = q ? all.filter((x) => x.scopeId !== scope.id && !x.node.scopeRef && match(x.node)).slice(0, 5) : [];
  const sessions = q ? all.filter((x) => x.node.type === "session" && match(x.node)).slice(0, 3) : [];
  const pages = q ? KG_NAV_PAGES.filter((p) => (p.label + " " + p.hint).toLowerCase().includes(q)) : [];

  // flatten into a keyboard-navigable command list
  const cmds = [];
  if (q) cmds.push({ kind: "ask", label: 'Ask the graph: "' + query.trim() + '"' });
  here.forEach((n) => cmds.push({ kind: "entity", node: n, scopeId: scope.id, group: "In this scope" }));
  folders.forEach((x) => cmds.push({ kind: "folder", node: x.node, scopeId: x.scopeId, group: "Folders" }));
  elsewhere.forEach((x) => cmds.push({ kind: "entity", node: x.node, scopeId: x.scopeId, scope: x.scope, group: "Across the workspace" }));
  sessions.forEach((x) => cmds.push({ kind: "entity", node: x.node, scopeId: x.scopeId, scope: x.scope, group: "Sessions" }));
  pages.forEach((p) => cmds.push({ kind: "page", page: p, group: "Go to" }));

  const run = (c) => {
    if (!c) return;
    if (c.kind === "ask") { onAsk(query.trim()); setOpen(false); return; }
    if (c.kind === "folder") { onNavigate(c.node.scopeRef); setOpen(false); return; }
    if (c.kind === "page") { onNavigate("__page:" + c.page.id); setOpen(false); return; }
    if (c.kind === "entity") { onPickEntity(c.scopeId, c.node.id); setOpen(false); }
  };
  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, cmds.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); run(cmds[hi]); }
  };
  React.useEffect(() => { setHi(0); }, [query]);

  let lastGroup = null;
  return (
    <div className="kg-search" ref={wrapRef}>
      <div className={"kg-search-field" + (open ? " is-open" : "")}>
        <IcSearch size={15} />
        <input ref={inputRef} value={query} placeholder="Search Broomva · entities, folders, sessions…"
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)} onKeyDown={onKeyDown} />
        {query ? <button type="button" className="kg-search-clear" onClick={() => { setQuery(""); inputRef.current.focus(); }} aria-label="Clear"><IcX size={13} /></button>
          : <kbd className="kg-search-kbd">⌘K</kbd>}
      </div>
      {open && q && (
        <div className="kg-palette">
          {cmds.length === 0 && <div className="kg-pal-empty">No matches for “{query.trim()}”.</div>}
          {cmds.map((c, i) => {
            const showGroup = c.group && c.group !== lastGroup; lastGroup = c.group || lastGroup;
            return (
              <React.Fragment key={i}>
                {showGroup && <div className="kg-pal-group">{c.group}</div>}
                <button type="button" className={"kg-pal-row" + (i === hi ? " is-hi" : "")}
                  onPointerEnter={() => setHi(i)} onClick={() => run(c)}>
                  {c.kind === "ask"
                    ? <><span className="kg-pal-ask-ic"><IcGraph size={14} /></span><span className="kg-pal-label">{c.label}</span><span className="kg-pal-meta">enrich ↵</span></>
                    : c.kind === "page"
                      ? <><span className="kg-legend-dot" style={{ background: "var(--bv-blue)" }}></span><span className="kg-pal-label">{c.page.label}</span><span className="kg-pal-meta">{c.page.hint}</span></>
                      : <><span className="kg-legend-dot" style={{ background: kgTypeColor(c.node) }}></span><span className="kg-pal-label">{c.node.label}</span><span className="kg-pal-meta">{c.scopeId !== scope.id ? KG_SCOPES[c.scopeId].crumb : (KG_TYPE[c.node.type] || {}).label || c.node.type}</span></>}
                </button>
              </React.Fragment>
            );
          })}
          <div className="kg-pal-foot"><span>↑↓ to move · ↵ to open · esc to close</span><span>searches everything · enriched by the graph</span></div>
        </div>
      )}
    </div>
  );
}

// ── The slide-over detail drawer ────────────────────────────────────────────
function KgDetailDrawer({ scope, nodeId, pinned, onPin, onSelect, onNavigate, onClose }) {
  const node = scope.nodes.find((n) => n.id === nodeId);
  if (!node) return null;
  const isPinned = pinned.some((p) => p.scopeId === scope.id && p.nodeId === nodeId);
  return (
    <div className="kg-drawer" data-screen-label="Node detail">
      <div className="kg-drawer-head">
        <span className="mc-detail-breadcrumb">{kgPath(scope.id).map((s) => s.crumb).join(" / ")}</span>
        <div className="kg-drawer-actions">
          <button type="button" className={"kg-iconbtn" + (isPinned ? " is-on" : "")} title={isPinned ? "Unpin" : "Pin"} onClick={() => onPin(scope.id, nodeId)}><IcPin size={15} /></button>
          <button type="button" className="kg-iconbtn" title="Close" onClick={onClose}><IcX size={15} /></button>
        </div>
      </div>
      <div className="kg-drawer-body">
        <KgInspector node={node} scope={scope} onSelect={onSelect} big />
        <div className="kg-ent-sec">
          <div className="mcc-panel-label">neighbourhood</div>
          <div className="kg-mini-wrap"><KgMiniGraph scope={scope} centerId={nodeId} onPick={onSelect} w={300} h={190} /></div>
        </div>
      </div>
    </div>
  );
}

// ── List / table view ───────────────────────────────────────────────────────
function KgListView({ scope, selectedId, onSelect, onNavigate, query, typeFilter }) {
  const q = (query || "").trim().toLowerCase();
  const rows = scope.nodes.filter((n) => {
    const cat = kgCategory(n);
    if (typeFilter && typeFilter.size && !typeFilter.has(cat)) return false;
    if (q && !(n.label + " " + (n.claim || "") + " " + n.type).toLowerCase().includes(q)) return false;
    return true;
  });
  const rel = (n) => scope.nodes.filter((m) => (m.related || []).includes(n.id) || (n.related || []).includes(m.id)).length;
  return (
    <div className="kg-list">
      <div className="kg-list-head"><span>Entity</span><span>Kind</span><span>Nous</span><span>Links</span></div>
      <div className="kg-list-rows">
        {rows.map((n) => {
          const total = n.score ? n.score[0] + n.score[1] + n.score[2] : null;
          return (
            <button type="button" key={n.id} className={"kg-list-row" + (n.id === selectedId ? " is-sel" : "")}
              onClick={() => n.scopeRef ? onNavigate(n.scopeRef) : onSelect(n.id)}>
              <span className="kg-list-name"><span className="kg-legend-dot" style={{ background: kgTypeColor(n) }}></span>{n.label}{n.live && <span className="mcc-dot-tide" style={{ width: 10, height: 10, marginLeft: 2 }}></span>}</span>
              <span className="kg-list-kind">{n.scopeRef ? "folder ›" : (KG_TYPE[n.type] || {}).label || n.type}</span>
              <span className="kg-list-score">{total != null ? <span className="kg-list-pip" data-v={total >= 7 ? "hi" : total >= 3 ? "mid" : "lo"}>{total}</span> : "—"}</span>
              <span className="kg-list-links">{rel(n)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Right rail · recently viewed · pinned · what's new ──────────────────────
function KgRailItem({ scopeId, nodeId, meta, onPick, onUnpin }) {
  const sc = KG_SCOPES[scopeId]; const n = sc && sc.nodes.find((x) => x.id === nodeId); if (!n) return null;
  return (
    <button type="button" className="kg-rail-item" onClick={() => onPick(scopeId, nodeId)}>
      <span className="kg-legend-dot" style={{ background: kgTypeColor(n) }}></span>
      <span className="kg-rail-body"><span className="kg-rail-label">{n.label}</span><span className="kg-rail-sub">{sc.crumb} · {meta || (KG_TYPE[n.type] || {}).label || n.type}</span></span>
      {onUnpin && <span className="kg-iconbtn kg-rail-pin" onClick={(e) => { e.stopPropagation(); onUnpin(scopeId, nodeId); }} title="Unpin"><IcPin size={13} /></span>}
    </button>
  );
}
function KgRail({ recent, pinned, onPick, onUnpin }) {
  return (
    <div className="kg-rail">
      {pinned.length > 0 && (
        <div className="kg-rail-sec">
          <div className="mcc-panel-label"><IcPin size={12} /> Pinned</div>
          {pinned.map((p) => <KgRailItem key={p.scopeId + p.nodeId} {...p} onPick={onPick} onUnpin={onUnpin} />)}
        </div>
      )}
      <div className="kg-rail-sec">
        <div className="mcc-panel-label">Recently viewed</div>
        {recent.length === 0 ? <p className="kg-rail-empty">Open an entity and it lands here.</p>
          : recent.map((p) => <KgRailItem key={p.scopeId + p.nodeId} {...p} onPick={onPick} />)}
      </div>
      <div className="kg-rail-sec">
        <div className="mcc-panel-label">What's new <span className="kg-rail-count">freshly bookkept</span></div>
        {KG_FRESH.map((f) => <KgRailItem key={f.scopeId + f.nodeId} scopeId={f.scopeId} nodeId={f.nodeId} meta={f.when + " ago"} onPick={onPick} />)}
      </div>
    </div>
  );
}

// ── The page ────────────────────────────────────────────────────────────────
function MccKnowledge({ onOpenView, theme, onToggleTheme }) {
  const noop = () => {};
  const [scopeId, setScopeId] = React.useState("broomva");
  const [sel, setSel] = React.useState(null);
  const [drawer, setDrawer] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [view, setView] = React.useState("graph");
  const [filter, setFilter] = React.useState(new Set());
  const [recent, setRecent] = React.useState([]);
  const [pinned, setPinned] = React.useState([{ scopeId: "broomva", nodeId: "p6" }]);
  const [ask, setAsk] = React.useState(null);

  const scope = KG_SCOPES[scopeId];
  const path = kgPath(scopeId);
  const cats = React.useMemo(() => { const s = new Set(scope.nodes.map(kgCategory)); return ["folder", "concept", "decision", "primitive", "tool", "person", "paper", "doc", "session", "pattern"].filter((c) => s.has(c)); }, [scope]);

  const navigate = (id) => {
    if (typeof id === "string" && id.indexOf("__page:") === 0) { onOpenView && onOpenView(id.slice(7)); return; }
    if (!KG_SCOPES[id]) return;
    setScopeId(id); setSel(null); setDrawer(false); setAsk(null);
  };
  const pushRecent = (sid, nid) => setRecent((r) => [{ scopeId: sid, nodeId: nid }, ...r.filter((x) => !(x.scopeId === sid && x.nodeId === nid))].slice(0, 6));
  const selectNode = (nid) => { setSel(nid); setDrawer(true); setAsk(null); pushRecent(scopeId, nid); };
  const pickEntity = (sid, nid) => { if (sid !== scopeId) { setScopeId(sid); } setSel(nid); setDrawer(true); setAsk(null); pushRecent(sid, nid); };
  const togglePin = (sid, nid) => setPinned((p) => p.some((x) => x.scopeId === sid && x.nodeId === nid) ? p.filter((x) => !(x.scopeId === sid && x.nodeId === nid)) : [...p, { scopeId: sid, nodeId: nid }]);
  const toggleCat = (c) => setFilter((f) => { const n = new Set(f); n.has(c) ? n.delete(c) : n.add(c); return n; });
  const doAsk = (text) => { setQ(text); const hits = scope.nodes.filter((n) => !n.scopeRef && (n.label + " " + n.claim).toLowerCase().includes(text.toLowerCase())).slice(0, 4); setAsk({ text, hits: hits.map((h) => h.id) }); setSel(null); setDrawer(false); };

  return (
    <div className="mcc-fill">
      <div className="bv-app" style={{ gridTemplateColumns: bvNavGrid() }}>
        <BvNavTree active="knowledge" inApp onNav={onOpenView} renderTree={() => <KnowTree activeId={scopeId} onNav={navigate} />} />
        <div className="bv-main">
          {/* shared root header · ⌘K here searches the graph (contextual) */}
          <McvTopBar theme={theme} onToggleTheme={onToggleTheme || noop} onOpenMaestro={() => onOpenView && onOpenView("app")}
            onWake={noop} waking={false} canWake={true} onShowIdea={noop}
            counts={{ needYou: 1, stuck: 1 }} workers={["claude", "bookkeeper"]}
            wakes={MCC_TICK_WAKES} items={WK_ITEMS} onAttention={() => onOpenView && onOpenView("app")}
            onCommand={() => window.dispatchEvent(new CustomEvent("bv:command-open"))} />

          <div className="kg-page" data-screen-label="Knowledge graph">
            <div className="kg-bar">
              <div className="kg-path">
                {path.map((s, i) => (
                  <React.Fragment key={s.id}>
                    {i > 0 && <span className="kg-crumb-sep">›</span>}
                    <button type="button" className={"kg-crumb-btn" + (s.id === scopeId ? " is-active" : "")} onClick={() => navigate(s.id)}>{s.crumb}</button>
                  </React.Fragment>
                ))}
                <span className="kg-scopekind">{scope.kind} · {scope.nodes.length}</span>
              </div>
              <div className="kg-bar-right">
                <div className="mcc-seg kg-viewtoggle">
                  <button type="button" className={"mcc-seg-btn" + (view === "graph" ? " is-active" : "")} onClick={() => setView("graph")}><IcGraph size={13} />Graph</button>
                  <button type="button" className={"mcc-seg-btn" + (view === "list" ? " is-active" : "")} onClick={() => setView("list")}><IcList size={13} />List</button>
                </div>
              </div>
            </div>

            <div className="kg-body">
              <div className="kg-main">
                <div className="kg-chips">
                  <button type="button" className={"kg-chip" + (filter.size === 0 ? " is-active" : "")} onClick={() => setFilter(new Set())}>All</button>
                  {cats.map((c) => (
                    <button type="button" key={c} className={"kg-chip" + (filter.has(c) ? " is-active" : "")} onClick={() => toggleCat(c)}>
                      <span className="kg-legend-dot" style={{ background: c === "folder" ? KG_GOLD : (KG_TYPE[c] || {}).color }}></span>
                      {c === "folder" ? "folders" : (KG_TYPE[c] || {}).label || c}
                    </button>
                  ))}
                </div>
                <div className="kg-graphwrap">
                  {view === "graph"
                    ? <KgGraph scope={scope} scopes={KG_SCOPES} selectedId={sel} onSelectNode={selectNode} onNavigate={navigate} query={ask ? ask.text : q} typeFilter={filter} width={820} height={660} />
                    : <KgListView scope={scope} selectedId={sel} onSelect={selectNode} onNavigate={navigate} query={q} typeFilter={filter} />}
                  {drawer && <KgDetailDrawer scope={scope} nodeId={sel} pinned={pinned} onPin={togglePin} onSelect={selectNode} onNavigate={navigate} onClose={() => { setDrawer(false); setSel(null); }} />}
                </div>
              </div>
              <div className="kg-panel">
                {ask
                  ? <KgAskPanel ask={ask} scope={scope} onPick={selectNode} onClose={() => { setAsk(null); setQ(""); }} />
                  : <KgRail recent={recent} pinned={pinned} onPick={pickEntity} onUnpin={togglePin} />}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// answer card for "ask the graph"
function KgAskPanel({ ask, scope, onPick, onClose }) {
  const hits = ask.hits.map((id) => scope.nodes.find((n) => n.id === id)).filter(Boolean);
  return (
    <div className="kg-ask">
      <div className="kg-ask-head"><span className="kg-ask-q"><IcGraph size={14} /> {ask.text}</span><button type="button" className="kg-iconbtn" onClick={onClose}><IcX size={14} /></button></div>
      <p className="kg-ask-answer">{hits.length ? <>The graph surfaces <b>{hits.length}</b> {hits.length === 1 ? "entity" : "entities"} in <b>{scope.crumb}</b> that bear on this · highlighted on the canvas, cited below.</> : <>Nothing in <b>{scope.crumb}</b> matches yet. Try a parent scope, or rephrase.</>}</p>
      <div className="kg-ask-cites">
        {hits.map((n) => (
          <button type="button" key={n.id} className="kg-back" onClick={() => onPick(n.id)}>
            <span className="kg-legend-dot" style={{ background: kgTypeColor(n) }}></span>{n.label}
          </button>
        ))}
      </div>
      <p className="kg-ask-foot">An answer is a retrieval, not a guess · every claim cites the entity it came from (P6).</p>
    </div>
  );
}

Object.assign(window, { MccKnowledge, BvKgSearch, KgDetailDrawer, KgListView, KgRail, KgAskPanel, KG_FRESH, KG_NAV_PAGES });
