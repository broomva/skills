// Maestro v3 · top bar (the bench + tick timer) + the live panel
// (closeable, resizable; Chat / Activity tabs; maestro-aware).

// The settled right zone, shared with the concepts canvas via window.
const MCC_TICK_WAKES = [
  { g: "↻", verb: "Routine · nightly digest", tone: "done", detail: "Self-scheduled at 02:00 → composed the handoff digest", t: "8h" },
  { g: "✎", verb: "You", detail: "\"prioritize the API work\" → reordered queue", t: "1h" },
  { g: "▷", verb: "Interval · 15m", detail: "No-op · holding at capacity (2/2 worktrees)", t: "17m" },
  { g: "▶", verb: "Worker returned", tone: "active", detail: "run/4fd028 → judged clean, moved to your gate", t: "2m" },
];

function MccLineageRow({ depth = 0, live, done, halt, who, label, dur, durPct }) {
  return (
    <div className="mcc-lin-row" style={{ paddingLeft: depth * 22 }}>
      {depth > 0 && <span className="mcc-lin-elbow"></span>}
      {live
        ? <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>
        : <span className="mc-chip-dot" style={{ background: done ? "var(--bv-success)" : halt ? "var(--bv-blue-accent)" : "var(--bv-gray-400)" }}></span>}
      <span className="mcc-lin-body">
        <span className="mcc-lin-label">{label}</span>
        <span className="mcc-lin-who">{who}</span>
      </span>
      <span className="mcc-lin-track"><span style={{ width: durPct }}></span></span>
      <span className="mcc-lin-dur">{dur}</span>
    </div>
  );
}

// Lineage derived from live items: sessions spawn sessions, hours roll up.
function MccLineage({ items }) {
  const rows = [{ live: true, label: "maestro", who: "the loop · routine", dur: "all day", durPct: "100%" }];
  for (const i of items.filter((x) => x.state === "running"))
    rows.push({ depth: 1, live: true, label: i.project, who: "maestro → " + (i.worker ? i.worker.name : "worker"), dur: i.time, durPct: "56%" });
  for (const i of items.filter((x) => x.state === "review"))
    rows.push({ depth: 1, halt: true, label: i.project, who: "waiting at your gate", dur: i.time, durPct: "96%" });
  for (const i of items.filter((x) => x.state === "queued").slice(0, 2))
    rows.push({ depth: 1, label: i.project, who: "queued · next loop", dur: "—", durPct: "0%" });
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {rows.slice(0, 6).map((r, i) => <MccLineageRow key={i} {...r} />)}
    </div>
  );
}

function MccBench({ workers, onClick, items }) {
  const colors = { claude: "var(--bv-blue)", bookkeeper: "var(--bv-purple, #7c6cf0)" };
  return (
    <div className="mcc-timer">
      <div className="mcc-undertow-halo mcc-halo--tidalnebula mcc-halo--pill">
        <span className="mcc-halo-spin-layer"></span>
        <button className="mcc-bench" type="button" onClick={onClick}
          title={workers.join(" · ") + " · open the orchestrator"}>
          <span className="mcc-bench-faces">
            {workers.map((w) => <McAvatar key={w} name={w} color={colors[w.toLowerCase()] || "var(--bv-blue)"} size={20} />)}
          </span>
          <span className="mcc-bench-label">{workers.length} live</span>
        </button>
      </div>
      <div className="mcc-timer-pop bv-glass-heavy" style={{ width: 380 }}>
        <div className="mcc-panel-label" style={{ paddingBottom: 6 }}>Live sessions · where the hours go</div>
        <MccLineage items={items || WK_ITEMS} />
      </div>
    </div>
  );
}

