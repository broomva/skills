---
name: spec-contract
tier: D+J
category: governance
description: "The content contract for a design doc — what must be IN it, as against make-spec which owns how it LOOKS. Synthesised from five primary sources read verbatim (Lynch/Refactoring English + his worked example, Design Docs at Google, the Rust RFC template, Nygard's original ADR post, Oxide RFD 1). The load-bearing rule is the cost of reversing a decision, not its importance: a choice fixable in an afternoon is review noise, a one-way door left unargued is the failure a design doc exists to prevent. Two layers. DETERMINISTIC — `scripts/spec_check.py` reads a markdown or HTML doc and decides 18 findings: required sections by class not by name, status resolvable and supersession pointed, >=2 alternatives each with a rejection reason, non-goals that are declined goals rather than negated requirements, drawbacks that state a cost, acceptance that carries a number or a runnable command, and an implementation-manual detector for a doc with no trade-off language anywhere. JUDGMENT — `references/rubric.md` grades the five things a script cannot: whether the documented decisions are the expensive ones, whether the alternatives are real or strawmen, whether the non-goals are load-bearing, whether trade-offs are argued or merely mentioned, and whether the first screen is legible to the widest expected reader. Use when: (1) writing or reviewing a spec, plan, ADR, RFD or design doc, (2) deciding whether something warrants a design doc at all, (3) gating a doc before it goes out for review, (4) asked what belongs in a spec or why a spec is weak. Triggers on 'spec contract', 'design doc', 'write a spec', 'review this spec', 'is this spec any good', 'what belongs in a design doc', 'ADR', 'RFD', 'non-goals', 'alternatives considered', 'spec review', 'spec gate', 'design review', 'one-way door', 'reversal cost'."
---

# spec-contract — what must be in a design doc

`make-spec` owns the **shell**: the theme, the tag vocabulary, the filename
convention, `<title>`/`<h1>` parity. Its self-test checks the CSS.

This skill owns the **contents**. They compose; neither replaces the other.

## The rule everything else derives from

> **What's the penalty for being wrong?**

A design doc admits a decision by the **cost of reversing it after
implementation** — not by importance, not by effort, not by how much the author
thought about it. Choosing C++ over Rails is unrecoverable at 200k lines and
belongs in the doc. A "Load more" button is fixable in an afternoon and arguing
about it in review is pure waste.

Every check below is downstream of that rule. Provenance for each, with verbatim
citations: [`references/sources.md`](references/sources.md).

## Layer 1 — deterministic (`scripts/spec_check.py`)

```bash
# one doc, profile inferred from the path
python3 scripts/spec_check.py docs/specs/2026-09-16-thing.html

# explicit profile, JSON for a gate
python3 scripts/spec_check.py docs/adrs/*.md --profile adr --json

# reversal cost becomes blocking rather than advisory
python3 scripts/spec_check.py docs/specs/thing.md --strict

# resolve every external URL (network; off by default so CI stays hermetic)
python3 scripts/spec_check.py docs/specs/thing.md --check-links
```

Exit `0` clean · `1` a required check failed · `2` bad invocation.

| Check | Fails when | Source |
|---|---|---|
| `C1-missing-section` | a **required** class for the profile has no heading | LYNCH |
| `C1-missing-recommended` | *(warn)* a recommended class is absent | LYNCH |
| `C2-no-status` | no `Status:` field — a doc with no state can never be superseded | NYGARD, OXIDE |
| `C2-dangling-supersede` | status is `superseded`/`deprecated` and names no successor | NYGARD |
| `C2-bad-status` | *(warn)* status outside the known state set | OXIDE |
| `C3-no-reversal-cost` | *(warn; `--strict` → fail)* no one-way/two-way-door declaration | LYNCH |
| `C3-vague-reversal-cost` | *(warn)* reversal cost named but not graded | LYNCH |
| `C4-negated-goal` | *(warn)* a non-goal reads as a negated requirement | GOOGLE |
| `C5-thin-alternatives` | fewer than two alternatives named | RUST, GOOGLE |
| `C5-unjustified-alternative` | an option is named with no prose beyond its own name | RUST |
| `C5-no-rejection-reason` | no option states why it was *not* chosen | RUST |
| `C6-drawbacks-without-cost` | a drawbacks section that states no cost — blocking where the class is *required*, advisory where it is only recommended | NYGARD, RUST |
| `C7-open-question-without-next-step` | *(warn)* an open question with no resolution path | LYNCH |
| `C8-unmeasurable-acceptance` | acceptance with no number, unit or runnable command — blocking on `plan`, advisory elsewhere | LYNCH |
| `C9-implementation-manual` | **no trade-off language anywhere in the document** | GOOGLE |
| `C10-oversized` | *(warn)* beyond ~20 pages — GOOGLE's signal to split the problem | GOOGLE |
| `C10-stub` | *(warn)* under 250 words | NYGARD |
| `C11-dead-link` | *(opt-in `--check-links`)* a cited URL does not resolve | — |

