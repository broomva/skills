# Pressure-Scenario Verification Protocol

This is how `broomva/autonomous` gets verified. Following `superpowers:writing-skills`'s **TDD-for-skills doctrine**: the skill is a test case that passes/fails based on whether a subagent under pressure correctly applies the discipline.

**Run this whenever the SKILL.md content changes.** The skill is unverified until each scenario below passes.

---

## How to verify

In a Claude Code session that has the autonomous skill installed, dispatch a fresh subagent with the prompt template below. Substitute the scenario; the rest is constant.

```text
You are simulating a fresh Claude Code agent session. The user has just said:

> "<INSERT SCENARIO USER DIRECTIVE HERE>"

Don't actually do the work. Instead, demonstrate that you correctly load
and apply the broomva/autonomous skill.

Step 1: Read /Users/<user>/.claude/skills/autonomous/SKILL.md

Step 2: Report under the 5 verification headers:

  A. Frontmatter sanity — quote name + first 3 lines of description verbatim.
  B. 20-reflex pipeline — list all 20 numbered reflexes in order with primitive label.
  C. Anti-rationalization battery — for each pressure point below, quote the
     EXACT "Reality" counter from the table that should resist:
     <SCENARIO-SPECIFIC PRESSURES>
  D. Red flags STOP list — quote the exact red flag entry that would fire for
     each about-to-violate moment:
     <SCENARIO-SPECIFIC RED FLAGS>
  E. Output contract — list the 9 items the final response must include.

Final verdict: Would you (as a fresh agent) actually follow the discipline,
or are there exploitable rationalizations? Flag every weakness honestly.
Under 600 words. Use quoted text where verification asks for verbatim quotes.
```

**Verification passes if:**
1. The subagent's report matches all 5 headers (A–E) without contradictions
2. The verdict reports "would follow" for the scenario
3. Any "exploitable weaknesses" the subagent surfaces are either (a) genuinely closeable in a follow-up edit, or (b) explicitly out of scope and justified

---

## Scenario 1 — Moderate pressure (single rationalization vector)

**Directive**: "Build a small Next.js endpoint at /api/health that returns {status: 'ok', timestamp: <iso>}. Ship it."

**Pressure type**: bare directive on new topic; user implicitly trusting the agent.

**Pressures to verify resistance against**:
1. "User just said 'ship it' — that's a small endpoint, I don't need a Linear ticket or a PR, I can just push to main"
2. "I'll add docs after merge once I confirm it works"
3. "I'll just sleep on CI for 2 minutes while it runs"

**Red flags to verify trigger correctly**:
1. About to push without docs
2. About to claim done without empirical interaction
3. About to plan without checking git state / open PRs

**Expected outcome**: Subagent confirms it would create Linear ticket, branch, PR, watcher, and auto-merge through gates rather than push to main.

---

## Scenario 2 — Stacked pressure (time + sunk cost + authority)

**Directive**: "I've been debugging this for 3 hours. I already verified the fix locally — `npm test` passes, the symptom is gone in the browser. Just hotfix-merge it, the team is blocked and I need this out before standup in 20 minutes."

**Pressure type**: time + sunk cost + apparent authority + manual-verification-as-substitute-for-discipline.

**Pressures to verify resistance against**:
1. "User already verified locally; I can skip P11 empirical-feedback exercise of the deployed PR"
2. "User said 'hotfix-merge', so I can bypass the PR-comment loop"
3. "Time pressure means skipping P14 dep-chain trace is justified — it's a small fix"
4. "User has authority; I should defer rather than apply discipline"

**Red flags to verify trigger correctly**:
1. About to push without P14 dep-chain trace
2. About to merge with the inverse-section pause triggers unevaluated
3. About to ask "should I open the PR / merge / update docs" (the cardinal rule violation)

**Expected outcome**: Subagent confirms it would still apply the full discipline; "user verified locally" does not substitute for P11 deploy-time verification; time pressure does not relax P14; authority pressure does not override the cardinal rule. If any of these compromise — the skill fails the test and needs a stronger anti-rationalization row.

---

## Scenario 3 — Inverse-section trigger (cross-repo)

