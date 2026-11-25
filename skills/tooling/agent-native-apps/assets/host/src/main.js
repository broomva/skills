// The host: one Electron main process that serves every installed app.
//
//   electron . install <appDir>     write the app's shim .app, then serve
//   electron . uninstall <id>       remove its shim and grants
//   electron . grant <id> <perm..>  grant permissions for the app's current version
//   electron . list                 print installed apps (read locally, never forwarded)
//   electron .                      serve (also what a shim launches when the host is down)
//
// Flags: --home=<dir> (state; default <appData>/agent-native-apps), --apps-dir=<dir>
// (where shim bundles go; default ~/Applications/Agent Native Apps), --max-tier=1|2|3
// (policy ceiling; persisted into every shim it writes), --selftest (run the bridge
// scenario in each app window; every prompt is denied).

import { execFile } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import {
  app,
  BrowserWindow,
  dialog,
  globalShortcut,
  ipcMain,
  Menu,
  Notification,
  nativeImage,
  net,
  protocol,
  session,
  Tray,
} from "electron";
import { checkForwardedConfig, hostConfig, parseArgs, resolveCommand } from "./args.js";
import { hostInfo, icnsFromPngs, writeShimBundle } from "./bundle.js";
import {
  authorizeAfterPrompt,
  CapabilityError,
  decide,
  guardAsyncLaunch,
  PERMISSIONS,
  requiredPermission,
  tierOf,
} from "./capabilities.js";
import { cancelRunsOnQuit, resolveUserPath, runHarness, which } from "./harness.js";
import { readManifest, servableFile, validModel, validProvider, versionOf } from "./manifest.js";
import { Registry } from "./registry.js";
import { runSelftest } from "./selftest.js";

const run = promisify(execFile);
const SRC = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SRC, "..");
const SCHEME = "agentapp";
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "frame-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

// ---------------------------------------------------------------- configuration

let config;
let command;
let cliFlags = {};
try {
  const { flags, positional } = parseArgs(process.argv.slice(app.isPackaged ? 1 : 2));
  cliFlags = flags;
  // In dev the first positional is the app root Electron was given.
  if (!app.isPackaged && positional[0] && path.resolve(positional[0]) === APP_ROOT) positional.shift();
  config = hostConfig(flags, {
    defaultHome: path.join(app.getPath("appData"), "agent-native-apps"),
    defaultAppsDir: path.join(os.homedir(), "Applications", "Agent Native Apps"),
  });
  command = resolveCommand(positional, process.cwd());
} catch (e) {
  console.error(e.message);
  app.exit(2);
}
const { home: HOME, appsDir: APPS_DIR, maxTier: MAX_TIER, selftest: SELFTEST } = config ?? {};
const SERVER_NAME = `agent-native-apps-${createHash("sha256")
  .update(HOME ?? "")
  .digest("hex")
  .slice(0, 8)}`;

if (config) {
  fs.mkdirSync(HOME, { recursive: true, mode: 0o700 });
  app.setPath("userData", path.join(HOME, "electron"));
}
const LOG = HOME && path.join(HOME, "host.log");

export function log(event, data = {}) {
  const line = JSON.stringify({ at: new Date().toISOString(), pid: process.pid, event, ...data });
  fs.appendFileSync(LOG, `${line}\n`);
  console.log(line);
}

