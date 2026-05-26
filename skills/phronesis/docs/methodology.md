# Phronesis — Methodology Reference

**Status:** v0.1.2-pre — Phase 1 complete (M0–M8). Phase 2 engagement-driven refinements ongoing.
**Audience:** Engagement operators (consultant or autonomous Life Runtime endpoint), framework contributors, and anyone evaluating phronesis as the substrate for an AI/digital advisory practice.
**Companion docs:** [`SKILL.md`](../SKILL.md) (agent-facing skill card), [`README.md`](../README.md) (install + quickstart), [`CHANGELOG.md`](../CHANGELOG.md) (per-release notes), [`docs/adr/`](adr/) (8 architectural decision records).

This document is the canonical methodology reference for phronesis. It describes the *why*, the *what*, and the *how* of running an AI/digital consulting engagement through the substrate — independent of the code that implements it. Where the doc references an architectural decision, the decision lives in an ADR; the prose here explains the choice in operator language.

## Contents

1. [Why phronesis exists](#1-why-phronesis-exists)
2. [The 5-stage pipeline](#2-the-5-stage-pipeline)
3. [The 7 deliverables](#3-the-7-deliverables)
4. [The 28 frameworks](#4-the-28-frameworks)
5. [The 5 review gates](#5-the-5-review-gates)
6. [The Bision failure-mode linter](#6-the-bision-failure-mode-linter)
7. [Anonymization by default](#7-anonymization-by-default)
8. [Two operating modes](#8-two-operating-modes)
9. [Engagement-driven discovery loop](#9-engagement-driven-discovery-loop)
10. [Cross-engagement IP extraction](#10-cross-engagement-ip-extraction)

---

## 1. Why phronesis exists

### The empirical failure that named the skill

Bision Consulting (Bogotá, 2026) audited a population of AI / digital-transformation engagements at C-level and surfaced five failure modes that recur with disturbing regularity:

| # | Failure (paraphrased from the Bision audit) | Empirical frequency |
|---|---|---|
| 1 | Sin tesis estratégica — "hagamos algo de IA" with no economic lever | **100%** |
| 2 | Casos de uso mal priorizados — selection by novelty rather than impact | **87%** |
| 3 | Datos no preparados — pilots launched on data the org can't actually deliver | **74%** |
| 4 | Desconexión negocio-tecnología — high model accuracy, near-zero adoption | **61%** |
| 5 | Sin medición de ROI — no baseline at start, no defensible claim at end | **48%** |

Failure 1 hit *every* audited engagement. That's not a quality issue with a particular consultancy. That's a *structural* gap in how AI/digital engagements are scoped. The lever-free engagement is the modal engagement.

Phronesis exists to make each of those failures **structurally impossible**, not merely discouraged. Discouragement happens in retrospectives; structure happens at construction time. Pydantic models that reject malformed primitives, stage runners that raise `ValueError` at gate boundaries, a linter that scans the journal and refuses to render deliverables — every one of those mechanisms is aimed at a specific Bision failure. The mapping is exact:

| Failure | Type primitive | Stage gate | Linter rule | ADR |
|---|---|---|---|---|
| 1 | `StrategicThesis` (required at Stage 1) | `IntakeStage.request_review()` | L1 STRATEGIC_THESIS_REQUIRED | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| 2 | `IdeationSource` enum (5 variants) + diversity check | `IdeateStage.request_review()` | L2 DIVERSE_IDEATION_SOURCES | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| 3 | `DataReadinessAssessment` on every `UseCase` | journal-time check in scan/ideate | L3 DATA_READINESS_GATE | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| 4 | `AdoptionMetric` required on `PilotDesign` + `Recommendation` | type-level on construction | L4 ADOPTION_METRIC_REQUIRED | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| 5 | `BaselineSection` non-empty on `PilotDesign`; journal-ordering invariant | `RoadmapStage.design_pilot()` | L5 BASELINE_REQUIRED | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |

The `tests/integration/test_bision_prevention.py` suite encodes the empirical claim: an engagement that goes through phronesis end-to-end cannot exhibit any of the 5 failure modes. The 9-test release gate constructs deliberately-broken engagements (intake without thesis, novelty-majority ideation, blocking data readiness, pilot without baseline) and verifies the substrate blocks each one. The gate ships green from day one and re-runs on every push.

### The consulting-IP-as-substrate thesis

Top-firm consulting methodology — McKinsey Three Horizons, MIT CISR digital maturity, Strategyzer Value Proposition Canvas, Intercom RICE, SAFe WSJF, QuantumBlack ML lifecycle, Wardley Mapping, CHAOSS project health — is *already* the right answer for most discovery-grade engagements. The problem isn't that the methods are wrong; it's that they live as PowerPoint frameworks and consultant intuition, not as code that can be invoked, composed, validated, and audited.

Phronesis encodes those methodologies as **typed primitives** (Pydantic models, Rust-clean per [ADR 0001](adr/0001-python-substrate-life-engine-phased.md)) and **runnable stages** (event-sourced journal per [ADR 0003](adr/0003-event-sourced-engagement-journal.md), human-review-gated per [ADR 0004](adr/0004-five-review-gates-non-negotiable.md)). The substrate offers the choices a partner-level consultant would offer; the stage runners enforce the discipline a partner-level consultant would enforce.

The substrate is plural by design. The framework directory ([ADR 0002](adr/0002-frameworks-organized-by-purpose.md)) is organized by consulting *purpose* (maturity, strategy, ideation, prioritization, ROI, AI-lifecycle, change) rather than by source firm — that way a consultant searching for "what helps me prioritize?" finds RICE alongside ICE and WSJF as a comparison set, not as a single firm's orthodoxy. Source credit is preserved per file via the `source_firm:` frontmatter; the directory shape teaches plural thinking.

### What phronesis is *not*

* **Not a code-generator for AI products.** Phronesis produces *plans* and *recommendations*; the running system is built downstream by whatever team takes the dossier and ships it. The substrate explicitly refuses to start an engagement without a strategic thesis (L1), so "build me some AI" is not a valid invocation.
* **Not a replacement for human judgment at decision boundaries.** Every stage exits through a human review gate ([ADR 0004](adr/0004-five-review-gates-non-negotiable.md)). Autonomous mode does not auto-approve on timeout — it pauses ([ADR 0004](adr/0004-five-review-gates-non-negotiable.md), Consequences).
* **Not a change-management or organizational-design tool.** The change-management frameworks (ADKAR, Kotter 8-Steps, McKinsey Influence) ship as D-scope stubs only; the active substrate is scoped to discovery and prioritization, not transformation execution.
* **Not a personal-decision-support skill.** For individual life or career decisions, see the `strategy-skills` family (decision logs, pre-mortems, braindumps). Phronesis is for org-scale advisory work.

---

## 2. The 5-stage pipeline

An engagement runs through exactly five stages, in this order:

```
  Stage 1            Stage 2           Stage 3            Stage 4              Stage 5
+----------+      +----------+      +----------+      +-----------+      +-----------+
|  Intake  | -->  |   Scan   | -->  |  Ideate  | -->  | Prioritize| -->  |  Roadmap  |
+----------+      +----------+      +----------+      +-----------+      +-----------+
     |                 |                 |                  |                   |
     v                 v                 v                  v                   v
 [review gate]    [review gate]    [review gate]      [review gate]       [review gate]
 (L1 enforced)    (≥1 dimension)   (L2 enforced)      (≥1 prioritized)    (L4 + L5)
```

Every stage advances by emitting an event to the engagement journal ([ADR 0003](adr/0003-event-sourced-engagement-journal.md)). The journal is the source of truth; engagement state is *always* derived by replaying the events. Pause/resume is trivial — load the journal, replay, continue. Audit is the persistence format itself.

### Stage 1 — Intake

**Purpose:** Establish scope, capture interviews and documents, **declare the strategic thesis**.

The intake stage cannot exit without a `StrategicThesis` event in the journal. That's not a soft preference — it's enforced at the type level (`StrategicThesis` requires non-empty `evidence`, non-zero `magnitude_estimate`, a named `decision_rights_owner`, and a specific `lever_kind`) and at the stage level (`IntakeStage.request_review()` raises `ValueError` if `state.thesis_id is None`).

The substrate ships a [strategic-thesis-elicitation prompt](../stages/01_intake/prompts/strategic_thesis_elicitation.md) — a 5-question follow-up the consultant uses with the sponsor (CDO / COO / CFO equivalent) to elicit a thesis that satisfies L1:

1. What measurable outcome would let you say "this engagement was worth it"?
2. What's the dollar magnitude (revenue / cost / risk / speed) of that outcome over the next 12 months?
3. How did you arrive at that number?
4. Is this a "now" (h1), "next" (h2), or "later" (h3) lever?
5. Who has authority to approve a $X-budget AI initiative aimed at this lever?

Vague answers ("operational excellence", "do AI better") are rejected — the prompt pushes back until the consultant has a quantified, owned, time-bound thesis. The substrate makes "hagamos algo de IA" structurally impossible.

**Deliverables seeded:** stakeholder map, interview guide, strategic thesis.
**Events emitted:** `ENGAGEMENT_STARTED`, `INTERVIEW_LOGGED` (per interview), `DOCUMENT_INGESTED` (per doc), `STRATEGIC_THESIS_DECLARED`, `INTAKE_COMPLETED`.
**Gate (L1):** `INTAKE_COMPLETED` cannot fire without a prior `STRATEGIC_THESIS_DECLARED`.

### Stage 2 — Maturity Scan

**Purpose:** Score the tenant along the dimensions the chosen maturity framework prescribes. Output is a capability heatmap and a gap analysis.

The framework selector (`core/selector.py`) proposes a maturity framework based on the tenant's `industry` and engagement scope. Industry preferences are encoded:

| Industry | Default maturity framework |
|---|---|
| banking | MIT CISR Digital |
| insurance | MIT CISR Digital |
| fin-services | MIT CISR Digital |
| energy-utilities | Gartner AI |
| construction | Gartner AI |
| tech (AI-BUILDING) | CHAOSS (Linux Foundation) |
| other / default | MIT CISR Digital |

The `tech` slate is a Phase-2 engagement-driven addition ([CHANGELOG v0.1.1-pre](../CHANGELOG.md#011-pre--2026-05-07), BRO-1031..1033) — surfaced when the Broomva Silicon synthetic engagement found MIT CISR's industrialized-vs-platform axis didn't fit an AI-infra tenant. CHAOSS measures the right thing for that tenant: contributor diversity, release cadence, code review depth, downstream adoption, governance maturity.

Each `MaturityDimension` carries a `current_score` and a `target_score`, both with non-empty `evidence` ([P3 — citations first-class](../core/types.py)). A target without evidence is wishful thinking; the substrate rejects it at construction time.

**Deliverables seeded:** maturity report (D.1), capability heatmap (D.2), gap analysis.
**Events emitted:** `MATURITY_DIMENSION_SCORED` (one per dimension), `STAGE_REVIEW_REQUESTED`.
**Gate:** at least one `MaturityDimension` scored; the review gate cannot fire on an empty scan.

### Stage 3 — Use-Case Ideation

**Purpose:** Surface candidate AI/data initiatives. Each candidate is a `UseCase` with a problem statement, hypothesis, solution sketch, expected value, cost estimate, framework lens, ideation source, and data readiness assessment.

The ideation stage enforces **L2 — diverse ideation sources**. Each use case carries an `IdeationSource` enum value drawn from:

* `BUSINESS_PAIN` — surfaced from a documented operational pain point
* `DATA_OPPORTUNITY` — surfaced from an under-leveraged data asset
* `REGULATORY_PRESSURE` — driven by an upcoming compliance deadline
* `COMPETITIVE_RESPONSE` — driven by a market move from a peer
* `NOVELTY` — surfaced because the technology is new and interesting

`NOVELTY` is the failure mode Bision Failure 2 names: pilots chosen "because LLM is hot," not because they pull on the thesis lever. L2 rejects an ideation set with **fewer than 3 distinct sources** or with **NOVELTY share > 50%**. That blocks the audited failure pattern at the gate, not at the retrospective.

Each `UseCase` also carries a `DataReadinessAssessment` (L3). The readiness bands are:

* `pilot-ready` — data is in place; pilot can start
* `needs-prep` — data exists but requires a prep phase before pilot
* `blocking` — data does not exist or is unavailable

L3 fires when any use case ranked as a candidate has `readiness_band == "blocking"` without an explicit `prep_phase_required: True` and a `prep_phase_estimated_weeks` value. The pattern that fails — "we'll deal with the data later" — becomes a typed validation error.

**Deliverables seeded:** prioritized use-case dossier (D.3) with JTBD + VPC framings.
**Events emitted:** `USE_CASE_PROPOSED` (per candidate), `STAGE_REVIEW_REQUESTED`.
**Gate (L2 + L3):** review cannot exit on a single-source ideation set or with blocking data readiness.

### Stage 4 — Prioritization

**Purpose:** Rank the proposed use cases using a quantitative framework (RICE, ICE, or WSJF) and project ROI using a financial framework (Unit Economics, NPV/DCF, or Real Options).

Prioritization is where the engagement converts qualitative intuition into a defensible ranking the CFO can read. The default prioritization framework is **RICE** (Reach × Impact × Confidence ÷ Effort) — it produces a transparent number that survives sponsor scrutiny. ICE is the lighter-weight variant for early-stage engagements; WSJF is the cost-of-delay-aware variant for SAFe-aligned organizations.

The ROI framework choice depends on the engagement shape:

* **Unit Economics** — when the use case has a clear per-unit cost-and-revenue model (e.g., per-ticket deflection, per-claim automation)
* **NPV/DCF** — when the use case has a multi-year cash-flow profile and the sponsor is finance-literate
* **Real Options** — when the use case carries genuine option value (kill if signal is weak; double down if signal is strong) and the sponsor will tolerate option-pricing language

ROI cells are typed as `RoiCell` with `Decimal` arithmetic ([ADR 0006](adr/0006-decimal-for-money.md)) — no floating-point drift across 5-year projections. Sensitivity analysis (`sensitivity_low`, `sensitivity_high`) is required, not optional; a point estimate without bounds is a vibe, not a decision.

**Deliverables seeded:** Impact-vs-Effort Matrix (D.4), ROI Model with sensitivity (D.5).
**Events emitted:** `USE_CASE_PRIORITIZED` (per ranked use case), `STAGE_REVIEW_REQUESTED`.
**Gate:** at least one use case prioritized; review cannot exit on an empty ranking.

### Stage 5 — Roadmap Synthesis

**Purpose:** Allocate the prioritized use cases across Three Horizons (h1 / h2 / h3), design the pilot for each, **capture the baselines** before the pilot starts.

Roadmap is the terminal stage. It produces the innovation roadmap (D.6) and the pilot plan (D.7), and it enforces **L5 — baselines before pilots**. The journal-level invariant is hard: `BASELINE_CAPTURED` must precede `PILOT_STARTED` for the same use case. Retroactive baselines — "we'll measure where we were after we launch" — are the modal Bision Failure 5 pattern, and the substrate refuses to render the pilot plan if any pilot lacks a prior baseline event.

The QuantumBlack ML lifecycle is the default AI-lifecycle framework for roadmap synthesis; Andrew Ng's pipeline is the alternative for engagements where the rigor is excessive. Each pilot has a typed `PilotDesign` with hypothesis, null hypothesis, cohort definition, success criteria, kill criterion, learning objectives, baselines (L5), and an `AdoptionMetric` (L4 — distinct from the technical success metric, owned by a business stakeholder, measured by business-side instrumentation).

The greenfield variant ([CHANGELOG v0.1.1-pre](../CHANGELOG.md#011-pre--2026-05-07), BRO-1034) handles the case where no incumbent metric exists — a brand-new product line with zero production traffic. `BaselineSection.is_greenfield = True` reinterprets the L5 invariant as "declare zero-state explicitly" rather than "capture incumbent metric." That protects against the subtler failure where a team SAYS they have a baseline but it's `0` because they didn't measure.

The terminal `ENGAGEMENT_CONCLUDED` event fires from `RoadmapStage.conclude()`. That event is the reflexive trigger for the cross-engagement IP extraction pipeline (see §10).

**Deliverables seeded:** innovation roadmap (D.6), pilot plan (D.7).
**Events emitted:** `ROADMAP_STEP_PROPOSED` (per step), `BASELINE_CAPTURED` (per baseline), `PILOT_STARTED` (per pilot), `DELIVERABLE_RENDERED` (per rendered file), `STAGE_REVIEW_REQUESTED`, `ENGAGEMENT_CONCLUDED`.
**Gate (L4 + L5):** every pilot has an adoption metric AND a prior baseline. Retroactive baselines rejected.

---

## 3. The 7 deliverables

Phase 1 ships **seven Discovery-grade deliverables**. They are produced by the orchestrator (`core/orchestrator.py`) via Jinja2 templates (`templates/*.md.j2`) with `StrictUndefined` enforcement — missing context variables raise `UndefinedError` immediately rather than silently producing empty output.

| # | Deliverable | Produced in stage | Drives the failure-mode rule | Template |
|---|---|---|---|---|
| 1 | Maturity Report | Stage 2 (Scan) | — (substrate input) | `templates/maturity-report.md.j2` |
| 2 | Capability Heatmap | Stage 2 (Scan) | — (substrate input) | `templates/capability-heatmap.md.j2` |
| 3 | Use-Case Dossier | Stage 3 (Ideate) | L2 (diverse ideation sources) + L3 (data readiness) | `templates/use-case-dossier.md.j2` |
| 4 | Impact-vs-Effort Matrix | Stage 4 (Prioritize) | — (substrate input) | `templates/impact-effort-matrix.md.j2` |
| 5 | ROI Model with Sensitivity | Stage 4 (Prioritize) | L5 backstop (baseline-aware) | `templates/roi-model.md.j2` |
| 6 | Innovation Roadmap (Three Horizons) | Stage 5 (Roadmap) | — (substrate input) | `templates/innovation-roadmap.md.j2` |
| 7 | Pilot Plan with Baselines | Stage 5 (Roadmap) | L4 (adoption metric) + L5 (baseline required) | `templates/pilot-plan.md.j2` |

### Two render modes

The orchestrator exposes two render entry points:

* **`render_all(engagement, output_dir, write=True)`** — render every deliverable that has the context it needs. Useful for previewing during stage iteration. Returns `(paths, lint_result)`. `write=False` is preview mode (returns rendered text without touching disk).
* **`render_with_gate(engagement, output_dir)`** — publication mode. Runs the linter FIRST. Writes ONLY if zero L-errors. Otherwise returns `({}, lint_result)` and the output directory is untouched. No partial state on disk.

The publication path is `render_with_gate`. It encodes the discipline: a pilot plan that violates L5 (no baseline) does not get written. The lint result is returned to the caller for inspection.

### The shape of a deliverable

Every deliverable footer surfaces the L-rules and P-rules the deliverable carries — that turns each rendered file into self-documenting evidence of the discipline that produced it. For example, the pilot plan footer reports:

* Which `PilotDesign` events anchored the plan
* The `BaselineSection` events that captured the baseline (and whether each is `is_greenfield`)
* The `AdoptionMetric` distinct from the technical success metric (L4 trace)
* The Three Horizons assignment for each pilot

A consultant reviewing the rendered pilot plan can verify L4 + L5 compliance by reading the footer; they don't need to inspect the journal directly. The deliverable carries its own audit trail.

### Beyond Phase 1

The substrate is designed to expand to **13 full-firm deliverables** (Operating Model, Change Management Plan, Architecture Blueprint, Vendor Landscape, Executive Briefing Deck, 90-Day Plan, etc.) without refactoring the core. Adding a new deliverable is a new template + a new context-builder; the orchestrator and the linter pick it up automatically. The D-scope frameworks already on disk are the seed for those deliverables.

---

## 4. The 28 frameworks

The framework library is organized by **consulting purpose, not by source firm** ([ADR 0002](adr/0002-frameworks-organized-by-purpose.md)). Each framework is a YAML file at `frameworks/<category>/<slug>.yaml` validated against `frameworks/_schema.yaml`. The schema enforces a P1-style framework-as-code contract: every framework declares its `purpose`, `inputs`, `dimensions`, `scoring_rubric`, `output_shape`, `when_to_use`, `when_NOT_to_use`, `example_application`, `relationships`, and `citations`.

Of the 28 frameworks on disk, **15 are Phase-1 active** (loaded by the selector, used by the stages, exercised by tests) and **13 are D-scope stubs** (Phase-2 placeholders — present as relationship targets but not selectable). The split is enforced via the `is_d_scope: true` frontmatter flag and verified by `scripts/lint_frameworks.py` on every CI run.

### Maturity

| Slug | Source firm | Year | Status | Output shape | When to use |
|---|---|---|---|---|---|
| `mit-cisr-digital` | MIT CISR (Ross/Beath/Mocker) | 2019 | Phase-1 | `MaturityDimension` | Established enterprise (>500 headcount), banking / insurance / fin-services / construction |
| `gartner-ai` | Gartner | 2024 | Phase-1 | `MaturityDimension` | Tenant familiar with Gartner terminology; energy-utilities / construction default |
| `chaoss` | Linux Foundation CHAOSS | 2017 | Phase-1 | `MaturityDimension` | AI-BUILDING / OSS-project / runtime tenants (BRO-1033 engagement-driven addition) |
| `forrester-data` | Forrester Research | 2023 | D-scope | `MaturityDimension` | Reserved — Phase-2 expansion |
| `mckinsey-7s` | McKinsey (Peters/Waterman) | 1980 | D-scope | `MaturityDimension` | Reserved — Phase-2 expansion |

### Strategy

| Slug | Source firm | Year | Status | Output shape | When to use |
|---|---|---|---|---|---|
| `three-horizons` | McKinsey (Baghai/Coley/White) | 1999 | Phase-1 | `RoadmapStep` | Annual or multi-year fiscal cadence; portfolio spans deploy-now and option-value bets |
| `wardley-mapping` | Simon Wardley | 2018 | Phase-1 | `RoadmapStep` | Tech-evolution explicit; deep-tech or AI-infra tenants |
| `where-to-play-how-to-win` | A.G. Lafley / Roger Martin | 2013 | D-scope | `Recommendation` | Reserved — Phase-2 expansion |
| `five-forces` | Michael Porter | 1979 | D-scope | `Finding` | Reserved — Phase-2 expansion |

### Ideation

| Slug | Source firm | Year | Status | Output shape | When to use |
|---|---|---|---|---|---|
| `jobs-to-be-done` | Christensen / Strategyn | 2003 | Phase-1 | `UseCase` | Customer-centric ideation; banking / consumer-goods default |
| `value-prop-canvas` | Strategyzer (Osterwalder) | 2014 | Phase-1 | `UseCase` | Use case requires fit-mapping between gains/pains and gain-creators/pain-relievers |
| `business-model-canvas` | Strategyzer (Osterwalder/Pigneur) | 2010 | D-scope | `Recommendation` | Reserved — Phase-2 expansion |
| `lean-canvas` | Ash Maurya | 2010 | D-scope | `Recommendation` | Reserved — Phase-2 expansion |

### Prioritization

| Slug | Source firm | Year | Status | Output shape | When to use |
|---|---|---|---|---|---|
| `rice` | Intercom (Sean McBride) | 2016 | Phase-1 | `Score` | ≥3 use cases of similar type; CFO wants a transparent number |
| `ice` | GrowthHackers (Sean Ellis) | 2009 | Phase-1 | `Score` | Lightweight prioritization; construction / early-stage default |
| `wsjf` | SAFe / Reinertsen | 2009 | Phase-1 | `Score` | Cost-of-delay aware; SAFe-aligned organization |
| `cost-of-delay` | Don Reinertsen | 2009 | D-scope | `Score` | Reserved — Phase-2 expansion (deepens WSJF) |

### ROI

| Slug | Source firm | Year | Status | Output shape | When to use |
|---|---|---|---|---|---|
| `unit-economics` | Silicon Valley canon | 2010 | Phase-1 | `RoiCell` | Per-unit cost-and-revenue model; banking / fin-services default |
| `npv-dcf` | Modigliani-Miller | 1958 | Phase-1 | `RoiCell` | Multi-year cash-flow profile; insurance default |
| `real-options` | Trigeorgis | 1999 | Phase-1 | `RoiCell` | Genuine option value (kill / double-down); deep-tech / energy-utilities default |
| `owner-earnings` | Buffett / Berkshire | 1986 | D-scope | `RoiCell` | Reserved — Phase-2 expansion |

### AI-lifecycle

| Slug | Source firm | Year | Status | Output shape | When to use |
|---|---|---|---|---|---|
| `quantumblack-ml` | McKinsey QuantumBlack | 2023 | Phase-1 | `PilotDesign` | High-rigor ML lifecycle; banking / insurance / fin-services default |
| `andrew-ng-pipeline` | DeepLearning.AI | 2021 | Phase-1 | `PilotDesign` | Lightweight ML lifecycle; energy-utilities / construction default |
| `google-pair` | Google PAIR | 2019 | D-scope | `Recommendation` | Reserved — Phase-2 expansion (UX-of-AI) |
| `ms-responsible-ai` | Microsoft | 2022 | D-scope | `Recommendation` | Reserved — Phase-2 expansion (responsible AI) |

### Change

| Slug | Source firm | Year | Status | Output shape | When to use |
|---|---|---|---|---|---|
| `adkar` | Prosci (Jeffrey Hiatt) | 2003 | D-scope | `Recommendation` | Reserved — Phase-2 (change management) |
| `kotter-8-steps` | John Kotter | 1995 | D-scope | `Recommendation` | Reserved — Phase-2 (change management) |
| `mckinsey-influence` | McKinsey | 2015 | D-scope | `Recommendation` | Reserved — Phase-2 (change management) |

### Selection: how a slate is picked

`core/selector.propose_frameworks(industry, maturity_band, scope_keywords, cap=4)` runs the following algorithm:

1. Map `scope_keywords` to category coverage (e.g., "maturity assessment" → `maturity`, "innovation roadmap" → `strategy`).
2. Augment with the **default coverage** — every AI/digital engagement gets at least `maturity` and `prioritization`, even if the scope statement doesn't name them.
3. For each needed category, look up the industry's preferred framework. Fall back to `_DEFAULT_PREFERENCES` if the industry isn't pre-mapped.
4. Skip any framework with `is_d_scope: true`.
5. **P7 hard cap at 5 frameworks per engagement.** Even if the caller requests more, the selector returns at most 5. A 7-framework engagement is over-frameworked; the rigor compounds into review fatigue and the discipline rots.
6. Emit `FrameworkSelection` records with rationale grounded in the framework's `purpose` field.

The selector is deterministic — same inputs produce the same slate. Industry preferences are documented per-industry in `core/selector.py:_INDUSTRY_PREFERENCES`; adding a new industry preference is a 6-line dict entry plus a test.

---

## 5. The 5 review gates

Every stage exits through a human review gate. The gates are **non-negotiable in both modes** — CLI and autonomous ([ADR 0004](adr/0004-five-review-gates-non-negotiable.md)). The rationale is the same one top-firm engagements rely on: human judgment at decision boundaries is how partners catch hallucinations and add the judgment the substrate can't encode.

| Gate | After stage | What it enforces | Who signs off | Failure mode if skipped |
|---|---|---|---|---|
| 1 | Intake | L1 — `StrategicThesis` declared. Magnitude, basis, owner, horizon all present. | Sponsor (CDO / COO / CFO equivalent) | Engagement runs without an economic lever; Bision Failure 1 (100%) |
| 2 | Scan | At least one `MaturityDimension` scored with non-empty evidence for current AND target | Sponsor + technical lead | Maturity report renders empty; capability heatmap has no signal |
| 3 | Ideate | L2 — ≥3 distinct `IdeationSource` values, NOVELTY share ≤50%; L3 — no blocking data readiness without prep phase | Sponsor + product lead | Pilots chosen by novelty (Failure 2, 87%); pilots on unavailable data (Failure 3, 74%) |
| 4 | Prioritize | At least one `UseCase` prioritized with a quantitative score (RICE/ICE/WSJF) and a ROI projection | Sponsor + CFO | Roadmap synthesized on an empty or unranked set; defensibility collapses |
| 5 | Roadmap | L4 — `AdoptionMetric` present on every `PilotDesign`; L5 — `BaselineSection` captured *before* `PILOT_STARTED` for every pilot | Sponsor + business owner | High accuracy / zero adoption (Failure 4, 61%); no ROI defense (Failure 5, 48%) |

### Gate enforcement mechanics

Each gate is enforced at three layers:

1. **Type-level (Pydantic).** The primitive's construction validates the field's presence and shape. `StrategicThesis` rejects empty evidence at `__init__`. `PilotDesign` rejects empty baseline list. `AdoptionMetric` is a required field, not optional.
2. **Stage-level (raise `ValueError`).** `IntakeStage.request_review()` raises `ValueError` if `state.thesis_id is None`. `RoadmapStage.design_pilot()` raises if any baseline metric lacks a prior `BASELINE_CAPTURED` event. The stage runner blocks at the gate.
3. **Linter-level (release-gate backstop).** `core/linter.py` runs L1–L5 + P3 + P7 + P8 rules over the journal as a backstop. If a stage was bypassed (e.g., the engagement was constructed manually outside the stage runners), the linter catches it before `render_with_gate` writes anything.

### Choosing which gates apply

The consultant can choose *which gates apply per engagement* (collapsing intake + scan into one for a single-day discovery sprint, for example) — but the substrate offers all 5 as defaults ([ADR 0004](adr/0004-five-review-gates-non-negotiable.md), Consequences). The decision to collapse is per-engagement, made explicit in the engagement scope; it is never the substrate's decision.

### Autonomous mode and timeouts

In autonomous mode, the runner blocks on `decision != "approved"` and is webhook-driven for the approval. **The default fallback on timeout is pause, never auto-approve.** Auto-approving on timeout would convert an autonomous consulting practice into an automated trust-destroying machine — an engagement that ships under a sponsor's silence is not an engagement, it's a liability.

---

## 6. The Bision failure-mode linter

`core/linter.py` implements eight rules — L1 through L5 (the Bision failure-mode rules) and P3, P7, P8 (the substrate-discipline rules). Each rule is a registered function that takes an `Engagement` and returns a list of `LintViolation` objects.

| Rule | What it catches | Severity | ADR |
|---|---|---|---|
| **L1** STRATEGIC_THESIS_REQUIRED | `INTAKE_COMPLETED` event without a prior `STRATEGIC_THESIS_DECLARED` | error | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| **L2** DIVERSE_IDEATION_SOURCES | Fewer than 3 distinct `IdeationSource` values across use cases, OR NOVELTY share >50% | error | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| **L3** DATA_READINESS_GATE | Any use case with `readiness_band == "blocking"` past Stage 3 without a declared prep phase | error | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| **L4** ADOPTION_METRIC_REQUIRED | `PILOT_STARTED` emitted but no `DELIVERABLE_RENDERED` for `slug == "pilot-plan"` (adoption metric never lands in the deliverable) | error | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| **L5** BASELINE_REQUIRED | `PILOT_STARTED` for a use case with zero prior `BASELINE_CAPTURED` events | error | [ADR 0008](adr/0008-bision-failure-mode-linter-rules.md) |
| P3 | Any `Finding`, `Recommendation`, `BaselineSection`, or `StrategicThesis` with empty `evidence` (typed validator catches this at construction; linter is the journal backstop) | error | — (P-rule discipline) |
| P7 | More than 5 active `FrameworkSelection` records per engagement (selector caps at 5; linter catches manual construction) | warning | — (P-rule discipline) |
| P8 | Any `Recommendation` missing one of `value`, `value_basis`, `owner`, `timeline_weeks`, `success_metric`, `success_target`, `kill_criterion` (typed validator catches at construction; linter is the journal backstop) | error | — (P-rule discipline) |

### Why a linter, given typed primitives?

The typed primitives catch the failure at construction time — that's the strongest enforcement layer. The linter is the **release-gate backstop**: it scans the engagement journal as a whole and catches failures that slipped through manual construction or out-of-stage code paths.

The release-gate test `tests/integration/test_bision_prevention.py` encodes the empirical claim with nine tests:

1. The clean Tropico Renovables fixture lints with zero L-errors (proof-of-life — the substrate doesn't false-positive on a well-formed engagement)
2. L1 — engagement closes intake without thesis → blocks (Bision Failure 1)
3. L2-A — fewer than 3 distinct ideation sources → blocks
4. L2-B — NOVELTY share >50% → blocks
5. L3 — use case with `readiness_band == "blocking"` → blocks (Bision Failure 3)
6. L4 — `PILOT_STARTED` without pilot-plan deliverable → blocks (Bision Failure 4)
7. L5-A — pilot without prior baseline → blocks (Bision Failure 5)
8. L5-B — retroactive baseline (captured *after* `PILOT_STARTED`) → blocks
9. Compound — L1 + L4 + L5 collected together, all reported in a single lint run

The pre-commit and pre-push hooks (`.githooks/pre-commit` and `.githooks/pre-push`) re-run the gate locally before any push — failures block the push rather than reaching CI. The gate also runs in CI on every push and pull request (`.github/workflows/ci.yml`).

### The bypass-flag policy

There is no `--skip-linter` flag. There is no `--allow-no-thesis` flag. There is no `--retroactive-baseline-ok` flag.

If a use case genuinely shouldn't have a baseline (e.g., a research spike with no metric), the substrate path is: don't call it a pilot. Use `UseCase.status = "deferred"` with a `status_rationale` that explains the deferral. The journal records the decision. The linter doesn't fire because no `PILOT_STARTED` event was emitted.

If an engagement genuinely needs a different methodology (e.g., a pure architecture review with no thesis), the substrate path is: don't run intake. Use the substrate's typed primitives directly without invoking the stage runners. The linter only fires on the journal events that *were* emitted; it can't fire on stages that were skipped because they weren't called.

The discipline is structural, not bureaucratic. The substrate refuses to call something a pilot if it isn't one; it doesn't refuse to do work that isn't a pilot.

---

## 7. Anonymization by default

Phronesis extracts learnings from completed engagements into `research/entities/` for cross-engagement compounding (see §10). The default posture is **strict anonymization** ([ADR 0005](adr/0005-anonymization-strict-by-default.md)): an extraction pipeline that defaults to "publish everything" leaks tenant data the first time someone forgets to turn a guard back on. Defaults define norms; the substrate's default is safe.

### What the policy strips

`core.anonymize.AnonymizationPolicy` defaults:

| Field | Default | What it does |
|---|---|---|
| `strip_tenant_slug` | `True` | Removes the tenant's slug (e.g., `acme-bank`) from output |
| `strip_tenant_name` | `True` | Removes the tenant's display name (e.g., "Acme Bank") |
| `strip_personal_names` | `True` | Removes detected personal names from interviews and notes |
| `replace_currency_with_bands` | `True` | `$640,000 USD` becomes `low-6-figures USD` |
| `replace_dates_with_relative` | `True` | `2026-Q3` becomes `next quarter`; specific ISO dates become relative descriptors |
| `replace_locations_with_regions` | `True` | `Bogotá` becomes `<latam-region>`; CO/LATAM cities normalize to the region |
| `redact_terms` | `[]` (extended at runtime) | Tenant-specified terms to redact (product names, internal codenames, etc.) |

The framework allowlist preserves canonical methodology terms — "Three Horizons", "Wardley Mapping", "RICE", "QuantumBlack ML", etc. — so anonymized learnings still surface their methodological lineage. A learning that says "MIT CISR Level 2 banking tenant struggled with cross-LOB integration" tells a future engagement something useful without telling it *which* bank.

### The canary release gate

`tests/integration/test_anonymization_canary.py` defines a fixed list of canary tokens — tenant slug, personal names, currency exact values, location-exact strings, product names, key phrases — and runs the full extraction pipeline against the `acme-bank` fixture. The test asserts that **no canary token appears in any extracted entity content** ([ADR 0007](adr/0007-canary-test-as-release-gate.md)). The canary catalog covers 42 tokens across 21 anonymized files in the M7 extraction pipeline ([CHANGELOG v0.1.2-pre](../CHANGELOG.md#012-pre--2026-05-08)) and the test ships green.

The canary test runs:

* in **pre-commit** (via `.githooks/pre-commit`),
* in **pre-push** (via `.githooks/pre-push`),
* in **CI** (via `.github/workflows/ci.yml`),
* in **release** (via `.github/workflows/release.yml` before any tag publishes a release artifact).

Failure blocks the path forward at every layer. P6 (tenant data isolation) is verified **mechanically**, not by reviewer attention.

### Loosening — by exception only

A publishable case study with explicit tenant consent loosens the policy via `engagements/<slug>/anonymization-overrides.yaml`. The override is per-engagement, reviewed by the reviewer signing off on the engagement, and recorded in the engagement journal. There is no global "permissive policy" flag; every loosening is local and audited.

### What anonymization does NOT cover

Anonymization protects *names, places, exact amounts, and dates*. It does **not** protect:

* **Methodological learnings** — "banking tenants with low cross-LOB integration take ~12-16 weeks to reach pilot-ready data readiness" is exactly the kind of pattern phronesis is designed to surface. Anonymization keeps the pattern; it strips the source.
* **Industry-level patterns** — "in CHAOSS-scored tech tenants, contributor diversity is the leading indicator of governance maturity" is a pattern, not a leak.
* **Aggregated benchmarks** — once enough engagements have run, aggregated maturity scores by industry-and-region become a substrate asset. Anonymization protects each engagement; aggregation produces a public learning.

The trade-off is intentional: some engagement IP that *could* be more public-friendly stays anonymous; that's the right side of the trust line.

---

## 8. Two operating modes

Phronesis runs in two modes — consultant CLI and autonomous Life Runtime endpoint. The two converge on the same substrate, the same primitives, the same gates. They differ in where the human review gate fires and how stage inputs are collected.

### Mode 1 — Consultant CLI

The consultant drives the engagement interactively from the command line. The CLI is intentionally minimal in Phase 1 — four commands that wrap the core engagement lifecycle:

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

# Inspect derived engagement state from the journal
phronesis status acme-bank

# Run the L1–L5 release-gate linter (strict mode for CI)
phronesis lint acme-bank --strict

# Render all 7 deliverables (lint-gated by default)
phronesis render acme-bank

# Render UNGATED (preview mode; lint result still surfaced)
phronesis render acme-bank --ungated

# Extract anonymized cross-engagement learnings (M7 pipeline; see §10)
phronesis bookkeep acme-bank
phronesis bookkeep acme-bank --dry-run
phronesis bookkeep acme-bank --queue-root /tmp/queue --entity-graph-root /tmp/entities
```

The stage commands — `intake`, `scan`, `ideate`, `prioritize`, `roadmap`, `review` — are queued for **M4**. Phase 1 ships the Python API for stage progression; the CLI scaffolds the engagement and gates the outputs. From the Python API:

```python
from decimal import Decimal
from core.engagement import Engagement, EngagementJournal
from core.types import StrategicThesis, Citation
from stages.intake import IntakeStage
from runners.cli.io import load_engagement

eng = load_engagement("acme-bank")
intake = IntakeStage()
intake.run(eng)
intake.log_interview(
    eng,
    interviewee="Carolina Pérez",
    role="CDO",
    transcript_ref="interview:cdo:Q2",
    key_findings=["Tier-1 volume up 18% YoY", "deflection rate plateaued at 6%"],
)
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

The CLI mode is the default for **discovery sprints** — week-scale to month-scale engagements where the consultant is in the loop continuously, where interviews and document ingestion are the dominant input source, and where the sponsor wants synchronous review at each gate.

### Mode 2 — Autonomous Life Runtime endpoint

The autonomous mode is a Phase-3 capability that ships as a stub in Phase 1 ([ADR 0001](adr/0001-python-substrate-life-engine-phased.md)). The endpoint accepts a typed `StartEngagementRequest`, drives the 5 stages without a human at the keyboard, fires webhooks at each review gate, and notifies when the engagement concludes.

The autonomous mode is the right shape for **long-horizon engagements** where the same substrate runs continuously against an enterprise — quarterly maturity reassessments, ongoing use-case discovery, recurring ROI recalibration. The Life Runtime infrastructure (lago event journal, haima billing, vigil telemetry, nous evaluators, anima identity, lifegw endpoint) is built to handle that shape; the Python substrate is the iteration layer that proves the methodology before the Rust crate productionizes it.

The Phase 1 stub (`runners/autonomous/contract.py` in the design spec, deferred in code) holds the typed contract: `StartEngagementRequest`, `EngagementStateNotification`, `ReviewGatePending`, `EngagementConcluded`. The `service.py` raises `NotImplementedError`. Phase 3 transcribes the Phase 1 Python primitives to Rust and wires them to the Life infrastructure. End-state matches "Life crate from day one" without paying the upfront cost.

### Where the modes converge

Both modes:

* Run the same 5 stages in the same order.
* Emit the same typed journal events.
* Enforce the same 5 review gates ([ADR 0004](adr/0004-five-review-gates-non-negotiable.md)).
* Apply the same L1–L5 linter rules.
* Render the same 7 deliverables.
* Use the same anonymization policy (strict by default).
* Trigger the same cross-engagement extraction pipeline on `ENGAGEMENT_CONCLUDED`.

The mode choice is about *who is at the gate*, not about *what the gate enforces*. The substrate is one substrate.

### Where the modes differ

| Aspect | CLI mode | Autonomous mode |
|---|---|---|
| Stage input source | Consultant types / pastes / uploads | Pre-built request payload + webhook responses |
| Review gate fires as | `phronesis review <stage>` blocks until `--approve` or `--revise` | Webhook to the reviewer; runner blocks on `decision != "approved"` |
| Persistence | `engagements/<slug>/journal.jsonl` on local disk | lago event journal in Life infrastructure (Phase 3) |
| Default on review timeout | N/A — consultant is in the loop | **Pause**, never auto-approve ([ADR 0004](adr/0004-five-review-gates-non-negotiable.md)) |
| Billing | Per-consultant time (out of band) | haima per-engagement-minute (Phase 3) |
| Identity | Local sponsor + consultant identifiers | anima-bound identity per actor (Phase 3) |

---

## 9. Engagement-driven discovery loop

The phronesis substrate evolves through **engagement-driven discovery**. Real or synthetic engagements are run against the current substrate; gaps surfaced by the engagement become Linear issues; issues close in single-PR batches that ship the substrate refinement *and* re-run the engagement to validate the fix.

This is the loop:

```
+-----------------+        +-----------------+        +-----------------+
| Engagement      | -----> | Gap surfaced by | -----> | Linear issue    |
| runs against    |        | the engagement  |        | filed against   |
| substrate vN    |        |                 |        | substrate vN    |
+-----------------+        +-----------------+        +-----------------+
                                                              |
                                                              v
+-----------------+        +-----------------+        +-----------------+
| Engagement      | <----- | Substrate vN+1  | <----- | PR closes issue |
| re-runs against |        | ships fix       |        | with single-PR  |
| substrate vN+1  |        |                 |        | refinement      |
+-----------------+        +-----------------+        +-----------------+
        |
        v
+-----------------+
| New gaps        | --> (loop)
| surface...      |
+-----------------+
```

### Worked examples

Two complete loop iterations are recorded in the [CHANGELOG](../CHANGELOG.md):

**`v0.0.2-m0.1` — Tropico Renovables S.A.S.** (renewable IPP, Colombian Caribbean coast). The first synthetic engagement found four type-level gaps in the M0 primitives:

* `JournalEvent.event_id` and `timestamp` lacked `default_factory` — callers were tempted to call `str(ulid.ULID())` by hand, which tripped Pydantic's buffer protocol (ulid-py's `ULID` extends `MemoryView`). Fixed via `_new_event_id` helper.
* `StrategicThesis` lacked a stable `thesis_id` — journal events couldn't reference the thesis after revisions. Added auto-generated ULID.
* `Score.value` could lie outside `Score.scale` — silently-wrong rubrics propagated to deliverables. Added `value_within_scale` validator.
* `MaturityDimension.target_score` accepted empty evidence — targets without citations were wishful thinking. Added `both_scores_must_have_evidence` validator.
* `UseCase` lacked a status lifecycle (`proposed` / `prioritized` / `deferred` / `dropped`) — dropped use cases silently disappeared from the dossier. Added `status` + `status_rationale` with audit-trail validation.
* `TenantContext.industry` lacked `energy-utilities` — IPPs / transmission operators fell back to `other` and lost typed signal for the selector. Added the variant.

All six gaps closed in one PR. Tests went from 47 → 57 (+10 regression tests, including `test_event_id_auto_generated` to document the ulid-py footgun for the next engineer).

**`v0.1.1-pre` — Broomva Silicon synthetic engagement (Spec E agent-loop runtime).** This was the AI-BUILDING engagement that surfaced five gaps. Closed five tickets in one PR:

* **BRO-1031** — `TenantContext.industry` lacked `"tech"`. AI-infra / runtime / library / chip-design tenants fell back to `other`, losing the selector signal.
* **BRO-1032** — `_INDUSTRY_PREFERENCES["tech"]` didn't exist; the tech path had no framework slate. Added the dict entry: Maturity → CHAOSS, Strategy → Wardley, ROI → real-options, AI-lifecycle → QuantumBlack ML, Prioritization → RICE, Ideation → Value Prop Canvas.
* **BRO-1033** — No maturity framework fit the AI-BUILDING tenant. MIT CISR's industrialized-vs-platform axis and Gartner AI's awareness-to-systemic ladder both missed the actual measurement. Added the **CHAOSS** framework (Linux Foundation, 2017) with five dimensions: contributor-diversity, release-cadence, code-review-depth, downstream-adoption, governance-maturity. Output is `MaturityDimension`. Total framework count: 14 + 1 = 15 Phase-1 active.
* **BRO-1034** — `BaselineSection` couldn't represent a greenfield baseline. A brand-new product line with zero production traffic has no incumbent metric — but a team that SAYS they have a baseline that's "$0" because they didn't measure is the modal Bision Failure 5 pattern. Added `is_greenfield: bool` with the L5 invariant reinterpretation: "declare zero-state explicitly" rather than "capture incumbent metric."
* **BRO-1035** — `templates/pilot-plan.md.j2` rendered greenfield baselines as numeric `0` — visually identical to a real measurement of zero. Modified the template to render `**[GREENFIELD]** zero-state declared` and added a "Greenfield pilot" blockquote when any baseline is greenfield. Section header changed from "Baselines **captured** before pilot start" to "Baselines **declared** before pilot start" — covers both incumbent + greenfield cases honestly.

All five gaps closed in one PR. Tests went 387 → 399 (+12, including 8 CHAOSS framework tests, 2 selector tech-preference tests, greenfield-baseline tests, greenfield-template-rendering test, D-scope-total-count bump from 27 to 28).

### Why this loop exists

The alternative is **a-priori design** — sketch a Phase-1 substrate that covers every conceivable engagement shape, then ship it. That path has two failure modes:

1. **Over-engineering for engagements that never happen.** Every speculative primitive is a maintenance cost; primitives without engagement validation accrete cruft.
2. **Under-engineering for engagements that actually happen.** Real engagements always surface gaps the designer didn't anticipate. The Tropico engagement found four gaps that the M0 design didn't see; the Broomva Silicon engagement found five more.

Engagement-driven discovery converts "what should the substrate do?" from a design question into an empirical question. The substrate evolves by being run, not by being designed.

### What counts as an engagement

The loop accepts synthetic engagements (built from fixture tenants like Tropico Renovables, Acme Bank, Nova Construction, Broomva Silicon) and real engagements (paid client work). Both feed the same loop. Synthetic engagements are faster and reversible; real engagements have higher signal because the gaps surface from genuine sponsor friction rather than designer imagination.

The substrate's fixture library lives at `tests/fixtures/`:

* `tropico_renovables.py` — 62 MW renewable IPP, Colombian Caribbean coast, used as the canonical proof-of-life fixture (lints clean, drives all 5 stages end-to-end).
* `acme_bank.py` — banking tenant, used as the M6 fixture for the anonymization canary release gate.
* `nova_construction.py` — construction-industry tenant, used as a second M6 E2E fixture covering a different industry slate.

Adding a new fixture is a regular PR: build the factory, drive the 5 stages, assert L-rules behave correctly, register the fixture in the test corpus.

---

## 10. Cross-engagement IP extraction

The reflexive close of the discovery loop is **cross-engagement IP extraction**. When an engagement concludes (`ENGAGEMENT_CONCLUDED` fires), the substrate automatically extracts anonymized learnings from the journal and stages them as candidates for the workspace knowledge graph at `research/entities/`.

The pipeline lives at `core/extraction/`:

```
core/extraction/
├── __init__.py        — package surface (exports + re-exports)
├── anonymizer.py      — EngagementAnonymizer wraps AnonymizationPolicy
├── candidates.py      — extract_industry_patterns() + extract_framework_refinements()
└── pipeline.py        — extract_and_queue() + on_engagement_concluded() reflexive hook
```

### The end-to-end flow

1. **`ENGAGEMENT_CONCLUDED` fires** from `RoadmapStage.conclude()`. The engagement model invokes `core.extraction.pipeline.on_engagement_concluded(engagement)` reflexively — this is not opt-in. The hook runs without being asked, on every concluded engagement.

2. **Candidates extracted.** `extract_industry_patterns(engagement)` and `extract_framework_refinements(engagement)` produce a list of `ExtractionCandidate` objects. Each candidate captures:
   * `entity_type` — `industry-pattern` or `framework-refinement`
   * `slug` — auto-generated slug for the entity page
   * `title` — short human-readable title
   * `content` — the pattern body (pre-anonymized)
   * `quote` — the source quote from the journal (pre-anonymized)
   * `industry` or `framework_ref` — the categorical anchor
   * `signals` — dict of metadata (e.g., maturity band, NPV magnitude, anti-pattern observed)
   * `provenance_event_ids` — list of journal event IDs that contributed to the pattern

3. **Anonymization applied.** Each candidate's `content` and `quote` are passed through `EngagementAnonymizer` with the engagement's strict policy plus journal-derived redact terms (tenant slug, sponsor name, product names mentioned in the engagement scope). A **defense-in-depth re-check** runs after construction: if any candidate still carries a tenant marker, it is **dropped** (added to `ExtractionResult.leaks`), not queued. The canary release-gate test in CI catches anything the runtime check misses.

4. **Scored via the workspace Nous gate (bookkeeping P6).** Each candidate is scored on the 9-point Nous gate (`novelty` 0–3 + `specificity` 0–3 + `relevance` 0–3). The scorer is the canonical workspace bookkeeping module — phronesis does not duplicate scoring math. If the bookkeeping module isn't importable (test environments, minimal CI runners), a deterministic stub fallback runs. Tests force the stub via `PHRONESIS_EXTRACTION_STUB_SCORER=1`.

5. **Queued or promoted.** Candidates scoring **≥5/9** are written to `<entity_graph_root>/<entity_type>/<slug>.md` as **entity-page stubs** with `status: candidate`. Candidates scoring `<5/9` are written to `<queue_root>/<engagement_slug>/low-score/` for forensic visibility — never silently dropped. All candidates (promoted and low-score) are also written as JSON queue records under `<queue_root>/<engagement_slug>/{promoted,low-score}/` for operator review.

6. **Operator promotes (or doesn't).** Candidates do **not** go directly to active knowledge-graph entries. Every promoted candidate is a *stub* with `status: candidate`. The operator polishes the body, verifies the signals, confirms the anonymization holds, and then promotes the status from `candidate` to `active` via the workspace bookkeeping flow. The substrate never short-circuits the human review pass — the same discipline that governs stages governs extraction.

### Queue layout

```
<queue_root>/                            # default: ~/.config/phronesis/extraction-queue/
└── <engagement_slug>/
    ├── promoted/
    │   └── <candidate-slug>-<timestamp>.json   # ≥5/9 candidates (also written to entity graph)
    └── low-score/
        └── <candidate-slug>-<timestamp>.json   # <5/9 candidates (queue only)

<entity_graph_root>/                     # default: ~/broomva/research/entities/
├── industry-pattern/
│   └── <candidate-slug>.md             # entity-page stub with status: candidate
└── framework-refinement/
    └── <candidate-slug>.md             # entity-page stub with status: candidate
```

Both paths are configurable via environment variables (`PHRONESIS_EXTRACTION_QUEUE_ROOT`, `PHRONESIS_ENTITY_GRAPH_ROOT`), and tests sandbox them to `tmp_path` so the suite never touches the real knowledge graph.

### Rule-of-three for promotion

A candidate that surfaces from a single engagement is **one instance**, not a stable pattern. The substrate explicitly records this in every promoted stub:

> Rule-of-three: this is one instance. Surface ≥2 more same-industry / same-framework engagements reproducing the pattern before treating as a stable graph node.

That note is what keeps the knowledge graph from filling up with one-off observations. The bookkeeping P6 mechanism in the workspace already enforces this discipline; phronesis hooks into it cleanly.

### CLI re-runs

The reflexive hook fires automatically on `ENGAGEMENT_CONCLUDED`. For re-runs (operator inspection, post-hoc anonymization-policy tightening, fixture-driven experiments), use the `phronesis bookkeep` command:

```bash
# Re-run extraction; persist to default queue + entity-graph roots
phronesis bookkeep acme-bank

# Dry-run: compute extraction; never touch disk
phronesis bookkeep acme-bank --dry-run

# Override roots (useful for tests + scratch experiments)
phronesis bookkeep acme-bank \
  --queue-root /tmp/queue \
  --entity-graph-root /tmp/entities

# Include low-score candidates in the summary listing
phronesis bookkeep acme-bank --show-low-score
```

If any candidate carries a tenant marker post-redaction, the CLI exits with code 2 and prints a `[BLOCK]` message naming each leaked slug and marker. That output is the operator's signal to tighten `core.anonymize` policy or `redact_terms` before re-running.

### Why this matters

The discovery loop (§9) is what makes the substrate evolve. The extraction pipeline is what makes the *knowledge graph* evolve — every concluded engagement contributes anonymized learnings to the workspace, without manual invocation, without leaking tenant data. That's the structural close of the loop: the substrate gets better as engagements run *and* the surrounding knowledge graph accumulates the cross-engagement IP that future engagements draw from.

In bstack terms (per the workspace `CLAUDE.md`), this is **Pillar 1 — recursive self-improvement** running through phronesis: each engagement is a learning instance, the workspace consolidates instances into patterns via P16 (Crystallize), and the next engagement starts with more substrate than the previous one.

---

## Appendix A — File map

The core substrate is one Python package with five layers, mirroring the type hierarchy:

| Path | What's there |
|---|---|
| `core/types.py` | Pydantic typed primitives (Layer 1–5). The L1/L4/L5 enforcement points live here. |
| `core/engagement.py` | `EngagementJournal` + `EngagementState` + `Engagement` aggregate. Replay-based state derivation. |
| `core/events.py` | Per-`EventKind` typed payload schemas + `payload_for(kind)` registry. |
| `core/frameworks.py` | YAML → Pydantic loader. Two-layer validation (jsonschema, then Pydantic). |
| `core/selector.py` | `propose_frameworks(industry, maturity_band, scope_keywords, cap=4)` — P7 capped at 5. |
| `core/linter.py` | L1–L5 + P3/P7/P8 rules. Release-gate backstop. |
| `core/render.py` | Jinja2 environment with `StrictUndefined`; `as_currency` / `as_percent` filters. |
| `core/orchestrator.py` | `render_all` + `render_with_gate`. Publication-mode is gated by lint result. |
| `core/anonymize.py` | `AnonymizationPolicy` + `anonymize(text, policy, tenant)` + `carries_tenant_marker(text, tenant)`. |
| `core/extraction/` | M7 cross-engagement IP extraction pipeline. |
| `stages/intake.py` | Stage 1 — L1 gate at `request_review()`. |
| `stages/scan.py` | Stage 2 — at-least-one-dimension gate. |
| `stages/ideate.py` | Stage 3 — L2 gate (≥3 sources, ≤50% NOVELTY). |
| `stages/prioritize.py` | Stage 4 — at-least-one-prioritized gate. |
| `stages/roadmap.py` | Stage 5 — L4 + L5 gates; terminal `ENGAGEMENT_CONCLUDED`. |
| `runners/cli/__main__.py` | Click CLI: `init` / `status` / `lint` / `render` / `bookkeep`. |
| `templates/*.md.j2` | 7 Jinja2 deliverable templates with `StrictUndefined`. |
| `frameworks/<category>/<slug>.yaml` | 28 framework YAMLs (15 Phase-1, 13 D-scope). |
| `tests/integration/test_bision_prevention.py` | L1–L5 release gate (9 tests). |
| `tests/integration/test_anonymization_canary.py` | Canary release gate (42 tokens × 21 anonymized files). |

## Appendix B — Validation gates

Every release passes the following gates locally and in CI:

| Gate | Local command | CI workflow |
|---|---|---|
| ruff lint | `uv run ruff check .` | `.github/workflows/ci.yml` |
| ruff format | `uv run ruff format --check .` | `.github/workflows/ci.yml` |
| mypy strict | `uv run mypy core/ tests/` | `.github/workflows/ci.yml` |
| pytest (unit + property) | `uv run pytest tests/unit/ -m "unit or property"` | `.github/workflows/ci.yml` |
| pytest (integration) | `uv run pytest tests/integration/` | `.github/workflows/ci.yml` |
| framework lint | `uv run python scripts/lint_frameworks.py` | `.github/workflows/ci.yml` |
| Bision-prevention release gate | `make bision-prevention` | `.github/workflows/ci.yml` + `.githooks/pre-push` |
| Anonymization canary release gate | `make canary-check` | `.github/workflows/ci.yml` + `.githooks/pre-push` + `.github/workflows/release.yml` |
| Scaffold doctor | `make doctor` | `.github/workflows/ci.yml` (scaffold-doctor job) |

The full suite at v0.1.2-pre runs **458 tests** to green. The Bision-prevention and canary suites are non-skippable — failure blocks every push, every PR, every release.

## Appendix C — Phase roadmap

| Phase | Status | What ships |
|---|---|---|
| Phase 1 (M0–M8) | **Complete** at v0.1.2-pre | Python substrate, 28 frameworks, 5 stages, 7 deliverables, L1–L5 linter, anonymization, M7 extraction pipeline, OSS-readiness |
| Phase 2 (engagement-driven) | **In progress** | M4 stage CLI commands, M5 autonomous-mode stub-to-real path, real-engagement validation, PyPI publish workflow |
| Phase 3 (Life Rust crate) | **Deferred** ([ADR 0001](adr/0001-python-substrate-life-engine-phased.md)) | `core/life/crates/life-phronesis/` — Phase 1 primitives transcribed to Rust + wired to lago / haima / vigil / nous / anima / lifegw |

The mode-2 autonomous endpoint is the bridge artifact. Its Phase-1 typed contract (`runners/autonomous/contract.py` as Pydantic models) is what Phase 3 transcribes; the `NotImplementedError` stub in Phase 1 is what holds the contract stable across the transcription.

---

## References

* [`SKILL.md`](../SKILL.md) — agent-facing skill card with triggers + commands
* [`README.md`](../README.md) — install + quickstart
* [`CHANGELOG.md`](../CHANGELOG.md) — per-release notes
* [`docs/adr/0001-python-substrate-life-engine-phased.md`](adr/0001-python-substrate-life-engine-phased.md) — Python substrate now, Life Rust crate Phase 3
* [`docs/adr/0002-frameworks-organized-by-purpose.md`](adr/0002-frameworks-organized-by-purpose.md) — Frameworks organized by consulting purpose
* [`docs/adr/0003-event-sourced-engagement-journal.md`](adr/0003-event-sourced-engagement-journal.md) — Event-sourced engagement journal
* [`docs/adr/0004-five-review-gates-non-negotiable.md`](adr/0004-five-review-gates-non-negotiable.md) — Five stage-boundary human review gates
* [`docs/adr/0005-anonymization-strict-by-default.md`](adr/0005-anonymization-strict-by-default.md) — Anonymization strict-by-default
* [`docs/adr/0006-decimal-for-money.md`](adr/0006-decimal-for-money.md) — Decimal for money
* [`docs/adr/0007-canary-test-as-release-gate.md`](adr/0007-canary-test-as-release-gate.md) — Canary anonymization test as release gate
* [`docs/adr/0008-bision-failure-mode-linter-rules.md`](adr/0008-bision-failure-mode-linter-rules.md) — Bision failure-mode linter rules
* Linear project: [Phronesis — AI-Native Advisory Practice](https://linear.app/broomva/project/phronesis-ai-native-advisory-practice-8007a216a186)
