// Concepts canvas · the architect's attention.
// One operator, many projects, many loops. Three jobs compete for the
// center of the screen:
//   command · text in (the chat is the key input interface)
//   observe · the live feed of session loops
//   decide  · the gate: approvals, unblocks, the human calls
// Three frames, each making a different job primary. The other two never
// disappear · they become a rail, a dock, or a summon.

// ── Shared demo data ──────────────────────────────────────────────────────
const MCC_AT_LOOPS = [
  { kind: "live", title: "@genesis/projection", line: "Edit reducer.ts · 9 tests passed", t: "2h 14m" },
  { kind: "live", title: "bookkeeping", line: "Reconciling May invoices · cloud sandbox", t: "6m" },
  { kind: "gate", title: "hawthorne-core", line: "run/7c2f1a judged clean · awaiting your approve", t: "12m" },
  { kind: "warn", title: "hawthorne-db", line: "Stuck · needs a Linear API scope", t: "41m" },
  { kind: "standing", title: "nightly-digest", line: "Standing · nightly 02:00 · last run 31m", t: "8h" },
];

function MccLoopDot({ kind }) {
  if (kind === "live") return <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>;
  if (kind === "standing") return <span className="mc-chip-dot bv-dot--pulse" style={{ background: "var(--bv-info)" }}></span>;
  if (kind === "queued") return <span className="mc-chip-dot" style={{ background: "var(--bv-gray-400)" }}></span>;
  return <span className="mc-chip-dot" style={{ background: kind === "warn" ? "var(--bv-warning)" : "var(--bv-blue-accent)" }}></span>;
}

