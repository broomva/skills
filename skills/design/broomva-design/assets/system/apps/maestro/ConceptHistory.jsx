// Concept · the History page. The full list of sessions: yours AND the loop's.
// Philosophy: a session is a projection of work, so History is the one place the
// session-list inheritance belongs. One live frame, four organizing axes
// (day · work · agent · lineage) + a you/autonomous filter · the axes ARE the
// variations. Built on the canonical BvNav so the chrome matches the app.

// agent → avatar colour
const HIST_AGENT = {
  maestro:    { color: "var(--bv-info)",            face: "orch" },
  claude:     { color: "var(--bv-blue)" },
  bookkeeper: { color: "var(--bv-purple, #7c6cf0)" },
  scout:      { color: "var(--bv-gray-500)" },
  you:        { color: "var(--bv-gray-600)" },
};

// state → dot tone
const HIST_STATE = {
  live:    { color: "var(--bv-info)",        plain: "running" },
  done:    { color: "var(--bv-success)",     plain: "done" },
  halt:    { color: "var(--bv-blue-accent)", plain: "needed you" },
  blocked: { color: "var(--bv-warning)",     plain: "stuck" },
};

const HIST_SESSIONS = [
  { id: "s1", title: "Implement resumable sessions", kind: "auto", state: "live", agent: "claude", parent: "maestro",
    folder: "hawthorne / hawthorne-core", dur: "2h 14m", unsup: true, events: 41, day: "Today", time: "2m" },
  { id: "s2", title: "Review the API design", kind: "you", state: "halt", agent: "claude", parent: "you",
    folder: "hawthorne / hawthorne-core", dur: "halted · 2 looks", unsup: false, events: 38, day: "Today", time: "18m" },
  { id: "s3", title: "Reconcile May invoices", kind: "auto", state: "live", agent: "bookkeeper", parent: "maestro",
    folder: "ops / bookkeeping", dur: "1h 02m", unsup: true, events: 27, day: "Today", time: "6m", where: "cloud sandbox" },
  { id: "s4", title: "Survey prior art on resumability", kind: "auto", state: "done", agent: "scout", parent: "claude", parentSession: "s1",
    folder: "hawthorne / hawthorne-core", dur: "47m", unsup: true, events: 61, day: "Today", time: "1h" },
  { id: "s5", title: "What's blocking the launch?", kind: "you", state: "done", agent: "claude", parent: "you",
    folder: "hawthorne", dur: "4m", unsup: false, events: 12, day: "Today", time: "1h" },
  { id: "s6", title: "Import Linear cycles into the store", kind: "auto", state: "blocked", agent: "claude", parent: "maestro",
    folder: "hawthorne / hawthorne-db", dur: "41m · missing scope", unsup: false, events: 19, day: "Today", time: "41m" },
  { id: "s7", title: "Nightly digest", kind: "auto", state: "done", agent: "maestro", parent: "maestro",
    folder: "ops / nightly-digest", dur: "31m", unsup: true, events: 33, day: "Today", time: "02:00", routine: true },
  { id: "s8", title: "Morning briefing", kind: "auto", state: "done", agent: "maestro", parent: "maestro",
    folder: "meta · across workspaces", dur: "8m", unsup: true, events: 14, day: "Today", time: "07:30", routine: true },
  { id: "s9", title: "Draft the relay protocol spec", kind: "you", state: "done", agent: "claude", parent: "you",
    folder: "hawthorne / hawthorne-core", dur: "22m", unsup: false, events: 22, day: "Yesterday", time: "16:10" },
  { id: "s10", title: "Reduce the NDJSON stream to a phase machine", kind: "you", state: "done", agent: "claude", parent: "you",
    folder: "genesis / projection", dur: "1h 18m", unsup: false, events: 54, day: "Yesterday", time: "14:02" },
  { id: "s11", title: "Close the single-stage execution loop (M1b)", kind: "auto", state: "done", agent: "claude", parent: "maestro",
    folder: "hawthorne / hawthorne-engine", dur: "3h 50m", unsup: true, events: 88, day: "Yesterday", time: "11:20" },
  { id: "s12", title: "Linear import · credential retry", kind: "auto", state: "done", agent: "maestro", parent: "maestro",
    folder: "ops", dur: "3m", unsup: true, events: 6, day: "Mon", time: "09:14", routine: true },
];

