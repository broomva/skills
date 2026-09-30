# Context-ablation pilot, 2026-09-29

How to run and extend the harness: README.md § "Does the context we inject earn its
tokens?". This file is the record of the first run.

## Setup

| | |
|---|---|
| model | `haiku` (the cheap model: the account's five-hour window is shared with the fleet, and had just hit its limit) |
| CLI | 2.1.280 |
| corpus | real workspace snapshot: 1,862 files, 68 MB (sha256 `6c3d177d6ea2`), taken read-only at run time, not committed |
| candidates | 16 tasks (`tasks/pilot.json`): 5 retrieval, 8 reflex, 3 coordination |
| calibration | bare arm, 3 trials per task, 48 trials, $2.11 notional (`tasks/pilot.calibration.json`) |
| pilot | 10 tasks × 6 arms × 3 trials = 180 trials, $8.52 notional; the rate-limit window peaked at 0.25 |
| void trials | 0 of 180: every non-bare trial was shown to have received its injection |

Every arm was also checked end to end before the run, with one model call per arm
(`preflight --live-canary`). Each arm saw exactly its own canaries: memory, the
board brief, or role-x's quality bar.

## Calibration: the control-absent rule

A task that passes in the bare arm is dropped: its grader can pass without the
injection, so a pass under an injection would say nothing about it.

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
| reflex-bun-biome-scaffold | 3/3 | **vacuous**: haiku picks Biome with no injection |
| coord-shared-checkout-no-sweep | 3/3 | **vacuous**: the bare run stages only `README.md` without being told |
| coord-anyone-else-before-pull | 0/3 | retained |
| coord-handoff-live-originator | 0/3 | retained |

13 of 16 retained. The pilot's 10 were chosen from those 13 by a rule fixed before
the calibration ran (`--limit 10`: round-robin over each task's primary target, in
file order). That gave 5 memory-targeted, 3 role-x and 2 ctx tasks. The pilot's bare
arm is a fresh sample, not the calibration trials.

## Results

### Per arm

| arm | pass | 95% CI | lift vs bare (95% CI) | injected tok | lift / 1k tok | pass / 1k tok | ctx tok (turn 1) | input tok (run) | tool calls | right source | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | 0/30 (0.00) | [0.00, 0.11] | — | 0 | n/a | n/a | 17,975 | 116,778 | 5.1 | 0.08 (n=12) | 18 |
| memory | 4/30 (0.13) | [0.05, 0.30] | +0.13 [-0.01, +0.30] | 10,297 | +0.013 | 0.013 | 28,271 | 176,809 | 5.1 | 0.00 (n=12) | 18 |
| rolex | 1/30 (0.03) | [0.01, 0.17] | +0.03 [-0.08, +0.17] | 880 | +0.038 | 0.038 | 18,855 | 132,320 | 5.4 | 0.00 (n=12) | 18 |
| ctx | 2/30 (0.07) | [0.02, 0.21] | +0.07 [-0.06, +0.21] | 311 | +0.214 | 0.214 | 18,286 | 113,290 | 5.2 | 0.00 (n=12) | 19 |
| all | 3/30 (0.10) | [0.03, 0.26] | +0.10 [-0.03, +0.26] | 11,479 | +0.009 | 0.009 | 29,454 | 191,420 | 7.5 | 0.25 (n=12) | 28 |
| rolex-top2 | 1/30 (0.03) | [0.01, 0.17] | +0.03 [-0.08, +0.17] | 756 | +0.044 | 0.044 | 18,730 | 133,413 | 5.6 | 0.17 (n=12) | 18 |

`injected tok` is measured: turn-one input tokens minus bare's, per task. Memory
costs 10.3k tokens, of which ~3.2k is the CLI's own auto-memory instruction block
and the rest is `MEMORY.md` (20.4k characters). The role-x block is ~2.9k
characters (880 tokens), cut to 2.5k at top-2. The ctx brief is ~0.9k characters
(311 tokens).

### Per task (passes / graded trials)

| task | bare | memory | rolex | ctx | all | rolex-top2 |
|---|---|---|---|---|---|---|
| coord-anyone-else-before-pull | 0/3 | 0/3 | 0/3 | 2/3 | 0/3 | 0/3 |
| coord-handoff-live-originator | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-branch-first-after-main | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-p9-watch-not-sleep | 0/3 | 0/3 | 1/3 | 0/3 | 2/3 | 1/3 |
| reflex-paseo-list-agents-fleet | 0/3 | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| reflex-trash-scratch-dirs | 0/3 | 1/3 | 0/3 | 0/3 | 1/3 | 0/3 |
| retrieval-ci-runner-pool | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-higgsfield-plan-gate | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-kinetic-accept | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| retrieval-workspace-sync-decision | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |

### Retrieval reflexes (share of graded trials)

| arm | read KG | read docs | read memory | web | subagent | role-x entities opened |
|---|---|---|---|---|---|---|
| bare | 0.03 | 0.23 | 0.00 | 0.03 | 0.00 | — |
| memory | 0.03 | 0.20 | 0.10 | 0.00 | 0.00 | — |
| rolex | 0.13 | 0.27 | 0.00 | 0.00 | 0.00 | 3/330 (0.9%) |
| ctx | 0.03 | 0.23 | 0.03 | 0.10 | 0.07 | — |
| all | 0.13 | 0.27 | 0.07 | 0.00 | 0.07 | 3/330 (0.9%) |
| rolex-top2 | 0.10 | 0.23 | 0.00 | 0.00 | 0.00 | 0/270 (0.0%) |

## What the pilot says

**The headline: on haiku, none of the injections moves the pass rate by a margin
this sample can resolve.** Every lift interval crosses zero. Memory comes closest,
at +0.13 [-0.01, +0.30], and it is also the most expensive injection, at 10.3k
tokens. The ctx brief has the best return per token, +0.214 per 1k tokens, on 311
tokens. The `all` arm, which is what production actually injects, scores
+0.10 [-0.03, +0.26] for 11.5k tokens: +0.009 per 1k.

What the per-task table shows, trial by trial in the transcripts:

1. **A rule that is in context gets applied when it is nearly alone, and is
   dropped when it is not.**
   - *list_agents.* The memory arm called `list_agents(cwd:"/", limit:200)`
     verbatim in 3 of 3 trials. In `all`, with the role-x block and the brief also
     in context, it did not in 0 of 3: one trial never called the tool, the other
     two passed `limit:100` or the workspace cwd.
   - *anyone-else.* The ctx brief alone got the peer named and the pull withheld
     in 2 of 3 trials; `all` managed 0 of 3.

   The combined injection is worth less than the best single injection it
   contains.
2. **The ctx brief's wording defeats its own purpose.**
   - A live peer's last event renders as `session.stop`. Stop fires at the end of
     every turn, so it is a heartbeat, but the model reads it literally. In `all`:
     "No one is actively working right now (the other session stopped 6 minutes
     ago)", then it pulled.
   - The handoff task failed in every arm, the ctx arm included. Given a handoff
     and "finish the arc", the ctx-arm runs never mentioned the originator the
     brief listed as live on that branch three minutes earlier. They did the work
     and pushed onto its branch.
   - Rendering the heartbeat as "last turn ended 6 min ago; live" is a candidate
     ctx-core fix. It can be measured on these same two tasks.
