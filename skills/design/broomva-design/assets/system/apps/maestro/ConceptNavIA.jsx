// Concept · sidebar architecture. The canvas already asked "what is the nav a
// list OF"; this answers "what are the top-level destinations, and where do
// History + Knowledge slot in". BvNav is the canonical sidebar, reused by the
// History and Knowledge full-page frames so the chrome is identical everywhere.

const IcSearch  = (p) => <McIcon {...p}><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></McIcon>;
const IcHistory = (p) => <McIcon {...p}><path d="M3 12a9 9 0 1 0 3-6.7L3 8"></path><path d="M3 3v5h5"></path><path d="M12 7v5l3 2"></path></McIcon>;
const IcGraph   = (p) => <McIcon {...p}><circle cx="5" cy="6" r="2.5"></circle><circle cx="19" cy="8" r="2.5"></circle><circle cx="12" cy="18" r="2.5"></circle><path d="M7.2 7.1 16.8 9M6.4 8.2l4.6 7.6M17.7 10.2l-4.6 6"></path></McIcon>;
const IcInbox   = (p) => <McIcon {...p}><path d="M22 12h-6l-2 3h-4l-2-3H2"></path><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"></path></McIcon>;
const IcUsers   = (p) => <McIcon {...p}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.9"></path><path d="M16 3.1a4 4 0 0 1 0 7.8"></path></McIcon>;
const IcMessage = (p) => <McIcon {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></McIcon>;

// ── The workspace tree rows (places) · shared across the IA frames ─────────
function NavTreeRows() {
  const sbText = { flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "left" };
  return (
    <>
      <button className="bv-sb-item" type="button">
        <IcFolderOpen size={14} /><span style={sbText}>hawthorne</span><span className="mc-init-progress">1/6</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 28 }}>
        <IcFolder size={13} /><span style={sbText}>hawthorne-core</span><span className="bv-sb-badge">1</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 28 }}>
        <IcFolder size={13} /><span style={sbText}>hawthorne-db</span><span className="bv-sb-badge">1</span>
      </button>
      <button className="bv-sb-item" type="button">
        <IcFolder size={14} /><span style={sbText}>genesis</span><span className="mc-init-progress">0/1</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 28 }}>
        <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span><span style={sbText}>@genesis/projection</span>
      </button>
      <button className="bv-sb-item" type="button">
        <IcFolder size={14} /><span style={sbText}>ops</span><span className="mc-init-progress">0/1</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 28 }}>
        <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span><span style={sbText}>bookkeeping</span>
      </button>
    </>
  );
}

function NavBench() {
  return (
    <div className="mcc-sb-bench" title="The bench · live workers, the orchestrator first among them">
      <span className="mcc-dot-comet" style={{ width: 15, height: 15 }}><span className="mcc-dot-comet-core"></span></span>
      <span className="mcc-bench-faces">
        <McAvatar name="claude" color="var(--bv-blue)" size={20} />
        <McAvatar name="bookkeeper" color="var(--bv-purple, #7c6cf0)" size={20} />
      </span>
      <span className="mcc-sb-sub" style={{ marginLeft: 2 }}>2 live · next 13m</span>
    </div>
  );
}

const IcArrowR = (p) => <McIcon {...p}><path d="M5 12h14M13 6l6 6-6 6"></path></McIcon>;

// Today's runs, the looks as notches, the live one under the tidepool.
const AUTOP_RUNS = [
  { l: 6, w: 4 }, { l: 30, w: 1.6 }, { l: 36, w: 1.1 },
  { l: 44, w: 21 }, { l: 67, w: 9 }, { l: 78, w: 8, live: true },
];
const AUTOP_LOOKS = [30, 65];
const AUTOP_WHERE = [
  { title: "Close the execution loop (M1b)", crumb: "hawthorne-engine", dur: "3h 50m", state: "done" },
  { title: "Reduce NDJSON to a phase machine", crumb: "genesis / projection", dur: "1h 18m", state: "live" },
  { title: "Nightly digest", crumb: "ops", dur: "31m", state: "routine" },
];

