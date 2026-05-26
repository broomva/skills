# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3-pre] — 2026-05-20

M8 — canonical methodology reference. Closes BRO-1198 and completes Phronesis
Phase 1 (M0–M8). Docs-only release: no substrate behavior changes.

### Added — `docs/methodology.md`
- Ten-section canonical methodology reference (~12,000 words).
- Section 1: Why phronesis exists — the Bision empirical 100% failure mode
  (Sin tesis estratégica) and the consulting-IP-as-substrate thesis.
- Section 2: The 5-stage pipeline (intake → maturity → ideate → prioritize →
  roadmap) with per-stage gate enforcement (typed primitive → stage runner →
  linter backstop).
- Section 3: The 7 Phase-1 deliverables, mapped to producing stage and the
  L-rules each one carries. Documents `render_all` vs `render_with_gate`
  publication modes.
- Section 4: The 28 frameworks — 7 tables grouped by purpose (maturity,
  strategy, ideation, prioritization, ROI, AI-lifecycle, change). Marks the
  15 Phase-1 active vs 13 D-scope split. Documents selector algorithm +
  industry preferences + P7 hard cap at 5.
- Section 5: The 5 review gates — non-negotiable in both CLI and autonomous
  modes. Three-layer enforcement (Pydantic / stage / linter). No
  auto-approve on timeout in autonomous mode.
- Section 6: The Bision failure-mode linter — L1–L5 + P3/P7/P8 rules
  documented per-rule; no bypass-flag policy explained.
- Section 7: Anonymization by default — the canary release-gate (42 tokens
  × 21 anonymized files = 0 leaks at v0.1.2-pre). What gets stripped, what
  stays (framework allowlist preserves methodology terms), how loosening
  works (per-engagement explicit override).
- Section 8: Two operating modes — consultant CLI (default) vs autonomous
  Life Runtime endpoint (Phase 3 stub today, ADR-0001). Documented
  convergence + per-aspect differences in a table.
- Section 9: Engagement-driven discovery loop — two worked examples
  (`v0.0.2-m0.1` Tropico Renovables, `v0.1.1-pre` Broomva Silicon) showing
  the loop closing in single-PR batches.
- Section 10: Cross-engagement IP extraction — M7 pipeline (reflexive on
  `ENGAGEMENT_CONCLUDED`), 6-step end-to-end flow, queue layout,
  rule-of-three for candidate promotion, CLI re-run commands.
- Appendix A: file map (paths + responsibilities).
- Appendix B: validation gates table (local command + CI workflow).
- Appendix C: phase roadmap (Phase 1 complete, Phase 2 in progress,
  Phase 3 deferred).

### Modified — `SKILL.md`
- Status header updated: "Phase 1 (M0 — foundation scaffolding)" →
  "Phase 1 complete (`v0.1.2-pre`)" — substrate + 15 frameworks + 5 stages
  + 7 deliverables + L1–L5 linter + M7 extraction pipeline. Phase 2
  engagement-driven (M4 stage CLI + M5 autonomous-mode stub-to-real path).
- Documentation section: methodology reference moved from "(M8) pending"
  to the canonical first entry; `docs/methodology.md` link now resolves
  (was a dead link in `v0.1.2-pre`).

### Tests
- 458 unchanged. ruff + mypy strict (core/ tests/) + 458 pytests + framework
  lint all green at branching base `eecbc13` and at the head of this
  branch — docs-only change, no substrate impact.

### Linear
- BRO-1198 closed via this PR. Phronesis Phase 1 (M0–M8) fully complete.

## [0.1.2-pre] — 2026-05-08

OSS-readiness pass. No substrate behavior changes — purely packaging,
distribution, contributor-facing infra.

### Added — distribution
- `pyproject.toml` `version = "0.1.1-pre"` (was `"0.1.0-pre"` — now tracks the
  most-recent shipped tag); bumped to `0.1.2-pre` for this release.
