// Maestro · the work item detail pane.
// One object, three projections: a lifecycle rail, an activity timeline
// (the run stream as receipts), and chat (the same stream as conversation).
// The rail, receipts and gate buttons compose the standard components.

const MC_RAIL_STAGES = [
  { id: "proposed", plain: "Proposed", system: "Proposed" },
  { id: "queued",   plain: "Queued",   system: "Todo" },
  { id: "running",  plain: "Running",  system: "InProgress" },
  { id: "review",   plain: "Your gate", system: "InReview" },
  { id: "done",     plain: "Done",     system: "Done" },
];
const MC_RAIL_INDEX = { proposed: 0, queued: 1, running: 2, blocked: 2, review: 3, done: 4 };

function McRail({ state, vocab }) {
  const cur = MC_RAIL_INDEX[state];
  const stages = MC_RAIL_STAGES.map((s, i) => ({
    name: (vocab === "system" ? s.system : s.plain) + (i === cur && state === "blocked" ? " · blocked" : ""),
    state: i < cur ? "passed" : i === cur ? (state === "blocked" ? "warn" : "current") : "upcoming",
  }));
  return (
    <div>
      <DsLifecycleRail stages={stages} />
      <div className="mc-rail-note">Done is earned · the judge is its only source, and clean runs still pass your gate.</div>
    </div>
  );
}

function McTimeline({ events }) {
  return (
    <div className="mc-tl">
      {events.map((e, i) => (
        <div key={i} className="mc-tl-item">
          <span className="mc-tl-glyph" style={e.tone ? { color: WK_TONE_COLOR[e.tone] } : undefined}>{e.g}</span>
          <div className="mc-tl-body">
            <span className="mc-tl-verb">{e.verb}<span className="mc-tl-time">{e.t}</span></span>
            {e.detail && <span className="mc-tl-detail">{e.detail}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function McRunCard({ msg }) {
  return (
    <div className="mc-run-card">
      <div className="mc-run-card-head">
        <span className="mc-phase">
          <span className="mc-chip-dot bv-dot--pulse" style={{
            background: msg.phase === "running" ? "var(--bv-info)"
              : msg.phase === "blocked" ? "var(--bv-warning)"
              : msg.phase === "done" ? "var(--bv-success)"
              : "var(--bv-blue-accent)",
            animation: msg.live ? undefined : "none",
          }}></span>
          {msg.phase}
        </span>
        <span className="mc-receipt">{msg.run}</span>
      </div>
      <div className="mc-run-lines">
        {msg.lines.map((l, i) => (
          <span key={i} className="mc-run-line"><b>{l[0]}</b> {l[1]}{msg.live && i === msg.lines.length - 1 ? <span className="mcc-caret"></span> : null}</span>
        ))}
      </div>
    </div>
  );
}

function McChat({ item, extra, typing, onSend }) {
  const [draft, setDraft] = React.useState("");
  const feedRef = React.useRef(null);
  const msgs = [...item.chat, ...(extra[item.id] || [])];

  React.useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs.length, typing]);

  function send() {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    onSend(item.id, text);
  }

  return (
    <div className="mc-chat">
      <div className="bv-chat-feed" ref={feedRef}>
        {msgs.map((m, i) => {
          if (m.from === "run") return <McRunCard key={i} msg={m} />;
          if (m.from === "user") return <div key={i} className="bv-msg bv-msg--user">{m.text}</div>;
          return <div key={i} className="bv-msg bv-msg--assistant" dangerouslySetInnerHTML={{ __html: m.html }}></div>;
        })}
        {typing && (
          <div className="bv-typing"><span></span><span></span><span></span></div>
        )}
      </div>
      <div className="bv-chat-composer-wrap">
        <MccPromptPlate
          className="mcc-prompt--glass"
          placeholder="Tell this work what's next…"
          value={draft}
          onChange={setDraft}
          onSend={() => send()}
        />
      </div>
    </div>
  );
}

function McDetail({ item, vocab, receipts, tab, onTab, onApprove, onSendBack, chatExtra, typing, onSend }) {
  if (!item) {
    return (
      <aside className="mc-detail" data-screen-label="Detail pane">
        <div className="mc-detail-empty">
          <span className="bv-greeting-title">No work selected</span>
          <span className="bv-greeting-sub">Pick a work item from the feed · it carries its own history, runs, and conversation.</span>
        </div>
      </aside>
    );
  }
  const meta = WK_STATES[item.state];
  const init = WK_INITIATIVES.find((i) => i.id === item.initiative);

  return (
    <aside className="mc-detail" data-screen-label="Detail pane">
      <div className="mc-detail-header">
        <span className="mc-detail-breadcrumb">{init ? init.name : ""} › {item.project}</span>
        <div className="mc-detail-title-row">
          <h2 className="mc-detail-title">{item.title}</h2>
          <span className="mc-badge" style={{ color: WK_TONE_COLOR[meta.tone] === "var(--bv-gray-400)" ? "var(--muted-foreground)" : undefined }}>
            <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>
            {vocab === "system" ? meta.system : meta.plain}
          </span>
        </div>
        {item.state === "review" && (
          <div className="mc-detail-actions">
            <DsButton size="sm" onClick={() => onApprove(item.id)}>
              <IcCheck size={16} />Approve
            </DsButton>
            <DsButton size="sm" variant="secondary" onClick={() => onSendBack(item.id)}>
              Send back
            </DsButton>
            {item.verdict && <span className="mc-triage-sub">{item.verdict}</span>}
          </div>
        )}
        {item.state === "blocked" && (
          <div className="mc-detail-actions">
            <DsButton size="sm">Grant access</DsButton>
            <span className="mc-triage-sub">{item.reason}</span>
          </div>
        )}
        <div className="bv-tabs" style={{ marginTop: 2 }}>
          <button className={"bv-tab" + (tab === "activity" ? " is-active" : "")} type="button" onClick={() => onTab("activity")}>Activity</button>
          <button className={"bv-tab" + (tab === "chat" ? " is-active" : "")} type="button" onClick={() => onTab("chat")}>Chat</button>
        </div>
      </div>

      {tab === "activity" ? (
        <div className="mc-detail-body">
          <div className="mc-detail-section">
            <McRail state={item.state} vocab={vocab} />
          </div>
          <div className="mc-detail-section" style={{ paddingTop: 4 }}>
            <McTimeline events={item.events} />
            {receipts && item.run && (
              <DsReceipt style={{ padding: "10px 13px", gap: 5, fontSize: 12.5 }} rows={[
                { icon: <IcBranch size={13} />, label: <span>branch <McMono>{item.run}</McMono> · worktree-per-run</span> },
                ...(item.verdict ? [{ icon: <IcGavel size={13} />, label: <span>judge · {item.verdict.toLowerCase()}</span> }] : []),
                { icon: <IcCheck size={13} />, label: "the branch is the receipt · the worktree is reclaimed after the run" },
              ]} />
            )}
          </div>
        </div>
      ) : (
        <McChat item={item} extra={chatExtra} typing={typing} onSend={onSend} />
      )}
    </aside>
  );
}

// Mono machine fact inside receipt copy · matches .mc-receipt-row code.
function McMono({ children }) {
  return <code style={{ fontFamily: "var(--bv-font-mono, ui-monospace, monospace)", fontSize: 11.5, color: "var(--foreground)" }}>{children}</code>;
}

Object.assign(window, { McDetail, McRail, McTimeline, McRunCard, McChat, McMono });
