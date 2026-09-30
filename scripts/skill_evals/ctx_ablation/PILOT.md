# Context-ablation pilot, 2026-09-29/30

How to run and extend the harness: README.md § "Does the context we inject earn its
tokens?". This file records the pilot.

**v3 is the result.** It ran on the final code of PR #248, after two review rounds.
v1 and v2 ran the same design on earlier code, and are kept at the end of this
file with the reason each was superseded. Their numbers are never pooled with v3's.

## Setup (v3)

| | |
|---|---|
| model | `haiku` (178 of 180 trials resolved to `claude-haiku-4-5-20251001`; the other 2 are void). The cheap model, because the account's five-hour window is shared with the fleet and had just hit its limit |
| CLI | 2.1.280 |
| corpus | real workspace snapshot: 1,863 files, 68 MB (sha256 `6132c3bcb0c3`), taken read-only at run time and not committed; absolute real-home paths rewritten to `~` |
| candidates | 16 tasks (`tasks/pilot.json`): 5 retrieval, 8 reflex, 3 coordination |
| calibration | bare arm, 3 trials per task: 48 trials, 0 void, $1.53 notional (`tasks/pilot.calibration.json`) |
| pilot | 10 tasks × 6 arms × 3 trials = 180 trials, $8.43 notional; the rate-limit window peaked at 0.31 |
| void trials | 2 of 180 (see below) |
| real state | no new entries in the operator's real Trash. That was checked by listing it by hand before and after, outside the sandbox the harness ran in, where its own Trash watch may not have been able to read it. `~/.config/broomva` changed at 1 path during calibration, another session's harness budget file; no harness write was found there |

**Every graded trial carries four delivery proofs:**
- **ctx:** the SessionStart `hook_response` carried the brief.
- **role-x:** the live hook logged an intake of this prompt's sha256.
- **memory:** the unexplained turn-one tokens cleared the threshold. Memory arms need
  at least 6,071, which covers the CLI's auto-memory block plus half of MEMORY.md;
  every other arm must stay under 2,500. No trial was flipped.
- **the case guard:** it logged at least as many decisions as guarded tool calls
  that ran. This is a count, not a per-call match.

**The 2 void trials** are both the p9 task, in memory and role-x-top2. Each hit the
420 s trial timeout while polling CI in a `sleep` loop, which is the behaviour the
p9 reflex exists to prevent. They are counted, never graded.

## Calibration: the control-absent rule

A task that passes in the bare arm is dropped, because its grader can pass without
the injection.

| task | bare passes | verdict |
|---|---|---|
| retrieval-ci-runner-pool | 0/3 | retained |
| retrieval-workspace-sync-decision | 0/3 | retained |
| retrieval-higgsfield-plan-gate | 0/3 | retained |
| retrieval-kinetic-accept | 0/3 | retained |
| retrieval-deepseek-harness-cordis | 1/3 | **vacuous**: the bare run found the entity by grep |
| reflex-paseo-list-agents-fleet | 0/3 | retained |
| reflex-trash-scratch-dirs | 0/3 | retained |
| reflex-branch-first-after-main | 0/3 | retained |
| reflex-merge-pinned-to-head | 0/3 | retained |
| reflex-deliverable-lands-in-specs | 0/3 | retained |
| reflex-open-the-pr-not-ask | 0/3 | retained |
| reflex-p9-watch-not-sleep | 0/3 | retained |
| reflex-bun-biome-scaffold | 2/3 | **vacuous**: haiku picks Biome with no injection |
| coord-shared-checkout-no-sweep | 3/3 | **vacuous**: the bare run stages only `README.md` without being told |
| coord-anyone-else-before-pull | 0/3 | retained |
| coord-handoff-live-originator | 0/3 | retained |