- `[tool.hatch.build.targets.wheel]` includes all top-level packages
  (`core`, `runners`, `stages`) plus force-includes data dirs
  (`frameworks/`, `templates/`, `scripts/`). The Phase-1 wheel now ships
  end-to-end installable.
- `[tool.hatch.build.targets.sdist]` allowlist for clean source-distribution
  contents (no `.venv`, `dist/`, `engagements/<tenant>/` leakage).
- `[project.optional-dependencies] build = [build, twine]` for release
  workflow.
- Verified: `uv build` produces clean wheel + sdist; `uv pip install
  phronesis-0.1.1rc0-py3-none-any.whl` in a fresh Python 3.12 venv works
  end-to-end (all imports + CLI + 28 frameworks load).

### Added — `.github/workflows/release.yml`
GitHub Release workflow on tag push:
- Re-runs bision-prevention + canary release-gate suites
- Builds sdist + wheel
- Verifies the wheel installs in a fresh venv with 28 frameworks loadable
- Extracts release notes from CHANGELOG section matching the tag
- Creates GitHub Release with sdist + wheel attached
- Marks pre-releases automatically based on `pre`/`rc` in tag name

### Added — Contributor-facing OSS files
- `SECURITY.md` — vulnerability disclosure policy (mailto: contact@broomva.tech),
  out-of-scope clarifications for the hook-bypass and ungated-render flags.
- `.github/ISSUE_TEMPLATE/bug_report.md` — repro + environment + which L-rule
  fired (if any).
- `.github/ISSUE_TEMPLATE/feature_request.md` — engagement-driven framing
  preferred; substrate-layer checklist.
- `.github/PULL_REQUEST_TEMPLATE.md` — release-gate impact checklist.

### Changed — CI
- `.github/workflows/ci.yml` — added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
  env var. Forwards-compatible with GitHub's June 2026 Node.js 20 → 24 default
  flip without waiting for `setup-uv@v7`.

### Changed — README
- 6 status badges (CI, License, Python, GitHub release, tests passing, bstack layer)
- Updated status header from "Phase 1 — M0" to "Phase 2 — engagement-driven (`v0.1.1-pre`)"
- Added CHAOSS to the methodology list (BRO-1033)
- Added `npx skills add` install path
- Added Quickstart section with `init/status/lint/render` flow + Python API example
- Documented engagement-driven discovery loop with backreferences to
  `v0.0.2-m0.1` and `v0.1.1-pre` as worked examples

### Dependencies
- Bumped lower bounds to current stable majors:
  - `pydantic>=2.13.0` (was `>=2.7.0`)
  - `click>=8.3.0` (was `>=8.1.7`)
  - `rich>=14.0.0` (was `>=13.7.0`)
  - `pytest>=9.0.0` (was `>=8.2.0`)
  - `pytest-cov>=7.0.0` (was `>=5.0.0`)
  - `ruff>=0.15.0` (was `>=0.5.0`)
  - **`mypy>=2.0.0`** (was `>=1.10.0`) — major version bump; clean upgrade,
    zero source changes required (mypy 2.0 strict on 60 files + tests).

### Tests
- 399 unchanged. ruff/mypy strict clean across 60 source files.
- All 4 release-gate suites green: bision-prevention (9), canary (4),
  CLI smoke (8), framework-lint (28 frameworks).

### Linear
- Closes implicit OSS-readiness backlog. Next: PyPI publish workflow
  (Trusted Publishing / OIDC) — Phase 2 follow-up.

## [0.1.1-pre] — 2026-05-07

Phase 2 — engagement-driven refinements from the Broomva Silicon synthetic
engagement (Spec E agent-loop runtime, 2026-05-07). Closes BRO-1031 through
BRO-1035; defers BRO-1036 to backlog.

