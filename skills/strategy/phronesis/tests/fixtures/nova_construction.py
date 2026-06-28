"""Synthetic Nova Construction engagement fixture — M6.

Reusable factory: build_nova_construction_engagement() returns a fully-populated
Engagement that:
  - Goes through all 5 stage runners (intake → scan → ideate → prioritize → roadmap)
  - Passes all 5 L-rules (L1-L5) — bision-prevention release-gate-clean
  - Records 7 deliverables as rendered
  - Concludes with state.is_concluded == True

Sister fixture to tropico_renovables.py + acme_bank.py — smaller-scale
engagement (4 interviews + 2 docs vs. acme-bank's 5 + 3) to prove the
substrate handles the engagement size spread.

Profile: synthetic CO mid-market constructora, construction industry,
CEO-sponsored. Tests that the 7-deliverable structure still produces with
fewer use cases + lower ROI numbers.

Anonymization canary list (10 tokens):
  tenant_slug, tenant_name, sponsor, 3 other interview names,
  2 project names, 1 city, 1 currency amount.

Used by:
  - tests/integration/test_nova_construction_e2e.py (M6 release gate)
  - tests/integration/test_anonymization_canary.py (M6 extension)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

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

# Severity literal alias — module-level so per-row tuples typecheck under
# mypy strict without tripping ruff N806 (function-local UpperCamelCase).
_Severity = Literal["critical", "major", "minor", "informational"]

# ----------------------------------------------------------------------------
# Tenant
# ----------------------------------------------------------------------------


def nova_construction_tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="nova-construction",
        name="Nova Construcciones S.A.S.",
        industry="construction",
        region="CO",
        revenue_band="10-100M",
        headcount_band="50-500",
        sponsor="Andrés Botero",
        sponsor_role="CEO",
        engagement_scope=(
            "AI/data maturity assessment + 3 prioritized use cases for a "
            "mid-market constructora running 11 active projects across "
            "residential + light-industrial verticals."
        ),
        starts_at=datetime(2026, 7, 8, tzinfo=UTC),
        target_duration_weeks=8,
    )


# Canary tokens — 14 strings that MUST NOT leak through anonymization.
# Aligned with the M7 14×3 release-gate convention shared with
# `acme_bank.py::ACME_BANK_CANARY_TOKENS` + `tropico_renovables.py
# ::TROPICO_CANARY_TOKENS`.
NOVA_CONSTRUCTION_CANARY_TOKENS: list[str] = [
    # Tenant identifiers (3)
    "nova-construction",
    "Nova Construcciones S.A.S.",
    "Nova Construcciones",
    # Sponsor + last name (2)
    "Andrés Botero",
    "Botero",
    # Other interviewees (3)
    "Sandra Castaño",
    "Javier Ospina",
    "Patricia Mejía",
    # Project codenames (2)
    "Torres Mirador",
    "Bodegas Norte",
    # City (1)
    "Barranquilla",
    # Currency amounts (3) — should bucket via core.anonymize bands
    "$680,000",
    "$120,000",
    "$110,000",
]


# Shared citations -----------------------------------------------------------

_INTERVIEW_CEO = Citation(
    kind="evidence",
    ref="interview:ceo-botero:2026-07-09",
    excerpt="11 active projects, ~$680K margin leakage from procurement variance",
    confidence="high",
)
_INTERVIEW_PROC = Citation(
    kind="evidence",
    ref="interview:head-procurement-castano:2026-07-10",
    excerpt="Supplier price variance 18% on commodity inputs",
    confidence="high",
)
_INTERVIEW_PM = Citation(
    kind="evidence",
    ref="interview:project-mgr-ospina:2026-07-10",
    excerpt="Schedule overruns avg 11% across last 12 projects",
    confidence="high",
)
_INTERVIEW_OPS = Citation(
    kind="evidence",
    ref="interview:ops-controller-mejia:2026-07-11",
    excerpt="Daily site reports in WhatsApp/PDF; no structured aggregate",
    confidence="medium",
)
_DOC_PROCUREMENT = Citation(
    kind="evidence",
    ref="doc:procurement-workflow:2026-Q3",
    excerpt="3-quote rule, manual reconciliation",
    confidence="high",
)
_DOC_SUPPLIERS = Citation(
    kind="evidence",
    ref="doc:supplier-list:2026-Q3",
    excerpt="42 active vendors, top-5 concentration 67%",
    confidence="high",
)
_BENCH_CO_CONSTRUCTION = Citation(
    kind="evidence",
    ref="bench:co-construction-mid-market-2025",
    excerpt="CO mid-market construction maturity benchmark 2025",
    confidence="medium",
)


# ----------------------------------------------------------------------------
# Typed primitives — built once and reused across stages + deliverables
# ----------------------------------------------------------------------------


def _thesis() -> StrategicThesis:
    return StrategicThesis(
        economic_lever=(
            "Recover $680K/yr by closing the procurement-variance gap "
            "(18% commodity input variance) and shrinking schedule overruns "
            "(currently 11%) through structured data aggregation + supplier "
            "price prediction."
        ),
        lever_kind="cost",
        magnitude_estimate=Decimal("680000"),
        magnitude_basis=(
            "11 projects × $42M total exec × 1.5% variance recapture + "
            "schedule overrun reduction × labor cost"
        ),
        strategic_horizon="h1-now",
        decision_rights_owner="Andrés Botero (CEO)",
        measured_in="USD/yr",
        evidence=[_INTERVIEW_CEO, _INTERVIEW_PROC],
    )


def _maturity_dimensions() -> list[MaturityDimension]:
    rows = [
        ("Operational data", 1.5, 3.0, "Daily reports in WhatsApp/PDF only"),
        ("Procurement intelligence", 1.5, 3.0, "Manual 3-quote rule, no analytics"),
        ("Project-mgmt digitization", 2.0, 3.5, "Excel + ERP, no real-time dashboards"),
    ]
    out: list[MaturityDimension] = []
    for name, current, target, gap in rows:
        out.append(
            MaturityDimension(
                name=name,
                framework_ref="framework:gartner-ai",
                current_score=Score(
                    dimension=name.lower().replace(" ", "-").replace("/", "-"),
                    value=current,
                    scale=(1.0, 5.0),
                    rubric_ref="cisr",
                    rationale=f"Current state for {name}",
                    evidence=[_INTERVIEW_OPS, _DOC_PROCUREMENT],
                ),
                target_score=Score(
                    dimension=name.lower().replace(" ", "-").replace("/", "-"),
                    value=target,
                    scale=(1.0, 5.0),
                    rubric_ref="cisr",
                    rationale=f"Target benchmarked vs CO mid-market peers ({name})",
                    evidence=[_BENCH_CO_CONSTRUCTION],
                ),
                gap_summary=gap,
                key_actions=[f"Close {name} gap via 3-month sprint"],
                evidence=[_INTERVIEW_CEO, _INTERVIEW_PROC],
            )
        )
    return out


def _capability_cells() -> list[CapabilityCell]:
    return [
        CapabilityCell(
            capability="Site-data ingestion pipeline",
            category="data",
            current_state="absent",
            target_state="defined",
            criticality="foundational",
            evidence=[_INTERVIEW_OPS],
        ),
        CapabilityCell(
            capability="Procurement analytics",
            category="tooling",
            current_state="absent",
            target_state="defined",
            criticality="foundational",
            evidence=[_INTERVIEW_PROC, _DOC_PROCUREMENT],
        ),
        CapabilityCell(
            capability="ML engineering function",
            category="talent",
            current_state="absent",
            target_state="ad-hoc",
            criticality="important",
            evidence=[_INTERVIEW_CEO],
        ),
        CapabilityCell(
            capability="Project-mgmt dashboard",
            category="tooling",
            current_state="ad-hoc",
            target_state="defined",
            criticality="important",
            evidence=[_INTERVIEW_PM],
        ),
    ]


def _findings() -> list[Finding]:
    """~20 findings — smaller than acme-bank's 25, matching the engagement scale."""
    rows: list[tuple[str, str, _Severity]] = [
        ("F-1", "Daily site reports unstructured (WhatsApp/PDF)", "major"),
        ("F-2", "Supplier price variance 18% on commodities", "major"),
        ("F-3", "Schedule overruns avg 11% trailing 12 projects", "major"),
        ("F-4", "No procurement analytics layer", "major"),
        ("F-5", "Top-5 supplier concentration 67%", "minor"),
        ("F-6", "Project-mgmt KPIs reported manually monthly", "major"),
        ("F-7", "Subcontractor performance not tracked centrally", "major"),
        ("F-8", "Safety incidents under-reported (paper forms)", "major"),
        ("F-9", "BIM models exist but disconnected from execution", "minor"),
        ("F-10", "Inventory shrinkage suspected but unmeasured", "minor"),
        ("F-11", "Cash-flow forecasting Excel-based", "major"),
        ("F-12", "Vendor-payment cycle inconsistent across projects", "minor"),
        ("F-13", "No experiment-tracking infrastructure (no ML in prod)", "minor"),
        ("F-14", "Limited data engineering capacity (1 FTE)", "major"),
        ("F-15", "Quality-control inspection results in spreadsheets", "minor"),
        ("F-16", "Lessons-learned across projects not codified", "minor"),
        ("F-17", "Bid-margin variance not analyzed post-mortem", "major"),
        ("F-18", "Equipment utilization tracked manually", "minor"),
        ("F-19", "Schedule deviation root-cause analysis absent", "major"),
        ("F-20", "Cloud spend untracked at project granularity", "informational"),
    ]
    return [
        Finding(
            title=title,
            body=f"Detail for {fid}: {title}. Surfaced during Stage 2 scan.",
            severity=sev,
            confidence="medium",
            evidence=[_INTERVIEW_OPS, _DOC_PROCUREMENT],
        )
        for fid, title, sev in rows
    ]


