---
name: fleet
tier: D
primitive: null
category: orchestration
version: 0.6.0
description: |
  The Broomva fleet: every Claude Code and Paseo session, PR and loop the
  coordinators drive, and the workflows that keep it reconciled. reconcile is
  the hourly launchd tick (observe, classify, report, owner asks; act under
  dry run). census, close-out and rollover are the coordinator's procedures
  from bstack's orchestrator-tick base. USE WHEN running or installing the
  tick, reading a tick report, answering fleet asks (fleet asks, fleet ack),
  asking which sessions are live, stalled or waiting on the owner, closing
  out or archiving a finished session, or rolling a heavy context over to a
  successor. NOT FOR merging PRs or waiting on CI (use p9).
when_to_use: |
  Triggers on "fleet", "fleet tick", "fleet reconcile", "fleet-reconcile",
  "fleet asks", "fleet ack", "class table", "which sessions are stalled",
  "install the tick", "is the fleet running", "census", "close out",
  "archive the session", "rollover", "successor", "driver profile",
  "janitor-check", "send gate".
---

# fleet

The fleet is every session, PR and loop that Broomva's standing coordinators
drive: the broomva coordinator (`coordinator-tick`), the SRI coordinator
(`sri-coordinator-tick`, its own scope), and the hourly reconcile tick that
reads them all. This skill is the entry point. Each thing done to the fleet
is a **workflow** with its own trigger, steps and a check you can run.

Named `fleet-reconcile` until 0.6.0 (BRO-3122). `fleet-reconcile` stays a
deprecated alias for one release: `skills/orchestration/fleet-reconcile/`
forwards its scripts here. The runtime names keep the old name (launchd
`com.broomva.fleet-reconcile.<scope>`, `~/.local/state/fleet-reconcile/`,
`~/.local/share/fleet-reconcile/releases/`, the loop rows), because Maestro
and the loop ledger read them.

## Workflows

| Workflow | Trigger | Mechanism | File |
|---|---|---|---|
| reconcile | launchd, hourly per scope; or `fleet reconcile` by hand | code: `scripts/tick.sh` and the `fleet` CLI | [workflows/reconcile.md](workflows/reconcile.md) |
| census | every coordinator fire, before any launch, resume or archive | procedure: bstack base §4; the overlay's snapshot | [workflows/census.md](workflows/census.md) |
| close-out | a driven session finished; an owner session idle over 12 h | procedure: bstack base §6 | [workflows/close-out.md](workflows/close-out.md) |
| rollover | a driven session over 600k context; the coordinator over 400k | procedure: bstack base §11; the overlay's Rollover | [workflows/rollover.md](workflows/rollover.md) |

Read the workflow file before acting. For census, close-out and rollover the
canonical text is bstack's `references/orchestrator-tick.md`, read from git;
the workflow file names its trigger and its check and links there rather
than copying it.

## The CLI

```bash
F=skills/orchestration/fleet/scripts/fleet   # or the pinned copy launchd runs
$F --help                     # every command; the workflows listed at the end
$F workflows                  # name, trigger, file
$F reconcile --scope broomva  # one reconcile tick now (tick.sh, DRY_RUN=1)
$F rollover                   # print a procedure workflow (also census, close-out)
$F asks --scope broomva       # the reconcile tick's own verbs, unchanged
```

The module names stay `fleet_reconcile.py` and `fleetlib/`: they are the
reconcile workflow's implementation, and tick.sh, install.sh, the tests and
every pinned release name them.

## Tests

```bash
cd skills/orchestration/fleet
python3 -m pytest tests/ -q          # test_layout.py: each routed workflow exists; the alias resolves
python3 tests/mutation_check.py
```