### Added — `frameworks/maturity/chaoss.yaml` (BRO-1033)
**CHAOSS Project Health Metrics** (Linux Foundation, 2017). Phase-1 maturity
framework for AI-BUILDING tenants where MIT CISR + Gartner AI both miss the
right axis. Five dimensions: contributor-diversity, release-cadence,
code-review-depth, downstream-adoption, governance-maturity. Output:
MaturityDimension. Relations: similar_to mit-cisr-digital + gartner-ai;
use_with wardley-mapping + real-options + three-horizons.

### Added — `TenantContext.industry: "tech"` (BRO-1031)
AI-infra / runtime / library / chip-design tenants no longer fall back to
`"other"`. Unblocks framework_selector + CHAOSS selection for the tech path.

### Added — `core/selector.py` `_INDUSTRY_PREFERENCES["tech"]` (BRO-1032)
Maturity → CHAOSS, Strategy → Wardley, ROI → real-options, AI-lifecycle →
QuantumBlack ML, Prioritization → RICE, Ideation → Value Prop Canvas. The
slate the Broomva Silicon engagement actually needed.

### Added — `BaselineSection.is_greenfield: bool` (BRO-1034)
Default `False` (incumbent metric). When `True`, baseline_value is interpreted
as zero-state declaration rather than measurement. The L5 invariant becomes
"declare zero-state explicitly" — protects against the failure where a team
SAYS they have a baseline but it's `0` because they didn't measure.

### Modified — `templates/pilot-plan.md.j2` greenfield rendering (BRO-1035)
Greenfield baselines render as `**[GREENFIELD]** zero-state declared` instead
of the numeric value. Adds a "Greenfield pilot" blockquote when any baseline
is greenfield. Footer now reports `(N greenfield, M incumbent)` accounting.
Section header: "Baselines **declared** before pilot start" (was: "captured")
— covers both incumbent + greenfield cases honestly.

### Backlog — BRO-1036
`lever_kind` option-value subtypes (defensive vs offensive vs real-option).
Single-engagement signal — defer until N≥5 option-shaped theses observed.

### Tests
- 387 → 399 (+12): test_tech_industry, 8 CHAOSS framework tests, 2 selector
  tech-preference tests, test_greenfield_baseline_explicit, greenfield template
  rendering test, d-scope total count bumped 27→28.
- ruff/mypy strict clean across 60 source files.
- All 4 release-gate suites green: bision-prevention (9), canary (4), CLI smoke (8), framework-lint (28 frameworks).

### Linear
- BRO-1031, BRO-1032, BRO-1033, BRO-1034, BRO-1035 closed via this PR.

## [0.1.0-pre] — 2026-05-07

**Phase 1 ship — Discovery-grade engagement runtime.**

Phase E (Integration + release gates) of the M1+M2+M3 parallel-worktree plan.
Closes M5 partial (CLI), M6 (synthetic fixture), M7 partial (anonymization
canary). Builds on Phases A-D (v0.0.3-m0.2 through v0.3.0-m3).

### Added — Persistence
- `EngagementJournal.save_jsonl(path)` / `load_jsonl(tenant, path)` —
  newline-delimited JSON. Phase 1 rewrites the whole file on save;
  Phase 3 will switch to true append-only writes via lago.

### Added — `tests/fixtures/`
- `tropico_renovables.py` — `build_tropico_engagement()` factory drives
  all 5 stage runners and produces an engagement that lints clean
  (zero L-errors). `deliverable_extras()` returns the typed-primitive
  context the render orchestrator needs to produce all 7 deliverables.

### Added — `core/anonymize.py`
- `AnonymizationPolicy` Pydantic model with strict-by-default fields:
  strip tenant_slug, strip tenant_name, strip personal_names,
  replace_currency_with_bands, replace_dates_with_relative,
  replace_locations_with_regions, redact_terms.
- `anonymize(text, policy, tenant)` function. Currency banding (Decimal
  → "low-6-figures USD"), date redaction (ISO/quarter/year → relative
  tokens), CO/LATAM city → `<latam-region>`, framework allowlist
  preserves Three Horizons / Wardley Mapping / etc.
