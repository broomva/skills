// End-to-end check, driven from OUTSIDE Electron so the OS is the witness:
//   1. install a copy of Agent Pad into a throwaway home and Applications folder
//   2. `open` its .app the way Finder would
//   3. the window server must report the window as owned by the shim's process
//      (named "Agent Pad"), and LaunchServices must list the shim as a
//      foreground (Dock) app; the host shows no window and no Dock icon
//   4. the host's --selftest runs the bridge scenario in the page (tiers,
//      grants, both harnesses, the agent editing its own app, grant revocation)
//   5. a re-signed impostor copy and a tampered bundle are both refused
//   6. kill the host, `open` the .app again: the shim must relaunch the host
//   Writes evidence/e2e-result.json and evidence/agent-pad-window.png.
//
// Usage: node scripts/e2e.mjs [--keep]   (needs a logged-in GUI session)

import { execFile, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { resolveUserPath, which } from "../src/harness.js";

const run = promisify(execFile);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ELECTRON = path.join(ROOT, "node_modules/electron/dist/Electron.app/Contents/MacOS/Electron");
const EVIDENCE = path.join(ROOT, "evidence");
const keep = process.argv.includes("--keep");

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "agent-native-apps-e2e-"));
const home = path.join(tmp, "home");
const appsDir = path.join(tmp, "Applications");
const appDir = path.join(tmp, "agent-pad");
fs.cpSync(path.join(ROOT, "examples/agent-pad"), appDir, { recursive: true });
fs.mkdirSync(home, { recursive: true });
const logFile = path.join(home, "host.log");

let hostChild;
const checks = [];
const check = (name, pass, detail = {}) => {
  checks.push({ name, pass: Boolean(pass), ...detail });
  console.log(
    `${pass ? "PASS" : "FAIL"}  ${name}${Object.keys(detail).length ? `  ${JSON.stringify(detail)}` : ""}`,
  );
};

function events() {
  if (!fs.existsSync(logFile)) return [];
  return fs
    .readFileSync(logFile, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((l) => JSON.parse(l));
}

async function waitFor(predicate, timeoutMs, label, from = 0) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const hit = events().slice(from).find(predicate);
    if (hit) return hit;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`timed out waiting for ${label}`);
}

async function onScreenWindows() {
  const js = `ObjC.import('CoreGraphics');
    JSON.stringify(ObjC.deepUnwrap(ObjC.castRefToObject(
      $.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, 0))).map((w) => ({
        pid: w.kCGWindowOwnerPID, owner: w.kCGWindowOwnerName, number: w.kCGWindowNumber,
        layer: w.kCGWindowLayer, bounds: w.kCGWindowBounds })))`;
  const { stdout } = await run("osascript", ["-l", "JavaScript", "-e", js]);
  return JSON.parse(stdout);
}

async function appType(pid) {
  // LaunchServices: "Foreground" apps are the ones in the Dock and Cmd-Tab.
  const found = await run("lsappinfo", ["find", `pid=${pid}`]).catch(() => ({ stdout: "" }));
  const asn = found.stdout.trim();
  if (!asn) return null;
  const { stdout } = await run("lsappinfo", ["info", "-only", "ApplicationType", asn]).catch(() => ({
    stdout: "",
  }));
  return /"ApplicationType"="([^"]+)"/.exec(stdout)?.[1] ?? null;
}

const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

