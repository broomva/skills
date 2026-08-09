// The account / user page · clicking the "Ana Diaz" row in the sidebar footer.
// Center of gravity: who you are and, in this product, your autonomy score —
// how much work ran without you. Full-page frame on the canonical BvNavTree.
// Two views, toggled in the top bar: an Overview dashboard, and an editable
// Account page (identity · preferences · security). Reuses globals defined by
// ConceptSettings (IcKey, IcShield, IcLink, SetSwitch, SetSeg) · loaded first.

const IcPencil = (p) => <McIcon {...p}><path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path></McIcon>;
const IcLogOut = (p) => <McIcon {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><path d="M16 17l5-5-5-5"></path><path d="M21 12H9"></path></McIcon>;
const IcLaptop = (p) => <McIcon {...p}><rect x="3" y="4" width="18" height="12" rx="2"></rect><path d="M2 20h20"></path></McIcon>;
const IcPhone = (p) => <McIcon {...p}><rect x="7" y="2" width="10" height="20" rx="2"></rect><path d="M11 18h2"></path></McIcon>;

const USR_WEEK = [
  { d: "Mon", h: 4.1 }, { d: "Tue", h: 6.4 }, { d: "Wed", h: 2.0 },
  { d: "Thu", h: 7.6, peak: true }, { d: "Fri", h: 5.2 }, { d: "Sat", h: 1.1 }, { d: "Sun", h: 4.8 },
];

function MccUser({ onOpenView }) {
  const [view, setView] = React.useState("overview"); // overview | account
  const maxH = Math.max(...USR_WEEK.map((d) => d.h));

  // Your sessions vs the loop's · drawn from the shared History dataset.
  const mine = (typeof HIST_SESSIONS !== "undefined" ? HIST_SESSIONS : []).slice(0, 6);

  const IdentityHeader = ({ big }) => (
    <div className="usr-id">
      <div className="usr-id-avatar">
        <McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={big ? 76 : 64} />
      </div>
      <div className="usr-id-meta">
        <div className="usr-id-name">Ana Diaz</div>
        <div className="usr-id-line">
          <span className="usr-role">Operator · Owner</span>
          <span className="usr-id-sep"></span>
          <span>ana@broomva.ai</span>
          <span className="usr-id-sep"></span>
          <span>joined Mar 2025</span>
        </div>
      </div>
      <DsButton size="sm" variant="secondary" onClick={() => setView("account")}><IcPencil size={16} />Edit profile</DsButton>
    </div>
  );

  return (
    <div className="mcc-fill">
      <div className="bv-app" style={{ gridTemplateColumns: bvNavGrid() }}>
        <BvNavTree active="user" inApp onNav={onOpenView} />
        <div className="bv-main">
          <header className="bv-top-bar" data-screen-label="Account · top bar">
            <div className="mc-topbar-left">
              <McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={20} />
              <span style={{ color: "var(--foreground)", fontWeight: 600 }}>Ana Diaz</span>
            </div>
            <div className="set-topright">
              <span className="mc-runner-pill"><span className="mc-runner-dot"></span>31h 12m unsupervised this week</span>
              <DsSegmented value={view} onChange={setView}
                options={[{ value: "overview", label: "Overview" }, { value: "account", label: "Account" }]} />
            </div>
          </header>

          {view === "overview" ? (
            <div className="usr-wrap" data-screen-label="Account · overview">
              <div className="usr-inner">
                <IdentityHeader big />

                {/* Autonomy score hero */}
                <div className="usr-score">
                  <div className="usr-score-head">
                    <span className="usr-score-title">Your autonomy score</span>
                    <span className="usr-score-sub">the number this product is really about · how long work ran without you</span>
                  </div>
                  <div className="usr-score-stats">
                    <div className="usr-stat">
                      <div className="usr-stat-val">31<small>h</small> 12<small>m</small></div>
                      <div className="usr-stat-label">Unsupervised this week</div>
                      <div className="usr-stat-foot">+18% vs last week</div>
                    </div>
                    <div className="usr-stat">
                      <div className="usr-stat-val">9</div>
                      <div className="usr-stat-label">Times you had to look</div>
                      <div className="usr-stat-foot">2 today · mostly scope grants</div>
                    </div>
                    <div className="usr-stat">
                      <div className="usr-stat-val">3<small>h</small> 50<small>m</small></div>
                      <div className="usr-stat-label">Longest single run</div>
                      <div className="usr-stat-foot">M1b execution loop · Tue</div>
                    </div>
                  </div>
                  <div className="usr-week">
                    <div className="usr-week-bars">
                      {USR_WEEK.map((d) => (
                        <div className="usr-week-day" key={d.d}>
                          <div className={"usr-week-bar" + (d.peak ? " is-peak" : "")} style={{ height: Math.round((d.h / maxH) * 56) + "px" }} title={d.h + "h"}></div>
                          <span className="usr-week-lab">{d.d}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Two columns: your sessions + preferences */}
                <div className="usr-cols">
                  <div className="usr-card">
                    <div className="usr-card-head">
                      <span className="usr-card-head-title">Your sessions</span>
                      <button type="button" className="usr-card-link" onClick={() => onOpenView && onOpenView("history")}>Open History →</button>
                    </div>
                    {mine.map((s) => (
                      <button type="button" className="usr-sess" key={s.id} onClick={() => onOpenView && onOpenView("history")}>
                        {s.state === "live"
                          ? <span className="mcc-dot-tide" style={{ width: 12, height: 12 }}></span>
                          : <span className="mc-chip-dot" style={{ width: 8, height: 8, background: s.state === "halt" ? "var(--bv-blue-accent)" : s.state === "blocked" ? "var(--bv-warning)" : "var(--bv-success)" }}></span>}
                        <span className="usr-sess-body">
                          <span className="usr-sess-title">{s.title}</span>
                          <span className="usr-sess-meta">{s.folder.split(" / ").slice(-1)[0]} · {s.dur}</span>
                        </span>
                        <span className={"usr-sess-kind usr-sess-kind--" + (s.kind === "you" ? "you" : "loop")}>{s.kind === "you" ? "you" : "loop"}</span>
                      </button>
                    ))}
                  </div>

                  <div className="usr-card">
                    <div className="usr-card-head"><span className="usr-card-head-title">Preferences</span></div>
                    <div className="usr-prow">
                      <div className="usr-prow-main"><span className="usr-prow-label">Start view</span><span className="usr-prow-desc">Where the app opens</span></div>
                      <div className="usr-prow-control"><SetSeg value="needs" set={() => {}} options={[["needs", "Needs you"], ["mc", "Mission"]]} /></div>
                    </div>
                    <div className="usr-prow">
                      <div className="usr-prow-main"><span className="usr-prow-label">Default runner</span><span className="usr-prow-desc">For sessions you start</span></div>
                      <div className="usr-prow-control"><SetSeg value="claude" set={() => {}} options={[["claude", "claude"], ["codex", "codex"]]} /></div>
                    </div>
                    <div className="usr-prow">
                      <div className="usr-prow-main"><span className="usr-prow-label">Digest email</span><span className="usr-prow-desc">A morning summary of overnight work</span></div>
                      <div className="usr-prow-control"><SetSwitch on={true} onClick={() => {}} /></div>
                    </div>
                    <div className="usr-prow">
                      <div className="usr-prow-main"><span className="usr-prow-label">Show autonomy clock</span><span className="usr-prow-desc">In the sidebar footer</span></div>
                      <div className="usr-prow-control"><SetSwitch on={true} onClick={() => {}} /></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="usr-wrap" data-screen-label="Account · account">
              <div className="usr-inner">
                <IdentityHeader />

                {/* Editable identity */}
                <div className="usr-card">
                  <div className="usr-card-head"><span className="usr-card-head-title">Identity</span><span className="mc-receipt">syncs to your profile</span></div>
                  <div className="usr-form">
                    <div className="usr-form-field"><label className="usr-form-label">Full name</label><input className="set-input" defaultValue="Ana Diaz" /></div>
                    <div className="usr-form-field"><label className="usr-form-label">Display name</label><input className="set-input" defaultValue="Ana" /></div>
                    <div className="usr-form-field"><label className="usr-form-label">Email</label><input className="set-input" defaultValue="ana@broomva.ai" /></div>
                    <div className="usr-form-field"><label className="usr-form-label">Role</label><input className="set-input" defaultValue="Operator" disabled style={{ opacity: 0.6 }} /></div>
                    <div className="usr-form-field usr-form-field--full"><label className="usr-form-label">Timezone</label><input className="set-input set-input--full" defaultValue="America/Mexico_City (GMT−6)" /></div>
                  </div>
                </div>

                {/* Personal preferences */}
                <div className="usr-card">
                  <div className="usr-card-head"><span className="usr-card-head-title">Personal preferences</span></div>
                  <div className="usr-prow">
                    <div className="usr-prow-main"><span className="usr-prow-label">Theme</span><span className="usr-prow-desc">Overrides the workspace default for you</span></div>
                    <div className="usr-prow-control"><SetSeg value="system" set={() => {}} options={[["light", "Light"], ["dark", "Dark"], ["system", "System"]]} /></div>
                  </div>
                  <div className="usr-prow">
                    <div className="usr-prow-main"><span className="usr-prow-label">Keyboard shortcuts</span><span className="usr-prow-desc"><code>⌘K</code> command · <code>g h</code> History · <code>g k</code> Knowledge</span></div>
                    <div className="usr-prow-control"><SetSwitch on={true} onClick={() => {}} /></div>
                  </div>
                  <div className="usr-prow">
                    <div className="usr-prow-main"><span className="usr-prow-label">Reduced motion</span><span className="usr-prow-desc">Calm the Undertow and tidepool animations</span></div>
                    <div className="usr-prow-control"><SetSwitch on={false} onClick={() => {}} /></div>
                  </div>
                </div>

                {/* Security */}
                <div className="usr-card">
                  <div className="usr-card-head"><span className="usr-card-head-title">Security</span></div>
                  <div className="usr-prow">
                    <div className="usr-prow-main"><span className="usr-prow-label">Sign-in method</span><span className="usr-prow-desc">Google · ana@broomva.ai · passkey enabled</span></div>
                    <div className="usr-prow-control"><DsButton size="sm" variant="secondary">Manage</DsButton></div>
                  </div>
                  <div className="usr-prow">
                    <div className="usr-prow-main"><span className="usr-prow-label">API keys</span><span className="usr-prow-desc"><code>brm_live_••••4f2a</code> · 2 active</span></div>
                    <div className="usr-prow-control"><DsButton size="sm" variant="secondary"><IcKey size={16} />Keys</DsButton></div>
                  </div>
                </div>

                {/* Active sessions */}
                <div className="usr-card">
                  <div className="usr-card-head"><span className="usr-card-head-title">Where you're signed in</span></div>
                  <div className="usr-dev">
                    <span className="set-rowglyph"><IcLaptop size={16} /></span>
                    <div className="usr-dev-body"><span className="usr-dev-name">MacBook Pro · Chrome <span className="usr-here">this device</span></span><span className="usr-dev-meta">Mexico City · active now</span></div>
                  </div>
                  <div className="usr-dev">
                    <span className="set-rowglyph"><IcPhone size={16} /></span>
                    <div className="usr-dev-body"><span className="usr-dev-name">iPhone 15 · Broomva PWA</span><span className="usr-dev-meta">Mexico City · 2h ago</span></div>
                    <button type="button" className="usr-danger">Revoke</button>
                  </div>
                  <div className="usr-dev">
                    <span className="set-rowglyph"><IcLaptop size={16} /></span>
                    <div className="usr-dev-body"><span className="usr-dev-name">Linux · cloud sandbox runner</span><span className="usr-dev-meta">us-east · 6h ago</span></div>
                    <button type="button" className="usr-danger">Revoke</button>
                  </div>
                </div>

                <DsButton size="sm" variant="secondary" style={{ alignSelf: "flex-start", color: "var(--bv-danger)" }}><IcLogOut size={16} />Sign out</DsButton>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MccUser });
