// Runs in the app's main frame only (sandboxed, context-isolated). Exposes
// window.agentApp: every method is one IPC call the host checks against the
// capability table, the manifest, the grants and the app version.
const { contextBridge, ipcRenderer } = require("electron");

const call = (module, method, ...args) =>
  ipcRenderer.invoke("agent-app:call", { module, method, args }).then((r) => {
    if (r.ok) return r.value;
    // contextBridge copies only an Error's message, so the code rides in it.
    // Read the code back with /^([A-Z]+): / on error.message.
    throw new Error(r.code ? `${r.code}: ${r.message}` : r.message);
  });

const listeners = { agent: new Set(), shortcut: new Set(), host: new Set() };
ipcRenderer.on("agent-app:event", (_event, payload) => {
  for (const cb of listeners[payload.kind] ?? []) {
    try {
      cb(payload);
    } catch (e) {
      console.error(e);
    }
  }
});
const subscribe = (kind) => (cb) => {
  listeners[kind].add(cb);
  return () => listeners[kind].delete(cb);
};

contextBridge.exposeInMainWorld("agentApp", {
  info: () => call("app", "info"),
  window: {
    setTitle: (title) => call("window", "setTitle", title),
    getBounds: () => call("window", "getBounds"),
    setBounds: (bounds) => call("window", "setBounds", bounds),
  },
  dock: {
    setBadge: (text) => call("dock", "setBadge", text),
    bounce: () => call("dock", "bounce"),
  },
  notification: { show: (opts) => call("notification", "show", opts) },
  tray: {
    set: (opts) => call("tray", "set", opts),
    remove: () => call("tray", "remove"),
  },
  globalShortcut: {
    register: (accelerator) => call("globalShortcut", "register", accelerator),
    unregisterAll: () => call("globalShortcut", "unregisterAll"),
    onPressed: subscribe("shortcut"),
  },
  permissions: {
    state: () => call("permissions", "state"),
    request: (permission) => call("permissions", "request", permission),
  },
  agent: {
    run: (opts) => call("agent", "run", opts),
    cancel: (runId) => call("agent", "cancel", runId),
    onEvent: subscribe("agent"),
  },
  onHostEvent: subscribe("host"),
  fs: {
    readFile: (file) => call("fs", "readFile", file),
    writeFile: (file, text) => call("fs", "writeFile", file, text),
    readdir: (dir) => call("fs", "readdir", dir),
  },
});
