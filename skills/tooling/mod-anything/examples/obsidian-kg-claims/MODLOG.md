# MODLOG — Obsidian 1.8.4 installer (app code self-updates; owner runs 1.13.7), macOS 26.5.2 arm64

- Idea: When the owner reads a markdown note containing a [[slug]] wikilink to a knowledge-graph entity, Obsidian shows that entity's core_claim inline and on hover.
- Done means: In a lab vault opened by the real Obsidian app, a note with [[slug]] links renders each entity's core_claim inline in reading view, shown by a window screenshot and a state dump written by the plugin; owner's profile and vault untouched.
- Started: 2026-10-04T13:53:35Z

Anything not in this journal is lost at the next context compaction.

## Route #1 — rung 2 (sanctioned API): Obsidian community plugin API (markdown post-processor in reading view) (sub-goal: show core_claim for [[slug]] links in reading view)

2026-10-04T13:53:50Z · Reason: Recon over the installed editors and note apps (examples/recon-macos-apps/). Rung 1 cannot: a CSS snippet cannot read another file's frontmatter. Rung 2 candidates: Obsidian plugin API, VS Code-family extension APIs; an editor whose extensions are Rust->WASM with a language server (hover only, most work); writing apps that expose only App Intents/URL schemes (cannot add UI); note apps with no sanctioned extension point. Obsidian wins: the owner's vault (the knowledge graph is linked into it) is where [[slug]] notes are read, Obsidian already resolves [[slug]] to the entity file, and its metadataCache exposes frontmatter, so the plugin needs no file paths or fs. Terms (obsidian.md/terms, 2025-02-20) forbid modifying the Software and allow reverse engineering only to develop third-party plugins, so rung 3 (renderer patch over CDP) is out of scope. Known lab cost: plugins load only after the vault leaves restricted mode, a consent stored in localStorage. VS Code extension API is the fallback if the Obsidian lab cannot be driven without input.