def _use_cases() -> list[UseCase]:
    """8 use cases across 4 distinct sources (no NOVELTY — small engagement
    stays disciplined on impact-driven prioritization)."""
    rows = [
        ("uc-procurement-pred", "320000", "120000", IdeationSource.BUSINESS_PAIN),
        ("uc-site-data-pipeline", "240000", "150000", IdeationSource.DATA_OPPORTUNITY),
        ("uc-schedule-risk-ml", "180000", "95000", IdeationSource.BUSINESS_PAIN),
        ("uc-supplier-scoring", "140000", "60000", IdeationSource.DATA_OPPORTUNITY),
        ("uc-safety-incident-ai", "90000", "55000", IdeationSource.REGULATORY_PRESSURE),
        ("uc-bid-margin-postmortem", "120000", "45000", IdeationSource.BUSINESS_PAIN),
        ("uc-equipment-util", "85000", "40000", IdeationSource.DATA_OPPORTUNITY),
        ("uc-bim-execution-link", "110000", "70000", IdeationSource.COMPETITIVE_RESPONSE),
    ]
    out: list[UseCase] = []
    for uc_id, value, cost, source in rows:
        out.append(
            UseCase(
                id=uc_id,
                problem=f"Problem statement for {uc_id}",
                hypothesis=f"Working hypothesis for {uc_id}",
                solution_summary=f"Solution summary for {uc_id}",
                expected_value=Decimal(value),
                cost_estimate=Decimal(cost),
                cost_breakdown={
                    "build": Decimal(cost) * Decimal("0.7"),
                    "run": Decimal(cost) * Decimal("0.3"),
                },
                data_required=["procurement-records", "project-schedule"],
                capabilities_required=["data-pipeline"],
                risks=[
                    Finding(
                        title=f"{uc_id} adoption risk",
                        body="Site teams may resist new workflow",
                        severity="major",
                        confidence="medium",
                        evidence=[_INTERVIEW_PM],
                    )
                ],
                framework_lens=["rice"],
                score_impact=Score(
                    dimension="impact",
                    value=6.5,
                    scale=(0.0, 10.0),
                    rubric_ref="rice",
                    rationale="Impact rationale",
                    evidence=[_INTERVIEW_CEO],
                ),
                score_effort=Score(
                    dimension="effort",
                    value=4.0,
                    scale=(0.0, 10.0),
                    rubric_ref="rice",
                    rationale="Effort rationale",
                    evidence=[_INTERVIEW_PM],
                ),
                ideation_source=source,
                data_readiness=DataReadinessAssessment(
                    use_case_id=uc_id,
                    data_dependencies=["procurement-records"],
                    weakest_dependency_state="ad-hoc",
                    readiness_band="needs-prep",
                    prep_phase_required=True,
                    prep_phase_estimated_weeks=4,
                    prep_phase_owner="Head of Procurement",
                ),
                evidence=[_INTERVIEW_CEO, _INTERVIEW_PROC],
            )
        )
    return out


