# Anti-Slop Rubric — bstack P20

This is the canonical scoring rubric for `cross-review` adversarial verdicts. Every cross-model evaluator (Strata A / B / C) reads this file as the contract for what "≥7/10" means.

## The 10-point rubric

| Dimension | Points | Pass condition |
|---|---|---|
| **No over-engineered abstractions** | 2 | No unnecessary wrappers; no premature generalization; no abstraction layer without ≥3 concrete consumers |
| **No template-paste patterns** | 2 | No copy-paste from training data without adaptation; no boilerplate without intent; no scaffolding without invariant |
| **Correct contracts at boundaries** | 2 | Typed I/O; validated inputs; explicit error modes; no silent failures; no implicit conversions across module boundaries |
| **Failure modes named explicitly** | 2 | What happens on bad input, network fail, race condition, empty state, very large input, concurrent access — surfaced in code or docs, not implicit |
| **Tests cover the change** | 2 | Unit / integration / E2E proportional to change shape; coverage matches what the change introduces; critical path tested |

**Total: 10 points. PASS at ≥7. LOOP if <7. ESCALATE if round 3 still <7.**

## The adversarial brief (what to give the evaluator)

When invoking a Strata-A (Codex) or Strata-B (subagent) evaluator, include this brief verbatim as the system instruction:

> You are the adversarial reviewer. The writer (a different model OR the same model in a different context) just produced the diff you're about to read. **You are NOT the writer's ally.** Your job is to find what's wrong, what's missing, what's over-built, what's under-tested, what's brittle.
>
> Read the diff. Apply the 5-dimension anti-slop rubric below. For each dimension, assign 0, 1, or 2 points:
>
> - 0: clear failure, named deduction with file:line reference
> - 1: marginal, named caveat with file:line reference
> - 2: clean pass
>
> Sum the points (max 10). Total ≥7 → APPROVE. <7 → REVISE.
>
> When you REVISE, name the specific failures the writer must address. Don't give vague feedback. Each deduction must cite a file path + line range + the rubric dimension violated. Be ruthless — finding nothing wrong is suspicious; correlated blind spots are real.

## Per-dimension detail

### Dim 1: No over-engineered abstractions (2 pts)

**Deductions:**
- Abstract base class / interface without ≥3 concrete implementations: -1
- Factory pattern with one concrete factory: -2
- Generic type parameter that's only ever instantiated with one type: -1
- Manager / Helper / Util class as the primary surface: -1 each
- Wrapper around a stable third-party library: -1 (unless wrapper adds invariant)
- Dependency injection plumbing for a non-swappable dependency: -1

**Positive signals (full 2 pts):**
- Concrete types named after the domain
- Functions over classes when state isn't intrinsic
- Direct calls when indirection isn't earning its complexity
- Three concrete uses *before* extracting the abstraction (rule-of-three for code)

### Dim 2: No template-paste patterns (2 pts)

**Deductions:**
- Identifier names from the training-data distribution that don't match the domain (`UserService`, `DataManager`, etc. when domain has specific words): -1
- Comments that restate what the code does ("// initialize the variable"): -1
- Defensive code for impossible cases (null-check on a value the type system guarantees non-null): -1
- Configuration object pattern with one caller: -1
- Try-catch around code that can't throw: -1

**Positive signals (full 2 pts):**
- Code reads like it was written *for* this domain, not a generic template
- Each line carries information; no filler
- Comments explain *why*, not *what*

### Dim 3: Correct contracts at boundaries (2 pts)

**Deductions:**
- Function with `any` / `unknown` / `Object` in a public signature: -1
- Validation absent at API entry point: -2
- Error returned as a plain string instead of a typed error: -1
- Silent retry without logging: -1
- Implicit type conversion across module boundary: -1

**Positive signals (full 2 pts):**
- Typed I/O at all public boundaries
- Validation as a separate step before processing
- Errors are typed and carry context
- Module boundaries are clear from the type system

### Dim 4: Failure modes named explicitly (2 pts)

**Deductions:**
- Network call without timeout: -1
- Database write without transaction: -1
- File operation without "what if the file doesn't exist": -1
- Concurrent operation without "what if two run simultaneously": -1
- User-facing error with a stack trace instead of a meaningful message: -1

**Positive signals (full 2 pts):**
- Each external interaction has its failure mode documented
- Error paths are tested (not just happy paths)
- Edge cases are named in comments or tests

### Dim 5: Tests cover the change (2 pts)

**Deductions:**
- New public function without a unit test: -1
- Bug fix without a regression test reproducing the bug: -2
- New API endpoint without an integration test: -1
- Frontend change without a visual or interaction test: -1

**Positive signals (full 2 pts):**
- Test coverage proportional to the change
- Tests verify the *intent* of the change, not just the syntax
- New failure modes are exercised, not just happy paths

## Strata-A specific: Codex cross-vendor brief

When invoking Strata A via `codex exec`, prepend this preamble to the rubric:

> You are GPT-5.4 reviewing code written by Claude Opus. You have different training, different biases, different pattern preferences. Where Claude tends toward elegant abstractions, you tend toward explicit handling. Where Claude tends toward concise code, you tend toward defensive code. These differences are the point — name what Claude missed because of *its* biases.

(And the inverse if Claude is reviewing Codex's code.)

## Strata-B specific: subagent fresh-context brief

When dispatching a Claude subagent via `Agent` tool for Strata B, prepend:

> You are a fresh-context reviewer. You did NOT write this code. You have no investment in the writer's choices. Your job is to find what the writer missed because they were in the trenches. Same-model echo chambers are real even within one session — your job is to break the echo by reading the diff *cold*.

## Scoring output format

The evaluator MUST output the verdict in this exact structure (parseable):

```
=== CROSS-REVIEW VERDICT ===
Strata: {A|B|C}
Round: {1|2|3}
Score:
  Dim 1 (over-engineered abstractions):  {0|1|2}  reason: ...
  Dim 2 (template-paste patterns):       {0|1|2}  reason: ...
  Dim 3 (correct contracts):             {0|1|2}  reason: ...
  Dim 4 (failure modes):                 {0|1|2}  reason: ...
  Dim 5 (tests cover change):            {0|1|2}  reason: ...
Total: {0-10}
Verdict: {APPROVE|REVISE}
Deductions (if REVISE):
  - file:line — dim X — specific issue
  - file:line — dim X — specific issue
```

The agent invoking `cross-review` parses this output, posts it as a PR comment, and either pushes (APPROVE) or fixes-and-rescores (REVISE).
