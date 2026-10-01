---
name: fleet-reconcile
tier: D
primitive: null
category: orchestration
version: 0.1.0
description: |
  The hourly fleet coordinator, phase 1: observe and classify, report only.
  Each tick reads every Claude Code session (claude agents --json --all and the
  background job files), Paseo's agent records and schedules from disk, the
  ctx-core board, transcript times, and GitHub (open PRs and the effective
  branch rules of every repo in the scope). It classifies each session with the
  spec's class table, runs the count check, inventories scheduled work
  (Paseo schedules, com.broomva.* LaunchAgents, bookkeeping, Dream), and writes
  a markdown and JSON report plus one batch of owner asks, shown in a dialog.
  It acts on no session: no mail, spawn, label or resume in phase 1. Runs
  hourly from launchd once the owner installs it. Coordination only; not a
  security boundary. USE WHEN installing or checking the fleet tick, reading a
  tick report, answering the fleet's asks (fleet asks, fleet ack), asking
  "which sessions are live / stalled / waiting on me", "which repos can get a
  driver", "what runs on a schedule and is it keeping time", or producing the
  phase-1 labelling sheet. NOT FOR messaging, spawning or resuming sessions
  (phase 2 dry run, phase 3 live), merging PRs, or waiting on CI (use p9).
when_to_use: |
  Triggers on "fleet tick", "fleet reconcile", "fleet-reconcile", "fleet asks",
  "fleet ack", "class table", "which sessions are stalled", "count check",
  "labelling sheet", "install the tick", "is the fleet running", "scheduled
  work inventory".
---

# fleet-reconcile: the hourly coordinator (phase 1: observe and classify)

The 09-26 → 09-29 run's coordinator reported 6 live sessions when there were
30, lost state to compaction, and kept its ledgers by hand. This skill is the
first phase of its replacement, as the design of record specifies:
`docs/specs/2026-09-29-fleet-reconcile-design.html` in broomva/workspace (§5.3
observe, §5.4 classes, §9 row 1), with the formats of its 2026-09-30
build-readiness amendment (§5.7, broomva/workspace#842, merged as 007f05a98).
Ticket BRO-2674.

Phase 1 is report-only and runs deterministic code; no model reads or decides
anything in a tick. It observes, classifies and reports, and asks the owner in
one batch per tick. The `would do` column of a report says what phase 3 would
do; nothing is done.

**Not a boundary.** Nothing here constrains any session. The tick's reads are
the owner's own reads (claude agents, gh with the fleet token or the keyring,
files under $HOME). What bounds a merge is the repo's ruleset on GitHub (spec
§5.1); the report's ruleset check says which repos have one.

## Install (the owner runs this)

```bash
cd ~/broomva/skills && git pull            # the checkout the job will run from
bash skills/orchestration/fleet-reconcile/scripts/install.sh --scope broomva --dry-run   # see it first
bash skills/orchestration/fleet-reconcile/scripts/install.sh --scope broomva
launchctl kickstart gui/$(id -u)/com.broomva.fleet-reconcile.broomva   # one tick now
# sri, report-only like everything in phase 1:
bash skills/orchestration/fleet-reconcile/scripts/install.sh --scope sri
# remove:
bash skills/orchestration/fleet-reconcile/scripts/install.sh --scope broomva --uninstall
```

The job runs a **pinned copy**, not the checkout: `install.sh` copies
fleet-reconcile's and ctx-core's scripts and templates to
`~/.local/share/fleet-reconcile/releases/<commit>/` and points the plist there,
so a branch switch or an edit in `~/broomva/skills` doesn't change what launchd
runs; installing again does. A checkout with uncommitted changes in either
skill is refused unless `--force`. It seeds `~/.config/ctx/fleet.json` from
`templates/fleet.json.example` only when absent (mode 0600, report mode,
`dry_run: 1`) and runs `config-check` (in `--dry-run` too), renders
`templates/launchd.plist.template` into
`~/Library/LaunchAgents/com.broomva.fleet-reconcile.<scope>.plist`
(StartInterval 3600, ProcessType Standard, logs in `~/Library/Logs/`), then
`launchctl bootout`, waits for the job to go, and `bootstrap`s (retried three
times), so a rerun reloads. `--uninstall` unloads and moves the plist to the
Trash; the config, the releases and the state dir stay.

## A tick

`scripts/tick.sh`, per scope (FLEET_SCOPE):