def _roi_cells(top_use_cases: list[UseCase]) -> list[RoiCell]:
    cells: list[RoiCell] = []
    for uc in top_use_cases:
        net = uc.expected_value - uc.cost_estimate
        cells.append(
            RoiCell(
                use_case_id=uc.id,
                year=1,
                revenue_impact=uc.expected_value,
                cost_savings=Decimal("0"),
                investment=uc.cost_estimate,
                one_time_cost=uc.cost_estimate * Decimal("0.6"),
                recurring_cost=uc.cost_estimate * Decimal("0.4"),
                net=net,
                cumulative_net=net,
                discount_rate=Decimal("0.15"),
                sensitivity_low=net * Decimal("0.5"),
                sensitivity_high=net * Decimal("1.5"),
                assumptions=["Project pipeline holds at 11 active ±2"],
            )
        )
    return cells


def _roadmap_steps() -> list[RoadmapStep]:
    return [
        RoadmapStep(
            id="rs-h1-procurement",
            title="Procurement price prediction pilot",
            horizon="h1-now",
            quarter="2026-Q4",
            related_use_cases=["uc-procurement-pred"],
            related_recommendations=["rec-procurement"],
            dependencies=["procurement-data-cleaned"],
            owner="Head of Procurement",
            success_gate=">=8% variance recapture vs 18% baseline",
        ),
        RoadmapStep(
            id="rs-h2-site-data",
            title="Site-data ingestion pipeline rollout",
            horizon="h2-next",
            quarter="2027-Q2",
            related_use_cases=["uc-site-data-pipeline"],
            related_recommendations=["rec-site-pipeline"],
            dependencies=["rs-h1-procurement success"],
            owner="Ops Controller",
            success_gate="Daily aggregate dashboards live across 8 projects",
        ),
        RoadmapStep(
            id="rs-h3-schedule",
            title="Schedule-risk ML scoring (advisory)",
            horizon="h3-later",
            quarter="2027-Q4",
            related_use_cases=["uc-schedule-risk-ml"],
            related_recommendations=["rec-schedule"],
            dependencies=["site-data pipeline managed"],
            owner="VP Operations",
            success_gate="Schedule deviation early-warn lead time >=3 weeks",
        ),
    ]


