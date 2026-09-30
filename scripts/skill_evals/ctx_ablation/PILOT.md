# Context-ablation pilot, 2026-09-29/30

How to run and extend the harness: README.md § "Does the context we inject earn its
tokens?". This file records the pilot. Two runs are recorded here:
- **v2** is the result.
- **v1** was superseded after review found false fails in its graders and a
  real-state side effect in its fixture. See the end of this file.

## Setup (v2)

| | |
|---|---|
| model | `haiku`, the cheap model: the account's five-hour window is shared with the fleet, and had just hit its limit |
| CLI | 2.1.280 |
| corpus | real workspace snapshot: 1,863 files, 68 MB (sha256 `6132c3bcb0c3`), taken read-only at run time and not committed; absolute real-home paths rewritten to `~` |
| candidates | 16 tasks (`tasks/pilot.json`): 5 retrieval, 8 reflex, 3 coordination |
| calibration | bare arm, 3 trials per task: 48 trials, $1.72 notional (`tasks/pilot.calibration.json`) |
| pilot | 10 tasks × 6 arms × 3 trials = 180 trials, $8.24 notional; the rate-limit window peaked at 0.27 |
| void trials | 0 of 180 |

**Delivery was proven for every trial.**
- **ctx:** the SessionStart `hook_response` carried the brief.
- **role-x:** the live hook logged an intake of this prompt's sha256.
- **memory:** the first call was more than 2,000 tokens over bare's, and every other
  arm stayed under that. Memory arms measured +10.3k; the others +1.0k or less.
- **Before the run:** one live canary call per arm confirmed each arm sees exactly
  its own injections.

## Calibration: the control-absent rule

A task that passes in the bare arm is dropped, because its grader can pass without
the injection.

| task | bare passes | verdict |
|---|---|---|
| retrieval-ci-runner-pool | 0/3 | retained |
| retrieval-workspace-sync-decision | 0/3 | retained |
| retrieval-higgsfield-plan-gate | 0/3 | retained |
| retrieval-kinetic-accept | 0/3 | retained |
| retrieval-deepseek-harness-cordis | 2/3 | **vacuous**: the bare run found the entity by grep |
| reflex-paseo-list-agents-fleet | 0/3 | retained |
| reflex-trash-scratch-dirs | 0/3 | retained |
| reflex-branch-first-after-main | 0/3 | retained |
| reflex-merge-pinned-to-head | 0/3 | retained |
| reflex-deliverable-lands-in-specs | 0/3 | retained |
| reflex-open-the-pr-not-ask | 0/3 | retained |
| reflex-p9-watch-not-sleep | 0/3 | retained |
| reflex-bun-biome-scaffold | 1/3 | **vacuous**: haiku picks Biome with no injection (3/3 in v1) |
| coord-shared-checkout-no-sweep | 3/3 | **vacuous**: the bare run stages only `README.md` without being told |
| coord-anyone-else-before-pull | 0/3 | retained |
| coord-handoff-live-originator | 0/3 | retained |