function NavAutonomy({ onOpenView }) {
  const [open, setOpen] = React.useState(false);
  const [pos, setPos] = React.useState(null);
  const cardRef = React.useRef(null);
  const timer = React.useRef(null);

  const place = () => {
    const el = cardRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const W = 332;
    let left = r.left;
    left = Math.max(8, Math.min(left, window.innerWidth - W - 8));
    setPos({ left, bottom: window.innerHeight - r.top + 8 });
  };
  const show = () => { clearTimeout(timer.current); place(); setOpen(true); };
  const hide = () => { clearTimeout(timer.current); timer.current = setTimeout(() => setOpen(false), 140); };
  React.useEffect(() => () => clearTimeout(timer.current), []);

  const pop = open && pos && ReactDOM.createPortal(
    <div className="autop" style={{ left: pos.left, bottom: pos.bottom }}
      onMouseEnter={show} onMouseLeave={hide}>
      <div className="autop-head">
        <div className="autop-head-main">
          <span className="autop-label">Unsupervised · today</span>
          <span className="autop-big">6h 24<small>m</small></span>
        </div>
        <span className="autop-delta"><IcArrowR size={12} style={{ transform: "rotate(-45deg)" }} />+18%</span>
      </div>

      <div className="autop-tl">
        <div className="autop-track" title="Each block is a run; each notch is a moment you looked">
          {AUTOP_RUNS.map((b, i) => (
            <span key={i} className={"autop-run" + (b.live ? " is-live" : "")} style={{ left: b.l + "%", width: b.w + "%" }}></span>
          ))}
          {AUTOP_LOOKS.map((l, i) => <span key={"k" + i} className="autop-look" style={{ left: l + "%" }}></span>)}
        </div>
        <div className="autop-ticks"><span>12a</span><span>9a</span><span>3p</span><span>now</span></div>
      </div>

      <div className="autop-stats">
        <div className="autop-stat"><span className="autop-stat-val">2</span><span className="autop-stat-lab">looks today</span></div>
        <div className="autop-stat"><span className="autop-stat-val">3h 50m</span><span className="autop-stat-lab">longest run</span></div>
        <div className="autop-stat"><span className="autop-stat-val">7</span><span className="autop-stat-lab">sessions</span></div>
      </div>

      <div className="autop-where">
        <div className="autop-where-label">Where the hours went</div>
        {AUTOP_WHERE.map((s, i) => (
          <div className="autop-row" key={i}>
            {s.state === "live"
              ? <span className="mcc-dot-tide" style={{ width: 11, height: 11, flexShrink: 0 }}></span>
              : <span className="mc-chip-dot" style={{ width: 8, height: 8, flexShrink: 0, background: s.state === "done" ? "var(--bv-success)" : "var(--bv-gray-400)" }}></span>}
            <span className="autop-row-body">
              <span className="autop-row-title">{s.title}</span>
              <span className="autop-row-crumb">{s.crumb}{s.state === "routine" ? " · routine" : ""}</span>
            </span>
            <span className="autop-row-dur">{s.dur}</span>
          </div>
        ))}
      </div>

      <div className="autop-foot">
        <span className="autop-foot-note">A look is any time you stepped in.</span>
        <button type="button" className="autop-link" onClick={() => { setOpen(false); onOpenView && onOpenView("history"); }}>Open History<IcArrowR /></button>
      </div>
    </div>,
    document.body
  );

  return (
    <div ref={cardRef} style={{ margin: "0 2px" }}
      onMouseEnter={show} onMouseLeave={hide} tabIndex={0} onFocus={show} onBlur={hide}>
      <DsAutonomyScoreboard
        hours="6h 24m" sub="2 looks · longest run 3h 50m"
        segments={[{ start: 0, width: 34 }, { start: 36, width: 42 }, { start: 80, width: 14, live: true }]}
        notches={[34, 78]}
        style={{
          margin: 0, cursor: "default",
          borderColor: open ? "var(--bv-border-15)" : undefined,
          background: open ? "var(--bv-frost-4)" : undefined,
          transition: "border-color var(--bv-dur-fast) var(--bv-ease-standard), background var(--bv-dur-fast)",
        }}
      >
        {pop}
      </DsAutonomyScoreboard>
    </div>
  );
}

