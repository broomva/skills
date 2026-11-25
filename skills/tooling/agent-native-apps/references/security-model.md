# What the host enforces, and what it does not

Read this before you grant an app a tier 3 permission.

## Enforced, and tested

Each line names the test that fails if the guard is removed. Unit tests are in
`assets/host/test/`; "e2e" is a step of `assets/host/scripts/e2e.mjs`.

| Property | Where it is checked |
|---|---|
| Only the exact bundle the host wrote can connect: a copy at another path, or the registered bundle re-signed, is refused | e2e: both shim-trust steps |
| The window belongs to the app's process; the host has no window or Dock icon | e2e: CGWindowList and LaunchServices steps |
| The version covers every file the host serves: dot-folders and `node_modules` (any casing) are neither served nor hashed | `manifest.test.js`: served set equals hashed set; e2e: 404 + `/NODE_MODULES/` step |
| Two different folders never share a version (length-prefixed hash) | `manifest.test.js`: NUL-joined file test |
| No symlink can serve or hide a file outside the app folder | `manifest.test.js`: symlink tests |
| A folder that cannot be hashed leaves the app with no version: nothing is granted or served | e2e: symlink step (503 and refusal) |
| A grant applies to one version; an edit drops it, the tray item and the shortcuts | `registry.test.js`; e2e: self-edit steps |
| A gated call re-hashes first, so an edit the watcher has not reported yet still counts | e2e: symlink step |
| The policy ceiling refuses higher tiers, survives a relaunch, and refuses on a bad value | `capabilities.test.js`, `args.test.js` |
| A prompt re-hashes the folder from disk after consent and grants only if the app is open and still matches | `capabilities.test.js`: `authorizeAfterPrompt` + mutant |
| Async agent setup (e.g. `ensureT3Project`) re-checks close, disk version, and grant before spawning | `capabilities.test.js`: `guardAsyncLaunch` + mutant |
| Browser permission APIs (`Notification`, media, geolocation, etc.) are denied on every app partition so they cannot bypass `window.agentApp` | e2e: browser `Notification.requestPermission()` denied step |
| The page cannot navigate away, open windows, download, or read another app's files | e2e: navigation, window.open and cross-app steps |
| Calls are accepted from the app's main frame only | code review only; the CSP forbids frames, so no test can make one |
| The prompt reaches the CLI on stdin, never as an argument | `harness.test.js`; e2e: Claude step with a `--help` prompt |
| Claude runs with no user settings, no project settings and no MCP servers | `harness.test.js` (arguments); probed once by hand, not in the e2e |
| The agent's environment is an allowlist, not the host's | `harness.test.js` |
| A run is over only when its process has exited; for local CLIs (`claude`, `codex`), cancel signals the whole process group including descendants | `harness.test.js` (live grandchild test + mutant) |
| The page may use only the harnesses `app.json` lists | e2e: EHARNESS step |

## Not enforced

- **The agent is not sandboxed.** It runs as you, with the app folder as its
  working directory.
  - A read-only Claude run has Read, Glob and Grep, which accept any path you can read.
  - Codex's `read-only` sandbox blocks writes, not reads, and it can run shell commands.
  - A T3 thread runs with its project's runtime mode, which is full access by default.

  That is why every agent permission is tier 3. Confining the agent needs an OS
  sandbox around the CLI, which this kit does not have.
- **Codex and T3 read your own configuration.** Only the Claude adapter turns
  user settings and MCP servers off.
- **`full-access` is what it says.** `fs.*` takes any absolute path.
- **Nothing reviews an app's code.** The version tells you the code has not
  changed since you granted it, not that it was safe when you did.
- **Signing is ad hoc.** It proves a shim is the one this host wrote on this
  machine. It says nothing to anyone else.
- **Cancelling a `t3` run stops the local waiter, not the server turn.** The
  `t3 thread` CLI exposes `list`, `start`, `send`, and `show` only (no interrupt
  subcommand), so `agent.cancel(runId)` terminates the local waiting `t3` CLI
  client while any active server-side turn keeps running until stopped in T3 Code.
- **The registry is a file** in the host's home (mode 600), not the keychain.
  Anything running as you can edit it.