- `carries_tenant_marker(text, tenant)` forensic helper for canary failures.

### Added — `runners/cli/`
- `runners/cli/__main__.py` — Click-based CLI exposing 4 commands:
  - `phronesis init <slug>` — creates `engagements/<slug>/{tenant.yaml,journal.jsonl}`
  - `phronesis status <slug>` — loads journal, prints derived state
  - `phronesis lint <slug>` — runs L1-L5 linter, `--strict` for CI gate
  - `phronesis render <slug>` — orchestrator render_with_gate (lint-blocked publication)
- `runners/cli/io.py` — tenant.yaml + journal.jsonl persistence helpers.
- Stage commands (intake/scan/ideate/prioritize/roadmap/review) explicitly
  out of Phase 1 scope; documented as M4 work. Phase 1 ships the Python API.

### Added — `tests/integration/`
- `test_bision_prevention.py` — RELEASE GATE. 9 tests:
  - clean Tropico fixture passes lint cleanly (proof-of-life)
  - L1: intake closed without thesis → blocks (Bision Failure 1, 100% obs)
  - L2: thin source mix or majority NOVELTY → blocks (Failure 2, 87%)
  - L3: blocking data readiness → blocks (Failure 3, 74%)
  - L4: PILOT_STARTED without pilot-plan deliverable → blocks (Failure 4, 61%)
  - L5: pilot without prior baseline OR retroactive baseline → blocks (Failure 5, 48%)
  - Compound failure: L1 + L4 + L5 collected together
- `test_anonymization_canary.py` — RELEASE GATE. 4 tests:
  - Zero tenant markers leak through anonymize() per deliverable
  - Currency amounts bucket to magnitude bands (no $640,000 verbatim)
  - Dates redact to relative tokens
  - Opt-out sanity (permissive policy preserves markers, proving strict policy works)
- `test_cli_smoke.py` — 8 tests via Click `CliRunner` with isolated tmp cwd:
  init, init-aborts-on-existing, status, lint, version flag, missing-engagement-error.

### Added — `.githooks/pre-push`
- Local release gate. Runs bision-prevention + canary before every push.
- Graceful degradation: skips if `uv` not on PATH (CI handles it).
- BLOCK exits 1 with a descriptive message naming the failing test +
  the file to investigate.

### Modified — `Makefile`
- `canary-check`, `bision-prevention`, `e2e` targets replaced their
  skip-with-message stubs with actual `pytest` invocations against
  `tests/integration/`.

### Tests
- 337 → 386 (+49): persistence (10), bision-prevention (9), canary (4),
  CLI smoke (8), anonymize unit (18).
- ruff/mypy strict clean across 59 source files.
- Pre-push hook passes locally end-to-end.

### Linear
- M5 partial (CLI), M6 (synthetic fixture), M7 partial (anonymization)
  closed. M5 stage commands + M7 full extraction pipeline → next phase.

## [0.3.0-m3] — 2026-05-07

Phase D (M3 — Deliverables + Linter) of the M1+M2+M3 parallel-worktree plan.
Closes BRO-1013. Builds on Phase C M2 stages (v0.2.0-m2).

### Added — `templates/`
7 Jinja2 deliverable templates with strict-undefined enforcement:
- `maturity-report.md.j2` (D.1 — worked template)
- `capability-heatmap.md.j2` (D.2)
- `use-case-dossier.md.j2` (D.3)
- `impact-effort-matrix.md.j2` (D.4)
- `roi-model.md.j2` (D.5)
- `innovation-roadmap.md.j2` (D.6)
- `pilot-plan.md.j2` (D.7)

Each footer surfaces the L-rule + P-rule invariants the deliverable carries.

### Added — `core/render.py`
- Jinja2 environment with `StrictUndefined` (missing context vars raise
  `UndefinedError` immediately rather than silently producing empty output)
