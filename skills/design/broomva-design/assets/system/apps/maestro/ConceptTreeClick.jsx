// Concepts canvas · clicking the workspace tree.
// The sidebar is the workspace; every rung is a folder with a contract.
// Selection scopes the plane AND retunes the panel's inspector:
//   root      → everything + the meta-contract (places, defaults, the score)
//   initiative→ the place's work + folder inspector (contract, subfolders)
//   project   → the contract's floor + spec & sessions (W2)
// Deeper rungs (work item → live panel, session → drill-in) already shipped.

const IcTcChev = (p) => <McIcon {...p}><path d="m9 18 6-6-6-6"></path></McIcon>;

const mccTcById = (id) => WK_ITEMS.find((i) => i.id === id);

// ── T0 · The ladder · schema ──────────────────────────────────────────────
function MccTreeSchema() {
  const rungs = [
    {
      depth: 0, glyph: <IcFolderOpen size={14} />, name: "Broomva", kind: "the workspace root",
      plane: "everything · all places, grouped by attention",
      panel: "the meta-contract: cascade defaults, the places, the score",
    },
    {
      depth: 1, glyph: <IcFolderOpen size={14} />, name: "hawthorne/", kind: "initiative folder",
      plane: "the place · its work, grouped by state",
      panel: "folder inspector: contract chips, subfolders, sessions rollup",
    },
    {
      depth: 2, glyph: <IcFolder size={13} />, name: "hawthorne-core/", kind: "project folder",
      plane: "the contract's floor · only this folder's items",
      panel: "spec + sessions · the W2 inspector",
    },
    {
      depth: 3, glyph: <span className="mc-chip-dot" style={{ background: "var(--bv-blue-accent)" }}></span>, name: "work item", kind: "card in the plane",
      plane: "stays put · the card highlights",
      panel: "the live panel: chat / activity / the look (shipped)",
    },
    {
      depth: 4, glyph: <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>, name: "session", kind: "row in an inspector",
      plane: "stays put",
      panel: "drill-in: the chat projection, back-link to its folder (shipped)",
    },
  ];
  return (
    <div className="mcc-pad">
      <div>
        {rungs.map((r, i) => (
          <div key={i} className="mcc-rung">
            <div className="mcc-rung-name" style={{ paddingLeft: r.depth * 16 }}>
              {r.glyph}
              <span className="mcc-rung-stack">
                <span>{r.name}</span>
                <span className="mcc-rung-kind">{r.kind}</span>
              </span>
            </div>
            <span className="mcc-prim-arrow">→</span>
            <div className="mcc-rung-out">
              <span><b>plane</b> {r.plane}</span>
              <span><b>panel</b> {r.panel}</span>
            </div>
          </div>
        ))}
      </div>
      <p className="mcc-caption">One law for the whole ladder: a click never navigates away · it scopes the plane and retunes the panel. The deeper the rung, the more specific the contract; the receipts stay one click away at every depth.</p>
    </div>
  );
}

