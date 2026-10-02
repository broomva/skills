# Changelog: fleet-reconcile

## [0.4.0] - 2026-10-01

The fleet uses the owner's gh login. Owner decision, 2026-10-01: no fleet
token or GitHub App ("it's fine that it goes as me"), and spec §5.2's
non-admin credential precondition is waived. The accepted residual is that
the fleet acts with the owner's admin rights: a ruleset binds that login only
as far as it lets an admin through, so the driver brief (never touch rulesets
or workflows) and phase 3's checks are what hold a driver to the rules. With
no token, nothing in code keeps a tick dry but the config's `dry_run` (dry by
default; only an exact 0 is live). Ticket BRO-2674.

- **No token anywhere.** tick.sh no longer reads `gh_token_file` (accepted,
  not read) and drops a `GH_TOKEN` or `GITHUB_TOKEN` it inherits, and
  `Sources` drops both too, so a `fleet` command run from a shell that has
  one still reads GitHub as the owner's login; the coordinator gets none; a
  live spawn and a live label no longer need one; a live tick runs its
  coordinator without one.
- **The driver profile carries no token** and no longer denies reading gh's
  config or the login keychain; the ~/.paseo, ~/.claude and settings-file
  denies stay. Measured in a credential drill on a private scratch repo
  (`~/.config/broomva/fleet/credential-drill-20261001/`): inside the sandbox
  `gh auth token` reads the owner's login without the network, git pushes
  through gh's credential helper, and curl opens a PR, updates a branch and
  squash-merges through REST. gh's own network calls fail TLS there (OSStatus
  -26276; a CA file doesn't help), and `sandbox.excludedCommands` didn't take
  gh out of the sandbox while `allowUnsandboxedCommands` is false. The global
  pre-push hook's git-lfs fails the same way, so the driver brief says to push
  with hooks bypassed and to stop on a change that adds LFS objects, and to
  pass the token to curl on stdin, never in argv.
- **Open residual (BRO-2755):** with the keychain's deny gone a driver can
  likely read any login-keychain item that trusts `/usr/bin/security`, not
  just gh's; the drill probed only gh's. It is measured before any live
  driver; spawns stay dry until then.
- The phase-2 drills left blocked on the token (the driver credential half,
  update-branch) passed in that drill.