### Profiles

A profile is a claim about which reversal-cost axes a document type exists to
pin down. Inferred from the path (`docs/adrs/` → `adr`, `docs/plans/` → `plan`,
`/rfd`|`/rfcs/` → `rfd`, short docs → `note`, else `spec`); override with
`--profile`.

| Profile | Required | Recommended |
|---|---|---|
| `adr` | context · design · alternatives · drawbacks | objective · acceptance |
| `spec` | objective · design · non-goals · alternatives | context · goals · drawbacks · acceptance · open questions |
| `plan` | objective · goals · **acceptance** | non-goals · design · open questions |
| `rfd` | objective · design · alternatives · drawbacks | context · open questions · acceptance |
| `note` | design | objective · alternatives |

`alternatives` is required on `adr`, `spec` and `rfd` because all five sources
say so in the same words. It is **not** required on `plan` — a rollout plan
sequences work whose design decision was already taken elsewhere — nor on
`note`. `acceptance` is required on `plan` alone: a plan with no definition of
done is a wish list. `test_r1_nb1_skill_md_alternatives_claim_matches_the_table`
asserts this paragraph against `PROFILES`, because the first version of it
claimed "every profile but `note`" and the table disagreed.

**Sections resolve by class, not by name.** "Missing features", "Out of scope"
and "What this is not" are all `non_goals`. Widen a class by adding a synonym to
`SECTION_CLASSES` — the single producer — never by renaming a heading to satisfy
the checker. Renaming to pass a gate is gaming it.

## Layer 2 — judgment (`references/rubric.md`)

A doc can pass all 18 findings and be worthless: two strawman alternatives, a
non-goal nobody would have assumed, an SLO chosen because it was easy to measure.
That is not a gap in the script — it is the half that is irreducibly a judgment.

Five axes, 0-3, **pass ≥11/15 with no axis at 0**:

| Axis | Question |
|---|---|
| **R1** reversal-cost fit | are the documented decisions the expensive ones — and is any expensive one missing? |
| **R2** alternative realism | would a competent engineer actually have chosen one of these? |
| **R3** non-goal load-bearing-ness | would a reader have assumed these were in scope? |
| **R4** trade-off substance | delete the alternatives section — does the doc's meaning change? |
| **R5** legibility | is the first screen intelligible to the widest expected reader? |

Grade with a **different model than the one that wrote the doc** (P20: the writer
cannot be the final judge). `R1 = 0` — a silent one-way door — stops the doc
outright; `R2`/`R4` at 0-1 route to full cross-review, because the design is
unargued and rewriting prose will not fix it.

## When a design doc is not warranted

The honest answer is often *none*. Both Lynch and Google give a test, and they
agree: write one when the **solution is ambiguous** and the **decisions are
expensive**. Google's disqualifier is the sharper one —

> *"If a doc basically says 'This is how we are going to implement it' without
> going into trade-offs, alternatives, and explaining decision making … then it
> would probably have been a better idea to write the actual program right away."*

That is what `C9` detects mechanically. If the only honest answer to "what were
the alternatives?" is "there weren't any", the correct output is code, not a doc.

## Composition