// ── Shared interactive frame ──────────────────────────────────────────────
// The maestro-loop sidebar · now in the IA4 tree-led structure (shared design
// with the Knowledge / History pages): adaptive lens primary + History/Knowledge
// lenses, the loop's Workspace tree (scope nav kept), bench, autonomy, footer.
function MccTcSidebar({ scope, setScope, onMission, missionActive, resize, collapsed, onOpenView }) {
  const sbText = { flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "left" };

  // Minimized · an icon rail (IA3): lenses + workspace folders + footer, icons only.
  if (collapsed) {
    const hawActive = scope === "hawthorne" || scope === "core";
    return (
      <aside className="mcc-rail mcc-rail--side" data-screen-label="Sidebar (rail)">
        <img className="bv-ws-logo" src="../../assets/broomva-blackhole-logo.png" alt="" style={{ width: 24, height: 24, marginBottom: 6 }} />
        <button className={"mcc-rail-btn" + (missionActive ? " is-on" : "")} type="button" onClick={onMission} title="Needs you">
          <IcInbox size={14} /><span className="mcc-rail-badge">2</span>
        </button>
        <button className="mcc-rail-btn" type="button" onClick={() => onOpenView && onOpenView("history")} title="History"><IcHistory size={14} /></button>
        <button className="mcc-rail-btn" type="button" onClick={() => onOpenView && onOpenView("knowledge")} title="Knowledge"><IcGraph size={14} /></button>
        <div className="mcc-rail-div"></div>
        <button className={"mcc-rail-btn" + (scope === "root" ? " is-on" : "")} type="button" onClick={() => setScope("root")} title="Broomva · workspace root"><IcFolderOpen size={14} /></button>
        <button className={"mcc-rail-btn" + (hawActive ? " is-on" : "")} type="button" onClick={() => setScope("hawthorne")} title="hawthorne"><IcFolder size={14} /></button>
        <button className="mcc-rail-btn" type="button" onClick={() => setScope("root")} title="genesis"><IcFolder size={14} /></button>
        <button className="mcc-rail-btn" type="button" onClick={() => setScope("root")} title="ops"><IcFolder size={14} /></button>
        <div className="bv-sb-spacer"></div>
        <button className="mcc-rail-btn" type="button" title="Feedback" onClick={() => onOpenView && onOpenView("feedback")}><IcMessage size={15} /></button>
        <button className="mcc-rail-btn" type="button" title="Settings" onClick={() => onOpenView && onOpenView("settings")}><IcSettings size={15} /></button>
        <button className="mcc-rail-btn mcc-rail-avatar" type="button" title="Ana Diaz" onClick={() => onOpenView && onOpenView("user")}><McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={20} /></button>
      </aside>
    );
  }

  return (
    <aside className="bv-sidebar mcc-nav" data-screen-label="Sidebar"
      style={collapsed ? { padding: 0, borderRight: "none" } : undefined}>
      {resize && !collapsed && <div className="mcc-coldrag mcc-coldrag--right" onMouseDown={resize} title="Drag to resize" />}
      <button className="bv-ws-switch" type="button">
        <img className="bv-ws-logo" src="../../assets/broomva-blackhole-logo.png" alt="" />
        <span className="bv-ws-name">Broomva</span>
        <IcChevrons size={14} />
      </button>
      <div className="mcc-lensbar">
        <button className={"mcc-lens" + (missionActive ? " is-active" : "")} type="button" onClick={onMission}><IcInbox size={14} />Needs you<span className="mcc-lens-badge">2</span></button>
        <button className="mcc-lens" type="button" onClick={() => onOpenView && onOpenView("history")}><IcHistory size={14} />History</button>
        <button className="mcc-lens" type="button" onClick={() => onOpenView && onOpenView("knowledge")}><IcGraph size={14} />Knowledge</button>
      </div>
      <div className="bv-sb-section-label">Workspace</div>
      <div className="mcc-sb-col">
        <button className={"bv-sb-item" + (scope === "root" ? " is-active" : "")} type="button"
          onClick={() => setScope("root")} title="The workspace root · ~/Broomva">
          <IcFolderOpen size={14} /><span style={sbText}>Broomva</span><span className="mc-init-progress">3 places</span>
        </button>
        <button className={"bv-sb-item" + (scope === "hawthorne" ? " is-active" : "")} type="button"
          style={{ paddingLeft: 24 }} onClick={() => setScope("hawthorne")}>
          <IcFolderOpen size={14} /><span style={sbText}>hawthorne</span><span className="mc-init-progress">1/6</span>
        </button>
        <button className={"bv-sb-item" + (scope === "core" ? " is-active" : "")} type="button"
          style={{ paddingLeft: 42 }} onClick={() => setScope("core")}>
          <IcFolder size={13} /><span style={sbText}>hawthorne-core</span><span className="bv-sb-badge">1</span>
        </button>
        <button className="bv-sb-item" type="button" style={{ paddingLeft: 42 }}>
          <IcFolder size={13} /><span style={sbText}>hawthorne-db</span><span className="bv-sb-badge">1</span>
        </button>
        <button className="bv-sb-item" type="button" style={{ paddingLeft: 24 }}>
          <IcFolder size={14} /><span style={sbText}>genesis</span><span className="mc-init-progress">0/1</span>
        </button>
        <button className="bv-sb-item" type="button" style={{ paddingLeft: 42 }}>
          <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>
          <span style={sbText}>@genesis/projection</span>
        </button>
        <button className="bv-sb-item" type="button" style={{ paddingLeft: 24 }}>
          <IcFolder size={14} /><span style={sbText}>ops</span><span className="mc-init-progress">0/1</span>
        </button>
        <button className="bv-sb-item" type="button" style={{ paddingLeft: 42 }}>
          <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>
          <span style={sbText}>bookkeeping</span>
        </button>
      </div>
      <div className="bv-sb-spacer"></div>
      <NavAutonomy onOpenView={onOpenView} />
      <div className="mcc-nav-foot">
        <button className="mcc-foot-btn" type="button" onClick={() => onOpenView && onOpenView("feedback")}><IcMessage size={15} />Feedback</button>
        <button className="mcc-foot-btn" type="button" onClick={() => onOpenView && onOpenView("settings")}><IcSettings size={15} />Settings</button>
        <button className="mcc-foot-btn mcc-foot-profile" type="button" onClick={() => onOpenView && onOpenView("user")}>
          <McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={20} /><span>Ana Diaz</span>
        </button>
      </div>
    </aside>
  );
}

