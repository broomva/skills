// Broomva Maestro · the mobile + tablet shell.
// Chat-first: the maestro conversation is the home surface, the gate queue
// rides above the prompt. Three primary surfaces · Chat · Mission · Files.
// The phone navigation *model* is selectable (`nav` prop / Tweaks panel). All
// keep the frosted-glass language; they differ in the underlying interaction:
//   · "page"  · surfaces are swipeable pages; a carousel indicator up top
//   · "sheet" · chat is the canvas; Mission & Files rise as pull-up sheets
//   · "menu"  · the header title is a "Chat ▾" popover switcher
//   · "edge"  · a slim vertical glass rail pinned to the right edge
// (legacy: "tray" / "top" / "orbit" kept for reference.)
// Tablets always use the right-edge side rail. The workspace tree is an
// off-canvas drawer. Reuses the desktop chat / plane / file components verbatim
// · only the chrome is phone-shaped.

const IcMlMenu = (p) => <McIcon {...p}><path d="M4 6h16"></path><path d="M4 12h16"></path><path d="M4 18h16"></path></McIcon>;
const IcMlBack = (p) => <McIcon {...p}><path d="m12 19-7-7 7-7"></path><path d="M19 12H5"></path></McIcon>;
const IcMlFiles = (p) => <McIcon {...p}><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"></path></McIcon>;
const IcMlChev = (p) => <McIcon {...p}><path d="m6 9 6 6 6-6"></path></McIcon>;

// mobile (<768) · tablet (768–1023) · desktop (≥1024)
function useBvViewport() {
  const get = () => {
    if (typeof window === "undefined") return "desktop";
    // ?vp=mobile|tablet|desktop forces a layout (for previewing on a wide canvas).
    try {
      const f = new URLSearchParams(location.search).get("vp");
      if (f === "mobile" || f === "tablet" || f === "desktop") return f;
    } catch (e) {}
    const w = window.innerWidth;
    return w < 768 ? "mobile" : w < 1024 ? "tablet" : "desktop";
  };
  const [vp, setVp] = React.useState(get);
  React.useEffect(() => {
    let raf = 0;
    const onR = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => setVp(get())); };
    window.addEventListener("resize", onR);
    window.addEventListener("orientationchange", onR);
    return () => { window.removeEventListener("resize", onR); window.removeEventListener("orientationchange", onR); cancelAnimationFrame(raf); };
  }, []);
  return vp;
}

// The Files surface · the pane (browse) or a single doc (read).
function MccMobileFiles({ fs, openFile, setOpenFile }) {
  if (openFile) return <MccFsDoc path={openFile} />;
  return (
    <MccFilePane entries={fs.entries()} label={fs.label}
      location={fs.location} worktree={fs.worktree}
      openPath={null} onOpen={setOpenFile} />
  );
}

// Files as a full pane · browse, or read one doc with a back affordance.
function MccFilesPane({ fs, openFile, setOpenFile }) {
  return (
    <section className="bvm-pane bvm-pane--files" data-screen-label="Files (mobile)">
      {openFile ? (
        <>
          <div className="bvm-panehead">
            <button className="bvm-iconbtn" type="button" aria-label="Back to files"
              onClick={() => setOpenFile(null)} style={{ marginLeft: 0 }}>
              <IcMlBack size={20} />
            </button>
            <span className="bvm-panehead-title">{openFile.split("/").pop()}</span>
          </div>
          <div className="bvm-pane-scroll"><MccFsDoc path={openFile} /></div>
        </>
      ) : (
        <MccMobileFiles fs={fs} openFile={null} setOpenFile={setOpenFile} />
      )}
    </section>
  );
}

