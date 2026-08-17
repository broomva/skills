# Changelog

All notable changes to the `citable` skill are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this skill adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-13

Initial release. Distilled from a full-corpus research ingest (18 newsletter
issues, 14 videos, three primary studies read verbatim) via `skillify`.

### Added

- `SKILL.md` — the two-selection-surfaces frame, the measured effect table, six
  first principles, the procedure, and explicit boundaries against `seo-llmeo`,
  `linkedin-profile-optimizer`, and `social-intelligence`.
- `scripts/citable_check.py` — the deterministic core. Checks math-alpha unicode
  (U+1D400–U+1D7FF), per-surface length budgets, quantity density, named-entity
  presence, link-in-comments, FAQ shape, em-dash density, and a full non-ASCII
  inventory. Five surfaces: `headline`, `services`, `post`, `article`, `prose`.
  Exit 0 / 1 / 2 so it drops into a pre-publish hook or CI.
- `references/evidence.md` — full methodology and provenance for every threshold,
  with HIGH/MED/LOW confidence tags, the known April 2026 citation decay, and an
  explicit "not verified" section.
- `tests/` — 41 tests, each check exercised on both arms, plus a real fixture
  pair (an actual drafted article and a degenerate post) and a guard against the
  two fixtures drifting to the same verdict.
- CI: pytest on Python 3.11 and 3.12, plus a two-arm dogfood job asserting the
  gate accepts real publishable content and rejects the degenerate case.

### Notes

Two defects in the linter were found by dogfooding it on real drafts during
development, both fixed with regression tests before release:

- The `headline` surface failed technical-specificity because a 192-character
  headline carries no digits. Density is now skipped on no-density surfaces.
- Spelled-out numerals were not counted, so "nine iterations, seven of them"
  read as unspecific. A real article reported 3 quantities against ~18 actual.

Effect sizes come from two 2026 studies over a single platform, inside a window
that already contains one observed decay point. Treat the coefficients as dated;
the structural finding is the durable part.

[1.0.0]: https://github.com/broomva/skills/releases/tag/citable-v1.0.0