function HistDot({ s }) {
  if (s.state === "live") return <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>;
  return <span className="mc-chip-dot" style={{ width: 9, height: 9, background: HIST_STATE[s.state].color }}></span>;
}

function HistRow({ s, selected, onSelect, depth = 0, showFolder = true, showAgent = true }) {
  return (
    <button type="button" className={"mcc-hrow" + (selected ? " is-sel" : "")}
      style={{ paddingLeft: 16 + depth * 24 }} onClick={() => onSelect(s.id)}>
      {depth > 0 && <span className="mcc-lin-elbow" style={{ marginRight: 2 }}></span>}
      <HistDot s={s} />
      <span className="mcc-hrow-body">
        <span className="mcc-hrow-title">{s.title}</span>
        <span className="mcc-hrow-meta">
          {showAgent && <span className="mcc-hrow-who">{s.parent === s.agent ? s.agent : s.parent + " → " + s.agent}</span>}
          {showFolder && <span className="mcc-hrow-crumb">{s.folder}</span>}
          <span className="mcc-hrow-dur">{s.unsup ? s.dur + " unsupervised" : s.dur} · {s.events} events</span>
        </span>
      </span>
      {s.routine ? <span className="mc-receipt">routine</span> : <span className={"mcc-hrow-kind mcc-hrow-kind--" + s.kind}>{s.kind === "you" ? "you" : "loop"}</span>}
      <span className="mcc-hrow-time">{s.time}</span>
    </button>
  );
}

function HistGroupLabel({ icon, children, count }) {
  return (
    <div className="mcc-hgroup">
      {icon}<span>{children}</span>{count != null && <span className="mcc-hgroup-count">{count}</span>}
    </div>
  );
}

