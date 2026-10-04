# Playbook: macOS apps

Everything here was observed on macOS (Darwin 25) on 2026-10-04 unless marked otherwise. App
versions move, so re-check on the target.

## Bundle anatomy: where the signals are

An app is a directory, `<Name>.app/Contents/`. These are the files that tell you which rungs
exist:

| Signal | Where | What it means |
|---|---|---|
| Bundle id, version | `Info.plist` → `CFBundleIdentifier`, `CFBundleShortVersionString` | This is the installer's version, not necessarily the running one. Obsidian's says 1.8.4 while it runs 1.13.7 from `<profile>/obsidian-1.13.7.asar`; a VS Code fork observed here carried a `product.json` version that differed from its Info.plist. Take the running version from the app itself (e.g. `obsidian version`) and record both. |
| URL schemes | `Info.plist` → `CFBundleURLTypes[].CFBundleURLSchemes` | Rung 2: `open "<scheme>://..."` deep links. Observed: `vscode`, `obsidian`, `slack`, `spotify`, `figma`, `discord`. |
| AppleScript dictionary | `Info.plist` → `OSAScriptingDefinition` names an `.sdef` in `Contents/Resources/` | Rung 2: `osascript` against the dictionary. Observed: Spotify, Google Chrome (`scripting.sdef`), Arc, Safari, Ghostty. |
| App Intents | `Contents/Resources/Metadata.appintents/` | Rung 2: Shortcuts actions. Observed: Ghostty. |
| Electron | `Contents/Frameworks/Electron Framework.framework` | A Chromium renderer plus Node. Observed: VS Code, Obsidian, Slack, Notion, Linear, Discord, Figma. |
| App code (Electron) | `Contents/Resources/*.asar` or `Contents/Resources/app/` | Observed: Obsidian `app.asar` + `obsidian.asar`; Slack per-arch `app-arm64.asar`; VS Code unpacked `app/`. |
| VS Code family | `Contents/Resources/app/product.json` | The extension API (rung 2); `dataFolderName` names the per-user folder (`.vscode` for VS Code). |
| Auto-update | `Contents/Frameworks/Sparkle.framework` | Updates can overwrite or invalidate a file-level mod. Observed: Arc, Ghostty. |
| Mac App Store | `Contents/_MASReceipt` | A store build; usually sandboxed. Observed: Slack. |
| Sandbox | `codesign -d --entitlements - --xml <app>` contains `com.apple.security.app-sandbox` | The app's own reach is limited, and so is a mod running inside it. Observed: Slack yes; Obsidian and Spotify no. |

## Electron fuses: the app's own declared protections

Electron apps carry a "fuse wire" in the `Electron Framework` binary. It is a list of
build-time switches that say which protections the app turned on. Format, from
[`electron/fuses`](https://github.com/electron/fuses) (`src/constants.ts`, `src/config.ts`):
- the ASCII sentinel `dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX`;
- then one version byte and one length byte;
- then one byte per fuse: `0x30` off, `0x31` on, `0x72` removed.

A universal binary carries one wire per architecture slice. Read the wire inside the slice
this machine runs: on Apple Silicon the first match in the file can be the Intel slice.
`scripts/recon_macos_app.py` does this.

The fuses, in wire order:

| Index | Fuse | When it is on |
|---|---|---|
| 0 | RunAsNode | `ELECTRON_RUN_AS_NODE` works |
| 1 | EnableCookieEncryption | |
| 2 | EnableNodeOptionsEnvironmentVariable | `NODE_OPTIONS` is honoured |
| 3 | EnableNodeCliInspectArguments | `--inspect` works |
| 4 | EnableEmbeddedAsarIntegrityValidation | the asar is integrity-checked |
| 5 | OnlyLoadAppFromAsar | |
| 6 | LoadBrowserProcessSpecificV8Snapshot | |
| 7 | GrantFileProtocolExtraPrivileges | |
| 8 | WasmTrapHandlers | |

Wires observed here carried 8 or 9 fuses.

What the fuses mean for the ladder:
- **EnableEmbeddedAsarIntegrityValidation on**: editing the app's files would defeat an
  integrity check, so file-level patching is out of the envelope. Observed on Slack, together
  with OnlyLoadAppFromAsar.
- **Inspect and Node-options fuses off**: the app's makers closed the Node-side debugging
  doors. Respect that. The inspect fuse governs only the Node main process, not the renderer's
  DevTools port. Use that port (rung 3) only when the terms allow client modification. An app
  shipping DevTools to its users is not permission to modify it.
- **Every protective fuse off, and the app ships a plugin API** (Obsidian: only
  GrantFileProtocolExtraPrivileges is on): use the API.

## Rungs for apps, cheapest first

1. **Data and config**: the app's settings, themes and CSS snippets, through the app's own UI
   or files. Obsidian CSS snippets live in `<vault>/.obsidian/snippets/`.
2. **Sanctioned API**: the extension or plugin API, the app's own CLI, AppleScript via
   `osascript`, URL schemes, Shortcuts / App Intents, the Accessibility (AX) API, an MCP
   server if the app ships one.
   - The app's own CLI is often the best input-free way to drive and verify a mod. Examples:
     Obsidian 1.12+ `obsidian` (73 commands, including `plugin:enable`, `dev:dom`,
     `dev:screenshot`), VS Code `bin/code`, Zed `cli`.
   - VS Code: extensions.
   - Obsidian: community plugins in `<vault>/.obsidian/plugins/<id>/` (`manifest.json` + `main.js`).
3. **Patch from inside**: Electron's renderer through the Chrome DevTools Protocol, by
   launching the app with `--remote-debugging-port=<port>` in a lab profile.
   - This runs your script in the page without editing app files, so asar integrity is not
     defeated.
   - An open debugging port is reachable by every local process, so bind it only for the
     session and close it after.
   - If the app's terms prohibit client modification, this rung is out of scope (see the
     envelope).