async function main() {
  // macOS launches one instance per .app: if another host from this same
  // Electron.app is running, a shim that needs a host gets that one activated
  // instead of a new host for this home, and step 5 cannot be observed.
  const others = await run("pgrep", ["-f", ELECTRON]).catch(() => ({ stdout: "" }));
  if (others.stdout.trim()) {
    throw new Error(`another host from ${ELECTRON} is running (pid ${others.stdout.trim()}); quit it first`);
  }

  // 1. install + serve with the selftest on.
  const host = spawn(
    ELECTRON,
    [ROOT, "install", appDir, `--home=${home}`, `--apps-dir=${appsDir}`, "--selftest"],
    { stdio: ["ignore", "ignore", "inherit"] },
  );
  hostChild = host;
  const installed = await waitFor((e) => e.event === "installed", 120000, "install");
  check(
    "install wrote a signed shim bundle",
    fs.existsSync(path.join(installed.bundlePath, "Contents/MacOS/agent-app")) &&
      /^[0-9a-f]{40}/.test(installed.cdhash),
    {
      bundlePath: path.relative(tmp, installed.bundlePath),
      cdhash: installed.cdhash,
    },
  );
  check(
    "the bundle has a generated icon",
    fs.existsSync(path.join(installed.bundlePath, "Contents/Resources/app.icns")),
  );

  // 2. open it like Finder would.
  await run("open", [installed.bundlePath]);
  const ready = await waitFor((e) => e.event === "window-ready", 30000, "window");
  const hostPid = ready.pid;
  const shimPid = ready.shimPid;
  await new Promise((r) => setTimeout(r, 1000));

  // 3. the OS says who owns the window.
  const windows = await onScreenWindows();
  const shimWindow = windows.find((w) => w.pid === shimPid && w.layer === 0);
  check(
    "the window is owned by the shim process, named after the app",
    shimWindow && shimWindow.owner === "Agent Pad",
    {
      shimPid,
      owner: shimWindow?.owner,
      bounds: shimWindow?.bounds,
    },
  );
  check("the host owns no on-screen window", !windows.some((w) => w.pid === hostPid && w.layer === 0), {
    hostPid,
  });
  const shimType = await appType(shimPid);
  const hostType = await appType(hostPid);
  check(
    "LaunchServices lists the shim as a Dock app and the host is hidden",
    shimType === "Foreground" && hostType !== "Foreground",
    {
      shimType,
      hostType,
    },
  );

  // 4. the bridge scenario.
  const done = await waitFor((e) => e.event === "selftest-done", 8 * 60000, "selftest");
  const selftest = JSON.parse(fs.readFileSync(path.join(home, "selftest.json"), "utf8"));
  for (const r of selftest.results) check(`bridge: ${r.name}`, r.pass, r.pass ? {} : { value: r.value });
  check("selftest passed every step", done.failed === 0, { passed: done.passed, failed: done.failed });

  fs.mkdirSync(EVIDENCE, { recursive: true });
  const after = (await onScreenWindows()).find((w) => w.pid === shimPid && w.layer === 0);
  if (after) {
    await run("screencapture", [
      "-x",
      "-o",
      `-l${after.number}`,
      path.join(EVIDENCE, "agent-pad-window.png"),
    ]).catch((e) => check("window screenshot", false, { message: e.message }));
  }

  // 5. shim trust: only the exact bundle the host wrote may connect.
  const resign = async (bundle, bundleId) => {
    await run("plutil", [
      "-replace",
      "CFBundleIdentifier",
      "-string",
      bundleId,
      path.join(bundle, "Contents/Info.plist"),
    ]);
    await run("codesign", ["--force", "--sign", "-", bundle]);
  };
  const impostor = path.join(appsDir, "Impostor.app");
  fs.cpSync(installed.bundlePath, impostor, { recursive: true });
  await resign(impostor, "tech.example.impostor");
  let mark = events().length;
  await run("open", ["-n", impostor]);
  const rejectedCopy = await waitFor((e) => e.event === "shim-rejected", 30000, "impostor rejection", mark);
  check("a re-signed copy of the shim at another path is refused", rejectedCopy.known === false, {
    bundlePath: path.basename(rejectedCopy.bundlePath),
  });
  fs.rmSync(impostor, { recursive: true, force: true });

  const aside = path.join(tmp, "genuine.app");
  fs.cpSync(installed.bundlePath, aside, { recursive: true });
  await resign(installed.bundlePath, "tech.example.tampered");
  mark = events().length;
  await run("open", ["-n", installed.bundlePath]);
  const rejectedTamper = await waitFor((e) => e.event === "shim-rejected", 30000, "tamper rejection", mark);
  check(
    "the registered bundle, tampered and re-signed in place, is refused (cdhash mismatch)",
    rejectedTamper.known === true,
  );
  fs.rmSync(installed.bundlePath, { recursive: true, force: true });
  fs.cpSync(aside, installed.bundlePath, { recursive: true }); // restore the genuine bundle

  // 6. kill the host; the shim goes with it; opening the .app relaunches the host.
  host.kill("SIGTERM");
  for (let i = 0; i < 40 && (alive(hostPid) || alive(shimPid)); i++)
    await new Promise((r) => setTimeout(r, 250));
  check("killing the host also ends the shim", !alive(hostPid) && !alive(shimPid));
  const before = events().length;
  await run("open", [installed.bundlePath]);
  const relaunched = await waitFor(
    (e) => e.event === "window-ready" && e.pid !== hostPid,
    60000,
    "relaunch",
    before,
  );
  const owner = (await onScreenWindows()).find((w) => w.pid === relaunched.shimPid && w.layer === 0);
  check(
    "opening the .app with no host running launches the host, which serves the window",
    owner?.owner === "Agent Pad",
    {
      newHostPid: relaunched.pid,
      newShimPid: relaunched.shimPid,
    },
  );
  check("the relaunched host loaded the edited app (v2)", relaunched.title === "Agent Pad v2", {
    title: relaunched.title,
  });
  check("the restored genuine bundle is accepted again", owner?.owner === "Agent Pad");
  try {
    process.kill(relaunched.pid, "SIGTERM");
  } catch {}
}

