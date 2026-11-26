// Agent Pad: a prompt pad wired to the host's agent harnesses. Everything
// native goes through window.agentApp, which the host gates per permission.
const $ = (id) => document.getElementById(id);
const api = window.agentApp;
let runs = 0;
let current = null;
let starting = false;
let early = []; // events that arrive before agent.run() has returned the runId

function print(text, cls) {
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = text;
  $("out").append(span);
  $("out").scrollTop = $("out").scrollHeight;
}

async function refresh() {
  const info = await api.info();
  $("version").textContent = `v${info.version} · ${info.harness}`;
  $("perms").replaceChildren(
    ...info.declared.map((p) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `perm${info.granted.includes(p) ? " on" : ""}`;
      b.textContent = p;
      b.title = info.granted.includes(p) ? "granted for this version" : "click to request";
      b.onclick = () => api.permissions.request(p).then(refresh, (e) => print(`${e.message}\n`, "err"));
      return b;
    }),
  );
}

function handle(e) {
  if (e.type === "text") print(e.text);
  else if (e.type === "tool") print(`\n⚙ ${e.name}\n`, "tool");
  else if (e.type === "error") print(`\n${e.message}\n`, "err");
  else if (e.type === "done") {
    print(e.ok ? "\n— done\n" : `\n— failed: ${e.summary}\n`, e.ok ? "" : "err");
    current = null;
    $("run").disabled = false;
    $("cancel").disabled = true;
    api.notification
      .show({ title: "Agent Pad", body: e.ok ? "The agent finished." : "The agent failed." })
      .catch(() => {});
    api.tray.set({ title: "✦ idle" }).catch(() => {});
    refresh();
  }
}

api.agent.onEvent((e) => {
  if (starting && !current) early.push(e);
  else if (e.runId === current) handle(e);
});

api.onHostEvent((e) => {
  if (e.type === "version-changed")
    print(`\n↻ app changed (${e.from} → ${e.to}); reloading, grants reset\n`, "tool");
});

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = $("prompt").value.trim();
  if (!prompt) return;
  $("out").textContent = "";
  $("run").disabled = true;
  starting = true;
  early = [];
  try {
    current = await api.agent.run({ prompt, harness: $("harness").value, edit: $("edit").checked });
    runs += 1;
    $("cancel").disabled = false;
    api.dock.setBadge(String(runs)).catch(() => {});
    api.tray.set({ title: "✦ working…" }).catch(() => {});
    const replay = early.filter((e) => e.runId === current);
    early = [];
    for (const e of replay) handle(e);
  } catch (e) {
    print(`${e.message}\n`, "err");
    $("run").disabled = false;
  } finally {
    starting = false;
  }
  refresh();
});

$("cancel").addEventListener("click", () => current && api.agent.cancel(current));

// The global shortcut is registered only once "shortcuts" is granted, so the
// app does not open with a permission prompt.
api.globalShortcut.onPressed(() => $("prompt").focus());
api.info().then((info) => {
  if (info.granted.includes("shortcuts"))
    api.globalShortcut.register("CommandOrControl+Shift+Space").catch(() => {});
});
refresh();