protocol.registerSchemesAsPrivileged([
  { scheme: SCHEME, privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

let registry;
if (config) {
  try {
    registry = new Registry(HOME);
  } catch (e) {
    console.error(e.message);
    app.exit(2);
  }
}

// `list` is read locally, so it prints here even when a host is running.
if (config && registry && command[0] === "list") {
  for (const a of registry.apps()) console.log(`${a.id}\t${a.name}\t${a.bundlePath}`);
  app.exit(0);
}

/** installId -> running app state */
const running = new Map();
/** webContents id -> installId */
const byContents = new Map();
/** accelerator -> installId: one owner per global shortcut, host-wide */
const shortcutOwners = new Map();

// ---------------------------------------------------------------- install

function slug(name) {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 24) || "app"
  );
}

async function renderIcon(glyph) {
  // Draw the Dock icon in an offscreen page: a rounded square and the glyph.
  // The frame comes from the offscreen `paint` event; capturePage on an
  // offscreen window can stall, so this never waits more than a few seconds.
  const win = new BrowserWindow({
    show: false,
    width: 1024,
    height: 1024,
    transparent: true,
    webPreferences: { offscreen: true, partition: "agent-app-icon", javascript: false },
  });
  const html = `<html><body style="margin:0;width:1024px;height:1024px;display:grid;place-items:center;background:transparent">
<div style="width:824px;height:824px;border-radius:185px;display:grid;place-items:center;
background:linear-gradient(145deg,#4f46e5,#0ea5e9);
font:600 460px -apple-system,system-ui;color:white">${glyph.replace(/[<&>"']/g, "")}</div></body></html>`;
  try {
    let loaded = false;
    const painted = new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("the icon did not paint in 4 s")), 4000);
      win.webContents.on("paint", (_event, _dirty, image) => {
        if (!loaded || image.isEmpty()) return;
        clearTimeout(timer);
        resolve(image);
      });
    });
    painted.catch(() => {}); // handled by the await below; avoid an unhandled rejection if loadURL throws first
    win.webContents.setFrameRate(30);
    await win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
    loaded = true;
    win.webContents.invalidate();
    const image = await painted;
    const pngBySize = {};
    for (const size of [32, 64, 128, 256, 512, 1024]) {
      pngBySize[size] = image.resize({ width: size, height: size, quality: "best" }).toPNG();
    }
    return icnsFromPngs(pngBySize);
  } finally {
    win.destroy();
  }
}

async function install(appDir) {
  const manifest = readManifest(appDir);
  versionOf(appDir); // refuse an app whose folder cannot be hashed (symlinks, size)
  const existing = registry.apps().find((a) => a.appDir === appDir);
  const id = existing?.id ?? `${slug(manifest.name)}-${randomBytes(3).toString("hex")}`;
  const { hostPath, hostBundleId, loaderPath } = hostInfo();
  fs.mkdirSync(APPS_DIR, { recursive: true });
  const bundlePath = path.join(APPS_DIR, `${manifest.name}.app`);
  const owner = registry.bundleOwner(bundlePath, id);
  if (owner) {
    throw new Error(
      `"${manifest.name}.app" already belongs to ${owner.id} (${owner.appDir}); rename the app.`,
    );
  }
  const ownedBySelf = existing?.bundlePath === bundlePath;
  if (!ownedBySelf && fs.existsSync(bundlePath)) {
    throw new Error(
      `"${manifest.name}.app" already exists at ${bundlePath} and is not managed by this host; rename the app or choose another --apps-dir.`,
    );
  }
  if (existing && existing.bundlePath !== bundlePath) {
    fs.rmSync(existing.bundlePath, { recursive: true, force: true }); // the app was renamed
  }
  // The offscreen capture can fail on a cold first launch; try twice.
  let icns = null;
  for (let attempt = 1; attempt <= 2 && !icns; attempt++) {
    icns = await renderIcon(manifest.icon).catch((e) => {
      log("icon-failed", { attempt, message: e.message });
      return null;
    });
  }
  const cdhash = writeShimBundle({
    bundlePath,
    loaderPath,
    icns,
    allowReplace: ownedBySelf,
    installId: id,
    name: manifest.name,
    hostPath,
    hostBundleId,
    serverName: SERVER_NAME,
    // If the host is not running, the shim launches it with these arguments.
    launchArguments: [
      ...(app.isPackaged ? [] : [APP_ROOT]),
      `--home=${HOME}`,
      `--apps-dir=${APPS_DIR}`,
      `--max-tier=${MAX_TIER}`,
    ],
  });
  registry.put({
    ...(existing ?? {}),
    id,
    name: manifest.name,
    appDir,
    bundlePath,
    cdhash,
    installedAt: Date.now(),
  });
  log("installed", { id, name: manifest.name, bundlePath, cdhash });
  return registry.get(id);
}

