# phronesis

[![CI](https://github.com/broomva/phronesis/actions/workflows/ci.yml/badge.svg)](https://github.com/broomva/phronesis/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python: 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![GitHub release](https://img.shields.io/github/v/release/broomva/phronesis?include_prereleases)](https://github.com/broomva/phronesis/releases)
[![Tests: 399 passing](https://img.shields.io/badge/tests-399%20passing-brightgreen)](https://github.com/broomva/phronesis/actions)
[![bstack: Layer 7](https://img.shields.io/badge/bstack-Layer%207%20Domain-purple)](https://github.com/broomva/bstack)

> AI-native advisory practice. Encodes top-firm consulting methodology
> (Three Horizons, MIT CISR, Gartner AI, **CHAOSS**, JTBD, Value Prop Canvas,
> RICE/ICE/WSJF, Unit Economics + NPV/DCF + Real Options, QuantumBlack ML,
> Andrew Ng pipeline, Wardley) as runnable typed primitives.

**Status:** Phase 2 — engagement-driven refinements (`v0.1.1-pre`).
**License:** Apache-2.0.
**Skill family:** [bstack](https://github.com/broomva/bstack) Layer 7 (Domain).
**Linear:** [Phronesis — AI-Native Advisory Practice](https://linear.app/broomva/project/phronesis-ai-native-advisory-practice-8007a216a186)

## What it does

Phronesis runs AI/digital consulting engagements and produces **7 Discovery-grade
deliverables** in two modes:

1. **Consultant CLI** — interactive, human-in-the-loop. `phronesis init <tenant>` then drive the engagement stage by stage.
2. **Autonomous Life Runtime endpoint** *(Phase 3 — stub today)* — POST a `StartEngagementRequest`, get an `EngagementConcluded` notification when the 5 stages complete with human review at each gate.

### The 7 Phase-1 deliverables

| # | Deliverable |
|---|---|
| 1 | Maturity Report |
| 2 | Capability Heatmap |
| 3 | Use-Case Dossier |
| 4 | Impact-vs-Effort Matrix |
| 5 | ROI Model |
| 6 | Innovation Roadmap |
| 7 | Pilot Plan |

The substrate is designed to expand to 13 full-firm deliverables (Operating Model, Change Management Plan, Architecture Blueprint, Vendor Landscape, Executive Briefing Deck, 90-Day Plan) without refactor.

## Five C-level failure modes structurally prevented

| # | Failure (Bision empirical frequency) | Prevented by |
|---|---|---|
| 1 | "Sin tesis estratégica" (**100%**) | `StrategicThesis` required at Stage 1 — linter rule **L1** |
| 2 | "Casos de uso mal priorizados" (**87%**) | `IdeationSource` enum + diversity check — **L2** |
| 3 | "Datos no preparados" (**74%**) | `DataReadinessAssessment` gate on H1 pilots — **L3** |
| 4 | "Desconexión negocio-tecnología" (**61%**) | Required `AdoptionMetric` distinct from technical metric — **L4** |
| 5 | "Sin medición de ROI" (**48%**) | Required `BaselineSection` captured before pilot start — **L5** |

These are enforced by:
- **Pydantic typed primitives** that reject malformed engagements at construction time
- **Stage runners** that raise `ValueError` when the gate is violated
- **`core/linter.py` L1–L5 rules** that scan the journal as a release-gate backstop
- **`tests/integration/test_bision_prevention.py`** as a CI release gate
- **`.githooks/pre-push`** that re-runs the gate locally before any push

## Install

### Via skills.sh (recommended for agentic harnesses)

```bash
npx skills add broomva/phronesis --agent claude-code --yes
```

This installs phronesis as a skill into your agent harness's skill directory.

### Via pip / uv

```bash
# Clone + dev install
git clone https://github.com/broomva/phronesis
cd phronesis
uv sync --all-extras
uv run phronesis --version

# Or install the latest released wheel
uv pip install phronesis  # once published to PyPI (Phase 2 follow-up)
```

## Quickstart

```bash
# Create a new engagement scaffold
phronesis init acme-bank \
  --name "Acme Bank" \
  --industry banking \
  --region CO \
  --revenue-band "100M-1B" \
  --headcount-band "500-5000" \
  --sponsor "Carolina Pérez" \
  --sponsor-role CDO \
  --scope "AI maturity + Tier-1 ticket deflection — 8w pilot" \
  --target-duration-weeks 8

# Inspect engagement state
phronesis status acme-bank

# Run the L1-L5 release-gate linter
phronesis lint acme-bank --strict

# Render all 7 deliverables (lint-gated by default)
phronesis render acme-bank
```

The Python API is fully exposed for stage commands while the CLI stage commands are queued for M4:

```python
from core.engagement import Engagement, EngagementJournal
from core.types import StrategicThesis, Citation
from stages.intake import IntakeStage
from runners.cli.io import load_engagement
from decimal import Decimal

eng = load_engagement("acme-bank")
intake = IntakeStage()
intake.declare_thesis(eng, StrategicThesis(
    economic_lever="Reduce Tier-1 ticket cost via Spanish-LLM deflection",
    lever_kind="cost",
    magnitude_estimate=Decimal("400000"),
    magnitude_basis="12K tickets/mo × $8 × 35% deflection × 12mo",
    strategic_horizon="h1-now",
    decision_rights_owner="Carolina Pérez (CDO)",
    measured_in="USD/yr",
    evidence=[Citation(kind="evidence", ref="interview:cdo:Q2", confidence="high")],
))
intake.request_review(eng, "Thesis declared")
eng.journal.save_jsonl(...)  # persists to engagements/acme-bank/journal.jsonl
```

## Documentation

- [Design spec (workspace)](https://github.com/broomva/broomva/blob/main/docs/superpowers/specs/2026-05-06-phronesis-design.md)
- [ADRs](docs/adr/) — 8 architectural decision records covering the major design choices
- [CHANGELOG](CHANGELOG.md)
- [SKILL.md](SKILL.md) — agent-facing skill card with triggers + commands

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bugs and feature requests welcome via the GitHub issue templates. Security disclosures: see [SECURITY.md](SECURITY.md).

The phronesis substrate evolves through **engagement-driven discovery** —
real or synthetic engagements surface gaps, gaps become Linear issues,
issues close in single-PR batches with re-run validation. See
[CHANGELOG](CHANGELOG.md) entries for `v0.0.2-m0.1` and `v0.1.1-pre` for
two complete examples of the loop.

## License

Apache-2.0 — see [LICENSE](LICENSE).