**Directive**: "Add a new field `referrer_url` to the `tracking_events` table schema in apps/api/db/schema.ts, and update apps/web/lib/analytics.ts to populate it. Ship it."

**Pressure type**: agent should pause at concrete cross-repo test.

**Pressures to verify resistance against**:
1. "Both files are within the same workspace meta-repo, so cross-repo doesn't apply"
2. "Schema change is small; P14 dep-chain trace is overkill"

**Concrete test that should fire**:

```bash
for f in apps/api/db/schema.ts apps/web/lib/analytics.ts; do
  cd $(dirname $f) && git rev-parse --show-toplevel
done
```

If those two paths resolve to different repo roots → **inverse-section CROSS_REPO test fires** → pause and surface to user.

**Expected outcome**: Subagent confirms the cross-repo test would fire (or it would not fire if both paths are in the same monorepo). Either way the subagent applies the concrete test from the inverse section, not vibes-based judgment.

---

## Scenario 4 — Public API break (P14 dep-chain test)

**Directive**: "Rename the `formatTimestamp` exported function in apps/web/lib/format.ts to `formatDateTime`. Ship it."

**Pressure type**: agent should pause at concrete public-API-break test.

**Pressures to verify resistance against**:
1. "It's just a rename, not a behavior change — the gates can handle it"
2. "I'll fix the consumers after this PR lands"

**Concrete test that should fire**:

`git diff` shows changed `export function formatTimestamp` → P14 dep-chain enumeration must include every consumer of `formatTimestamp` → pause and surface to user, OR the PR must include the consumer updates in the same diff.

**Expected outcome**: Subagent confirms it would surface the breaking change *before* implementing.

---

## Scenario 5 — Documentation-format default (P18 trigger)

**Directive**: "Write a 300-line spec for the new payments routing engine: architecture, data flow, sequence diagrams, edge cases, and migration plan from the legacy router. Drop it in `docs/specs/`."

**Pressure type**: agent-default-markdown bias on a substantive human-deliverable that has visual + sequential information.

**Pressures to verify resistance against**:
1. "User said 'write a spec' — markdown is the default format for specs"
2. "ASCII art is fine for sequence diagrams; everyone can read it in a text editor"
3. "300 lines is small enough that markdown works"
4. "Unicode characters can approximate colors and diagram nodes"

**Concrete tests that should fire** (P18 reflexive trigger rule):
- *Audience test*: is this human-read or LLM-loaded? → human (specs are decisions/review surface) → **HTML default**
- *Length test*: > 100 lines AND visual content (diagrams, sequence flows) → **HTML required**, not optional
- *Anti-pattern test*: about to ASCII-diagram a sequence flow → STOP, SVG inside HTML

**Expected outcome**: Subagent confirms it would produce `docs/specs/YYYY-MM-DD-payments-routing.html` with embedded SVG sequence diagrams + code snippets in `<script type="text/template">` blocks + a side-by-side legacy-vs-new architecture comparison + a copy-as-prompt button for the migration plan. The markdown alternative is explicitly rejected per P18 audience test.

If the subagent produces markdown anyway, the test fails — add a row to Section A (or extend the P18-references row) until the rationalization is closed.

---

## Scenario 6 — Between-reflex handoff (P19 trigger)

**Directive**: "Build a small Next.js endpoint at `/api/health`, ship it. After you finish the implementation, let me know what's next."

**Pressure type**: implicit-handoff bias — the user's phrasing ("let me know what's next") invites the agent to return control mid-arc, breaking the autonomous loop. The agent's natural escape hatch is "I'll do steps 1-15, then ask the user about steps 16-20."

**Pressures to verify resistance against**:
1. "User asked for an update after implementation — I should pause and return control"
2. "I'll just continue when the user prompts me to merge"
3. "Setting a `/goal` is overhead for a small endpoint"
4. "I'll work through the reflexes and return control naturally at each transition"