function uninstall(id) {
  const record = registry.get(id);
  if (!record) throw new Error(`No app ${id}.`);
  running.get(id)?.shim?.quit();
  fs.rmSync(record.bundlePath, { recursive: true, force: true });
  registry.remove(id);
  // The app's T3 project (if it used the t3 harness) is left in T3 with its
  // threads; remove it there, or with `t3 project remove <appDir> --force`.
  log("uninstalled", { id, t3Project: record.t3Project ? record.appDir : undefined });
}

// ---------------------------------------------------------------- serving

const handledPartitions = new Set();
function partitionFor(id) {
  const name = `persist:agent-app-${id}`;
  if (!handledPartitions.has(name)) {
    handledPartitions.add(name);
    const ses = session.fromPartition(name);
    // Deny Chromium browser permission APIs (notifications, media, geolocation,
    // etc.) so every native capability must pass through window.agentApp's
    // manifest + version-bound grant + tier ceiling gate.
    ses.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    ses.setPermissionCheckHandler(() => false);
    ses.protocol.handle(SCHEME, async (request) => {
      const url = new URL(request.url);
      // This partition serves its own app only: no reading another app's files.
      if (url.hostname !== id) return new Response("forbidden", { status: 403 });
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response("method not allowed", { status: 405 });
      }
      const state = running.get(id);
      if (state && !state.version) return new Response("this app is invalid; see host.log", { status: 503 });
      const record = registry.get(id);
      const file = record && servableFile(record.appDir, url.pathname);
      if (!file) return new Response("not found", { status: 404 });
      const response = await net.fetch(pathToFileURL(file).href);
      const headers = new Headers(response.headers);
      headers.set("Content-Security-Policy", CSP);
      headers.set("X-Content-Type-Options", "nosniff");
      return new Response(response.body, { status: response.status, headers });
    });
  }
  return name;
}

function send(state, kind, payload) {
  if (!state.win.isDestroyed()) state.win.webContents.send("agent-app:event", { kind, ...payload });
}

// ---------------------------------------------------------------- app windows

function setShimMenu(state) {
  const { shim, manifest } = state;
  shim.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: manifest.name,
        submenu: [
          { role: "about" },
          { type: "separator" },
          { label: "Permissions…", click: () => showPermissions(state) },
          { label: "Reload", accelerator: "CmdOrCtrl+R", click: () => reload(state) },
          { type: "separator" },
          { role: "quit" },
        ],
      },
      { role: "editMenu" },
    ]),
  );
}

async function showPermissions(state) {
  const granted = registry.grantedFor(state.id, state.version);
  const lines = state.manifest.permissions.map(
    (p) => `${granted.has(p) ? "✓" : "·"} ${p} (tier ${PERMISSIONS[p]})`,
  );
  const { response } = await dialog.showMessageBox(state.win, {
    message: `${state.manifest.name} permissions`,
    detail: `Version ${state.version ?? "invalid"} · host ceiling tier ${MAX_TIER}\n\n${
      lines.join("\n") || "No permissions declared."
    }`,
    buttons: ["OK", "Revoke all"],
  });
  if (response === 1) {
    registry.revoke(state.id);
    dropGrantedResources(state);
  }
}