// The loops, as a rail · observation made peripheral but always present.
function MccLoopsRail() {
  return (
    <aside className="mcc-loops" data-screen-label="Loops rail">
      <div className="mcc-loops-head">
        <span className="mcc-panel-label">Loops</span>
        <span className="mcc-loops-count">2 live · 2 need you · 1 standing</span>
      </div>
      <div className="mcc-sess-list">
        {MCC_AT_LOOPS.map((l) => (
          <button key={l.title} className="mcc-sess" type="button">
            <MccLoopDot kind={l.kind} />
            <span className="mcc-sess-body">
              <span className="mcc-sess-label">{l.title}</span>
              <span className={"mcc-sess-meta" + (l.kind === "live" ? " mcc-caret" : "")}>{l.line}</span>
            </span>
            <span className="mcc-loops-t">{l.t}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}

// The docked plate · command demoted to one keystroke away, never gone.
function MccCmdDock({ placeholder = "Tell the workspace what's next · it routes through maestro…" }) {
  return (
    <div className="mcc-dock">
      <div className="mcc-dock-inner">
        <MccPromptPlate className="mcc-prompt--glass" placeholder={placeholder} />
      </div>
    </div>
  );
}

function MccAttnFrame({ children, screenLabel }) {
  const noop = () => {};
  return (
    <div className="mcc-fill">
      <div className="bv-app">
        <MccTcSidebar scope="root" setScope={noop} />
        <div className="bv-main" data-screen-label={screenLabel}>
          <McvTopBar theme="light" onToggleTheme={noop} onOpenMaestro={noop}
            onWake={noop} waking={false} canWake={true} onShowIdea={noop}
            counts={{ needYou: 1, stuck: 1 }} workers={["claude", "bookkeeper"]}
            wakes={MCC_TICK_WAKES} items={WK_ITEMS} onAttention={noop} onCommand={noop} />
          {children}
        </div>
      </div>
    </div>
  );
}

// ── S · The matrix · what each layout makes primary ──────────────────────
function MccAttnSchema() {
  const cell = (v) => (
    <span className={"mcc-mx-badge" + (v === "primary" ? " is-primary" : "")}>{v}</span>
  );
  const rows = [
    { name: "V1 · The console", sub: "chat-first", c: "primary", o: "rail", d: "inline in chat" },
    { name: "V2 · The tower", sub: "loops-first", c: "docked plate", o: "primary", d: "strip actions" },
    { name: "V3 · The gate", sub: "decisions-first", c: "docked plate", o: "rail", d: "primary" },
  ];
  return (
    <div className="mcc-pad">
      <div className="mcc-mx">
        <div className="mcc-mx-row mcc-mx-head">
          <span></span>
          <span>command · text in</span>
          <span>observe · the loops</span>
          <span>decide · the gate</span>
        </div>
        {rows.map((r) => (
          <div key={r.name} className="mcc-mx-row">
            <span className="mcc-mx-name">{r.name}<span className="mcc-mx-sub">{r.sub}</span></span>
            {cell(r.c)}{cell(r.o)}{cell(r.d)}
          </div>
        ))}
      </div>
      <p className="mcc-caption">The architect runs three loops, but a screen has one center. The honest move is to pick · and keep the other two one glance or one keystroke away. The philosophy leans V3: unsupervised hours are the score, so the human's screen should be sorted by the decisions only a human can make.</p>
    </div>
  );
}

// ── V1 · The console · the conversation is the control surface ───────────
function MccAttnConsole() {
  const w3 = WK_ITEMS.find((i) => i.id === "w3");
  return (
    <MccAttnFrame screenLabel="Console · chat-first">
      <div className="mcc-attn-row" style={{ gridTemplateColumns: "minmax(0, 1fr) 360px" }}>
        <div className="mcc-console" data-screen-label="Maestro console">
          <div className="bv-chat-feed mcc-console-feed">
            <div className="bv-msg bv-msg--assistant">Morning. Overnight: the nightly digest ran 31m unsupervised. Two things wait at your gate · transcripts (clean, 14 tests) and the Linear import (needs a scope from you).</div>
            <div className="bv-msg bv-msg--user">prioritize the API work, and show me what genesis is doing</div>
            <McRunCard msg={w3.chat[1]} />
            <div className="bv-msg bv-msg--assistant">Queue reordered · the relay handoff moves up. Genesis is live above: reducing the NDJSON stream to the phase machine, 9 tests green so far. Approve the transcripts branch when you have a minute and I'll build phase 2 on top of it tonight.</div>
          </div>
          <div className="bv-chat-composer-wrap" style={{ padding: "8px 20px 16px" }}>
            <MccPromptPlate className="mcc-prompt--glass" placeholder="Message maestro · dispatch, ask, steer…" />
          </div>
        </div>
        <MccLoopsRail />
      </div>
    </MccAttnFrame>
  );
}

// ── V2 · The tower · the loops are the screen ────────────────────────────
const MCC_AT_STRIPS = [
  { group: "Needs you", hint: "The only rows a human must touch", rows: [
    { kind: "gate", title: "Persist run transcripts", crumb: "hawthorne-core", line: "run/7c2f1a · judge passed · 14 tests", t: "12m", action: "Approve" },
    { kind: "warn", title: "Import Linear cycles", crumb: "hawthorne-db", line: "Worker paused · needs a Linear API scope", t: "41m", action: "Grant" },
  ]},
  { group: "Running", hint: "Live loops · narration updates in place", rows: [
    { kind: "live", title: "Reduce the NDJSON stream", crumb: "@genesis/projection", line: "Edit reducer.ts · bun test 9 passed", t: "2h 14m", live: true },
    { kind: "live", title: "Reconcile May invoices", crumb: "bookkeeping", line: "Matching 41 of 63 · cloud sandbox", t: "6m", live: true },
  ]},
  { group: "Holding", hint: "Maestro's queue · touches itself on the next tick", rows: [
    { kind: "queued", title: "Resume sessions (Phase 2)", crumb: "@genesis/projection", line: "Holding at capacity · 2/2 worktrees", t: "2h" },
    { kind: "queued", title: "Maestro relay, phase 1b", crumb: "hawthorne-engine", line: "First action attached · any session can pick it up", t: "1d" },
  ]},
];

function MccAttnTower() {
  return (
    <MccAttnFrame screenLabel="Tower · loops-first">
      <div className="mcc-tower" data-screen-label="Session strips">
        {MCC_AT_STRIPS.map((g) => (
          <React.Fragment key={g.group}>
            <div className="mcc-list-group">{g.group}<span className="mc-group-hint">{g.hint}</span></div>
            {g.rows.map((r) => (
              <div key={r.title} className="mcc-strip">
                <MccLoopDot kind={r.kind === "queued" ? "queued" : r.kind} />
                <span className="mcc-strip-title">{r.title}</span>
                <span className="mcc-strip-crumb">{r.crumb}</span>
                <span className={"mcc-strip-line" + (r.live ? " mcc-caret" : "")}>{r.line}</span>
                <span className="mcc-loops-t">{r.t}</span>
                {r.action
                  ? <DsButton size="sm">{r.action}</DsButton>
                  : <DsButton size="sm" variant="secondary">Open</DsButton>}
              </div>
            ))}
          </React.Fragment>
        ))}
      </div>
      <MccCmdDock />
    </MccAttnFrame>
  );
}

// ── V3 · The gate · sorted by what only a human can do ───────────────────
function MccAttnGate() {
  return (
    <MccAttnFrame screenLabel="Gate · decisions-first">
      <div className="mcc-attn-row" style={{ gridTemplateColumns: "minmax(0, 1fr) 360px" }}>
        <div className="mcc-gatecol" data-screen-label="Decision queue">
          <div className="mcc-gate-head">
            <span className="mcc-plane-title">Your gate</span>
            <span className="mcc-plane-sub">2 decisions · everything else is maestro's problem</span>
          </div>
          <div className="bv-card mcc-gatecard">
            <div className="mc-card-top">
              <span className="mc-breadcrumb"><b>hawthorne</b> › hawthorne-core</span>
              <span className="mc-card-time">12m</span>
            </div>
            <div className="mc-card-title">Persist run transcripts on the Run record</div>
            <div className="mcc-look-ran">ran <b>2h 14m unsupervised</b> · 41 events · judge passed · 14 tests added</div>
            <ul className="mcc-look-list">
              <li>Persisted on the Run record, not the session · survives restarts</li>
              <li>Replay covered by tests instead of snapshotting live state</li>
            </ul>
            <div className="mc-detail-actions">
              <DsButton size="sm"><IcCheck size={16} />Approve</DsButton>
              <DsButton size="sm" variant="secondary">Send back</DsButton>
              <span className="mcc-look-timer">a 90-second look</span>
            </div>
          </div>
          <div className="bv-card mcc-gatecard">
            <div className="mc-card-top">
              <span className="mc-breadcrumb"><b>hawthorne</b> › hawthorne-db</span>
              <span className="mc-card-time">41m</span>
            </div>
            <div className="mc-card-title">Import Linear cycles into the object model</div>
            <div className="mcc-look-ran">worker paused · <b>needs a Linear API scope</b> before the import can run</div>
            <div className="mc-detail-actions">
              <DsButton size="sm">Grant access</DsButton>
              <DsButton size="sm" variant="secondary">Park it</DsButton>
              <span className="mcc-look-timer">unblocks 1 worker</span>
            </div>
          </div>
          <div className="mcc-allclear">
            <IcCheck size={14} />
            Nothing else needs you · maestro holds 2 live loops and the queue · next tick 13m
          </div>
        </div>
        <MccLoopsRail />
      </div>
      <MccCmdDock placeholder="Anything beyond approve/deny · say it, maestro routes it…" />
    </MccAttnFrame>
  );
}

Object.assign(window, { MccAttnSchema, MccAttnConsole, MccAttnTower, MccAttnGate, MccLoopsRail, MccCmdDock, MccLoopDot, MCC_AT_LOOPS });