function MccHistory({ onOpenView, theme, onToggleTheme }) {
  const noop = () => {};
  const [axis, setAxis] = React.useState("day");
  const [filter, setFilter] = React.useState("all");
  const [sel, setSel] = React.useState("s1");
  const [qq, setQq] = React.useState("");

  const rows = HIST_SESSIONS.filter((s) =>
    (filter === "all" || s.kind === filter) &&
    (!qq.trim() || (s.title + " " + s.folder + " " + s.agent).toLowerCase().includes(qq.trim().toLowerCase())));

  const onSelect = setSel;
  let body;

  if (axis === "day") {
    const days = ["Today", "Yesterday", "Mon"];
    body = days.map((d) => {
      const list = rows.filter((s) => s.day === d);
      if (!list.length) return null;
      return (
        <React.Fragment key={d}>
          <HistGroupLabel count={list.length}>{d}</HistGroupLabel>
          {list.map((s) => <HistRow key={s.id} s={s} selected={s.id === sel} onSelect={onSelect} />)}
        </React.Fragment>
      );
    });
  } else if (axis === "work") {
    const folders = [...new Set(rows.map((s) => s.folder))];
    body = folders.map((f) => {
      const list = rows.filter((s) => s.folder === f);
      return (
        <React.Fragment key={f}>
          <HistGroupLabel icon={<IcFolder size={13} />} count={list.length}>{f}</HistGroupLabel>
          {list.map((s) => <HistRow key={s.id} s={s} selected={s.id === sel} onSelect={onSelect} showFolder={false} />)}
        </React.Fragment>
      );
    });
  } else if (axis === "agent") {
    const order = ["maestro", "claude", "bookkeeper", "scout"];
    body = order.map((ag) => {
      const list = rows.filter((s) => s.agent === ag);
      if (!list.length) return null;
      const c = HIST_AGENT[ag].color;
      return (
        <React.Fragment key={ag}>
          <HistGroupLabel count={list.length}
            icon={ag === "maestro"
              ? <span className="mcc-dot-comet" style={{ width: 14, height: 14 }}><span className="mcc-dot-comet-core"></span></span>
              : <McAvatar name={ag} color={c} size={17} />}>
            {ag === "maestro" ? "maestro · the loop" : ag}
          </HistGroupLabel>
          {list.map((s) => <HistRow key={s.id} s={s} selected={s.id === sel} onSelect={onSelect} showAgent={false} />)}
        </React.Fragment>
      );
    });
  } else { // lineage
    // two roots: the loop (maestro) and you. Build parent→children.
    const renderTree = (rootLabel, rootIcon, predicate) => {
      const roots = rows.filter(predicate);
      if (!roots.length) return null;
      return (
        <React.Fragment key={rootLabel}>
          <HistGroupLabel icon={rootIcon}>{rootLabel}</HistGroupLabel>
          {roots.map((s) => (
            <React.Fragment key={s.id}>
              <HistRow s={s} selected={s.id === sel} onSelect={onSelect} showAgent={true} />
              {rows.filter((c) => c.parentSession === s.id).map((c) =>
                <HistRow key={c.id} s={c} selected={c.id === sel} onSelect={onSelect} depth={1} showAgent={true} />)}
            </React.Fragment>
          ))}
        </React.Fragment>
      );
    };
    body = (
      <>
        {renderTree("The loop · maestro spawned", <span className="mcc-dot-comet" style={{ width: 14, height: 14 }}><span className="mcc-dot-comet-core"></span></span>,
          (s) => s.parent === "maestro" && s.agent !== "scout")}
        {renderTree("You started", <McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={17} />,
          (s) => s.parent === "you")}
      </>
    );
  }

  const axes = [["day", "By day"], ["work", "By work"], ["agent", "By agent"], ["lineage", "By lineage"]];
  const filters = [["all", "All"], ["you", "You"], ["auto", "Autonomous"]];

  return (
    <div className="mcc-fill">
      <div className="bv-app" style={{ gridTemplateColumns: bvNavGrid() }}>
        <BvNavTree active="history" inApp onNav={onOpenView} />
        <div className="bv-main">
          <McvTopBar theme={theme} onToggleTheme={onToggleTheme || noop} onOpenMaestro={() => onOpenView && onOpenView("app")}
            onWake={noop} waking={false} canWake={true} onShowIdea={noop}
            counts={{ needYou: 1, stuck: 1 }} workers={["claude", "bookkeeper"]}
            wakes={MCC_TICK_WAKES} items={WK_ITEMS} onAttention={() => onOpenView && onOpenView("app")}
            onCommand={() => window.dispatchEvent(new CustomEvent("bv:command-open"))} />
          <div className="mcc-hist" data-screen-label="History page">
            <div className="mcc-hist-bar">
              <div className="mcc-hsearch">
                <IcSearch size={14} />
                <input value={qq} onChange={(e) => setQq(e.target.value)} placeholder="Search sessions…" />
              </div>
              <DsSegmented value={axis} onChange={setAxis}
                options={axes.map(([id, label]) => ({ value: id, label }))} />
              <div className="mc-chips" style={{ marginLeft: "auto" }}>
                {filters.map(([id, label]) => (
                  <button key={id} type="button" className={"mc-chip" + (filter === id ? " is-active" : "")} onClick={() => setFilter(id)}>{label}</button>
                ))}
              </div>
            </div>
            <div className="mcc-hist-list">
              {body}
              <div className="mcc-hist-end">312 sessions · the conversation bridge writes each one back as an Obsidian doc</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── H0 · Session anatomy ──────────────────────────────────────────────────
function MccHistAnatomy() {
  const s = HIST_SESSIONS[0];
  return (
    <div className="mcc-pad" style={{ gap: 14 }}>
      <div className="mcc-anat">
        <HistRow s={s} selected={true} onSelect={() => {}} />
      </div>
      <div className="mcc-anat-grid">
        <div className="mcc-anat-cell"><b>The dot</b><span>state at a glance · the tidepool for live, a flat dot for done · needed-you · stuck.</span></div>
        <div className="mcc-anat-cell"><b>Lineage</b><span>who → whom. <code>maestro → claude</code> reads the spawn, not just the worker.</span></div>
        <div className="mcc-anat-cell"><b>The folder</b><span>the work it touched · a session is a projection <i>of</i> a folder, never free-floating.</span></div>
        <div className="mcc-anat-cell"><b>Unsupervised</b><span>the number that matters: how long it ran before a human had to look.</span></div>
        <div className="mcc-anat-cell"><b>you / loop</b><span>did you start it, or did the orchestrator? The filter toggles between them.</span></div>
      </div>
      <p className="mcc-caption">Every row encodes the same five facts in the same places, so the eye learns them once and the axis switcher only re-groups · it never re-teaches. Halts read accent-blue, not red: needing you is a gate, not a failure.</p>
    </div>
  );
}

Object.assign(window, { MccHistory, MccHistAnatomy, HIST_SESSIONS, HIST_AGENT, HIST_STATE });