// ── The canonical sidebar · reused by History + Knowledge pages ────────────
function BvNav({ active, inApp }) {
  const item = (id, icon, label, badge) => (
    <button className={"bv-sb-item" + (active === id ? " is-active" : "")} type="button">
      {icon}<span className="mcc-sb-text">{label}</span>
      {badge != null && <span className="bv-sb-badge">{badge}</span>}
    </button>
  );
  return (
    <aside className={"bv-sidebar mcc-nav" + (inApp ? "" : " mcc-side")} data-screen-label="Canonical sidebar">
      <button className="bv-ws-switch" type="button">
        <img className="bv-ws-logo" src="../../assets/broomva-blackhole-logo.png" alt="" />
        <span className="bv-ws-name">Broomva</span>
        <IcChevrons size={14} />
      </button>
      <button className="mcc-sb-cmd" type="button">
        <IcSearch size={14} /><span>Search or run a command</span><kbd>⌘K</kbd>
      </button>
      <nav className="mcc-sb-col" style={{ marginTop: 4 }}>
        {item("needs", <IcInbox size={16} />, "Needs you", 2)}
        {item("mc", <IcBoard />, "Maestro")}
      </nav>
      <div className="bv-sb-section-label">Workspace</div>
      <div className="mcc-sb-col"><NavTreeRows /></div>
      <div className="bv-sb-section-label">Library</div>
      <div className="mcc-sb-col">
        {item("history", <IcHistory size={16} />, "History")}
        {item("knowledge", <IcGraph size={16} />, "Knowledge")}
      </div>
      <div className="bv-sb-spacer"></div>
      <div className="bv-sb-section-label" style={{ paddingBottom: 6 }}>Bench</div>
      <NavBench />
      <NavAutonomy />
      <button className="bv-sb-item" type="button" style={{ marginTop: 2 }}>
        <McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={18} />
        <span style={{ flex: 1, textAlign: "left" }}>Ana Diaz</span>
        <IcSettings size={15} />
      </button>
    </aside>
  );
}

// ── IA0 · The inventory · what earns a place in the sidebar ────────────────
const NAV_INVENTORY = [
  { name: "Needs you", role: "The gate · clean runs + blocks waiting on a human", verdict: "in", note: "first verb" },
  { name: "Maestro", role: "The plane · work sorted by what only you can decide", verdict: "in", note: "home" },
  { name: "Workspace", role: "Places · the FS tree, folders are work at any scale", verdict: "in", note: "the backbone" },
  { name: "History", role: "Sessions · every run, yours and the loop's", verdict: "lens", note: "a projection, not a place" },
  { name: "Knowledge", role: "The graph · frontmatter entities + related: edges", verdict: "lens", note: "a projection, not a place" },
  { name: "The bench", role: "Presence · live workers, maestro first", verdict: "dock", note: "footer, not nav" },
  { name: "Autonomy clock", role: "The score · unsupervised hours, next look", verdict: "dock", note: "footer" },
  { name: "Command / search", role: "Jump to any folder, session, or entity", verdict: "in", note: "top, ⌘K" },
  { name: "Sessions list", role: "Recent conversations, newest first", verdict: "out", note: "→ lives in History" },
  { name: "Settings", role: "Engine room · runners, credentials, scopes", verdict: "tuck", note: "by the account" },
];
const NAV_VERDICT = {
  in:   { c: "var(--bv-success)",     t: "nav" },
  lens: { c: "var(--bv-blue)",        t: "library" },
  dock: { c: "var(--bv-blue-accent)", t: "docked" },
  tuck: { c: "var(--bv-gray-500)",    t: "tucked" },
  out:  { c: "var(--bv-warning)",     t: "out" },
};

