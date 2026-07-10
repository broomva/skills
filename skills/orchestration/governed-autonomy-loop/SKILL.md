---
name: governed-autonomy-loop
category: orchestration
description: >-
  Turn any work-queue + any enforcement pipeline into a self-driving, self-healing,
  human-minimal autonomy loop with a control-systems safety envelope. A prose-defined
  governor closes a feedback loop over the queue, drives isolated worktree arcs to
  Done, is metacognitive (defers when the runtime can't support the act, escalates
  only when genuinely blocked, self-heals when the block clears), and NEVER performs
  the irreversible act itself — it delegates every merge/deploy/publish to an isolated
  arc gated by adversarial review + a policy gate + a server-side aggregate check. The
  controller is a markdown prompt interpreted fresh each tick; a thin tested shell
  (tick.sh) only schedules, locks, and logs. The skill SCAFFOLDS + GOVERNS a new loop
  instance: the invariant spine stays fixed, four adapters (tracker / irreversible-act
  + enforcement / runtime / partition) are per-instance, the deterministic core
  (scheduler, in-flight fold, reseed gate, config + denylist validation) is extracted
  into tested scripts, and the latent decisions stay prose with scenario evals.
  Generalizes the proven broomva ticket-dispatch governor (BRO-1740 + BRO-1833). USE
  WHEN setting up an autonomous ticket/PR/deploy loop, standing up a governor that
  drives a queue unattended, building a self-merging arc pipeline, adding a
  metacognitive control loop over background agents, or the user says "governed
  autonomy loop", "autonomy loop", "self-driving loop", "ticket-dispatch governor",
  "loopcast", "loop-caster", "set up an autonomous governor". NOT FOR a single
  in-session autonomous task (use /autonomous), a one-shot background watcher (use
  P9 wait), or a cross-session single-agent restart loop with no queue (use P12
  persist) — this is the external-trigger, across-session, queue-driven,
  irreversible-act-gated quadrant.
---

# governed-autonomy-loop

> Verbal incantation ("be autonomous", "merge when green") is **open-loop** control.
> A governed autonomy loop is the **closed-loop** version — a controller whose
> verification signals are causally independent of the agent (`h ⟂ U`), so
> "autonomous" becomes a machine-checkable behavior instead of a hope.

This skill packages a *demonstrated controller*, not a described one: the reference
loop ran in production, hit two real runtime failures, degraded gracefully without
paging a human, and self-healed to close its arc — all observable in
`loop-log.jsonl` (broomva BRO-1740 + BRO-1833, first fully-autonomous merge
2026-07-10). It generalizes that instance into a recipe.

## The latent-vs-deterministic split (the load-bearing idea)

| Deterministic → tested code (`scripts/`) | Latent → prose (`templates/runner-prompt.template.md`) |
|---|---|
| `tick.sh` — durable scheduler: fire-timing, flock, run-counter, quiet hours, mode decision, watchdog, child-guard | reconcile classification (merged? dead? stale?) |
| `loop_state.py` — in-flight fold, **reseed gate arithmetic**, busy-guard, arc-status contract | dispatch selection (which candidate, trust-bounded) |
| `validate_config.py` — fail-closed kill switch, DRY_RUN, num_or, partition guard | the govern/escalate judgment |
| `denylist_check.py` — tracker write-surface coverage | the adversarial (P20) review verdict |

The rule: *precision work with one right answer per input lives in tested code; the
model's intelligence builds the constraint that then constrains the model.* The
scripts are pinned by 65 unit/integration tests + an E2E smoke.

## The invariant spine vs the swappable adapters

Keep the spine verbatim (`references/invariant-spine.md`): the loop shape (outer
A–E + inner F), the eight safety invariants, the metacognitive gate, the
irreversible-act delegation, resumability + rot-reseed, comment-first attribution,
the trust boundary. Fill four adapters (`references/adapters.md`):

| Adapter | What you provide | Reference |
|---|---|---|
| **Tracker** | list/read/comment/transition/read-answer + the write-surface denylist | `linear-server` MCP + `templates/denylist.linear.json` |
| **Irreversible-act + enforcement** | the act (merge/deploy/publish) + the 3-layer gate | PR-merge + P20 + `.control/policy.yaml` + `merge-gate.yml` |
| **Runtime** | what pokes `tick.sh` on a cheap interval | launchd / systemd / cron / k8s CronJob |
| **Partition** | the disjoint label discriminator (N governors, one queue) | `agent-ok` vs `life-agent-ok` |