// The t3 harness registered the app folder as a T3 project; remove it and its threads.
async function cleanupT3() {
  let record;
  try {
    record = Object.values(JSON.parse(fs.readFileSync(path.join(home, "registry.json"), "utf8")).apps)[0];
  } catch {
    return;
  }
  if (!record?.t3Project) return;
  const t3 = which("t3", resolveUserPath(process.env));
  if (!t3) {
    check("the e2e's T3 project was removed", false, { error: "t3 is not on PATH" });
    return;
  }
  const removed = await run(t3, ["project", "remove", appDir, "--force"]).then(
    () => true,
    (e) => e.message,
  );
  check("the e2e's T3 project was removed", removed === true, removed === true ? {} : { error: removed });
}

let error;
try {
  await main();
} catch (e) {
  error = e.message;
  check("e2e ran to the end", false, { error });
} finally {
  // Never leave a host behind: it would hold this home and the output pipe.
  hostChild?.kill("SIGTERM");
  const left = await run("pgrep", ["-f", `--home=${home}`]).catch(() => ({ stdout: "" }));
  for (const pid of left.stdout.split("\n").filter(Boolean)) {
    try {
      process.kill(Number(pid), "SIGTERM");
    } catch {}
  }
}
await cleanupT3();
const result = {
  at: new Date().toISOString(),
  electron: JSON.parse(fs.readFileSync(path.join(ROOT, "node_modules/electron/package.json"), "utf8"))
    .version,
  macos: (await run("sw_vers", ["-productVersion"])).stdout.trim(),
  passed: checks.filter((c) => c.pass).length,
  failed: checks.filter((c) => !c.pass).length,
  checks,
};
fs.mkdirSync(EVIDENCE, { recursive: true });
fs.writeFileSync(path.join(EVIDENCE, "e2e-result.json"), `${JSON.stringify(result, null, 2)}\n`);
if (keep) console.log(`kept ${tmp}`);
else fs.rmSync(tmp, { recursive: true, force: true });
console.log(`\n${result.passed} passed, ${result.failed} failed`);
process.exit(result.failed === 0 ? 0 : 1);