function MccNavInventory() {
  return (
    <div className="mcc-pad" style={{ gap: 10 }}>
      <div className="mcc-inv">
        <div className="mcc-inv-row mcc-inv-head">
          <span>Candidate</span><span>What it is</span><span>Where it lands</span>
        </div>
        {NAV_INVENTORY.map((r) => {
          const v = NAV_VERDICT[r.verdict];
          return (
            <div key={r.name} className="mcc-inv-row">
              <span className="mcc-inv-name">{r.name}</span>
              <span className="mcc-inv-role">{r.role}</span>
              <span className="mcc-inv-verdict">
                <span className="mcc-inv-pill" style={{ color: v.c, borderColor: "color-mix(in oklch, " + v.c + " 40%, transparent)" }}>{v.t}</span>
                <span className="mcc-inv-note">{r.note}</span>
              </span>
            </div>
          );
        })}
      </div>
      <p className="mcc-caption">The test isn't "is it useful" · everything's useful. It's <b>what kind of thing is it.</b> Verbs and places are nav; presence and the score are docked furniture; sessions and the graph are <i>projections</i> of the work · powerful lenses, so they get a Library group, never the backbone. The old "recent sessions" list is the one thing that leaves: it graduates into History.</p>
    </div>
  );
}

// ── IA1 · Canonical (the lead) ─────────────────────────────────────────────
function MccNavCanonical() {
  return (
    <div className="mcc-side-pad">
      <BvNav active="mc" />
      <p className="mcc-caption">The lead: a command surface up top, two verbs (the gate, the plane), the <b>Workspace</b> tree as the backbone, then a <b>Library</b> of lenses · History and Knowledge · that read across the work without being places. The bench, the autonomy clock and the account settle into the footer. Six destinations, one score, never a flat dump.</p>
    </div>
  );
}

// ── IA2 · Flat destinations ───────────────────────────────────────────────
function MccNavFlat() {
  const sbText = { flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "left" };
  const row = (icon, label, badge, active) => (
    <button className={"bv-sb-item" + (active ? " is-active" : "")} type="button">
      {icon}<span style={sbText}>{label}</span>{badge != null && <span className="bv-sb-badge">{badge}</span>}
    </button>
  );
  return (
    <div className="mcc-side-pad">
      <aside className="bv-sidebar mcc-side mcc-nav" data-screen-label="Flat destinations">
        <button className="bv-ws-switch" type="button">
          <img className="bv-ws-logo" src="../../assets/broomva-blackhole-logo.png" alt="" />
          <span className="bv-ws-name">Broomva</span><IcChevrons size={14} />
        </button>
        <button className="mcc-sb-cmd" type="button"><IcSearch size={14} /><span>Search…</span><kbd>⌘K</kbd></button>
        <nav className="mcc-sb-col" style={{ marginTop: 4 }}>
          {row(<IcInbox size={16} />, "Needs you", 2, true)}
          {row(<IcBoard />, "Maestro")}
          {row(<IcLayers size={15} />, "Workspace")}
          {row(<IcHistory size={16} />, "History")}
          {row(<IcGraph size={16} />, "Knowledge")}
          {row(<IcUsers size={16} />, "Bench", "2")}
          {row(<IcSettings size={15} />, "Settings")}
        </nav>
        <div className="bv-sb-spacer"></div>
        <NavAutonomy />
      </aside>
      <p className="mcc-caption">The literal seven, flat. Honest and dead simple · every destination is one click, no nesting to tend. The cost: <b>Workspace</b> hides the tree behind a click, so the folders that are the actual work go quiet, and the bench loses its faces. Best when the workspace is small or the operator lives in Maestro.</p>
    </div>
  );
}

