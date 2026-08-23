---
name: cross-review
tier: D
primitive: P20
category: governance
description: "bstack P20 — Cross-Model Adversarial Review Gate. The model that wrote the code cannot be the final judge of the code. Before substantive PRs merge, fire a cross-model adversarial gate — different evaluator than writer, anti-slop scoring ≥7/10, a dynamic round budget (3 free, 4-7 earned by a continuation verdict carrying a falsifiable prediction, >=8 human), verdict logged in PR. Three strata: (A) Codex CLI cross-vendor for true different-model verdict, (B) fresh-context subagent under devils-advocate brief, (C) composed existing adversarial-review skills always parallel. Use cross-review when: (1) about to push a substantive PR (>200 LOC OR public API OR multi-file OR governance-class), (2) reviewing a draft plan/design before implementation, (3) auditing a feature spec against single-model blind spots, (4) integrating with the /autonomous skill's pre-push gate. Triggers on 'cross-review', 'P20', 'adversarial review', 'anti-slop', 'cross-model gate', 'different evaluator', 'devils advocate gate', 'self-review prohibition'."
---

# cross-review — bstack P20 Cross-Model Adversarial Review Gate

**The writer cannot be the final judge of the work.**

When the same AI model plans, implements, and reviews, it will not challenge its own assumptions. It has systematic blind spots baked into its training. A different model — trained differently, with different biases and pattern preferences — catches what the first one misses.

`cross-review` is the bstack gate that enforces this discipline. Substantive PRs cannot merge until a *different evaluator* than the writer scores the work ≥ 7/10 against an anti-slop rubric.

## Origin

