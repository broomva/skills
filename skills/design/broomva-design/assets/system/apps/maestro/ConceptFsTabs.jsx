// Concepts canvas · the filesystem surfaces: tabs + the file pane.
// The workspace root IS a location on the FS, but nothing in the UI lets
// you walk it as files. Two placements for the missing pair (a tab strip
// where chats live and files open, plus a browsable file pane):
//   A · inside the right panel · the session keeps its geography
//   B · in the chrome · app-level tabs under the header, FS pane at the
//       layout's right edge, the session panel untouched.

const IcFtChev = (p) => <McIcon {...p}><path d="m9 18 6-6-6-6"></path></McIcon>;

// ── The documents · every file is a contract or a receipt ────────────────
const MCC_FS_DOCS = {
  "broomva.md": {
    crumb: "~ / Broomva / broomva.md",
    title: "Broomva · the workspace contract",
    chips: ["kind: workspace", "runner: claude", "gate: human-approve"],
    body: [
      "The meta-workspace. Every folder below this file is work at some scale; what's written here cascades down the tree until a deeper contract overrides it.",
      { list: ["Defaults: worktree-per-run, judge on every exit", "Budgets are granted at spawn · never ambient", "Receipts land beside the work, sessions in the engine room"] },
    ],
  },
  "hawthorne.md": {
    crumb: "~ / Broomva / hawthorne / hawthorne.md",
    title: "Hawthorne · durable agent infrastructure",
    chips: ["kind: initiative", "owner: you", "budget: 24h/wk unsupervised"],
    body: [
      "North star: an agent session you can leave overnight and trust in the morning. The unsupervised hour is the unit of progress.",
      { list: ["Current focus: persist run transcripts (at the gate)", "Unblock the Linear import · needs an API scope", "Spec the TunnelRunner relay protocol (V2)"] },
    ],
  },
  "spec.md": {
    crumb: "~ / Broomva / hawthorne / hawthorne-core / spec.md",
    title: "Persist run transcripts on the Run record",
    chips: ["kind: project", "owner: maestro", "budget: 8h unsupervised", "gate: human-approve"],
    body: [
      "Reviews should never need the live session. Persist the full transcript on each Run so any session · yours or a worker's · can replay it cold.",
      { list: ["Persist on the Run record, not the session · survives worker restarts", "Replay covered by 14 tests instead of snapshotting live state", "Compression deferred · transcripts stay small until multi-day runs land"] },
    ],
  },
  "prior-art.md": {
    crumb: "… / hawthorne-core / notes / prior-art.md",
    title: "Survey · resumable sessions in OSS agents",
    chips: ["written by: scout", "47m unsupervised"],
    body: [
      "Six frameworks surveyed. The durable pattern everywhere: event-sourced transcripts plus idempotent tool replay · snapshots rot, logs don't.",
      { list: ["Replay beats snapshot in all six", "Fork-at-event needs stable event ids from day one", "Folded into the reducer design by claude"] },
    ],
  },
  "api-decisions.md": {
    crumb: "… / hawthorne-core / notes / api-decisions.md",
    title: "Resume API · decisions",
    chips: ["decided with: you", "2 looks"],
    body: [
      "Two surfaces only. resume(sessionId) rehydrates from the persisted transcript; fork(sessionId, at) branches a new session at any event.",
      { list: ["Forks share the parent's budget, capped · your call", "No partial rehydration: all or nothing", "Fork is the undo · there is no rewind"] },
    ],
  },
  "run-7c2f1a.md": {
    crumb: "… / hawthorne-core / runs / run-7c2f1a.md",
    title: "Receipt · run/7c2f1a",
    chips: ["judge: checks passed", "14 tests added", "2h 14m unsupervised"],
    body: [
      "Ran to the gate. The branch is the receipt · the worktree was reclaimed after the run; this file is what the judge saw.",
      { list: ["41 events · 2 looks requested, 0 needed", "Branch run/7c2f1a awaiting your approve", "Transcript persisted on the Run record (dogfood)"] },
    ],
  },
};

function MccFsDoc({ path }) {
  const d = MCC_FS_DOCS[path];
  if (!d) return null;
  return (
    <div className="mcc-doc">
      <div className="mcc-doc-inner">
        <span className="mcc-doc-crumb">{d.crumb}</span>
        <h1 className="mcc-doc-title">{d.title}</h1>
        <div className="mcc-fm-chips">
          {d.chips.map((c) => <span key={c} className="mc-receipt">{c}</span>)}
        </div>
        {d.body.map((b, i) =>
          typeof b === "string"
            ? <p key={i} className="mcc-doc-p">{b}</p>
            : <ul key={i} className="mcc-doc-list">{b.list.map((l) => <li key={l}>{l}</li>)}</ul>
        )}
      </div>
    </div>
  );
}

