# Obsidian 1.13.7: show a linked entity's `core_claim` next to its [[wikilink]]

A community plugin (`kg-claims`) that, in reading view, prints the target note's
`core_claim` frontmatter inline after each internal link and sets it as the link's hover
title. Source, journal and evidence: `examples/obsidian-kg-claims/` (all paths below are
relative to the skill root).

## Versions

- Target: Obsidian app code 1.13.7 on installer 1.8.4. The app's own `obsidian version` says
  `1.13.7 (installer 1.8.4)`. Info.plist `CFBundleShortVersionString` says only 1.8.4, and the
  installer ships Electron 33.3.2.
- Platform: macOS 26.5.2 (25F84), Apple Silicon (arm64).
- Tools: plain CommonJS plugin, no build step, against the `obsidian` module the app provides;
  Obsidian's built-in CLI (1.12+) to drive the lab; Python 3.14 stdlib harness
  `examples/obsidian-kg-claims/harness/lab.py`; `scripts/recon_macos_app.py` for recon.

## Route

1. Rung 2 (the mod), the Obsidian community plugin API: `registerMarkdownPostProcessor`,
   `metadataCache.getFirstLinkpathDest` and `getFileCache(file).frontmatter.core_claim`.
   - Why Obsidian: the owner reads [[slug]] notes in an Obsidian vault, Obsidian already resolves
     the link, and its cache already parsed the frontmatter, so the plugin needs no file system and
     no paths.
   - Why not rung 1: a CSS snippet cannot read another note's frontmatter.
   - Why not rung 3: the terms forbid modifying the Software.
   - What recon ranked below it: the VS Code and Antigravity IDE extension API (rung 2, but
     [[slug]] is not a link there), Zed extensions (Rust to WASM plus a language server, hover
     only), Ulysses and Goodnotes (App Intents and URL schemes, which cannot add UI), and Notion
     and Superlist (no sanctioned extension point).
2. Rung 2, lab sub-goal (leave restricted mode and capture evidence with no input):
   Obsidian's own CLI.
   - It stalled three times: the CLI client hung and the lab main died.
   - Re-rank to rung 3: a session-bound DevTools port. The reason was a wrong diagnosis
     ("installer too old"). The port hung the same way and never ran a command.
   - A stack sample of the running main showed the real cause, gotcha 2.
   - Re-rank back to rung 2: the CLI plus `--use-mock-keychain`, which worked. The DevTools
     code was removed.
- Stall on route #1 (the lab sub-goal on the CLI), x3. It was re-ranked to route #2, and route #3
  corrected that re-rank. MODLOG.md keeps the wrong guess as written.

## What it really does

- **The version is not in the bundle.** The launcher (`app.asar`) loads the newest
  `obsidian-<ver>.asar` from the profile folder. A fresh `--user-data-dir` profile runs the
  installer's bundled 1.8.4, downloads the current release into the profile (signature-checked),
  and runs it from the next launch.
- **`--user-data-dir` is honoured.** The vault registry (`obsidian.json`), localStorage and
  `obsidian.log` all live there. A pre-seeded
  `{"vaults": {"<16 hex>": {"path": "<lab vault>", "open": true}}}` opens the lab vault with no
  input.
- **Restricted mode.** It is a per-vault localStorage flag, `enable-plugin-<appId>`. If the flag
  is unset and a plugin folder exists at startup, a consent modal opens.
- **The 1.12+ CLI.** On every start, whether the CLI is turned on or not, the app unlinks and
  binds `os.homedir()/.obsidian-cli.sock`. Commands run only with `"cli": true` in
  `obsidian.json`. The client is the same binary: it first meets the Chromium single-instance
  lock (per user-data-dir), then the socket. It offers 73 commands, among them
  `plugins:restrict`, `plugin:enable`, `open`, `property:set`, `dev:dom` and `dev:screenshot`
  (`webContents.capturePage`).
- **The keychain.** 1.13.7 adds a keychain item from JS at startup, on the main thread
  (`SecKeychainAddGenericPassword`).
- **Console logging.** 1.13.7 appends `log-level=3`, so `--enable-logging=stderr` shows renderer
  `CONSOLE` lines only while the 1.8.4 app code runs.
- **What reading view hands the post-processor.** `a.internal-link[data-href]`.
  - `[[x|alias]]` keeps `data-href="x"`.
  - `[[x#Heading]]` gives `"x#Heading"`, which `getLinkpath` strips.
  - Dangling links and links to notes without `core_claim` get nothing.
- **Re-rendering.** Claims render on open, at startup after a restart, and again when an entity's
  frontmatter changes (`metadataCache` `changed`).
- **Unexplained.** In the first session, three CLI commands (`open`, `property:set`,
  `dev:screenshot`) printed nothing although their effects landed. Five later `open` calls
  printed `Opened: ...`.

## Verification

- The plugin renders in the running app: five claims after the five entity links, including the
  alias and `#heading` forms, each also set as the link's `title`. `plain-note` and the dangling
  link get nothing. Evidence: `examples/obsidian-kg-claims/evidence/cli-session.txt` and
  `examples/obsidian-kg-claims/evidence/reading-view.png`.
- Changing the lab copy's `core_claim` re-renders the open note:
  `examples/obsidian-kg-claims/evidence/cli-live-update.txt`.