function MccTickTimer({ wakes = MCC_TICK_WAKES, label = "next 13m", onClick, disabled }) {
  const r = 8, c = 2 * Math.PI * r;
  return (
    <div className="mcc-timer">
      <button className="mcc-orch-chip" type="button" onClick={onClick} disabled={disabled}
        title="Next tick · click to wake now">
        <span className="mcc-ring">
          <svg viewBox="0 0 20 20" width="20" height="20">
            <circle cx="10" cy="10" r={r} fill="none" stroke="var(--bv-border-15)" strokeWidth="2"></circle>
            <circle cx="10" cy="10" r={r} fill="none" stroke="var(--bv-blue)" strokeWidth="2"
              strokeLinecap="round" strokeDasharray={c}
              strokeDashoffset={c * (13 / 15)}
              transform="rotate(-90 10 10)" className="mcc-ring-arc"></circle>
            <circle cx="10" cy="10" r="3" fill="var(--bv-info)"></circle>
          </svg>
        </span>
        <span className="mcc-orch-meta">{label}</span>
      </button>
      <div className="mcc-timer-pop bv-glass-heavy">
        <div className="mcc-panel-label" style={{ paddingBottom: 6 }}>The loop</div>
        <McTimeline events={wakes} />
      </div>
    </div>
  );
}

Object.assign(window, { MccBench, MccTickTimer, MccLineage, MCC_TICK_WAKES });

function McvTopBar({ theme, onToggleTheme, onOpenMaestro, onWake, waking, canWake, onShowIdea,
  counts, workers, wakes, items, onAttention, onCommand, cmdOpen }) {
  const attn = counts.needYou + counts.stuck;
  return (
    <header className="bv-top-bar mcv-top" data-screen-label="Top bar">
      <button className="mcc-quiet mcc-narr mcv-narr" type="button" onClick={onOpenMaestro}
        title="Open the wake log">
        <span className="mcc-dot-tide"></span>
        <span className="mcv-narr-text">
          {waking ? "maestro is waking…" : <>maestro woke 2m ago · <b>run/4fd028</b> judged clean, at your gate</>}
        </span>
      </button>
      <span className={"cmdk-lift" + (cmdOpen ? " is-open" : "")}>
        <button className="mcc-cmd" type="button" data-cmdk-anchor onClick={onCommand} title="Ask, find, or start work (⌘K)">
          <IcChat size={14} />
          <span className="mcc-cmd-ph">Ask, find, or start work…</span>
          <span className="mcc-cmd-kbd">⌘K</span>
        </button>
      </span>
      <div className="mc-topbar-right">
        {attn > 0 && (
          <button className="mcc-attn-chip mcc-attn-btn" type="button" onClick={onAttention}
            title="Blocked or waiting on you">
            <span className="mc-chip-dot" style={{ background: "var(--bv-blue-accent)" }}></span>
            {attn} need{attn === 1 ? "s" : ""} you
          </button>
        )}
        <MccTickTimer wakes={wakes} label={waking ? "waking…" : "next 13m"}
          onClick={onWake} disabled={waking || !canWake} />
        <button className="bv-icon-btn" type="button" aria-label="Toggle theme" onClick={onToggleTheme}>
          {theme === "dark" ? <IcSun size={18} /> : <IcMoon size={18} />}
        </button>
      </div>
    </header>
  );
}