// ── The file pane ─────────────────────────────────────────────────────────
function MccFilePane({ entries, openPath, onOpen, label, location, worktree }) {
  return (
    <div className="mcc-ftree" data-screen-label="File pane">
      {label && <div className="mcc-ftree-label">{label}</div>}
      {location && (
        <div className="mcc-ftree-loc">
          <span className="mcc-ftree-loc-path">{location}</span>
          {worktree && <span className="mc-receipt">{worktree}</span>}
        </div>
      )}
      {entries.map((e) => (
        <button key={e.path || e.name + e.depth} type="button"
          className={"mcc-ftree-row" + (e.path && e.path === openPath ? " is-active" : "") + (e.path ? "" : " is-folder")}
          style={{ paddingLeft: 8 + e.depth * 14 }}
          onClick={e.path ? () => onOpen(e.path) : undefined}>
          {e.kind === "folder"
            ? <IcFolderOpen size={13} />
            : <IcDoc size={13} />}
          <span className="mcc-ftree-name">{e.name}</span>
          {e.live && <span className="mcc-dot-tide" style={{ width: 11, height: 11, marginLeft: "auto" }}></span>}
        </button>
      ))}
    </div>
  );
}

const MCC_FT_CORE = [
  { name: "spec.md", path: "spec.md", depth: 0, kind: "file" },
  { name: "notes", depth: 0, kind: "folder" },
  { name: "prior-art.md", path: "prior-art.md", depth: 1, kind: "file" },
  { name: "api-decisions.md", path: "api-decisions.md", depth: 1, kind: "file" },
  { name: "runs", depth: 0, kind: "folder" },
  { name: "run-7c2f1a.md", path: "run-7c2f1a.md", depth: 1, kind: "file" },
];

const MCC_FT_ROOT = [
  { name: "broomva.md", path: "broomva.md", depth: 0, kind: "file" },
  { name: "hawthorne", depth: 0, kind: "folder" },
  { name: "hawthorne.md", path: "hawthorne.md", depth: 1, kind: "file" },
  { name: "hawthorne-core", depth: 1, kind: "folder" },
  { name: "spec.md", path: "spec.md", depth: 2, kind: "file" },
  { name: "prior-art.md", path: "prior-art.md", depth: 2, kind: "file" },
  { name: "api-decisions.md", path: "api-decisions.md", depth: 2, kind: "file" },
  { name: "run-7c2f1a.md", path: "run-7c2f1a.md", depth: 2, kind: "file" },
  { name: "hawthorne-db", depth: 1, kind: "folder" },
  { name: "genesis", depth: 0, kind: "folder", live: true },
  { name: "ops", depth: 0, kind: "folder", live: true },
];

// ── The tab strip ─────────────────────────────────────────────────────────
function MccFTabs({ tabs, act, setAct, onClose, onNew }) {
  return (
    <div className="mcc-ftabs" data-screen-label="Tab strip">
      {tabs.map((t, i) => (
        <button key={t.key} type="button"
          className={"mcc-ftab" + (i === act ? " is-active" : "")}
          onClick={() => setAct(i)} title={t.title}>
          {t.glyph}
          <span className="mcc-ftab-name">{t.label}</span>
          {t.closable && (
            <span className="mcc-ftab-x" role="button" aria-label={"Close " + t.label}
              onClick={(e) => { e.stopPropagation(); onClose(i); }}>
              <IcX size={11} />
            </span>
          )}
        </button>
      ))}
      <button type="button" className="mcc-prompt-iconbtn" style={{ width: 26, height: 26 }}
        aria-label="New chat" title="New chat" onClick={onNew}>
        <IcxPlus size={14} />
      </button>
    </div>
  );
}

// Tab-state helper shared by both frames.
function useMccFTabs(baseTabs) {
  const [open, setOpen] = React.useState([]);   // file paths + chat ids
  const [act, setAct] = React.useState(0);
  const tabs = [
    ...baseTabs,
    ...open.map((o) =>
      o.kind === "file"
        ? { key: o.path, kind: "file", path: o.path, label: o.path.split("/").pop(), glyph: <IcDoc size={13} />, closable: true, title: MCC_FS_DOCS[o.path] ? MCC_FS_DOCS[o.path].crumb : o.path }
        : { key: o.id, kind: "chat", label: "new chat", glyph: <span className="mc-chip-dot bv-dot--pulse" style={{ background: "var(--bv-info)" }}></span>, closable: true, title: "A fresh session in this folder" }
    ),
  ];
  const openFile = (path) => {
    const idx = tabs.findIndex((t) => t.kind === "file" && t.path === path);
    if (idx >= 0) { setAct(idx); return; }
    setOpen((o) => [...o, { kind: "file", path }]);
    setAct(tabs.length);
  };
  const newChat = () => {
    setOpen((o) => [...o, { kind: "chat", id: "chat-" + Date.now() }]);
    setAct(tabs.length);
  };
  const close = (i) => {
    const oi = i - baseTabs.length;
    if (oi < 0) return;
    setOpen((o) => o.filter((_, j) => j !== oi));
    setAct((a) => (a === i ? Math.max(0, i - 1) : a > i ? a - 1 : a));
  };
  return { tabs, act, setAct, openFile, newChat, close };
}

