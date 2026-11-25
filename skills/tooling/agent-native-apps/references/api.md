# `window.agentApp`

Exposed to the app's main frame only. Every method returns a promise. A refused
call rejects with an `Error` whose message starts with a code and a colon, for
example `EPERM: "notifications" is not granted for this version of the app.`
Read the code with `/^([A-Z]+): /.exec(e.message)?.[1]`.

| Call | Permission | Tier |
|---|---|---|
| `info()` → `{id, name, version, harness, harnesses, t3Thread, declared, granted, maxTier}` | none | 1 |
| `window.setTitle(title)`, `window.getBounds()`, `window.setBounds({x, y, width, height})` | none | 1 |
| `dock.setBadge(text)`, `dock.bounce()` | none | 1 |
| `permissions.state()`, `permissions.request(name)` → `boolean` | none | 1 |
| `tray.remove()`, `globalShortcut.unregisterAll()`, `agent.cancel(runId)` | none | 1 |
| `notification.show({title, body})` | `notifications` | 2 |
| `tray.set({title, tooltip})` | `menu-bar` | 2 |
| `globalShortcut.register(accelerator)` → `boolean`; `globalShortcut.onPressed(cb)` | `shortcuts` | 2 |
| `agent.run({prompt, harness?, model?, provider?, edit?, newThread?})` → `runId` | `agent`; `agent-edit` when `edit` is true or the harness is `t3` | 3 |
| `fs.readFile(absPath)`, `fs.writeFile(absPath, text)`, `fs.readdir(absPath)` | `full-access` | 3 |

## Agent events

`agent.onEvent(cb)` and `onHostEvent(cb)` return an unsubscribe function.

```js
agent.onEvent((e) => {
  // every event carries e.runId
  // {type: "text", text}          assistant text
  // {type: "tool", name, input}   a tool the agent used
  // {type: "thread", threadId}    t3 only: the thread this app now keeps
  // {type: "error", message}      a non-fatal problem
  // {type: "done", ok, summary}   exactly one per run, after the process exits
});
onHostEvent((e) => {
  // {type: "version-changed", from, to}   the app's files changed; a reload follows
});
```

`agent.run` options:

- `harness`: one of the manifest's `agent.harnesses`. Defaults to `agent.harness`.
- `edit`: let the agent change the app's files. Always on for `t3`.
- `model`: a model id. For `t3`, pass `provider` with it.
- `newThread`: `t3` only. Start a fresh thread; the default continues the app's thread.

## Error codes

| Code | Meaning |
|---|---|
| `ENOTDECLARED` | The permission is not in `app.json`. |
| `EPERM` | Declared, but not granted for this version (the user said no, or the app changed). |
| `EPOLICY` | Above the host's `--max-tier`. |
| `EVERSION` | The app's files changed since it loaded; it is reloading. Retry after the reload. |
| `EINVALIDAPP` | The folder cannot be hashed (a symlink, too large) or `app.json` is invalid. |
| `EHARNESS` | The harness is not in `agent.harnesses`. |
| `ENOHARNESS` | The harness's CLI is not installed. |
| `EBUSY` | Another app owns that global shortcut. |
| `ENOSYS` | No such method. |

## `app.json`

```json
{
  "name": "My App",
  "icon": "✦",
  "permissions": ["notifications", "agent", "agent-edit"],
  "agent": {
    "harness": "t3",
    "harnesses": ["t3", "claude"],
    "provider": "claudeAgent",
    "model": "claude-haiku-5-5"
  }
}
```

- `name`: 1 to 40 letters, digits, spaces, `.`, `_` or `-`. It becomes the `.app` name, so it must be unique among installed apps.
- `icon`: up to 4 characters; drawn as the Dock icon.
- `permissions`: any of `notifications`, `menu-bar`, `shortcuts`, `agent`, `agent-edit`, `full-access`.
- `agent.provider` is a T3 provider instance id and needs `agent.model`.
