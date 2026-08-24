// Feedback · handed to the loop, not fired into a void.
// The product's thesis is that the loop CLOSES: work is a noun with a state
// and a receipt, and the living signal is the Undertow/tidepool. So feedback
// is a tracked THREAD you can watch. One has already been pulled into a live
// maestro session (Undertow treatment) · the moment that proves the thesis.
// A right-docked drawer over the dimmed app. Reuses globals (McIcon, IcX,
// IcCheck, IcArrowRight if present).

const IcBulb2 = (p) => <McIcon {...p}><path d="M9 18h6"></path><path d="M10 22h4"></path><path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.1V17h6v-.2c0-.8.4-1.6 1-2.1A7 7 0 0 0 12 2Z"></path></McIcon>;
const IcBug2 = (p) => <McIcon {...p}><rect x="8" y="6" width="8" height="12" rx="4"></rect><path d="M8 10H4M8 14H3M16 10h4M16 14h5M12 4V2M9 5 7.5 3.5M15 5l1.5-1.5"></path></McIcon>;
const IcHeart2 = (p) => <McIcon {...p}><path d="M19 14c1.5-1.5 3-3.3 3-5.5A4.5 4.5 0 0 0 12 6 4.5 4.5 0 0 0 2 8.5C2 12 5 14 12 20c2.5-2.1 4.6-3.9 6-5.5Z"></path></McIcon>;
const IcSend = (p) => <McIcon {...p}><path d="m22 2-7 20-4-9-9-4Z"></path><path d="M22 2 11 13"></path></McIcon>;
const IcMsg2 = (p) => <McIcon {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"></path></McIcon>;
const IcArrow = (p) => <McIcon {...p}><path d="M5 12h14M13 6l6 6-6 6"></path></McIcon>;

const FB_TYPES2 = [
  { id: "idea", label: "Idea", icon: <IcBulb2 />, ph: "What would make the loop work better for you?" },
  { id: "issue", label: "Issue", icon: <IcBug2 />, ph: "What went wrong · and what did you expect instead?" },
  { id: "praise", label: "Praise", icon: <IcHeart2 />, ph: "What's landing well? maestro likes to know too." },
];

// Your feedback so far · each a noun with a state, newest first.
const FB_THREADS_SEED = [
  {
    id: "fb-live", live: true, type: "idea",
    title: "Auto-retry blocked imports once I grant the scope",
    status: "live", statusLabel: "maestro picked this up",
    detail: "drafting in ops / feedback-triage · 6m unsupervised",
    time: "1h",
  },
  {
    id: "fb2", type: "idea",
    title: "Let the gate queue group by folder, not just by time",
    status: "triage", statusLabel: "With the team",
    detail: "Theo replied 2d ago",
    time: "3d",
  },
  {
    id: "fb3", type: "issue",
    title: "Dark mode washed out the run timeline ticks",
    status: "ship", statusLabel: "Shipped",
    detail: "v4.2 · last week",
    time: "1w",
  },
  {
    id: "fb4", type: "idea",
    title: "A shortcut to jump straight to “Needs you”",
    status: "log", statusLabel: "Logged",
    detail: "in the backlog",
    time: "2w",
  },
];

function FbDot({ status }) {
  if (status === "live") return <span className="mcc-dot-tide fb-thread-dot" style={{ width: 12, height: 12 }}></span>;
  const color = status === "ship" ? "var(--bv-success)"
    : status === "triage" ? "var(--bv-blue)"
    : "var(--bv-gray-400)";
  return <span className="mc-chip-dot fb-thread-dot" style={{ width: 9, height: 9, background: color }}></span>;
}

function FbThread({ t, fresh }) {
  const inner = (
    <button type="button" className={"fb-thread" + (t.live ? " fb-thread--live" : "") + (fresh ? " fb-thread--fresh" : "")}>
      <FbDot status={t.status} />
      <span className="fb-thread-body">
        <span className="fb-thread-top">
          <span className="fb-thread-title">{t.title}</span>
          <span className="fb-thread-time">{t.time}</span>
        </span>
        <span className="fb-thread-meta">
          <span className={"fb-thread-status fb-thread-status--" + t.status}>{t.statusLabel}</span>
          <span className="fb-thread-detail">{t.detail}</span>
        </span>
        {t.live && <span className="fb-live-link">Open session<IcArrow /></span>}
      </span>
    </button>
  );
  // The live thread wears the Undertow · the product's hero living signal.
  if (t.live) {
    return (
      <DsUndertow style={{ margin: "4px 0" }}>
        {inner}
      </DsUndertow>
    );
  }
  return inner;
}

function MccFeedback({ open, onClose, context = "Maestro" }) {
  const [type, setType] = React.useState("idea");
  const [text, setText] = React.useState("");
  const [attach, setAttach] = React.useState(true);
  const [threads, setThreads] = React.useState(FB_THREADS_SEED);
  const [freshId, setFreshId] = React.useState(null);
  const taRef = React.useRef(null);

  React.useEffect(() => {
    if (!open) return;
    setText(""); setType("idea"); setAttach(true);
    setThreads(FB_THREADS_SEED); setFreshId(null);
    const t = setTimeout(() => taRef.current && taRef.current.focus(), 80);
    const onKey = (e) => { if (e.key === "Escape") onClose && onClose(); };
    window.addEventListener("keydown", onKey);
    return () => { clearTimeout(t); window.removeEventListener("keydown", onKey); };
  }, [open]);

  if (!open) return null;

  const active = FB_TYPES2.find((t) => t.id === type) || FB_TYPES2[0];

  const send = () => {
    const body = text.trim();
    if (!body) { taRef.current && taRef.current.focus(); return; }
    const id = "fb-new-" + Date.now();
    // Lands as a tracked thread · logging, with the tidepool · then settles.
    const fresh = {
      id, type,
      title: body.length > 78 ? body.slice(0, 77) + "…" : body,
      status: "live", statusLabel: "Routing to the team",
      detail: attach ? "maestro is reading it · " + context : "maestro is reading it",
      time: "now",
    };
    setThreads((prev) => [fresh, ...prev]);
    setFreshId(id);
    setText("");
    // It settles into "Logged" · the loop acknowledged it.
    setTimeout(() => {
      setThreads((prev) => prev.map((t) => t.id === id
        ? { ...t, status: "log", statusLabel: "Logged", detail: "the team has it · maestro tagged it " + type }
        : t));
    }, 1700);
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }
  };

  return (
    <>
      <div className="fb-scrim" onClick={onClose}></div>
      <aside className="fb-drawer" data-screen-label="Feedback drawer" role="dialog" aria-modal="true" aria-label="Feedback">
        <header className="fb-head">
          <span className="fb-head-glyph"><IcMsg2 size={18} /></span>
          <div className="fb-head-main">
            <div className="fb-title">Feedback</div>
            <div className="fb-sub">Hand it to the loop · the team reads it, and so does maestro.</div>
          </div>
          <button type="button" className="fb-x" aria-label="Close" onClick={onClose}><IcX size={17} /></button>
        </header>

        <div className="fb-body">
          <div className="fb-compose">
            <div className="fb-compose-field">
              <textarea ref={taRef} className="fb-text" value={text} placeholder={active.ph}
                onChange={(e) => setText(e.target.value)} onKeyDown={onKeyDown} />
              <div className="fb-tray">
                <div className="fb-types">
                  {FB_TYPES2.map((t) => (
                    <button key={t.id} type="button" className={"fb-type" + (type === t.id ? " is-active" : "")} onClick={() => setType(t.id)}>
                      {React.cloneElement(t.icon, { size: 14 })}{t.label}
                    </button>
                  ))}
                </div>
                <button type="button" className="fb-send" aria-label="Send feedback" disabled={!text.trim()} onClick={send}><IcSend size={16} /></button>
              </div>
            </div>
            <label className="fb-ctx">
              <span className={"fb-ctx-check" + (attach ? " is-on" : "")} onClick={() => setAttach(!attach)} role="checkbox" aria-checked={attach}><IcCheck size={12} /></span>
              <span className="fb-ctx-label">Attach this screen · a snapshot + <code>{context}</code> context</span>
            </label>
          </div>

          <div className="fb-threads">
            <div className="fb-threads-head">
              <span className="fb-threads-label">Your feedback</span>
              <span className="fb-threads-note">{threads.length} threads · 1 in a session</span>
            </div>
            {threads.map((t) => <FbThread key={t.id} t={t} fresh={t.id === freshId} />)}
          </div>
        </div>
      </aside>
    </>
  );
}

Object.assign(window, { MccFeedback });