function MccTcGroup({ state, items }) {
  const meta = WK_STATES[state];
  return (
    <section className="mc-group">
      <div className="mc-group-header">
        <span className="mc-group-label">
          <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>
          {meta.plain}
        </span>
        <span className="mc-group-count">{items.length}</span>
        <span className="mc-group-hint">{WK_GROUP_HINTS[state]}</span>
      </div>
      <div className="mc-group-cards">
        {items.map((item) => (
          <MccLiveWorkCard key={item.id} item={item} selected={false} onSelect={() => {}} />
        ))}
      </div>
    </section>
  );
}

const MCC_TC_PLANE = {
  root: {
    crumb: "~",
    title: "Broomva/",
    chips: ["kind: workspace", "3 places", "defaults cascade ↓"],
    groups: [["review", ["w1"]], ["blocked", ["w2"]], ["running", ["w3", "w4"]]],
  },
  hawthorne: {
    crumb: "~ / Broomva",
    title: "hawthorne/",
    chips: ["kind: initiative", "owner: you", "budget: 24h/wk unsupervised", "gate: human-approve"],
    groups: [["review", ["w1"]], ["blocked", ["w2"]], ["queued", ["w5", "w6"]]],
  },
  core: {
    crumb: "~ / Broomva / hawthorne",
    title: "hawthorne-core/",
    chips: ["kind: project", "inherits: budget 8h · gate human-approve", "worktree-per-run"],
    groups: [["review", ["w1"]], ["queued", ["w5"]], ["proposed", ["w7"]]],
  },
};

