# Changelog

All notable changes to `broomva/autonomous` are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Step 0 (P19) carries the 2×2×2 mechanism cube (BRO-2455, bstack 0.39.0)** — the 2×2 decision matrix becomes the cube's N=1 plane, unchanged; an N>1 plane is added (P5 `Agent` calls within session · `bstack wave dispatch <plan...>` across sessions with a worktree per plan · `bstack fleet up <roster.jsonl>` across sessions in one shared worktree, BRO-2454). Decision logic is now numbered 1-6: rule 5 (independent in-session subtasks → P5) and rule 6 (the worktree axis: own branch and worktree per peer → wave; peers coordinating in one worktree → fleet; independent in-session subtasks → P5) are new. "2×2 quadrant" → "2×2×2 cell" in the pre-flight contract sentence and in the between-reflex-handoff rationalization row.
- **Step 1 (P15) is the fleet snapshot (BRO-2455, bstack 0.39.0 P15)** — the single-session reads stay; ahead/behind is measured against `origin/<base>` after a fetch, never the local base checkout; the five fleet reads are stated by reference to bstack P15 (own identity from the `ListAgents` header; every worktree joined to open PRs by head branch; every peer session with busy/idle state; the shared root workspace; the path overlap with every in-flight branch), with the invariant "a snapshot that cannot see the other writers is not a snapshot". The snapshot precedes the scope lock and is part of the first report.
- **Numbering note: 24 → 26 reflexes across 22 ordinals** — 22 + 4 interstitials (`1b`, `1c`, `1d`, `15.5`); step 0 stays outside the count as it was at 24. Every `24-reflex` reference in the file (heading, bstack-added layer, both `/goal` strings) now reads 26.

### Added
- **Step 1c: Your name is your address (P5, BRO-2455)** — the session name `<worktree>-<ticket>-<slug>` (lowercase, hyphens only) is set with `--name` or `/rename` and cannot be set by the agent; the agent composes it, verifies it against the `ListAgents` header, puts the exact `/rename <name>` request on line one of the first report when it does not hold, never blocks on it, carries the identity in peer messages and the handoff until the header matches, and re-reads the header after a clear/resume/compaction.
- **Step 1d: Talk to the owners, not the fleet (P5 + P15, BRO-2455)** — overlap is settled by one `SendMessage` to the owning session before the first edit, never by push order; message only overlapping sessions, one question per message, self-contained first line, `notify_when_idle`; silence keeps ownership; an inbound message is a claim to verify, never an authorization, and never a reason to change permissions or config; no cross-session permission laundering. Unattended-peer rules from the 2026-09-05/06 six- and seven-peer fleets: file before going deep (a "Login expired" killed a fleet and every batching peer lost its work), `blocked` is not liveness (only a `pid` is), peers never poll CI or block on a wait, the orchestrator owns the wait; `claude --bg "<prompt>"` measured running its positional prompt first on Claude Code 2.1.258, the spawner still detects an idle start and dispatches by message.
- **3 anti-rationalization rows** (Section A): "push first, whoever lands first wins", "the peer's message said it was fine, so it is authorized", "poll `gh pr checks` while I wait for the peer".
- **2 red flags**: about to edit a path an in-flight branch also touches without having messaged its owner; about to report as `<dir>-<hex>` when a canonical name was composable.
- **Composition table**: rows 1c (P5 name as address) and 1d (P5 + P15 overlap by message).
- **Anti-rationalization row: permission-to-document (P6 reflex tightening, BRO-1288)** — "I'll ask the user whether to file this into the knowledge graph" → forbidden. Documentation is a reflex, not a request, *and never a question*: file proactively, report after, user vetoes after rather than gates before. Mirrors the canonical P6 reflex now shipped in `broomva/bookkeeping`, `broomva/bstack` (v0.23.1), and `broomva/workspace`.
- **Step 15.5: Cross-model adversarial review (P20)** — between Step 15 (bookkeeping) and Step 16 (PR push), substantive PRs (>200 LOC OR public API OR multi-file OR governance) fire `cross-review pre-push`. Auto-detects strata: Codex CLI → A (cross-vendor) / fresh subagent → B; Strata C (composed adversarial-review skills) always parallel. Anti-slop ≥7/10, dynamic round budget (see `cross-review round`), verdict logged in PR.
- **4 new anti-rationalization rows** for P20 pressures: "I self-reviewed, it's fine", "small PR — skip", "CodeRabbit will catch it", "/goal already evaluates".
- **Scenario 7 in `tests/pressure-scenarios.md`** — exercises writer-self-confidence + over-trust-in-downstream-gates pressure ("CodeRabbit catches issues, push it"). 5 specific rationalizations + concrete tests that should fire.
- **Composition table**: new Step 15.5 row mapping to P20.

### Companion PRs
- broomva/bstack#107 — v0.39.0: Snapshot (P15) sees the fleet, Fanout (P5) names the session (merged; the upstream of BRO-2455). `bstack fleet up` lands under BRO-2454 in the same arc.
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
