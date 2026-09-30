# Context ablation on stronger models: sonnet-5 and opus-5-5, 2026-09-30

The haiku pilot ([PILOT.md](PILOT.md)) found no established lift; only concrete memory rules
moved anything. This asks whether that holds on `claude-sonnet-5` and `claude-opus-5-5`.
The harness is a82e8ea, unchanged. Same 6 arms and 3 trials; each model recalibrated the
pilot's 13 retained tasks in its own bare arm.

**In short:**
- **Stronger models, more lift.** On the 6 tasks all three models kept, every injected
  arm's pass rate rises from haiku to sonnet to opus. That is descriptive: 17–18 trials per
  cell, no CI, and haiku ran on another corpus. Across the full task sets, memory does not
  rise (0.21 → 0.19 → 0.48).
- **Opus and memory.** On opus, memory's lift is established: +0.48, task-clustered CI
  [+0.12, +0.85]. `all` is established on sonnet and opus.
- **The ctx brief** is the most efficient per token on its targets: 6/6 on opus, for ~400
  tokens. Its arm-level lift is not established.
- **role-x's clear effect is on p9:** 0/9 bare, 6/9 rolex, 7/8 top-2. Elsewhere it is small.
- **Retrieval.** Opus passes 3 of 4 retrieval tasks bare, and sonnet 1 of 4. On the tasks
  kept, no injection's lift is detectable.

## Headline: pass rate by arm

Each cell is passes / graded trials, with the task-clustered 95% CI of the lift vs bare.

| arm | haiku (pilot, 10 tasks) | sonnet (11 tasks) | opus (9 tasks) | like-for-like, 6 shared tasks: haiku / sonnet / opus |
|---|---|---|---|---|
| bare | 0/30 | 0/33 | 0/27 | 0/18 · 0/18 · 0/18 |
| memory | 6/29 [-0.10, +0.50] | 6/32 [-0.03, +0.39] | **13/27 [+0.12, +0.85]** | 3/17 · 4/17 · 6/18 |
| rolex | 1/30 [-0.04, +0.11] | 2/33 [-0.07, +0.20] | 5/27 [-0.10, +0.47] | 1/18 · 2/18 · 5/18 |
| ctx | 1/30 [-0.04, +0.11] | 3/33 [-0.05, +0.24] | 6/27 [-0.12, +0.56] | 1/18 · 3/18 · 6/18 |
| all | 8/30 [-0.00, +0.54] | **12/33 [+0.07, +0.65]** | **21/27 [+0.44, +1.00]** | 7/18 · 12/18 · 15/18 |
| rolex-top2 | 2/29 [-0.13, +0.33] | 3/33 [-0.05, +0.24] | 4/26 [-0.11, +0.41] | 2/17 · 3/18 · 4/18 |

**Reading the table.** Compare within a column. Each model's task set is what it failed
bare, so the first three columns are different task sets. The last column holds the 6 tasks
all three models kept: 2 coordination, branch-first, p9, trash, higgsfield. On those, every
injected arm rises from haiku to sonnet to opus. Across the full columns memory does not (0.21 →
0.19 → 0.48).

## Headline: each injection on the tasks it targets (passes; bare is 0 on every row)

| injection → targets | haiku | sonnet | opus |
|---|---|---|---|
| ctx brief → 2 coordination tasks | 1/6 | 3/6 | **6/6** |
| role-x → p9 watch (rolex / top-2) | 1/3 / 2/2 | 2/3 / 2/3 | **3/3 / 3/3** |
| memory → rules stated as an action in a MEMORY.md line (trash; branch-first) | 3/6 | 4/6 | **6/6** |
| memory → rules the index only hints at or omits (merge pin, specs, open-the-PR) | not in pilot | **0/9** | 7/9 |

## Setup