4. **Hooks and wires**: capture and replay the app's own HTTP traffic to its backend, for
   your own account only; or a native hook. Rarely needed for app mods.
5. **Reimplement**: a small companion app or CLI that does the thing next to the app, using
   its data files or API, instead of changing it.

## Labs: isolated profiles

**The rule that cost a run.** `--user-data-dir` isolates the profile but not the keychain or
`$HOME`.
- Obsidian 1.13.7 writes a keychain item at startup.
- With a lab `HOME` there is no login keychain, so the main thread blocks in a system
  authorization prompt. That prompt can appear on the user's screen, and every IPC channel then
  hangs behind it.
- Fix: always add `--use-mock-keychain` to Electron apps, and set `HOME=<lab>/home` only
  together with it. Some apps bind sockets in `$HOME`: Obsidian's CLI server unlinks and binds
  `~/.obsidian-cli.sock` on every start, so a lab on the real `HOME` would take over the
  user's CLI.

- **VS Code**: `"/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
  --user-data-dir <lab>/data --extensions-dir <lab>/ext`. Both flags are in `code --help`.
  The user's real profile is untouched. Also set `"update.mode": "none"` in the lab's
  `settings.json`, so the lab instance does not update the shared app.
- **Electron apps generally**: `--user-data-dir=<lab>` is a Chromium switch most Electron apps
  honour (not verified per app; check that the lab profile starts empty).
- **Obsidian**: a lab vault alone is not a lab.
  - A vault opened in the user's profile registers in the user's `obsidian.json`, and
    `obsidian://` URLs route to the running instance.
  - Use a lab profile as well: `--user-data-dir=<lab>/data`, pre-seeded with
    `obsidian.json` = `{"vaults": {"<16 hex>": {"path": "<lab vault>", "open": true}}, "cli": true}`.
  - Never use `obsidian://` in a lab.
  - Run `obsidian plugins:restrict off` before installing a plugin, or a consent modal blocks it.
  - `examples/obsidian-kg-claims/harness/lab.py` wires all of this.
- **Chrome / Arc**: a separate `--user-data-dir` profile for Chrome.

**What a lab profile does not isolate** (not observed failing in a run yet; reasoned from how
macOS works):
- **The installed app and its updater.** An updater running in the lab (Squirrel, Sparkle)
  updates `/Applications/<App>.app` for the user too. Turn updates off in the lab where the
  app allows it. Obsidian downloads updates into the profile, so its lab is safe from this.
- **System preferences and saved state.** CoreFoundation resolves the home folder from the
  user record, not `$HOME`, so `~/Library/Preferences/<bundle-id>.plist` and Saved
  Application State are shared with the lab.
- **The user's file access.** A plugin or script you run in the lab can read and write
  anything the user can. Keep the code you run there to the code you wrote.
- **macOS permissions (TCC).** Bluetooth, Screen Recording and Accessibility grants belong to
  the responsible process, not the profile. A lab that needs one raises a system dialog;
  that grant is the user's call, so ask.
- **The keychain, beyond Electron.** Chrome and Arc also reach the login keychain. Use
  `--use-mock-keychain` (Chrome also accepts `--password-store=basic`) in their lab profiles.
- **Checking you left no trace.** A directory's modification time does not change when a file
  inside it is appended to. To prove you left the user's profile alone, hash its files before
  and after.

## Launching and stopping

- **Launch** in the background as a new instance, never the user's:
  `open -g -n -a <App> --env K=V --args --user-data-dir=<lab> --use-mock-keychain`.
- **Find** the PID by its exact command line (including the lab path), never by name.
- **Stop** that PID with SIGTERM. A macOS app can survive SIGTERM without windows; send a
  second SIGTERM to the same PID.
- **A main thread blocked in a system prompt ignores SIGTERM**: `sample <pid> 1` to confirm,
  then SIGKILL that exact PID.
- **Never** `pkill` or `killall`.

## Verifying in the running app

- **Screenshots from inside the app need no permission**, for example Obsidian
  `dev:screenshot` or Electron `webContents.capturePage()`. Prefer them.
  `screencapture -l <windowid>` needs the Screen Recording permission for the calling process:
  without it, it fails with "could not create image from window", even though window names
  stay readable.
- **Logs**: the extension or plugin's own console output (VS Code: the Output panel or
  `--verbose`; Electron: the DevTools console over CDP).
- **State**: what the API reports back, such as a command's return value or a file the mod
  writes.
- Record each with `modlog.py ok --evidence <file>`.

## Gotchas to expect (reasoned, not yet hit)

The gotchas actually hit are in `field-notes/obsidian/kg-claims-inline.md`.


1. A Mac App Store build is sandboxed → its own file access is limited, so a mod inside it is
   too → use the app's API or URL scheme, not file paths outside its container.
2. Sparkle updates the app in place → a file-level mod disappears or breaks the signature →
   prefer rung 2 or a launch-time rung 3 that re-applies per session.