def _baseline() -> BaselineSection:
    return BaselineSection(
        metric_name="Commodity-input price variance",
        baseline_value=Decimal("0.18"),
        baseline_window="2026-Q2 procurement ledger",
        baseline_data_source="ERP procurement export",
        baseline_measurement_date=datetime(2026, 6, 30, tzinfo=UTC),
        captured_by="Head of Procurement + CEO",
        evidence=[_INTERVIEW_PROC, _DOC_PROCUREMENT],
    )


def _adoption() -> AdoptionMetric:
    return AdoptionMetric(
        metric_name="Procurement team uses price-prediction recommendation",
        target_value=">=70% of POs reference the prediction prior to issue",
        measurement_method="ERP PO field audit, weekly cadence",
        owner="Head of Procurement",
    )


def _pilot(baseline: BaselineSection, adoption: AdoptionMetric) -> PilotDesign:
    return PilotDesign(
        use_case_id="uc-procurement-pred",
        hypothesis=(
            "A commodity price prediction model + supplier-scoring overlay "
            "shrinks input variance from 18% to <=10% across the 5 highest-"
            "spend commodities within 12 weeks."
        ),
        null_hypothesis="No statistically significant variance reduction at p<0.05",
        duration_weeks=12,
        cohort_definition=(
            "Top-5 commodity inputs (cement, steel, aggregates, lumber, "
            "rebar) across 11 active projects. Other 8 inputs = control."
        ),
        success_criteria=[
            "Variance <=10% sustained weeks 8-12",
            "Supplier mix maintains top-5 concentration <=70%",
            "Adoption metric >=70% by week 10",
        ],
        kill_criterion="Week-6 variance >15% OR cost net increase",
        learning_objectives=[
            "Vendor catalog cleanliness vs prediction quality tradeoff",
            "Forecast horizon (4-week vs 8-week) accuracy curve",
        ],
        risks=[
            Finding(
                title="Vendor data sparseness",
                body=(
                    "Some commodities have <12-month price history — "
                    "prediction confidence band needs to widen accordingly."
                ),
                severity="minor",
                confidence="high",
                evidence=[_INTERVIEW_PROC],
            )
        ],
        cost_estimate=Decimal("120000"),
        adoption_metric=adoption,
        baseline=[baseline],
        evidence=[_INTERVIEW_CEO, _INTERVIEW_PROC],
    )


