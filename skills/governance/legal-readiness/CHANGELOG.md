# Changelog

## [0.1.0] — 2026-08-09

### Added

- Jurisdiction-aware, evidence-first legal-readiness workflow.
- Standard-library manifest validator and public-surface probe.
- Neutral manifest template, issue-area reference, trigger evals, and tests.
- `check --repo-root`: recomputes every path-shaped evidence `sha256` against
  the named file, so a digest binds to an artifact instead of being
  shape-checked. Routing is on the locator, never on author-supplied `kind`.
  The root must be a git checkout whose `origin` matches `project.repository`.
  `ready-for-counsel-review` requires it when the manifest carries any
  path-shaped evidence locator.