- OK (2026-10-04T13:53:50Z, route #1): recon: ten apps ranked by recon_macos_app.py; Obsidian rung 2 plugin API chosen — evidence: `../recon-macos-apps/obsidian.json`, `../recon-macos-apps/summary.tsv`, `../recon-macos-apps/visual-studio-code.json`

- OK (2026-10-04T13:56:13Z, route #1): lab: Obsidian launched with --user-data-dir=<lab>/obsidian-data and a pre-seeded obsidian.json opens the lab vault; the launcher downloaded obsidian-1.13.7.asar into the lab profile (first run still ran the bundled 1.8.4); renderer console reaches stderr with --enable-logging=stderr. Restore path: delete the lab dir; the owner's profile is not touched (stat snapshot taken before). — evidence: `evidence/lab1-launcher.log`, `evidence/lab1-stderr-excerpt.txt`

- FAIL (2026-10-04T13:56:13Z, route #1, x1): screencapture cannot capture the lab window — screencapture -l <id> -> 'could not create image from window'; even -R 0,0,50,50 fails: this process has no Screen Recording permission (window names are still readable via CGWindowList). Verify through the app's own CLI (dev:screenshot uses webContents.capturePage) instead.

- FAIL (2026-10-04T14:03:10Z, route #1, x1): obsidian cli client hangs and the lab main instance dies — harness cli: 4 calls each timed out at 30 s; the lab main was gone afterwards and later clients took the singleton lock

- FAIL (2026-10-04T14:03:10Z, route #1, x2): obsidian cli client hangs and the lab main instance dies — single client by hand: no output, main never logged 'Received command line', main died between +8 s and +42 s. Hypothesis: this agent shell is sandboxed, the client cannot reach the main's Chromium SingletonSocket, and ProcessSingleton kills the 'hung' main. Next: launch the client through LaunchServices (open -W), outside the shell sandbox.

- FAIL (2026-10-04T14:03:56Z, route #1, x3): obsidian cli client hangs and the lab main instance dies — client launched through LaunchServices (open -W -g -n) hangs the same way and the main dies: the shell-sandbox hypothesis is refuted
- STALL: re-rank the routes for this sub-goal; first check whether the original can simply be run.

## Route #2 — rung 3 (patch from inside): session-bound DevTools Protocol to call the app's own app.plugins.setEnable(true), then a normal launch with a lab-only probe plugin that writes evidence (sub-goal: lab only: leave restricted mode and capture evidence without input, CLI unavailable)

2026-10-04T14:05:08Z · Reason: STALL re-rank for this sub-goal (the mod itself stays rung 2). 1) Run the original: the app runs fine alone; what fails is the second-process CLI client, which never gets past the single-instance handshake on installer 1.8.4 (it never prints its own 'installer is out of date ... better CLI support' line), and Chromium then kills the lab main as hung. Updating the installer in /Applications needs an ask, so the CLI is out for this run. 2) Cheaper rung: restricted mode lives in localStorage, so no rung-1 file reaches it. 3) Oracle: the running app, not my reading, refuted the sandbox hypothesis (LaunchServices-launched clients fail the same way). Chosen: --remote-debugging-port on 127.0.0.1 for one lab session only, calling the same setter the Settings toggle calls; no input events, no app files touched, port closed after. Then relaunch with no debugging port so the mod loads exactly as it would for the owner, and a lab-only probe plugin (harness/, never shipped) dumps the rendered claims and a capturePage PNG into the lab vault. Obsidian ships DevTools to its users (View > Toggle Developer Tools), so this is not a door its makers closed.

- FAIL (2026-10-04T14:09:22Z, route #2, x1): lab main blocked in keychain authorization — CDP endpoint accepts TCP but never answers; sample shows the main thread in JS -> SecKeychainAddGenericPassword -> AuthorizationCopyRights. Cause: my lab knob HOME=<lab>/home leaves the Security framework without a login keychain, so it waits for a human. This, not the installer, explains the three CLI hangs (Chromium's single-instance handshake also needs the UI thread). SIGTERM could not land; SIGKILL on the exact lab PID.

## Route #3 — rung 2 (sanctioned API): Obsidian's own CLI (plugins:restrict, plugin:enable, open, dev:dom, dev:screenshot) against a lab launched with HOME=<lab>/home and --use-mock-keychain (sub-goal: lab only: leave restricted mode and capture evidence without input)

2026-10-04T14:09:34Z · Reason: Correction to route #2: the oracle (a stack sample of the running lab main) showed the CLI was never broken. The main thread was blocked in a login-keychain authorization request that my own HOME override caused, and every IPC channel (Chromium single-instance socket, Obsidian CLI socket, DevTools port) waits on that thread. The installer-1.8.4 explanation in route #2 was a guess, and it was wrong. Fix: Chromium's --use-mock-keychain switch, so the lab never reaches a keychain (neither a missing one, nor the owner's real login keychain, which a lab on the real HOME would read). Keep HOME=<lab>/home so the CLI socket stays in the lab. Back on rung 2: the app's own CLI is cheaper and more sanctioned than a DevTools port, so route #2 is dropped.

- OK (2026-10-04T14:11:14Z, route #3): lab fixed: with --use-mock-keychain the lab main thread has no keychain frames, no SecurityAgent starts, and the app's own CLI answers ('1.13.7 (installer 1.8.4)') — evidence: `evidence/cli-session.txt`

- OK (2026-10-04T14:11:14Z, route #3): restricted mode left and kg-claims enabled through the app's own CLI (plugins:restrict off, reload, plugin:enable id=kg-claims) — evidence: `evidence/cli-session.txt`

- OK (2026-10-04T14:11:14Z, route #3): vertical slice in the running app: reading view shows the core_claim inline after all 5 entity links (incl. alias and #heading forms) and as each link's title; plain-note and the dangling link get nothing (dev:dom + dev:screenshot) — evidence: `evidence/cli-session.txt`, `evidence/reading-view.png`

- OK (2026-10-04T14:12:50Z, route #3): live update: changing the lab copy's core_claim through the app (property:set) re-renders the open note with the new claim; the real entity file is unchanged — evidence: `evidence/cli-live-update.txt`

- OK (2026-10-04T14:12:50Z, route #3): restart: after stopping the lab main by PID and relaunching with no other action, the plugin is still enabled and all 5 claims render at startup — evidence: `evidence/cli-restart.txt`, `evidence/after-restart.png`

- OK (2026-10-04T14:12:50Z, route #3): uninstall path: plugin:disable removes every claim span and every title/data-kg-claim it set; plugin:enable brings all 5 back — evidence: `evidence/cli-disable.txt`

- FAIL (2026-10-04T14:14:50Z, route #3, x1): lab stop: first sigterm leaves obsidian running windowless — re-run lab ISmV: after SIGTERM the window closed but the main idled in NSApplication run for 50 s (macOS app convention: no windows is not quit); a second SIGTERM to the same PID quit it in 1 s

- OK (2026-10-04T14:18:02Z, route #3): the shipped harness reproduces the slice in a fresh mktemp lab by following INSTALL.txt literally: five claims, none for plain-note or the dangling link — evidence: `evidence/rerun-fresh-lab.txt`

- FAIL (2026-10-04T14:18:02Z, route #3, x1): enabled plugin list found empty after a restart — once, in the fresh lab, right after a stop that needed two SIGTERMs; not reproduced in 5 later restarts (all kept ['kg-claims'] and rendered 5 claims at startup). Cause not established.

- OK (2026-10-04T14:18:02Z, route #3): fixed harness stop (second SIGTERM to the same PID) verified; restart persistence held in 5 of 6 restarts, the exception recorded as unexplained — evidence: `evidence/restart-rounds.txt`, `evidence/restart-empty-list.png`

- OK (2026-10-04T14:18:15Z, route #3): owner untouched: the owner's Obsidian profile metadata is identical before/after, no ~/.obsidian-cli.sock, the source entities are git-clean, no lab process left running — evidence: `evidence/owner-untouched.txt`

- NOTE (2026-10-04T14:29:15Z): Before publication (reviewer, 2026-10-04): replaced the copied real entities with synthetic fixtures (harness/fixtures/entities/), added harness/record_evidence.sh, and regenerated cli-session, cli-live-update, cli-restart, cli-disable, reading-view.png and after-restart.png from it. Removed rerun-fresh-lab.txt and restart-empty-list.png (private claims or slugs). Entries above that cite those files describe the first run. — evidence: `evidence/cli-session.txt`, `evidence/after-restart.png`, `harness/record_evidence.sh`

- NOTE (2026-10-04T14:50:39Z): Review round 2 (2026-10-04): the fixtures were replaced by neutral topics, the lab vault's entity folder was renamed to entities, the vault path in route #1's reason was generalized, and the plugin now clears its pending timer on unload. The evidence was then regenerated by harness/record_evidence.sh. Earlier entries citing evidence/rerun-fresh-lab.txt and evidence/restart-empty-list.png describe the first run; both files were removed before publication. — evidence: `harness/record_evidence.sh`

- NOTE (2026-10-04T15:33:41Z): Before publication: examples/recon-macos-apps/ was trimmed to three common apps (Obsidian, VS Code, Spotify). Entries above that say ten describe the run itself. — evidence: `../recon-macos-apps/summary.tsv`

