// Maestro · sidebar (the workspace tree + autonomy footer) + legacy top bar.
// Composes the standard components (DsAvatar, DsButton, DsAutonomyScoreboard)
// via ds-adapter.jsx instead of re-implementing them.

const IcFolder = (p) => <McIcon {...p}><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"></path></McIcon>;
const IcFolderOpen = (p) => <McIcon {...p}><path d="m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H18a2 2 0 0 1 2 2v2"></path></McIcon>;

function McAvatar({ name, color, size = 22 }) {
  // Thin projection over the standard Avatar · keeps the app-local name.
  return <DsAvatar name={name} color={color} size={size} />;
}

function McSidebar({ attention, initiativeCounts, items = WK_ITEMS }) {
  // The nav is the workspace itself: folders at any depth, live sessions as
  // dot comets, autonomy halts as badges. Initiative → folder, project →
  // subfolder (shown only while it has live or halted work).
  const sbText = { flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "left" };
  const folders = WK_INITIATIVES.map((init) => {
    const list = items.filter((i) => i.initiative === init.id);
    const projects = [...new Set(list.map((i) => i.project))]
      .map((p) => {
        const pl = list.filter((i) => i.project === p);
        return {
          name: p,
          live: pl.some((i) => i.state === "running"),
          attn: pl.filter((i) => WK_ATTENTION.includes(i.state)).length,
        };
      })
      .filter((p) => p.live || p.attn > 0);
    return {
      id: init.id,
      done: list.filter((i) => i.state === "done").length,
      total: list.length,
      projects,
    };
  });
  return (
    <aside className="bv-sidebar" data-screen-label="Sidebar">
      <button className="bv-ws-switch" type="button">
        <img className="bv-ws-logo" src="../../assets/broomva-blackhole-logo.png" alt="" />
        <span className="bv-ws-name">Broomva</span>
        <IcChevrons size={14} />
      </button>

      <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <button className="bv-sb-item is-active" type="button">
          <IcBoard />Maestro
          {attention > 0 && <span className="bv-sb-badge">{attention}</span>}
        </button>
        <button className="bv-sb-item" type="button"><IcDoc />Docs</button>
      </nav>

      <div className="bv-sb-section-label">Workspace</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {folders.map((f) => (
          <React.Fragment key={f.id}>
            <button className="bv-sb-item" type="button">
              {f.projects.length > 0 ? <IcFolderOpen size={14} /> : <IcFolder size={14} />}
              <span style={sbText}>{f.id}</span>
              <span className="mc-init-progress">{f.done}/{f.total}</span>
            </button>
            {f.projects.map((p) => (
              <button key={p.name} className="bv-sb-item" type="button" style={{ paddingLeft: 28 }}>
                {p.live
                  ? <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span>
                  : <IcFolder size={13} />}
                <span style={sbText}>{p.name}</span>
                {p.attn > 0 && <span className="bv-sb-badge">{p.attn}</span>}
              </button>
            ))}
          </React.Fragment>
        ))}
      </div>

      <div className="bv-sb-spacer"></div>

      <DsAutonomyScoreboard
        title="Unsupervised hours today · each notch is a human look"
        hours="6h 24m" sub="2 looks · longest run 3h 50m"
        segments={[{ start: 0, width: 34 }, { start: 36, width: 42 }, { start: 80, width: 14, live: true }]}
        notches={[34, 78]}
      />

      <button className="bv-sb-item" type="button">
        <McAvatar name="Ana Diaz" color="var(--bv-gray-600)" size={18} />
        <span style={{ flex: 1, textAlign: "left" }}>Ana Diaz</span>
      </button>
    </aside>
  );
}

function McTopBar({ theme, onToggleTheme, onTick, ticking, canTick, onShowIdea }) {
  return (
    <header className="bv-top-bar" data-screen-label="Top bar">
      <div className="mc-topbar-left">
        <span>Maestro</span>
      </div>
      <div className="mc-topbar-right">
        <span className="mc-runner-pill" title="The armed runner · the seam the scheduler dispatches through">
          <span className="mc-runner-dot"></span>
          runner <code>claude</code> · worktrees 2/2
        </span>
        <DsButton size="sm" variant="secondary"
          onClick={onTick} disabled={ticking || !canTick}
          title="One scheduler tick: observe, decide, act, judge, commit">
          <IcPlay size={16} />{ticking ? "Ticking" : "Tick"}
        </DsButton>
        <DsButton size="sm" variant="soft" onClick={onShowIdea}>
          The idea
        </DsButton>
        <button className="bv-icon-btn" type="button" onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Switch to light" : "Switch to dark"}
          title={theme === "dark" ? "Switch to light" : "Switch to dark"}>
          {theme === "dark" ? <IcSun size={18} /> : <IcMoon size={18} />}
        </button>
      </div>
    </header>
  );
}

Object.assign(window, { McAvatar, McSidebar, McTopBar, IcFolder, IcFolderOpen });
