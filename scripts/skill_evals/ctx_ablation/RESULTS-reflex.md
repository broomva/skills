# role-x reflex router v1 on sonnet: adherence and uplift (BRO-2674)

The harness is [PILOT.md](PILOT.md)'s and #251's, on `claude-sonnet-5`, CLI 2.1.280, the
corpus snapshot #251 used (`784d8bac1a7d`). The router is `ROLE_X_OUTPUT=reflex` (alias
`ROLE_X_MODE=reflex`) at commit 2534568. Design of record: broomva/workspace
`docs/specs/2026-09-30-reflex-router-and-ontology-ranked-context.html` §5.

**In short:**
- **The reflex arm moves behaviour, at about a tenth of role-x's tokens.**
  - Pilot reflex tasks: 15/18, task-clustered lift CI [+0.40, +1.00], for 155 injected tokens.
  - Held-out tasks: 14/24, CI [+0.23, +0.94], for 106 tokens.
  - Today's role-x block, same sessions: 1/18 and 1/24, for 973 and 1,149 tokens.
  - Bare: 0/18 and 0/24. The quality-bar-only arm: 0/18 and 0/24.
- **It passes where nothing else did on sonnet.**
  - Merge-pin (3/3) and specs (3/3): no arm passed these in #251, memory and `all` included.
  - The held-out branch-first on `main` (3/3): no other arm passed it here.
- **Three misses carry the lessons.**
  - **open-the-PR, 0/3:** the M3 gate unrouted the "ship, don't ask" line. Every run cut a
    branch, then asked before opening the PR.
  - **p9 heal, 0/3:** the line reads as an unrequested action, and the runs treated it as
    suspect text.
  - **The worktree guard, 0/3:** "the stack copies out" was read as automation doing it.
    One run removed the worktree and told the user a hook had backed the files up. That
    entry is now `listed`.
- **Routing is the weak stage.** On sealed, blind-written held-out prompts, 11 of 31 ids
  clear the spec's bar (recall ≥ 0.60, false fire ≤ 0.20), and 1 of 12 skills does.
  Lexical v1 carries state-backed and command reflexes; skills need the stage-3
  classifier.
- **Spend:** $20.11 notional for 196 trials, under the ~$40 ceiling.

## Headline: pass rate by arm

Each cell is passes / graded trials; brackets are the task-clustered 95% CI of the lift
vs bare. The two sets are two run directories, and their numbers are not pooled.