1. The recursion guard (`FLEET_CHILD`), then the kill switch: the tick fires
   only when `fleet config-get <scope> dispatch_enabled` prints exactly `1`.
   Any other value is the owner's off (exit 0). A config that can't be read
   is off too, and is a failure (below). Then `config-check`.
2. `dry_run` falls toward dry: live only when the config says exactly `0`; any
   `DRY_RUN` value but `0` in the environment forces dry. Phase 1 acts on
   nothing either way; the ledger records the mode.
3. A mkdir lock per scope. A stale lock (both pids gone, 2 minutes old) is
   reclaimed under a second mkdir mutex that re-reads its holder, so two
   ticks can't both reclaim it.
4. The tick number from `fleet next-tick`: one past both the counter file and
   the ledger's last `tick_fire`, so a lost counter can't reuse a number.
5. The fleet token: `gh_token_file` (the example config sets
   `~/.config/broomva/fleet/gh-token`) is read from its file, never argv, never
   printed, and exported for the observe step only; observe passes it to `gh`
   and to no other child. An absent, unreadable or empty file means the
   keyring, which the report says. A mode other than 0600 is logged.
6. `fleet observe`, `fleet report` and `fleet core-compare` (the core's
   comparison, once a day from `compare_hour`), each in its own
   process group under a TERM-then-KILL watchdog bounded by
   `tick_timeout_min` (15), so a timeout also ends its `claude` and `gh`
   children.
7. `tick_fire` and `runner_exit` records in the ledger (through
   `fleet ledger-append`), the lock released, then `fleet act ask --show` (a
   dialog that can wait 10 minutes), and one line on stdout for launchd's log.

**A failed tick is loud.** An unreadable config, a failed `config-check`, or
observe or report failing, or a lock held for over 2 h, shows a dialog directly
from bash (so it works when Python is what broke), at most once per 6 h per
kind, and exits 1, so launchd's last exit shows it.

By hand: `FLEET_SCOPE=broomva bash scripts/tick.sh`.

## What a tick reads, and what it does with a failure

| Surface | Read from | On failure |
|---|---|---|
| Sessions | `claude agents --json --all` | reported; nothing is classified. At `listing_cap` (200) rows or more the listing counts as complete only when every job file on disk appears in it (the listing has no limit parameter but lists every background job ever run); otherwise it **fails closed** the same way |
| Background detail | `~/.claude/jobs/<id>/state.json` | the directory unread: every background session that would be 9, 9a or 10 reads unknown. One file that doesn't parse: only its session does |
| Activity | the latest assistant entry or tool result in each session's transcript and its newest subagent transcripts (spec §5.3); not the mtime, which Claude Code moves with untimestamped records long after a turn (36 of 77 captured transcripts by over 10 min) | reported |
| Paseo | `~/.paseo/agents/*/*.json`, `~/.paseo/schedules/*.json` (read-only) | reported; the count check says it could not run |
| The board | ctx-core's `events.jsonl`, rebuilt in memory (no cache write) | reported and asked per scope; that scope's sessions that would be 9, 9a or 10 read unknown, since 2, 4, 7 and 8 couldn't be checked |
| GitHub | per repo: slug from `origin`, `repos/<r>` default branch, `rules/branches/<b>`, `gh pr list` | **that repo** is reported as not observed. A slug that doesn't resolve, a gh error or a PR list at `pr_list_cap` never reads as zero PRs |

The parsers are pinned to Claude Code 2.1.280 and tested against copies
captured on it (`tests/fixtures/cc-2.1.280/`). Another running version, a new
listing field or an unfamiliar enum value is reported as drift and asked
about. Never extracted (each file is loaded whole and these fields are
dropped before anything is kept): a Paseo record's `persistence.metadata`
(where the MCP bearer lives), a job file's `providerEnv`, `output` and inline
`--settings`, a schedule's prompt and run output, the bookkeeping log's
`source_files`.
Other sessions' words (names, job details, PR titles) are flattened, clipped
and passed through ctx-core's guard; a credential-shaped string or a `crm/`
path is withheld.

## The classes (spec §5.4, first match wins)

