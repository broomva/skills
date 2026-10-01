# Changelog: fleet-reconcile

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
- After round 3 (passed 7/10; fixed before the real ticks): a tick resolves an
  ask only from a surface it read; a prompt's key carries the activity time;
  the activity tail widens (128 KiB, 2 MiB, 16 MiB) past a large last line;
  the ack wording says one batch (or `--all`); the dialog defaults to Later,
  and one that can't be shown records nothing and fails the tick; owner ids
  stay distinct within a millisecond; a failed compare doesn't use up the day
  and the prototype's compare line is refused with the move to make; the
  tick-number alert releases the lock first; scheduled work raises no asks;
  a token file open to others is not used.