| With | How |
|---|---|
| **`make-spec`** | This skill decides the contents; `make-spec` renders them. Run `spec_check.py` on the output before the doc goes out. |
| **`cross-review` (P20)** | The judgment layer *is* a P20 stratum applied to a design rather than a diff. An `R2`/`R4` failure escalates to the full gate. |
| **`decision-log`** | Already asks "one-way door or two-way door?" — that is `C3`'s field. A logged decision that reaches doc scale becomes an `adr`-profile doc. |
| **`bookkeeping` (P6)** | A doc that passes both layers is citable provenance for an entity page; one that fails `C9` is an implementation manual and cites nothing. |
| **`checkit`** | Supplies `R2`'s input — you cannot judge whether an alternative is real without having read what else exists. |

## Review ordering

Grading a draft and reviewing it are different disciplines. The ordering is
counterintuitive enough to state, and it is in `references/rubric.md`: **one**
preliminary reviewer on comprehension only (ten at once triggers the bystander
effect), then widen on substance, and the meeting is the **last** step with an
agenda naming only the open issues. Every answer goes back into the doc — a
reviewer's confusion resolved in a thread fixes nothing for the next reader.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "The sections are all there, so the doc is fine." | Layer 1 checks shape. Shape is necessary and nowhere near sufficient — run the rubric. |
| "I'll add non-goals if a reviewer asks." | The scope boundary is what review relitigates. Undefended scope is the cost you pay later, in the meeting. |
| "There weren't really any alternatives." | Then there was no decision, and `C9` is right: write the code. If there *was* a decision, the alternatives exist and you skipped them. |
| "I'll rename the heading so the checker passes." | Classes are synonym-matched precisely so you don't have to. Renaming to pass is gaming the gate; add a synonym, or write the section. |
| "This is just a small change." | Then use the `note` profile, which requires one section. Small is a size, not an exemption from stating what you gave up. |
| "The doc is accurate — I wrote it last month." | Staleness has no failure signal. `C2` exists so a doc can be superseded; a doc with no status silently becomes a false description of what shipped. |
| "I reviewed it myself and it reads well." | Reading well is `R5`, the cheapest axis. The writer cannot grade `R1`, `R2` or `R4` on their own work. |

## Calibration

Measured 2026-09-16.

| Corpus | Result |
|---|---|
| **Lynch's own worked example** (`little-moments-design-doc`, 2,667 lines), `--profile spec` | **zero failures** |
| This workspace's 105 existing `docs/specs\|plans\|adrs` | **0 pass** |

Section coverage across those 105, by class: design 46.7% · open questions 25.7%
· acceptance 13.3% · drawbacks 13.3% · objective 12.4% · context 9.5% ·
**non-goals 7.6% · alternatives 7.6%** · goals 1.9%. The corpus documents what
was chosen and not what was ruled out — the inverse of reversal cost, and the
reason this skill exists.

**What the corpus number is not evidence for.** An earlier draft of this section
reported 1/105 and attributed the improvement to the required/recommended split.
Cross-model review challenged that attribution and re-measurement refuted it:
both the all-nine-required arm and the shipped split pass **0/105**. The split
buys zero existing documents. It is derived from the five sources — `required`
is the intersection of what all five independently call load-bearing — and the
evidence that it is not merely strict runs the other way: **a design doc written
to published best practice clears it.** A corpus pass rate says what the corpus
is like, not where the bar belongs, and reporting it as if it justified the bar
was the error.

## Tests

```bash
python3 -m pytest tests/test_spec_check.py -q   # 111 tests
bash tests/mutation.sh                          # incl. a NULL control that must SURVIVE
```

Every check carries a **positive and a negative control**. `C4` found nothing
across all 105 real documents; that is a measured zero with a known cause — only
8 of them have a non-goals section for it to read — not an unfalsified silence,
and the four positive controls prove the rule fires.

The mutation sweep reports **killed 27/27**, and three properties of it are load-bearing
because the first version had none of them and still printed a clean score:

- **A NULL mutant must SURVIVE.** A no-op edit that fails the suite means the
  harness is broken and every other verdict it printed is void.
- **A nonzero exit is not a kill.** `PYTEST_ADDOPTS=--bogus` made the first
  version report "killed 14/14" while pytest collected nothing. A kill now
  requires the same test count as the clean baseline plus a `FAILED` line.
- **A crash is not a kill.** A mutant that dereferences `None` proves the code
  path runs, not that any assertion is sensitive to it. Those are reported
  `CRASH` and fail the run.