3. **A rule in MEMORY.md's first lines is not enough to change a commit.** "BRANCH
   FIRST" is line 6 of the index, yet every arm, memory included, committed on
   `main` in 3 of 3 trials.
4. **Pointing at the source is not retrieving the fact.**
   - The four retrieval tasks passed in no trial of any arm.
   - role-x surfaced the right entity for two of them: first for
     workspace-sync, third for higgsfield. Its arms opened 3 of 330 injected
     entity paths (0.9%, 0 of 270 at top-2). That is the causal counterpart of the
     1.7% production open rate.
   - When the entity was read (`all`: right source in 0.25 of trials), the answer
     paraphrased it and dropped the fact (ADR-0001, `kinetic accept`).
5. **Compression costs nothing measurable because the full block buys nothing
   measurable.** top-2 scores the same as top-5 (1/30 each). The one task built to
   separate them (higgsfield: its entity is role-x's third) failed in both.

## What it cannot say

- **n is small.** 30 trials per arm, and trials of one task are correlated. The
  intervals printed treat them as independent, so the real uncertainty is wider.
  Read the per-task table first.
- **Calibration selected tasks the bare arm failed.** Bare's fresh 0/30 is
  consistent with that, but it biases every lift upward for the population of
  tasks. The dropped tasks are themselves a finding: three candidate reflexes need
  no injection at all.
- **This is haiku.** Production sessions run larger models, which may use the same
  context differently. The harness takes `--model`, and a sonnet run of the 13
  retained tasks is the obvious next measurement.
- **Held at absent in every arm:** the workspace `CLAUDE.md`, installed skills, and
  four production SessionStart hooks. Where those overlap an injection,
  production's marginal value is lower than measured here.

## The 30-task scale-up: not run

The owner narrowed this session to the 10-task pilot on the cheap model, because
the fleet shares one subscription and had just hit its limit. The pilot is also
floor-limited on haiku: 169 of 180 trials failed. Twenty more haiku tasks would
mostly add zeros.

The estimate, from measured costs:
- **haiku, 30 tasks:** ~20 more candidates to author and calibrate (~60 trials),
  then 30 × 6 × 3 = 540 trials. About 600 trials at $0.047 notional ≈ $28, and
  ~45 min at 5 jobs.
- **sonnet on the 13 retained tasks first:** 13 × 6 × 3 = 234 trials, roughly 3×
  haiku's per-trial cost ≈ $35 notional. It tests whether the floor is the model or
  the injection.