def _pilot_site_data(adoption: AdoptionMetric) -> PilotDesign:
    """Second pilot — site-data pipeline. Tests that multi-pilot engagements
    surface multiple BASELINE_CAPTURED → PILOT_STARTED orderings."""
    second_baseline = BaselineSection(
        metric_name="Daily site report structured-data coverage",
        baseline_value=Decimal("0.0"),
        baseline_window="2026-Q2 trailing 90 days",
        baseline_data_source="Project archive audit",
        baseline_measurement_date=datetime(2026, 6, 30, tzinfo=UTC),
        captured_by="Ops Controller",
        evidence=[_INTERVIEW_OPS],
        is_greenfield=True,
    )
    return PilotDesign(
        use_case_id="uc-site-data-pipeline",
        hypothesis=(
            "Structured daily-site-report capture rises from 0% (greenfield) "
            "to >=60% adoption across 3 pilot projects within 8 weeks."
        ),
        null_hypothesis="Adoption stalls below 30%",
        duration_weeks=8,
        cohort_definition="3 of 11 active projects (selected by PM team)",
        success_criteria=["Coverage >=60% by week 6"],
        kill_criterion="Coverage <30% by week 4",
        learning_objectives=["WhatsApp-to-structured workflow viability"],
        risks=[
            Finding(
                title="Site supervisor digital literacy",
                body="Mixed comfort levels with mobile structured entry",
                severity="minor",
                confidence="high",
                evidence=[_INTERVIEW_OPS],
            )
        ],
        cost_estimate=Decimal("150000"),
        adoption_metric=adoption,
        baseline=[second_baseline],
        evidence=[_INTERVIEW_OPS, _INTERVIEW_PM],
    )


# ----------------------------------------------------------------------------
# Public factories
# ----------------------------------------------------------------------------


