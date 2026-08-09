// Concepts canvas · the maestro loop: the synthesis (v2).
// This is the workspace-click view; clicking any folder underneath looks
// the same, except the FS pane shows THAT folder's location (and worktree).
// Tabs: sessions live on the LEFT of the strip; files open on the RIGHT,
// sliding in from the file pane and pushing the queue leftward. Drag a
// file tab toward the chat to keep a two-sided view. + spawns a new
// session on the current workspace layer; the toggle at the strip's right
// edge hides the FS pane.

const IcMlPanel = (p) => <McIcon {...p}><rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M15 3v18"></path></McIcon>;
const IcMlPanelLeft = (p) => <McIcon {...p}><rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M9 3v18"></path></McIcon>;

// ── The gate queue · stopgaps accumulated over ticks ─────────────────────
const MCC_ML_GATE_SEED = [ // superseded · the live seed is AiProtocol.jsx's MCC_ML_GATE (data-gate parts)
  {
    id: "g1", kind: "gate",
    title: "Persist run transcripts on the Run record",
    meta: "ran 2h 14m unsupervised · judge passed · 14 tests",
    ask: "Approve the branch and tonight's phase 2 builds on it.",
    actions: [["Approve", "primary"], ["Send back", "secondary"]],
    t: "12m",
  },
  {
    id: "g2", kind: "warn",
    title: "Linear import needs an API scope",
    meta: "worker paused 41m · blocks 3 queued items downstream",
    ask: "Grant read access to Linear cycles, or park the import.",
    actions: [["Grant access", "primary"], ["Park it", "secondary"]],
    t: "41m",
  },
];