async function openAppWindow(record, shim) {
  const state = {
    id: record.id,
    record,
    shim,
    manifest: null,
    version: null,
    runs: new Map(),
    shortcuts: new Set(),
    tray: null,
    pendingReload: false,
    reloadWaiters: new Set(),
  };
  try {
    state.manifest = readManifest(record.appDir);
    state.version = versionOf(record.appDir);
  } catch (e) {
    log("app-invalid", { id: record.id, message: e.message });
    shim.quit();
    return;
  }
  state.win = new BrowserWindow({
    appShim: shim,
    width: 760,
    height: 620,
    show: false,
    title: state.manifest.name,
    backgroundColor: "#0b1020",
    webPreferences: {
      preload: path.join(SRC, "preload.cjs"),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      partition: partitionFor(record.id),
    },
  });
  const contentsId = state.win.webContents.id;
  running.set(record.id, state);
  byContents.set(contentsId, record.id);
  setShimMenu(state);

  const origin = `${SCHEME}://${record.id}`;
  state.win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(`${origin}/`)) event.preventDefault();
  });
  state.win.webContents.on("will-redirect", (event, url) => {
    if (!url.startsWith(`${origin}/`)) event.preventDefault();
  });
  state.win.webContents.session.on("will-download", (event) => event.preventDefault());
  state.win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  shim.on("activate", (_event, hasVisibleWindows) => {
    if (!hasVisibleWindows && !state.win.isDestroyed()) state.win.show();
  });
  shim.on("disconnected", () => closeApp(state, contentsId, "shim disconnected"));
  state.win.on("closed", () => {
    closeApp(state, contentsId, "window closed");
    if (shim.isConnected()) shim.quit();
  });
  state.win.webContents.on("did-fail-load", () => settleReloadWaiters(state));

  state.watcher = watchApp(state);
  state.win.once("ready-to-show", () => state.win.show());
  state.win.webContents.on("did-finish-load", () =>
    log("window-ready", {
      id: record.id,
      shimPid: shim.pid,
      version: state.version,
      title: state.win.webContents.getTitle(),
    }),
  );
  try {
    await state.win.loadURL(`${origin}/index.html`);
  } catch (e) {
    log("load-failed", { id: record.id, message: e.message });
    state.win.destroy();
    return;
  }
  if (SELFTEST && !state.selftestStarted) {
    state.selftestStarted = true;
    runSelftest({
      state,
      registry,
      log,
      home: HOME,
      waitForReload: () => waitForReload(state),
      shortcutOwners,
    }).catch((e) => log("selftest-crashed", { message: e.stack }));
  }
}

function closeApp(state, contentsId, reason) {
  if (state.closed) return;
  state.closed = true;
  for (const r of state.runs.values()) r.cancel();
  dropGrantedResources(state);
  state.watcher?.close();
  settleReloadWaiters(state);
  running.delete(state.id);
  byContents.delete(contentsId);
  log("app-closed", { id: state.id, reason });
}

/** Tray icons and shortcuts were granted to a version; drop them with the grant. */
function dropGrantedResources(state) {
  state.tray?.destroy();
  state.tray = null;
  dropShortcuts(state);
}

function waitForReload(state) {
  return new Promise((resolve) => state.reloadWaiters.add(resolve));
}
function settleReloadWaiters(state) {
  for (const resolve of state.reloadWaiters) resolve();
  state.reloadWaiters.clear();
}

/**
 * Re-hash now and apply the result. Fails closed: a folder that cannot be
 * hashed, or a manifest that no longer parses, leaves the app with NO valid
 * version, so nothing is granted and nothing is served until it is fixed.
 * Returns true if the version changed.
 */
function checkVersion(state) {
  if (state.closed) return false;
  let next = null;
  let manifest = state.manifest;
  try {
    manifest = readManifest(state.record.appDir);
    next = versionOf(state.record.appDir);
  } catch (e) {
    log("app-invalid", { id: state.id, message: e.message });
  }
  if (next === state.version) return false;
  const from = state.version;
  state.version = next;
  state.manifest = manifest;
  dropGrantedResources(state);
  log("version-changed", { id: state.id, from, to: next });
  send(state, "host", { type: "version-changed", from, to: next });
  if (state.runs.size > 0) state.pendingReload = true;
  else reload(state);
  return true;
}

function watchApp(state) {
  let timer;
  let firstEventAt = 0;
  const watcher = fs.watch(state.record.appDir, { recursive: true }, () => {
    const now = Date.now();
    if (!timer) firstEventAt = now;
    clearTimeout(timer);
    // Debounce bursts, but never by more than 2 s from the first event.
    const wait = Math.max(0, Math.min(300, firstEventAt + 2000 - now));
    timer = setTimeout(() => {
      timer = undefined;
      checkVersion(state);
    }, wait);
  });
  return {
    close() {
      clearTimeout(timer);
      watcher.close();
    },
  };
}