// ── IA3 · Icon rail + reveal ──────────────────────────────────────────────
function MccNavRail() {
  const rail = [
    { ic: <IcInbox size={19} />, on: false, badge: 2 },
    { ic: <IcBoard />, on: true },
    { ic: <IcLayers size={18} />, on: false },
    { ic: <IcHistory size={19} />, on: false },
    { ic: <IcGraph size={19} />, on: false },
  ];
  const sbText = { flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "left" };
  return (
    <div className="mcc-side-pad">
      <div className="mcc-railwrap mcc-side" data-screen-label="Icon rail + reveal">
        <div className="mcc-rail">
          <img className="bv-ws-logo" src="../../assets/broomva-blackhole-logo.png" alt="" style={{ width: 26, height: 26, marginBottom: 4 }} />
          {rail.map((r, i) => (
            <button key={i} className={"mcc-rail-btn" + (r.on ? " is-on" : "")} type="button">
              {r.ic}{r.badge != null && <span className="mcc-rail-badge">{r.badge}</span>}
            </button>
          ))}
          <div className="bv-sb-spacer"></div>
          <button className="mcc-rail-btn" type="button"><IcUsers size={18} /></button>
          <McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={26} />
        </div>
        <div className="mcc-rail-reveal">
          <div className="mcc-reveal-head">Maestro</div>
          <div className="bv-sb-section-label" style={{ paddingTop: 4 }}>Workspace</div>
          <div className="mcc-sb-col"><NavTreeRows /></div>
          <div className="bv-sb-spacer"></div>
          <NavBench />
        </div>
      </div>
      <p className="mcc-caption">The rail keeps all seven destinations one click away in 52px, and the second column reveals the <i>contents</i> of whichever you're in · here, Maestro's workspace tree. Space-efficient and calm; the tradeoff is a hover/click to read any label, so it rewards a power user who's learned the icons.</p>
    </div>
  );
}

// Sidebar width · the full-page frames read the same persisted column the app's
// drag-resize writes, so the sidebar never jumps when switching views.
function bvNavGrid() {
  let w = 200;
  try { w = JSON.parse(localStorage.getItem("bv-ml-cols") || "{}").nav || 200; } catch {}
  return Math.round(w) + "px 1fr";
}

// The app's actual workspace tree · mirrors MccTcSidebar so the sidebar reads
// identically on the full-page frames (History / Settings / Account). Rows
// jump back into the app.
function AppTreeRows({ onOpen }) {
  const sbText = { flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "left" };
  const open = onOpen || (() => {});
  return (
    <>
      <button className="bv-sb-item" type="button" onClick={open} title="The workspace root · ~/Broomva">
        <IcFolderOpen size={14} /><span style={sbText}>Broomva</span><span className="mc-init-progress">3 places</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 24 }} onClick={open}>
        <IcFolderOpen size={14} /><span style={sbText}>hawthorne</span><span className="mc-init-progress">1/6</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 42 }} onClick={open}>
        <IcFolder size={13} /><span style={sbText}>hawthorne-core</span><span className="bv-sb-badge">1</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 42 }} onClick={open}>
        <IcFolder size={13} /><span style={sbText}>hawthorne-db</span><span className="bv-sb-badge">1</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 24 }} onClick={open}>
        <IcFolder size={14} /><span style={sbText}>genesis</span><span className="mc-init-progress">0/1</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 42 }} onClick={open}>
        <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>
        <span style={sbText}>@genesis/projection</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 24 }} onClick={open}>
        <IcFolder size={14} /><span style={sbText}>ops</span><span className="mc-init-progress">0/1</span>
      </button>
      <button className="bv-sb-item" type="button" style={{ paddingLeft: 42 }} onClick={open}>
        <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>
        <span style={sbText}>bookkeeping</span>
      </button>
    </>
  );
}