| # | class | evidence |
|---|---|---|
| 1 | out of scope | the core's scope rule places the cwd elsewhere, the cwd is in no repo, or it can't be placed (cwd gone, no board row) |
| 2 | dead: limit | a board `session.died` with `rate_limit`, or a background job blocked on Claude Code's limit text; the reset is read from the job or the transcript tail, else assumed 5 h after the death |
| 3 | waiting at a prompt | listing `status: waiting` with a `waitingFor`, unless it is a background question to its user |
| 4 | error | listing `state: failed`, or a board death with another error (transient: 5xx or network only) |
| 5 | running | busy, activity within 2 h |
| 6 | hung | busy, a transcript found, no activity for over 2 h |
| 7 | blocked on the owner | a current `ARC-STATUS: BLOCKED`, or a background job blocked on a question (its needs, a suggested reply, or a detail that asks) |
| 8 | closed | a current `MERGED`, `CLOSED` or `DONE`, a known branch, and no open PR on it; an unknown branch is unknown |
| 9 / 9a | stalled / idle, recent | ours (a ledger spawn, or adopted by session id or through its Paseo agent), idle, no activity for ≥ 1 h / activity within 1 h; 9's action is a mail with a live process, else a resume |
| 10 | unmanaged | in scope, not ours |
| — | unknown | nothing matched (a missing transcript), or a terminal status on a repo whose PRs weren't read |

Choices the spec leaves open, pending the spec and listed in
`scripts/fleetlib/classify.py`: class 2 also reads the job file and the
transcript tail for the reset (a dated reset like "Oct 3, 10am" included; an
unreadable one is assumed 5 h after the death); a board death or ARC-STATUS
counts only while nothing happened after it (the core measured sessions that
died at the limit and kept working); "idle" includes a background session with
no process and no status whose state is done or stopped; the spawn pause counts
a limit death in any scope, since every scope here runs on one account.

The overlap pass runs on fixtures only until the core's phase 2 publishes
claims. The count check reports every Paseo record that isn't archived and has
no live process, and every in-scope session with neither a Paseo record nor a
fleet name.

## The owner channel (spec §5.7, the ask channel)

An ask is per occurrence of a condition. Candidates: a session waiting at a
prompt or blocked on the owner, a repo without a pull_request rule or with
unpinned checks, a repo not observed, a surface not read, drift, a scheduled
job exiting non-zero or overdue, records with no process. A key is asked once,
stays open until the owner answers it or a tick finds it no longer true (a
resolution record), and an answer holds for as long as the condition does; a
condition that ends and comes back is a new ask. Keys carry no counts or error
text, so they don't change tick to tick. A tick writes a batch
(`<state_dir>/asks/<tick>.md` and an ask intent in the ledger) only when it has
a new key.

With the tick's lock released, `fleet act ask --show` shows a dialog (banners
are stored but not shown on this Mac, spec §5.7): the scope, the number of
open asks and the newest one's line, with Seen and Later, giving up after 10
minutes. The outcome is a `seen` record. A batch not clicked Seen is shown
again at the next tick and then at most every `ask_renotify_h` (6) hours. It
also calls `p9 notify` with the count only, since p9 may send off the machine.
A Seen click is a statement, not a proof; only an answer closes an ask:

```bash
F=~/.local/share/fleet-reconcile/releases/<commit>/orchestration/fleet-reconcile/scripts/fleet
$F asks --scope broomva            # the open asks, one line each, oldest first
$F ack 12 --scope broomva          # answer tick 12's batch
$F ack 12 --ask a3 --scope broomva # one ask of tick 12
$F ack --all --scope broomva       # every batch with an open ask
```

`fleet ack` refuses when `FLEET_CHILD` or `CLAUDECODE` is set (a floor: the
owner answers from a terminal). Every report leads with the number of
unanswered and unseen batches and of open asks. `ask` runs in every mode and
under dry run (§5.7): it reaches only the owner.

## Files

```
~/.config/ctx/fleet.json                         the config (spec §5.7), owner-edited, 0600
~/.local/state/fleet-reconcile/<scope>/
  ledger.jsonl, ledger.lock                      the write-ahead ledger (flock, fsync)
  ticks/<NNNNN>/snapshot.json, report.json, report.md   (snapshots pruned after 7 days)
  asks/<NNNNN>.md                                one ask batch per tick
  labelling/<name>.md, .csv                      the owner's labelling sheet
  tick.log, tick-counter, .tick.lock, .alert-<kind>
~/.local/share/fleet-reconcile/releases/<commit>/  the pinned copy the job runs
~/Library/Logs/com.broomva.fleet-reconcile.<scope>.log
```