Inspired by [Dallionking/cross-model-agents](https://github.com/Dallionking/cross-model-agents) (May 2026) — 31-agent bidirectional Claude↔Codex review system. That project ships specific agents and hooks. `broomva/cross-review` absorbs the *discipline* while composing with the existing bstack adversarial-review skill toolkit.

## The 3 strata

Different mechanisms for different environments. The *substance* is the gate — what mechanism implements it is secondary.

| Strata | Mechanism | When | Strength |
|---|---|---|---|
| **A — True cross-vendor** | `codex exec -m gpt-5.4` (or similar) reads the diff and scores | Codex CLI installed | Strongest — different weights, different training, genuinely different blind spots |
| **B — Cross-context same-model** | Fresh `Agent` subagent under devil's-advocate brief reads diff and scores | Always available | Weaker than (A) but still strong — fresh context + adversarial framing breaks within-conversation echo |
| **C — Composed existing skills** | Dispatch `superpowers:constructive-dissent`, `devils-advocate`, `pr-review-toolkit:*`, `critique`, `premortem`, `plan-design-review`, `plan-ceo-review`, `plan-eng-review` — each fires a domain-specific lens | Always | Toolkit P20 makes mandatory — adversarial-review-by-composition |

**Default**: invoke Strata A if Codex available, fall back to Strata B, always run Strata C in parallel.

## The anti-slop rubric

Cross-model-agents' core insight is *scoring* not just *reviewing*. The reviewer assigns a numeric score (1-10) against a rubric:

```
ANTI-SLOP RUBRIC (10 points total)

  2 pts — No over-engineered abstractions
          (no unnecessary wrappers, no premature generalization,
           no abstraction layers without ≥3 concrete consumers)

  2 pts — No template-paste patterns
          (no copy-paste from training data without adaptation,
           no boilerplate that doesn't carry intent,
           no scaffolding without invariant)

  2 pts — Correct contracts at boundaries
          (typed I/O, validated inputs, explicit error modes,
           no silent failures, no implicit conversions)

  2 pts — Failure modes named explicitly
          (what happens on bad input, network fail, race condition,
           empty state, very large input, concurrent access)

  2 pts — Tests cover the change
          (unit/integration/E2E proportional to change shape;
           coverage matches what the change introduces;
           no critical path untested)

PASS: ≥7/10
LOOP: <7 → fix the specific deductions → rescore
BUDGET: 3 free rounds · 4-7 earned by a continuation verdict · ≥8 human
ESCALATE: STOP verdict, two refuted predictions, a score regression, or round 8
```

### The round budget is dynamic

The old rule was `max 3 rounds`, and it was enforced nowhere — `pre-push` printed
the number and nothing read it. Practice ran past it routinely (BRO-2190 to 21
rounds, BRO-2185 to 22, BRO-2079 to 12 and closed unmerged) while the live rule
was an *unwritten* controller reconstructed from memory each arc.

**Score slope is the wrong signal.** BRO-2185 sat at 5-6 for eighteen consecutive
rounds, then moved 6→8 in one round once the invariant was hoisted; a plateau-stop
kills it at ~round 4 and discards the arc that eventually passed. BRO-2079 ran
twelve rounds on an equally flat score and closed unmerged. Same slope, opposite
correct answer.

**The currency is a reproduced, executable defect in the change** — not a score
bump, not reviewer opinion, and never a finding about the *justification* for the
change. Track it with `cross-review round`:

```bash
cross-review round record-round   --run-id=$ID --score=5 --defect=yes
cross-review round budget         --run-id=$ID    # exit 0 authorized, 5 review-required,
                                                  # 6 stop, 7 human, 3 passed
cross-review round record-verdict --run-id=$ID --verdict=CONTINUE \
    --prediction="unhandled empty-input branch in parse_args at scripts/foo.sh:88"
```

### The continuation review brief

Rounds 4-7 are earned, one at a time, by a review of **the decision to continue** —
not of the diff. The orchestrator's "one more round because…" is the prose that has
never been adversarially read, and justification is reliably the weakest part of any
change.

Dispatch it read-only, same as any stratum. Its input is the round ledger
(`cross-review round show`), the **last fix's diff only**, and the orchestrator's
stated rationale. Mandate this template verbatim:

```
The default is STOP. The burden is on continuation.

VERDICT: CONTINUE | STOP | STRUCTURAL
  CONTINUE   — requires a PREDICTION: the defect class AND location the next
               round should surface, and why the last N rounds did not find it.
               The next round settles it CONFIRMED or REFUTED.
  STRUCTURAL — another fix round is the wrong move. Name the directive:
               hoist the invariant | delete the justification | cut the gate |
               close unmerged.
  STOP       — the artifact is defective or the surface is exhausted.
CONFIDENCE: and the ONE thing that would flip this verdict.
```

`STRUCTURAL` is a verdict, not a regex. The ledger *proposes* the shape ("this
defect class has now appeared at three distinct locations"); the reviewer
*disposes*. It is how eighteen rounds of chasing the same defect into a new branch
each time collapse into one directive.

**Why this is not a rubber stamp.** "Should I extend?" asked cold answers *yes*
almost always, and a second model rubber-stamping it is worse than the fixed
counter it replaces — it launders the writer's appetite through something that
looks independent. Four rules are checked by `round-budget.sh` against the
ledger, so they do not depend on the agent recalling them correctly — see
*What this enforces, and what it does not* below for the boundary:

1. `CONTINUE` requires a non-empty prediction. A continuation that cannot be
   refuted is an opinion, not a verdict.
2. A round following `CONTINUE` must settle it. Otherwise rule 3 can never fire.
3. Two consecutive `REFUTED` predictions stop the loop — no override.
4. `CONTINUE` verdicts cannot stack without an intervening round.

The ceiling at round 8 is deliberate and is not timidity: an agent that grants
itself unbounded budget by asking itself has begun acquiring its own resources,
and the workspace leaves that pillar open **by design**.

### What this enforces, and what it does not

The first version of this section claimed the four rules were "enforced by the
recorder, not by the agent's discipline." Two independent reviewers showed that
was false, and both were right: every rule yielded to a short sequence of
*legal* commands. The rules are now genuinely enforced against the ledger — and
the honest statement of the boundary is part of the mechanism, not a caveat
appended to it.

**Enforced, and mutation-proved:**

| Property | Why it holds |
|---|---|
| A stop cannot be cleared by appending | every stop is computed over the WHOLE history and is absorbing — a later `CONFIRMED` round does not clear two `REFUTED`, and **a round claiming a passing score clears nothing**: stops are checked before `PASSED`, because the score is the agent's own self-report and a stop that costs one integer to escape is not a stop. `record-round` also refuses to append past a terminal state |
| A budget cannot be reset by re-running `pre-push` | the ledger id is derived from branch + merge-base, not the PID |
| Pointing at a new file is not a *casual* reset | `--ledger` is gated behind `ROUND_BUDGET_TEST_LEDGER`, so it is no longer an undocumented flag that silently resets a budget. It is **not** a barrier — see *not enforced* below |
| An unparsable ledger cannot authorize | malformed scores, unknown verdict tokens, and unreadable files all fail CLOSED |
| A `CONTINUE` cannot be empty of content | the prediction must name a location the next round can check |
| The arithmetic is not from recall | the round count and score series come from a file, which is the thing agents do worst from memory |

**NOT enforced — the bypasses, stated rather than implied:**

- **Nothing compels the agent to call `budget` at all.** `pre-push` prints the
  command; it cannot run the loop on the agent's behalf. This is the same shape
  as the defect it replaces — the old bound was a number no conditional read;
  this one is a conditional no caller is *required* to run — and pretending
  otherwise would repeat the original mistake one level up.
- **The ledger is not a security boundary.** It is a plain file under `.git/`.
  An agent determined to evade it can edit or delete it. It is bookkeeping that
  makes drift *visible*, not a control that makes drift impossible.
- **`--defect=yes` is the agent's own assertion.** The controller enforces that
  two consecutive `no` rounds stop the arc; it cannot verify that a `yes` was
  actually earned. That judgement belongs to the reviewer's findings.
- **One environment variable reopens the ledger path.**
  `ROUND_BUDGET_TEST_LEDGER=1 … --ledger=/tmp/fresh` starts a clean budget. The
  gate makes that a deliberate act rather than an accident; it does not prevent
  it, and nothing here could — see the first bullet.
- **"Names a location" is a weak check.** The predicate accepts any path-ish
  token, so `aaaa/aaaaaaa` passes. It rules out `--prediction=x`, which is the
  failure that actually occurred; it cannot tell a real location from a
  plausible-looking one.
- **The ledger is invisible to CI.** It lives in `.git/`, so no workflow can see
  whether an arc ever ran the loop. Paste `cross-review round show` into the PR
  alongside the verdict — that is what makes the budget part of the merge
  artifact rather than a private note.

The value is real but bounded: it removes the *accidental* drift — the miscounted
round, the stop quietly walked back, the budget reset by a re-invocation — which
is what actually went wrong across the arcs that ran to 12, 21, and 22 rounds. It
does not, and cannot, bind an agent that has decided to evade it.

The rubric is *concrete* and *machine-applicable* — every deduction names a specific failure category, not a vague "could be better."

## Mutation-proof — the one rubric dimension a machine can check

Four of the five rubric dimensions are judgement calls. The fifth — *tests cover the change* — is not. It has an operational definition:

> **A test covers a change iff neutering the change turns the test red.**

`scripts/mutation-proof.sh` runs that experiment. It copies the tree to a scratch dir under `mktemp`, neuters the target **in the copy**, and re-runs the test command with `cwd` set to the copy. The working tree is never touched.

```
green before + RED after   → PROVEN. The test discriminates.
green before + GREEN after → UNPROVEN. The test is decoration with respect
                             to that target. That is the finding.
not green before           → INCONCLUSIVE. Nothing can be proven about a
                             test that does not pass to begin with.
```

Three further shapes resolve to INCONCLUSIVE rather than a verdict, because in each the experiment did not happen:

- **The mutation changed nothing.** `--ref HEAD~1` when the file last changed earlier leaves it byte-identical, and the suite never ran without the code. Reported with the ref named.
- **The mutated run emitted fewer checks than the baseline while exiting 0.** It did not pass; it did not run.
- **The runner aborted before reaching a verdict.** Setup failures exit 2, never 1 — borrowing the UNPROVEN code would report "your test is decoration" when the truth is "the runner fell over".

A **symlinked target is refused outright**: `cat >` follows a link, so mutating one writes through it into the real file, which may sit outside `--root` and would not be restored. Point `--target` at the real file.

Two further containment properties, because a leaf check taken before the test command runs is not enough. **The tree is re-copied before every target**, so one target's test cannot leave the tree — or a swapped-in symlink — behind for the next; and **containment is re-asserted at the moment of every write**, resolving the parent chain physically rather than trusting the snapshot taken at argument-resolution time.

```bash
# neuter a script and see whether the suite notices
mutation-proof run \
  --target scripts/control-gate-hook.sh \
  --test 'python3 scripts/test_hook_gates.py'

# prove a fix against its own pre-fix state
mutation-proof run \
  --target src/gate.sh \
  --test 'bash t/run.sh' \
  --strategy revert --ref HEAD~1
```

| Strategy | Mutation | Use for |
|---|---|---|
| `stub` (default) | Replaces the target with a trivially-succeeding no-op for its type — for shell, `return 0 2>/dev/null \|\| true; exit 0`, which is inert when the file is *sourced* and exits 0 when executed; a `main()` returning 0 for python; `process.exit(0)` for node. Type from extension, then shebang; an unrecognised type is an error, not a guess. | "Does this suite test this file at all?" |
| `revert` | `git show <ref>:<path>` restores the pre-fix content. A file absent at that ref is deleted, because absence *is* the pre-fix state. | "Does this test prove *this fix*?" |

Exit codes: `0` PROVEN · `1` UNPROVEN · `2` usage/setup error · `3` INCONCLUSIVE. Each mutation also emits one parseable line: `mutation-proof: verdict=… target=… rc_before=… rc_after=… flipped=…`.

**On the flip count.** When both runs emit per-check markers *and* the suite ran the same number of checks, the report names how many flipped ok→FAIL. When the output is not parseable, or the suite aborted early so the shapes differ, it says so and reports exit codes only. An invented count would be exactly the decorative signal this tool exists to catch.

### Emitting a probe receipt for unhobble

`unhobble --probe-receipts` answers "has this mechanism been demonstrated to fire?" from a recorded receipt with three legs — `fires_on_trigger`, `silent_on_non_trigger`, `neutered_check_went_red` — and reads `fires` only when all three are `true`. It cannot verify a receipt: it does `all(rec.get(leg) is True …)`, so hand-written `true`s buy a free-to-delete verdict. That is a gate whose producer can trivially satisfy it.

This runner performs the third leg for real, so it can record it from an observation instead of an assertion:

```bash
mutation-proof run --target scripts/gate.sh --test 'bash tests/gate.test.sh' \
  --emit-receipt probes.json
```

```json
{
  "probes": {
    "scripts/gate.sh": {
      "neutered_check_went_red": true,
      "evidence": {
        "producer": "mutation-proof v0.0.1 (broomva/skills cross-review)",
        "legs_observed": ["neutered_check_went_red"],
        "legs_not_observed": ["fires_on_trigger", "silent_on_non_trigger"],
        "exit_code_baseline": 0, "exit_code_mutated": 1, "checks_flipped": 3
      }
    }
  }
}
```

**It writes one leg and only one leg.** The other two describe trigger behaviour this runner never exercises, so they are left *absent* and unhobble reads the receipt as `incomplete`. Defaulting them to `true` for a tidier verdict would forge two untested legs — the identical defect one level up. An honest `incomplete` is the correct output.

**Evidence is leg-scoped, and that is not cosmetic.** unhobble's `shows_evidence` is per-*record*: `bool(str(rec.get("evidence") or "").strip())`. A top-level `evidence` key would star the whole record as evidenced, silently upgrading a hand-written bare `yes*` to `yes` — this runner's honest observation acting as cover for two unevidenced claims. Verified by execution against BRO-2035: the top-level shape yields `yes`, the leg-scoped shape preserves `yes*`. When merging onto legs asserted `true` with nothing behind them, the runner says so on stderr.

**What the receipt cannot do yet.** With one leg of three, `probe_state` returns `incomplete` whether the verdict was PROVEN, UNPROVEN, or absent — so `--emit-receipt` cannot presently move a consumer verdict in either direction. What it guarantees today is that it never *falsely* moves one. Per-leg consumption is BRO-2035's side of the contract.

Three distinctions the emitter keeps:

- `neutered_check_went_red: false` is **written**, not omitted. "I ran it and the check did not go red" is a finding; "I did not run it" is a gap. They must not look alike.
- An INCONCLUSIVE run writes **nothing**. Nothing was observed, so there is nothing to claim.
- Merging preserves legs recorded by other producers, and a file that is not a receipt is refused rather than overwritten.

**Scope is mandatory for the receipt to name anything.** unhobble's verdict is per *rule*, and a receipt with no `covers` reads as `unscoped`: it names no rule and promotes nothing, deliberately — probing one branch of one mechanism must not license deleting every rule that happens to cite that mechanism. Pass `--covers 'Section Heading'` (repeatable, comma-separated accepted) to scope it; without it the runner says so on stdout rather than claiming otherwise. Scoping makes the receipt *addressable*, not promoting: one leg of three still cannot reach `fires`.

Keying: unhobble keys a probe by the backticked reference *as written in the audited prose*, resolved against its `--repo-root`. The default key here is the target's path under `--root`, which is that same string whenever the two roots agree. When the prose refers to a mechanism differently — a user-scope `~/.claude/...` ref, say — pass `--receipt-key` rather than letting the runner guess at a normalisation.

This is a reporting flag, not a dependency: nothing here imports unhobble or reads its schema back. The receipt is still a file an agent could hand-write; what changes is that an honest path now exists, and a receipt that shows its exit codes can be audited by a reader instead of taken on faith.

### Why this exists

"Every fix mutation-proven" was a P20 discipline that lived only in prose and memory. Per the workspace invariant, *a phrase that recurs as a discipline must map to a concrete machine-checkable behavior, or it is not discipline.*

In the BRO-2019 hook-gate audit the step caught two things nothing else did:

1. **Five path-shape tests that passed identically with and without the fix.** They exercised the branch where `Path.resolve()` normalises for free, not the branch that carried the defect. Green, and testing nothing.
2. **Three control-gate checks that passed against an `exit 0` stub** — because "empty stdout + rc 0" is indistinguishable from a dead script.

It also produced the positive evidence for every fix in that work: reverting the casefold failed 4 checks, the suffix match 3, the advisory-continue 1, the G3 pattern 7, `replace_all` 1, `surrogateescape` 1.

### On pre-push it is a REPORTED SIGNAL, not a gate

```bash
cross-review pre-push \
  --mutation-target=scripts/foo.sh \
  --mutation-test='bash tests/foo.test.sh'
```

`pre-push` prints the verdict and **does not change its own exit code**, whatever the verdict is. That is deliberate on first landing: the false-positive rate on real repositories is not yet known, and a gate that blocks pushes on an unmeasured signal trains people to bypass gates. An UNPROVEN verdict is information the reviewer must answer — fix the test, or state in the PR why the coverage lives elsewhere — not an automatic stop.

Promoting it to a blocking gate is a later decision, and it needs evidence: a measured false-positive rate across real repos, gathered from the reported signal. When no `--mutation-target` is given, `pre-push` says so explicitly rather than staying silent, because "the signal did not run" and "the signal passed" must never look alike.

## Taking the reviewer's hands away

**The gate keeps its authority. The reviewer loses its hands — as far as the
harness allows, which is further for Codex than for a subagent.**

A reviewer that can edit the tree does not report findings — it fixes them. And a
finding that was silently fixed is indistinguishable from one that was never
found, which makes the score meaningless in exactly the direction that flatters
the writer. The audit's job is to produce an honest verdict; the moment it can
close its own findings it starts optimising for a clean report instead.

This was a real hole here, not a hypothetical: Strata B used to be dispatched as
`subagent_type='general-purpose'`, which carries `Tools: *` — full `Edit`/`Write`.
Strata A invoked `codex exec` unsandboxed, which can patch the tree just as
easily. The stronger stratum had the same defect as the weaker one.

Two layers, because **a prose instruction is not a capability** — and the two
strata are not equally strong, which matters more than it first looks:

| Layer | Mechanism | What it actually buys |
|---|---|---|
| 1a — Strata A | `codex exec -c sandbox_mode=read-only` | A real sandbox. The process cannot write, full stop |
| 1b — Strata B | `subagent_type='Explore'` — every tool **except** `Edit`/`Write`/`NotebookEdit` | **Reduced, not removed.** `Explore` still has `Bash`, and a shell can write. It is instructed not to; that is a disposition, not a wall |
| 2 — detector | `reviewer-guard capture` / `verify` | For Strata A, corroboration. For Strata B, **the only thing standing between a shell redirect and an unnoticed edit** |

**Do not read layer 1b as "the reviewer cannot write."** It removes the ergonomic
path — the tools a reviewer would naturally reach for — and leaves a deliberate
one open. Against a reviewer that is *drifting* (fixing because fixing is what it
does) that is enough. Against one that has decided to write, it is not, and the
fingerprint is what catches it. Stating this the other way round would be the
same error this section exists to name: describing a disposition as a capability.

The asymmetry has a practical consequence: **prefer Strata A when Codex is
available**, not only because a different vendor has different blind spots, but
because it is the only stratum where "cannot write" is literally true.

```bash
cross-review reviewer-guard capture     # fingerprint before dispatch
# ...run the review...
cross-review reviewer-guard verify      # exit 4 = REVIEW INVALID
```

The fingerprint is `git status --porcelain -uall`, plus `git diff HEAD`, plus a
hash of the **contents** of every untracked file. All three are load-bearing:
`status` lists untracked *paths* but says nothing about their bytes, and `git
diff HEAD` does not see untracked files at all — so without the third, a reviewer
editing a file that was already untracked at capture was invisible to both. `core.fsmonitor`
is forced **off** for both: this repo family sets `core.fsmonitor=true`, and a
dead daemon makes `git status` report a clean tree while files are modified,
which would turn the detector into a rubber stamp precisely when it matters.

**What this does not detect.** The guard compares two snapshots, so it sees writes
that **persist**. It does not see: a write made and reverted inside the review; a
write outside this worktree; or a reviewer that overwrites the baseline file
itself. It is corroboration that layer 1 held, not proof — **layer 1, the
read-only tool set, is the actual control.** A guard described as proof would
license dropping the tool-set restriction, which is the only part that cannot be
worked around. Everything it *does* catch, it fails closed on: if `git` errors, or
the baseline is missing or empty, the verdict is *unverifiable* (exit 4), never
*clean*.

**Exit 4 is REVIEW INVALID, and it is not a low score.** A verdict produced by a
reviewer that edited the tree is *no verdict at all* — discard it, revert the
writes, re-run. Missing baseline is also exit 4: "I never captured" and "nothing
changed" must never look alike.

**Fix rounds belong to the writer.** The `<7 → fix → rescore` loop is the
*writer's* work. The reviewer scores, hands back, and touches nothing.

### Why P20 still blocks

The upstream framing of this idea (dzhng's `audit-choices`) says the audit "never
blocks". That is right for an *audit* and wrong for a *gate*, and they are
different objects. P20 is a merge gate: it stays blocking at <7/10. What changes
is the reviewer's capability, not the gate's authority — the same split bstack
already holds as `out-of-band-observer-in-band-gate`: **non-writable observer,
authority elsewhere.** Adopting "never blocks" wholesale would have strictly
weakened P20.

## Invocation patterns

### Pattern 1: pre-push gate (the canonical use)

```bash
# Substantive PR ready, about to push
cross-review pre-push \
  --diff-base origin/main \
  --strata auto \
  --rubric anti-slop
```

`--max-rounds` is **retired** and now exits 2. It was accepted and ignored for its
whole life; continuing to accept it silently would reproduce the defect the dynamic
budget removes. Drive the loop with `cross-review round` instead.

Returns:
- Exit code 0 if verdict ≥ 7
- Exit code 2 on a usage error (including the retired `--max-rounds`)
- Exit code 4 if the reviewer wrote to the tree — REVIEW INVALID, not a low score
- Stdout: the verdict + reasoning, formatted as a PR comment

Between rounds, `cross-review round budget --run-id=$ID` answers whether another
one may run: 0 authorized · 3 passed · 5 continuation review required · 6 stop ·
7 human.

Agent's job: capture the output, paste into PR description or comment, only push after exit 0.

### Pattern 2: plan-stage gate (catch slop before code is written)

```bash
cross-review plan \
  --spec docs/specs/2026-05-XX-feature.md \
  --strata C \
  --skills plan-design-review,plan-ceo-review,plan-eng-review
```

Same rubric, applied to the spec instead of the diff. Use when the work shape is genuinely substantive and the cost of fixing post-implementation would be high.

### Pattern 3: audit-on-demand (no PR context)

```bash
cross-review audit \
  --target apps/api/src/auth/ \
  --concerns security,owasp-top-10 \
  --strata A
```

Used outside the PR flow — e.g., when investigating a class of issues across an existing codebase. Strata A (cross-vendor) is the default here because audit lacks the pre-merge time pressure that makes Strata B useful.

## Composition with bstack primitives

| Primitive | Composition role |
|---|---|
| **P4** PR Pipeline | P20 fires *before* P4 auto-merge — verdict + reasoning are part of the PR artifact |
| **P7** CI Watcher (`broomva/p9`) | After P20 passes + PR is pushed, P7 watches CI; the two gates are sequential (P20 quality → P7 CI green) |
| **P11** Empirical Feedback | Different dimension: P11 is "does it run" (interaction); P20 is "is it well-built" (review). Both fire pre-merge; both are mandatory for substantive work |
| **P17** Lens-Routed Articulation | P17 lenses become P20 evaluator stances (security lens → security audit, frontend lens → UI critique, etc.) |
| **P18** Format-Follows-Audience | P20 verdict is *agent-readable* (machine-parseable rubric output) AND *human-readable* (the PR comment); markdown is correct |
| **P19** Mechanism Selection | A P20-gated PR is naturally a `/goal` arc: condition = "verdict ≥7 logged in PR AND PR merged" |

## Reflexive Trigger Rule (binding on every agent)

P20 (this skill) is a reflex, not a request. Agents must apply the following without being prompted:

1. **Before pushing any substantive PR** — fire `cross-review pre-push`. State the strata + score in the response.
1b. **When the PR claims test coverage for a fix** — mutation-prove it. "I added a test" is a claim; `verdict=PROVEN` is evidence. Report the verdict either way; UNPROVEN does not block, it obliges an answer.
2. **When verdict < 7** — apply the specific fixes the rubric flagged, rescore, and record the round: `cross-review round record-round --run-id=$ID --score=N --defect=yes|no`. Ask `cross-review round budget` before starting another; past round 3 it will require a continuation verdict.
2b. **When the budget returns REVIEW-REQUIRED (exit 5)** — run the continuation review on *the decision to continue*, against a STOP default. `CONTINUE` obliges a falsifiable prediction that the next round settles; two refuted in a row end the loop regardless of score.
3. **When the writer is the only model in the loop** — STOP. Strata B at minimum is mandatory.
4. **When tempted to skip "this PR is small enough"** — apply the substantive-threshold test (>200 LOC OR public API OR multi-file OR governance-class).
5. **When P20 verdict and CI verdict disagree** — P20 is the *quality* gate; CI is the *correctness* gate. Both must pass. P20 cannot override CI; CI cannot substitute for P20.

## Cardinal rule

> The cross-review gate is not optional theater. Single-model echo chambers are real and observable in the diff output of every agent-implemented PR. P20 names the gate that makes the existing adversarial-review skill toolkit mandatory — invocation is not a question; it's a reflex.

## Anti-rationalizations

| Excuse | Reality |
|---|---|
| "I already self-reviewed; it's good" | Self-review by the writing model is forbidden as the *sole* verdict. Same-model echo chamber. |
| "This PR is small — gate is overhead" | Threshold is *substantive* (>200 LOC OR public API OR multi-file OR governance). If your PR crosses ANY of those, P20 fires. |
| "CodeRabbit + claude-review already reviewed it" | Those are external gates that catch *specific patterns*. P20 is *additional* — the writer's own attempt must face a fresh-context adversarial verdict before merge, not just rubber-stamp validators. |
| "We don't have Codex installed — P20 doesn't apply" | Strata B (fresh subagent) + Strata C (composed skills) are always available. The substance is the gate, not the vendor pair. |
| "The Haiku evaluator in /goal already judges quality" | `/goal` evaluates *condition met*, not *work quality*. Different gate. |
| "It scored 6/10 but the work is fine — let me push anyway" | Threshold is ≥7. <7 → fix, rescore, ask the budget. Don't push override. |
| "The reviewer said one more round seems reasonable" | That is the vacuous yes. A `CONTINUE` without a falsifiable prediction is refused by `round-budget.sh` at record time, because a verdict that cannot be wrong is not a verdict. |
| "The score is flat but each round finds something real — keep going" | Check the *shape* first. Same defect class at a new location each round is `STRUCTURAL`: hoist the invariant instead of taking another swing. Eighteen rounds of BRO-2185 were this. |
| "We are at round 9 but the last verdict said CONTINUE" | The ceiling overrides every verdict. Escalate through the handback contract with the ledger attached. |
| "The reviewer noticed a small thing and just fixed it — that's efficient" | Then the finding never existed. A reviewer that writes is optimising for a clean report. Dispatch it read-only; `reviewer-guard verify` exits 4 if it wrote. |
| "I told the subagent not to edit anything" | A prose instruction is not a capability. `general-purpose` carries `Tools: *`; use `Explore`. The brief is layer 2, the tool set is layer 1. |
| "Codex is a different vendor, the sandbox is belt-and-braces" | Different weights, same hands. `codex exec` unsandboxed patches the tree as readily as a subagent — pin `-c sandbox_mode=read-only`. |
| "dzhng's audit never blocks, so P20 shouldn't either" | Audit ≠ gate. Make the *reviewer* non-writing; keep the *gate* blocking. Conflating them weakens the merge bar on an external project's say-so. |
| "The tests are green, so dimension 5 is satisfied" | Green proves the suite ran, not that it watches the code you changed. Delete the code and re-run: if it stays green, the test is decoration. `mutation-proof run --target … --test …`. |

## Red flags — STOP if you catch yourself

- About to push without firing the gate → STOP, run `cross-review pre-push`
- About to merge with verdict <7 → STOP, fix or escalate
- About to use only "I reviewed it" as the verdict → STOP, fire Strata B at minimum
- About to skip the rubric because "the score doesn't matter, I see the work is good" → STOP, the score is the contract
- About to dispatch a reviewer with a writable tool set → STOP, `Explore` (or `sandbox_mode=read-only`), never `general-purpose`
- About to accept a verdict without `reviewer-guard verify` → STOP, an unverifiable review is not a passed review
- About to let the reviewer apply its own findings → STOP, fix rounds are the writer's

## Implementation

`scripts/cross-review.sh` — the entry point. Auto-detects Codex availability (Strata A), falls back to subagent dispatch (Strata B), always runs composed adversarial skills (Strata C).

`scripts/mutation-proof.sh` — the mutation-proof runner. The only part of the rubric this repo executes rather than describes.

See [`scripts/cross-review.sh`](./scripts/cross-review.sh) and [`scripts/mutation-proof.sh`](./scripts/mutation-proof.sh) for the implementations + [`references/rubric.md`](./references/rubric.md) for the full rubric definition + [`tests/`](./tests/) for the verification battery.

`tests/mutation-proof.test.sh` includes the self-referential case: it stubs `mutation-proof.sh` and requires its own suite to go red. A mutation-proof runner whose tests pass against a stubbed runner would be the exact defect it exists to detect.

## Related

- bstack P20 governance reference: [`broomva/workspace`](https://github.com/broomva/workspace) AGENTS.md §P20
- bstack substrate: [`broomva/bstack`](https://github.com/broomva/bstack) primitives.md §P20
- Inspiration: [Dallionking/cross-model-agents](https://github.com/Dallionking/cross-model-agents)
- Composed skills: `superpowers:constructive-dissent`, `devils-advocate`, `pr-review-toolkit:*`, `critique`, `premortem`

## License

MIT — see the [repository LICENSE](https://github.com/broomva/skills/blob/main/LICENSE).