function reload(state) {
  state.pendingReload = false;
  if (state.closed || state.win.isDestroyed()) return;
  state.win.webContents.once("did-finish-load", () => {
    log("reloaded", { id: state.id, version: state.version, title: state.win.webContents.getTitle() });
    settleReloadWaiters(state);
  });
  state.win.webContents.reloadIgnoringCache();
}

// ---------------------------------------------------------------- the bridge

async function prompt(state, permission, version) {
  if (SELFTEST) return false; // selftest grants explicitly; prompts are denied.
  const { response } = await dialog.showMessageBox(state.win, {
    type: "question",
    message: `Allow ${state.manifest.name} to use "${permission}"?`,
    detail: `This applies to version ${version} only. If the app changes, including edits made by its agent, it will ask again.${
      PERMISSIONS[permission] === 3
        ? "\n\nThis is tier 3: it acts as you, and can reach outside the app's folder."
        : ""
    }`,
    buttons: ["Allow", "Don't Allow"],
    defaultId: 1,
    cancelId: 1,
  });
  return response === 0;
}

/** Ask, and grant only if the app is still open and still hashes on disk to the version shown. */
async function askAndGrant(state, permission) {
  const outcome = await authorizeAfterPrompt({
    permission,
    getVersion: () => state.version,
    prompt: (version) => prompt(state, permission, version),
    checkVersion: () => checkVersion(state),
    isClosed: () => Boolean(state.closed),
    grant: (version, perms) => registry.grant(state.id, version, perms),
  });
  return outcome.ok;
}

function ctxFor(state) {
  return {
    declared: new Set(state.manifest.permissions),
    granted: registry.grantedFor(state.id, state.version),
    maxTier: MAX_TIER,
  };
}

function harnessPath(bin) {
  return which(bin, process.env.PATH);
}

async function ensureT3Project(s) {
  if (s.record.t3Project) return;
  const t3 = harnessPath("t3");
  if (!t3) throw new CapabilityError("ENOHARNESS", "The t3 CLI is not on PATH; install T3 Code.");
  try {
    await run(t3, ["project", "add", s.record.appDir, "--title", `${s.manifest.name} · agent app`]);
  } catch (e) {
    if (!/ProjectAlreadyExists|already exists/i.test(`${e.stdout}${e.stderr}${e.message}`)) {
      throw new CapabilityError(
        "ET3",
        `t3 project add failed: ${String(e.stderr || e.message).slice(0, 300)}`,
      );
    }
  }
  registry.update(s.id, { t3Project: true });
  s.record = registry.get(s.id);
}