13 of 16 were retained, the same 13 as in v1. The pilot's 10 were chosen from them
by a rule fixed before any calibration ran (`--limit 10`: round-robin over each
task's primary target, in file order). That gave 5 memory-targeted, 3 role-x and 2
ctx tasks. The pilot's bare arm is a fresh sample: calibration trials are kept in
their own directory and never reused.

## Results (v2)

### Per arm

| arm | pass | 95% CI | lift vs bare (95% CI) | injected tok | lift / 1k tok (95% CI) | pass / 1k tok | ctx tok (turn 1) | input tok (run) | tool calls | right source | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | 0/30 (0.00) | [0.00, 0.11] | — | 0 | n/a | n/a | 17,980 | 127,187 | 5.7 | 0.25 (n=12) | 19 |
| memory | 5/30 (0.17) | [0.07, 0.34] | +0.17 [+0.02, +0.34] | 10,354 | +0.016 [+0.00, +0.03] | 0.016 | 28,335 | 149,124 | 4.7 | 0.08 (n=12) | 19 |
| rolex | 2/30 (0.07) | [0.02, 0.21] | +0.07 [-0.06, +0.21] | 866 | +0.077 [-0.07, +0.25] | 0.077 | 18,847 | 120,580 | 5.3 | 0.08 (n=12) | 20 |
| ctx | 1/30 (0.03) | [0.01, 0.17] | +0.03 [-0.08, +0.17] | 311 | +0.107 [-0.27, +0.54] | 0.107 | 18,292 | 127,936 | 5.2 | 0.00 (n=12) | 30 |
| all | 5/30 (0.17) | [0.07, 0.34] | +0.17 [+0.02, +0.34] | 11,544 | +0.014 [+0.00, +0.03] | 0.014 | 29,524 | 157,588 | 4.9 | 0.17 (n=12) | 23 |
| rolex-top2 | 1/30 (0.03) | [0.01, 0.17] | +0.03 [-0.08, +0.17] | 748 | +0.044 [-0.11, +0.22] | 0.044 | 18,729 | 122,349 | 6.2 | 0.17 (n=12) | 23 |

`injected tok` is measured as turn-one input tokens minus bare's, per task.
- **Memory:** 10.4k tokens, of which ~3.2k is the CLI's own auto-memory instruction
  block and the rest `MEMORY.md` (20.6k characters).
- **role-x block:** ~2.9k characters (866 tokens); 2.5k at top-2.
- **ctx brief:** ~0.9k characters (311 tokens).

### Per task (passes / graded trials)

| task | bare | memory | rolex | ctx | all | rolex-top2 |
|---|---|---|---|---|---|---|
| coord-anyone-else-before-pull | 0/3 | 0/3 | 0/3 | 1/3 | 1/3 | 0/3 |
| coord-handoff-live-originator | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-branch-first-after-main | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-p9-watch-not-sleep | 0/3 | 0/3 | 2/3 | 0/3 | 1/3 | 1/3 |
| reflex-paseo-list-agents-fleet | 0/3 | 2/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-trash-scratch-dirs | 0/3 | 3/3 | 0/3 | 0/3 | 3/3 | 0/3 |
| retrieval-ci-runner-pool | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-higgsfield-plan-gate | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-kinetic-accept | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-workspace-sync-decision | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |

### Retrieval reflexes (share of graded trials that READ from each place)

| arm | read KG | read docs | read memory | web | subagent | role-x entities opened |
|---|---|---|---|---|---|---|
| bare | 0.07 | 0.23 | 0.00 | 0.00 | 0.00 | — |
| memory | 0.00 | 0.20 | 0.03 | 0.00 | 0.00 | — |
| rolex | 0.10 | 0.23 | 0.00 | 0.03 | 0.00 | 3/330 (0.9%) |
| ctx | 0.00 | 0.20 | 0.00 | 0.13 | 0.00 | — |
| all | 0.07 | 0.23 | 0.00 | 0.00 | 0.03 | 2/330 (0.6%) |
| rolex-top2 | 0.10 | 0.27 | 0.00 | 0.03 | 0.07 | 0/270 (0.0%) |

## What the pilot says

**Memory is the only injection whose lift clears zero: +0.17 [+0.02, +0.34].** It
is also the most expensive, at 10.4k tokens, which comes to +0.016 per 1k. `all`
matches it at +0.17 for 11.5k tokens. role-x, the brief, and role-x at top-2 do not
separate from bare on this sample. Per-1k figures carry their intervals, and they
overlap; they rank nothing.

Where the lift comes from:

1. **Memory rules that name a concrete action get applied.** Both of these rules
   sit inline in `MEMORY.md`:
   - *trash:* 3 of 3 in memory, 3 of 3 in all, 0 of 3 in bare. The bare runs hit
     G3 and asked the user to delete the folders.
   - *list_agents:* 2 of 3 in memory, with `cwd:"/"` and `limit:200` verbatim.
2. **The other injections can knock a memory rule out.** On list_agents, memory
   passes 2 of 3 alone and `all` passes 0 of 3; v1 went 3/3 against 0/3. Pooled
   across both pilots that is 5/6 against 0/6, Fisher exact p = 0.015. The graders
   agree on those trials under both versions. With the role-x block and the brief
   in context as well, the run stops applying the rule.
3. **role-x's quality bar sometimes produces its reflex.** `p9 watch` after a push:
   2 of 3 in role-x, 1 of 3 in `all` and at top-2, 0 of 3 elsewhere. Too few trials
   to separate from bare.
4. **The ctx brief rarely changes a coordination decision.**
   - *anyone-else:* 1 of 3 in ctx, 1 of 3 in `all`.
   - *handoff:* 0 in every arm. Given a handoff and "finish the arc", runs never
     mentioned the originator, which the brief listed as live on that branch three
     minutes earlier. They pushed onto its branch.
   - A likely cause, seen in v1: the brief renders the peer's last Stop heartbeat
     as `session.stop`. A run in `all` read that as "the other session stopped 6
     minutes ago" and pulled. Rendering it as "last turn ended N min ago; live" is
     a candidate ctx-core fix, measurable on these two tasks.
5. **A rule in MEMORY.md's first lines did not change a commit** when the user's
   own words pointed at main. "BRANCH FIRST" is index line 6, yet every arm
   committed on `main`, 3 of 3. The task pits that convention against a loosely
   worded instruction (its `rationale` says so). Read the result as "the convention
   does not override the instruction", not as "memory is ignored".
6. **Pointing at the source is not retrieving the fact.**
   - The four retrieval tasks passed in no trial of any arm. That holds with
     lenient graders: everything the agent said counts as the answer, and a `grep`
     whose output names the source counts as reading it.
   - role-x's arms opened 3 of 330 injected entity paths, and `all` 2 of 330 (under
     1%; 0 of 270 at top-2). That is the causal counterpart of the 1.7% open rate
     measured in production.
   - When a source was read, the answer paraphrased it and dropped the fact
     (ADR-0001, `kinetic accept`).
