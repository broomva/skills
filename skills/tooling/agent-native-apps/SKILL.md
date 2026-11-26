---
name: agent-native-apps
description: Build an agent-native app — a small web app installed as its own macOS app (Dock icon, menu bar, Cmd-Tab) with an agent wired into it that can use native features and rewrite the app itself. Uses Electron app shims for the window and a T3 Code thread, Claude Code or Codex as the app's agent. Ships a host kit, a scaffold, a validator and an end-to-end check. USE WHEN the user wants to turn an idea or a web page into an installed desktop app with an agent inside, asks for an agentic or agent-native app, wants a Dock or menu-bar tool backed by T3, or asks how Claude's Install as app works and how to build the same thing. NOT FOR ordinary web apps or PWAs, Windows or Linux desktop apps, mobile apps, or packaging an app for distribution.
tier: D
---

# agent-native-apps

An **agent-native app** is a folder, a manifest and an agent:

```
my-app/
  app.json      name, icon, permissions it may ask for, which agent it uses
  index.html    the UI (plus any .js / .css it loads from this folder)
```

Installed, it is a real macOS app with its own Dock icon. Inside it, the page
calls `window.agentApp` for anything native, and `window.agentApp.agent.run()`
puts a coding agent to work in the app's own folder. That agent can change the
app. The host then reloads it and asks for its permissions again.

## The idea in four parts

1. **Shell.** The host writes `<Name>.app`, whose executable is a copy of
   Electron's `app_shim_loader`. Opening it connects to the host, and the host
   draws the app's window inside that process. This is the mechanism behind
   Claude desktop's "Install as app"
   ([electron#54932](https://github.com/electron/electron/pull/54932)).
2. **Bridge.** The page gets one object, `window.agentApp`. Every native power is
   one call, and the host decides each call.
3. **Version-bound grants.** A call passes only if all three hold:
   - `app.json` declares the permission;
   - the user granted it for the app's **current version**, a hash of every file the host serves;
   - it is within the host's policy ceiling.

   Any edit is a new version, so the app asks again.
4. **An agent in the loop.** The app's agent is a T3 thread (or Claude Code, or
   Codex) running in the app folder. With T3 the app keeps one thread, so the
   agent remembers earlier turns and shows up in T3 like any other thread.

## Procedure

Run every step with the script; do not hand-write bundles or manifests.

```sh
ANA="node <this skill's folder>/scripts/ana.mjs"

$ANA doctor                 # 1. what this machine has; fix every FAIL line
$ANA setup                  # 2. once: installs the host kit (Electron 45.5) in ~/.agent-native-apps/host
$ANA new ./my-app --name "My App" --harness t3 --provider claudeAgent --model claude-haiku-5-5
                            # 3. scaffold; omit --provider/--model to use the T3 project's default
#    4. build the app: edit index.html, app.js, style.css in ./my-app
$ANA check ./my-app         # 5. validate exactly as the host will; fix every FAIL line
$ANA install ./my-app       # 6. writes ~/Applications/Agent Native Apps/My App.app and serves it
open ~/Applications/"Agent Native Apps"/"My App.app"
```

Step 4 is the judgment part. Rules that keep an app valid:

- **Everything loads from the app folder.** No CDN scripts, no remote styles, no
  inline `<script>`, no `onclick=` attributes, no iframes. The CSP blocks them
  and `ana check` reports them.
- **Declare only what the app uses** in `permissions`. Each undeclared call fails
  with `ENOTDECLARED`. Each declared one prompts the user once per version.
- **Handle refusals.** Every `window.agentApp` call can reject. The error message
  starts with a code: `EPERM`, `ENOTDECLARED`, `EPOLICY`, `EVERSION`, `EHARNESS`.
- **Subscribe before you run.** Call `agent.onEvent` first, then `agent.run`, and
  buffer events until `run` returns the run id (the template does this).

The full bridge API is in [references/api.md](references/api.md). What the host
enforces, and what it does not, is in
[references/security-model.md](references/security-model.md); read it before
granting an app tier 3.

After the app works, verify the machine end to end (quit any running agent-native
apps and their Electron host first, since macOS launches one host per Electron.app):

```sh
$ANA e2e
```

It installs a copy of the example app in a throwaway home, opens it, and checks
the full host, OS-window, gate, and installed-harness matrix from outside the
host: who owns the window, that the app is in the
Dock, the gate, each harness that is installed, the agent editing its own app,
that a tampered shim is refused, and that opening the app starts the host.

## Choosing the agent

| `agent.harness` | The agent is | Needs | Notes |
|---|---|---|---|
| `t3` | a T3 Code thread in the app folder | the `t3` CLI and a running T3 | Any provider T3 has. One thread per app, kept across runs. The reply arrives when the turn ends. Always needs `agent-edit`. |
| `claude` | `claude -p`, run with no user or project settings | Claude Code | Streams text and tool use. Read-only runs get Read, Glob and Grep only. |
| `codex` | `codex exec` | Codex | Streams. `read-only` or `workspace-write` sandbox. |

Set `agent.harnesses` in `app.json` to let the page pick among several.

## Limits

- macOS only. The host kit needs Electron 45.3 or newer (about 100 MB, installed once).
- Signing is ad hoc, for apps you run on your own machine. Distributing one needs
  the host and every shim signed by the same Apple Developer team.
- **An agent run is tier 3.** There is no OS sandbox around the agent: it runs as
  you. Grant `agent` and `agent-edit` only to apps whose files you trust.
- Notifications and menu-bar items are posted by the host, so macOS attributes
  them to the host, not the app.
- Uninstalling an app leaves its T3 project and threads in T3.

## Files

- `scripts/ana.mjs`: doctor, setup, new, check, install, list, open, uninstall, e2e.
- `assets/host/src/main.js`: the host. `assets/host/src/capabilities.js` is the gate,
  `assets/host/src/manifest.js` the manifest and version, `assets/host/src/harness.js`
  the three agent adapters, `assets/host/src/bundle.js` the shim writer.
- `assets/host/examples/agent-pad/app.json`: a worked example that can use all three harnesses.
- `assets/templates/app/index.html`: the scaffold `ana new` copies.
- `assets/host/scripts/e2e.mjs`: the end-to-end check.
- `tests/ana.test.mjs` and `assets/host/test/capabilities.test.js` (with its siblings): unit tests.
