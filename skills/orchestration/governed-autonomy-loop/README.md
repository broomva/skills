# governed-autonomy-loop

Turn any work-queue + any enforcement pipeline into a self-driving, self-healing,
human-minimal autonomy loop with a control-systems safety envelope.

A **prose-defined governor** closes a feedback loop over a queue, drives isolated
worktree arcs to Done, is **metacognitive** (defers when the runtime can't support
the act, escalates only when genuinely blocked, self-heals when it clears), and
**never performs the irreversible act itself** — every merge/deploy/publish is
delegated to an isolated arc gated by adversarial review + a policy gate + a
server-side aggregate check.

It generalizes the broomva **ticket-dispatch governor** (BRO-1740 + BRO-1833),
which ran in production, hit two real runtime failures, degraded without paging a
human, and self-healed to close its arc.

## Install

```sh
npx skills add broomva/skills --skill governed-autonomy-loop
```

## Quickstart

The controller is a markdown prompt interpreted fresh each tick; a thin **tested**
shell (`scripts/tick.sh`) only schedules, locks, logs, and spawns. To stand up a
loop:

```sh
# 1. validate the deterministic core (offline, zero side effects)
python3 -m pytest tests/ -q          # 65 tests
bash tests/smoke.sh                  # E2E DRY tick, zero side effects

# 2. a spawnless dry tick end-to-end
DRY_RUN=1 FORCE=1 GAL_CLAUDE_BIN=echo bash scripts/tick.sh
```

Then fill the four adapters (`references/adapters.md`), ship the server-side net
(`references/server-side-net.md`), wire a runtime (`templates/`), review one DRY
digest, and arm with `DRY_RUN=0`. Full procedure in `SKILL.md`.

## What ships

- `scripts/` — the tested deterministic core: `tick.sh` (scheduler),
  `loop_state.py` (in-flight fold + reseed gate + busy-guard + arc-status
  contract), `validate_config.py` (fail-closed config), `denylist_check.py`
  (tracker write-surface coverage), `mine_loop_log.py` (distill a running loop's
  history into taxonomy + fixtures + a drift check — keeps the skill learning).
- `templates/` — the latent controller (`runner-prompt.template.md` with adapter
  slots), `config.env.template`, the tracker denylist adapter, `merge-gate.yml`
  (server-side net), launchd + systemd runtime adapters.
- `references/` — the invariant spine, the four adapter contracts, the server-side
  net checklist, the scenario evals.
- `tests/` — 65 unit/integration tests + an E2E smoke.

## The thesis

Verbal incantation ("be autonomous") is open-loop control; this is the closed-loop
version — a controller whose verification signals are causally independent of the
agent (`h ⟂ U`). See `references/invariant-spine.md`.
