// Writes the shim: a real macOS .app whose executable is a copy of Electron's
// app_shim_loader and whose Info.plist names this host. Launching it connects
// to the host's shim server (electron#54932); the host then creates the app's
// window inside the shim's process, so the Dock, Cmd-Tab and the menu bar show
// the app, not the host.

import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export const BUNDLE_ID_PREFIX = "tech.broomva.agent-native-apps.app.";
export const EXECUTABLE = "agent-app";

function xml(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function plistValue(value) {
  if (value === true) return "<true/>";
  if (value === false) return "<false/>";
  if (Array.isArray(value)) return `<array>${value.map(plistValue).join("")}</array>`;
  return `<string>${xml(value)}</string>`;
}

/** Info.plist text. Pure. */
export function infoPlist({ installId, name, hostPath, hostBundleId, serverName, launchArguments, hasIcon }) {
  const keys = [
    ["CFBundleExecutable", EXECUTABLE],
    ["CFBundleIdentifier", BUNDLE_ID_PREFIX + installId],
    ["CFBundleName", name],
    ["CFBundleDisplayName", name],
    ["CFBundlePackageType", "APPL"],
    ["CFBundleShortVersionString", "1.0"],
    ["CFBundleVersion", "1"],
    ["NSHighResolutionCapable", true],
    ["NSPrincipalClass", "NSApplication"],
    ...(hasIcon ? [["CFBundleIconFile", "app"]] : []),
    ["AgentNativeAppId", installId],
    ["ElectronAppShimHostPath", hostPath],
    ["ElectronAppShimHostBundleIdentifier", hostBundleId],
    ["ElectronAppShimServerName", serverName],
    ["ElectronAppShimHostArguments", launchArguments],
  ];
  const body = keys.map(([k, v]) => `  <key>${xml(k)}</key>${plistValue(v)}`).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
${body}
</dict>
</plist>
`;
}

/** The host .app, its bundle id and its loader, from the running Electron. */
export function hostInfo(execPath = process.execPath) {
  const hostPath = path.resolve(execPath, "..", "..", "..");
  const plist = fs.readFileSync(path.join(hostPath, "Contents", "Info.plist"), "utf8");
  const hostBundleId = /<key>CFBundleIdentifier<\/key>\s*<string>([^<]+)<\/string>/.exec(plist)?.[1];
  if (!hostBundleId) throw new Error(`No CFBundleIdentifier in ${hostPath}`);
  const loaderPath = path.join(
    hostPath,
    "Contents/Frameworks/Electron Framework.framework/Helpers/app_shim_loader",
  );
  if (!fs.existsSync(loaderPath))
    throw new Error(`${loaderPath} is missing: app shims need Electron 44.x/45.3+.`);
  return { hostPath, hostBundleId, loaderPath };
}

/** Parse `codesign -dvvv` output for the CDHash. Pure. */
export function parseCdhash(codesignOutput) {
  return /^CDHash=([0-9a-f]{40,64})$/m.exec(codesignOutput)?.[1] ?? null;
}

/**
 * Write and ad-hoc sign the shim bundle. Returns its cdhash, which the host
 * pins: a shim whose running code does not match is refused on connect.
 */
export function writeShimBundle({ bundlePath, loaderPath, icns, ...plistKeys }) {
  fs.rmSync(bundlePath, { recursive: true, force: true });
  const contents = path.join(bundlePath, "Contents");
  fs.mkdirSync(path.join(contents, "MacOS"), { recursive: true });
  fs.mkdirSync(path.join(contents, "Resources"), { recursive: true });
  const exe = path.join(contents, "MacOS", EXECUTABLE);
  fs.copyFileSync(loaderPath, exe);
  fs.chmodSync(exe, 0o755);
  if (icns) fs.writeFileSync(path.join(contents, "Resources", "app.icns"), icns);
  fs.writeFileSync(path.join(contents, "Info.plist"), infoPlist({ ...plistKeys, hasIcon: Boolean(icns) }));
  fs.writeFileSync(path.join(contents, "PkgInfo"), "APPL????");
  execFileSync("codesign", ["--force", "--sign", "-", bundlePath], {
    stdio: "pipe",
  });
  // codesign prints its details on stderr.
  const shown = spawnSync("codesign", ["-dvvv", bundlePath], {
    encoding: "utf8",
  });
  if (shown.status !== 0) throw new Error(`codesign -dvvv failed for ${bundlePath}: ${shown.stderr}`);
  const cdhash = parseCdhash(`${shown.stdout}\n${shown.stderr}`);
  if (!cdhash) throw new Error(`No CDHash for ${bundlePath}`);
  return cdhash;
}

/** icns container from PNG buffers keyed by size. Pure. */
export function icnsFromPngs(pngBySize) {
  const types = [
    ["ic11", 32],
    ["ic12", 64],
    ["ic07", 128],
    ["ic13", 256],
    ["ic08", 256],
    ["ic14", 512],
    ["ic09", 512],
    ["ic10", 1024],
  ];
  const chunks = types
    .filter(([, size]) => pngBySize[size])
    .map(([type, size]) => {
      const png = pngBySize[size];
      const header = Buffer.alloc(8);
      header.write(type, 0, "latin1");
      header.writeUInt32BE(8 + png.length, 4);
      return Buffer.concat([header, png]);
    });
  const body = Buffer.concat(chunks);
  const header = Buffer.alloc(8);
  header.write("icns", 0, "latin1");
  header.writeUInt32BE(8 + body.length, 4);
  return Buffer.concat([header, body]);
}
