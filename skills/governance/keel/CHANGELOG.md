# Changelog

All notable changes to the `keel` skill are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this skill adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-08-03

First release from `broomva/skills`. Keel previously lived in a standalone
repository; this is the same tool, packaged as a monorepo skill.

### Added

- `scripts/portability-check.sh` — refuses to commit a machine-specific path.
  Ported from the standalone repo with a tighter rule: measurement artifacts
  under `reports/` were previously exempt wholesale, which is why a curve
  disclosure and a probe warning shipped carrying an absolute home path. They
  are now scanned for *our own* paths while quoted evidence from a measured
  target still passes, so the gate covers the one directory where the defect
  actually occurred.
- `docs/` — the architecture reframe, the substrate-generalization design, the
  agentic-corpus finding, the production roadmap, the design-system guidelines,
  and the as-minted probe record behind the crystallization curve.

### Changed

- Install path is now `npx skills add broomva/skills --skill keel`.
- `scripts/corpus.ts` no longer infers its workspace from where the skill sits.
  `corpus.json` ships beside the skill now, so the old "the directory above the
  skill, if it holds a corpus.json" rule would have been satisfied by every
  *install* as well as every checkout — and a corpus run shallow-clones
  multi-hundred-megabyte repositories. The workspace is `KEEL_REPO_ROOT`, else
  the cwd, and is never guessed.
- `scripts/render.ts` resolves `reports/curve.svg` relative to the skill root
  rather than three levels above `scripts/`, which pointed outside the skill in
  the monorepo's category-bucket layout.
- `tests/published-markup.test.ts` now parses what `render.ts` emits instead of
  a published site directory. The publish step and the site it wrote were not
  carried over, so the original subject no longer exists; the property belongs
  to the renderer, which does ship. Verified to still fail on the bug it was
  written for — a bare `<repo>` placeholder inside the curve's SVG `<desc>`.

### Removed

- The real-target arm of `gather · local gates are recognised`. It measured a
  repository that carried `.githooks/` and `.control/` at its root; no tree in
  reach has that shape now, and creating one so the assertion passes would
  manufacture the evidence. The constructed-tree arm still covers the property.
  See the note in `tests/gather-coverage.test.ts`.

### Known limitations

- The `keel` entry in `corpus.json` pinned a repository that no longer exists,
  so that one target is not re-runnable and its number is not reproducible. The
  row is kept because the published ratios and the crystallization curve were
  computed over this population; deleting it would falsify what they describe.
  The other 14 targets remain pinned and re-runnable.
- The probe sandbox is enforced on macOS only (`sandbox-exec`). On Linux and
  Windows a probe gets a stripped environment and a kill-timer and nothing more.
  See `SECURITY.md`.