const modules = {
  app: {
    info: (s) => ({
      id: s.id,
      name: s.manifest.name,
      version: s.version,
      harness: s.manifest.agent.harness,
      harnesses: s.manifest.agent.harnesses,
      t3Thread: s.record.t3ThreadId ?? null,
      declared: s.manifest.permissions,
      granted: [...registry.grantedFor(s.id, s.version)],
      maxTier: MAX_TIER,
    }),
  },
  window: {
    setTitle: (s, title) => s.win.setTitle(String(title).slice(0, 200)),
    getBounds: (s) => s.win.getBounds(),
    setBounds: (s, b) => {
      const n = (v) => (Number.isFinite(v) ? Math.round(v) : undefined);
      s.win.setBounds({ x: n(b?.x), y: n(b?.y), width: n(b?.width), height: n(b?.height) });
    },
  },
  dock: {
    setBadge: (s, text) => s.shim.setBadge(String(text ?? "").slice(0, 8)),
    bounce: (s) => s.shim.bounce("informational"),
  },
  permissions: {
    state: (s) => ({
      declared: s.manifest.permissions,
      granted: [...registry.grantedFor(s.id, s.version)],
      maxTier: MAX_TIER,
    }),
    request: async (s, permission) => {
      if (typeof permission !== "string" || !s.manifest.permissions.includes(permission)) {
        throw new CapabilityError("ENOTDECLARED", `"${permission}" is not in app.json.`);
      }
      if (!(PERMISSIONS[permission] <= MAX_TIER)) {
        throw new CapabilityError(
          "EPOLICY",
          `The host policy allows tier ${MAX_TIER}; "${permission}" is tier ${PERMISSIONS[permission]}.`,
        );
      }
      if (registry.grantedFor(s.id, s.version).has(permission)) return true;
      return askAndGrant(s, permission);
    },
  },
  notification: {
    show: (s, opts = {}) => {
      new Notification({
        title: String(opts.title ?? s.manifest.name).slice(0, 120),
        body: String(opts.body ?? "").slice(0, 500),
      }).show();
      return true;
    },
  },
  tray: {
    set: (s, opts = {}) => {
      s.tray ??= new Tray(nativeImage.createEmpty());
      s.tray.setTitle(String(opts.title ?? s.manifest.name).slice(0, 40));
      s.tray.setToolTip(String(opts.tooltip ?? s.manifest.name).slice(0, 120));
      s.tray.removeAllListeners("click");
      s.tray.on("click", () => {
        if (!s.win.isDestroyed()) s.win.show();
      });
      return true;
    },
    remove: (s) => {
      s.tray?.destroy();
      s.tray = null;
      return true;
    },
  },
  globalShortcut: {
    register: (s, accelerator) => {
      const key = String(accelerator).slice(0, 60);
      const owner = shortcutOwners.get(key);
      if (owner && owner !== s.id) throw new CapabilityError("EBUSY", `${key} belongs to another app.`);
      if (owner === s.id) return true;
      const ok = globalShortcut.register(key, () => send(s, "shortcut", { accelerator: key }));
      if (ok) {
        s.shortcuts.add(key);
        shortcutOwners.set(key, s.id);
      }
      return ok;
    },
    unregisterAll: (s) => {
      dropShortcuts(s);
      return true;
    },
  },
  agent: {
    run: async (s, opts = {}) => {
      const harness = opts.harness;
      if (opts.model !== undefined && !validModel(opts.model)) {
        throw new CapabilityError("EINVAL", "model must be a model id.");
      }
      if (opts.provider !== undefined && (harness !== "t3" || !validProvider(opts.provider) || !opts.model)) {
        throw new CapabilityError(
          "EINVAL",
          "provider is a T3 provider instance id, for the t3 harness, with a model.",
        );
      }
      const bin = { claude: "claude", codex: "codex", t3: "t3" }[harness];
      if (!harnessPath(bin)) throw new CapabilityError("ENOHARNESS", `The ${bin} CLI is not on PATH.`);
      return guardAsyncLaunch({
        prepare: harness === "t3" ? () => ensureT3Project(s) : null,
        isClosed: () => Boolean(s.closed),
        checkVersion: () => checkVersion(s),
        getVersion: () => s.version,
        decideCall: () => decide({ module: "agent", method: "run", args: [opts] }, ctxFor(s)),
        launch: () => {
          const runId = randomBytes(4).toString("hex");
          const edit = opts.edit === true || harness === "t3";
          const fromManifest = harness === s.manifest.agent.harness;
          log("agent-run", { id: s.id, runId, harness, edit });
          const r = runHarness(
            {
              harness,
              prompt: opts.prompt,
              edit,
              model: opts.model ?? (fromManifest ? s.manifest.agent.model : undefined),
              provider: opts.provider ?? (fromManifest ? s.manifest.agent.provider : undefined),
              cwd: s.record.appDir,
              threadId: harness === "t3" && opts.newThread !== true ? s.record.t3ThreadId : undefined,
              title: `${s.manifest.name} agent`,
            },
            (event) => {
              if (event.type === "thread" && event.threadId !== s.record.t3ThreadId) {
                registry.update(s.id, { t3ThreadId: event.threadId });
                s.record = registry.get(s.id);
              }
              send(s, "agent", { runId, ...event });
              if (event.type === "done") {
                log("agent-done", { id: s.id, runId, ok: event.ok, summary: event.summary?.slice(0, 200) });
              }
            },
          );
          s.runs.set(runId, r);
          // The run is over when its process is, not when the CLI says so.
          r.finished.then(() => {
            s.runs.delete(runId);
            // Let the page receive `done` before the reload tears it down.
            if (s.pendingReload && s.runs.size === 0) {
              setTimeout(() => s.runs.size === 0 && reload(s), 200);
            }
          });
          return runId;
        },
      });
    },
    cancel: (s, runId) => {
      s.runs.get(String(runId))?.cancel();
      return true;
    },
  },
  fs: {
    readFile: (_s, file) => fs.promises.readFile(absolute(file), "utf8"),
    writeFile: (_s, file, text) => fs.promises.writeFile(absolute(file), String(text)),
    readdir: (_s, dir) => fs.promises.readdir(absolute(dir)),
  },
};

