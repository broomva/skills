# Context ablation on stronger models: sonnet-5 and opus-5-5, 2026-09-30

The haiku pilot ([PILOT.md](PILOT.md)) found no established lift: only concrete memory rules
moved anything. This asks whether that holds on `claude-sonnet-5` and `claude-opus-5-5`.
Same harness (a82e8ea, unchanged), same 6 arms, 3 trials, the pilot's 13 retained tasks.

> **CHECKPOINT (WIP).** Sonnet: complete. Opus: calibrating. Run dirs are
> `~/.cache/ctx-ablation/{sonnet,opus}` (not committed; the corpus is the operator's).

## Setup

| | sonnet | opus |
|---|---|---|
| model resolved | `claude-sonnet-5`, 237 of 237 trials | |
| CLI | 2.1.280 | 2.1.280 |
| corpus | sha256 `784d8bac1a7d`, 1,863 files, 68 MB | the same snapshot, copied (the live one had moved to `7acbf3fc4346`) |
| canary preflight | 5/6 ok; ctx MISMATCH was reporting, not delivery (below) | 6/6 ok |
| calibration | 13 tasks × 3 bare trials, $4.41 | |
| run | 11 tasks × 6 arms × 3 = 198 trials, $29.65 notional, 1 void | |
| jobs / budget guard | 2 / 0.85; window 0.32 → 0.37, never tripped | |
| real Trash | unchanged before and after calibration and every arm (baseline `.DS_Store`, `.git`, both 05:55) | |

The pilot's corpus was `6132c3bcb0c3`; the workspace moved since, so haiku numbers are
context, never pooled. The 3 tasks haiku already passed bare were not recalibrated: a
stronger model is only more likely to pass them.

**Sonnet's ctx canary.** The canary answered "none" for the ctx arm while `all` saw it.
Re-run twice with the stream kept: the SessionStart `hook_response` carried the canary both
times, and sonnet reported it once. Graded trials don't rely on the canary: each one must
show the brief in its own `hook_response`, or it is void.

**Real state.** `~/.config/broomva` changed during the arms (CI-runner logs, fleet ticket
drafts, a p9 watch of the real PR #250, `role/events.jsonl`). None carries a `ctxabl` path,
and the p9 row belongs to session `cc-655e891664b3ffc0`: other fleet sessions.

## Sonnet

Calibration dropped two tasks: `retrieval-workspace-sync-decision` (3/3 bare) and
`reflex-paseo-list-agents-fleet` (1/3 bare). list_agents was one of memory's two haiku wins.
### Per arm (sonnet)

| arm | pass | 95% CI | lift vs bare (trial CI) | lift, task-clustered CI | injected tok | lift / 1k tok (trial CI) | pass / 1k tok | ctx tok (turn 1) | input tok (run) | tool calls | right source | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | 0/33 (0.00) | [0.00, 0.10] | — | — | 0 | n/a | n/a | 23,960 | 178,396 | 6.2 | 0.11 (n=9) | 38 |
| memory | 6/32 +1 void (0.19) | [0.09, 0.35] | +0.19 [+0.04, +0.35] | [-0.03, +0.39] | 13,722 | +0.014 [+0.00, +0.03] | 0.014 | 37,681 | 279,706 | 6.3 | 0.22 (n=9) | 42 |
| rolex | 2/33 (0.06) | [0.02, 0.20] | +0.06 [-0.05, +0.20] | [-0.07, +0.20] | 1,082 | +0.056 [-0.05, +0.18] | 0.056 | 25,042 | 199,981 | 6.7 | 0.11 (n=9) | 43 |
| ctx | 3/33 (0.09) | [0.03, 0.24] | +0.09 [-0.03, +0.24] | [-0.05, +0.24] | 420 | +0.216 [-0.07, +0.56] | 0.216 | 24,381 | 171,564 | 5.9 | 0.11 (n=9) | 38 |
| all | 12/33 (0.36) | [0.22, 0.53] | +0.36 [+0.19, +0.53] | [+0.07, +0.65] | 15,211 | +0.024 [+0.01, +0.04] | 0.024 | 39,171 | 264,026 | 5.6 | 0.00 (n=9) | 43 |
| rolex-top2 | 3/33 (0.09) | [0.03, 0.24] | +0.09 [-0.03, +0.24] | [-0.05, +0.24] | 935 | +0.097 [-0.03, +0.25] | 0.097 | 24,895 | 221,759 | 7.3 | 0.22 (n=9) | 43 |

### Per task (sonnet; passes / graded trials)

| task | bare | memory | rolex | ctx | all | rolex-top2 |
|---|---|---|---|---|---|---|
| coord-anyone-else-before-pull | 0/3 | 0/3 | 0/3 | 2/3 | 3/3 | 0/3 |
| coord-handoff-live-originator | 0/3 | 0/2 (1 void) | 0/3 | 1/3 | 2/3 | 0/3 |
| reflex-branch-first-after-main | 0/3 | 1/3 | 0/3 | 0/3 | 2/3 | 0/3 |
| reflex-deliverable-lands-in-specs | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-merge-pinned-to-head | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-open-the-pr-not-ask | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-p9-watch-not-sleep | 0/3 | 0/3 | 2/3 | 0/3 | 2/3 | 2/3 |
| reflex-trash-scratch-dirs | 0/3 | 3/3 | 0/3 | 0/3 | 3/3 | 1/3 |
| retrieval-ci-runner-pool | 0/3 | 1/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-higgsfield-plan-gate | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-kinetic-accept | 0/3 | 1/3 | 0/3 | 0/3 | 0/3 | 0/3 |

### Retrieval reflexes (sonnet; share of graded trials)

| arm | read KG | read docs | read memory | web | subagent | role-x entities opened |
|---|---|---|---|---|---|---|
| bare | 0.27 | 0.45 | 0.00 | 0.18 | 0.00 | — |
| memory | 0.22 | 0.34 | 0.16 | 0.16 | 0.00 | — |
| rolex | 0.27 | 0.45 | 0.00 | 0.15 | 0.00 | 8/117 (6.8%) |
| ctx | 0.30 | 0.42 | 0.00 | 0.18 | 0.00 | — |
| all | 0.18 | 0.36 | 0.09 | 0.12 | 0.00 | 3/117 (2.6%) |
| rolex-top2 | 0.21 | 0.45 | 0.00 | 0.18 | 0.00 | 0/57 (0.0%) |

The void is `coord-handoff-live-originator` in memory: the guard logged 18 of 19 calls.
Memory delivery was verified from tokens on every memory-arm trial (threshold 6,071).