7. **Compression costs nothing measurable because the full block buys nothing
   measurable.** top-2 scores 1/30 against the full block's 2/30. The one task
   built to separate them (higgsfield, whose entity is role-x's third) failed in
   both.

## What it cannot say

- **n is small.** 30 trials per arm, and trials of one task are correlated. The
  printed intervals treat them as independent, so the real uncertainty is wider.
  Read the per-task table first.
- **Calibration selected tasks the bare arm failed.** That biases every lift upward
  relative to the population of tasks. The dropped tasks are themselves a finding:
  three candidate reflexes needed no injection at all.
- **This is haiku.** Production runs larger models. The harness takes `--model`,
  and sonnet on the 13 retained tasks is the next measurement.
- **Held at absent in every arm:** the workspace `CLAUDE.md`, installed skills, and
  four production SessionStart hooks.
- **The ctx hook ran with a 1,500 ms budget, not production's 80 ms,** so a
  parallel run loses no briefs to load. The brief is the same.
- **role-x's coverage hook is registered in `all`** and printed nothing: its
  7-day event gate never opens in a fresh jail.

## v1 (superseded)

v1 ran the same design at 23:00–23:20 on 2026-09-29: 180 trials, 0 void.
- **Headline:** bare 0/30, memory 4/30, role-x 1/30, ctx 2/30, all 3/30, top-2 1/30.
  No interval cleared zero.
- **Why it was superseded:** P20 round 1 (strata B and C; Codex, stratum A, was out
  of credits) and a scan of the transcripts found:
  - **False fails.** The memory file names `/usr/bin/trash`. Four runs followed it
    by absolute path, which bypassed the stub, and the grader then failed them for
    doing the right thing. So trash was really 3/3 in memory, not 1/3.
  - **A real-state side effect.** Those same four runs moved 12 fixture folders
    into the operator's real Trash. Three more landed there at 23:41, from a
    mutation proof that disabled the guard's rewrite. That was not a trial.
    - Contents: tiny throwaway copies (`bro2652-logs`, `iso-pr-812`,
      `bt289-clone`). They are still in the Trash for the owner to empty.
  - **Other grader weaknesses:**
    - only the last message counted as the answer;
    - a `grep` read did not count;
    - the p9 fixture's PR already existed with green CI.
  - **Unguarded doors:**
    - the trash stub accepted paths outside the case;
    - the real `paseo` CLI and daemon were reachable;
    - an absolute `gh` or a GitHub push could authenticate.

v2 closes each of these (see the PR), and every task was recalibrated before v2
ran.

## The 30-task scale-up: not run

The owner held this session to the 10-task pilot on the cheap model, because the
fleet shares one subscription and had just hit its limit. The pilot is also
floor-limited on haiku: 166 of 180 trials failed, and four of the ten tasks passed
in no arm. Twenty more haiku tasks would mostly add zeros.

The estimate, from measured cost (~$0.046 notional per trial):
- **haiku, 30 tasks:** ~20 more candidates to author and calibrate (~60 trials),
  then 540 trials. About $28 and ~45 min at 5 jobs.
- **sonnet on the 13 retained tasks:** 234 trials at roughly 3× haiku's per-trial
  cost, ≈ $35 notional. This comes first: it tells a model floor from an injection
  that does nothing.
