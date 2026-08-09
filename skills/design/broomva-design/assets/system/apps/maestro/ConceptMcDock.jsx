// Concepts canvas · the mission-control dock, restyled.
// The docked column in the maestro-loop frame was a flat list; these
// variations keep the FEED's vocabulary instead · group headers with tone
// dots, real work cards, the Undertow on running work. M1 is wired into
// the synthesis frames.

const MCC_MD_LIVELINE = {
  w3: "Edit reducer.ts · bun test 9 passed",
  w4: "Matching 41 of 63 · cloud sandbox",
};

const mccMdItems = (ids) => ids.map((id) => WK_ITEMS.find((i) => i.id === id));

// ── The feed body · group headers + cards, dock-compacted ────────────────
function MccDockFeedBody({ filter }) {
  const noop = () => {};
  const groups = [
    { state: "review", items: mccMdItems(["w1"]), kind: "attention" },
    { state: "blocked", items: mccMdItems(["w2"]), kind: "attention" },
    { state: "running", items: mccMdItems(["w3", "w4"]), kind: "running" },
  ].filter((g) => !filter || g.kind === filter);
  return (
    <div className="mcc-dockfeed">
      {groups.map((g) => {
        const meta = WK_STATES[g.state];
        return (
          <section key={g.state} className="mc-group">
            <div className="mc-group-header">
              <span className="mc-group-label">
                <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>
                {meta.plain}
              </span>
              <span className="mc-group-count">{g.items.length}</span>
            </div>
            <div className="mc-group-cards">
              {g.items.map((item) => (
                <McvLiveCard key={item.id} item={item} selected={false} onSelect={noop} />
              ))}
            </div>
          </section>
        );
      })}
      <div className="mcc-dock-foot">4 queued · 1 standing · maestro holds them until a worktree frees</div>
    </div>
  );
}

// ── Compact live row · the Undertow at one-line scale ────────────────────
function MccDockLiveRow({ item }) {
  return (
    <div className="mcc-undertow-halo mcc-halo--tidalnebula mcc-dockrow-halo">
      <span className="mcc-halo-spin-layer"></span>
      <button className="mcc-dockrow" type="button">
        <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>
        <span className="mcc-dockrow-body">
          <b>{item.project}</b>
          <span className="mcc-caret">{MCC_MD_LIVELINE[item.id]}</span>
        </span>
        <span className="mcc-loops-t" style={{ marginTop: 2 }}>{item.time}</span>
      </button>
    </div>
  );
}

// ── Spec wrapper for the artboards ────────────────────────────────────────
function MccDockSpec({ caption, children, body }) {
  return (
    <div className="mcc-side-pad">
      <div className="mcc-side" style={{ width: 324, display: "flex", flexDirection: "column" }}>
        <div className="mcc-mcol-head">
          <span className="mcc-panel-label">Maestro</span>
          <span className="mcc-loops-count" style={{ marginLeft: "auto" }}>2 live</span>
          <button className="mcc-panel-close" type="button" aria-label="Collapse">
            <IcChevrons size={13} style={{ transform: "rotate(90deg)" }} />
          </button>
        </div>
        <div className="mcc-mcol-body">{children}</div>
      </div>
      <p className="mcc-caption">{caption}</p>
    </div>
  );
}

// M0 · Today · the flat list (reference).
function MccDockToday() {
  return (
    <MccDockSpec caption="The reference: flat rows, no grouping, no cards. Quiet, but it speaks a different language than the plane · the feed's groups and the Undertow vanish at the dock.">
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
    </MccDockSpec>
  );
}

// M1 · The feed dock · the plane's own vocabulary, compacted.
function MccDockFeed() {
  return (
    <MccDockSpec caption="The lead, wired into the synthesis frames: the same groups, cards, and Undertow as the plane · just narrower. Group hints drop, paddings tighten, queued work folds into one quiet footer line. The dock is the feed, not a summary of it.">
      <MccDockFeedBody filter={null} />
    </MccDockSpec>
  );
}

// M2 · Attention cards + live rows · full weight only where a human acts.
function MccDockAttention() {
  const noop = () => {};
  return (
    <MccDockSpec caption="A hierarchy of weight: needs-you keeps full cards (they're the decisions), running compresses to one-line Undertow rows (it's ambient), everything else is the footer. Densest feed-true take.">
      <div className="mcc-dockfeed">
        <section className="mc-group">
          <div className="mc-group-header">
            <span className="mc-group-label">
              <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR.review }}></span>
              Needs you
            </span>
            <span className="mc-group-count">2</span>
          </div>
          <div className="mc-group-cards">
            {mccMdItems(["w1", "w2"]).map((item) => (
              <McvLiveCard key={item.id} item={item} selected={false} onSelect={noop} />
            ))}
          </div>
        </section>
        <section className="mc-group">
          <div className="mc-group-header">
            <span className="mc-group-label">
              <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR.active }}></span>
              Running
            </span>
            <span className="mc-group-count">2</span>
          </div>
          <div className="mc-group-cards">
            {mccMdItems(["w3", "w4"]).map((item) => <MccDockLiveRow key={item.id} item={item} />)}
          </div>
        </section>
        <div className="mcc-dock-foot">4 queued · 1 standing · maestro holds them until a worktree frees</div>
      </div>
    </MccDockSpec>
  );
}

// M3 · Chips + feed · the plane's filter carried to the edge.
function MccDockChips() {
  const [filter, setFilter] = React.useState(null);
  const chip = (id, label, dot, count) => (
    <button type="button" className={"mc-chip" + (filter === id ? " is-active" : "")}
      onClick={() => setFilter(filter === id ? null : id)}>
      {dot && <span className="mc-chip-dot" style={{ background: dot }}></span>}
      {label}
      {count != null && <span className="mc-chip-count">{count}</span>}
    </button>
  );
  return (
    <MccDockSpec caption="M1 plus the feed's chips: filter the dock to attention or running without touching the plane. Earns its row once the workspace has a dozen live loops; below that it's chrome.">
      <div className="mc-chips" style={{ padding: "2px 10px 8px" }}>
        {chip(null, "All", null, 4)}
        {chip("attention", "Needs you", "var(--bv-blue-accent)", 2)}
        {chip("running", "Running", "var(--bv-info)", 2)}
      </div>
      <MccDockFeedBody filter={filter} />
    </MccDockSpec>
  );
}

Object.assign(window, { MccDockFeedBody, MccDockLiveRow, MccDockToday, MccDockFeed, MccDockAttention, MccDockChips });