// ── IA4 · Tree-led, lenses pinned (the chosen direction) ──────────────────
// The tree-led sidebar itself · reused by the IA4 frame AND the History /
// Knowledge pages (pass inApp). `active` is the lit lens; `attention` drives the
// adaptive primary (Needs you + count → Maestro when the gate is clear).
function BvNavTree({ active, attention = 2, inApp, renderTree, onNav }) {
  const go = (id) => onNav && onNav(id);
  const lens = (id, icon, label) => (
    <button className={"mcc-lens" + (active === id ? " is-active" : "")} type="button" onClick={() => go(id)}>
      {icon}{label}
    </button>
  );
  return (
    <aside className={"bv-sidebar mcc-nav" + (inApp ? "" : " mcc-side")} data-screen-label="Tree-led nav">
      <button className="bv-ws-switch" type="button">
        <img className="bv-ws-logo" src="../../assets/broomva-blackhole-logo.png" alt="" />
        <span className="bv-ws-name">Broomva</span><IcChevrons size={14} />
      </button>
      <div className="mcc-lensbar">
        {attention > 0
          ? <button className={"mcc-lens" + (active === "needs" ? " is-active" : "")} type="button" onClick={() => go("app")}><IcInbox size={14} />Needs you<span className="mcc-lens-badge">{attention}</span></button>
          : <button className={"mcc-lens" + (active === "needs" ? " is-active" : "")} type="button" onClick={() => go("app")}><IcBoard />Maestro</button>}
        {lens("history", <IcHistory size={14} />, "History")}
        {lens("knowledge", <IcGraph size={14} />, "Knowledge")}
      </div>
      <div className="bv-sb-section-label">Workspace</div>
      {renderTree ? renderTree() : (
        <div className="mcc-sb-col"><AppTreeRows onOpen={() => go("app")} /></div>
      )}
      <div className="bv-sb-spacer"></div>
      <NavAutonomy />
      <div className="mcc-nav-foot">
        <button className="mcc-foot-btn" type="button" onClick={() => go("feedback")}><IcMessage size={15} />Feedback</button>
        <button className={"mcc-foot-btn" + (active === "settings" ? " is-active" : "")} type="button" onClick={() => go("settings")}><IcSettings size={15} />Settings</button>
        <button className={"mcc-foot-btn mcc-foot-profile" + (active === "user" ? " is-active" : "")} type="button" onClick={() => go("user")}>
          <McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={20} /><span>Ana Diaz</span>
        </button>
      </div>
    </aside>
  );
}

function MccNavTreeLed() {
  const [attention, setAttention] = React.useState(2);
  return (
    <div className="mcc-side-pad">
      <BvNavTree active="needs" attention={attention} />
      <div className="mcc-demo-row">
        <span>demo · the gate:</span>
        <button type="button" className={attention > 0 ? "is-on" : ""} onClick={() => setAttention(2)}>2 pending</button>
        <button type="button" className={attention === 0 ? "is-on" : ""} onClick={() => setAttention(0)}>all clear</button>
      </div>
      <p className="mcc-caption">Work-as-noun taken literally: the sidebar <b>is</b> the workspace tree, and the projections · History and Knowledge · pin above it as lenses, not siblings. The primary lens is <b>adaptive</b>: while work waits at your gate it reads <b>Needs you</b> with the count; the moment the queue clears it falls back to <b>Maestro</b> · one slot that always answers “where do I go first.” Settings and Feedback settle into the footer. <i>Toggle the gate above to watch the primary morph.</i></p>
    </div>
  );
}

Object.assign(window, {
  IcSearch, IcHistory, IcGraph, IcInbox, IcUsers,
  BvNav, NavTreeRows, AppTreeRows, NavBench, NavAutonomy, bvNavGrid,
  MccNavInventory, MccNavCanonical, MccNavFlat, MccNavRail, MccNavTreeLed,
});