| | sonnet | opus |
|---|---|---|
| model resolved | `claude-sonnet-5`, 237/237 trials | `claude-opus-5-5`, 201/201 trials |
| corpus | sha256 `784d8bac1a7d`, 1,863 files (harness count), 68 MB | the same snapshot, copied (the live one had moved on) |
| canary preflight | 5/6; the ctx miss was reporting, not delivery (below) | 6/6 (`opus-preflight.log`, taken on the live corpus `7acbf3fc4346` before the snapshot swap) |
| calibration | 39 trials, $4.41; **11/13 retained** | 39 trials, $7.22; **9/13 retained** |
| run | 11 × 6 × 3 = 198 trials, $29.65, 1 void | 9 × 6 × 3 = 162 trials, $34.96, 1 void |
| wall, jobs | 06:06–07:36, jobs=2, arms one after another | 07:44–09:14, jobs=2; paused 08:44–08:51 |
| rate-limit window | 0.32 → 0.37 | 0.38 → 0.85; the budget guard stopped `all` mid-arm, resumed after the 08:50 reset |

Notional cost is ~$76 over 438 trials; the canary calls were not metered.
- **Opus estimate.** Made before its calibration, from sonnet's cost and the 2× list price:
  $70–80.
- **Actual.** $42. Fewer tasks were retained, and an opus trial cost 1.64× sonnet's in
  calibration and 1.44× in the run.

**Dropped in calibration (they pass bare):**
- **sonnet:** `retrieval-workspace-sync-decision` (3/3), `reflex-paseo-list-agents-fleet` (1/3).
- **opus:** those two (2/3 and 3/3), plus `retrieval-kinetic-accept` (3/3) and
  `retrieval-ci-runner-pool` (2/3).

list_agents was one of memory's two haiku wins. Opus does it unaided (3/3); sonnet did
it once in 3.

**Delivery.** Every graded trial carries the pilot's four proofs. Memory was verified from
tokens on every memory-arm trial, and no trial was flipped. Void trials:
- **sonnet, 1:** handoff in memory; the guard logged 18 of 19 calls.
- **opus, 1:** open-the-pr in rolex-top2, at the 420 s timeout.

**Sonnet's ctx canary** answered "none". It was re-run twice with the stream kept: the
SessionStart `hook_response` carried the canary both times, and sonnet reported it once.
That evidence is in this session's log, not the run directory.

**Real Trash.** New entries, listed before and after each stage:

| stage | sonnet | opus |
|---|---|---|
| calibrate, bare, memory | none | none |
| rolex | none | 9 `kin_*` at 08:22: another session's subagent ran `trash /tmp/kin_*` (Paseo worktree `0t10n7id`) |
| ctx | none | none |
| all | none | `ccprobe-write-test-56393` (08:54) |
| rolex-top2 | none | `.ccprobe-writetool-41059075` and `settings.local.json` (`{"_probe": "41059075"}`), 08:57 |

- **The ccprobe entries** match `./probe.sh` sessions driven from worktree
  `0t10n7id-sharp-moth`. The evidence is those sessions' own transcripts, not the run
  directory. No trial transcript names any of these entries.
- **Later arrivals.** `ccprobe-ids.48558`, `ccprobe-CcnrMz` and `ccprobe2-gBKBqm` reached
  the Trash at 09:19:56, 09:20:07 and 09:32:28 (status-change times). That is after the
  last trial (09:14:01), when no harness was running.
- **The check lines.** From 08:51, checks diffed against a baseline that included the 9
  `kin_*` files, and their "unchanged" line still printed the old baseline label.
- **Mine, not a trial:** my own `trash` of an unused corpus copy, moved back out at once.

