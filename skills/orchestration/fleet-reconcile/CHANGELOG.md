# Changelog: fleet-reconcile

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
