// The Settings page · "the engine room": runners, credentials, autonomy,
// routines, notifications, appearance, members. A full-page frame on the
// canonical BvNavTree (same chrome as History / Knowledge). Two layouts,
// toggled in the top bar: a two-pane section nav, and a single editorial
// scroll with a sticky table of contents.

// ── Local icons (built on the global McIcon) ──────────────────────────────
const IcCpu = (p) => <McIcon {...p}><rect x="4" y="4" width="16" height="16" rx="2"></rect><rect x="9" y="9" width="6" height="6"></rect><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"></path></McIcon>;
const IcKey = (p) => <McIcon {...p}><circle cx="7.5" cy="15.5" r="4.5"></circle><path d="m10.7 12.3 8.3-8.3M16 6l3 3M14 8l2 2"></path></McIcon>;
const IcSliders = (p) => <McIcon {...p}><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"></path></McIcon>;
const IcClock = (p) => <McIcon {...p}><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></McIcon>;
const IcBell = (p) => <McIcon {...p}><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"></path><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"></path></McIcon>;
const IcPalette = (p) => <McIcon {...p}><circle cx="13.5" cy="6.5" r="1.5"></circle><circle cx="17.5" cy="10.5" r="1.5"></circle><circle cx="8.5" cy="7.5" r="1.5"></circle><circle cx="6.5" cy="12.5" r="1.5"></circle><path d="M12 2a10 10 0 0 0 0 20 2.5 2.5 0 0 0 2-4 2.5 2.5 0 0 1 2-4h2a4 4 0 0 0 4-4 10 10 0 0 0-10-8Z"></path></McIcon>;
const IcShield = (p) => <McIcon {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"></path></McIcon>;
const IcLink = (p) => <McIcon {...p}><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"></path><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"></path></McIcon>;
const IcPlus = (p) => <McIcon {...p}><path d="M12 5v14M5 12h14"></path></McIcon>;

function SetSwitch({ on, onClick }) {
  // Thin projection over the standard Switch.
  return <DsSwitch checked={on} onChange={onClick} />;
}
function SetStepper({ value, set, min = 0, max = 99, suffix }) {
  return (
    <div className="set-stepper">
      <button type="button" disabled={value <= min} onClick={() => set(Math.max(min, value - 1))}>−</button>
      <span className="set-stepper-val">{value}{suffix ? <span style={{ fontWeight: 400, color: "var(--muted-foreground)" }}> {suffix}</span> : null}</span>
      <button type="button" disabled={value >= max} onClick={() => set(Math.min(max, value + 1))}>+</button>
    </div>
  );
}
function SetSeg({ value, set, options }) {
  // Thin projection over the standard Segmented (kit options are [value, label] pairs).
  return <DsSegmented value={value} onChange={set} options={options.map(([v, label]) => ({ value: v, label }))} />;
}
function SetSlider({ value, set, min, max, step = 1, fmt }) {
  return (
    <div className="set-slider">
      <input className="set-range" type="range" min={min} max={max} step={step} value={value} onChange={(e) => set(Number(e.target.value))} />
      <span className="set-slider-val">{fmt(value)}</span>
    </div>
  );
}

const SET_SECTIONS = [
  { id: "runners",   label: "Runners & worktrees", short: "Runners",     icon: <IcCpu /> },
  { id: "creds",     label: "Credentials & scopes", short: "Credentials", icon: <IcKey />, badge: 1 },
  { id: "autonomy",  label: "Autonomy defaults",    short: "Autonomy",    icon: <IcSliders /> },
  { id: "routines",  label: "Routines & wake",      short: "Routines",    icon: <IcClock /> },
  { id: "notify",    label: "Notifications",        short: "Notifications", icon: <IcBell /> },
  { id: "appearance",label: "Appearance",           short: "Appearance",  icon: <IcPalette /> },
  { id: "members",   label: "Workspace & members",  short: "Members",     icon: <IcUsers /> },
];

const CREDS = [
  { name: "GitHub", glyph: "GH", desc: "hawthorne · 4 repos", scopes: ["repo", "workflow", "read:org"], status: "ok" },
  { name: "Linear", glyph: "LN", desc: "Import cycles · blocking 1 run", scopes: ["read", "write?"], miss: "write", status: "warn" },
  { name: "Anthropic API", glyph: "AI", desc: "runner claude · sonnet + opus", scopes: ["messages", "batches"], status: "ok" },
  { name: "Obsidian vault", glyph: "OB", desc: "the conversation bridge writes here", scopes: ["local fs"], status: "ok" },
  { name: "Slack", glyph: "SL", desc: "not connected", scopes: [], status: "off" },
];

const ROUTINES = [
  { name: "Nightly digest", when: "daily · 02:00", on: true },
  { name: "Morning briefing", when: "weekdays · 07:30", on: true },
  { name: "Linear import", when: "every 6h", on: false },
];
const WAKES = [
  { name: "On push to main", desc: "review + queue follow-up work", on: true },
  { name: "On new issue", desc: "triage into the right folder", on: true },
  { name: "On credential restored", desc: "retry the runs it blocked", on: true },
];
const MEMBERS = [
  { name: "Ana Diaz", role: "Owner", email: "ana@broomva.ai", color: "var(--bv-gray-600)" },
  { name: "Theo Park", role: "Operator", email: "theo@broomva.ai", color: "var(--bv-blue)" },
  { name: "Maya Lin", role: "Viewer", email: "maya@broomva.ai", color: "var(--bv-purple, #7c6cf0)" },
];

function MccSettings({ onOpenView, theme, onSetTheme, density, onSetDensity, blue, onSetBlue }) {
  const [layout, setLayout] = React.useState("twopane"); // twopane | scroll
  const [active, setActive] = React.useState("runners");

  // engine-room state
  const [runner, setRunner] = React.useState("claude");
  const [worktrees, setWorktrees] = React.useState(2);
  const [sandbox, setSandbox] = React.useState("both");
  const [concurrency, setConcurrency] = React.useState(3);
  const [autoClean, setAutoClean] = React.useState(true);
  const [budget, setBudget] = React.useState(20);
  const [gate, setGate] = React.useState("risk");
  const [cascade, setCascade] = React.useState(2);
  const [spend, setSpend] = React.useState(40);
  const [routines, setRoutines] = React.useState(ROUTINES.map((r) => r.on));
  const [wakes, setWakes] = React.useState(WAKES.map((w) => w.on));
  const [notif, setNotif] = React.useState({ app: true, email: true, slack: false });
  const [pingWhen, setPingWhen] = React.useState("blocks");

  const Section = ({ id }) => {
    switch (id) {
      case "runners": return (
        <div className="set-section" id="set-runners">
          <div className="set-section-head">
            <div className="set-section-title"><IcCpu size={17} />Runners & worktrees</div>
            <div className="set-section-sub">The armed seam the scheduler dispatches through, and how many checkouts can run at once.</div>
          </div>
          <div className="set-panel">
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Default runner</span><span className="set-field-desc">The model the loop arms by default. Per-folder overrides win.</span></div>
              <div className="set-field-control"><SetSeg value={runner} set={setRunner} options={[["claude", "claude"], ["codex", "codex"], ["local", "local"]]} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Worktrees per runner</span><span className="set-field-desc">Parallel git checkouts a single runner can hold.</span></div>
              <div className="set-field-control"><SetStepper value={worktrees} set={setWorktrees} min={1} max={6} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Where work runs</span><span className="set-field-desc">Local machine, an ephemeral cloud sandbox, or whichever is free.</span></div>
              <div className="set-field-control"><SetSeg value={sandbox} set={setSandbox} options={[["local", "Local"], ["cloud", "Cloud"], ["both", "Both"]]} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Concurrency cap</span><span className="set-field-desc">Most sessions live at once across the whole workspace.</span></div>
              <div className="set-field-control"><SetStepper value={concurrency} set={setConcurrency} min={1} max={12} suffix="live" /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Auto-clean merged worktrees</span><span className="set-field-desc">Drop a checkout once its branch lands.</span></div>
              <div className="set-field-control"><SetSwitch on={autoClean} onClick={() => setAutoClean(!autoClean)} /></div>
            </div>
          </div>
        </div>
      );
      case "creds": return (
        <div className="set-section" id="set-creds">
          <div className="set-section-head">
            <div className="set-section-title"><IcKey size={17} />Credentials & scopes</div>
            <div className="set-section-sub">The thing that blocks runs. A missing scope halts the loop until a human grants it.</div>
          </div>
          <div className="set-panel">
            {CREDS.map((c) => (
              <div className="set-field" key={c.name}>
                <span className="set-rowglyph" style={{ fontSize: 11, fontWeight: 600, fontFamily: "var(--bv-font-mono, monospace)" }}>{c.glyph}</span>
                <div className="set-field-main">
                  <span className="set-field-label">{c.name}</span>
                  <span className="set-field-desc">{c.desc}</span>
                  {c.scopes.length > 0 && (
                    <div className="set-scopes" style={{ marginTop: 4 }}>
                      {c.scopes.map((s) => <span key={s} className={"set-scope" + (s.endsWith("?") ? " set-scope--miss" : "")}>{s.replace("?", "")}{s.endsWith("?") ? " · missing" : ""}</span>)}
                    </div>
                  )}
                </div>
                <div className="set-field-control" style={{ flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
                  <span className={"set-status set-status--" + c.status}><span className="set-status-dot"></span>{c.status === "ok" ? "connected" : c.status === "warn" ? "needs scope" : "off"}</span>
                  <DsButton size="sm" variant="secondary">{c.status === "off" ? "Connect" : c.status === "warn" ? "Grant write" : "Manage"}</DsButton>
                </div>
              </div>
            ))}
          </div>
          <DsButton size="sm" variant="soft" style={{ alignSelf: "flex-start" }}><IcPlus size={16} />Add credential</DsButton>
        </div>
      );
      case "autonomy": return (
        <div className="set-section" id="set-autonomy">
          <div className="set-section-head">
            <div className="set-section-title"><IcSliders size={17} />Autonomy defaults</div>
            <div className="set-section-sub">How far the loop runs before it has to come back to your gate.</div>
          </div>
          <div className="set-panel">
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Weekly budget</span><span className="set-field-desc">Unsupervised hours the loop may spend before pausing for review.</span></div>
              <div className="set-field-control"><SetSlider value={budget} set={setBudget} min={0} max={60} fmt={(v) => v + " h / wk"} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Gate policy</span><span className="set-field-desc">When a session needs you. <code>Ask on risk</code> stops only at irreversible steps.</span></div>
              <div className="set-field-control"><SetSeg value={gate} set={setGate} options={[["ask", "Ask first"], ["risk", "Ask on risk"], ["free", "Run free"]]} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Cascade depth</span><span className="set-field-desc">How many levels deep maestro may spawn sub-agents.</span></div>
              <div className="set-field-control"><SetStepper value={cascade} set={setCascade} min={0} max={5} suffix="levels" /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Spend cap</span><span className="set-field-desc">Hard ceiling on model + sandbox cost per week.</span></div>
              <div className="set-field-control"><SetSlider value={spend} set={setSpend} min={0} max={200} step={5} fmt={(v) => "$" + v + " / wk"} /></div>
            </div>
          </div>
        </div>
      );
      case "routines": return (
        <div className="set-section" id="set-routines">
          <div className="set-section-head">
            <div className="set-section-title"><IcClock size={17} />Routines & wake triggers</div>
            <div className="set-section-sub">Standing loops on a schedule, and the events that wake the orchestrator.</div>
          </div>
          <div className="set-panel">
            {ROUTINES.map((r, i) => (
              <div className="set-field" key={r.name}>
                <span className="set-rowglyph"><IcClock size={16} /></span>
                <div className="set-field-main"><span className="set-field-label">{r.name}</span><span className="set-field-desc">{r.when}</span></div>
                <div className="set-field-control"><span className="mc-receipt">routine</span><SetSwitch on={routines[i]} onClick={() => setRoutines(routines.map((v, j) => j === i ? !v : v))} /></div>
              </div>
            ))}
          </div>
          <div className="set-panel">
            {WAKES.map((w, i) => (
              <div className="set-field" key={w.name}>
                <div className="set-field-main"><span className="set-field-label">{w.name}</span><span className="set-field-desc">{w.desc}</span></div>
                <div className="set-field-control"><SetSwitch on={wakes[i]} onClick={() => setWakes(wakes.map((v, j) => j === i ? !v : v))} /></div>
              </div>
            ))}
          </div>
        </div>
      );
      case "notify": return (
        <div className="set-section" id="set-notify">
          <div className="set-section-head">
            <div className="set-section-title"><IcBell size={17} />Notifications</div>
            <div className="set-section-sub">When and where the loop pings you · kept quiet by default.</div>
          </div>
          <div className="set-panel">
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">In-app</span><span className="set-field-desc">The <b>Needs you</b> lens badge.</span></div>
              <div className="set-field-control"><SetSwitch on={notif.app} onClick={() => setNotif({ ...notif, app: !notif.app })} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Email</span><span className="set-field-desc">ana@broomva.ai</span></div>
              <div className="set-field-control"><SetSwitch on={notif.email} onClick={() => setNotif({ ...notif, email: !notif.email })} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Slack</span><span className="set-field-desc">Connect Slack in Credentials first.</span></div>
              <div className="set-field-control"><SetSwitch on={notif.slack} onClick={() => setNotif({ ...notif, slack: !notif.slack })} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Ping me when</span><span className="set-field-desc">Every halt is chatty; <code>Only blocks</code> waits for a real wall.</span></div>
              <div className="set-field-control"><SetSeg value={pingWhen} set={setPingWhen} options={[["halt", "Every halt"], ["blocks", "Only blocks"], ["digest", "Daily digest"]]} /></div>
            </div>
          </div>
        </div>
      );
      case "appearance": return (
        <div className="set-section" id="set-appearance">
          <div className="set-section-head">
            <div className="set-section-title"><IcPalette size={17} />Appearance</div>
            <div className="set-section-sub">These write through to the live app right now.</div>
          </div>
          <div className="set-panel">
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Theme</span><span className="set-field-desc">Calm monochrome, light or dark.</span></div>
              <div className="set-field-control"><SetSeg value={theme} set={onSetTheme} options={[["light", "Light"], ["dark", "Dark"]]} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Density</span><span className="set-field-desc">Calm gives cards room; dense packs the feed.</span></div>
              <div className="set-field-control"><SetSeg value={density} set={onSetDensity} options={[["calm", "Calm"], ["dense", "Dense"]]} /></div>
            </div>
            <div className="set-field">
              <div className="set-field-main"><span className="set-field-label">Blue intensity</span><span className="set-field-desc">How much the ai-blue glow tints frost, shadow and the Undertow.</span></div>
              <div className="set-field-control"><SetSlider value={blue} set={onSetBlue} min={0} max={2} step={0.1} fmt={(v) => v.toFixed(1) + "×"} /></div>
            </div>
          </div>
        </div>
      );
      case "members": return (
        <div className="set-section" id="set-members">
          <div className="set-section-head">
            <div className="set-section-title"><IcUsers size={17} />Workspace & members</div>
            <div className="set-section-sub">Who shares this orchestration plane, and what they can do.</div>
          </div>
          <div className="set-panel">
            <div className="set-field set-field--stacked">
              <span className="set-field-label">Workspace name</span>
              <input className="set-input set-input--full" defaultValue="Broomva" />
            </div>
          </div>
          <div className="set-panel">
            {MEMBERS.map((m) => (
              <div className="set-field" key={m.email}>
                <McAvatar name={m.name} color={m.color} size={32} />
                <div className="set-field-main"><span className="set-field-label">{m.name}</span><span className="set-field-desc">{m.email}</span></div>
                <div className="set-field-control"><SetSeg value={m.role} set={() => {}} options={[["Owner", "Owner"], ["Operator", "Operator"], ["Viewer", "Viewer"]]} /></div>
              </div>
            ))}
          </div>
          <DsButton size="sm" variant="soft" style={{ alignSelf: "flex-start" }}><IcPlus size={16} />Invite member</DsButton>
        </div>
      );
      default: return null;
    }
  };

  return (
    <div className="mcc-fill">
      <div className="bv-app" style={{ gridTemplateColumns: bvNavGrid() }}>
        <BvNavTree active="settings" inApp onNav={onOpenView} />
        <div className="bv-main">
          <header className="bv-top-bar" data-screen-label="Settings · top bar">
            <div className="mc-topbar-left"><IcSettings size={17} /><span style={{ color: "var(--foreground)", fontWeight: 600 }}>Settings</span><span style={{ color: "var(--muted-foreground)" }}>· the engine room</span></div>
            <div className="set-topright">
              <span className="set-saved"><IcCheck size={14} />Saved</span>
              <DsSegmented value={layout} onChange={setLayout}
                options={[{ value: "twopane", label: "Two-pane" }, { value: "scroll", label: "One scroll" }]} />
            </div>
          </header>

          {layout === "twopane" ? (
            <div className="set-twopane" data-screen-label="Settings · two-pane">
              <nav className="set-secnav">
                <div className="set-secnav-label">Engine room</div>
                {SET_SECTIONS.map((s) => (
                  <button key={s.id} type="button" className={"set-secnav-btn" + (active === s.id ? " is-active" : "")} onClick={() => setActive(s.id)}>
                    {React.cloneElement(s.icon, { size: 16 })}<span>{s.label}</span>
                    {s.badge ? <span className="set-secnav-badge">{s.badge}</span> : null}
                  </button>
                ))}
              </nav>
              <div className="set-content">
                <div className="set-content-inner"><Section id={active} /></div>
              </div>
            </div>
          ) : (
            <div className="set-scrollwrap" data-screen-label="Settings · one scroll">
              <div className="set-scrollgrid">
                <div className="set-scrollmain">
                  {SET_SECTIONS.map((s, i) => (
                    <div key={s.id} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                      <div className="set-bignum">{String(i + 1).padStart(2, "0")}</div>
                      <Section id={s.id} />
                    </div>
                  ))}
                </div>
                <aside className="set-toc">
                  <div className="set-toc-label">On this page</div>
                  {SET_SECTIONS.map((s, i) => (
                    <a key={s.id} href={"#set-" + s.id} className={"set-toc-btn" + (i === 0 ? " is-active" : "")}>
                      <span className="set-toc-num">{String(i + 1).padStart(2, "0")}</span><span>{s.short}</span>
                    </a>
                  ))}
                </aside>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MccSettings });