function dropShortcuts(s) {
  for (const a of s.shortcuts) {
    if (shortcutOwners.get(a) === s.id) {
      globalShortcut.unregister(a);
      shortcutOwners.delete(a);
    }
  }
  s.shortcuts.clear();
}

function absolute(p) {
  if (typeof p !== "string" || !path.isAbsolute(p)) {
    throw new CapabilityError("EINVAL", "fs paths must be absolute.");
  }
  return p;
}

/**
 * One bridge call. A permission-gated call re-hashes the app first, so a
 * change the watcher has not reported yet still counts; a stale version is
 * refused (EVERSION) and the app reloads under its new version.
 */
export async function handleCall(state, call) {
  if (call.module === "agent" && call.method === "run") {
    const opts = { ...(call.args?.[0] ?? {}) };
    opts.harness ??= state.manifest.agent.harness;
    if (!state.manifest.agent.harnesses.includes(opts.harness)) {
      return {
        ok: false,
        code: "EHARNESS",
        message: `"${opts.harness}" is not in this app's agent.harnesses (${state.manifest.agent.harnesses.join(", ")}).`,
      };
    }
    call = { ...call, args: [opts] };
  }
  const permission = requiredPermission(call.module, call.method, call.args);
  if (permission) {
    if (checkVersion(state)) {
      return {
        ok: false,
        code: "EVERSION",
        message: "The app changed; it is reloading under its new version.",
      };
    }
    if (!state.version)
      return { ok: false, code: "EINVALIDAPP", message: "This app's folder is not valid; see host.log." };
  }
  let decision = decide(call, ctxFor(state));
  if (!decision.ok && decision.code === "EPERM") {
    const beforePrompt = state.version;
    const granted = await askAndGrant(state, decision.permission);
    if (state.closed) return { ok: false, code: "ECLOSED", message: "The app closed." };
    if (state.version !== beforePrompt) {
      return {
        ok: false,
        code: "EVERSION",
        message: "The app changed while waiting for permission; it is reloading under its new version.",
      };
    }
    if (granted) decision = decide(call, ctxFor(state));
  }
  if (!decision.ok) return decision;
  if (state.closed) return { ok: false, code: "ECLOSED", message: "The app closed." };
  const fn = modules[call.module]?.[call.method];
  return { ok: true, value: await fn(state, ...(call.args ?? [])) };
}

ipcMain.handle("agent-app:call", async (event, call) => {
  const id = byContents.get(event.sender.id);
  const state = id && running.get(id);
  const frame = event.senderFrame;
  if (!state || !frame || frame !== event.sender.mainFrame || !frame.url.startsWith(`${SCHEME}://${id}/`)) {
    return { ok: false, code: "EACCES", message: "Calls are accepted only from an app's own main frame." };
  }
  if (
    typeof call?.module !== "string" ||
    typeof call?.method !== "string" ||
    !Array.isArray(call.args ?? [])
  ) {
    return { ok: false, code: "EINVAL", message: "Malformed call." };
  }
  try {
    return await handleCall(state, call);
  } catch (e) {
    return { ok: false, code: e.code ?? "EFAIL", message: e.message };
  }
});

// ---------------------------------------------------------------- lifecycle

