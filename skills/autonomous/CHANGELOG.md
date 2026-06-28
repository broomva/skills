# Changelog

All notable changes to `broomva/autonomous` are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Anti-rationalization row: permission-to-document (P6 reflex tightening, BRO-1288)** — "I'll ask the user whether to file this into the knowledge graph" → forbidden. Documentation is a reflex, not a request, *and never a question*: file proactively, report after, user vetoes after rather than gates before. Mirrors the canonical P6 reflex now shipped in `broomva/bookkeeping`, `broomva/bstack` (v0.23.1), and `broomva/workspace`.
- **Step 15.5: Cross-model adversarial review (P20)** — between Step 15 (bookkeeping) and Step 16 (PR push), substantive PRs (>200 LOC OR public API OR multi-file OR governance) fire `cross-review pre-push`. Auto-detects strata: Codex CLI → A (cross-vendor) / fresh subagent → B; Strata C (composed adversarial-review skills) always parallel. Anti-slop ≥7/10, max 3 fix rounds, verdict logged in PR.
- **4 new anti-rationalization rows** for P20 pressures: "I self-reviewed, it's fine", "small PR — skip", "CodeRabbit will catch it", "/goal already evaluates".
- **Scenario 7 in `tests/pressure-scenarios.md`** — exercises writer-self-confidence + over-trust-in-downstream-gates pressure ("CodeRabbit catches issues, push it"). 5 specific rationalizations + concrete tests that should fire.
- **Composition table**: new Step 15.5 row mapping to P20.

### Companion PRs
- broomva/workspace#55 — workspace canonical P20 definition (merged)
- broomva/bstack#14 — bstack SKILL.md / doctor.sh / primitives.md §P20 (merged)
- broomva/cross-review — new skill repo implementing the gate (published)

## [0.0.3.1] — 2026-05-13 (unreleased — P19 work)

### Added
- **Pre-flight Step 0: Mechanism selection (P19)** — agent applies the 2×2 decision matrix (`/goal` | P7 watcher | `/loop` | P12 persist) BEFORE Step 1 state snapshot. Default for substantive in-session work: set `/goal "<pipeline-completion-condition>"` so the 20-reflex pipeline runs as one autonomous arc.
- **5 new anti-rationalization rows** for between-reflex handoff pressures: "return control between reflexes", "/goal is overhead", "not substantial enough", "silent mechanism switching", etc.
- **Scenario 6 in `tests/pressure-scenarios.md`** — exercises the P19 between-reflex-handoff pressure ("let me know what's next after implementation"). Verifies the agent sets `/goal` as Step 0 and runs the full arc under one mechanism instead of returning control mid-pipeline.

### Companion PRs
- [broomva/workspace#52](https://github.com/broomva/workspace/pull/52) — defines P19 canonically (workspace AGENTS.md/CLAUDE.md/bstack-engine ledger)
- broomva/bstack — syncs P19 to SKILL.md/doctor.sh/primitives.md

## [0.0.3] — 2026-05-13

### Changed
- **Step 12 collapses to reference workspace P18** — Documentation discipline is now governed by `bstack` primitive **P18 Format-Follows-Audience**, not by an inline ritual in this skill. The prior "every `.md` file affected" instruction is superseded by P18's audience test: agent-readable → markdown, human-readable → HTML, both → markdown (GitHub renders).
- Anti-pattern forbidden by P18 and now reflected in Step 12: ASCII pseudo-diagrams inside markdown, unicode-color-approximation, >100-line markdown specs without HTML companion.

### Added
- **Scenario 5 in `tests/pressure-scenarios.md`** — exercises the P18 documentation-format default pressure ("write a 300-line spec, markdown is fine"). Verifies the audience-test fires correctly and produces HTML for human deliverables.

### Companion PRs
- [broomva/workspace#51](https://github.com/broomva/workspace/pull/51) — defines P18 canonically (workspace AGENTS.md/CLAUDE.md/bstack-engine ledger)
- [broomva/bstack#11](https://github.com/broomva/bstack/pull/11) — syncs P17 + P18 into bstack SKILL.md/doctor.sh/primitives.md

## [0.0.2] — 2026-05-13

### Closed (REFACTOR phase of TDD-for-skills)

Yesterday's verification surfaced 4 rationalization surfaces. All four now closed:

- **Step 8 "Brainstorm-or-not"** — replaced vibes-based "if user just chose" with a concrete two-condition test (enumerated steps OR explicit option-selection). Names the most common escape-hatch rationalization.
- **Step 19 split into 19 + 20** — Janitor (P9, P10) and Dogfood receipt (P11) are now separate reflexes. Pipeline count: **19 → 20**.
- **Inverse section** — three prose pause triggers replaced with machine-checkable tests (cross-repo via `git rev-parse --show-toplevel`, destructive op via P2 hook exit code, public-API-break via AST diff of `pub`/`export`/top-level `def`). "This feels important" explicitly forbidden as a pause trigger.
- **Primitive labels** — every step now has either a `(PN)` marker or an explicit `(no primitive — invariant: ...)` marker. No more unlabeled "guideline-shaped" reflexes.

### Added
- Three new anti-rationalization rows for stacked pressure (Section A):
  - "User already verified locally" — local ≠ deploy; signal not substitute
  - "Time pressure / hotfix" — discipline saves you precisely under pressure
  - "User has authority, defer instead of applying discipline" — cardinal rule is non-negotiable; authority operates on *what* to build, not *whether* to bypass gates
- `tests/pressure-scenarios.md` — 4-scenario verification corpus (moderate, stacked, cross-repo trigger, public-API-break trigger) + template for appending new scenarios

### PR
- [broomva/autonomous#1](https://github.com/broomva/autonomous/pull/1)

## [0.0.1] — 2026-05-12

### Added
- Initial release. bstack full-discipline operating mode.
- Workspace-specific operationalization of the universal [autonomous-senior-engineer prompt](https://broomva.tech/prompts/autonomous-senior-engineer).
- 19-reflex pipeline (pre-flight, plan, execution, pre-push, PR + merge, post-merge).
- Role-contract embedded verbatim from `broomva.tech/prompts/autonomous-senior-engineer` v1.0.
- Anti-rationalization tables: Section A (generic, writing-skills doctrine) + Section B (15 dump-extracted excuses with raw-dump line citations).
- Red flags STOP list.
- 9-item output contract per the canonical prompt's final-output spec.
- Composes with bstack P1–P16 + `broomva.tech/prompts/*` upstream prompts.

[Unreleased]: https://github.com/broomva/autonomous/compare/v0.0.2...HEAD
[0.0.2]: https://github.com/broomva/autonomous/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/broomva/autonomous/releases/tag/v0.0.1