function MccMobileShell({ mode = "mobile", theme = "light", onToggleTheme, nav = "page", sheetTrigger = "peek" }) {
  const [tab, setTab] = React.useState("chat");      // chat | mission | files
  const [drawer, setDrawer] = React.useState(false);
  const [scope, setScope] = React.useState("root");
  const [openFile, setOpenFile] = React.useState(null);
  const [orbit, setOrbit] = React.useState(false);   // legacy orbit switcher
  const [sheetSurf, setSheetSurf] = React.useState(null); // sheet model: null|mission|files
  const [menuOpen, setMenuOpen] = React.useState(false);  // menu model popover
  const bodyRef = React.useRef(null);
  const pagerLock = React.useRef(false);
  const noop = () => {};

  const fs = MCC_ML_FS[scope] || MCC_ML_FS.root;
  const isTablet = mode === "tablet";
  // ?nav=… forces a model (preview without the panel), mirroring ?vp. Tablets
  // always use the right-edge side rail; the phone `nav` tweak governs phones.
  let navPref = nav;
  try {
    const f = new URLSearchParams(location.search).get("nav");
    if (["page", "sheet", "menu", "edge", "tray", "top", "orbit"].includes(f)) navPref = f;
  } catch (e) {}
  const navMode = isTablet ? "rail" : navPref;

  // Sheet-model trigger treatment (how Mission/Files are surfaced). Only used
  // when navMode === "sheet". ?strig= overrides for preview.
  let strig = sheetTrigger;
  try {
    const f = new URLSearchParams(location.search).get("strig");
    if (["peek", "dock", "edge", "icons"].includes(f)) strig = f;
  } catch (e) {}

  // The three primary surfaces · shared by every nav model.
  const surfaces = [
    { id: "chat", icon: <IcChat size={21} />, label: "Chat", badge: "2" },
    { id: "mission", icon: <IcBoard size={21} />, label: "Mission" },
    { id: "files", icon: <IcMlFiles size={21} />, label: "Files" },
  ];
  const dockIdx = Math.max(0, surfaces.findIndex((s) => s.id === tab));
  const active = surfaces.find((s) => s.id === tab) || surfaces[0];

  // The two surfaces that rise as sheets over the chat canvas.
  const sheetSurfaces = [
    { id: "mission", label: "Mission", icon: <IcBoard size={20} />, count: "2", hint: "2 awaiting" },
    { id: "files", label: "Files", icon: <IcMlFiles size={20} />, count: null, hint: "~/Broomva" },
  ];

  // Lock body scroll while a full overlay is open.
  React.useEffect(() => {
    const open = drawer || orbit || sheetSurf || menuOpen;
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [drawer, orbit, sheetSurf, menuOpen]);

  React.useEffect(() => { setOrbit(false); setMenuOpen(false); }, [tab]);

  // ── Pager model: keep horizontal scroll position synced with `tab` ──
  React.useEffect(() => {
    if (navMode !== "page") return;
    const el = bodyRef.current; if (!el) return;
    const i = surfaces.findIndex((s) => s.id === tab);
    el.scrollLeft = i * el.clientWidth;          // jump on mount / model switch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navMode]);
  React.useEffect(() => {
    if (navMode !== "page") return;
    if (pagerLock.current) { pagerLock.current = false; return; }
    const el = bodyRef.current; if (!el) return;
    const i = surfaces.findIndex((s) => s.id === tab);
    el.scrollTo({ left: i * el.clientWidth, behavior: "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, navMode]);
  const onPagerScroll = () => {
    if (navMode !== "page") return;
    const el = bodyRef.current; if (!el) return;
    const i = Math.round(el.scrollLeft / el.clientWidth);
    const id = surfaces[i] && surfaces[i].id;
    if (id && id !== tab) { pagerLock.current = true; setTab(id); }
  };

  const goScope = (s) => { setScope(s); setOpenFile(null); setDrawer(false); };
  const goMission = () => { pick("mission"); setDrawer(false); };

  // The one surface-selection entry point · behaves per model.
  function pick(id) {
    if (navMode === "sheet") { setSheetSurf(id === "chat" ? null : id); return; }
    setTab(id); setOrbit(false); setMenuOpen(false);
  }

  const sub = scope === "root" ? "~/Broomva · 2 live" : fs.location;
  const title = tab === "mission" ? "The plane" : tab === "files" ? "Files" : "Maestro";

  // Header center varies by model.
  let headerCenter;
  if (navMode === "top") {
    headerCenter = (
      <nav className="bvm-topseg" role="tablist" aria-label="Surface"
        style={{ "--seg-idx": dockIdx, "--seg-n": surfaces.length }}>
        <span className="bvm-topseg-pill" aria-hidden="true"></span>
        {surfaces.map((s) => (
          <button key={s.id} role="tab" aria-selected={tab === s.id}
            className={"bvm-topseg-btn" + (tab === s.id ? " is-active" : "")}
            type="button" onClick={() => pick(s.id)}>
            <span className="bvm-topseg-ico">{s.icon}</span>
            <span className="bvm-topseg-lbl">{s.label}</span>
            {s.badge && tab !== s.id ? <span className="bvm-topseg-badge">{s.badge}</span> : null}
          </button>
        ))}
      </nav>
    );
  } else if (navMode === "menu") {
    // Title becomes a dropdown switcher.
    headerCenter = (
      <button className={"bvm-titlebtn" + (menuOpen ? " is-open" : "")} type="button"
        aria-haspopup="true" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}>
        <span className="bvm-titlebtn-ico">{active.icon}</span>
        <span className="bvm-titlebtn-txt">{title}</span>
        <span className="bvm-titlebtn-chev"><IcMlChev size={16} /></span>
        {tab !== "chat" ? <span className="bvm-titlebtn-badge">2</span> : null}
      </button>
    );
  } else if (navMode === "sheet" && strig === "icons") {
    // Minimal: clean icon buttons live in the top-actions row (below); the
    // header center stays as the plain identity block.
    headerCenter = (
      <div className="bvm-top-id">
        <img className="bvm-top-logo" src="../../assets/broomva-blackhole-logo.png" alt="" />
        <div className="bvm-top-titles">
          <span className="bvm-top-title">{title}</span>
          <span className="bvm-top-sub">{sub}</span>
        </div>
      </div>
    );
  } else {
    headerCenter = (
      <div className="bvm-top-id">
        <img className="bvm-top-logo" src="../../assets/broomva-blackhole-logo.png" alt="" />
        <div className="bvm-top-titles">
          <span className="bvm-top-title">{title}</span>
          <span className="bvm-top-sub">{sub}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bvm" data-mode={mode} data-tab={tab} data-nav={navMode} data-strig={strig}
      data-drawer={drawer ? "open" : "shut"} data-orbit={orbit ? "open" : "shut"}
      data-sheet={sheetSurf ? "open" : "shut"} data-menu={menuOpen ? "open" : "shut"}>

      {/* ── Top bar ── */}
      <header className="bvm-top" data-screen-label="Mobile top bar">
        <button className="bvm-iconbtn" type="button" aria-label="Open workspace" onClick={() => setDrawer(true)}>
          <IcMlMenu size={21} />
        </button>
        {headerCenter}
        <div className="bvm-top-actions">
          {navMode === "sheet" && strig === "icons" && (
            <div className="bvm-sicons" role="group" aria-label="Surfaces">
              {sheetSurfaces.map((s) => (
                <button key={s.id} type="button"
                  className={"bvm-iconbtn bvm-sicon" + (sheetSurf === s.id ? " is-active" : "")}
                  aria-label={"Open " + s.label} onClick={() => setSheetSurf(s.id)}>
                  {s.icon}
                  {s.count ? <span className="bvm-sicon-badge">{s.count}</span> : null}
                </button>
              ))}
              <span className="bvm-sicons-div" aria-hidden="true"></span>
            </div>
          )}
          <button className="bvm-iconbtn" type="button" aria-label="Toggle theme" onClick={onToggleTheme || noop}>
            {theme === "dark" ? <IcSun size={19} /> : <IcMoon size={19} />}
          </button>
        </div>

        {/* Menu-model popover hangs off the header */}
        {navMode === "menu" && (
          <>
            <div className="bvm-menu-scrim" onClick={() => setMenuOpen(false)}></div>
            <div className="bvm-navmenu" role="menu">
            {surfaces.map((s) => (
              <button key={s.id} role="menuitemradio" aria-checked={tab === s.id}
                className={"bvm-navmenu-item" + (tab === s.id ? " is-active" : "")}
                type="button" onClick={() => pick(s.id)}>
                <span className="bvm-navmenu-ico">{s.icon}</span>
                <span className="bvm-navmenu-lbl">{s.label}</span>
                {s.badge && tab !== s.id ? <span className="bvm-navmenu-badge">{s.badge}</span> : null}
                {tab === s.id ? <span className="bvm-navmenu-dot" aria-hidden="true"></span> : null}
              </button>
            ))}
          </div>
          </>
        )}
      </header>

      {/* Pager carousel indicator · sits just under the header */}
      {navMode === "page" && (
        <div className="bvm-pager" role="tablist" aria-label="Surface">
          {surfaces.map((s) => (
            <button key={s.id} role="tab" aria-selected={tab === s.id}
              className={"bvm-pager-seg" + (tab === s.id ? " is-active" : "")}
              type="button" onClick={() => pick(s.id)}>
              <span className="bvm-pager-ico">{s.icon}</span>
              <span className="bvm-pager-lbl">{s.label}</span>
              {s.badge && tab !== s.id ? <span className="bvm-pager-badge">{s.badge}</span> : null}
            </button>
          ))}
        </div>
      )}

      {/* ── Body · the panes ── */}
      <div className="bvm-body" ref={bodyRef} onScroll={onPagerScroll}>
        <section className="bvm-pane bvm-pane--chat" data-screen-label="Maestro (mobile)">
          <MccMaestroChat layer={fs.layer} />
        </section>
        <section className="bvm-pane bvm-pane--mission" data-screen-label="Mission plane (mobile)">
          <MccMissionPlane />
        </section>
        <MccFilesPane fs={fs} openFile={openFile} setOpenFile={setOpenFile} />
      </div>

      {/* ── Edge rail ── */}
      {navMode === "edge" && (
        <nav className="bvm-edge" data-screen-label="Edge rail"
          style={{ "--eidx": dockIdx, "--en": surfaces.length }}>
          <span className="bvm-edge-pill" aria-hidden="true"></span>
          {surfaces.map((s) => (
            <button key={s.id} className={"bvm-edge-btn" + (tab === s.id ? " is-active" : "")}
              type="button" aria-label={s.label} onClick={() => pick(s.id)}>
              <span className="bvm-edge-ico">{s.icon}</span>
              {s.badge && tab !== s.id ? <span className="bvm-edge-badge">{s.badge}</span> : null}
            </button>
          ))}
        </nav>
      )}

      {/* ── Sheet model · trigger treatments + the rising sheet ── */}
      {navMode === "sheet" && (
        <>
          {/* Trigger: Peek · the two sheets rest as thin cards above the composer */}
          {strig === "peek" && (
            <div className="bvm-peek" data-screen-label="Peek triggers">
              {sheetSurfaces.map((s) => (
                <button key={s.id} type="button" className="bvm-peek-card"
                  onClick={() => setSheetSurf(s.id)}>
                  <span className="bvm-peek-grab" aria-hidden="true"></span>
                  <span className="bvm-peek-ico">{s.icon}</span>
                  <span className="bvm-peek-lbl">{s.label}</span>
                  <span className="bvm-peek-hint">{s.hint}</span>
                  {s.count ? <span className="bvm-peek-badge">{s.count}</span> : null}
                  <span className="bvm-peek-up"><IcMlChev size={15} /></span>
                </button>
              ))}
            </div>
          )}

          {/* Trigger: Dock · a slim launcher bar above the composer */}
          {strig === "dock" && (
            <div className="bvm-sdock" data-screen-label="Dock triggers">
              {sheetSurfaces.map((s) => (
                <button key={s.id} type="button" className="bvm-sdock-chip"
                  onClick={() => setSheetSurf(s.id)}>
                  <span className="bvm-sdock-ico">{s.icon}</span>
                  <span className="bvm-sdock-lbl">{s.label}</span>
                  {s.count ? <span className="bvm-sdock-badge">{s.count}</span> : null}
                </button>
              ))}
            </div>
          )}

          {/* Trigger: Edge · vertical pull-tabs on the right edge */}
          {strig === "edge" && (
            <div className="bvm-stabs" data-screen-label="Edge pull-tabs">
              {sheetSurfaces.map((s) => (
                <button key={s.id} type="button" className="bvm-stab"
                  onClick={() => setSheetSurf(s.id)}>
                  <span className="bvm-stab-ico">{s.icon}</span>
                  <span className="bvm-stab-lbl">{s.label}</span>
                  {s.count ? <span className="bvm-stab-badge">{s.count}</span> : null}
                </button>
              ))}
            </div>
          )}

          <div className="bvm-sheet-scrim" onClick={() => setSheetSurf(null)}></div>
          <div className="bvm-sheet" data-screen-label="Pull-up sheet">
            <div className="bvm-sheet-grab" onClick={() => setSheetSurf(null)}>
              <span className="bvm-sheet-bar" aria-hidden="true"></span>
            </div>
            <div className="bvm-sheet-body">
              {sheetSurf === "mission" && <MccMissionPlane />}
              {sheetSurf === "files" && <MccFilesPane fs={fs} openFile={openFile} setOpenFile={setOpenFile} />}
            </div>
          </div>
        </>
      )}

      {/* ── Legacy models: tray / rail / orbit ── */}
      {(navMode === "tray" || navMode === "rail") && (
        <nav className="bvm-dock" data-screen-label={navMode === "rail" ? "Side rail" : "Bottom tray"}
          style={{ "--bvm-idx": dockIdx, "--bvm-n": surfaces.length }}>
          <span className="bvm-dock-glow" aria-hidden="true"></span>
          <span className="bvm-dock-pill" aria-hidden="true"></span>
          {surfaces.map((s) => (
            <button key={s.id} className={"bvm-tab" + (tab === s.id ? " is-active" : "")}
              type="button" onClick={() => pick(s.id)}>
              <span className="bvm-tab-ico">{s.icon}</span>
              <span className="bvm-tab-lbl">{s.label}</span>
              {s.badge ? <span className="bvm-tab-badge">{s.badge}</span> : null}
            </button>
          ))}
        </nav>
      )}
      {navMode === "orbit" && (
        <>
          <div className="bvm-orbit-scrim" onClick={() => setOrbit(false)}></div>
          <div className="bvm-orbit" data-screen-label="Orbit switcher">
            <div className="bvm-orbit-stack">
              {surfaces.map((s, i) => (
                <button key={s.id} className={"bvm-orbit-item" + (tab === s.id ? " is-active" : "")}
                  type="button" style={{ "--oi": surfaces.length - 1 - i }}
                  onClick={() => pick(s.id)}>
                  <span className="bvm-orbit-lbl">{s.label}</span>
                  <span className="bvm-orbit-ico">{s.icon}</span>
                  {s.badge && tab !== s.id ? <span className="bvm-orbit-badge">{s.badge}</span> : null}
                </button>
              ))}
            </div>
            <button className="bvm-orbit-fab" type="button"
              aria-label={orbit ? "Close switcher" : "Switch surface"} aria-expanded={orbit}
              onClick={() => setOrbit((v) => !v)}>
              <span className="bvm-orbit-fab-ico">{orbit ? <IcX size={22} /> : active.icon}</span>
              {!orbit && tab !== "chat" ? <span className="bvm-tab-badge">2</span> : null}
            </button>
          </div>
        </>
      )}

      {/* ── Drawer · the workspace tree ── */}
      <div className="bvm-scrim" onClick={() => setDrawer(false)}></div>
      <aside className="bvm-drawer" data-screen-label="Workspace drawer">
        <MccTcSidebar scope={tab === "mission" ? "__none" : scope} setScope={goScope}
          onMission={goMission} missionActive={tab === "mission"} />
      </aside>
    </div>
  );
}

Object.assign(window, { useBvViewport, MccMobileShell });
