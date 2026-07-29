# disambiguate

**Rewrite a requirement so it can only be read one way.**

A requirement is read by someone who cannot ask you what you meant. Every
reading your words permit is a system someone might build.

```bash
npx skills add broomva/skills --skill disambiguate
```

## What it does

Takes a requirement, acceptance criterion, ticket, spec line, runbook step, or
agent prompt, and reports which of five questions the reader cannot answer:

| | The reader asks | And cannot answer it when… |
|---|---|---|
| **A** | Which thing? | the text points without naming |
| **B** | Who must, and must they? | the actor or the obligation is missing |
| **C** | How do I know it is done? | no observation settles it |
| **D** | Can I hold this? | the unit exceeds what one pass can carry |
| **E** | Can I parse it at all? | the construction admits two grammars |

Then it rewrites. Every finding carries a substitute — a prohibition without
one is a complaint, not a review.

## Where it comes from

Distilled from **ASD-STE100 Simplified Technical English**, the aerospace
writing standard. STE exists because maintenance manuals were killing people:
technicians across dozens of first languages misread procedures written by
native English engineers. It is not a style guide that emerged from taste. It
is an incident ledger, and each rule closes one observed way a reader went
wrong.

Its design assumptions are why it transfers. The reader may not share your
language, **cannot ask a follow-up question**, pays dearly for a misreading,
and consumes one unit at a time, out of context. That is a technician at 3am.
It is also an engineer picking up your ticket and an agent executing your
prompt.

## Use

```bash
# check a file
python3 scripts/disambiguate.py REQUIREMENTS.md

# machine-readable
python3 scripts/disambiguate.py REQUIREMENTS.md --json

# CI gate: warnings are fatal
python3 scripts/disambiguate.py REQUIREMENTS.md --strict

# count one sentence the way the standard counts
python3 scripts/disambiguate.py --count "Remove the safety pin (10)."   # → 5

# product names and proper nouns that count as one word
python3 scripts/disambiguate.py REQUIREMENTS.md --glossary terms.json
```

Mode is detected automatically. Procedural text (commands the reader) gets a
20-word ceiling. Descriptive text (informs them) gets 25. Override with
`--mode`.

Exit code is `1` on a `block` finding, or on any `warn` under `--strict`.

## Example

```
$ python3 scripts/disambiguate.py ticket.md

B — Who must, and must they?  (2)
  [WARN ] B3-weak-modal          line 1
          > The system should handle authentication errors gracefully.
          why: "should" does not say whether this is mandatory, permitted, or
               merely hoped for. Two readers will build two different systems
               and both will claim to have met the requirement.
          fix: Choose one: "must" (mandatory), "can" (capability or
               permission), "will" (a future fact).
          ste: 1.3, 5.3
```

## Design

**Deterministic** (`scripts/disambiguate.py`, stdlib only, no network, no model
calls): the word-count algorithm plus 23 conservative detectors. A parenthetical,
a quoted span, an uppercase run, a number with its unit, and a hyphenated
compound each count as **one word** — the counting rules are not naive splitting.

**Latent** (`SKILL.md`): which preposition restores the right relation in a noun
stack, whether two actions are genuinely simultaneous, what the threshold should
be, and whether the requirement is worth having.

Where the algorithm cannot decide — a multi-word proper noun needs domain
knowledge — it reports an advisory naming the gap and the remedy rather than
guessing. Silent approximation would read as coverage.

## Tests

```bash
python3 -m pytest tests/ -q     # 153 tests
python3 tests/mutation_proof.py # revert each fix, assert its test fails
```

The word-count cases are the worked examples published in the standard's
section 8, where it states the expected count for each sentence, so the
algorithm is checked against the authority. Every detector asserts both
polarities: it fires on the defect and stays silent on the clean rewrite.

## Copyright

ASD-STE100 is © ASD, Brussels, and free to download from
[asd-ste100.org](https://www.asd-ste100.org). ASD grants reproduction rights to
a defined set of organizations, so **no dictionary entries and no rule text are
redistributed here.** What ships is a distilled principle set, an original
detector implementation, and short example sentences used as test fixtures.
Rule references point into the standard so a reader can check the source.

STE proper is a controlled language with an approved vocabulary, and word-level
conformance needs the official dictionary, which this skill deliberately does
not carry. What it carries is the part that generalizes.