The same 13 were retained, and the same 3 dropped, in all three calibrations. The
pilot's 10 came from those 13 by a rule fixed before any calibration ran
(`--limit 10`: round-robin over each task's primary target, in file order). That
gave 5 memory-targeted, 3 role-x and 2 ctx tasks. The pilot's bare arm is a fresh
sample; calibration trials live in their own directory and are never reused.

## Results (v3)

### Per arm

| arm | pass | 95% CI | lift vs bare (trial CI) | lift, task-clustered CI | injected tok | lift / 1k tok (trial CI) | pass / 1k tok | ctx tok (turn 1) | input tok (run) | tool calls | right source | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | 0/30 (0.00) | [0.00, 0.11] | — | — | 0 | n/a | n/a | 17,973 | 133,395 | 6.0 | 0.25 (n=12) | 28 |
| memory | 6/29 +1 void (0.21) | [0.10, 0.38] | +0.21 [+0.05, +0.38] | [-0.10, +0.50] | 10,361 | +0.020 [+0.00, +0.04] | 0.020 | 28,334 | 164,279 | 4.7 | 0.08 (n=12) | 18 |
| rolex | 1/30 (0.03) | [0.01, 0.17] | +0.03 [-0.08, +0.17] | [-0.04, +0.11] | 883 | +0.038 [-0.09, +0.19] | 0.038 | 18,856 | 127,655 | 6.4 | 0.17 (n=12) | 24 |
| ctx | 1/30 (0.03) | [0.01, 0.17] | +0.03 [-0.08, +0.17] | [-0.04, +0.11] | 323 | +0.103 [-0.26, +0.52] | 0.103 | 18,296 | 102,020 | 6.1 | 0.08 (n=12) | 22 |
| all | 8/30 (0.27) | [0.14, 0.44] | +0.27 [+0.10, +0.44] | [-0.00, +0.54] | 11,550 | +0.023 [+0.01, +0.04] | 0.023 | 29,523 | 165,308 | 5.5 | 0.17 (n=12) | 23 |
| rolex-top2 | 2/29 +1 void (0.07) | [0.02, 0.22] | +0.07 [-0.06, +0.22] | [-0.13, +0.33] | 760 | +0.091 [-0.07, +0.29] | 0.091 | 18,733 | 112,326 | 5.1 | 0.25 (n=12) | 19 |

**The two lift intervals.** The trial interval treats every trial as independent.
The task-clustered interval is a t-interval over the 10 per-task differences from
bare, which is the honest one here: trials of one task are correlated.

**Injected tokens** are measured as turn-one input tokens minus bare's, per task.
- **Memory:** 10.4k tokens, ~3.2k of them the CLI's own auto-memory block, the rest
  `MEMORY.md` (20.6k characters).
- **role-x block:** ~2.9k characters (883 tokens); 2.5k at top-2.
- **ctx brief:** ~0.9k characters (323 tokens).

### Per task (passes / graded trials)

| task | bare | memory | rolex | ctx | all | rolex-top2 |
|---|---|---|---|---|---|---|
| coord-anyone-else-before-pull | 0/3 | 0/3 | 0/3 | 1/3 | 2/3 | 0/3 |
| coord-handoff-live-originator | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-branch-first-after-main | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-p9-watch-not-sleep | 0/3 | 0/2 (1 void) | 1/3 | 0/3 | 2/3 | 2/2 (1 void) |
| reflex-paseo-list-agents-fleet | 0/3 | 3/3 | 0/3 | 0/3 | 1/3 | 0/3 |
| reflex-trash-scratch-dirs | 0/3 | 3/3 | 0/3 | 0/3 | 3/3 | 0/3 |
| retrieval-ci-runner-pool | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-higgsfield-plan-gate | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-kinetic-accept | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-workspace-sync-decision | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |

### Retrieval reflexes (share of graded trials that READ from each place)

| arm | read KG | read docs | read memory | web | subagent | role-x entities opened |
|---|---|---|---|---|---|---|
| bare | 0.20 | 0.30 | 0.03 | 0.03 | 0.07 | — |
| memory | 0.14 | 0.24 | 0.03 | 0.00 | 0.00 | — |
| rolex | 0.20 | 0.33 | 0.03 | 0.00 | 0.03 | 3/120 (2.5%) |
| ctx | 0.20 | 0.30 | 0.00 | 0.03 | 0.10 | — |
| all | 0.13 | 0.27 | 0.10 | 0.00 | 0.07 | 4/120 (3.3%) |
| rolex-top2 | 0.21 | 0.28 | 0.00 | 0.00 | 0.00 | 0/58 (0.0%) |

"Role-x entities opened" counts only the task-relevant entities role-x lists: the
ones that ask to be opened. It excludes the persona constraints, which carry their
claim inline.

## What the pilot says

**No injection's lift is established on this sample.**
- **Memory** is +0.21 on the trial interval [+0.05, +0.38], but the task-clustered
  interval, [-0.10, +0.50], includes zero.
- **`all`** is +0.27 [+0.10, +0.44] by trial, and task-clustered [-0.00, +0.54]:
  zero sits at the edge.
- **role-x, the ctx brief and role-x at top-2** are within noise of bare on both
  intervals.

Every lift comes from a handful of tasks, and the per-task table is where to read
it:

1. **Two memory rules that name a concrete action were applied.** Both are inline
   in `MEMORY.md`.
   - *trash:* 3 of 3 in memory, 3 of 3 in all, 0 of 3 in bare. The bare runs hit
     the delete gate, then asked the user or moved the folders ad hoc.
   - *list_agents:* 3 of 3 in memory, with `cwd:"/"` and `limit:200` verbatim.

   These two tasks carry all of memory's passes. That is why the task-clustered
   interval is wide.
2. **Whether the other injections knock a memory rule out is not settled.**
   - On list_agents, `all` scored 1 of 3 against memory's 3 of 3 (Fisher exact
     p = 0.40). The same direction showed in v1 and v2, but those runs had other
     graders and corpora, so they are not pooled.
   - On anyone-else the direction reversed: ctx 1 of 3, `all` 2 of 3.
   - It is a hypothesis for a larger run, not a finding.
3. **role-x's quality bar produced its reflex.** It names p9, and `p9 watch` after a
   push came in 1 of 3 in role-x, 2 of 3 in `all`, 2 of 2 at top-2 (one void), and
   0 in bare (0 of 3) and memory (0 of 2). This is the one role-x signal in the
   pilot, and it is small.
