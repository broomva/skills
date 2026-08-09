// The prompt plate · Broomva's composer, promoted from the concepts canvas (P2).
// Two storeys: text on top with the ⌘L hint, a rail of dispatch context
// beneath. Glass is earned by the composer, so the plate keeps the
// frosted-blue halo. Shared by the v3 app and the concepts canvas.

const IcxPlus = (p) => <McIcon {...p}><path d="M5 12h14"></path><path d="M12 5v14"></path></McIcon>;
const IcxMic = (p) => <McIcon {...p}><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><path d="M12 19v3"></path></McIcon>;
const IcxSpark = (p) => <McIcon {...p}><path d="M12 6v12"></path><path d="M17.196 9 6.804 15"></path><path d="m6.804 9 10.392 6"></path></McIcon>;
const IcxChevDown = (p) => <McIcon {...p}><path d="m6 9 6 6 6-6"></path></McIcon>;
const IcxStop = (p) => <McIcon {...p}><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none"></rect></McIcon>;
const IcxClock = (p) => <McIcon {...p}><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></McIcon>;

function MccEffortBars({ level = 4, bars = 6 }) {
  return (
    <span className="mcc-effort" aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => (
        <span key={i} className={i < level ? "" : "is-off"} style={{ height: 3 + i * 2 }}></span>
      ))}
    </span>
  );
}

function MccRailModel() {
  return (
    <button type="button" className="mcc-prompt-chip mcc-prompt-chip--model">
      <IcxSpark size={14} />
      <span className="mcc-prompt-chip-label">claude 4.6</span>
      <IcxChevDown size={11} className="mcc-prompt-chev" />
    </button>
  );
}

function MccRailEffort() {
  return (
    <button type="button" className="mcc-prompt-chip mcc-prompt-chip--effort">
      <MccEffortBars level={4} />
      <span className="mcc-prompt-chip-label">High</span>
    </button>
  );
}

function MccRailScope({ label = "hawthorne-core" }) {
  return (
    <button type="button" className="mcc-prompt-chip mcc-prompt-chip--scope">
      <IcFolder size={14} />
      <span className="mcc-prompt-code mcc-prompt-chip-label">{label}</span>
    </button>
  );
}

function MccRailAutonomy() {
  return (
    <button type="button" className="mcc-prompt-chip">
      <IcxClock size={13} />
      <span>4h</span>
      <span className="mcc-chip-sub">unsupervised</span>
    </button>
  );
}

function MccPromptSend({ ready, stop, onClick }) {
  return (
    <button
      type="button"
      aria-label={stop ? "Stop" : "Send"}
      className={"mcc-prompt-send" + (ready || stop ? " is-ready" : "")}
      onClick={onClick}
    >
      {stop ? <IcxStop size={15} /> : <IcArrowUp size={16} />}
    </button>
  );
}

function MccPromptRight({ ready, stop, onSend }) {
  return (
    <div className="mcc-prompt-rail-right">
      <button type="button" className="mcc-prompt-iconbtn" aria-label="Attach"><IcxPlus size={16} /></button>
      <button type="button" className="mcc-prompt-iconbtn" aria-label="Dictate"><IcxMic size={15} /></button>
      <MccPromptSend ready={ready} stop={stop} onClick={onSend} />
    </div>
  );
}

function MccPromptPlate({
  placeholder = "Tell this work what's next…",
  hint = "⌘L to focus",
  className = "",
  mini = false,
  railLeft,
  stop = false,
  value,
  onChange,
  onSend,
}) {
  const [inner, setInner] = React.useState("");
  const text = value !== undefined ? value : inner;
  const set = onChange || setInner;
  const ready = text.trim().length > 0;
  const taRef = React.useRef(null);
  // Auto-grow · the field tracks its content up to ~5 lines, then scrolls.
  React.useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    const max = mini ? 120 : 184;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, max) + "px";
    ta.style.overflowY = ta.scrollHeight > max ? "auto" : "hidden";
  }, [text, mini]);
  // ⌘L focuses the plate, as the hint promises.
  React.useEffect(() => {
    if (!hint || hint.indexOf("⌘L") === -1) return;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "l" || e.key === "L")) {
        const ta = taRef.current;
        if (ta && ta.offsetParent !== null) { e.preventDefault(); ta.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [hint]);
  const send = () => {
    if (!ready || !onSend) return;
    onSend(text.trim());
    if (value === undefined) setInner("");
  };
  return (
    <div className={"mcc-prompt " + className + (mini ? " mcc-prompt--mini" : "")}>
      <div className="mcc-prompt-top">
        <textarea
          ref={taRef}
          className="mcc-prompt-input"
          rows={1}
          placeholder={placeholder}
          value={text}
          onChange={(e) => set(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
        ></textarea>
        {hint && <span className="mcc-prompt-hint">{hint}</span>}
      </div>
      <div className="mcc-prompt-rail">
        <div className="mcc-prompt-rail-left">
          {railLeft !== undefined ? railLeft : (
            window.MccDefaultRail
              ? <MccDefaultRail />
              : <><MccRailModel /><MccRailEffort /></>
          )}
        </div>
        <MccPromptRight ready={ready} stop={stop} onSend={send} />
      </div>
    </div>
  );
}

Object.assign(window, {
  IcxPlus, IcxMic, IcxSpark, IcxChevDown, IcxStop, IcxClock,
  MccEffortBars, MccRailModel, MccRailEffort, MccRailScope, MccRailAutonomy,
  MccPromptSend, MccPromptRight, MccPromptPlate,
});