- `as_currency` filter: Decimal → `$640,000` style
- `as_percent` filter: 0.234 → `23.4%`
- `render(slug, context)` — load + render one deliverable

### Added — `core/linter.py`
5 L-rule release-gate scanners + decorator-based registry:
- **L1** STRATEGIC_THESIS_REQUIRED — INTAKE_COMPLETED without thesis (Bision Failure 1, 100% obs)
- **L2** DIVERSE_IDEATION_SOURCES — <3 distinct sources OR >50% NOVELTY (Bision Failure 2, 87%)
- **L3** DATA_READINESS_GATE — use case with `readiness_band == blocking` (Bision Failure 3, 74%)
- **L4** ADOPTION_METRIC_REQUIRED — PILOT_STARTED but no pilot-plan deliverable rendered (Bision Failure 4, 61%)
- **L5** BASELINE_REQUIRED — PILOT_STARTED with zero prior BASELINE_CAPTURED events (Bision Failure 5, 48%)

`LintResult.has_errors / has_warnings / errors_for_rule(rule)`. Linter is the
BACKSTOP — stages already enforce gates at boundaries; the linter catches
engagements constructed manually without going through the stage runners.

### Added — `core/orchestrator.py`
- `render_all(engagement, output_dir, *, extra_context, write=True)` —
  renders all 7 deliverables; returns (paths, lint_result).
  `write=False` enables preview mode.
- `render_with_gate(engagement, output_dir, *, extra_context)` —
  publication path. Lint runs FIRST. Writes ONLY if zero L-errors.
  Otherwise returns ({}, lint_result) and output_dir is untouched —
  no partial state on disk.
- `build_roi_totals(roi_cells)` helper for template totals fields.
- `DELIVERABLE_SLUGS` canonical 7-name tuple.

### Tests
- 264 → 337 (+73): per-deliverable render tests (4-8 each), linter
  positive + negative cases per rule, aggregate runner, orchestrator
  happy path + lint-gated rejection (broken engagement → zero files
  written), build_roi_totals.
- ruff/mypy strict clean across 50 source files.

### Linear
- BRO-1013 (M3 Deliverables + Linter) closed.

## [0.2.0-m2] — 2026-05-07

Phase C (M2 — Stages) of the M1+M2+M3 parallel-worktree plan. Closes
BRO-1012. Builds on Phase B M1 frameworks (v0.1.0-m1).

### Added — `stages/`
- `stages/base.py` — `StageBase` ABC. Subclasses set `SLUG` + `NEXT_STAGE`
  class vars + implement `run()` and `request_review()`.
- `stages/intake.py` — Stage 1 (Intake). L1 GATE enforced in
  `request_review()` — cannot exit without `declare_thesis()`.
- `stages/scan.py` — Stage 2 (Maturity Scan). Gate: ≥1 dimension scored.
- `stages/ideate.py` — Stage 3 (Use-Case Ideation). L2 GATE — ≥3 distinct
  ideation sources AND ≤50% NOVELTY (Bision Failure 2, 87% observed).
- `stages/prioritize.py` — Stage 4 (Prioritization). Gate: ≥1 prioritized.
  Includes `compute_year1_net()` helper + `render_impact_effort_matrix()`.
- `stages/roadmap.py` — Stage 5 (terminal). L5 GATE — `design_pilot()`
  rejects if any baseline metric lacks a prior `BASELINE_CAPTURED` event.
  `conclude()` emits terminal `ENGAGEMENT_CONCLUDED`.

### Added — `stages/01_intake/prompts/`
- `strategic_thesis_elicitation.md` — 5-question follow-up to elicit a
  quantified, owned, time-bound StrategicThesis (rejects vague answers).

### Added — Cross-stage integration test
- `tests/unit/test_stages_integration.py` — drives all 5 stages on the
  synthetic Tropico Renovables fixture. Asserts journal sequence,
  replay reaches `state.is_concluded == True`, all L-rules fire correctly,
  7 deliverable slugs recorded as rendered.

