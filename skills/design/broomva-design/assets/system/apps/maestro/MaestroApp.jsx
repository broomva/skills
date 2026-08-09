// Maestro v4 · the maestro loop, promoted from the concepts canvas.
// One layout, two states: Maestro grows the plane (feed/board/list,
// chat docked right); clicking a workspace/folder collapses it to the dock
// and the conversation takes center. Tabs and the FS pane never move.
// All fixed columns drag to resize; the FS pane and dock yield responsively.

const MC4_TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "calm",
  "blue": 1,
  "chatLen": "short",
  "rail": "quiet",
  "mobileNav": "sheet"
}/*EDITMODE-END*/;

function Mc4App() {
  const [t, setTweak] = useTweaks(MC4_TWEAK_DEFAULTS);
  const [theme, setTheme] = React.useState("light");
  const [view, setView] = React.useState("app"); // app | knowledge | history | settings | user
  const [feedbackOpen, setFeedbackOpen] = React.useState(false);
  const [cmdOpen, setCmdOpen] = React.useState(false);
  const vp = useBvViewport();
  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");
  const openView = (id) => {
    if (id === "feedback") { setFeedbackOpen(true); return; }
    setView(
      id === "knowledge" ? "knowledge"
      : id === "history" ? "history"
      : id === "settings" ? "settings"
      : id === "user" ? "user"
      : "app"
    );
  };
  const FB_CONTEXT = { app: "Maestro", knowledge: "Knowledge", history: "History", settings: "Settings", user: "Ana Diaz" };

  // ⌘K is global; the shared command field (on every page) dispatches an event.
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); setCmdOpen((v) => !v); }
    };
    const onOpen = () => setCmdOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("bv:command-open", onOpen);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("bv:command-open", onOpen); };
  }, []);

  React.useEffect(() => {
    const el = document.documentElement;
    el.setAttribute("data-theme", theme);
    el.setAttribute("data-density", t.density);
    el.style.setProperty("--bv-blue-mult", String(t.blue));
    // Keep the PWA status-bar colour in step with the theme.
    const meta = document.querySelector('meta[name="theme-color"]:not([media])');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#16151f" : "#ffffff");
  }, [theme, t.density, t.blue]);

  return (
    <>
      {vp === "desktop" ? (
        view === "knowledge" ? <MccKnowledge onOpenView={openView} theme={theme} onToggleTheme={toggleTheme} />
        : view === "history" ? <MccHistory onOpenView={openView} theme={theme} onToggleTheme={toggleTheme} />
        : view === "settings" ? <MccSettings onOpenView={openView}
            theme={theme} onSetTheme={setTheme}
            density={t.density} onSetDensity={(v) => setTweak("density", v)}
            blue={t.blue} onSetBlue={(v) => setTweak("blue", v)} />
        : view === "user" ? <MccUser onOpenView={openView} />
        : <MccMaestroLoopV2 app={true} initialMode="mission" theme={theme} onToggleTheme={toggleTheme} onOpenView={openView} chatLen={t.chatLen} rail={t.rail} />
      ) : (
        <MccMobileShell mode={vp} theme={theme} onToggleTheme={toggleTheme} nav={t.mobileNav} sheetTrigger="icons" />
      )}
      <MccCommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} onNav={openView} context={view} />
      <MccFeedback open={feedbackOpen} onClose={() => setFeedbackOpen(false)} context={FB_CONTEXT[view] || "Maestro"} />
      <TweaksPanel>
        <TweakSection label="Layout" />
        <TweakRadio label="Density" value={t.density}
          options={["calm", "dense"]}
          onChange={(v) => setTweak("density", v)} />
        <TweakSection label="Conversation" />
        <TweakRadio label="Length" value={t.chatLen}
          options={["short", "stress", "extreme"]}
          onChange={(v) => setTweak("chatLen", v)} />
        <TweakRadio label="Dispatch rail" value={t.rail}
          options={[{ value: "quiet", label: "Quiet" }, { value: "full", label: "Full" }]}
          onChange={(v) => setTweak("rail", v)} />
        <TweakSection label="Mobile nav" />
        <TweakRadio label="Model" value={t.mobileNav}
          options={[{ value: "sheet", label: "Sheets" }, { value: "page", label: "Pager" }, { value: "menu", label: "Menu" }, { value: "edge", label: "Edge" }]}
          onChange={(v) => setTweak("mobileNav", v)} />
        <TweakSection label="Color" />
        <TweakSlider label="Blue intensity" value={t.blue} min={0} max={2} step={0.1}
          onChange={(v) => setTweak("blue", v)} />
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<Mc4App />);
