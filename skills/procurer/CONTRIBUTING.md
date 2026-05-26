# Contributing to procurer

Thank you for considering contributing. This document explains what's in scope, what to expect from a review, and how to develop locally.

---

## What's in scope

The procurer skill exists to do one thing well: **turn a procurement need into a decision-shaped report with grounded citations**. Contributions should compound on that mission.

Welcome contributions:

- **New worked examples** in `assets/examples/` covering non-construction domains (services, technology, professional services, consumer goods) and locales other than Colombia.
- **Refinements to the references** in `references/` — sharper decomposition patterns, additional provider archetypes for specific categories, locale-specific tax/regulatory notes.
- **Validator improvements** in `scripts/validate_report.py` — additional structural checks, better error messages, performance.
- **Tests** in `tests/` — covering currently-untested validator paths or new structural rules.
- **CI improvements** — packaging, linting, security scanning.

Out of scope:

- Replacing the 5-stage procedure with a different orchestration shape. The procedure is the skill's mechanism.
- Adding runtime dependencies. The validator is stdlib-only on purpose; new dependencies require strong justification.
- Domain-specific business logic that belongs in a downstream consumer (e.g., tenant-specific rules-packages for the Broomva Life Agent OS — those live alongside the tenant, not in this skill).

---

## Development setup

```bash
git clone https://github.com/broomva/procurer.git
cd procurer

# Optional: create a venv (only needed if you want pytest)
python3 -m venv .venv
source .venv/bin/activate
pip install pytest

# Run the test suite
python3 -m pytest tests/ -v

# Validate the canonical worked example
python3 scripts/validate_report.py assets/examples/window-noise-attenuation.md
```

Python 3.11+ required. No other runtime dependencies.

---

## How to add a new worked example

1. Create `assets/examples/<topic>-<locale>.md`.
2. Follow the template in `references/report-template.md` exactly — the validator must pass against it.
3. Include 3–5 alternatives spanning multiple tiers, the dominant-failure-mode framing, a recommendation with budget envelope, and at least placeholder citations.
4. Add a one-line entry to `SKILL.md` under `### assets/examples/`.
5. Run `python3 scripts/validate_report.py assets/examples/<your-file>.md` — it must exit 0.
6. Open a PR with a short description of the procurement context (locale, decision stakes, mode used).

---

## How to add a new reference

References in `references/` are load-on-demand depth. They get pulled into the agent's context when the procedure needs them.

1. Create the file under `references/`.
2. Link it from `SKILL.md` in the appropriate stage of the procedure (Decompose / Map providers / Choose mode / Search with grounding / Render).
3. Keep each reference focused on one concern — if it's spanning multiple, split it.
4. Cross-link to other references at the bottom.

---

## How to change the validator

1. Add a failing test first in `tests/test_validator_failures.py` (or canonical pass behavior in `tests/test_validator_canonical.py`).
2. Update `scripts/validate_report.py` to make the test pass.
3. If the change adds a new structural rule, update `references/report-template.md` "Validator contract" section.
4. If the change is breaking (an existing valid report would now fail), bump the minor version in `CHANGELOG.md` and call it out explicitly.

---

## Coding conventions

- **Python style**: PEP 8, type hints on every public function.
- **Markdown style**: ATX headings (`#`, not `===`), code fences with language tags, no trailing whitespace.
- **Commit messages**: short imperative subject (≤ 72 chars), blank line, optional body. Conventional Commits prefixes (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`) welcome but not required.
- **PRs**: focused, one concern per PR. Link to a Linear ticket if the change is part of a tracked initiative.

---

## Releasing

Maintainers: bump version in `CHANGELOG.md`, tag the commit, push.

```bash
# Once CHANGELOG is updated and merged:
git tag -a v0.X.Y -m "v0.X.Y"
git push origin v0.X.Y
gh release create v0.X.Y --notes-from-tag
```

The skills.sh registry picks up new tags automatically via the GitHub topic `agent-skill`.

---

## Questions?

Open an issue at <https://github.com/broomva/procurer/issues> or reach the maintainer at <contact@broomva.tech>.
