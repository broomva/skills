// A starter agent-native app. Everything native goes through window.agentApp;
// the host checks each call against app.json and your grants for this version.
//
// The agent is the harness named in app.json. With "t3" it is a T3 thread that
// this app keeps talking to, so it remembers earlier turns and shows up in T3.
const $ = (id) => document.getElementById(id);
const api = window.agentApp;
let current = null;
let starting = false;
let early = [];

function print(text, cls) {
  const el = document.createElement("div");
  if (cls) el.className = cls;
  el.textContent = text;
  $("log").append(el);
  $("log").scrollTop = $("log").scrollHeight;
}

async function refresh() {
  const info = await api.info();
  $("meta").textContent = `${info.harness}${info.t3Thread ? " · thread kept" : ""} · v${info.version.slice(0, 8)}`;
}

function handle(e) {
  if (e.type === "text") print(e.text);
  else if (e.type === "tool") print(`⚙ ${e.name}`, "tool");
  else if (e.type === "error") print(e.message, "err");
  else if (e.type === "done") {
    if (!e.ok) print(`failed: ${e.summary}`, "err");
    current = null;
    $("send").disabled = false;
    $("stop").disabled = true;
    $("status").textContent = "";
    api.dock.bounce().catch(() => {});
    refresh();
  }
}

api.agent.onEvent((e) => {
  if (starting && !current) early.push(e);
  else if (e.runId === current) handle(e);
});

api.onHostEvent((e) => {
  if (e.type === "version-changed") print("↻ this app changed; reloading. Permissions will be asked again.", "tool");
});

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = $("prompt").value.trim();
  if (!prompt) return;
  print(prompt, "you");
  $("prompt").value = "";
  $("send").disabled = true;
  $("status").textContent = "working…";
  starting = true;
  early = [];
  try {
    current = await api.agent.run({ prompt });
    $("stop").disabled = false;
    const replay = early.filter((e) => e.runId === current);
    early = [];
    for (const e of replay) handle(e);
  } catch (e) {
    print(e.message, "err");
    $("send").disabled = false;
    $("status").textContent = "";
  } finally {
    starting = false;
  }
});

$("stop").addEventListener("click", () => current && api.agent.cancel(current));
refresh();
