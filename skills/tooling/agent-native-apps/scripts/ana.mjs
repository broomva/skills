#!/usr/bin/env node
// ana — build, check and install agent-native apps.
//
//   ana doctor [--json]              what this machine has and lacks
//   ana setup [--kit <dir>]          install the host kit (Electron 45.5) once
//   ana new <dir> --name "My App" [--harness t3|claude|codex] [--provider P --model M]
//                 [--permissions a,b,c] [--icon ✦]
//   ana check <dir> [--json]         validate an app folder; print its version
//   ana install <dir>                write its .app and start serving it
//   ana list                         installed apps
//   ana uninstall <id>               remove an app's .app and grants
//   ana open <id>                    open an installed app
//   ana e2e                          run the kit's end-to-end check (opens a test app)
//
// The pure functions are exported for tests; nothing here needs Electron except
// `install`, `list` and `uninstall`, which run the host kit.

import { execFileSync, spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PERMISSIONS } from "../assets/host/src/capabilities.js";
import { resolveUserPath, which } from "../assets/host/src/harness.js";
import {
  HARNESS_NAMES,
  ManifestError,
  readManifest,
  servedFiles,
  validateManifest,
  versionOf,
} from "../assets/host/src/manifest.js";

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const KIT_SOURCE = path.join(SKILL, "assets", "host");
const TEMPLATE = path.join(SKILL, "assets", "templates", "app");
export const DEFAULT_KIT = path.join(os.homedir(), ".agent-native-apps", "host");
export const MIN_ELECTRON = [45, 3, 0];

export class UsageError extends Error {}

/**
 * Child environment for Electron launches: strip ELECTRON_RUN_AS_NODE so
 * calling ana from T3 Code, VS Code, or another Electron terminal boots
 * Electron as Electron rather than plain Node. Pure.
 */
export function electronEnv(env = process.env) {
  const out = { ...env };
  delete out.ELECTRON_RUN_AS_NODE;
  return out;
}

// ------------------------------------------------------------------ pure parts

/** `--name value`, `--name=value` and bare `--flag`; everything else positional. Pure. */
export function parseCli(argv, booleans = ["json", "force"]) {
  const flags = {};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const m = /^--([a-z][a-z-]*)(?:=(.*))?$/s.exec(arg);
    if (!m) {
      positional.push(arg);
      continue;
    }
    const [, name, inline] = m;
    if (booleans.includes(name)) {
      if (inline !== undefined) throw new UsageError(`--${name} takes no value.`);
      flags[name] = true;
    } else if (inline !== undefined) {
      flags[name] = inline;
    } else {
      if (i + 1 >= argv.length) throw new UsageError(`--${name} needs a value.`);
      flags[name] = argv[++i];
    }
  }
  return { flags, positional };
}

