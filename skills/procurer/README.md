# procurer

> **Grounded procurement research for any real-world need.** Turn a problem — "reduce bedroom noise from the avenue", "add air conditioning", "hire an accountant", "buy a TV mount" — into a decision-shaped report with 3–5 ranked alternatives spanning DIY-retail → consultant/turnkey, cited price bands, confidence scores, locale-aware currency, and a clear recommendation with budget envelope.

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://github.com/broomva/procurer/actions/workflows/tests.yml/badge.svg)](https://github.com/broomva/procurer/actions/workflows/tests.yml)
[![skills.sh](https://skills.sh/b/broomva/procurer)](https://skills.sh/broomva/procurer)

The procurer skill is the agent's reflex when the user is about to spend money or effort on a problem and needs **calibration** before committing. It enforces grounding discipline (no price without a citation; no fabrication from training data; flag the dominant failure mode early) and produces a report you can act on.

---

## Quick start

### Install (Claude Code via skills.sh)

```bash
# Project-level install:
npx skills add broomva/skills --skill procurer

# Or globally for your user:
npx skills add -g broomva/procurer
```

You can also discover it through the interactive finder:

```bash
npx skills find procurer
```

### Invoke

Once installed, the skill auto-fires on procurement-shaped prompts:

> "How much would it cost to fix the noise from my bedroom window?"  
> "What are my options for adding A/C?"  
> "Should I hire an accountant or do my taxes myself?"  
> "Give me a budget for renovating the bathroom."

You can also invoke explicitly with `/procurer` if your agent supports slash commands.

### Validate a generated report

```bash
python3 scripts/validate_report.py path/to/report.md
```

Exits non-zero with a list of structural issues if the report doesn't conform to the procurement-report template (≥ 3 alternatives, citations resolve, recommendation has a budget envelope, etc.).

---

## What you get

Every procurer run produces a **decision-shaped report** with this structure:

```markdown
# <Need restated>

**Locale**: CO Bogotá · **Currency**: COP · **Mode**: standard

## Problem framing
<Dominant failure mode named — separates symptom from cause>

## Alternatives
### Alternative A — <name>  (Tiers: T1 → T3)
**Thesis** · **Cost band (low / typical / high)** · **Confidence (0–1)** · **Providers cited (table)** · **Notes**

### Alternative B — ...
### Alternative C — ...

## Cross-cutting notes
<Tax treatment · supplier shortlist · hidden costs · lead times>

## Recommendation
**Start with**: <X>  
**Total budget envelope**: <low – high>  
**Rationale**: <2–3 sentences>  
**If that doesn't work**: <Y> as fallback

## Sources
[1] <url> — "<title>" — fetched <iso8601>
[2] ...
```

See [`assets/examples/window-noise-attenuation.md`](assets/examples/window-noise-attenuation.md) for a fully-worked example.

---

## The 5-stage procedure

1. **Decompose** the need into 3–5 ranked alternatives using one of four canonical patterns:
   - *Incremental → Augmentation → Replacement* (fix-it problems)
   - *DIY → Service → Managed* (accountability questions)
   - *Standard → Custom → Bespoke* (spec-driven cost)
   - *Single-vendor → Multi-vendor → Integrator* (sourcing complexity)
2. **Map provider archetypes** — each alternative gets placed on a 5-tier model (DIY-retail → mid-retail → specialty/fabricator → contractor → consultant/turnkey).
3. **Choose mode** — `fast` (rough number, < 1 min) / `standard` (default, ~3–5 min) / `deep` (executive report, multi-vendor sensitivity).
4. **Search with grounding discipline** — every price carries `source_url`, `source_title`, `fetched_at`, `provider_tier`, and a confidence score (0–1). No fabrication; quote-on-request signals captured explicitly.
5. **Render the report** — using the template above. Validate with `scripts/validate_report.py`.

Full procedure: [`SKILL.md`](SKILL.md). Detailed references in [`references/`](references/).

---

## Why this skill is different

| Skill | Output shape | Use when |
|---|---|---|
| `procurer` (this) | **Decision-shaped** — recommendation + budget envelope | About to spend money or effort |
| `deep-research` | Research-shaped — knowledge artifact with citations | Understanding a topic |
| `technical-research` | Spike-shaped — technology selection memo | Choosing libraries / APIs / tools |

The differentiator: procurer **ends with an actionable recommendation and a budget**. The user can read it once and proceed. No follow-up synthesis required.

---

## Grounding discipline (binding)

These rules bind every run, regardless of mode:

1. **No price without a citation.** Every cost band carries `source_url`, `source_title`, `fetched_at`.
2. **No alternative without a thesis.** Don't list options; list options *with the problem each solves*.
3. **No recommendation without a budget envelope.** "Go with X" is incomplete; "Go with X, $A–$B inclusive of installation" is decision-shaped.
4. **No locale assumption.** Ask the user's region before searching — supplier networks and tax handling diverge sharply.
5. **Flag the dominant failure mode early.** If 80% of the problem can be solved by a 5% intervention, say so before recommending the 100% solution.

Full rules: [`references/grounding-discipline.md`](references/grounding-discipline.md).

---

## Repository layout

```
procurer/
├── SKILL.md                         # Agent entry point — frontmatter + procedure
├── README.md                        # This file — user-facing intro
├── LICENSE                          # MIT
├── CHANGELOG.md                     # Release history
├── CONTRIBUTING.md                  # How to contribute
├── SECURITY.md                      # Vulnerability disclosure
├── references/                      # Load-on-demand depth (read by the agent)
│   ├── decomposition-patterns.md
│   ├── provider-taxonomy.md
│   ├── grounding-discipline.md
│   ├── mode-tiers.md
│   └── report-template.md
├── scripts/
│   └── validate_report.py           # Structural linter for procurement reports
├── tests/                           # pytest suite for the validator
│   ├── conftest.py
│   ├── test_validator_canonical.py
│   ├── test_validator_failures.py
│   └── fixtures/
└── assets/examples/                 # Worked examples (treated as output references)
    ├── window-noise-attenuation.md
    └── construction-materials-co.md
```

---

## Development

```bash
# Run the validator's test suite
python3 -m pytest tests/ -v

# Validate the canonical worked example
python3 scripts/validate_report.py assets/examples/window-noise-attenuation.md
# → OK — passes all procurer-report structural checks.
```

No runtime dependencies — the validator uses only the Python 3.11+ standard library.

---

## Compounds with

- **[`bookkeeping`](https://github.com/broomva/bookkeeping)** (P8) — reusable knowledge from procurement reports (market bands, supplier shortlists) is filed into the entity graph for future runs to compound on.
- **`deep-research`** — for needs where the user must learn before deciding, run `deep-research` first, then `procurer` for the cost layer.
- **`technical-research`** — for software/library choice with a cost dimension, combine technical evaluation with SaaS/consultancy pricing.

---

## License

MIT © 2026 [Carlos D. Escobar-Valbuena](https://broomva.tech) (broomva). See [LICENSE](LICENSE).

---

## Acknowledgments

Procurer extracts and generalizes the supplier/taxonomy/grounding discipline of the **materiales-intel.v1** rules-package — the construction-materials intelligence module shipped as part of the Broomva Life Agent OS. The construction-specific reference at [`assets/examples/construction-materials-co.md`](assets/examples/construction-materials-co.md) preserves that lineage.
