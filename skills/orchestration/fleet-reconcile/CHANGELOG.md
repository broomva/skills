# Changelog: fleet-reconcile

## [0.1.0] - 2026-09-30

Phase 1 of fleet-reconcile (broomva/workspace
`docs/specs/2026-09-29-fleet-reconcile-design.html`, §5.3 observe, §5.4, §9
row 1; formats from the §5.7 build-readiness amendment, broomva/workspace#842).
Observe and classify, report only; no session is acted on. Ticket BRO-2674.

- **Parsers**, pinned to Claude Code 2.1.280 and tested against anonymized
  captures: the session listing, background job files, Paseo agent records and
  schedules (read-only; the bearer's field is never parsed), `gh pr list`, the
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
- **The report**: markdown and JSON per tick in the scope's state dir; one ask
  batch per tick, notified by osascript and p9, seen only once acked
  (`fleet asks`, `fleet ack`).
- **tick.sh, install.sh and the launchd template**: the kill switch, dry falls
  toward dry, a mkdir lock, the fleet token through the environment, a
  TERM-then-KILL watchdog; hourly; installed and removed by the owner.
- **The scheduled-work inventory**, report-only: Paseo schedules, com.broomva.*
  LaunchAgents, the last bookkeeping and Dream runs. The seam for the spec's
  later Dream and heartbeat section.
- **The core comparison** lands in ctx-core 0.2.0 as `ctx doctor --compare`;
  the tick runs it daily.