function MccGateQueue({ items, mini }) {
  const [open, setOpen] = React.useState(mini ? -1 : 0);
  // The grace window · a decision takes effect on the next tick, so the verb
  // stays reversible for a beat instead of being instantly irreversible.
  const [done, setDone] = React.useState({});
  const timers = React.useRef({});
  const GRACE = 10;
  React.useEffect(() => () => Object.values(timers.current).forEach(clearInterval), []);
  const act = (g, label) => {
    setDone((d) => ({ ...d, [g.id]: { label, left: GRACE } }));
    timers.current[g.id] = setInterval(() => {
      setDone((d) => {
        const e = d[g.id];
        if (!e) return d;
        if (e.left <= 1) { clearInterval(timers.current[g.id]); return { ...d, [g.id]: { ...e, left: 0, final: true } }; }
        return { ...d, [g.id]: { ...e, left: e.left - 1 } };
      });
    }, 1000);
  };
  const undo = (id) => {
    clearInterval(timers.current[id]);
    setDone((d) => { const n = { ...d }; delete n[id]; return n; });
  };
  const live = items.filter((g) => !(done[g.id] && done[g.id].final));
  if (!live.length) {
    return (
      <div className="mcc-allclear" style={{ padding: "2px 2px" }}>
        <IcCheck size={14} />
        Nothing at your gate. The loop holds everything · next tick 13m
      </div>
    );
  }
  return (
    <div className="mcc-gateq" data-screen-label="Gate queue">

      {live.map((g, i) => {
        const d = done[g.id];
        return (
        <div key={g.id} className="mcc-gateq-card" onClick={() => setOpen(open === i ? -1 : i)}>
          <div className="mcc-gateq-row">
            <MccLoopDot kind={g.kind} />
            <span className="mcc-gateq-title">{g.title}</span>
            <span className="mcc-loops-t" style={{ marginTop: 0 }}>{g.t}</span>
          </div>
          <span className="mcc-gateq-meta">{g.meta}</span>
          {d ? (
            <div className="mcc-gateq-done" onClick={(e) => e.stopPropagation()}>
              <IcCheck size={14} />
              {d.label}
              <span className="mcc-gateq-done-note">takes effect on the next tick</span>
              <button className="bv-pill bv-pill--secondary bv-pill--sm mcc-gateq-undo" type="button" onClick={() => undo(g.id)}>
                Undo · {d.left}s
              </button>
            </div>
          ) : open === i && (
            <>
              {g.look ? (
                <div className="mcc-gateq-look">
                  {g.look.map(([k, v]) => (
                    <div key={k} className="mcc-gateq-look-row">
                      <span className="mcc-gateq-look-key">{k}</span>
                      <span className="mcc-gateq-look-val">{v}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <span className="mcc-gateq-ask">{g.ask}</span>
              )}
              <div className="mc-detail-actions" onClick={(e) => e.stopPropagation()}>
                {g.actions.map(([label, tone]) => (
                  <button key={label} className={"bv-pill bv-pill--" + tone + " bv-pill--sm"} type="button"
                    onClick={() => act(g, tone === "primary" ? (label === "Approve" ? "Approved" : label + " · done") : label === "Send back" ? "Sent back with notes" : label + " · done")}>
                    {tone === "primary" && <IcCheck size={13} />}{label}
                  </button>
                ))}
                <span className="mcc-look-timer">{g.hint || (i === 0 ? "a 90-second look" : "unblocks 1 worker")}</span>
              </div>
            </>
          )}
        </div>
        );
      })}
    </div>
  );
}

// ── The tick card · the loop narrating itself in the chat (gen-UI) ───────
function MccTickCard({ rows }) {
  rows = rows || [
    { g: "▷", cause: "interval 15m", causeColor: "var(--bv-gray-500)", label: "No-op · at capacity (2/2 worktrees)", t: "32m" },
    { g: "▶", cause: "worker returned", causeColor: "var(--bv-blue)", label: "run/7c2f1a judged clean → queued to your gate", t: "12m" },
    { g: "▷", cause: "interval 15m", causeColor: "var(--bv-gray-500)", label: "Holding · 2 decisions open at your gate", t: "2m" },
  ];
  return (
    <div className="mcc-tickcard" data-screen-label="Tick receipt (gen-UI)">
      <div className="mcc-tickcard-head">
        <span className="mcc-dot-tide" style={{ width: 12, height: 12 }}></span>
        the loop · last 3 ticks
      </div>
      <div className="mcc-wake-list">
        {rows.map((r, i) => (
          <div key={i} className="mcc-wake">
            <span className="mcc-wake-glyph">{r.g}</span>
            <span className="mcc-wake-body">
              <span className="mcc-wake-top">
                <span className="mcc-wake-cause" style={{ color: r.causeColor }}>{r.cause}</span>
                <span className="mcc-wake-label">{r.label}</span>
                <span className="mcc-loops-t" style={{ marginTop: 0 }}>{r.t}</span>
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Maestro, docked left and collapsible ─────────────────────────
function MccMcDock({ shut, onToggle, resize }) {
  if (shut) {
    return (
      <div className="mcc-mcol mcc-mcol--shut" data-screen-label="Maestro (collapsed)">
        <button className="mcc-panel-close" type="button" onClick={onToggle} aria-label="Expand Maestro" title="Maestro">
          <IcBoard size={15} />
        </button>
        <span className="mcc-attn-chip" style={{ padding: 0, width: 24, height: 24, justifyContent: "center" }}>2</span>
        {MCC_AT_LOOPS.filter((l) => l.kind === "live").map((l) => (
          <span key={l.title} title={l.title}><MccLoopDot kind="live" /></span>
        ))}
      </div>
    );
  }
  return (
    <div className="mcc-mcol" data-screen-label="Maestro (docked)">
      {resize && <div className="mcc-coldrag mcc-coldrag--right" onMouseDown={resize} title="Drag to resize"></div>}
      <div className="mcc-mcol-head">
        <span className="mcc-panel-label">Maestro</span>
        <span className="mcc-loops-count" style={{ marginLeft: "auto" }}>2 live</span>
        <button className="mcc-panel-close" type="button" onClick={onToggle} aria-label="Collapse Maestro" title="Collapse">
          <IcChevrons size={13} style={{ transform: "rotate(90deg)" }} />
        </button>
      </div>
      <div className="mcc-mcol-body">
        <MccDockFeedBody filter={null} />
      </div>
    </div>
  );
}

// ── Per-scope FS pane data ────────────────────────────────────────────────
const MCC_FT_HAW = [
  { name: "hawthorne.md", path: "hawthorne.md", depth: 0, kind: "file" },
  { name: "hawthorne-core", depth: 0, kind: "folder" },
  { name: "spec.md", path: "spec.md", depth: 1, kind: "file" },
  { name: "prior-art.md", path: "prior-art.md", depth: 1, kind: "file" },
  { name: "api-decisions.md", path: "api-decisions.md", depth: 1, kind: "file" },
  { name: "run-7c2f1a.md", path: "run-7c2f1a.md", depth: 1, kind: "file" },
  { name: "hawthorne-db", depth: 0, kind: "folder" },
  { name: "hawthorne-engine", depth: 0, kind: "folder" },
];

const MCC_ML_FS = {
  root: { label: "Broomva/", location: "~/Broomva", entries: () => MCC_FT_ROOT, layer: "the workspace" },
  hawthorne: { label: "hawthorne/", location: "~/Broomva/hawthorne", entries: () => MCC_FT_HAW, layer: "hawthorne/" },
  core: { label: "hawthorne-core/", location: "~/Broomva/hawthorne/hawthorne-core", worktree: "worktree: run/7c2f1a", entries: () => MCC_FT_CORE, layer: "hawthorne-core/" },
};

// ── Chat panes · maestro + fresh sessions on the current layer ───────────
function MccChatPane({ session, layer, chatLen, rail }) {
  if (session.id !== "maestro") {
    return (
      <div className="mcc-chatcol" data-screen-label={"Session pane · " + session.label}>
        <div className="mcc-newchat">
          <div className="mcc-newchat-inner">
            <span className="bv-greeting-title">A fresh session on {layer}</span>
            <span className="bv-greeting-sub">It inherits this layer's contract · budget, gate, scope · and its receipts land here.</span>
            <MccPromptPlate className="mcc-prompt--glass" placeholder={"Tell " + layer + " what's next…"} />
          </div>
        </div>
      </div>
    );
  }
  return <MccMaestroChat key={chatLen || "short"} layer={layer} chatLen={chatLen} rail={rail} />;
}

// The conversation minimap · a thin ruler pinned to the chat's right edge.
// The conversation minimap · a thin ruler of your inputs pinned to the chat's
// right edge. Three behaviours that adapt to volume:
//  · compact (a handful): a tight centered band; hovering a mark grows it with
//    a dock-style falloff onto its neighbours.
//  · dense (dozens–hundreds): a proportional overview. Adjacent inputs that
//    would collide are BUCKETED into a single mark whose thickness shows how
//    many it holds · so the rail stays legible at any density. On hover the
//    cursor opens a LENS: a fixed filmstrip of the ~11 turns around the focus
//    fans out at a readable pitch (dock magnification), and moving the cursor
//    scrubs that window through the whole history. Click jumps to the focus.
// Hover/scrub → the message + when you sent it; click → smooth-scroll there.
function MccChatMinimap({ feedRef, messages }) {
  const railRef = React.useRef(null);
  const ticksRef = React.useRef([]);
  const [ticks, setTicks] = React.useState([]);
  const [buckets, setBuckets] = React.useState([]);
  const [mode, setMode] = React.useState("compact");
  const [railH, setRailH] = React.useState(0);
  const [active, setActive] = React.useState(-1);
  const [hover, setHover] = React.useState(-1);          // compact: hovered index
  const [pointerY, setPointerY] = React.useState(null);  // dense: cursor Y in rail
  ticksRef.current = ticks;

  const DENSE_WIN = 5, DENSE_PITCH = 13; // lens: ±5 turns at 13px pitch

  const computeActive = React.useCallback(() => {
    const feed = feedRef.current;
    if (!feed) return;
    const probe = feed.scrollTop + 72;
    const arr = ticksRef.current;
    let idx = -1;
    for (let i = 0; i < arr.length; i++) { if (arr[i].top <= probe) idx = i; else break; }
    setActive(idx);
  }, [feedRef]);

  const measure = React.useCallback(() => {
    const feed = feedRef.current, rail = railRef.current;
    if (!feed || !rail) return;
    const rh = rail.clientHeight || 1;
    const total = feed.scrollHeight || 1;
    const rows = [];
    feed.querySelectorAll('[data-bv-user="1"]').forEach((el) => {
      rows.push({ top: el.offsetTop, text: (el.textContent || "").trim(), time: el.dataset.bvTime || "" });
    });
    const n = rows.length;
    const pad = 12;
    const usable = Math.max(1, rh - pad * 2);
    const compactGap = 14;
    const dense = n > 1 && (n - 1) * compactGap > usable;
    let bks = [];
    if (n === 1) {
      rows[0].y = rows[0].yBase = Math.round(rh / 2);
    } else if (dense) {
      rows.forEach((t) => { t.yBase = pad + (t.top / total) * usable; t.y = t.yBase; });
      // Bin inputs into fixed ~5px slots so the at-rest overview never
      // collapses into one bar; each non-empty slot becomes one bucket.
      const bucketPitch = 5;
      let cur = null, curBin = -999;
      rows.forEach((t, i) => {
        const bin = Math.floor(t.yBase / bucketPitch);
        if (cur && bin === curBin) {
          cur.members.push(i); cur.y1 = t.yBase; cur.timeEnd = t.time;
        } else {
          cur = { y0: t.yBase, y1: t.yBase, members: [i], timeStart: t.time, timeEnd: t.time };
          curBin = bin; bks.push(cur);
        }
      });
      bks.forEach((b) => { b.y = Math.round((b.y0 + b.y1) / 2); b.count = b.members.length; });
    } else if (n > 1) {
      const minT = rows[0].top, maxT = rows[n - 1].top;
      const range = Math.max(1, maxT - minT);
      const span = Math.min(usable, (n - 1) * compactGap);
      const startY = Math.round(rh / 2 - span / 2);
      rows.forEach((t) => { t.y = Math.round(startY + ((t.top - minT) / range) * span); t.yBase = t.y; });
    }
    ticksRef.current = rows;
    setRailH(rh);
    setMode(dense ? "dense" : "compact");
    setTicks(rows);
    setBuckets(bks);
    computeActive();
  }, [feedRef, computeActive]);

  React.useLayoutEffect(() => {
    measure();
    const feed = feedRef.current;
    if (!feed) return;
    const onScroll = () => computeActive();
    feed.addEventListener("scroll", onScroll, { passive: true });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => measure()) : null;
    if (ro) ro.observe(feed);
    window.addEventListener("resize", measure);
    return () => {
      feed.removeEventListener("scroll", onScroll);
      if (ro) ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure, computeActive, feedRef, messages]);

  const jump = (t) => {
    const feed = feedRef.current;
    if (!feed) return;
    const target = Math.max(0, Math.min(t.top - 20, feed.scrollHeight - feed.clientHeight));
    const start = feed.scrollTop;
    const dist = target - start;
    if (Math.abs(dist) < 2) { feed.scrollTop = target; return; }
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { feed.scrollTop = target; return; }
    const dur = Math.min(560, 200 + Math.abs(dist) * 0.45);
    const t0 = performance.now();
    const ease = (p) => 1 - Math.pow(1 - p, 3);
    const step = (now) => {
      const p = Math.min(1, (now - t0) / dur);
      feed.scrollTop = start + dist * ease(p);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  const onRailMove = (e) => {
    const r = railRef.current && railRef.current.getBoundingClientRect();
    if (r) setPointerY(e.clientY - r.top);
  };

  // Focus mark: nearest to cursor (dense) / hovered (compact).
  let focus = mode === "compact" ? hover : -1;
  if (mode === "dense" && pointerY != null && ticks.length) {
    let best = Infinity;
    ticks.forEach((t, i) => { const dd = Math.abs(t.yBase - pointerY); if (dd < best) { best = dd; focus = i; } });
  }

  const clampY = (v) => Math.max(12, Math.min(railH - 12, v));
  const tip = focus >= 0 && ticks[focus] ? ticks[focus] : null;
  const tipRenderY = tip ? (mode === "dense" ? clampY(pointerY) : tip.y) : 0;
  const popY = tip ? Math.min(Math.max(tipRenderY, 30), Math.max(30, railH - 30)) : 0;

  const renderDense = () => {
    const els = [];
    const winS = focus >= 0 ? Math.max(0, focus - DENSE_WIN) : -1;
    const winE = focus >= 0 ? Math.min(ticks.length - 1, focus + DENSE_WIN) : -1;
    const rTop = focus >= 0 ? clampY(pointerY + (winS - focus) * DENSE_PITCH) : 0;
    const rBot = focus >= 0 ? clampY(pointerY + (winE - focus) * DENSE_PITCH) : 0;
    buckets.forEach((b, bi) => {
      // Hide buckets behind the open lens; the filmstrip stands in for them.
      if (focus >= 0 && b.y >= rTop - 3 && b.y <= rBot + 3) return;
      const act = focus < 0 && active >= 0 && b.members.indexOf(active) >= 0;
      els.push(<button key={"b" + bi} type="button" tabIndex={-1} aria-hidden="true"
        className={"mcc-mmap-tick" + (b.count > 1 ? " is-bucket" : "") + (act ? " is-active" : "")}
        style={{ top: b.y + "px", height: (b.count > 1 ? Math.min(7, 2 + b.count * 0.5) : 2) + "px" }}></button>);
    });
    if (focus >= 0) {
      for (let i = winS; i <= winE; i++) {
        const o = i - focus, ao = Math.abs(o);
        const mag = ao === 0 ? " is-hover" : ao === 1 ? " is-near" : ao === 2 ? " is-near2" : "";
        els.push(<button key={"r" + i} type="button" tabIndex={-1} aria-hidden="true"
          className={"mcc-mmap-tick is-reveal" + mag}
          style={{ top: clampY(pointerY + o * DENSE_PITCH) + "px" }}></button>);
      }
    }
    return els;
  };

  return (
    <div className={"mcc-mmap" + (mode === "dense" ? " is-dense" : "")} ref={railRef}
      aria-hidden={ticks.length ? undefined : "true"}>
      {mode === "dense" && (
        <div className="mcc-mmap-hit"
          onMouseMove={onRailMove}
          onMouseLeave={() => setPointerY(null)}
          onClick={() => { if (focus >= 0 && ticks[focus]) jump(ticks[focus]); }}>
        </div>
      )}
      {mode === "compact" && ticks.map((t, i) => {
        const dist = hover >= 0 ? Math.abs(i - hover) : 99;
        const mag = dist === 0 ? " is-hover" : dist === 1 ? " is-near" : dist === 2 ? " is-near2" : "";
        return (
          <button key={i} type="button"
            className={"mcc-mmap-tick" + (i === active ? " is-active" : "") + mag}
            style={{ top: t.y + "px" }}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? -1 : h))}
            onFocus={() => setHover(i)}
            onBlur={() => setHover((h) => (h === i ? -1 : h))}
            onClick={() => jump(t)}
            aria-label={"Jump to your message · " + t.text}>
          </button>
        );
      })}
      {mode === "dense" && renderDense()}
      {tip && (
        <div className="mcc-mmap-pop" style={{ top: popY + "px" }}>
          <span className="mcc-mmap-pop-text">{tip.text}</span>
          {tip.time && <span className="mcc-mmap-pop-time">{tip.time}</span>}
        </div>
      )}
    </div>
  );
}

// The maestro conversation · UIMessages over a switchable transport.
// Parts render via MccMessage (AiProtocol.jsx); the gate queue is derived
// from data-gate parts; the model chip cycles claude → gpt → harness.
function MccMaestroChat({ layer, chatLen, rail }) {
  const d = useMccDispatch();
  const { messages, status, sendMessage } = useBvChat({
    transport: bvGetTransport(d.harness, d.model),
    initialMessages: chatLen === "extreme" ? BV_SEED_EXTREME : chatLen === "stress" ? BV_SEED_STRESS : BV_SEED_MESSAGES,
  });
  const gate = bvSelectGate(messages);
  const feedRef = React.useRef(null);
  React.useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, status]);
  return (
    <div className="mcc-chatcol" data-screen-label="Maestro · the conversation">
      <div className="mcc-chatcol-main">
        <div className="bv-chat-feed mcc-chatcol-feed" ref={feedRef}>
          {messages.map((m) => <MccMessage key={m.id} msg={m} />)}
        </div>
        <MccChatMinimap feedRef={feedRef} messages={messages} />
      </div>
      <div className="mcc-chatcol-foot">
        <MccGateQueue items={gate} />
        <MccPromptPlate className="mcc-prompt--glass"
          placeholder="Message maestro · anything beyond approve and send back…"
          stop={status !== "ready"}
          onSend={(text) => sendMessage({ text })}
          railLeft={<MccDispatchRail d={d} quiet={rail !== "full"} />}
        />
      </div>
    </div>
  );
}

// ── The frame ─────────────────────────────────────────────────────────────
// ── Maestro as the grown center · the full plane ──────────────
function MccMissionPlane() {
  const [view, setView] = React.useState(() => { try { return localStorage.getItem("mc4-view") || "feed"; } catch { return "feed"; } });
  const [filter, setFilter] = React.useState(null);
  const noop = () => {};
  React.useEffect(() => { try { localStorage.setItem("mc4-view", view); } catch {} }, [view]);
  const feedGroups = WK_GROUP_ORDER
    .map((state) => ({ state, items: WK_ITEMS.filter((i) => i.state === state) }))
    .filter((g) => g.items.length > 0);
  return (
    <div className="mcc-plane" data-screen-label="Maestro plane">
      <div className="mcc-plane-bar" style={{ padding: "10px 22px 10px" }}>
        {view === "feed" ? (
          <div className="mc-chips" style={{ flex: 1 }}>
            <button type="button" className={"mc-chip" + (filter === null ? " is-active" : "")}
              onClick={() => setFilter(null)}>All</button>
            {feedGroups.map((g) => {
              const meta = WK_STATES[g.state];
              return (
                <button key={g.state} type="button"
                  className={"mc-chip" + (filter === g.state ? " is-active" : "")}
                  onClick={() => setFilter(filter === g.state ? null : g.state)}>
                  <span className="mc-chip-dot" style={{ background: WK_TONE_COLOR[meta.tone] }}></span>
                  {meta.plain}
                  <span className="mc-chip-count">{g.items.length}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div style={{ flex: 1 }} />
        )}
        <McvViewToggle view={view} onView={setView} />
      </div>
      <div className="mcc-plane-body" data-view={view}>
        {view === "feed" && (
          <McvPlaneFeed items={WK_ITEMS} selectedId={null} onSelect={noop} vocab="plain"
            receipts={true} signal="undertow" filter={filter} onFilter={setFilter} hideFilters={true} />
        )}
        {view === "board" && (
          <McvPlaneBoard items={WK_ITEMS} selectedId={null} onSelect={noop} vocab="plain"
            receipts={true} signal="undertow" />
        )}
        {view === "list" && (
          <McvPlaneList items={WK_ITEMS} selectedId={null} onSelect={noop} vocab="plain" receipts={true} />
        )}
      </div>
    </div>
  );
}

function MccMaestroLoopV2({ initialScope = "root", initialMode = "workspace", app = false, theme = "light", onToggleTheme, onOpenView, chatLen, rail }) {
  const noop = () => {};
  const [mode, setMode] = React.useState(initialMode);
  const [scope, setScope] = React.useState(initialScope);
  const [shut, setShut] = React.useState(() => (app && typeof window !== "undefined" ? window.innerWidth < 1080 : false));
  const [fsOpen, setFsOpen] = React.useState(() => (app && typeof window !== "undefined" ? window.innerWidth >= 1280 : true));
  const [navOpen, setNavOpen] = React.useState(() => {
    if (app && typeof window !== "undefined" && window.innerWidth < 1080) return false;
    try { return localStorage.getItem("bv-nav-open") !== "false"; } catch { return true; }
  });
  const [cols, setCols] = React.useState(() => {
    const base = { dock: 320, chat: 430, fs: 380, split: 420, nav: 200 };
    try { return { ...base, ...JSON.parse(localStorage.getItem("bv-ml-cols") || "{}") }; } catch { return base; }
  });
  const [fileTabs, setFileTabs] = React.useState([]);
  const [chatTabs, setChatTabs] = React.useState([{ id: "maestro", label: "maestro" }]);
  const [chatAct, setChatAct] = React.useState("maestro");
  const [view, setView] = React.useState({ kind: "chat" });
  const [split, setSplit] = React.useState(null);
  const [dragging, setDragging] = React.useState(null);
  const [overDrop, setOverDrop] = React.useState(false);

  const fsScope = mode === "mission" ? "root" : scope;
  const fs = MCC_ML_FS[fsScope] || MCC_ML_FS.root;

  // Column resizing · every fixed column has a drag edge; widths persist.
  React.useEffect(() => { try { localStorage.setItem("bv-ml-cols", JSON.stringify(cols)); } catch {} }, [cols]);
  React.useEffect(() => { try { localStorage.setItem("bv-nav-open", navOpen); } catch {} }, [navOpen]);
  const MCC_ML_CLAMP = { dock: [240, 440], chat: [360, 620], fs: [280, 480], split: [320, 640], nav: [160, 320] };
  const startDrag = (key, dir) => (e) => {
    e.preventDefault();
    const x0 = e.clientX, w0 = cols[key], [lo, hi] = MCC_ML_CLAMP[key];
    const move = (ev) => setCols((c) => ({ ...c, [key]: Math.max(lo, Math.min(hi, w0 + (ev.clientX - x0) * dir)) }));
    const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  // Responsive (app only): the FS pane yields first, then the dock.
  React.useEffect(() => {
    if (!app) return;
    let prev = window.innerWidth;
    const onR = () => {
      const w = window.innerWidth;
      if (w < 1280 && prev >= 1280) setFsOpen(false);
      if (w >= 1280 && prev < 1280) setFsOpen(true);
      if (w < 1080 && prev >= 1080) { setShut(true); setNavOpen(false); }
      if (w >= 1080 && prev < 1080) {
        setShut(false);
        try { setNavOpen(localStorage.getItem("bv-nav-open") !== "false"); } catch { setNavOpen(true); }
      }
      prev = w;
    };
    window.addEventListener("resize", onR);
    return () => window.removeEventListener("resize", onR);
  }, [app]);

  const goMission = () => { setMode("mission"); setSplit(null); setView({ kind: "chat" }); };
  const openMaestro = () => { setChatAct("maestro"); if (!split) setView({ kind: "chat" }); };
  const goScope = (s) => { setScope(s); setMode("workspace"); };

  const openFile = (path) => {
    setFileTabs((t) => (t.includes(path) ? t : [...t, path]));
    if (split) setSplit(path); else setView({ kind: "file", path });
  };
  const clickFileTab = (path) => { if (split) setSplit(path); else setView({ kind: "file", path }); };
  const closeFile = (path) => {
    setFileTabs((t) => t.filter((p) => p !== path));
    if (split === path) { setSplit(null); setView({ kind: "chat" }); }
    if (view.kind === "file" && view.path === path) setView({ kind: "chat" });
  };
  const clickChatTab = (id) => { setChatAct(id); if (!split) setView({ kind: "chat" }); };
  const newChat = () => {
    const n = chatTabs.length;
    const id = "sess-" + n;
    setChatTabs((c) => [...c, { id, label: "session " + (n + 1) }]);
    setChatAct(id);
    if (!split) setView({ kind: "chat" });
  };
  const closeChat = (id) => {
    setChatTabs((c) => c.filter((x) => x.id !== id));
    if (chatAct === id) setChatAct("maestro");
  };

  const session = chatTabs.find((c) => c.id === chatAct) || chatTabs[0];
  const fileActive = (p) => (split ? split === p : view.kind === "file" && view.path === p);
  const chatShowing = split !== null || view.kind === "chat";

  return (
    <div className="mcc-fill">
      <div className="bv-app" style={{ gridTemplateColumns: (navOpen ? cols.nav : 56) + "px 1fr", transition: "grid-template-columns 0.15s ease" }}>
        <MccTcSidebar scope={mode === "workspace" ? scope : "__none"} setScope={goScope}
          onMission={goMission} missionActive={mode === "mission"} resize={startDrag("nav", 1)} collapsed={!navOpen} onOpenView={onOpenView} />
        <div className="bv-main">
          <McvTopBar theme={theme} onToggleTheme={onToggleTheme || noop} onOpenMaestro={openMaestro}
            onWake={noop} waking={false} canWake={true} onShowIdea={noop}
            counts={{ needYou: 1, stuck: 1 }} workers={["claude", "bookkeeper"]}
            wakes={MCC_TICK_WAKES} items={WK_ITEMS} onAttention={noop}
            onCommand={() => window.dispatchEvent(new CustomEvent("bv:command-open"))} />

          <div className="mcc-ftabs" data-screen-label="Tab strip">
            <button type="button" className={"mcc-prompt-iconbtn" + (navOpen ? " is-on" : "")} style={{ width: 26, height: 26, flexShrink: 0, marginRight: 2 }}
              aria-label="Toggle sidebar" title={navOpen ? "Minimize sidebar" : "Expand sidebar"} onClick={() => setNavOpen(v => !v)}>
              <IcMlPanelLeft size={14} />
            </button>
            {chatTabs.map((c) => (
              <button key={c.id} type="button"
                className={"mcc-ftab" + (chatShowing && chatAct === c.id ? " is-active" : "")}
                onClick={() => clickChatTab(c.id)}
                title={c.id === "maestro" ? "The orchestrator's session · pinned" : "A session on " + fs.layer}>
                <span className="mc-chip-dot bv-dot--pulse" style={{ background: "var(--bv-info)" }}></span>
                <span className="mcc-ftab-name">{c.label}</span>
                {c.id !== "maestro" && (
                  <span className="mcc-ftab-x" role="button" aria-label={"Close " + c.label}
                    onClick={(e) => { e.stopPropagation(); closeChat(c.id); }}>
                    <IcX size={11} />
                  </span>
                )}
              </button>
            ))}
            <button type="button" className="mcc-prompt-iconbtn" style={{ width: 26, height: 26 }}
              aria-label="New session" title={"New session on " + fs.layer} onClick={newChat}>
              <IcxPlus size={14} />
            </button>
            <span className="mcc-ftabs-spacer"></span>
            {fileTabs.map((p) => (
              <button key={p} type="button" draggable={mode === "workspace"}
                className={"mcc-ftab mcc-ftab--in" + (fileActive(p) ? " is-active" : "")}
                onClick={() => clickFileTab(p)}
                onDragStart={(e) => { e.dataTransfer.setData("text/plain", p); e.dataTransfer.effectAllowed = "move"; setDragging(p); }}
                onDragEnd={() => { setDragging(null); setOverDrop(false); }}
                title={MCC_FS_DOCS[p] ? MCC_FS_DOCS[p].crumb + " · drag toward the chat to split" : p}>
                <IcDoc size={13} />
                <span className="mcc-ftab-name">{p.split("/").pop()}</span>
                <span className="mcc-ftab-x" role="button" aria-label={"Close " + p}
                  onClick={(e) => { e.stopPropagation(); closeFile(p); }}>
                  <IcX size={11} />
                </span>
              </button>
            ))}
            <button type="button" className={"mcc-prompt-iconbtn" + (fsOpen ? " is-on" : "")} style={{ width: 26, height: 26 }}
              aria-label="Toggle file pane" title={fsOpen ? "Hide files" : "Show files"} onClick={() => setFsOpen(!fsOpen)}>
              <IcMlPanel size={14} />
            </button>
          </div>

          <div className="mcc-mlrow" style={{ gridTemplateColumns: (mode === "mission" ? "minmax(420px, 1fr) minmax(340px, " + cols.chat + "px)" : (shut ? "44px" : cols.dock + "px") + " minmax(0, 1fr)") + (fsOpen ? " " + cols.fs + "px" : "") }}>
            {mode === "mission" ? (
              <div className="mcc-mlcenter">
                {view.kind === "file" ? <MccFsDoc path={view.path} /> : <MccMissionPlane />}
              </div>
            ) : (
              <MccMcDock shut={shut} onToggle={() => setShut(!shut)} resize={startDrag("dock", 1)} />
            )}
            {mode === "mission" ? (
              <div className="mcc-chatside" data-screen-label="Chat docked right">
                <div className="mcc-coldrag mcc-coldrag--left" onMouseDown={startDrag("chat", -1)} title="Drag to resize"></div>
                <MccChatPane session={session} layer={fs.layer} chatLen={chatLen} rail={rail} />
              </div>
            ) : (
            <div className="mcc-mlcenter">
              {split ? (
                <div className="mcc-split" style={{ gridTemplateColumns: "minmax(0, 1fr) " + cols.split + "px" }}>
                  <MccChatPane session={session} layer={fs.layer} chatLen={chatLen} rail={rail} />
                  <div className="mcc-splitpane" data-screen-label="Split file pane">
                    <div className="mcc-coldrag mcc-coldrag--left" onMouseDown={startDrag("split", -1)} title="Drag to resize"></div>
                    <div className="mcc-splitpane-head">
                      <IcDoc size={13} />
                      <span className="mcc-ftab-name">{split.split("/").pop()}</span>
                      <button className="mcc-panel-close" type="button" aria-label="Close split"
                        onClick={() => { setSplit(null); setView({ kind: "chat" }); }}>
                        <IcX size={13} />
                      </button>
                    </div>
                    <MccFsDoc path={split} />
                  </div>
                </div>
              ) : view.kind === "chat" ? (
                <MccChatPane session={session} layer={fs.layer} chatLen={chatLen} rail={rail} />
              ) : (
                <MccFsDoc path={view.path} />
              )}
              {dragging && !split && mode === "workspace" && (
                <div className={"mcc-dropzone" + (overDrop ? " is-over" : "")}
                  onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setOverDrop(true); }}
                  onDragLeave={() => setOverDrop(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    const p = e.dataTransfer.getData("text/plain") || dragging;
                    setSplit(p); setView({ kind: "chat" }); setDragging(null); setOverDrop(false);
                  }}>
                  <span>Drop to view beside the chat</span>
                </div>
              )}
            </div>
            )}
            {fsOpen && (
              <div className="mcc-rpane">
                <div className="mcc-coldrag mcc-coldrag--left" onMouseDown={startDrag("fs", -1)} title="Drag to resize"></div>
                <MccFilePane entries={fs.entries()} label={fs.label}
                  location={fs.location} worktree={fs.worktree}
                  openPath={split || (view.kind === "file" ? view.path : null)} onOpen={openFile} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MccMaestroLoop() { return <MccMaestroLoopV2 initialScope="root" />; }
function MccMaestroLoopFolder() { return <MccMaestroLoopV2 initialScope="core" />; }
function MccMaestroLoopMission() { return <MccMaestroLoopV2 initialMode="mission" />; }

// ── The storyboard · ticks accumulate, the queue grows ───────────────────
function MccLoopStory() {
  const steps = [
    {
      label: "tick 09:15 · dispatched 2, nothing for you",
      cap: "The loop moves on its own. No decisions pending: the queue is an all-clear line, the prompt is just a prompt.",
      items: [],
    },
    {
      label: "tick 09:45 · a worker returned, judged clean",
      cap: "First stopgap: the run is at your gate. Maestro renders the decision above the prompt · chat stays the only surface.",
      items: [MCC_ML_GATE[0]],
    },
    {
      label: "tick 10:15 · the import hit a missing scope",
      cap: "Second stopgap stacks beneath the first; the header now says what the pile is costing (3 queued items wait). Clear them in queue order or just talk.",
      items: MCC_ML_GATE,
    },
  ];
  return (
    <div className="mcc-pad" style={{ gap: 12 }}>
      {steps.map((s) => (
        <div key={s.label} className="mcc-cmp-study">
          <div className="mcc-cmp-study-label">{s.label}</div>
          <div className="mcc-ml-step">
            <MccGateQueue items={s.items} mini />
            <MccPromptPlate mini hint={null} placeholder="Message maestro…" />
          </div>
          <p className="mcc-caption">{s.cap}</p>
        </div>
      ))}
    </div>
  );
}

Object.assign(window, { MccMaestroLoop, MccMaestroLoopFolder, MccMaestroLoopMission, MccMaestroLoopV2, MccLoopStory, MccGateQueue, MccTickCard, MccMcDock, MccMissionPlane, MccMaestroChat, MccChatPane, MCC_ML_FS });