/** [major, minor, patch] from "45.5.0" / "v45.5.0-beta.1"; null if not a version. Pure. */
export function parseVersion(text) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)/.exec(String(text).trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

/** a >= b for version triples. Pure. */
export function versionAtLeast(a, b) {
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return true;
}

/**
 * The manifest `ana new` writes. Pure. Validated with the host's own
 * validateManifest, so a scaffold can never be one the host refuses.
 */
export function scaffoldManifest({ name, icon, harness = "t3", provider, model, permissions }) {
  if (!HARNESS_NAMES.includes(harness)) {
    throw new UsageError(`--harness must be one of ${HARNESS_NAMES.join(", ")}.`);
  }
  // A t3 run always needs agent-edit: T3 threads take their project's runtime mode.
  const wanted = permissions ?? (harness === "t3" ? ["agent", "agent-edit"] : ["agent"]);
  const manifest = {
    name,
    ...(icon ? { icon } : {}),
    permissions: wanted,
    agent: { harness, ...(provider ? { provider } : {}), ...(model ? { model } : {}) },
  };
  try {
    validateManifest(manifest);
  } catch (e) {
    throw new UsageError(e.message);
  }
  if (harness === "t3" && !wanted.includes("agent-edit")) {
    throw new UsageError('A t3 app needs the "agent-edit" permission: T3 threads run with their project\'s runtime mode.');
  }
  return manifest;
}

const REMOTE = /^(?:[a-z][a-z0-9+.-]*:)?\/\//i;

/**
 * Static problems in an app's HTML that the host's CSP will block at run time.
 * Returns [{file, problem}]. Pure. A regex scan, not a parser: it reports what
 * it can see and stays silent otherwise.
 */
export function lintHtml(file, html) {
  const problems = [];
  const add = (problem) => problems.push({ file, problem });
  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    const src = /\bsrc\s*=\s*["']?([^"'\s>]+)/i.exec(m[1])?.[1];
    if (!src && m[2].trim()) add("inline <script>: the CSP is script-src 'self'; move it to a .js file.");
    if (src && REMOTE.test(src)) add(`remote script ${src}: apps load code from their own folder only.`);
  }
  for (const m of html.matchAll(/<link\b[^>]*\bhref\s*=\s*["']?([^"'\s>]+)/gi)) {
    if (REMOTE.test(m[1])) add(`remote stylesheet or link ${m[1]}: bundle it into the app folder.`);
  }
  for (const m of html.matchAll(/<(?:img|audio|video|source)\b[^>]*\bsrc\s*=\s*["']?([^"'\s>]+)/gi)) {
    if (REMOTE.test(m[1])) add(`remote media ${m[1]}: bundle it into the app folder.`);
  }
  if (/<iframe\b/i.test(html)) add("<iframe>: the CSP is frame-src 'none'.");
  if (/\son[a-z]+\s*=\s*["']/i.test(html)) add("inline event handler (onclick=…): use addEventListener in a .js file.");
  return problems;
}

/**
 * Validate an app folder the way the host will. Returns
 * {ok, manifest?, version?, files, problems:[{file,problem}], warnings:[string]}.
 */
export function checkApp(appDir) {
  const result = { ok: false, files: [], problems: [], warnings: [] };
  const fail = (file, problem) => result.problems.push({ file, problem });
  let manifest;
  try {
    manifest = readManifest(appDir);
    result.manifest = manifest;
  } catch (e) {
    fail("app.json", e.message);
  }
  try {
    result.files = servedFiles(appDir).map((f) => path.relative(appDir, f));
    result.version = versionOf(appDir);
  } catch (e) {
    fail(".", e instanceof ManifestError ? e.message : String(e));
  }
  for (const rel of result.files.filter((f) => /\.html?$/i.test(f))) {
    result.problems.push(...lintHtml(rel, fs.readFileSync(path.join(appDir, rel), "utf8")));
  }
  if (manifest) {
    const tier3 = manifest.permissions.filter((p) => PERMISSIONS[p] === 3);
    if (tier3.length) {
      result.warnings.push(`tier 3 permissions (${tier3.join(", ")}): the app's agent acts as you, beyond the app folder.`);
    }
    if (manifest.agent.harness === "t3" && !manifest.permissions.includes("agent-edit")) {
      fail("app.json", 'agent.harness is "t3" but "agent-edit" is not declared; every t3 run needs it.');
    }
    if (!manifest.permissions.some((p) => p === "agent" || p === "agent-edit")) {
      result.warnings.push("no agent permission declared: window.agentApp.agent.run will be refused.");
    }
  }
  for (const hidden of ["node_modules", ".git"]) {
    if (fs.existsSync(path.join(appDir, hidden))) {
      result.warnings.push(`${hidden}/ is neither served nor part of the version; the page cannot load from it.`);
    }
  }
  result.ok = result.problems.length === 0;
  return result;
}

/** Write a new app folder from the template. Refuses a non-empty directory. */
export function scaffold(appDir, options) {
  const manifest = scaffoldManifest(options);
  if (fs.existsSync(appDir) && fs.readdirSync(appDir).length > 0) {
    throw new UsageError(`${appDir} exists and is not empty.`);
  }
  fs.mkdirSync(appDir, { recursive: true });
  for (const file of fs.readdirSync(TEMPLATE)) {
    const text = fs.readFileSync(path.join(TEMPLATE, file), "utf8").replaceAll("__APP_NAME__", manifest.name);
    fs.writeFileSync(path.join(appDir, file), text);
  }
  fs.writeFileSync(path.join(appDir, "app.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  return manifest;
}

// ------------------------------------------------------------------ the machine

const has = (bin) => spawnSync("/bin/sh", ["-c", `command -v "$1"`, "sh", bin], { encoding: "utf8" }).stdout.trim() || null;

function tryVersion(bin, args = ["--version"]) {
  const r = spawnSync(bin, args, { encoding: "utf8", timeout: 15000 });
  return r.status === 0 ? `${r.stdout}${r.stderr}`.trim().split("\n")[0] : null;
}

export function kitInfo(kit = DEFAULT_KIT) {
  const electronApp = path.join(kit, "node_modules/electron/dist/Electron.app");
  const loader = path.join(electronApp, "Contents/Frameworks/Electron Framework.framework/Helpers/app_shim_loader");
  let version = null;
  try {
    version = JSON.parse(fs.readFileSync(path.join(kit, "node_modules/electron/package.json"), "utf8")).version;
  } catch {
    // not installed
  }
  return {
    kit,
    installed: fs.existsSync(path.join(kit, "src/main.js")),
    electron: version,
    electronBin: path.join(electronApp, "Contents/MacOS/Electron"),
    loader: fs.existsSync(loader),
  };
}

export function doctor(kit = DEFAULT_KIT) {
  const k = kitInfo(kit);
  // Look for the agent CLIs the way the host will, not only on this shell's PATH.
  const hostPath = resolveUserPath(process.env);
  const cli = (bin) => which(bin, hostPath);
  const node = parseVersion(process.version);
  const ev = k.electron && parseVersion(k.electron);
  const checks = [
    { name: "macOS", ok: process.platform === "darwin", required: true, detail: process.platform, fix: "App shims are macOS only." },
    { name: "node >= 22", ok: versionAtLeast(node, [22, 0, 0]), required: true, detail: process.version, fix: "Install Node 22 or newer." },
    { name: "codesign", ok: Boolean(has("codesign")), required: true, detail: has("codesign"), fix: "Install the Xcode command line tools: xcode-select --install" },
    { name: "bun or npm", ok: Boolean(has("bun") || has("npm")), required: true, detail: has("bun") ?? has("npm"), fix: "Install bun (https://bun.sh) or npm." },
    { name: "host kit", ok: k.installed, required: true, detail: k.kit, fix: "Run: ana setup" },
    {
      name: `Electron >= ${MIN_ELECTRON.join(".")} with app_shim_loader`,
      ok: Boolean(ev && versionAtLeast(ev, MIN_ELECTRON) && k.loader),
      required: true,
      detail: k.electron ?? "not installed",
      fix: "Run: ana setup",
    },
    { name: "t3 CLI (T3 harness)", ok: Boolean(cli("t3")), required: false, detail: cli("t3") && `${cli("t3")}, ${tryVersion(cli("t3"))}`, fix: "Install T3 Code (its CLI lives at ~/.t3/bin/t3) to give apps T3 threads." },
    { name: "claude CLI", ok: Boolean(cli("claude")), required: false, detail: cli("claude"), fix: "Optional: Claude Code, for the claude harness." },
    { name: "codex CLI", ok: Boolean(cli("codex")), required: false, detail: cli("codex"), fix: "Optional: Codex, for the codex harness." },
  ];
  const harnesses = checks.slice(-3).filter((c) => c.ok).length;
  checks.push({ name: "at least one agent harness", ok: harnesses > 0, required: true, detail: `${harnesses} found`, fix: "Install T3 Code, Claude Code or Codex." });
  return { ok: checks.every((c) => c.ok || !c.required), checks };
}

function setup(kit) {
  if (process.platform !== "darwin") throw new UsageError("App shims are macOS only.");
  fs.mkdirSync(kit, { recursive: true });
  fs.cpSync(KIT_SOURCE, kit, { recursive: true, filter: (src) => !src.split(path.sep).includes("node_modules") });
  const pm = has("bun") ? "bun" : "npm";
  console.log(`Installing Electron into ${kit} with ${pm} (one time, about 100 MB)…`);
  execFileSync(pm, ["install"], { cwd: kit, stdio: "inherit" });
  const k = kitInfo(kit);
  if (!k.loader) {
    // Electron fetches its binary in a postinstall that some installers skip.
    execFileSync(process.execPath, [path.join(kit, "node_modules/electron/install.js")], { cwd: kit, stdio: "inherit" });
  }
  const after = kitInfo(kit);
  if (!after.loader) throw new Error(`Electron in ${kit} has no app_shim_loader; it needs ${MIN_ELECTRON.join(".")}+.`);
  console.log(`Host kit ready: Electron ${after.electron} at ${kit}`);
}

function requireKit(kit) {
  const k = kitInfo(kit);
  if (!k.installed || !k.loader) throw new UsageError("The host kit is not installed. Run: ana setup");
  return k;
}

function registryPath(home) {
  return path.join(home ?? path.join(os.homedir(), "Library/Application Support/agent-native-apps"), "registry.json");
}

function readRegistry(home) {
  try {
    return Object.values(JSON.parse(fs.readFileSync(registryPath(home), "utf8")).apps ?? {});
  } catch {
    return [];
  }
}

async function install(appDir, { kit, home, appsDir }) {
  const k = requireKit(kit);
  const checked = checkApp(appDir);
  if (!checked.ok) {
    for (const p of checked.problems) console.error(`  ${p.file}: ${p.problem}`);
    throw new UsageError(`${appDir} is not a valid app; fix the problems above.`);
  }
  const args = [k.kit, "install", appDir, ...(home ? [`--home=${home}`] : []), ...(appsDir ? [`--apps-dir=${appsDir}`] : [])];
  const before = readRegistry(home).find((a) => a.appDir === appDir)?.installedAt ?? 0;
  // Detached: the host keeps serving after this command returns.
  spawn(k.electronBin, args, { detached: true, stdio: "ignore", env: electronEnv() }).unref();
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    const record = readRegistry(home).find((a) => a.appDir === appDir);
    if (record && record.installedAt > before && fs.existsSync(record.bundlePath)) return record;
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error("The host did not finish the install in 120 s; see host.log in the host's home.");
}

const HELP = `ana — agent-native apps

  ana doctor [--json]            check this machine
  ana setup [--kit <dir>]        install the host kit once
  ana new <dir> --name "My App" [--harness t3|claude|codex] [--provider P --model M] [--permissions a,b] [--icon X]
  ana check <dir> [--json]       validate an app folder
  ana install <dir>              write its .app and serve it
  ana list                       installed apps
  ana uninstall <id>             remove an app
  ana open <id>                  open an installed app
  ana e2e                        end-to-end check of this machine (opens a test app)

  Common flags: --kit <dir> (default ~/.agent-native-apps/host), --home <dir>, --apps-dir <dir>`;

export async function main(argv) {
  const { flags, positional } = parseCli(argv);
  const [cmd, target] = positional;
  const kit = path.resolve(flags.kit ?? DEFAULT_KIT);
  const home = flags.home && path.resolve(flags.home);
  switch (cmd) {
    case "doctor": {
      const report = doctor(kit);
      if (flags.json) console.log(JSON.stringify(report, null, 2));
      else {
        for (const c of report.checks) {
          console.log(`${c.ok ? "ok  " : c.required ? "FAIL" : "--  "} ${c.name}${c.detail ? `  (${c.detail})` : ""}`);
          if (!c.ok) console.log(`       ${c.fix}`);
        }
      }
      return report.ok ? 0 : 1;
    }
    case "setup":
      setup(kit);
      return 0;
    case "new": {
      if (!target || !flags.name) throw new UsageError('Usage: ana new <dir> --name "My App"');
      const manifest = scaffold(path.resolve(target), {
        name: flags.name,
        icon: flags.icon,
        harness: flags.harness,
        provider: flags.provider,
        model: flags.model,
        permissions: flags.permissions?.split(",").map((p) => p.trim()).filter(Boolean),
      });
      console.log(`Created ${path.resolve(target)} (${manifest.name}, harness ${manifest.agent.harness}).`);
      console.log(`Next: ana check ${target} && ana install ${target}`);
      return 0;
    }
    case "check": {
      if (!target) throw new UsageError("Usage: ana check <dir>");
      const result = checkApp(path.resolve(target));
      if (flags.json) console.log(JSON.stringify(result, null, 2));
      else {
        for (const p of result.problems) console.log(`FAIL ${p.file}: ${p.problem}`);
        for (const w of result.warnings) console.log(`warn ${w}`);
        if (result.ok) console.log(`ok   ${result.manifest.name}  version ${result.version}  ${result.files.length} files`);
      }
      return result.ok ? 0 : 1;
    }
    case "install": {
      if (!target) throw new UsageError("Usage: ana install <dir>");
      const record = await install(path.resolve(target), { kit, home, appsDir: flags["apps-dir"] && path.resolve(flags["apps-dir"]) });
      console.log(`Installed ${record.name} (${record.id})`);
      console.log(`Open it:  open "${record.bundlePath}"`);
      return 0;
    }
    case "list":
      for (const a of readRegistry(home)) console.log(`${a.id}\t${a.name}\t${a.bundlePath}`);
      return 0;
    case "open": {
      const record = readRegistry(home).find((a) => a.id === target || a.name === target);
      if (!record) throw new UsageError(`No installed app "${target}". Try: ana list`);
      execFileSync("open", [record.bundlePath]);
      return 0;
    }
    case "e2e": {
      const k = requireKit(kit);
      const r = spawnSync(process.execPath, [path.join(k.kit, "scripts", "e2e.mjs")], { cwd: k.kit, stdio: "inherit", env: electronEnv() });
      return r.status ?? 1;
    }
    case "uninstall": {
      if (!target) throw new UsageError("Usage: ana uninstall <id>");
      const k = requireKit(kit);
      execFileSync(k.electronBin, [k.kit, "uninstall", target, ...(home ? [`--home=${home}`] : [])], { stdio: "inherit", env: electronEnv() });
      return 0;
    }
    case undefined:
    case "help":
      console.log(HELP);
      return 0;
    default:
      throw new UsageError(`Unknown command "${cmd}".\n\n${HELP}`);
  }
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (e) => {
      console.error(e instanceof UsageError ? e.message : (e.stack ?? e));
      process.exit(e instanceof UsageError ? 2 : 1);
    },
  );
}
