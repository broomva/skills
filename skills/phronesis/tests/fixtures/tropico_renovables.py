"""Synthetic Tropico Renovables engagement fixture.

Reusable factory: build_tropico_engagement() returns a fully-populated
Engagement that:
  - Goes through all 5 stage runners (intake → scan → ideate → prioritize → roadmap)
  - Passes all 5 L-rules (L1-L5) — bision-prevention release-gate-clean
  - Records 7 deliverables as rendered
  - Concludes with state.is_concluded == True

The deliverable_extras() helper returns the typed-primitive context the
render orchestrator needs to produce all 7 deliverables.

Used by:
  - tests/integration/test_anonymization_canary.py  (E.3)
  - tests/integration/test_bision_prevention.py     (E.2 — clean baseline)
  - any future integration test that needs a "good engagement"

Phase 1 — synthetic only. Phase 2 will replace with first real engagement
extracts (anonymized via core.anonymize before checkin).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from core.engagement import Engagement, EngagementJournal
from core.types import (
    AdoptionMetric,
    BaselineSection,
    CapabilityCell,
    Citation,
    DataReadinessAssessment,
    EventKind,
    Finding,
    IdeationSource,
    MaturityDimension,
    PilotDesign,
    RoadmapStep,
    RoiCell,
    Score,
    StrategicThesis,
    TenantContext,
    UseCase,
)

# ----------------------------------------------------------------------------
# Tenant
# ----------------------------------------------------------------------------


def tropico_tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="tropico-renovables",
        name="Tropico Renovables S.A.S.",
        industry="energy-utilities",
        region="CO",
        revenue_band="<10M",
        headcount_band="50-500",
        sponsor="Catalina Vélez",
        sponsor_role="COO",
        engagement_scope=(
            "AI control-engineering maturity assessment + 3 prioritized use "
            "cases for 62 MW tropical-coast renewable portfolio."
        ),
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=10,
    )


# Canary tokens — the 14 strings that MUST NOT leak through anonymization.
# Mirror of `acme_bank.py::ACME_BANK_CANARY_TOKENS` + `nova_construction.py
# ::NOVA_CONSTRUCTION_CANARY_TOKENS`. Tropico's fixture is intentionally
# spare (1 sponsor, no project codenames), so the 14 come from tenant name
# variants + first/last sponsor name splits + currency amounts that should
# bucket via `core.anonymize._CURRENCY_RE`.
TROPICO_CANARY_TOKENS: list[str] = [
    # Tenant identifiers (5)
    "tropico-renovables",
    "Tropico Renovables S.A.S.",
    "Tropico Renovables",
    "Tropico",
    "tropico",
    # Sponsor name variants (3)
    "Catalina Vélez",
    "Catalina",
    "Vélez",
    # Currency amounts — must bucket to bands, never survive verbatim (6)
    "$640,000",
    "$420,000",
    "$220,000",
    "$110,000",
    "$160,000",
    "$180,000",
]


# Shared citations
_INTERVIEW_CITE = Citation(
    kind="evidence",
    ref="interview:coo-velez:2026-05-06",
    excerpt="38 GWh/yr lost to curtailment + cloud-transient ramp violations",
    confidence="high",
)
_SCADA_CITE = Citation(
    kind="evidence",
    ref="scada-export:tropico:2024-2026",
    excerpt="6-yr SCADA telemetry, 1Hz inverter + 5min POI",
    confidence="high",
)
_BENCH_CITE = Citation(
    kind="evidence",
    ref="bench:peer-iPP-2025",
    excerpt="LATAM peer IPP CF benchmarks 2025",
    confidence="medium",
)


# ----------------------------------------------------------------------------
# Typed primitives — built once and reused across stages + deliverables
# ----------------------------------------------------------------------------


def _thesis() -> StrategicThesis:
    return StrategicThesis(
        economic_lever=(
            "Recover 4% blended capacity factor on the 62 MW portfolio via "
            "model-predictive control + 14-day inflow forecasting."
        ),
        lever_kind="revenue",
        magnitude_estimate=Decimal("640000"),
        magnitude_basis="62 MW × 8760 h × 0.04 ΔCF × $79/MWh × 0.37 realism",
        strategic_horizon="h1-now",
        decision_rights_owner="Catalina Vélez (COO)",
        measured_in="USD/yr",
        evidence=[_INTERVIEW_CITE],
    )


def _maturity_dimensions() -> list[MaturityDimension]:
    rows = [
        ("Operational digitization", 2.0, 4.0, "Open-loop dispatch"),
        ("Data infrastructure", 2.5, 4.0, "Telemetry siloed in Atos OASYS"),
        ("ML/AI capability", 1.5, 3.0, "No ML-engineering function"),
        ("Grid-services readiness", 2.0, 4.0, "FFR market opens 2027-Q1"),
    ]
    out = []
    for name, current, target, gap in rows:
        out.append(
            MaturityDimension(
                name=name,
                framework_ref="framework:gartner-ai",
                current_score=Score(
                    dimension=name.lower().replace(" ", "-"),
                    value=current,
                    scale=(1.0, 5.0),
                    rubric_ref="cisr",
                    rationale=f"Current state for {name}",
                    evidence=[_SCADA_CITE],
                ),
                target_score=Score(
                    dimension=name.lower().replace(" ", "-"),
                    value=target,
                    scale=(1.0, 5.0),
                    rubric_ref="cisr",
                    rationale=f"Target benchmarked vs LATAM peer iPPs ({name})",
                    evidence=[_BENCH_CITE],
                ),
                gap_summary=gap,
                key_actions=[f"Address {name} gap"],
                evidence=[_INTERVIEW_CITE],
            )
        )
    return out


def _capability_cells() -> list[CapabilityCell]:
    return [
        CapabilityCell(
            capability="Time-series ML pipeline",
            category="tooling",
            current_state="absent",
            target_state="defined",
            criticality="foundational",
            evidence=[_SCADA_CITE],
        ),
        CapabilityCell(
            capability="Control-engineering team",
            category="talent",
            current_state="ad-hoc",
            target_state="managed",
            criticality="foundational",
            evidence=[_INTERVIEW_CITE],
        ),
        CapabilityCell(
            capability="ML model governance",
            category="governance",
            current_state="absent",
            target_state="defined",
            criticality="important",
            evidence=[_SCADA_CITE],
        ),
    ]


def _use_cases() -> list[UseCase]:
    rows = [
        ("uc-mpc-solar", "420000", "180000", IdeationSource.BUSINESS_PAIN),
        ("uc-inflow-fcst", "110000", "75000", IdeationSource.DATA_OPPORTUNITY),
        ("uc-ffr-grid", "110000", "220000", IdeationSource.REGULATORY_PRESSURE),
        ("uc-ppa-bid", "160000", "90000", IdeationSource.COMPETITIVE_RESPONSE),
    ]
    out = []
    for uc_id, value, cost, source in rows:
        out.append(
            UseCase(
                id=uc_id,
                problem=f"problem for {uc_id}",
                hypothesis=f"hypothesis for {uc_id}",
                solution_summary=f"solution for {uc_id}",
                expected_value=Decimal(value),
                cost_estimate=Decimal(cost),
                cost_breakdown={"x": Decimal(cost)},
                data_required=["d"],
                capabilities_required=["c"],
                risks=[
                    Finding(
                        title=f"{uc_id} risk",
                        body="Vendor / regulatory / market risk",
                        severity="major",
                        confidence="medium",
                        evidence=[_INTERVIEW_CITE],
                    )
                ],
                framework_lens=["rice"],
                score_impact=Score(
                    dimension="impact",
                    value=7.0,
                    scale=(0.0, 10.0),
                    rubric_ref="rice",
                    rationale="r",
                    evidence=[_INTERVIEW_CITE],
                ),
                score_effort=Score(
                    dimension="effort",
                    value=4.0,
                    scale=(0.0, 10.0),
                    rubric_ref="rice",
                    rationale="r",
                    evidence=[_INTERVIEW_CITE],
                ),
                ideation_source=source,
                data_readiness=DataReadinessAssessment(
                    use_case_id=uc_id,
                    data_dependencies=["d"],
                    weakest_dependency_state="managed",
                    readiness_band="pilot-ready",
                    prep_phase_required=False,
                ),
                evidence=[_INTERVIEW_CITE],
            )
        )
    return out


def _roi_cells(top_use_cases: list[UseCase]) -> list[RoiCell]:
    cells = []
    for uc in top_use_cases:
        net = uc.expected_value - uc.cost_estimate
        cells.append(
            RoiCell(
                use_case_id=uc.id,
                year=1,
                revenue_impact=uc.expected_value,
                cost_savings=Decimal("0"),
                investment=uc.cost_estimate,
                one_time_cost=uc.cost_estimate * Decimal("0.7"),
                recurring_cost=uc.cost_estimate * Decimal("0.3"),
                net=net,
                cumulative_net=net,
                discount_rate=Decimal("0.14"),
                sensitivity_low=net * Decimal("0.6"),
                sensitivity_high=net * Decimal("1.4"),
                assumptions=["Bolsa price $79/MWh ±18%"],
            )
        )
    return cells


def _roadmap_steps() -> list[RoadmapStep]:
    return [
        RoadmapStep(
            id="rs-h1-mpc",
            title="MPC pilot on Farm 1 (12 MW)",
            horizon="h1-now",
            quarter="2026-Q3",
            related_use_cases=["uc-mpc-solar"],
            related_recommendations=["rec-mpc"],
            dependencies=["data-readiness-managed"],
            owner="VP Operations",
            success_gate="≥3% CF improvement sustained 8 weeks",
        ),
        RoadmapStep(
            id="rs-h2-portfolio",
            title="Portfolio MPC + inflow forecast",
            horizon="h2-next",
            quarter="2026-Q4",
            related_use_cases=["uc-mpc-solar", "uc-inflow-fcst"],
            related_recommendations=["rec-portfolio"],
            dependencies=["rs-h1-mpc-pilot success"],
            owner="VP Operations",
            success_gate="Combined CF +3% across 62 MW",
        ),
        RoadmapStep(
            id="rs-h3-grid",
            title="FFR pre-qualification + grid-services",
            horizon="h3-later",
            quarter="2027-Q2",
            related_use_cases=["uc-ffr-grid"],
            related_recommendations=["rec-ffr"],
            dependencies=["XM FFR market live"],
            owner="Commercial Director",
            success_gate="FFR-qualified + first capacity revenue",
        ),
    ]


def _baseline() -> BaselineSection:
    return BaselineSection(
        metric_name="Farm-1 capacity factor",
        baseline_value=Decimal("0.234"),
        baseline_window="2026-Q1 production",
        baseline_data_source="SCADA POI 5-min export",
        baseline_measurement_date=datetime(2026, 4, 1, tzinfo=UTC),
        captured_by="VP Ops + Head of Data",
        evidence=[_SCADA_CITE],
    )


def _adoption() -> AdoptionMetric:
    return AdoptionMetric(
        metric_name="Operations team accepts MPC setpoints",
        target_value=">=85% of 5-min dispatch intervals over 4 weeks",
        measurement_method="SCADA override-flag log review, weekly cadence",
        owner="VP Operations",
    )


def _pilot(baseline: BaselineSection, adoption: AdoptionMetric) -> PilotDesign:
    return PilotDesign(
        use_case_id="uc-mpc-solar",
        hypothesis="Receding-horizon MPC lifts Farm-1 CF from 23.4% to ≥24.1% over 16 wk",
        null_hypothesis="No statistically significant CF lift at p<0.05",
        duration_weeks=16,
        cohort_definition="Farm-1 only (12 MW). Farm-2/3 + hydro = control.",
        success_criteria=[
            "Farm-1 CF ≥24.1% sustained weeks 9-16",
            "Zero ramp-rate violations",
            "Adoption metric ≥85% by week 12",
        ],
        kill_criterion="Week-8 CF <23.5% OR ramp-violations exceed pre-pilot avg",
        learning_objectives=[
            "Cloud-nowcast horizon vs computational latency tradeoff",
            "Does MPC lift transfer to Farm-2/3 with minimal retuning?",
        ],
        risks=[
            Finding(
                title="Cloud-nowcast feed reliability",
                body="GOES-R outages historically 0.8% — fail-open to legacy setpoint",
                severity="minor",
                confidence="high",
                evidence=[_SCADA_CITE],
            )
        ],
        cost_estimate=Decimal("180000"),
        adoption_metric=adoption,
        baseline=[baseline],
        evidence=[_INTERVIEW_CITE, _SCADA_CITE],
    )


# ----------------------------------------------------------------------------
# Public factories
# ----------------------------------------------------------------------------


def build_tropico_engagement() -> Engagement:
    """Construct a fully-populated, L-clean Tropico engagement.

    Drives all 5 stage runners. The engagement passes through:
      Stage 1 (intake) → Stage 2 (scan) → Stage 3 (ideate)
      → Stage 4 (prioritize) → Stage 5 (roadmap) → concluded.

    Returns an Engagement whose journal contains the full event sequence
    and whose state.is_concluded is True.
    """
    # Late imports to keep the fixture importable without forcing stage
    # imports at test-collection time.
    from stages.ideate import IdeationStage
    from stages.intake import IntakeStage
    from stages.prioritize import PrioritizationStage
    from stages.roadmap import RoadmapStage
    from stages.scan import MaturityScanStage

    tenant = tropico_tenant()
    eng = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))

    # Stage 1 — intake
    intake = IntakeStage()
    intake.run(eng)
    intake.log_interview(
        eng,
        interviewee="Catalina Vélez (COO)",
        role="COO",
        transcript_ref="interviews/coo.md",
        key_findings=["38 GWh/yr lost to curtailment"],
    )
    thesis = _thesis()
    intake.declare_thesis(eng, thesis)
    intake.request_review(eng, "Thesis declared, scope locked")

    # Stage 2 — maturity scan
    scan = MaturityScanStage()
    scan.run(eng)
    for dim in _maturity_dimensions():
        scan.score_dimension(eng, dim)
    scan.request_review(eng, "4 dimensions scored")

    # Stage 3 — ideation (4 distinct sources, 0% NOVELTY)
    ideate = IdeationStage()
    ideate.run(eng)
    use_cases = _use_cases()
    for uc in use_cases:
        ideate.propose_use_case(eng, uc)
    ideate.request_review(eng, "4 candidates across 4 distinct sources")

    # Stage 4 — prioritization
    prioritize = PrioritizationStage()
    prioritize.run(eng)
    top_3 = use_cases[:3]
    rice_scores = {"uc-mpc-solar": 14.9, "uc-inflow-fcst": 8.4, "uc-ffr-grid": 5.5}
    roi_cells = _roi_cells(top_3)
    for rank, (uc, roi) in enumerate(zip(top_3, roi_cells, strict=True), start=1):
        prioritize.prioritize_use_case(
            eng,
            use_case_id=uc.id,
            rice_score=rice_scores[uc.id],
            roi_cell=roi,
            rank=rank,
        )
    prioritize.render_impact_effort_matrix(eng, "/tmp/iem.md")
    prioritize.request_review(eng, "Top-3 selected, RoiCells ready")

    # Stage 5 — roadmap
    roadmap = RoadmapStage()
    roadmap.run(eng)
    for step in _roadmap_steps():
        roadmap.propose_roadmap_step(eng, step)
    baseline = _baseline()
    roadmap.capture_baseline(eng, baseline)
    pilot = _pilot(baseline, _adoption())
    roadmap.design_pilot(eng, pilot)
    roadmap.render_deliverables(
        eng,
        slugs=[
            "maturity-report",
            "capability-heatmap",
            "use-case-dossier",
            "impact-effort-matrix",
            "roi-model",
            "innovation-roadmap",
            "pilot-plan",
        ],
        output_dir="/tmp/tropico",
    )
    roadmap.request_review(eng, "Roadmap + baselines + pilot ready")
    roadmap.conclude(
        eng,
        top_pilot="uc-mpc-solar",
        deliverable_slugs=[
            "maturity-report",
            "capability-heatmap",
            "use-case-dossier",
            "impact-effort-matrix",
            "roi-model",
            "innovation-roadmap",
            "pilot-plan",
        ],
    )

    return eng


def deliverable_extras() -> dict[str, Any]:
    """Return the typed-primitive context the render orchestrator needs.

    Pairs with build_tropico_engagement() — the engagement carries the journal
    events; this function carries the typed Pydantic objects the templates
    iterate over (since the journal stores serialized payloads, not Pydantic
    objects).
    """
    from core.orchestrator import build_roi_totals

    thesis = _thesis()
    use_cases = _use_cases()
    top_3 = use_cases[:3]
    roi_cells = _roi_cells(top_3)
    rice_scores = {"uc-mpc-solar": 14.9, "uc-inflow-fcst": 8.4, "uc-ffr-grid": 5.5}
    baseline = _baseline()
    pilot = _pilot(baseline, _adoption())

    return {
        "thesis": thesis,
        "dimensions": _maturity_dimensions(),
        "capabilities": _capability_cells(),
        "use_cases": use_cases,
        "frameworks_applied": [
            "mit-cisr-digital",
            "gartner-ai",
            "rice",
            "real-options",
            "three-horizons",
        ],
        "ranked": [
            {
                "rank": rank,
                "use_case_id": uc.id,
                "rice_score": rice_scores[uc.id],
                "impact": uc.score_impact.value,
                "effort": uc.score_effort.value,
                "ideation_source": uc.ideation_source.value,
                "year1_net": roi.net,
            }
            for rank, (uc, roi) in enumerate(zip(top_3, roi_cells, strict=True), start=1)
        ],
        "top_n": 3,
        "roi_cells": roi_cells,
        "discount_rate": Decimal("0.14"),
        **build_roi_totals(roi_cells),
        "assumptions": [
            "Bolsa price holds at $79/MWh (±18% sensitivity)",
            "No regulatory delay on FFR market",
            "Vendor delivery on contract (uc-mpc-solar)",
        ],
        "roadmap_steps": _roadmap_steps(),
        "pilot": pilot,
        "generated_at": "2026-05-07",
    }


__all__ = [
    "TROPICO_CANARY_TOKENS",
    "build_tropico_engagement",
    "deliverable_extras",
    "tropico_tenant",
]


# Demonstration that the fixture isn't degenerate — silence the unused-import
# warning without burying the EventKind import. Test loaders import the fixture.
_EVENT_KIND_REF = EventKind  # noqa: F841 — keeps EventKind import close