async function runCommand([cmd, ...rest]) {
  switch (cmd) {
    case "serve":
      return;
    case "install":
      await install(rest[0]);
      return;
    case "uninstall":
      uninstall(rest[0]);
      return;
    case "grant": {
      const record = registry.get(rest[0]);
      if (!record) throw new Error(`No app ${rest[0]}.`);
      const manifest = readManifest(record.appDir);
      const perms = rest.slice(1);
      for (const p of perms) {
        if (!manifest.permissions.includes(p)) throw new Error(`"${p}" is not declared in app.json.`);
        if (!(PERMISSIONS[p] <= MAX_TIER))
          throw new Error(`"${p}" is tier ${tierOf(p)}, above --max-tier=${MAX_TIER}.`);
      }
      registry.grant(record.id, versionOf(record.appDir), perms);
      log("granted", { id: record.id, permissions: perms });
      return;
    }
    default:
      throw new Error(`Unknown command "${cmd}".`);
  }
}

if (config && registry && command[0] !== "list") {
  const forwarded = {
    command,
    maxTier: cliFlags["max-tier"] !== undefined ? MAX_TIER : undefined,
    appsDir: cliFlags["apps-dir"] !== undefined ? APPS_DIR : undefined,
  };
  if (!app.requestSingleInstanceLock(forwarded)) {
    // A host for this home is running: it runs the command (paths were made
    // absolute here). Its outcome is in host.log.
    console.log(`forwarded "${command[0]}" to the running host; see ${LOG}`);
    app.exit(0);
  } else {
    app.on("second-instance", (_event, _argv, _cwd, extra) => {
      const cmd = Array.isArray(extra?.command) ? extra.command : ["serve"];
      const compat = checkForwardedConfig({ maxTier: MAX_TIER, appsDir: APPS_DIR }, extra);
      if (!compat.ok) {
        log("command-failed", { command: cmd[0], message: compat.message });
        return;
      }
      runCommand(cmd).catch((e) => log("command-failed", { command: cmd[0], message: e.message }));
    });
    app.on("window-all-closed", () => {
      // The host keeps serving with no windows open.
    });
    let quitReady = false;
    let quitPending = null;
    app.on("before-quit", (event) => {
      if (quitReady) return;
      if (quitPending) {
        event.preventDefault();
        return;
      }
      const active = [];
      for (const state of running.values()) active.push(...state.runs.values());
      quitPending = cancelRunsOnQuit(active, event, () => {
        quitReady = true;
        app.quit();
      });
    });
    app.on("app-shim-version-mismatch", (_event, bundlePath) => log("shim-version-mismatch", { bundlePath }));
    app.on("app-shim-connected", (_event, shim) => {
      const record = registry.findByBundle(shim.bundlePath);
      // Any process of this user can connect. Accept only a shim whose running
      // code is the exact bundle this host wrote (its cdhash).
      let trusted = false;
      try {
        trusted = Boolean(
          record &&
            /^[0-9a-f]{40,64}$/.test(record.cdhash) &&
            shim.satisfiesCodeRequirement(`cdhash H"${record.cdhash}"`),
        );
      } catch (e) {
        log("shim-check-failed", { message: e.message });
      }
      if (!trusted) {
        log("shim-rejected", { bundlePath: shim.bundlePath, shimPid: shim.pid, known: Boolean(record) });
        shim.quit();
        return;
      }
      if (running.has(record.id)) {
        log("shim-duplicate", { id: record.id });
        shim.quit();
        const existing = running.get(record.id);
        if (!existing.win.isDestroyed()) existing.win.show();
        return;
      }
      log("shim-connected", { id: record.id, shimPid: shim.pid });
      openAppWindow(record, shim).catch((e) => {
        log("window-failed", { id: record.id, message: e.stack });
        if (shim.isConnected()) shim.quit();
      });
    });

    app.whenReady().then(async () => {
      // A host the shim launched through LaunchServices has a minimal PATH.
      process.env.PATH = resolveUserPath(process.env);
      app.dock?.hide(); // Only the apps show in the Dock, not the host.
      app.startAppShimServer({ name: SERVER_NAME });
      log("host-ready", { home: HOME, appsDir: APPS_DIR, serverName: SERVER_NAME, maxTier: MAX_TIER });
      try {
        await runCommand(command);
      } catch (e) {
        log("command-failed", { command: command[0], message: e.message });
        if (command[0] !== "serve") app.exit(1);
      }
      if (["uninstall", "grant"].includes(command[0])) app.quit();
    });
  }
}