Config keys beyond §5.7's, pending the spec: `listing_cap`, `pr_list_cap`,
`gh_token_file`, `actions_app_id` (15368, GitHub Actions), `launchd_prefix`,
`launchd_logs` (a label's real log, when its stdout is silent),
`bookkeeping_run_log`, `dream_run_log`, `ask_renotify_h`, `tick_timeout_min`, `compare_hour`.
§5.7's `b_step_timeout_min` and an adoption's `paseo_agent_id` are accepted.

## Scheduled work (report-only; the seam for the Dream and heartbeat section)

`scripts/fleetlib/scheduled.py` lists, per scope: Paseo schedules (placed by
cwd), LaunchAgents with the scope's `launchd_prefix` (cadence, loaded, runs,
last exit, last run read from a log's mtime, staleness), the last bookkeeping
run, and the last Dream (P13) run when `dream_run_log` names one (there is no
Dream run log on this machine yet). Every item has the same keys, so the later
spec section adds a source without changing the report. It starts, stops and
edits nothing.

## The phase-1 exit (spec §9)

The tests pass; then three real ticks, and the owner labels a stratified
sample (at least 3 sessions per class that occurs):

```bash
$F label-sheet --scope broomva --ticks 1,2,3   # writes labelling/<name>.md and .csv
```

≥90% agreement overall and no class below 2 of 3. The owner also acks those
ticks' ask batches from the dialog, which shows the channel reached
them.

## Commands

```
fleet config-get <scope> <key> | config-check [<scope>]
fleet observe --tick N [--fixtures DIR]
fleet report --tick N [--dry-run 0|1]
fleet act ask --show --tick N             (mail, spawn, label, resume: refused in phase 1, exit 3)
fleet asks [--all] | ack <tick> [--ask ID ...] | ack --all
fleet next-tick | ledger-append fire|exit --tick N
fleet core-compare [--force]
fleet label-sheet --ticks A,B,C [--per-class 3] [--seed 0]
```

All take `--scope` or `FLEET_SCOPE`. `scripts/fleet` execs `python3 -I`, so
the caller's cwd and user site stay off `sys.path`; it imports ctx-core from
`../ctx-core/scripts` in the same checkout.

## Tests

```bash
cd skills/orchestration/fleet-reconcile
python3 -m pytest tests/ -q
python3 tests/mutation_check.py      # every rule deleted, every overlapping pair swapped, 27 protections removed
python3 tests/capture_fixtures.py    # recapture on a new Claude Code version (anonymized; public repo)
```

| File | Pins |
|---|---|
| `test_parsers.py` | Every parser against the 2.1.280 capture; missing fields fail the surface; drift is reported; the bearer, env and prompts are never extracted; the slug rule; the ruleset check (skills flagged until its pull_request rule lands, unpinned checks flagged) |
| `test_classify.py` | A positive case per class; the spec's five ordering tests; 41 rule pairs that can both match, the earlier winning; a grid proving the other 14 pairs can't; the arc and death currency rules; the spawn pause; the count check; the overlap pass |
| `test_observe.py` | The pipeline over the capture in a scratch HOME; a 200-row listing fails closed unless the job files show it complete; one unparsed job file degrades only its session; an unresolvable slug, a gh error and a PR list at the cap fail only their repo; the bearer never reaches a snapshot or report |
| `test_report.py` | Every section; withheld crm/ paths and tokens; per-occurrence asks (once, then still open; an answer holds while true; a recurrence is new; a different question is new), answers per batch, stable count keys, failed-surface asks, the ruleset wording, the dialog's re-show rule; the labelling sheet (distinct sessions only) |
| `test_ledger.py` | Validation, corrupt-line counting, 4 processes × 50 appends lose nothing, the ask and spawn folds |
| `test_tick.py` | tick.sh end to end with stub claude/gh/osascript/p9: kill switch, a bad config alerting once and exiting 1, a failed step alerting, dry falls toward dry, live and stale locks and the reclaim mutex, the recursion guard, the watchdog killing the step's children, the token reaching gh and not claude, an empty token file, tick numbers past a lost counter, the dialog shown again at the next tick and stopped by Seen, ack refused inside a session, refused verbs, the labelling sheet |
| `test_install.py` | The pinned copy (runnable without the checkout), plist rendering, config seeded once at 0600, bootout-wait-bootstrap on every run, a retried bootstrap, uninstall to the Trash, dry run, a broken config, uncommitted changes refused without --force |

## Phase 2 and 3

Phase 2 (dry run, spec §9 row 2) adds `fleet act mail|spawn|label|resume`
writing intent before and outcome after, `fleet recover`, the coordinator's
settings (disallowedTools from the pinned Paseo classification, the
SendMessage hooks), the driver profile generator and `fleet janitor-check`,
all under `DRY_RUN=1`, with the drills. Phase 3 needs the three preconditions
in spec §5.2.