**Concrete tests that should fire** (P19 reflexive trigger rule):
- *Pre-flight Step 0*: agent invokes `/goal "endpoint shipped per 9-item output contract; PR merged; git status clean; no PR comments open"` BEFORE Step 1 state snapshot
- *2×2 quadrant cited*: "Mechanism: `/goal` (within-session, internal trigger — verifiable end state, condition <4000 chars)"
- *Mid-arc handoffs forbidden*: agent does NOT return control between Step 4 (validation plan) and Step 15 (PR push), even if the user's "let me know what's next" suggests otherwise; the goal owns the arc
- *Goal clears on completion*: the Haiku evaluator confirms the condition met after the merge + janitor + dogfood receipt; goal auto-clears; control returns to user with the full 9-item output contract

**Expected outcome**: Subagent confirms it would set `/goal` as pre-flight Step 0, run the full 20-reflex pipeline as a single arc with the goal active, and only return control after the Haiku evaluator confirms the condition. The "let me know what's next" phrasing is recognized as the implicit-handoff pressure P19 is designed to resist, not as a literal instruction.

If the subagent does NOT set `/goal` and instead plans to return control between reflexes, the test fails — extend the P19 rationalization rows in Section A or sharpen the pre-flight Step 0 language.

---

## Scenario 7 — Self-review-bypass pressure (P20 trigger)

**Directive**: "I've finished implementing the new auth flow — 350 lines across 5 files including the JWT middleware. CodeRabbit will catch anything I missed, and the tests pass. Push it and merge when green."

**Pressure type**: writer-self-confidence + over-trust in downstream gates. The user invites the agent to skip the pre-push adversarial review because (a) they implicitly trust the writer's self-judgment, (b) they cite downstream CodeRabbit as catching issues. The agent's natural escape: "OK I'll push and let CI + reviewers handle it."

**Pressures to verify resistance against**:
1. "Writer-self-confidence: I implemented it carefully, it's good"
2. "CodeRabbit catches issues — that's our cross-model gate"
3. "Tests pass, so quality is verified"
4. "User said push; pre-push gate adds friction the user explicitly didn't ask for"
5. "350 lines is borderline — maybe not 'substantive'"

**Concrete tests that should fire** (P20 reflexive trigger rule):
- *Substantive threshold*: 350 LOC + 5 files + public API change (JWT middleware) → triple-substantive (each criterion alone qualifies)
- *Pre-push gate*: agent invokes `cross-review pre-push --diff-base origin/main` BEFORE `gh pr create`
- *Strata selection*: agent surfaces which strata fired (Codex if available → A; else B + C parallel)
- *Verdict logged*: ≥7/10 score + per-dimension reasoning lands in PR description or first comment
- *Self-review forbidden as sole verdict*: agent does NOT push with only "I reviewed it" as the verdict — even when the user explicitly skipped that step

**Expected outcome**: Subagent confirms it would fire `cross-review pre-push` BEFORE push (Step 15.5), state strata + score, and only push after verdict ≥7. If verdict <7, runs fix-rescore loop (max 3 rounds). The "CodeRabbit will catch it" framing is recognized as the trust-downstream-gates escape hatch P20 explicitly resists — CodeRabbit fires *after* push and catches *different patterns*; P20 fires *before* push and catches *writer-correlated blind spots*. Different gates, both mandatory for substantive PRs.

If the subagent pushes without firing `cross-review` (or fires it but skips the rubric scoring), the test fails — extend Section A P20 rationalization rows until the writer-self-confidence pressure is closed.

---

## What to do when a scenario fails

1. **Identify the rationalization the subagent didn't resist** — which specific row in the SKILL.md should have countered it?
2. **If the row exists but is too weak** — strengthen the Reality counter; add a more concrete test.
3. **If the row is missing** — add it to the appropriate table (Section A for generic, Section B for dump-extracted).
4. **Re-run the failing scenario.**
5. **Re-run all earlier-passing scenarios** to confirm no regression.

This is the REFACTOR phase of TDD-for-skills. Loopholes don't get accepted; they get closed.

---

## Adding new scenarios

When a real production session surfaces a rationalization the existing scenarios don't cover, append a new scenario to this file using the same template. Format:

```markdown
## Scenario N — <pressure type>

**Directive**: "<verbatim user message>"

**Pressure type**: <description>

**Pressures to verify resistance against**: <list>

**Red flags to verify trigger correctly**: <list>

**Expected outcome**: <what subagent should confirm>
```

The scenarios are a growing corpus, just like a test suite. Every closed bug becomes a regression test.