## Procedure — instantiate a new loop

1. **Scaffold the instance dir**: copy `scripts/` verbatim; copy
   `templates/runner-prompt.template.md` and fill every `{{SLOT}}` for your
   adapters; copy + edit `templates/config.env.template` (starts DRY_RUN=1).
2. **Author the tracker adapter**: point the runner-prompt at your queue's tool
   surface; write `templates/denylist.<queue>.json` (full write surface + both
   denylists) and run `python3 scripts/denylist_check.py <that file>` — it must PASS.
3. **Author the enforcement adapter + ship the server-side net**: follow
   `references/server-side-net.md` — copy `templates/merge-gate.yml`, prove it green
   on one PR, THEN require it in a branch ruleset with **no admin bypass**.
4. **Wire the runtime**: fill `templates/launchd.plist.template` or
   `templates/systemd/*.template`; set `GAL_*` env; enable it.
5. **Validate before arming** (all offline, zero side effects):
   `python3 -m pytest tests/` · `bash tests/smoke.sh` ·
   `DRY_RUN=1 FORCE=1 GAL_CLAUDE_BIN=echo bash scripts/tick.sh` → assert a
   well-formed digest + `runner_exit rc=0`.
6. **Arm deliberately**: review at least one DRY digest, then flip `DRY_RUN=0`. The
   first live fire is an operator decision, never an accident (DRY fails toward
   observation; the kill switch fails closed).
7. **Dogfood the generalization**: instantiate a SECOND loop (a different queue or
   partition) — proving the spine/adapter factoring holds is the real test that you
   skillified the *pattern*, not re-described the instance.

## Key parameters (config.env)

`DISPATCH_ENABLED` (kill switch, exactly 1) · `DRY_RUN` (live = exactly 0) ·
`WIP_CAP` · `LABEL` (the trust boundary — applying it authorizes code execution) ·
`FIRE_INTERVAL_HOURS` · `RESUME_ENABLED` · `RESEED_TURN_CAP` (context-rot bound) ·
`RESEED_MAX_GENERATIONS` (runaway guard). Full inline docs in the template.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "The governor can just merge when it's green." | Then it is a bot, not a controller. The governor NEVER performs the irreversible act (invariant 4) — an isolated arc does, only behind the independent enforcement pipeline. |
| "The prose controller is enough; skip the scripts." | The scheduler + reseed gate + fail-closed config are ARITHMETIC. Latent space doing them is the bug — it silently drops a safety block. They are tested code. |
| "I'll require the individual CI jobs." | Path-filtered CI skips on docs-only PRs and blocks them forever. Require the always-runs aggregate gate instead (`references/server-side-net.md`). |
| "Admin bypass is fine, I'm the admin." | The arc runs as an admin identity. Admin-bypass = no gate for it. No bypass. |
| "One loop proves it." | One loop proves the instance. Instantiate a second to prove the *pattern* generalized. |

## Validation (skill self-test)

- **Deterministic core**: `python3 -m pytest tests/ -q` (65 tests) +
  `bash tests/smoke.sh` (E2E DRY tick, zero side effects).
- **Gate**: `python3 <skillify>/scripts/skillify_check.py <this dir> --run-tests`
  exits 0 (SKILL.md contract + syntax-valid scripts + real unit tests).

## References

- `references/invariant-spine.md` — the fixed control-loop core + the 8 invariants.
- `references/adapters.md` — the four adapter contracts + the optional Step-F adapters.
- `references/server-side-net.md` — the mandatory checklist for autonomous acts.
- `references/scenarios.md` — the run-41 defer / reseed-exhaust / merge_not_authorized
  gradeable scenarios (latent-decision evals).
- Reference implementation: broomva `scripts/ticket-dispatch/` (BRO-1740 + BRO-1833).
  Composes bstack primitives P3/P4/P5/P9/P12/P19/P20; it is the concrete realization
  of P19's external-trigger + across-session cube cell.