def build_nova_construction_engagement() -> Engagement:
    """Construct a fully-populated, L-clean Nova Construction engagement.

    Drives all 5 stage runners. The engagement passes through:
      Stage 1 (intake) → Stage 2 (scan) → Stage 3 (ideate)
      → Stage 4 (prioritize) → Stage 5 (roadmap) → concluded.
    """
    from stages.ideate import IdeationStage
    from stages.intake import IntakeStage
    from stages.prioritize import PrioritizationStage
    from stages.roadmap import RoadmapStage
    from stages.scan import MaturityScanStage

    tenant = nova_construction_tenant()
    eng = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))

    # Stage 1 — intake (4 interviews + 2 documents)
    intake = IntakeStage()
    intake.run(eng)
    interviews = [
        (
            "Andrés Botero (CEO)",
            "CEO",
            "interviews/ceo.md",
            ["11 active projects", "$680K margin leakage"],
        ),
        (
            "Sandra Castaño (Head of Procurement)",
            "Head of Procurement",
            "interviews/proc.md",
            ["Supplier variance 18%", "Manual 3-quote rule"],
        ),
        (
            "Javier Ospina (Project Manager)",
            "Project Manager",
            "interviews/pm.md",
            ["Schedule overruns 11%", "BIM disconnected"],
        ),
        (
            "Patricia Mejía (Ops Controller)",
            "Ops Controller",
            "interviews/ops.md",
            ["WhatsApp/PDF daily reports"],
        ),
    ]
    for interviewee, role, ref, findings_kw in interviews:
        intake.log_interview(
            eng,
            interviewee=interviewee,
            role=role,
            transcript_ref=ref,
            key_findings=findings_kw,
        )
    intake.ingest_document(
        eng,
        path="docs/procurement-workflow.md",
        kind="report",
        summary="3-quote rule, manual reconciliation",
    )
    intake.ingest_document(
        eng,
        path="docs/supplier-list.md",
        kind="report",
        summary="42 active vendors, top-5 concentration 67%",
    )
    thesis = _thesis()
    intake.declare_thesis(eng, thesis)
    intake.request_review(eng, "Thesis declared on procurement + schedule levers")

    # Stage 2 — maturity scan (3 dimensions — smaller engagement)
    scan = MaturityScanStage()
    scan.run(eng)
    for dim in _maturity_dimensions():
        scan.score_dimension(eng, dim)
    scan.request_review(eng, "3 dimensions scored on Gartner AI framework")

    # Stage 3 — ideation (8 candidates across 4 sources, 0% NOVELTY)
    ideate = IdeationStage()
    ideate.run(eng)
    use_cases = _use_cases()
    for uc in use_cases:
        ideate.propose_use_case(eng, uc)
    ideate.request_review(eng, "8 candidates surfaced across 4 distinct sources")

    # Stage 4 — prioritization (top-3)
    prioritize = PrioritizationStage()
    prioritize.run(eng)
    top_3 = use_cases[:3]
    rice_scores = {
        "uc-procurement-pred": 16.5,
        "uc-site-data-pipeline": 9.8,
        "uc-schedule-risk-ml": 7.4,
    }
    roi_cells = _roi_cells(top_3)
    for rank, (uc, roi) in enumerate(zip(top_3, roi_cells, strict=True), start=1):
        prioritize.prioritize_use_case(
            eng,
            use_case_id=uc.id,
            rice_score=rice_scores[uc.id],
            roi_cell=roi,
            rank=rank,
        )
    prioritize.render_impact_effort_matrix(eng, "/tmp/iem-nova.md")
    prioritize.request_review(eng, "Top-3 selected, RoiCells ready")

    # Stage 5 — roadmap (3 steps + 2 baselines + 2 pilots designed)
    roadmap = RoadmapStage()
    roadmap.run(eng)
    for step in _roadmap_steps():
        roadmap.propose_roadmap_step(eng, step)
    procurement_baseline = _baseline()
    roadmap.capture_baseline(eng, procurement_baseline)
    pilot = _pilot(procurement_baseline, _adoption())
    roadmap.design_pilot(eng, pilot)
    # Second pilot — site-data, greenfield (zero-state baseline)
    site_data_adoption = AdoptionMetric(
        metric_name="Structured daily report submission rate",
        target_value=">=60% of site-days have structured submissions",
        measurement_method="Project archive audit, weekly cadence",
        owner="Ops Controller",
    )
    site_data_pilot = _pilot_site_data(site_data_adoption)
    # Capture the second pilot's baseline before designing it
    roadmap.capture_baseline(eng, site_data_pilot.baseline[0])
    roadmap.design_pilot(eng, site_data_pilot)
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
        output_dir="/tmp/nova-construction",
    )
    roadmap.request_review(eng, "Roadmap + baselines + 2 pilots ready")
    roadmap.conclude(
        eng,
        top_pilot="uc-procurement-pred",
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
    """Return the typed-primitive context the render orchestrator needs."""
    from core.orchestrator import build_roi_totals

    thesis = _thesis()
    use_cases = _use_cases()
    top_3 = use_cases[:3]
    roi_cells = _roi_cells(top_3)
    rice_scores = {
        "uc-procurement-pred": 16.5,
        "uc-site-data-pipeline": 9.8,
        "uc-schedule-risk-ml": 7.4,
    }
    procurement_baseline = _baseline()
    pilot = _pilot(procurement_baseline, _adoption())

    return {
        "thesis": thesis,
        "dimensions": _maturity_dimensions(),
        "capabilities": _capability_cells(),
        "use_cases": use_cases,
        "frameworks_applied": [
            "gartner-ai",
            "rice",
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
        "discount_rate": Decimal("0.15"),
        **build_roi_totals(roi_cells),
        "assumptions": [
            "Project pipeline steady at 11 active (±2)",
            "Commodity-input mix stable through pilot",
            "Vendor data history available (≥12 months for 4/5 commodities)",
        ],
        "roadmap_steps": _roadmap_steps(),
        "pilot": pilot,
        "generated_at": "2026-07-15",
    }


def findings_for_test() -> list[Finding]:
    """Expose the synthetic-finding list for E2E tests that assert count."""
    return _findings()


__all__ = [
    "NOVA_CONSTRUCTION_CANARY_TOKENS",
    "build_nova_construction_engagement",
    "deliverable_extras",
    "findings_for_test",
    "nova_construction_tenant",
]


# Silence the EventKind unused-import warning.
_EVENT_KIND_REF = EventKind  # noqa: F841
