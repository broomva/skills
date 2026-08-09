// Maestro v2 · the work feed: triage headline, filter chips,
// attention-first groups (Maestro's ordering on the Hawthorne object model).

function McStateLabel({ state, vocab, dot }) {
  const meta = WK_STATES[state];
  return (
    <span className="mc-state" style={{ color: "var(--foreground)" }}>
      {dot || <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>}
      {vocab === "system" ? meta.system : meta.plain}
    </span>
  );
}

function McWorkCard({ item, selected, onSelect, vocab, receipts, glow = true, dot, extra }) {
  const init = WK_INITIATIVES.find((i) => i.id === item.initiative);
  const running = item.state === "running";
  const effDot = dot || (running ? <span className="mcc-dot-tide"></span> : undefined);
  const card = (
    <button type="button"
      className={"bv-card mc-card" + (selected ? " is-selected" : "")}
      onClick={() => onSelect(item.id)}>
      <div className="mc-card-top">
        <span className="mc-breadcrumb"><b>{init ? init.name : ""}</b> › {item.project}</span>
        <span className="mc-card-time">{item.time}</span>
      </div>
      <div className="mc-card-title">{item.title}</div>
      {item.reason && (
        <div className="mc-reason"><IcAlert />{item.reason}</div>
      )}
      {item.firstAction && (
        <div className="mc-reason mc-reason--top"><IcArrowUp /><span className="mc-clamp2">First action: {item.firstAction}</span></div>
      )}
      <div className="mc-card-meta">
        <McStateLabel state={item.state} vocab={vocab} dot={effDot} />
        {item.worker && (
          <span className="mc-worker">
            <McAvatar name={item.worker.name} color={item.worker.where === "cloud sandbox" ? "var(--bv-blue-accent)" : "var(--bv-blue)"} size={15} />
            {item.worker.name} · {item.worker.where}
          </span>
        )}
        {receipts && item.run && <span className="mc-receipt">{item.run}</span>}
      </div>
      {extra}
    </button>
  );
  if (running && glow) {
    return (
      <div className="mcc-undertow-halo mcc-halo--tidalnebula">
        <span className="mcc-halo-spin-layer"></span>
        {card}
      </div>
    );
  }
  return card;
}

function McFeed({ items, selectedId, onSelect, vocab, receipts, filter, onFilter }) {
  const attention = items.filter((i) => WK_ATTENTION.includes(i.state)).length;
  const active = items.filter((i) => i.state !== "done").length;

  const groups = WK_GROUP_ORDER
    .map((state) => ({ state, items: items.filter((i) => i.state === state) }))
    .filter((g) => g.items.length > 0);

  const visible = filter ? groups.filter((g) => g.state === filter) : groups;

  return (
    <div className="mc-feed" data-screen-label="Work feed">
      <div className="mc-feed-inner">
        <div className="mc-triage">
          <div className="mc-triage-headline">
            <span className="mc-triage-title">
              {attention > 0
                ? `${attention} ${attention === 1 ? "piece" : "pieces"} of work ${attention === 1 ? "needs" : "need"} you`
                : "All clear"}
            </span>
            <span className="mc-triage-sub">{active} active · workers handle the rest</span>
          </div>
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
        </div>

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
                  <McWorkCard key={item.id} item={item}
                    selected={item.id === selectedId}
                    onSelect={onSelect} vocab={vocab} receipts={receipts} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

Object.assign(window, { McFeed, McWorkCard, McStateLabel });