function MccTcPlane({ scope }) {
  const p = MCC_TC_PLANE[scope];
  return (
    <div className="mcc-plane" data-screen-label={"Plane scoped to " + scope}>
      <div className="mcc-scope-head">
        <span className="mc-detail-breadcrumb">{p.crumb}</span>
        <div className="mcc-folder-title-row">
          <span className="mcc-chat-pop-title">{p.title}</span>
          <div className="mcc-fm-chips">
            {p.chips.map((c) => <span key={c} className="mc-receipt">{c}</span>)}
          </div>
        </div>
      </div>
      <div className="mcc-plane-body" data-view="feed">
        <div className="mcc-plane-feed">
          {p.groups.map(([state, ids]) => (
            <MccTcGroup key={state} state={state} items={ids.map(mccTcById)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function MccTcRow({ glyph, label, meta, onClick }) {
  return (
    <button className="mcc-sess" type="button" onClick={onClick} style={onClick ? undefined : { cursor: "default" }}>
      {glyph}
      <span className="mcc-sess-body">
        <span className="mcc-sess-label">{label}</span>
        <span className="mcc-sess-meta">{meta}</span>
      </span>
      {onClick && <IcTcChev size={13} />}
    </button>
  );
}

function MccTcPanel({ scope, setScope }) {
  if (scope === "root") {
    return (
      <aside className="mcc-live-panel" data-screen-label="Workspace inspector">
        <div className="mcc-panel-head">
          <span className="mc-detail-breadcrumb">~ / Broomva</span>
          <div className="mcc-chat-pop-title-row">
            <span className="mcc-chat-pop-title">Broomva/</span>
            <span className="mc-badge"><span className="mc-chip-dot" style={{ background: "var(--bv-blue-accent)" }}></span>2 need you</span>
          </div>
          <div className="mcc-fm-chips">
            <span className="mc-receipt">kind: workspace</span>
            <span className="mc-receipt">runner: claude · worktrees 2/2</span>
            <span className="mc-receipt">defaults: gate human-approve</span>
          </div>
        </div>
        <div className="mcc-panel-activity">
          <div className="mcc-panel-label" style={{ paddingBottom: 0 }}>Places · contracts cascade down</div>
          <div className="mcc-sess-list">
            <MccTcRow glyph={<IcFolderOpen size={14} />} label="hawthorne"
              meta="1/6 done · 2 need you · budget 24h/wk" onClick={() => setScope("hawthorne")} />
            <MccTcRow glyph={<span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>}
              label="genesis" meta="1 live · reduce the NDJSON stream" />
            <MccTcRow glyph={<span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>}
              label="ops" meta="1 live · 1 standing · nightly digest 02:00" />
          </div>
          <div className="mcc-panel-label" style={{ paddingBottom: 0 }}>The score</div>
          <MccTcRow glyph={<span className="mc-chip-dot" style={{ background: "var(--bv-success)" }}></span>}
            label="6h 24m unsupervised today" meta="2 looks · longest run 3h 50m" />
        </div>
      </aside>
    );
  }
  if (scope === "hawthorne") {
    return (
      <aside className="mcc-live-panel" data-screen-label="Folder inspector (initiative)">
        <div className="mcc-panel-head">
          <span className="mc-detail-breadcrumb">Broomva / hawthorne</span>
          <div className="mcc-chat-pop-title-row">
            <span className="mcc-chat-pop-title">hawthorne/</span>
            <span className="mc-badge"><span className="mc-chip-dot" style={{ background: "var(--bv-blue-accent)" }}></span>2 need you</span>
          </div>
          <div className="mcc-fm-chips">
            <span className="mc-receipt">kind: initiative</span>
            <span className="mc-receipt">owner: you</span>
            <span className="mc-receipt">spec: hawthorne.md</span>
            <span className="mc-receipt">budget: 24h/wk</span>
          </div>
        </div>
        <div className="mcc-panel-activity">
          <div className="mcc-panel-label" style={{ paddingBottom: 0 }}>Folders</div>
          <div className="mcc-sess-list">
            <MccTcRow glyph={<IcFolder size={14} />} label="hawthorne-core"
              meta="3 open · 1 at your gate" onClick={() => setScope("core")} />
            <MccTcRow glyph={<span className="mc-chip-dot" style={{ background: "var(--bv-warning)", marginTop: 5 }}></span>}
              label="hawthorne-db" meta="1 stuck · needs a Linear API scope" />
            <MccTcRow glyph={<IcFolder size={14} />} label="hawthorne-engine" meta="1 queued · 1 done" />
          </div>
          <div className="mcc-panel-label" style={{ paddingBottom: 0 }}>Sessions today</div>
          <MccTcRow glyph={<span className="mc-chip-dot" style={{ background: "var(--bv-success)" }}></span>}
            label="3 sessions · 2h 40m unsupervised" meta="1 look · the API design review" />
        </div>
      </aside>
    );
  }
  return (
    <aside className="mcc-live-panel" data-screen-label="Folder inspector (project, W2)">
      <div className="mcc-panel-head">
        <span className="mc-detail-breadcrumb">hawthorne / hawthorne-core</span>
        <div className="mcc-chat-pop-title-row">
          <span className="mcc-chat-pop-title">hawthorne-core/</span>
          <span className="mc-badge"><span className="mc-chip-dot" style={{ background: "var(--bv-blue-accent)" }}></span>At your gate</span>
        </div>
        <div className="mcc-fm-chips">
          <span className="mc-receipt">kind: project</span>
          <span className="mc-receipt">owner: maestro</span>
          <span className="mc-receipt">budget: 8h unsupervised</span>
          <span className="mc-receipt">gate: human-approve</span>
        </div>
      </div>
      <div className="mcc-panel-activity">
        <div className="mcc-panel-label" style={{ paddingBottom: 0 }}>Contract</div>
        <div className="mcc-sess-list">
          <MccTcRow glyph={<IcDoc size={14} />} label="spec.md"
            meta="persist transcripts on the Run record · updated 2d" />
          <MccTcRow glyph={<IcFolder size={14} />} label="notes/"
            meta="2 files · prior-art survey, API decisions" />
        </div>
        <div className="mcc-panel-label" style={{ paddingBottom: 0 }}>Sessions</div>
        <div className="mcc-sess-list">
          <MccTcRow glyph={<span className="mc-chip-dot" style={{ background: "var(--bv-blue-accent)", marginTop: 5 }}></span>}
            label="persist run transcripts" meta="maestro → claude · 2h 14m · ran to the gate" />
          <MccTcRow glyph={<span className="mc-chip-dot" style={{ background: "var(--bv-success)", marginTop: 5 }}></span>}
            label="API design review" meta="you → claude · 38 events · done (2 looks)" />
        </div>
      </div>
    </aside>
  );
}

function MccTreeFrame({ initial }) {
  const noop = () => {};
  const [scope, setScope] = React.useState(initial);
  return (
    <div className="mcc-fill">
      <div className="bv-app">
        <MccTcSidebar scope={scope} setScope={setScope} />
        <div className="bv-main">
          <McvTopBar theme="light" onToggleTheme={noop} onOpenMaestro={noop}
            onWake={noop} waking={false} canWake={true} onShowIdea={noop}
            counts={{ needYou: 1, stuck: 1 }} workers={["claude", "bookkeeper"]}
            wakes={MCC_TICK_WAKES} items={WK_ITEMS} onAttention={noop} onCommand={noop} />
          <div className="mcc-merged-row" style={{ gridTemplateColumns: "minmax(0, 1fr) 440px" }}>
            <MccTcPlane scope={scope} />
            <MccTcPanel scope={scope} setScope={setScope} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MccTreeRoot() { return <MccTreeFrame initial="root" />; }
function MccTreeInitiative() { return <MccTreeFrame initial="hawthorne" />; }
function MccTreeProject() { return <MccTreeFrame initial="core" />; }

Object.assign(window, { MccTreeSchema, MccTreeRoot, MccTreeInitiative, MccTreeProject, MccTcSidebar, MccTcPlane, MccTcPanel });