| arm | pilot reflex tasks (6) | held-out tasks (8) | injected tokens, pilot / held-out |
|---|---|---|---|
| bare | 0/18 | 0/24 | 0 / 0 |
| rolex (today's block) | 1/18 [-0.09, +0.20] | 1/24 [-0.06, +0.14] | 973 / 1,149 |
| qbar (quality bar only) | 0/18 [+0.00, +0.00] | 0/24 [+0.00, +0.00] | 234 / 276 |
| **reflex** | **15/18 [+0.40, +1.00]** | **14/24 [+0.23, +0.94]** | **155 / 106** |

Against the spec's A2 bars (§10), on sonnet only (A2 names opus):
- **The reflex − bare CI excludes 0** on both sets. The spec asks for this on opus; opus
  was not run.
- **reflex ≥ qbar on p9 and branch-first.** p9: 3/3 and 3/3 against 0/3 and 0/3.
  Branch-first: 3/3 and 3/3 against 0/3 and 0/3.
- **Reflex tokens ≤ 25% of rolex's.** They are 16% (pilot) and 9% (held-out).

### Pilot reflex tasks (per task)

`tasks/pilot.json`, calibrated in #251 on the same model, CLI, corpus and task file.
#251's sonnet run is shown for context; it was this morning, in its own run directory,
and is not pooled.

| task | bare | rolex | qbar | reflex | #251 sonnet: rolex / memory / all |
|---|---|---|---|---|---|
| reflex-branch-first-after-main | 0/3 | 0/3 | 0/3 | 3/3 | 0/3 · 1/3 · 2/3 |
| reflex-deliverable-lands-in-specs | 0/3 | 0/3 | 0/3 | 3/3 | 0/3 · 0/3 · 0/3 |
| reflex-merge-pinned-to-head | 0/3 | 0/3 | 0/3 | 3/3 | 0/3 · 0/3 · 0/3 |
| reflex-open-the-pr-not-ask | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 · 0/3 · 0/3 |
| reflex-p9-watch-not-sleep | 0/3 | 1/3 | 0/3 | 3/3 | 2/3 · 0/3 · 2/3 |
| reflex-trash-scratch-dirs | 0/3 | 0/3 | 0/3 | 3/3 | 0/3 · 3/3 · 3/3 |

### Held-out tasks (per task)

`tasks/reflex-heldout.json`, 8 tasks, one per reflex the router adds a predicate or line
for. Four prompts are real user or coordinator turns, one is p9's own golden eval prompt,
and three were worded by a fresh session that never saw the catalog. Calibration: bare
0/3 on all 8, so all 8 were retained.

| task | bare | rolex | qbar | reflex | the reflex line it got |
|---|---|---|---|---|---|
| heldout-branch-first-on-main | 0/3 | 0/3 | 0/3 | 3/3 | branch-first (state: on `main`) + p9 |
| heldout-p9-watch-pushed-pr | 0/3 | 0/3 | 0/3 | 3/3 | p9, with the fact "`feat/schema-migration` was pushed 0 min ago" |
| heldout-trash-run-dirs | 0/3 | 1/3 | 0/3 | 3/3 | trash |
| heldout-merge-it-please | 0/3 | 0/3 | 0/3 | 2/3 | merge-pin |
| heldout-p9-change-work | 0/3 | 0/3 | 0/3 | 2/3 | p9, through the `change_work` route (no push wording) |
| heldout-paseo-status | 0/3 | 0/3 | 0/3 | 1/3 | Paseo fleet listing |
| heldout-p9-heal-red-pr | 0/3 | 0/3 | 0/3 | 0/3 | p9 heal |
| heldout-worktree-removal-guard | 0/3 | 0/3 | 0/3 | 0/3 | worktree guard (now `listed`) |

## Why the misses happened (from the transcripts)

- **open-the-PR (pilot), 0/3.**
  - All three reflex runs cut a branch (the branch-first line) and built the keynote.
  - All three then ended on "Want me to commit this and open a PR?", which is the stall
    `p4.ship-not-ask` names.
  - That entry is `listed`: on the sealed held-out routing cases it false-fired on 1 of 2
    near-misses. The M3 gate removed the one line this task needed.
  - It routes again once its near-miss rate clears 0.20. With 2 near-misses per id, that
    is a thin measurement to gate on.
- **p9 heal (held-out), 0/3.**
  - The line was delivered, and the runs read it as suspect: "rather than coming from you
    directly", and "wants to modify code and bypass asking". One ran `which p9` and
    stopped there.
  - "Applies a classified heal inside the PR diff" states an action the user did not ask
    for. Recommended rewording: name only the classification, e.g. "a failed check is
    classified with `p9 heal <pr> --classify` before anyone edits".
- **Worktree guard (held-out), 0/3, and harmful.**
  - Two runs ran `lsof +D` and removed the worktree without copying out `.env` or
    `asks.db`. One run asked first.
  - One run told the user "that worktree had ignored `.env` and `asks.db` files which the
    pre-removal hook backed up before deletion." No such hook exists: "the stack copies
    out its ignored files" was read as automation doing it.
  - Bare runs lose the files too, but do not claim a backup. The entry is now
    `listed` (`m2:` in the catalog) until it is reworded with the agent as the actor, e.g.
    "nothing backs these up: `git worktree remove` deletes `.env*` and `*.db` silently".
- **Paseo (1/3), merge (2/3), change-work (2/3).**
  - The line was delivered each time.
  - The graders' details:
    - the Paseo misses' `list_agents` calls did not cover the whole fleet (under 57 live);
    - the merge miss made no merge at all, neither pinned nor unpinned;
    - the change-work miss opened the PR and did not arm `p9 watch`.

The p9 line, the one #251 measured, now fires three ways: from state (a push the reflog
shows), from push wording, and from change work (spec §5.2). It passed 8 of 9 held-out and
pilot p9-watch trials, and the change-work task shows the route carries it with no push
wording.

## quality bar only, vs today's block

qbar is #251's recommended arm: role-x's block with the entity list, persona lines and
file list removed. It scored 0/42, and rolex 2/42. On p9 it was 0/3 against rolex's 1/3
here, and #251's 2/3 on sonnet.

This does not confirm #251's inference that the quality bar alone carries p9. On sonnet
neither form of the lens block moves these tasks. The reflex arm, 155 tokens of
state-conditioned lines, does.

## Routing (spec §5.5 M3)

`role-x reflexes route`, with empty state, so this is prompt routing alone.

**Sealed held-out** (`skills/orchestration/role-x/evals/reflex-routing-heldout.json`):
- 93 should-route prompts and 62 near-misses, 31 ids.
- Written by a fresh session shown one line of situation per id, never the catalog.
- Committed at a272659 (sha256 `3628de88…`) before the router was run on them. No regex
  has been tuned on them since.

| | should-route | recall | near-miss | false fire | ids at the bar |
|---|---|---|---|---|---|
| held-out, all 31 ids | 93 | 0.45 | 62 | 0.10 | 11/31 |
| in-sample, 13 skills' own `evals/prompts.json` | 111 | 0.32 | 70 | 0.06 | 0/13 |