**`~/.config/broomva` changes** (CI-runner logs, fleet drafts, p9 watches of the real PRs
workspace#837/838 and skills#250) carry no `ctxabl` path. They are live sessions.

## Sonnet

| arm | pass | 95% CI | lift vs bare (trial CI) | lift, task-clustered CI | injected tok | lift / 1k tok (trial CI) | pass / 1k tok | ctx tok (turn 1) | input tok (run) | tool calls | right source | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | 0/33 (0.00) | [0.00, 0.10] | — | — | 0 | n/a | n/a | 23,960 | 178,396 | 6.2 | 0.11 (n=9) | 38 |
| memory | 6/32 +1 void (0.19) | [0.09, 0.35] | +0.19 [+0.04, +0.35] | [-0.03, +0.39] | 13,722 | +0.014 [+0.00, +0.03] | 0.014 | 37,681 | 279,706 | 6.3 | 0.22 (n=9) | 42 |
| rolex | 2/33 (0.06) | [0.02, 0.20] | +0.06 [-0.05, +0.20] | [-0.07, +0.20] | 1,082 | +0.056 [-0.05, +0.18] | 0.056 | 25,042 | 199,981 | 6.7 | 0.11 (n=9) | 43 |
| ctx | 3/33 (0.09) | [0.03, 0.24] | +0.09 [-0.03, +0.24] | [-0.05, +0.24] | 420 | +0.216 [-0.07, +0.56] | 0.216 | 24,381 | 171,564 | 5.9 | 0.11 (n=9) | 38 |
| all | 12/33 (0.36) | [0.22, 0.53] | +0.36 [+0.19, +0.53] | [+0.07, +0.65] | 15,211 | +0.024 [+0.01, +0.04] | 0.024 | 39,171 | 264,026 | 5.6 | 0.00 (n=9) | 43 |
| rolex-top2 | 3/33 (0.09) | [0.03, 0.24] | +0.09 [-0.03, +0.24] | [-0.05, +0.24] | 935 | +0.097 [-0.03, +0.25] | 0.097 | 24,895 | 221,759 | 7.3 | 0.22 (n=9) | 43 |

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

## Opus

| arm | pass | 95% CI | lift vs bare (trial CI) | lift, task-clustered CI | injected tok | lift / 1k tok (trial CI) | pass / 1k tok | ctx tok (turn 1) | input tok (run) | tool calls | right source | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | 0/27 (0.00) | [0.00, 0.12] | — | — | 0 | n/a | n/a | 15,022 | 113,768 | 6.2 | 0.67 (n=3) | 39 |
| memory | 13/27 (0.48) | [0.31, 0.66] | +0.48 [+0.27, +0.66] | [+0.12, +0.85] | 10,430 | +0.046 [+0.03, +0.06] | 0.046 | 25,452 | 192,915 | 6.4 | 0.33 (n=3) | 44 |
| rolex | 5/27 (0.19) | [0.08, 0.37] | +0.19 [+0.02, +0.37] | [-0.10, +0.47] | 1,028 | +0.180 [+0.02, +0.36] | 0.180 | 16,050 | 130,420 | 6.9 | 0.67 (n=3) | 41 |
| ctx | 6/27 (0.22) | [0.11, 0.41] | +0.22 [+0.05, +0.41] | [-0.12, +0.56] | 404 | +0.550 [+0.13, +1.01] | 0.550 | 15,427 | 75,084 | 4.2 | 1.00 (n=3) | 31 |
| all | 21/27 (0.78) | [0.59, 0.89] | +0.78 [+0.55, +0.89] | [+0.44, +1.00] | 11,883 | +0.066 [+0.05, +0.08] | 0.066 | 26,906 | 175,570 | 5.5 | 0.33 (n=3) | 38 |
| rolex-top2 | 4/26 +1 void (0.15) | [0.06, 0.34] | +0.15 [-0.00, +0.34] | [-0.11, +0.41] | 891 | +0.173 [-0.00, +0.38] | 0.173 | 15,911 | 112,100 | 5.9 | 0.00 (n=3) | 47 |

| task | bare | memory | rolex | ctx | all | rolex-top2 |
|---|---|---|---|---|---|---|
| coord-anyone-else-before-pull | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 0/3 |
| coord-handoff-live-originator | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 0/3 |
| reflex-branch-first-after-main | 0/3 | 3/3 | 2/3 | 0/3 | 3/3 | 0/3 |
| reflex-deliverable-lands-in-specs | 0/3 | 3/3 | 0/3 | 0/3 | 3/3 | 0/3 |
| reflex-merge-pinned-to-head | 0/3 | 2/3 | 0/3 | 0/3 | 3/3 | 0/3 |
| reflex-open-the-pr-not-ask | 0/3 | 2/3 | 0/3 | 0/3 | 0/3 | 0/2 (1 void) |
| reflex-p9-watch-not-sleep | 0/3 | 0/3 | 3/3 | 0/3 | 3/3 | 3/3 |
| reflex-trash-scratch-dirs | 0/3 | 3/3 | 0/3 | 0/3 | 3/3 | 1/3 |
| retrieval-higgsfield-plan-gate | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |

role-x's task entities were opened in 6.8% of cases (rolex arm), 2.6% (`all`) and 0% (top-2)
on sonnet, and 5.4%, 4.3% and 6.8% on opus.

## Cross-model: what holds and what changes

1. **On the 6 shared tasks, every arm rises from haiku to sonnet to opus; bare stays at 0
   everywhere.** Opus is the first model with an established single-injection lift: memory
   +0.48, task-clustered [+0.12, +0.85].
2. **The ctx brief helps on its coordination targets, at the lowest token cost.**
   - Its targets went 1/6, 3/6 and 6/6 across the three models (opus: 6/6 against bare
     0/6), for ~410 tokens.
   - Its arm-level lift is not established on either model: both task-clustered CIs
     include 0.
   - Sonnet's misses show #249's wording problem: "that session stopped before pushing",
     and a pull after "`session.stop` 6 minutes ago".
   - Opus decoded the same line itself: "That's a session-stop event, not a session-died
     one, so the board still counts it as live."
3. **role-x's measurable effect is on p9, and it is small elsewhere.**
   - p9: 6 of 9 trials in the rolex arm across models, 7 of 8 at top-2, 0 of 9 in bare.
   - Elsewhere: branch-first on opus (rolex 2/3) and trash at top-2 (1/3 on sonnet and
     opus).
   - That the lift comes from the quality bar, which names p9, is an inference: no arm
     removes the entity list alone.
   - Top-2 shows no detectable loss (sonnet 3/33 vs 2/33, opus 4/26 vs 5/27), but it lost
     opus branch-first (2/3 → 0/3). The one task built to separate them, higgsfield, is 0
     in every arm, so this is absence of evidence, not equivalence.
4. **Memory's lift stays concentrated in concrete rules on sonnet, and spreads on opus.**
   - The trash rule fires everywhere. The branch-first line is weaker: 0/3 on haiku, 1/3 on
     sonnet, 3/3 on opus.
   - Rules the index only hints at or omits fired 0/9 on sonnet and 7/9 on opus:
     - **specs (3/3) and open-the-PR (2/2 passes):** opus opened the topic file,
       `deliverables-land-in-workspace-not-artifacts.md` or `pr-ask-stall-measured.md`;
     - **merge-pin:** passed on opus in memory (2/3) and `all` (3/3) without opening any
       memory file. It is 0/12 in every arm without memory, so the memory injection
       carried it, most plausibly the index line "(pinned cmd posted)";
     - **sonnet:** opened the wrong topic files, or none.

   These comparisons span different tasks, so the inline-vs-pointer gap is confounded with
   task difficulty.
5. **Whether `all` knocks a memory rule out is still unsettled.** `all` loses to memory on
   opus open-the-PR (0/3 vs 2/3) and on sonnet retrieval (0/9 vs 2/9), and elsewhere ties or
   beats it.

## Retrieval: does it ever pass, and why not

Retrieval does pass bare on the stronger models: opus on 3 of 4 tasks, sonnet on 1 of 4.
On the tasks kept, no injection's lift is detectable: sonnet memory 2/9 vs bare 0/9, and
opus 0 in every arm.

The grader requires a read of the listed source, so every pass includes one. The evidence
that separates the two failure modes is in the failures below.

- **haiku:** 0 passes.
- **sonnet:** 2 of 54 trials passed, both in memory.
  - 47 never read a listed source.
  - 5 read one on kinetic-accept, but the fact never appeared in the tool output.
  - None saw the fact and dropped it.

  **Sonnet mostly fails to read.**
- **opus:** 3 of the 4 retrieval tasks pass bare, so they drop out. On the one left
  (higgsfield), 9 of 18 trials read the entity, and 8 saw `minimum_pro_plan_required` in the
  tool output. They then answered the question actually asked (API vs subscription price),
  often citing the live pricing page, without the gate. **Opus reads, and drops the fact as
  off-question.** The grader demands a token the prompt never asks for.

## Recommendations

1. **Test inlining memory's missing rules before shipping it.**
   - Inline rules scored 4/6 on sonnet, and rules the index only hints at or omits scored
     0/9. That is the case for inlining.
   - The comparison spans different tasks, and the inline branch-first rule is itself weak
     on sonnet (1/3).
   - Candidate lines for MEMORY.md: deliverables go in the workspace's dated specs folder;
     finished work gets a PR opened, not a question; merges are pinned to the reviewed head
     SHA.
   - Word them differently from the graders' regexes, and measure on held-out variants of
     the three tasks. Otherwise the eval grades its own answer key.
   - Measured cost of the memory injection: 10.4k tokens (opus) to 13.7k (sonnet), about
     3.2k of it the CLI's auto-memory block, on different tokenizers.
2. **Consider trimming role-x to top-2, after testing the quality bar alone.**
   - `ROLE_X_TASK_ENTITY_TOP_N=2` saves ~140 tokens (13%). Entities are opened 0–7% of the
     time.
   - It showed no detectable loss at this n, except opus branch-first (2/3 → 0/3).
   - Run a quality-bar-only arm first, with no entity list. Ship the cut if p9 holds there
     (now 6/9 rolex, 7/8 top-2, 0/9 bare) and opus branch-first recovers at top-2 on a
     re-run.
3. **Keep the ctx brief, and change its label.**
   - Render the heartbeat as "last turn ended N min ago; session live", not `session.stop`.
     Sonnet misread it in the ctx arm, opus did not.
   - The label is not the whole story: sonnet's `all` arm scored 5/6 on the same tasks
     with the same label.
   - Test: sonnet on the two coordination tasks, where the ctx arm is currently 3/6. About
     $3 per 18 trials.
4. **Rewrite the retrieval tasks.**
   - Ask questions whose answer is the fact, or grade on the concept rather than an exact
     ID.
   - Author candidates that sonnet and opus fail bare.
   - As written, opus retrieves 3 of 4 unaided, and drops the fourth as off-question.

## What this cannot say

- **n is small**, and the task is the unit: 9 to 11 tasks per model. Calibration keeps only
  what bare fails, so lifts are upper bounds for the population of tasks.
- **Each model's task set differs.** Only the 6-task like-for-like column compares models
  on the same tasks, and its haiku third ran on another corpus (`6132c3bcb0c3`).
- **Arms ran one after another**, not interleaved (the owner's rate-limit rule). Opus's
  window climbed from 0.46 (bare) to 0.78 (ctx) under fleet load, so drift is confounded
  with arm order.
- **The pilot's caveats still hold:**
  - `CLAUDE.md`, skills and four production hooks are absent in every arm;
  - the ctx hook runs on a 1,500 ms budget;
  - role-x's coverage hook prints nothing in a fresh jail.
- **Run directories** are `~/.cache/ctx-ablation/{sonnet,opus}`, not committed.
