# Context ablation on stronger models: sonnet-5 and opus-5-5, 2026-09-30

The haiku pilot ([PILOT.md](PILOT.md)) found no established lift; only concrete memory rules
moved anything. This asks whether that holds on `claude-sonnet-5` and `claude-opus-5-5`.
The harness is a82e8ea, unchanged. Same 6 arms and 3 trials; each model recalibrated the
pilot's 13 retained tasks in its own bare arm.

## Setup

| | sonnet | opus |
|---|---|---|
| model resolved | `claude-sonnet-5`, 237/237 trials | `claude-opus-5-5`, 201/201 trials |
| corpus | sha256 `784d8bac1a7d`, 1,863 files, 68 MB | the same snapshot, copied (the live one had moved on) |
| canary preflight | 5/6; the ctx miss was reporting, not delivery (below) | 6/6 |
| calibration | 39 trials, $4.41; **11/13 retained** | 39 trials, $7.22; **9/13 retained** |
| run | 11 × 6 × 3 = 198 trials, $29.65, 1 void | 9 × 6 × 3 = 162 trials, $34.96, 1 void |
| wall, jobs | 06:06–07:36, jobs=2, arms one after another | 07:44–09:14, jobs=2; paused 08:44–08:51 |
| rate-limit window | 0.32 → 0.37 | 0.37 → 0.85: the budget guard stopped `all` mid-arm; resumed after the 08:50 reset |

Notional cost is ~$76 over 438 trials; the canary calls were not metered. The Opus
estimate made before its calibration was $70–80. It came in at $42, because fewer tasks
were retained and a trial cost 1.6× sonnet's, not the 2× list-price ratio.

**Dropped in calibration (they pass bare):**
- **sonnet:** `retrieval-workspace-sync-decision` (3/3), `reflex-paseo-list-agents-fleet` (1/3).
- **opus:** those two (2/3 and 3/3), plus `retrieval-kinetic-accept` (3/3) and
  `retrieval-ci-runner-pool` (2/3).

list_agents was one of memory's two haiku wins; the stronger models do it unaided.

**Delivery.** Every graded trial carries the pilot's four proofs. Memory was verified from
tokens on every memory-arm trial, and no trial was flipped. Sonnet's ctx canary said
"none", so it was re-run twice with the stream kept: the SessionStart `hook_response`
carried the canary both times, and sonnet reported it once. Void trials:
- **sonnet, 1:** handoff in memory; the guard logged 18 of 19 calls.
- **opus, 1:** open-the-pr in rolex-top2, at the 420 s timeout.

**Real state.** No trial changed the operator's real Trash. It was listed before and after
calibration and every arm. New entries did appear during the Opus run, and each traces to
another fleet session; no trial transcript names any of them:
- **08:22:** 9 `kin_*` files. A subagent in Paseo worktree `0t10n7id` ran `trash /tmp/kin_*`.
- **08:54–08:57:** 3 `ccprobe` probe files, from `./probe.sh` sessions driven from worktree
  `0t10n7id-sharp-moth`.
- **Mine, not a trial:** my own `trash` of an unused corpus copy, moved back out at once.

