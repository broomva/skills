// Maestro v3 · the work planes: feed / board / list, switchable.
// Running work wears the Undertow (contained halo + tidepool dot) · the one
// running treatment. The border comet is retired.

const MCV_UNDERTOW_DOT = (
  <span className="mcc-dot-tide"></span>
);

// A work card that wears the running signal.
function McvLiveCard({ item, selected, onSelect, vocab, receipts }) {
  if (item.state !== "running") {
    return <McWorkCard item={item} selected={selected} onSelect={onSelect} vocab={vocab} receipts={receipts} />;
  }
  return (
    <div className="mcc-undertow-halo mcc-halo--tidalnebula">
      <span className="mcc-halo-spin-layer"></span>
      <McWorkCard item={item} selected={selected} onSelect={onSelect} vocab={vocab} receipts={receipts}
        glow={false} dot={MCV_UNDERTOW_DOT} />
    </div>
  );
}

function McvGroups({ items, filter }) {
  const groups = WK_GROUP_ORDER
    .map((state) => ({ state, items: items.filter((i) => i.state === state) }))
    .filter((g) => g.items.length > 0);
  return filter ? groups.filter((g) => g.state === filter) : groups;
}

// ── Feed ──────────────────────────────────────────────────────────────────
function McvPlaneFeed({ items, selectedId, onSelect, vocab, receipts, signal, filter, onFilter, hideFilters }) {
  const groups = WK_GROUP_ORDER
    .map((state) => ({ state, items: items.filter((i) => i.state === state) }))
    .filter((g) => g.items.length > 0);
  const visible = filter ? groups.filter((g) => g.state === filter) : groups;
  return (
    <div className="mcc-plane-feed">
      {!hideFilters && (
        <div className="mc-chips">
          <button type="button" className={"mc-chip" + (filter === null ? " is-active" : "")}
            onClick={() => onFilter(null)}>All</button>
          {groups.map((g) => {
            const meta = WK_STATES[g.state];
            return (
              <button key={g.state} type="button"
                className={"mc-chip" + (filter === g.state ? " is-active" : "")}
                onClick={() => onFilter(filter === g.state ? null : g.state)}>
                <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>
                {vocab === "system" ? meta.system : meta.plain}
                <span className="mc-chip-count">{g.items.length}</span>
              </button>
            );
          })}
        </div>
      )}
      {visible.map((g) => {
        const meta = WK_STATES[g.state];
        return (
          <section key={g.state} className="mc-group" data-screen-label={"Group: " + meta.plain}>
            <div className="mc-group-header">
              <span className="mc-group-label">
                <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>
                {vocab === "system" ? meta.system : meta.plain}
              </span>
              <span className="mc-group-count">{g.items.length}</span>
              <span className="mc-group-hint">{WK_GROUP_HINTS[g.state]}</span>
            </div>
            <div className="mc-group-cards">
              {g.items.map((item) => (
                <McvLiveCard key={item.id} item={item} selected={item.id === selectedId}
                  onSelect={onSelect} vocab={vocab} receipts={receipts} signal={signal} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

// ── Board ─────────────────────────────────────────────────────────────────
const MCV_COLS = [
  { label: "Queued", states: ["proposed", "queued"], tone: "muted", hint: "Specs and next ticks" },
  { label: "Running", states: ["running"], tone: "active", hint: "Live in worktrees" },
  { label: "Needs you", states: ["review", "blocked"], tone: "review", hint: "At your gate or stuck" },
  { label: "Done", states: ["done"], tone: "done", hint: "The branch is the receipt" },
];

function McvPlaneBoard({ items, selectedId, onSelect, vocab, receipts, signal }) {
  return (
    <div className="mcc-plane-board">
      {MCV_COLS.map((col) => {
        const colItems = items.filter((i) => col.states.includes(i.state));
        return (
          <div key={col.label} className="mcc-col" data-screen-label={"Column: " + col.label}>
            <div className="mcc-col-header">
              <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[col.tone] }}></span>
              {col.label}
              <span className="mcc-col-count">{colItems.length}</span>
            </div>
            <div className="mcc-col-hint">{col.hint}</div>
            <div className="mcc-col-body">
              {colItems.map((item) => (
                <McvLiveCard key={item.id} item={item} selected={item.id === selectedId}
                  onSelect={onSelect} vocab={vocab} receipts={receipts} signal={signal} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── List ──────────────────────────────────────────────────────────────────
function McvPlaneList({ items, selectedId, onSelect, vocab, receipts }) {
  const groups = WK_GROUP_ORDER
    .map((state) => ({ state, items: items.filter((i) => i.state === state) }))
    .filter((g) => g.items.length > 0);
  return (
    <div className="mcc-plane-list">
      {groups.map((g) => {
        const meta = WK_STATES[g.state];
        return (
          <React.Fragment key={g.state}>
            <div className="mcc-list-group">
              <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>
              {vocab === "system" ? meta.system : meta.plain}
              <span className="mc-group-count">{g.items.length}</span>
              <span className="mc-group-hint">{WK_GROUP_HINTS[g.state]}</span>
            </div>
            {g.items.map((item) => {
              const init = WK_INITIATIVES.find((i) => i.id === item.initiative);
              return (
                <button key={item.id} type="button"
                  className={"mcc-rowitem" + (item.id === selectedId ? " is-selected" : "")}
                  onClick={() => onSelect(item.id)}>
                  {item.state === "running"
                    ? MCV_UNDERTOW_DOT
                    : <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>}
                  <span className="mcc-row-title">{item.title}</span>
                  <span className="mcc-row-crumb">{init ? init.name : ""} › {item.project}</span>
                  {receipts && item.run ? <span className="mc-receipt">{item.run}</span> : <span></span>}
                  <span className="mcc-row-time">{item.time}</span>
                </button>
              );
            })}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── View toggle ───────────────────────────────────────────────────────────
const MCV_VIEWS = [
  { id: "feed", label: "Feed", icon: IcList },
  { id: "board", label: "Board", icon: IcBoard },
  { id: "list", label: "List", icon: IcSeam },
];

function McvViewToggle({ view, onView }) {
  return (
    <div className="mcc-seg" role="tablist">
      {MCV_VIEWS.map((v) => (
        <button key={v.id} type="button" role="tab" aria-selected={view === v.id}
          className={"mcc-seg-btn" + (view === v.id ? " is-active" : "")}
          onClick={() => onView(v.id)}>
          <v.icon size={13} /><span className="mcc-seg-label">{v.label}</span>
        </button>
      ))}
    </div>
  );
}

Object.assign(window, { McvLiveCard, McvPlaneFeed, McvPlaneBoard, McvPlaneList, McvViewToggle, MCV_UNDERTOW_DOT });