function MccFsNewChat() {
  return (
    <div className="mcc-newchat">
      <div className="mcc-newchat-inner">
        <span className="bv-greeting-title">A fresh session in this folder</span>
        <span className="bv-greeting-sub">It inherits the contract · budget, gate, scope · from the folder it starts in.</span>
        <MccPromptPlate className="mcc-prompt--glass" placeholder="Tell this folder what's next…" />
      </div>
    </div>
  );
}

// ── A · Tabs inside the right panel ──────────────────────────────────────
function MccFsTabsPanel() {
  const noop = () => {};
  const w1 = WK_ITEMS.find((i) => i.id === "w1");
  const base = [{
    key: "chat", kind: "chat-w1", label: "persist run transcripts", closable: false,
    glyph: <span className="mc-chip-dot" style={{ background: "var(--bv-blue-accent)" }}></span>,
    title: "The work item's session",
  }];
  const { tabs, act, setAct, openFile, newChat, close } = useMccFTabs(base);
  const cur = tabs[act] || tabs[0];
  return (
    <div className="mcc-fill">
      <div className="bv-app">
        <MccTcSidebar scope="core" setScope={noop} />
        <div className="bv-main">
          <McvTopBar theme="light" onToggleTheme={noop} onOpenMaestro={noop}
            onWake={noop} waking={false} canWake={true} onShowIdea={noop}
            counts={{ needYou: 1, stuck: 1 }} workers={["claude", "bookkeeper"]}
            wakes={MCC_TICK_WAKES} items={WK_ITEMS} onAttention={noop} onCommand={noop} />
          <div className="mcc-merged-row" style={{ gridTemplateColumns: "minmax(0, 1fr) 680px" }}>
            <MccTcPlane scope="core" />
            <aside className="mcc-live-panel" data-screen-label="Tabbed panel + file pane">
              <div className="mcc-panel-head" style={{ paddingBottom: 10 }}>
                <span className="mc-detail-breadcrumb">hawthorne / hawthorne-core</span>
              </div>
              <MccFTabs tabs={tabs} act={act} setAct={setAct} onClose={close} onNew={newChat} />
              <div className="mcc-ftab-row">
                <div className="mcc-ftab-main">
                  {cur.kind === "chat-w1" && <McChat item={w1} extra={{}} typing={false} onSend={noop} />}
                  {cur.kind === "file" && <MccFsDoc path={cur.path} />}
                  {cur.kind === "chat" && <MccFsNewChat />}
                </div>
                <MccFilePane entries={MCC_FT_CORE} label="hawthorne-core/"
                  openPath={cur.kind === "file" ? cur.path : null} onOpen={openFile} />
              </div>
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── B · Tabs in the chrome, FS pane at the layout edge ───────────────────
function MccFsTabsChrome() {
  const noop = () => {};
  const base = [{
    key: "mc", kind: "mc", label: "Maestro", closable: false,
    glyph: <IcBoard size={13} />, title: "The plane · work grouped by attention",
  }];
  const { tabs, act, setAct, openFile, newChat, close } = useMccFTabs(base);
  const cur = tabs[act] || tabs[0];
  return (
    <div className="mcc-fill">
      <div className="bv-app">
        <MccTcSidebar scope="core" setScope={noop} />
        <div className="bv-main">
          <McvTopBar theme="light" onToggleTheme={noop} onOpenMaestro={noop}
            onWake={noop} waking={false} canWake={true} onShowIdea={noop}
            counts={{ needYou: 1, stuck: 1 }} workers={["claude", "bookkeeper"]}
            wakes={MCC_TICK_WAKES} items={WK_ITEMS} onAttention={noop} onCommand={noop} />
          <MccFTabs tabs={tabs} act={act} setAct={setAct} onClose={close} onNew={newChat} />
          <div className="mcc-fsrow">
            <div className="mcc-fsmain">
              {cur.kind === "mc" && (
                <div className="mcc-merged-row" style={{ gridTemplateColumns: "minmax(0, 1fr) 400px" }}>
                  <MccTcPlane scope="core" />
                  <MccTcPanel scope="core" setScope={noop} />
                </div>
              )}
              {cur.kind === "file" && <MccFsDoc path={cur.path} />}
              {cur.kind === "chat" && <MccFsNewChat />}
            </div>
            <MccFilePane entries={MCC_FT_ROOT} label="Broomva/"
              openPath={cur.kind === "file" ? cur.path : null} onOpen={openFile} />
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MccFsTabsPanel, MccFsTabsChrome, MccFilePane, MccFsDoc, MccFsNewChat, MccFTabs, useMccFTabs, MCC_FT_ROOT, MCC_FT_CORE });