### Tests
- 223 → 264 (+41): per-stage tests (gate-pass + gate-reject scenarios),
  StageBase ABC contract, full cross-stage integration.
- ruff clean, mypy strict clean across 42 source files.

### Linear
- BRO-1012 (M2 Stages) closed.

## [0.1.0-m1] — 2026-05-07

Phase B (M1 — Frameworks Library) of the M1+M2+M3 parallel-worktree plan.
Closes BRO-1011. Builds on Phase A foundations (v0.0.3-m0.2).

### Added — `frameworks/`
14 Phase-1 framework YAMLs:
- **strategy/** three-horizons (McKinsey 1999), wardley-mapping (Wardley 2018)
- **maturity/** mit-cisr-digital (MIT CISR 2019), gartner-ai (Gartner 2024)
- **ideation/** jobs-to-be-done (Christensen/Strategyn 2003), value-prop-canvas (Strategyzer 2014)
- **prioritization/** rice (Intercom 2016 — worked template), ice (GrowthHackers 2009), wsjf (SAFe/Reinertsen 2009)
- **roi/** unit-economics (SV canon 2010), npv-dcf (Modigliani-Miller 1958), real-options (Trigeorgis 1999)
- **ai-lifecycle/** quantumblack-ml (McKinsey QuantumBlack 2023), andrew-ng-pipeline (DeepLearning.AI 2021)

13 D-scope stubs marked `is_d_scope: true` (Phase 2 placeholders): where-to-play-how-to-win,
five-forces, mckinsey-7s, forrester-data, lean-canvas, business-model-canvas, cost-of-delay,
owner-earnings, ms-responsible-ai, google-pair, kotter-8-steps, adkar, mckinsey-influence.

### Added — `frameworks/_schema.yaml`
JSON Schema source-of-truth for the framework-as-code contract (P1). Required fields:
id (kebab-case), name, source_firm, source_year, source_citation, category (7-enum),
purpose, inputs, dimensions, scoring_rubric, output_shape (8-enum typed primitive),
when_to_use (3-5 items), when_NOT_to_use (2-3 items), example_application,
relationships (similar_to/use_with/upstream_from/downstream_to), citations.

### Added — `core/frameworks.py`
- `Framework` Pydantic model with `populate_by_name=True` so YAMLs mixed-case
  `when_NOT_to_use` maps cleanly via alias to Python `when_not_to_use`
- `load_framework(path)` — two-layer validation: jsonschema (rich errors)
  then Pydantic (clean Python objects)
- `load_all()` — discovers all YAMLs under `frameworks/`, dedupe-checks ids

### Added — `core/selector.py`
- `propose_frameworks(industry, maturity_band, scope_keywords, cap=4)`
- Industry-specific preferences for banking, energy-utilities, fin-services,
  insurance, construction; default fallback for unmapped industries
- Defaults to maturity + prioritization coverage on every engagement
- **P7 enforcement**: hard cap at 5 frameworks per engagement
- D-scope frameworks excluded (verified via `test_d_scope_frameworks_excluded`)
- `FrameworkSelection` emitted with rationale grounded in framework purpose

### Added — `scripts/lint_frameworks.py`
Validates all 27 framework YAMLs + cross-checks every `relationships.{kind}`
target resolves to a known framework slug or documented deliverable suffix.
`make framework-lint` invokes it (replaces M1 skip-with-message).

### Tests
- 100 → 223 (+123): one test file per framework (7 tests each), schema
  loader rejection cases, D-scope marker correctness, registry totals,
  selector basic constraints + P7 cap + industry preferences + D-scope
  exclusion across 7 industries + default coverage.
- ruff clean, mypy strict clean across 35 source files.

### Linear
- BRO-1011 (M1 Frameworks Library) closed.

## [0.0.3-m0.2] — 2026-05-06

Phase A foundations of the M1+M2+M3 parallel-worktree plan. Closes the
4 deferred design gaps surfaced by the Tropico Renovables synthetic
engagement (v0.0.2-m0.1) and unblocks parallel M1+M2+M3 dispatch.

### Added — `core/events.py`
Typed Pydantic payload schemas for all 16 EventKinds (Gap #11):
`EngagementStartedPayload`, `IntakeCompletedPayload`, `InterviewLoggedPayload`,
`DocumentIngestedPayload`, `StrategicThesisDeclaredPayload`,
`MaturityDimensionScoredPayload`, `UseCaseProposedPayload`,
`UseCasePrioritizedPayload`, `RoadmapStepProposedPayload`,
`BaselineCapturedPayload`, `PilotStartedPayload`,
`DeliverableRenderedPayload`, `StageReviewRequestedPayload`,
`StageReviewApprovedPayload`, `StageReviewRevisedPayload`,
`EngagementConcludedPayload`. `payload_for(kind)` returns the class.
Decimal-bearing fields use `str` for journal portability (JSONL).

### Added — `core/engagement.py`
- `EngagementJournal` — append-only event log scoped to one tenant (Gap #12)
- `EngagementState` — derived state from journal replay (read-only)
- `_apply(state, event)` — pure event-application function
- `EngagementJournal.replay()` — pure fold; idempotent; doesn't mutate journal
- `Engagement` — aggregate root: tenant + journal + emit() (Gap #13)
- `Engagement.emit(kind, stage, payload)` — only mutation path; payloads
  validated via JournalEvent's typed-payload validator before append.

### Added — `core/revision.py`
- `retract_to_revision_point(engagement, stage)` — replay-safe stage revision (Gap #19)
- Preserves review markers (`STAGE_REVIEW_*`) as audit trail per P5
- Cross-stage events untouched
- Phase 3 will switch to tombstone-based compaction (lago journal pattern)

### Modified — `core/types.py`
- `JournalEvent.payload_matches_kind` model_validator — re-validates payload
  against `payload_for(kind)` schema at construction. Wrong-shape payloads
  raise `ValidationError` before append.

### Tests
- 57 → 100 (+43): typed-payload positive/negative cases, full replay
  sequence, idempotency, non-mutation properties, Engagement aggregate,
  emit() validation, revision retraction, audit-trail preservation,
  cross-stage isolation.
- All gates green: ruff, mypy strict, 100/100 tests.

### Linear
- BRO-1011 (M1) and BRO-1012 (M2) and BRO-1013 (M3) prerequisites met.

## [0.0.2-m0.1] — 2026-05-06

Engagement-driven gap closures discovered during a synthetic Phase-1
walk-through (Tropico Renovables S.A.S., 62 MW renewable IPP, Colombian
Caribbean coast). All 5 stages run end-to-end against the M0 substrate
with L1–L5 + P3 + P8 firing as designed.

### Fixed
- **JournalEvent ergonomics (Gap #1).** `event_id` and `timestamp` now have
  `default_factory` so callers don't construct ULIDs by hand. The previous
  shape made it tempting to call `str(ulid.ULID())`, which trips Pydantic's
  buffer protocol because ulid-py's `ULID` extends `MemoryView`. Internal
  `_new_event_id` helper wraps `ulid.new()`.

### Added
- **`StrategicThesis.thesis_id` (Patch A).** Auto-generated ULID so journal
  events stably reference the thesis even after revisions.
- **`Score` range validation (Patch C).** `value` must lie within `scale`
  inclusive interval; `scale` must be ordered `(lo < hi)`. Silently-wrong
  rubrics no longer propagate into deliverables.
- **`MaturityDimension` evidence parity (Patch B).** Both `current_score`
  and `target_score` must carry non-empty `evidence`. Targets without
  citations are wishful thinking — must be benchmarked, regulated, peer-
  comparable, or thesis-derived.
- **`UseCase.status` audit trail (Patch D).** New
  `Literal["proposed", "prioritized", "deferred", "dropped"]` field with
  `status_rationale: str | None`. `dropped` and `deferred` require non-empty
  rationale. Preserves the engagement audit trail when a sponsor kills a
  candidate at any gate.
- **`TenantContext.industry` enum (Gap #2).** `energy-utilities` variant
  added. Previously a renewable IPP, transmission operator, or water
  utility had to fall back to `other`, losing typed signal that
  `framework_selector` (M1) needs to propose industry-relevant slates.

### Tests
- 47 → 57 unit tests (+10), all green. ruff clean. mypy clean.
- New regression tests exercise the full L1–L5 + P3 path on each new
  validator. `test_event_id_auto_generated` documents the ulid-py footgun
  in the test corpus so the next engineer doesn't re-discover it.

### Linear
- Engagement-driven; no new tickets opened. Follow-on M1–M3 design gaps
  (typed payloads per EventKind, EngagementJournal replay, Engagement
  aggregate, revision protocol) batched into the M1+M2+M3 plan when written.

## [0.0.1-m0] — 2026-05-06

### Added
- **M0 Foundation** — repo scaffolding, top-level files, build config, agent-facing skill card, 8 ADRs.
- `core/types.py` with **19 typed primitives across 5 layers**:
  - Layer 1 (atomic): `Citation`, `Score`, `Finding` (P3), `Recommendation` (P8 + L4), `AdoptionMetric`, `BaselineSection`, `DataReadinessAssessment`, `IdeationSource`, `StrategicThesis` (L1)
  - Layer 2 (deliverable aggregates): `UseCase`, `MaturityDimension`, `CapabilityCell`, `RoiCell`, `RoadmapStep`, `PilotDesign` (L4 + L5)
  - Layer 3 (event sourcing): `EventKind` (16 canonical kinds), `JournalEvent`
  - Layer 4 (review gate): `StageReview` (P5)
  - Layer 5 (engagement context): `TenantContext` (P6), `FrameworkSelection` (P7)
- 8 ADRs (`docs/adr/0001..0008-*.md`) covering all major design decisions.
- Pre-commit hook enforcing P6 (tenant data isolation) + secret-assignment scan.
- Makefile with `smoke` / `check` / `e2e` / `framework-lint` / `canary-check` / `bision-prevention` / `doctor` / `lint` / `type-check` targets (skip-with-message for milestones not yet shipped).
- 47 unit tests across 5 test files; ruff clean; mypy clean.
- Pyproject.toml configured with Pydantic 2.7+, Jinja2, PyYAML, ulid-py, click, rich; ruff/pytest/mypy strict configured.

### Architecture
- Substrate / product split (mirrors finance-substrate → investment-management).
- Layer 7 of bstack — depends downward only.
- Apache-2.0 license.
- Phase 1 of 3 — Phase 2 (real engagements) and Phase 3 (Life Rust crate) outlined in design spec.

### Bision-failure-prevention readiness
M0 ships the typed primitives required for L1-L5. Linter rules + release-gate test land in M3.

### Linear
- Project: https://linear.app/broomva/project/phronesis-ai-native-advisory-practice-8007a216a186
- M0 issues closed: BRO-1007 (M0.1), BRO-1008 (M0.2), BRO-1009 (M0.3), BRO-1010 (M0.4)

## [Unreleased]

### Coming in M1 (Frameworks Library)
- `frameworks/_schema.yaml` + 14 Phase-1 framework YAMLs + 13 D-scope stubs
- `core/selector.py` — framework_selector primitive (P7)
- Property tests: every YAML schema-valid

## [0.1.0-pre] — TBD (Phase 1 ship)

Initial pre-release covering all of Phase 1 (M0-M8). Synthetic-fixture-validated only — no real engagements yet.
