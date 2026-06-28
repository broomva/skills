---
name: cross-review
category: governance
description: "bstack P20 — Cross-Model Adversarial Review Gate. The model that wrote the code cannot be the final judge of the code. Before substantive PRs merge, fire a cross-model adversarial gate — different evaluator than writer, anti-slop scoring ≥7/10, max 3 fix rounds, verdict logged in PR. Three strata: (A) Codex CLI cross-vendor for true different-model verdict, (B) fresh-context subagent under devils-advocate brief, (C) composed existing adversarial-review skills always parallel. Use cross-review when: (1) about to push a substantive PR (>200 LOC OR public API OR multi-file OR governance-class), (2) reviewing a draft plan/design before implementation, (3) auditing a feature spec against single-model blind spots, (4) integrating with the /autonomous skill's pre-push gate. Triggers on 'cross-review', 'P20', 'adversarial review', 'anti-slop', 'cross-model gate', 'different evaluator', 'devils advocate gate', 'self-review prohibition'."
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
LOOP: <7 → fix the specific deductions → rescore (max 3 rounds)
ESCALATE: round 3 still <7 → surface to user
```

The rubric is *concrete* and *machine-applicable* — every deduction names a specific failure category, not a vague "could be better."

## Invocation patterns

### Pattern 1: pre-push gate (the canonical use)

```bash
# Substantive PR ready, about to push
cross-review pre-push \
  --diff-base origin/main \
  --strata auto \
  --rubric anti-slop \
  --max-rounds 3
```

Returns:
- Exit code 0 if verdict ≥ 7
- Exit code 1 if verdict < 7 after max rounds (with fix recommendations)
- Stdout: the verdict + reasoning, formatted as a PR comment

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
2. **When verdict < 7** — apply the specific fixes the rubric flagged, rescore. Max 3 rounds.
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
| "It scored 6/10 but the work is fine — let me push anyway" | Threshold is ≥7. <7 → fix, rescore, max 3 rounds. Don't push override. |

## Red flags — STOP if you catch yourself

- About to push without firing the gate → STOP, run `cross-review pre-push`
- About to merge with verdict <7 → STOP, fix or escalate
- About to use only "I reviewed it" as the verdict → STOP, fire Strata B at minimum
- About to skip the rubric because "the score doesn't matter, I see the work is good" → STOP, the score is the contract

## Implementation

`scripts/cross-review.sh` — the entry point. Auto-detects Codex availability (Strata A), falls back to subagent dispatch (Strata B), always runs composed adversarial skills (Strata C).

See [`scripts/cross-review.sh`](./scripts/cross-review.sh) for the implementation + [`references/rubric.md`](./references/rubric.md) for the full rubric definition + [`tests/`](./tests/) for the verification battery.

## Related

- bstack P20 governance reference: [`broomva/workspace`](https://github.com/broomva/workspace) AGENTS.md §P20
- bstack substrate: [`broomva/bstack`](https://github.com/broomva/bstack) primitives.md §P20
- Inspiration: [Dallionking/cross-model-agents](https://github.com/Dallionking/cross-model-agents)
- Composed skills: `superpowers:constructive-dissent`, `devils-advocate`, `pr-review-toolkit:*`, `critique`, `premortem`

## License

MIT — see the [repository LICENSE](https://github.com/broomva/skills/blob/main/LICENSE).
