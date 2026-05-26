# Changelog

All notable changes to the `procurer` skill are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-13

### Added
- **Initial release** of the `procurer` skill — grounded procurement research for any real-world need.
- **SKILL.md** with the 5-stage procedure (decompose → map providers → choose mode → search with grounding → render report).
- **References** — five load-on-demand documents:
  - `decomposition-patterns.md` — four canonical patterns for breaking a need into alternatives (Incremental/Augmentation/Replacement; DIY/Service/Managed; Standard/Custom/Bespoke; Single/Multi/Integrator).
  - `provider-taxonomy.md` — the 5-tier provider archetype model (DIY-retail → consultant/turnkey).
  - `grounding-discipline.md` — eight binding rules (citation, confidence 0–1, locale, tax handling, sanity bands, dominant-failure-mode honesty).
  - `mode-tiers.md` — `fast` / `standard` / `deep` mode contracts with concrete budgets.
  - `report-template.md` — output skeleton with validator contract.
- **`scripts/validate_report.py`** — structural linter for procurement reports. Exit non-zero on missing sections, < 3 alternatives, malformed confidence values, currency inconsistency, unresolved footnotes, or missing recommendation fields. Stdlib-only.
- **Worked examples** in `assets/examples/`:
  - `window-noise-attenuation.md` — bedroom-window noise on a Bogotá avenue, three-tier remediation (felpa replacement → secondary window → acoustic DVH) with optional Tier-5 consultant rung.
  - `construction-materials-co.md` — Colombian construction materials locale reference (supplier shortlist by tier, family taxonomy, IVA/retención handling, sanity-band multipliers per family).
- **Tests** — pytest suite for the validator covering canonical pass + structural failure modes.
- **CI** — GitHub Actions workflow running pytest on Python 3.11, 3.12, 3.13.
- **OSS packaging** — MIT LICENSE, README, CONTRIBUTING, SECURITY, .gitignore.

### Lineage
- Extracted the reusable abstractions of the `materiales-intel.v1` rules-package (CO construction-materials intelligence module for Broomva Life Agent OS) and generalized them into a domain-agnostic procurement skill. The original construction-specific skeleton remains at `~/broomva/freelance/_pending-constructora/rules-package/` as a tenant deployment artifact.

[Unreleased]: https://github.com/broomva/procurer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/broomva/procurer/releases/tag/v0.1.0