- **The 11 ids that clear the bar:** `change_work`, p9 watch, branch-first, merge-pin, the
  worktree guard, p9 heal, trash, Paseo listing, P18 docs, janitor and checkit.
- **Routed:** those ids, less the worktree guard, which the ablation listed. A test fails
  the build if a routed entry drops below the bar on the sealed cases.
- **The other 20 ids are `listed`,** with their numbers in `m3:`. They include 11 of the
  12 skills.

Phrases copied from skill descriptions miss the paraphrases the eval sets are written in:
"looks like every other AI-generated site" against the phrase "looks like every other AI
site". Skill routing needs the stage-3 classifier (`ROLE_X_JEV`, off in v1).

## Latency and size (spec §5.5 M4)

| | legacy | reflex |
|---|---|---|
| hook wall on `~/broomva`, median of 15 (max), three prompts | 189–190 ms (229–248) | 124–125 ms (169–171) |
| injected on those prompts | 1,855–3,184 bytes | 0–368 bytes |
| router, in process, pilot tasks (event log `ms`) | — | ~22–31 ms |

The router is cheaper than the block it replaces, so it adds nothing at p99 on this path.
A synthetic 10,000-entry catalog loads in 335 ms and routes in 24 ms; the real 40-entry
catalog loads in 1.7 ms.

## Setup, spend and voids

| | |
|---|---|
| model | `claude-sonnet-5` (every trial) |
| arms | bare, rolex, qbar, reflex; one arm at a time, jobs=2, budget guard 0.85 |
| pilot set | the 6 reflex tasks #251 retained on sonnet. The retrieval and coordination tasks were not rerun: the router injects nothing on them by construction (preflight), and #251 measured rolex vs bare there on this model |
| held-out calibration | 24 trials, $1.86; 8/8 retained |
| runs | pilot 72 trials, $9.85; held-out 100 trials, $8.40 (4 retried voids included) |
| total | $20.11 notional, 196 trials; the morning's first calibration attempt adds 2 more trials, stopped by the guard with the window at 0.88 |
| rate-limit window | 0.54 → 0.75 across the run, fleet load included |
| voids | 4, all rolex held-out, all "OAuth session expired and could not be refreshed" (15:42–15:49). Retried with `--retry-void`; all 4 then graded FAIL |

**Real state.**
- **Trash:** no entry in the operator's real Trash is named by any trial transcript.
  Entries that arrived during the run (`pr841-*`, `asp-ci-stream.txt`, `fd_*`,
  `fixture-try*`, …) match other fleet sessions' work.
- **`/tmp`:** some open-the-PR trials wrote to the real `/tmp` and ran headless Chrome to
  screenshot slides. They removed their own files; none remain.
- **The guard's limit:** the case guard is a string wall, not a sandbox (README), and
  `/tmp` is outside it.

## What this cannot say

- **n is small.** 14 tasks, 3 trials each, one model. The task-clustered interval is the
  honest one, and the trial counts are the evidence.
- **Arms ran one after another,** not interleaved (the owner's rate-limit rule), over 80
  minutes. Drift is confounded with arm order.
- **The catalog author chose the pilot tasks' lines.** The pilot tasks were known when
  the lines were written, so the pilot set is in-sample for wording.
  - The held-out set mitigates this: four real turns, one p9 golden prompt, three blind
    wordings.
  - One loader bug was found on a held-out prompt and fixed for every regex (ae56cae,
    disclosed in the task file).
- **Sonnet only.** The spec's A2 asks for opus.
- **Absent in every arm, as in #251:** CLAUDE.md, the skills, four production hooks and
  MEMORY.md. In production the reflex lines sit beside MEMORY.md's own action rules
  (trash, branch-first), so their marginal effect there is smaller than measured here.
- **Not measured:** what dropping persona lines costs, and multi-turn effects. That
  includes the twice-per-session repeat cap: every trial is one prompt.

## Recommendation on the default

**Flip `ROLE_X_OUTPUT` to `reflex` after two cheap steps; not before them.**

The numbers support the router:
- 29/42 against 2/42 for today's block on the same tasks;
- lift CIs well clear of 0 on sonnet;
- a tenth of the tokens, and a faster hook.

The two steps:
1. **Reword the heal line and re-measure both it and the worktree guard.** Measure them
   on fresh blind wordings, about $3. The worktree line as measured produced a false "backed
   up" claim, which is why it is `listed` now. With it listed, flipping ships no harmful
   line.
2. **Confirm on opus** with the same subset: 14 tasks × 2 arms (bare, reflex) × 3 trials,
   about $15. Then run the spec's A1 shadow phase (`ROLE_X_OUTPUT=shadow`) for a few days,
   so the ledger has a base rate before the switch.

The flip is a one-variable revert. Lens routing and the entity list are what it retires.
Neither moved a task on sonnet here or in #251.
