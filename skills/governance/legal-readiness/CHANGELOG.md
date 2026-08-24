# Changelog

## [0.1.0] — 2026-08-09

### Added

- Jurisdiction-aware, evidence-first legal-readiness workflow.
- Standard-library manifest validator and public-surface probe.
- Neutral manifest template, issue-area reference, trigger evals, and tests.
- `check --repo-root`: recomputes evidence digests against the named files, so a
  digest binds to an artifact instead of being shape-checked. A locator that
  resolves to a **tracked** repository file is verified and must be declared
  `repo`/`test`; evidence declared `repo`/`test` must resolve to one. Lying in
  either direction is a finding, so no label escapes verification. The root must
  be a git checkout whose `origin` matches `project.repository`, and a matching
  digest over an uncommitted file is reported. `ready-for-counsel-review`
  requires `--repo-root` unconditionally.

  Known limitations: HEAD is not bound to the lifecycle commit receipts, so a
  clean but stale checkout of the right repository is accepted; and a CommonMark
  HTML comment is not treated as a code region.