4. **The ctx brief moved one coordination decision a little.**
   - *anyone-else:* 1 of 3 in ctx, 2 of 3 in `all`, 0 elsewhere.
   - *handoff:* 0 in every arm. Given a handoff and "finish the arc", runs pushed
     onto a branch the brief listed as live three minutes earlier.
   - A candidate cause, seen in v1's transcripts: the brief renders the peer's
     Stop heartbeat as `session.stop`, which a run read as "stopped". A wording fix
     in ctx-core is testable on these two tasks.
5. **A convention in MEMORY.md's first lines did not override the user's words.**
   "BRANCH FIRST" is index line 6, and every arm committed on `main` when told to
   switch to main and commit. The task pits the two against each other (see its
   `rationale`).
6. **The retrieval tasks passed in no arm.**
   - That result belongs to these tasks, not to retrieval in general. Each grader
     requires an exact ID token the prompt never asks for (`ADR-0001`,
     `minimum_pro_plan_required`, `make ci-runner`, `kinetic accept`) AND a read of
     a listed source.
   - Runs did read the sources: 0.08–0.25 of trials per arm, bare included. The
     answers then paraphrased the fact away.
   - role-x's arms opened 3 of 120 and 4 of 120 task entities they were pointed
     at (2.5% and 3.3%; 0 of 58 at top-2). That sits near the 1.7% the
     coordinator measured in production, but the denominators differ: here 6 of
     the 10 tasks are not retrieval questions.
7. **Compression shows no measurable cost.** top-2 is 2/29 against the full block's
   1/30. The one task built to separate them (higgsfield, whose entity is role-x's
   third) failed in both.

## What it cannot say

- **n is small**, and the task is the real unit: 10 tasks, 3 trials each.
- **Selection bias.** Calibration kept only tasks bare failed, which biases lifts
  upward relative to the population of tasks. Three candidate reflexes needed no
  injection at all.
- **This is haiku.** Production runs larger models.
- **Held at absent in every arm:** the workspace `CLAUDE.md`, installed skills, and
  four production SessionStart hooks.
- **The ctx hook ran with a 1,500 ms budget,** not production's 80 ms.
- **role-x's coverage hook** is registered in `all` and printed nothing, because
  its 7-day event gate never opens in a fresh jail.
- **The case guard matches strings.** It is a wall against a run that wanders, not
  a sandbox. A command built at runtime can get past it (README).

## Superseded runs

**v2** (2026-09-29, 23:55 to 00:15), on the code after review round 1: 180 trials,
0 void.
- **Results:** bare 0/30, memory 5/30, role-x 2/30, ctx 1/30, all 5/30, top-2 1/30.
- **Why superseded:** review round 2 found four problems.
  - A grader could never fail: the trash task's `refused` check.
  - The memory-delivery threshold sat below the auto-memory block.
  - The guard failed open and logged only its blocks, so v2's trials cannot
    satisfy the guard-ran proof.
  - PILOT pooled v2 with v1 for a significance claim, which the harness's own
    run-key rule forbids.

**v1** (2026-09-29, 23:00 to 23:20), on the first code: 180 trials, 0 void.
- **Results:** bare 0/30, memory 4/30, role-x 1/30, ctx 2/30, all 3/30, top-2 1/30.
- **Why superseded:** review round 1 found:
  - **False fails.** Four runs followed MEMORY.md's `/usr/bin/trash` by absolute
    path, which bypassed the stub, and were graded FAIL for the right action.
  - **A real-state side effect.** Those same runs put 12 fixture folders into the
    operator's real Trash.
  - **Unguarded doors.** The trash stub accepted outside paths; the `paseo` CLI and
    real GitHub were reachable.
  - **Other false-fail modes** in several graders.

**The Trash incident, in full.** 15 tiny fixture copies are in the operator's real
Trash (`bro2652-logs`, `iso-pr-812`, `bt289-clone`, with timestamp suffixes):
- 12 from the v1 trials, at 23:03–23:15 on 2026-09-29;
- 3 at 23:41 from a mutation proof that disabled the guard's rewrite. The synthetic
  executor has refused real binaries outright since then.

Nothing has landed there since. The Trash is now watched on every run. The folders
are left for the owner to empty.

## The 30-task scale-up: not run

The owner held this session to the 10-task pilot on the cheap model, because the
fleet shares one subscription and had just hit its limit. The pilot is also
floor-limited on haiku: 160 of 178 graded trials failed, and 6 of the 10 tasks
passed in at most one arm.

The estimate, from measured cost (~$0.047 notional per trial):
- **haiku, 30 tasks:** ~20 more candidates to author and calibrate (~60 trials),
  then 540 trials. About $28, and ~45 min at 5 jobs in 10-minute chunks.
- **sonnet on the 13 retained tasks:** 234 trials at roughly 3× haiku's per-trial
  cost, ≈ $35 notional. This comes first: it tells a model floor from an injection
  that does nothing.