// ── The live panel ────────────────────────────────────────────────────────
function McvLivePanel({ item, isMaestro, routines, tab, onTab, onClose, onDragStart,
  vocab, receipts, onApprove, onSendBack, chatExtra, typing, onSend }) {
  const meta = WK_STATES[item.state];
  const init = item.initiative ? WK_INITIATIVES.find((i) => i.id === item.initiative) : null;
  const isReview = !isMaestro && item.state === "review";
  // The look is only available at the gate; fall back to chat elsewhere.
  const effTab = tab === "look" && !isReview ? "chat" : tab;
  return (
    <aside className="mcc-live-panel" data-screen-label="Live panel">
      <div className="mcc-panel-drag" onMouseDown={onDragStart} title="Drag to resize"></div>
      <div className="mcc-panel-head">
        <div className="mcc-panel-top">
          <span className="mc-detail-breadcrumb">
            {isMaestro ? "Agents › orchestrator" : (init ? init.name : "") + " › " + item.project}
          </span>
          <button className="mcc-panel-close" type="button" aria-label="Close panel" onClick={onClose}><IcX size={14} /></button>
        </div>
        <div className="mcc-chat-pop-title-row">
          <span className="mcc-chat-pop-title">{item.title}</span>
          {isMaestro ? (
            <span className="mc-badge">
              <span className="mc-chip-dot bv-dot--pulse" style={{ background: "var(--bv-info)" }}></span>
              Listening
            </span>
          ) : (
            <span className="mc-badge">
              <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>
              {vocab === "system" ? meta.system : meta.plain}
            </span>
          )}
        </div>
        {isMaestro && (
          <span className="mcc-orch-routines">
            {routines.map((r) => <span key={r} className="mc-receipt">{r}</span>)}
          </span>
        )}
        {!isMaestro && item.state === "review" && effTab !== "look" && (
          <div className="mc-detail-actions">
            <DsButton size="sm" onClick={() => onApprove(item.id)}>
              <IcCheck size={16} />Approve
            </DsButton>
            <DsButton size="sm" variant="secondary" onClick={() => onSendBack(item.id)}>
              Send back
            </DsButton>
          </div>
        )}
        <div className="bv-tabs" style={{ marginTop: 2 }}>
          {isReview && (
            <button className={"bv-tab" + (effTab === "look" ? " is-active" : "")} type="button" onClick={() => onTab("look")}>Review</button>
          )}
          <button className={"bv-tab" + (effTab === "chat" ? " is-active" : "")} type="button" onClick={() => onTab("chat")}>Chat</button>
          <button className={"bv-tab" + (effTab === "activity" ? " is-active" : "")} type="button" onClick={() => onTab("activity")}>
            {isMaestro ? "Wake log" : "Activity"}
          </button>
        </div>
      </div>
      {effTab === "look" ? (
        <div className="mcc-panel-activity" style={{ gap: 14 }}>
          <span className="mcc-look-ran">
            <b>{item.look ? item.look.ran : "Ran to the gate"}</b>
            {item.worker ? <span> · {item.worker.name} · {item.worker.where}</span> : null}
          </span>
          <div className="mcc-look-sec">
            <div className="mcc-panel-label" style={{ paddingBottom: 4 }}>What changed</div>
            <DsReceipt style={{ padding: "10px 13px", gap: 5, fontSize: 12.5 }} rows={[
              ...(item.run ? [{ icon: <IcBranch size={13} />, label: <span>branch <McMono>{item.run}</McMono> · worktree-per-run</span> }] : []),
              ...(item.verdict ? [{ icon: <IcGavel size={13} />, label: <span>judge · {item.verdict.toLowerCase()}</span> }] : []),
              ...(item.run ? [{ icon: <IcEye size={13} />, label: <span>scope: worktree · reads ../spec.md · writes runs/{item.run.replace("run/", "")}.md</span> }] : []),
            ]} />
          </div>
          {item.look && item.look.decided && (
            <div className="mcc-look-sec">
              <div className="mcc-panel-label" style={{ paddingBottom: 4 }}>What it decided</div>
              <ul className="mcc-look-list">
                {item.look.decided.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </div>
          )}
          <div className="mcc-look-sec">
            <div className="mcc-panel-label" style={{ paddingBottom: 4 }}>The ask</div>
            <p className="mcc-look-ask">{item.look ? item.look.ask : "Approve the branch · it lands as the receipt."}</p>
          </div>
          <div className="mc-detail-actions">
            <DsButton size="sm" onClick={() => onApprove(item.id)}>
              <IcCheck size={16} />Approve
            </DsButton>
            <DsButton size="sm" variant="secondary" onClick={() => onSendBack(item.id)}>
              Send back
            </DsButton>
            <span className="mcc-look-timer">a 90-second look</span>
          </div>
        </div>
      ) : effTab === "chat" ? (
        <McChat item={item} extra={chatExtra} typing={typing} onSend={onSend} />
      ) : (
        <div className="mcc-panel-activity">
          {!isMaestro && item.run && (
            <div className="mcc-panel-receipt-label">Live feed<span className="mc-receipt">{item.run}</span></div>
          )}
          <McTimeline events={item.events} />
          {!isMaestro && item.run && (
            <DsReceipt style={{ padding: "10px 13px", gap: 5, fontSize: 12.5 }} rows={[
              { icon: <IcBranch size={13} />, label: <span>branch <McMono>{item.run}</McMono> · worktree-per-run</span> },
              ...(item.verdict ? [{ icon: <IcGavel size={13} />, label: <span>judge · {item.verdict.toLowerCase()}</span> }] : []),
              { icon: <IcEye size={13} />, label: <span>scope: worktree · reads ../spec.md · writes runs/{item.run.replace("run/", "")}.md</span> },
            ]} />
          )}
        </div>
      )}
    </aside>
  );
}

Object.assign(window, { McvTopBar, McvLivePanel });