- #261's deferred review findings (BRO-2714):
  - the read-back window's 14 days run from a batch's latest raise, not from
    the batch;
  - the bash alert fallback counts any answer from Maestro (made, refused, no
    clear answer) as raised, so a run that couldn't start ("Could not start
    the run") no longer raises one alert per hour. It runs in its own
    process group under a TERM-then-KILL watchdog (120 s, then 30 s), its
    output to a file rather than a pipe a child could hold. Anything that
    never reached Maestro (not listening, a CLI that didn't run, the
    watchdog) is tried again at the next tick;
  - `seen` is cleared when an item goes gone;
  - Maestro's refusals are told apart by the words their message starts with,
    on exit 1 only, not by a match anywhere in it (a failed start that quotes
    "No work item" is not gone); Maestro has no refusal code yet: BRO-2753;
  - a race with Maestro's loop no longer fails the tick: "already being
    dispatched" is a wait, and any other refused dispatch is checked against
    the item, which is recorded where it went when it left the queue;
  - raising is `new`, then `start()`'s dispatch, so an item whose run couldn't
    start is recorded queued and dispatched at a later tick, never raised
    twice;
  - recover counts a queue-operation only when it is an `enqueue`, and a
    malformed transcript entry as nothing rather than stopping recovery;
  - a duplicate fleet name's ask resolves only from a listing that was read;
  - a PR file list shorter than its `changed_files` (GitHub's 3000-file cap)
    refuses the spawn;
  - a coordinator whose stream ends before its init event fails its posture,
    with its own exit code beside it, and is stopped if it still runs;
  - an item past its 14-day read-back window says so each tick while an ask
    in its batch is open, rather than going quiet;
  - the janitor: an ignored directory it can't walk makes the backup check
    `not run`, a profile or gh dir it can't delete fails the run, and the
    owner-mismatch message is set only on a mismatch;
  - binding an adopted item to more than its title marker is BRO-2754.

## [0.3.0] - 2026-10-01

The owner channel moves to Paseo (owner decision, 2026-10-01: "If it goes to
the computer and I'm not there it won't work"). It replaces the macOS dialog
that broomva/workspace#842 §5.7 chose. Ticket BRO-2674.

- **`fleet act ask --show` raises each batch with an open ask as Maestro work
  at Needs you** (`fleetlib/paseo_ask.py`). It runs inside the tick's lock.
  `maestro new --dispatch` runs one turn in the fleet's own scratch repo; the
  asks are fenced as data in the brief, and the look is the fleet's own
  summary. Measured end to end: the item reached `review` and its agent's
  Paseo record read `requiresAttention: true`.
  - A batch is raised once an ask in it has lasted `ask_raise_after_min` (50),
    so an ask a later tick found no longer true isn't raised.
  - Raising is idempotent: an open item Maestro made before failing is found
    by its title's scope and batch marker, and one queued at the cap is
    dispatched later (a refusal there is logged, not a failed tick).
  - Each tick reads back only decisions that took effect (Maestro's
    `Took effect` receipt), never an undone or dropped one, nor the item's
    display `verdict`, from items raised in the last 14 days until one is
    final, keeping every note: approve acknowledges, send back with a note
    answers, cancel dismisses. Chat replies are not read.
- Where a Maestro item stands is one rule (`ledger.maestro_phase`: queued,
  owner, final, gone) that the ledger's `seen`, raising, reading back, alerts
  and dispatching all read. Only "At capacity" is a wait; an item Maestro no
  longer has frees its batch to be raised again.
- tick.sh's alerts go the same way, at most once per 6 h per kind of failure,
  stamped only once past Maestro's queue; `fleet alert` adopts an open item of
  the kind, with a bash fallback when Python or the config broke. The dialog, the banner path and p9
  notify are gone.
- The coordinator's tool list is an allowlist: `--tools Bash Read
  SendMessage`. Measured on 2.1.280, the init event lists exactly those.
  Any other tool (Paseo's pinned read tools aside), or no list, stops it. A late init event can't undo the
  deadline's stop.
- Carried from #258's review:
  - mail: the overlap template waits for the core's published claims; the
    hold label is refused however it's spelled;
  - spawn: a file list that isn't a list refuses it, and the owner-merge
    check reads a rename's old path;
  - a live resume waits for the listing;
  - the janitor:
    - PATH must be the owner's worktree itself, not a directory above it;
    - `scratch()` fails closed;
    - secrets in ignored directories are found, dependency dirs skipped;
    - a worktree `claude rm` keeps is an abort;
    - a removed driver's profile and gh dir go with it;
    - two backups in one instant both land;
  - the send gate refuses on a corrupt ledger, and the `fleet` shim makes
    any failure of `send-gate pre` exit 2;
  - recover counts only the two delivery shapes, not a quote;
  - a fleet child drops every session and Paseo variable (a parent's
    messaging token included) but keeps auth and provider settings;
  - a removed driver's profile is found through the ledger's spawn, never a
    listing name;
  - a partial Paseo classification fails config-check;
  - a duplicate fleet name is asked while it lasts;
  - the driver brief treats PR text as data.

## [0.2.0] - 2026-10-01

Phase 2 (spec §9 row 2): the coordinator and its verbs under dry run. Ticket BRO-2674.

- **fleet act mail|spawn|label|resume** (`fleetlib/act.py`): refused in report
  mode, on a corrupt ledger (mail, spawn) and on an unanswered ask about the
  target; each re-observes and re-checks eligibility in code (§5.5's driver
  rules, the caps, the spawn pause; mail only to fleet spawns and adopted
  sessions, resolved by session id or the Paseo agent's current session, the
  6 h rule; resume only a background session with no process, no flags);
  intent before, outcome after; under dry run spawn, label and resume close at
  once with the argv or call they would have made.
- **The send gate** (`fleet send-gate pre|post`): the coordinator's SendMessage
  hooks, every §5.7 check named in its refusal; dry run closes the intent and
  still blocks.
- **fleet recover**, run first in every tick: §5.7's recovery rules per verb.
- **The coordinator** (`fleet coordinator`, act mode only): settings with the
  hooks, `--disallowedTools Agent Edit Write` plus the pinned Paseo writes,
  `--` before the prompt, the child environment, and the init event's tool
  list checked as it starts (a disallowed or unclassified Paseo tool ends it).
  The pinned Paseo 0.9.2 classification ships as the default, with a test that
  fails on a tool it doesn't classify.
- **The driver profile** (`fleet driver-profile`): probe 6's shape, 0600, the
  token from `gh_token_file` and never printed.
- **The janitor** (`fleet janitor-check`, `fleet janitor-run`): six checks,
  failing closed when one can't run; the backup; removal of scratch worktrees
  only until the owner accepts the drill.
- Phase-1 carry-overs from #254's review: the compare asks keyed on the
  owner's action owed; the failed-run counter tested; report.json's compare
  error guarded; a non-GitHub origin no longer blocks a departed repo's
  resolution; `fleet ack` says how many asks it answered, tested.
- After Cross-Review (P20) round 1:
  - the send gate fails closed on its own errors, inside the hook's time;
  - mail templates take only fixed shapes (no free text), and hours come from
    the config;
  - the hold label is the owner's; a live label needs the fleet token;
  - spawn refuses when the listing, job files, transcripts or a board weren't
    read, reads names raw, refuses while a spawn of the key is unconfirmed,
    records a spawn whose session the listing lags by its job id, and reads
    every PR file (paginated);
  - the coordinator loads no MCP server, has NotebookEdit disallowed and a
    budget, is stopped on an event before its init event or none within 60 s,
    and stays in the watchdog's process group;
  - the janitor refuses an owner that doesn't own the path, needs the board
    for a scope repo's owner, counts its ancestors as its own, finds secrets
    in ignored directories, and prunes;
  - tick.sh exports the fleet token before recover and runs no live
    coordinator without it;
  - a duplicate spawn is an ask.
- Drills on scratch sessions (evidence under
  `~/.config/broomva/fleet/phase2-drills-20261001/`):
  - PASS: kill switch, tool-list posture, SendMessage refusals 5/5, the
    injected-text floor, the janitor;
  - driver profile: the sandbox half passed, fresh and resumed; the credential
    half is blocked on the token file;
  - not run: the recovery drill.

## [0.1.0] - 2026-09-30

Phase 1 of fleet-reconcile (broomva/workspace
`docs/specs/2026-09-29-fleet-reconcile-design.html`, §5.3 observe, §5.4, §9
row 1; formats from the §5.7 build-readiness amendment, broomva/workspace#842).
Observe and classify, report only; no session is acted on. Ticket BRO-2674.

- **Parsers**, pinned to Claude Code 2.1.280 and tested against anonymized
  captures: the session listing, background job files, Paseo agent records and
  schedules (read-only; the bearer's field is never extracted), `gh pr list`, the
  effective branch rules, `launchctl print`. Drift is reported and asked about.
- **The class table** (§5.4), first match wins, with 9a and unknown, the spec's
  five ordering tests, 41 overlapping rule pairs and a grid proving the other
  14 exclusive. The overlap pass on fixtures. Mutation-proved: every rule
  deleted and every overlapping pair swapped fails a test.
- **Fail-closed observation**: a listing at 200 rows, an unresolvable slug, a
  gh error or a PR list at its cap fails the surface or the repo; none reads as
  zero. The count check and the ruleset check (a repo without a pull_request
  rule or with unpinned checks is flagged; skills becomes eligible once its
  rule lands).
- **The report**: markdown and JSON per tick in the scope's state dir; an ask
  batch when a tick has a new key, shown in a dialog (Seen/Later) and counted
  to p9; answered with `fleet asks` and `fleet ack`.
- **tick.sh, install.sh and the launchd template**: the kill switch, dry falls
  toward dry, a mkdir lock, the fleet token through the environment, a
  TERM-then-KILL watchdog; hourly; installed and removed by the owner.
- **The scheduled-work inventory**, report-only: Paseo schedules, com.broomva.*
  LaunchAgents, the last bookkeeping and Dream runs. The seam for the spec's
  later Dream and heartbeat section.
- **The core comparison** lands in ctx-core 0.2.0 as `ctx doctor --compare`;
  the tick runs it daily.
- After Cross-Review (P20) round 1: a job's `updatedAt` is read as the ISO
  string 2.1.280 writes; the listing cap is cross-checked against the job
  files; an unread board or job file turns 9/9a/10 into unknown; an unknown
  branch is unknown, not closed; asks are per-key state with ack-through; a
  failed tick notifies and exits 1; the token reaches gh only; the watchdog
  kills the step's process group; the job runs a pinned copy of the code;
  bootstrap waits for bootout and retries; tick numbers come from the ledger
  too; snapshots are pruned after 7 days.
- After round 2, and aligned with the spec as merged (workspace#842,
  007f05a98): activity is the latest assistant entry or tool result (not the
  mtime, which Claude Code moves with untimestamped records); the ask channel
  is a dialog (`fleet act ask --show`, Seen/Later, a `seen` record, shown again
  at the next tick then at most every 6 h) run with the lock released; ledger
  records carry a unique id, `by` and `of`, owner records a null tick, and
  tick.sh writes through `fleet ledger-append`; asks are per occurrence (a
  tick records a resolution when one stops being true), keys are stable, and
  an answer holds while the condition does; `fleet ack` answers one batch (or
  `--all`) and refuses inside a session; adoption follows a Paseo agent across
  a relaunch; class 8 joins on a hash of the raw branch; the plist sets
  ProcessType Standard.
- After round 3 (passed 7/10) and a review of the fixes: a tick resolves an
  ask only when it read the surfaces that raise that key (per key kind; not
  for a session that reads as unknown; a repo that left the scope resolves);
  a prompt's key stays the session and what it waits for (activity moves
  while subagents write); the activity tail is ctx-core's reader, widening
  (128 KiB, 2 MiB, 16 MiB) and keeping a line the window starts on; the ack
  wording says one batch (or `--all`), and the header counts after this
  tick's resolutions; `fleet asks` and the dialog list every open ask; the
  dialog defaults to Later and leads with the newest due batch's first open
  ask, and one that can't be shown records nothing, sends no p9 and fails the
  tick; owner ids stay distinct within a millisecond; the core comparison
  asks when it can't run (no registration, the prototype's file, a torn
  first line; one key) and after three failed runs in a row, and a failed
  run doesn't use up the day; open asks whose surface wasn't read are listed
  as not re-checked; `fleet ack` says how many open asks it answered; a tail
  keeps a line its window starts on; the trap is cleared
  before the lock is released; scheduled work raises no asks; a token file
  open to others is not used.