- A restart renders the claims at startup with no other action:
  `examples/obsidian-kg-claims/evidence/cli-restart.txt` and
  `examples/obsidian-kg-claims/evidence/after-restart.png`. It held in 5 of 6 restarts; the
  exception is in `examples/obsidian-kg-claims/evidence/restart-rounds.txt`.
- Disabling the plugin removes everything it added:
  `examples/obsidian-kg-claims/evidence/cli-disable.txt`.
- The evidence above was regenerated from synthetic fixture entities by
  `examples/obsidian-kg-claims/harness/record_evidence.sh`, which runs the whole lab end to end in a
  fresh lab profile. The first run used copies of real entities; those transcripts and screenshots
  were removed before publication.
- The diagnosis of the hang: `examples/obsidian-kg-claims/evidence/main-thread-blocked-keychain.txt`
  and `examples/obsidian-kg-claims/evidence/cli-hang.txt`.
- The owner's profile, home and entities are untouched:
  `examples/obsidian-kg-claims/evidence/owner-untouched.txt`.
- Not verified:
  - the hover tooltip appearing on screen (it needs mouse input; only the `title` attribute is
    checked);
  - Live Preview and source mode (out of this slice);
  - the owner's real vault, where the knowledge-graph folder is a symlink (the lab used
    copied synthetic files).

## Gotchas

1. `screencapture -l <id>` prints "could not create image from window", and even `-R 0,0,50,50` fails → the agent's process has no Screen Recording permission (CGWindowList still returns window names) → capture through the app instead: `obsidian dev:screenshot path=<file>` uses `webContents.capturePage` and needs no permission or input.
2. Lab CLI calls hang, the lab main then disappears, and a DevTools port accepts TCP but never answers → launching with `HOME=<lab>/home` leaves the Security framework without a login keychain, so the main thread blocks in a login-keychain authorization prompt (`SecKeychainAddGenericPassword` → `AuthorizationCopyRights`, and SecurityAgent starts), and every IPC channel waits on that thread → add Chromium's `--use-mock-keychain` to the lab launch and to the CLI client, and run `sample <pid> 1` before theorising about a hang.
3. A lab Obsidian started with the real HOME would take over the user's CLI → the 1.12+ server unlinks and binds `~/.obsidian-cli.sock` on every start, whatever the CLI setting → always launch labs with `HOME=<lab>/home` plus the mock keychain from gotcha 2.
4. In a fresh lab vault a consent modal covers the window and the plugin never loads → restricted mode is a per-vault localStorage flag, and the modal opens at startup when a plugin folder exists and the flag is unset → open the vault once with no plugin folder, run `obsidian plugins:restrict off`, then install and run `obsidian plugin:enable id=kg-claims`.
5. A fresh lab runs Obsidian 1.8.4, which has no CLI → the bundle carries the installer's app code; the launcher downloads the current release into the profile and uses it from the next launch → do a warm-up launch, stop, then relaunch (`lab.py launch` does this).
6. After SIGTERM the window is gone but the process idles in `NSApplication run` → a macOS app with no windows has not quit → send a second SIGTERM to the same PID (`lab.py stop` does this), never `pkill`.
7. A bare `[[slug]]` shows the claim of an unexpected entity → two entities share the slug in different type folders (the fixtures' `concept/garden-map` and `tool/garden-map`), and Obsidian resolves a bare `[[slug]]` to one of them (`tool/` in the lab) → link with the folder (`[[concept/garden-map]]`) or keep slugs unique. The mod deliberately shows the claim of the file the link opens.
8. Once, after a restart, the plugin was off and `community-plugins.json` held `[]` → cause not established: it was seen once, after a stop that needed two SIGTERMs, and the CLI answers `Enabled` before the plugin manager's 1 s debounced save → wait at least 1 s after `plugin:enable` and check `community-plugins.json` before stopping; check `plugins:enabled` after a restart.

## Envelope

- Rung: 2 for the mod (Obsidian's community plugin API). The lab was driven by Obsidian's own
  CLI.
- A rule was crossed under the stall. Route #1 ruled rung 3 out under Obsidian's terms. After
  the stall, route #2 re-ranked to rung 3 anyway: a lab-only DevTools port meant to flip
  restricted mode. It never ran a command (it hung on the same keychain prompt), and route #3
  returned to rung 2. A stall is not a reason to cross the rules, and the skill's STALL
  checklist now says so first.
- Terms checked: the [Obsidian Terms of Service](https://obsidian.md/terms), last updated
  2025-02-20.
  - The customer shall not "create derivative works based on or otherwise modify the Services
    or Software". No app file was modified.
  - Reverse engineering is barred "except for the purpose of developing Third Party Plugins for
    non-commercial use". Reading `app.js` and `main.js` was for developing this plugin, which is
    non-commercial and uses the published plugin API.
- Bytes shipped:
  - our own `plugin/` (manifest.json, main.js, styles.css), `harness/lab.py`,
    `harness/record_evidence.sh`, the fixture notes and synthetic entities, INSTALL.txt and the
    evidence;
  - no Obsidian bytes and no entity files. `publish_check.py` exits 0.
  - The published evidence and fixtures are synthetic (`harness/fixtures/entities/`). The first
    run's transcripts and screenshots quoted the owner's private knowledge graph and were removed.
- Disclosure: none found. The CLI socket accepts commands, including `eval`, from any process of
  the same user once the user turns the CLI on. That is the documented design, not a flaw.