`~/.config/broomva` changes (CI-runner logs, fleet drafts, p9 watches of the real PRs
workspace#837/838 and skills#250) carry no `ctxabl` path. They are live sessions.

## Headline: pass rate by arm (lift vs bare, task-clustered 95% CI)

| arm | haiku (pilot, 10 tasks) | sonnet (11 tasks) | opus (9 tasks) |
|---|---|---|---|
| bare | 0/30 | 0/33 | 0/27 |
| memory | 6/29 [-0.10, +0.50] | 6/32 [-0.03, +0.39] | **13/27 [+0.12, +0.85]** |
| rolex | 1/30 [-0.04, +0.11] | 2/33 [-0.07, +0.20] | 5/27 [-0.10, +0.47] |
| ctx | 1/30 [-0.04, +0.11] | 3/33 [-0.05, +0.24] | 6/27 [-0.12, +0.56] |
| all | 8/30 [-0.00, +0.54] | **12/33 [+0.07, +0.65]** | **21/27 [+0.44, +1.00]** |
| rolex-top2 | 2/29 [-0.13, +0.33] | 3/33 [-0.05, +0.24] | 4/26 [-0.11, +0.41] |

The task sets differ by model: calibration keeps what each model fails bare. The pilot's
corpus was `6132c3bcb0c3`. Read across the rows, never pool them.

## Headline: each injection on the tasks it targets (passes; bare is 0 on every row)

| injection → targets | haiku | sonnet | opus |
|---|---|---|---|
| ctx brief → 2 coordination tasks | 1/6 | 3/6 | **6/6** |
| role-x → p9 watch (rolex / top-2) | 1/3 / 2/2 | 2/3 / 2/3 | **3/3 / 3/3** |
| memory → rules written inline in MEMORY.md as an action (trash, branch-first) | 3/6 | 4/6 | **6/6** |
| memory → rules reachable only through a topic file (merge pin, specs, open-the-PR) | not in pilot | **0/9** | 7/9 |

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

1. **Every injection lifts more on a stronger model, and nothing lifts bare.** Opus is the
   first model with an established single-injection lift: memory +0.48, task-clustered
   [+0.12, +0.85]. `all` is established on sonnet and opus.
2. **The ctx brief works, and it is the cheapest per token.** On its two targets it scores
   1/6, 3/6 and 6/6 across the three models, for ~410 tokens. Its lift per 1k tokens is
   the highest of any arm: +0.22 on sonnet, +0.55 on opus.
   - Sonnet's misses are #249's wording problem, in its own words: "that session stopped
     before pushing", "no agent was reachable", "`stop` 6 minutes ago".
   - Opus decoded the same line itself: "That's a session-stop event, not a session-died
     one, so the board still counts it as live."
3. **role-x's measurable effect is the p9 reflex from its quality bar.**
   - p9: 6 of 9 trials in the rolex arm across models, 7 of 8 at top-2, and 0 of 9 in
     bare.
   - Outside p9, role-x passed only branch-first on opus (2/3), plus trash at top-2
     (1/3 on each model).
   - The 5-entity task list is rarely opened: 0–7% of listed entities. Top-2 matches the
     full block (sonnet 3/33 vs 2/33, opus 4/26 vs 5/27) at 13–14% fewer tokens.
4. **Memory's lift stays concentrated in concrete rules on sonnet, and spreads on opus.**
   - Rules written in the index as a literal action fire on every model.
   - Rules the index only points at fired 0/9 on sonnet and 7/9 on opus. Opus opened the
     topic file: every specs pass read `deliverables-land-in-workspace-not-artifacts.md`,
     and the open-the-PR passes read `pr-ask-stall-measured.md`. Sonnet opened unrelated
     arcs, or none.
5. **Whether `all` knocks a memory rule out is still unsettled.** `all` loses where memory
   wins on opus open-the-PR (0/3 vs 2/3) and on sonnet retrieval (0/6 vs 2/6), and it wins
   everywhere else.

## Retrieval: does it ever pass, and why not

- **haiku:** 0 passes.
- **sonnet:** 2 of 54 retrieval trials, both in memory, both after reading a listed source
  and seeing the fact. 45 of 54 never read a listed source, and no trial saw the fact and
  then dropped it. **Sonnet fails to read.**
- **opus:** finds 3 of the 4 retrieval facts unaided, which makes those tasks vacuous. On
  the one left (higgsfield), 9 of 18 trials read the entity and 8 saw
  `minimum_pro_plan_required` in the tool output. They then answered the question actually
  asked (API vs subscription price), often citing the live pricing page, without the
  gate. **Opus reads and drops the fact as off-question.** That is partly the grader: it
  demands a token the prompt never asks for.

## Recommendations

1. **Rewrite memory's pointer-only rules as inline actions in MEMORY.md.** Inline rules
   scored 4/6 on sonnet and 6/6 on opus; pointer-only rules scored 0/9 and 7/9. Sonnet
   ignores pointers, so an inline line makes a rule work regardless of model. Three lines,
   each ~25 tokens:
   - "Deliverables go in `docs/specs/YYYY-MM-DD-<slug>.html` in the workspace";
   - "Finished work: push and `gh pr create`; never ask 'open a PR?'";
   - "Merge with `gh pr merge <n> --match-head-commit <sha>`".

   The index costs 10.4k tokens (opus) to 13.7k (sonnet) per session, for +0.014 to +0.046
   lift per 1k tokens. Shrinking the status/arc lines is the next test, not a finding.
2. **Trim role-x to its quality bar and a top-2 entity list.**
   - Set `ROLE_X_TASK_ENTITY_TOP_N` to 2: top-2 matched the full block on pass rate, and
     entities are opened 0–7% of the time.
   - Keep the quality bar: it is the p9 lift (6 or 7 of 9 across models, against 0 of 9
     bare).
3. **Keep the ctx brief, and change its label.** Render the heartbeat as "last turn ended N
   min ago; session live", not `session.stop`. Sonnet misread it, opus did not.
   - Test: sonnet on the two coordination tasks, where the ctx arm is currently 3/6.
     About $2 per 18 trials.
4. **Fix the retrieval tasks before measuring retrieval again.**
   - Opus makes 3 of 4 vacuous. On the fourth, it reads the fact and drops it as
     off-question.
   - Ask questions whose answer is the fact, or grade on the concept rather than an
     exact ID.
   - Author harder retrieval candidates.

## What this cannot say

- n is small, and the task is the unit: 9 to 11 tasks per model. Calibration keeps only
  what bare fails, so lifts are upper bounds for the population of tasks.
- Arms ran one after another, not interleaved (the owner's rate-limit rule), so any drift
  over ~90 minutes is confounded with arm order.
- Held absent in every arm, as in the pilot: `CLAUDE.md`, skills, four production hooks.
- Run directories are `~/.cache/ctx-ablation/{sonnet,opus}`, not committed.
