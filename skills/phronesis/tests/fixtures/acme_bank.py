"""Synthetic Acme Bank engagement fixture — M6.

Reusable factory: build_acme_bank_engagement() returns a fully-populated
Engagement that:
  - Goes through all 5 stage runners (intake → scan → ideate → prioritize → roadmap)
  - Passes all 5 L-rules (L1-L5) — bision-prevention release-gate-clean
  - Records 7 deliverables as rendered
  - Concludes with state.is_concluded == True

Sister fixture to tropico_renovables.py — same shape, different industry +
scale + tenant identity, so the substrate is exercised across the spread
of real engagements Phase 2 will see.

Profile: synthetic LATAM mid-market bank, financial services, CDO-sponsored.
Larger scale than Tropico (more interviews, more use cases, more findings).

Anonymization canary list (14 tokens — verified by
tests/integration/test_anonymization_canary.py:
  tenant_slug, tenant_name, sponsor, 4 person names from interviews,
  3 product names, 3 cities, 2 currency amounts).

Used by:
  - tests/integration/test_acme_bank_e2e.py (M6 release gate)
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

# Severity literal alias — kept module-level so per-row tuples typecheck
# under mypy strict (function-local TypeAliases trip ruff N806).
_Severity = Literal["critical", "major", "minor", "informational"]

# ----------------------------------------------------------------------------
# Tenant
# ----------------------------------------------------------------------------


def acme_bank_tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="acme-bank",
        name="Acme Bank Holdings S.A.",
        industry="fin-services",
        region="CO",
        revenue_band="100M-1B",
        headcount_band="500-5000",
        sponsor="Mariana Restrepo",
        sponsor_role="CDO",
        engagement_scope=(
            "AI maturity assessment + 5 prioritized use cases across "
            "retail banking, SME credit, and ops for a 1.2M-customer "
            "mid-market bank with 23-branch footprint."
        ),
        starts_at=datetime(2026, 6, 1, tzinfo=UTC),
        target_duration_weeks=12,
    )


# Canary tokens — 14 strings that MUST NOT leak through anonymization.
# Aligned with the M7 14×3 release-gate convention shared with
# `tropico_renovables.py::TROPICO_CANARY_TOKENS` + `nova_construction.py
# ::NOVA_CONSTRUCTION_CANARY_TOKENS`. The 14: tenant_slug + tenant_name +
# sponsor + 4 interviewees + 3 product/project names + 3 branch cities +
# 1 sensitive currency magnitude (the headline thesis figure).
ACME_BANK_CANARY_TOKENS: list[str] = [
    "acme-bank",
    "Acme Bank Holdings S.A.",
    "Mariana Restrepo",
    # Other interviewed people (4)
    "Roberto Sánchez",
    "Diego Maldonado",
    "Lucía Forero",
    "Felipe Quintero",
    # Product / project names (3)
    "AcmePay",
    "TarjetaPlus",
    "CrediFlex",
    # Branch cities (CO-specific) (3)
    "Bogotá",
    "Medellín",
    "Cartagena",
    # Sensitive currency amount (must bucket to a band) (1)
    "$4,200,000",
]


# Shared citations -----------------------------------------------------------

_INTERVIEW_CDO = Citation(
    kind="evidence",
    ref="interview:cdo-restrepo:2026-06-02",
    excerpt="~12K Tier-1 service tickets/month; 4-day avg resolution",
    confidence="high",
)
_INTERVIEW_CFO = Citation(
    kind="evidence",
    ref="interview:cfo-sanchez:2026-06-03",
    excerpt="SME credit default rate 4.7%; manual underwriting 3.5d cycle",
    confidence="high",
)
_INTERVIEW_CTO = Citation(
    kind="evidence",
    ref="interview:cto-maldonado:2026-06-04",
    excerpt="3 core systems; data lake on AWS; no production ML",
    confidence="high",
)
_INTERVIEW_HEAD_CS = Citation(
    kind="evidence",
    ref="interview:head-cs-forero:2026-06-05",
    excerpt="65% of Tier-1 tickets are balance/transaction queries",
    confidence="high",
)
_INTERVIEW_LEAD_DE = Citation(
    kind="evidence",
    ref="interview:lead-de-quintero:2026-06-05",
    excerpt="Core ETL nightly; transactions land in lake within 6h",
    confidence="medium",
)
_DOC_ORG_CHART = Citation(
    kind="evidence",
    ref="doc:org-chart:2026-Q2",
    excerpt="3 BUs: Retail (350 FTE), SME (180 FTE), Treasury (90 FTE)",
    confidence="high",
)
_DOC_IT_ARCH = Citation(
    kind="evidence",
    ref="doc:it-architecture-narrative:2026-Q2",
    excerpt="3-core legacy; Mambu evaluation in pilot; AWS DL since 2024",
    confidence="high",
)
_DOC_INCIDENT = Citation(
    kind="evidence",
    ref="doc:incident-report:redacted:2026-Q1",
    excerpt="Manual reconciliation gap surfaced after batch failure",
    confidence="medium",
)
_BENCH_LATAM = Citation(
    kind="evidence",
    ref="bench:latam-mid-market-bank-2025",
    excerpt="LATAM mid-market bank AI maturity peer benchmark 2025",
    confidence="medium",
)


# ----------------------------------------------------------------------------
# Typed primitives — built once and reused across stages + deliverables
# ----------------------------------------------------------------------------


def _thesis() -> StrategicThesis:
    return StrategicThesis(
        economic_lever=(
            "Recover $4.2M/yr through (a) self-service deflection of 65% of "
            "Tier-1 balance/transaction queries and (b) ML-augmented SME "
            "credit underwriting that compresses cycle time from 3.5d to <1d."
        ),
        lever_kind="cost",
        magnitude_estimate=Decimal("4200000"),
        magnitude_basis=(
            "12K tickets/mo × 65% deflect × $14/ticket avg cost + "
            "SME book $180M × 40% velocity-driven volume × 1.4% margin"
        ),
        strategic_horizon="h1-now",
        decision_rights_owner="Mariana Restrepo (CDO)",
        measured_in="USD/yr",
        evidence=[_INTERVIEW_CDO, _INTERVIEW_CFO],
    )


def _maturity_dimensions() -> list[MaturityDimension]:
    rows = [
        ("Data infrastructure", 2.5, 4.0, "Lake exists, no feature store"),
        ("ML/AI capability", 1.0, 3.0, "No production ML; PoCs only"),
        ("Customer-facing AI", 1.0, 3.5, "No chatbot, no smart triage"),
        ("Risk-modeling readiness", 2.0, 3.5, "Logistic regression scorecards"),
    ]
    out: list[MaturityDimension] = []
    for name, current, target, gap in rows:
        out.append(
            MaturityDimension(
                name=name,
                framework_ref="framework:mit-cisr-digital",
                current_score=Score(
                    dimension=name.lower().replace(" ", "-").replace("/", "-"),
                    value=current,
                    scale=(1.0, 5.0),
                    rubric_ref="cisr",
                    rationale=f"Current state for {name}",
                    evidence=[_INTERVIEW_CTO, _DOC_IT_ARCH],
                ),
                target_score=Score(
                    dimension=name.lower().replace(" ", "-").replace("/", "-"),
                    value=target,
                    scale=(1.0, 5.0),
                    rubric_ref="cisr",
                    rationale=f"Target benchmarked vs LATAM mid-market peers ({name})",
                    evidence=[_BENCH_LATAM],
                ),
                gap_summary=gap,
                key_actions=[
                    f"Close {name} gap via 6-month sprint",
                    f"Hire/upskill {name} lead",
                ],
                evidence=[_INTERVIEW_CDO, _INTERVIEW_LEAD_DE],
            )
        )
    return out


def _capability_cells() -> list[CapabilityCell]:
    return [
        CapabilityCell(
            capability="Customer-tier ML pipeline",
            category="tooling",
            current_state="absent",
            target_state="defined",
            criticality="foundational",
            evidence=[_INTERVIEW_LEAD_DE, _DOC_IT_ARCH],
        ),
        CapabilityCell(
            capability="ML engineering team",
            category="talent",
            current_state="absent",
            target_state="managed",
            criticality="foundational",
            evidence=[_INTERVIEW_CTO, _DOC_ORG_CHART],
        ),
        CapabilityCell(
            capability="Feature store",
            category="tooling",
            current_state="absent",
            target_state="defined",
            criticality="foundational",
            evidence=[_INTERVIEW_LEAD_DE],
        ),
        CapabilityCell(
            capability="Conversational AI platform",
            category="tooling",
            current_state="absent",
            target_state="defined",
            criticality="important",
            evidence=[_INTERVIEW_HEAD_CS],
        ),
        CapabilityCell(
            capability="Model risk governance",
            category="governance",
            current_state="ad-hoc",
            target_state="managed",
            criticality="foundational",
            evidence=[_INTERVIEW_CFO, _DOC_INCIDENT],
        ),
        CapabilityCell(
            capability="Real-time event stream",
            category="data",
            current_state="absent",
            target_state="defined",
            criticality="important",
            evidence=[_INTERVIEW_LEAD_DE],
        ),
    ]


def _findings() -> list[Finding]:
    """Stage-2 + Stage-3 findings — surfaced for the deliverable narrative.
    Targets ~30 findings spread across the 4 maturity dimensions, key
    operational gaps, and per-use-case risks. The use-case risks (counted
    separately on UseCase.risks) are NOT double-counted here.
    """
    rows: list[tuple[str, str, _Severity]] = [
        ("F-1", "No feature store", "major"),
        ("F-2", "ETL latency 6h blocks real-time decisions", "major"),
        ("F-3", "Customer 360 view fragmented across 3 cores", "major"),
        ("F-4", "No production ML pipeline", "major"),
        ("F-5", "Tier-1 service center under-automated", "major"),
        ("F-6", "Credit underwriting cycle 3.5 days vs <1d benchmark", "major"),
        ("F-7", "Model-risk governance ad-hoc", "major"),
        ("F-8", "No conversational interface for retail", "major"),
        ("F-9", "Branch-network traffic data unanalyzed", "minor"),
        ("F-10", "Fraud-detection rules static (not ML)", "major"),
        ("F-11", "AML reporting manually compiled", "major"),
        ("F-12", "Marketing campaign attribution unmeasured", "minor"),
        ("F-13", "SME default modelling on logistic regression only", "major"),
        ("F-14", "No experiment-tracking infrastructure", "minor"),
        ("F-15", "Data lineage opaque from core → lake", "major"),
        ("F-16", "Vendor concentration risk (3 core systems, 1 vendor)", "minor"),
        ("F-17", "Tier-2 (corporate) needs not yet scoped", "informational"),
        ("F-18", "Compliance team operating without ML expertise", "major"),
        ("F-19", "Treasury BU excluded from initial scope", "informational"),
        ("F-20", "Cloud spend untracked at workload granularity", "minor"),
        ("F-21", "Customer-churn early-warning absent", "major"),
        ("F-22", "Branch-staff allocation data-driven gaps", "minor"),
        ("F-23", "No A/B testing capability for digital channels", "major"),
        ("F-24", "Mobile app NPS lower than retail-bank peer median", "minor"),
        ("F-25", "Operational risk metrics manually aggregated", "minor"),
    ]
    return [
        Finding(
            title=title,
            body=f"Detail for {fid}: {title}. Surfaced during Stage 2 scan.",
            severity=sev,
            confidence="medium",
            evidence=[_INTERVIEW_CTO, _DOC_IT_ARCH],
        )
        for fid, title, sev in rows
    ]


def _use_cases() -> list[UseCase]:
    """12 use cases — slightly above the deliverable threshold so prioritization
    has a real selection problem; matches the expected ~12 from the handoff."""
    rows = [
        ("uc-chatbot-tier1", "1200000", "320000", IdeationSource.BUSINESS_PAIN),
        ("uc-sme-credit-ml", "1800000", "550000", IdeationSource.BUSINESS_PAIN),
        ("uc-fraud-ml", "850000", "280000", IdeationSource.REGULATORY_PRESSURE),
        ("uc-churn-early-warn", "450000", "190000", IdeationSource.DATA_OPPORTUNITY),
        ("uc-aml-automation", "380000", "160000", IdeationSource.REGULATORY_PRESSURE),
        ("uc-branch-staffing", "180000", "70000", IdeationSource.DATA_OPPORTUNITY),
        ("uc-mobile-recsys", "260000", "140000", IdeationSource.COMPETITIVE_RESPONSE),
        ("uc-treasury-fx", "320000", "180000", IdeationSource.DATA_OPPORTUNITY),
        ("uc-collections-ml", "420000", "200000", IdeationSource.BUSINESS_PAIN),
        ("uc-marketing-ltv", "210000", "120000", IdeationSource.COMPETITIVE_RESPONSE),
        ("uc-doc-extraction", "190000", "85000", IdeationSource.DATA_OPPORTUNITY),
        ("uc-genai-experiment", "150000", "180000", IdeationSource.NOVELTY),
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
                    "build": Decimal(cost) * Decimal("0.6"),
                    "run": Decimal(cost) * Decimal("0.4"),
                },
                data_required=["transactions", "customer-master"],
                capabilities_required=["feature-store", "ml-pipeline"],
                risks=[
                    Finding(
                        title=f"{uc_id} adoption risk",
                        body="Branch staff or customers may resist new flow",
                        severity="major",
                        confidence="medium",
                        evidence=[_INTERVIEW_HEAD_CS],
                    )
                ],
                framework_lens=["rice", "real-options"],
                score_impact=Score(
                    dimension="impact",
                    value=7.5,
                    scale=(0.0, 10.0),
                    rubric_ref="rice",
                    rationale="Impact rationale",
                    evidence=[_INTERVIEW_CDO],
                ),
                score_effort=Score(
                    dimension="effort",
                    value=5.0,
                    scale=(0.0, 10.0),
                    rubric_ref="rice",
                    rationale="Effort rationale",
                    evidence=[_INTERVIEW_CTO],
                ),
                ideation_source=source,
                data_readiness=DataReadinessAssessment(
                    use_case_id=uc_id,
                    data_dependencies=["transaction-stream", "customer-master"],
                    weakest_dependency_state="managed",
                    readiness_band="pilot-ready",
                    prep_phase_required=False,
                ),
                evidence=[_INTERVIEW_CDO, _INTERVIEW_LEAD_DE],
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
                one_time_cost=uc.cost_estimate * Decimal("0.65"),
                recurring_cost=uc.cost_estimate * Decimal("0.35"),
                net=net,
                cumulative_net=net,
                discount_rate=Decimal("0.16"),
                sensitivity_low=net * Decimal("0.55"),
                sensitivity_high=net * Decimal("1.4"),
                assumptions=["Customer-base steady ±5%"],
            )
        )
    return cells


def _roadmap_steps() -> list[RoadmapStep]:
    return [
        RoadmapStep(
            id="rs-h1-chatbot",
            title="Tier-1 deflection chatbot pilot",
            horizon="h1-now",
            quarter="2026-Q4",
            related_use_cases=["uc-chatbot-tier1"],
            related_recommendations=["rec-chatbot"],
            dependencies=["transaction-stream-online"],
            owner="VP Customer Service",
            success_gate=">=55% deflection of balance/txn queries",
        ),
        RoadmapStep(
            id="rs-h1-sme-credit",
            title="SME credit ML pilot (1 segment)",
            horizon="h1-now",
            quarter="2026-Q4",
            related_use_cases=["uc-sme-credit-ml"],
            related_recommendations=["rec-sme-credit"],
            dependencies=["feature-store-managed"],
            owner="VP SME",
            success_gate="Cycle <=1.5d on pilot segment, default rate parity",
        ),
        RoadmapStep(
            id="rs-h2-fraud",
            title="ML fraud detection portfolio rollout",
            horizon="h2-next",
            quarter="2027-Q1",
            related_use_cases=["uc-fraud-ml"],
            related_recommendations=["rec-fraud"],
            dependencies=["rs-h1-chatbot success"],
            owner="CISO",
            success_gate="Recall +20%, false-positive -30% vs static rules",
        ),
        RoadmapStep(
            id="rs-h2-churn",
            title="Customer churn early-warning",
            horizon="h2-next",
            quarter="2027-Q2",
            related_use_cases=["uc-churn-early-warn"],
            related_recommendations=["rec-churn"],
            dependencies=["customer-360 unified"],
            owner="VP Retail",
            success_gate="Retain >=40% of high-risk segment via targeted offers",
        ),
        RoadmapStep(
            id="rs-h3-genai",
            title="Generative AI customer-rep copilot",
            horizon="h3-later",
            quarter="2027-Q4",
            related_use_cases=["uc-genai-experiment"],
            related_recommendations=["rec-genai"],
            dependencies=["model-risk governance managed"],
            owner="CDO",
            success_gate="Productivity uplift measurable on agent QA",
        ),
    ]


def _baseline() -> BaselineSection:
    return BaselineSection(
        metric_name="Tier-1 service deflection rate",
        baseline_value=Decimal("0.07"),
        baseline_window="2026-Q2 service center",
        baseline_data_source="Service-desk monthly aggregate",
        baseline_measurement_date=datetime(2026, 5, 15, tzinfo=UTC),
        captured_by="VP Customer Service + Head of Data",
        evidence=[_INTERVIEW_HEAD_CS],
    )


def _baseline_sme() -> BaselineSection:
    return BaselineSection(
        metric_name="SME credit decision cycle time",
        baseline_value=Decimal("3.5"),
        baseline_window="2026-Q2 SME book",
        baseline_data_source="Core lending system extract",
        baseline_measurement_date=datetime(2026, 5, 20, tzinfo=UTC),
        captured_by="VP SME + Head of Risk Modeling",
        evidence=[_INTERVIEW_CFO],
    )


def _adoption() -> AdoptionMetric:
    return AdoptionMetric(
        metric_name="Self-service container handles query end-to-end",
        target_value=">=60% of opened Tier-1 conversations close without human",
        measurement_method="Service-desk routing logs, weekly cadence",
        owner="VP Customer Service",
    )


def _pilot(baseline: BaselineSection, adoption: AdoptionMetric) -> PilotDesign:
    return PilotDesign(
        use_case_id="uc-chatbot-tier1",
        hypothesis=(
            "A retrieval-augmented chatbot deflects balance/transaction "
            "Tier-1 queries from 7% baseline to >=55% within 12 weeks."
        ),
        null_hypothesis="No statistically significant deflection lift at p<0.05",
        duration_weeks=12,
        cohort_definition=(
            "Mobile app + WhatsApp inbound channels only. Branch + call-center remain control."
        ),
        success_criteria=[
            "Deflection rate >=55% sustained weeks 8-12",
            "CSAT delta within -2 pp tolerance vs control",
            "Adoption metric >=60% by week 10",
        ],
        kill_criterion=("Week-6 deflection <30% OR CSAT delta < -5 pp vs control"),
        learning_objectives=[
            "Retrieval-vs-generative response quality tradeoff",
            "Containment vs handoff trigger thresholds",
        ],
        risks=[
            Finding(
                title="Hallucinated balance/payment data",
                body=(
                    "RAG response cites non-authoritative source — must constrain "
                    "to verified core-system reads only. Fail-closed on uncertainty."
                ),
                severity="major",
                confidence="high",
                evidence=[_INTERVIEW_CTO, _DOC_INCIDENT],
            )
        ],
        cost_estimate=Decimal("320000"),
        adoption_metric=adoption,
        baseline=[baseline],
        evidence=[_INTERVIEW_CDO, _INTERVIEW_HEAD_CS],
    )


# ----------------------------------------------------------------------------
# Public factories
# ----------------------------------------------------------------------------


def build_acme_bank_engagement() -> Engagement:
    """Construct a fully-populated, L-clean Acme Bank engagement.

    Drives all 5 stage runners. The engagement passes through:
      Stage 1 (intake) → Stage 2 (scan) → Stage 3 (ideate)
      → Stage 4 (prioritize) → Stage 5 (roadmap) → concluded.

    Returns an Engagement whose journal contains the full event sequence
    and whose state.is_concluded is True.
    """
    from stages.ideate import IdeationStage
    from stages.intake import IntakeStage
    from stages.prioritize import PrioritizationStage
    from stages.roadmap import RoadmapStage
    from stages.scan import MaturityScanStage

    tenant = acme_bank_tenant()
    eng = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))

    # Stage 1 — intake (5 interviews + 3 documents)
    intake = IntakeStage()
    intake.run(eng)
    interviews = [
        (
            "Mariana Restrepo (CDO)",
            "CDO",
            "interviews/cdo.md",
            ["12K Tier-1 tickets/mo", "65% are balance/txn queries"],
        ),
        (
            "Roberto Sánchez (CFO)",
            "CFO",
            "interviews/cfo.md",
            ["SME book $180M", "Default rate 4.7%"],
        ),
        (
            "Diego Maldonado (CTO)",
            "CTO",
            "interviews/cto.md",
            ["3 core systems", "AWS data lake since 2024"],
        ),
        (
            "Lucía Forero (Head of Customer Service)",
            "Head of Customer Service",
            "interviews/head-cs.md",
            ["65% query mix", "Avg 4-day resolution"],
        ),
        (
            "Felipe Quintero (Lead Data Engineer)",
            "Lead Data Engineer",
            "interviews/lead-de.md",
            ["Nightly ETL", "Lake landing within 6h"],
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
        eng, path="docs/org-chart.md", kind="report", summary="3 BUs, 620 FTE total"
    )
    intake.ingest_document(
        eng, path="docs/it-architecture.md", kind="report", summary="3-core legacy + AWS lake"
    )
    intake.ingest_document(
        eng, path="docs/incident-2026-q1.md", kind="report", summary="Manual reconciliation gap"
    )
    thesis = _thesis()
    intake.declare_thesis(eng, thesis)
    intake.request_review(eng, "Thesis declared, scope locked across 5 interviews")

    # Stage 2 — maturity scan (4 dimensions)
    scan = MaturityScanStage()
    scan.run(eng)
    for dim in _maturity_dimensions():
        scan.score_dimension(eng, dim)
    scan.request_review(eng, "4 dimensions scored on MIT CISR Digital framework")

    # Stage 3 — ideation (12 candidates across 5 sources — 1/12 NOVELTY ~ 8%)
    ideate = IdeationStage()
    ideate.run(eng)
    use_cases = _use_cases()
    for uc in use_cases:
        ideate.propose_use_case(eng, uc)
    ideate.request_review(eng, "12 candidates surfaced across 5 distinct sources")

    # Stage 4 — prioritization (top-5)
    prioritize = PrioritizationStage()
    prioritize.run(eng)
    top_5 = use_cases[:5]
    rice_scores = {
        "uc-chatbot-tier1": 18.2,
        "uc-sme-credit-ml": 17.4,
        "uc-fraud-ml": 12.6,
        "uc-churn-early-warn": 8.9,
        "uc-aml-automation": 7.7,
    }
    roi_cells = _roi_cells(top_5)
    for rank, (uc, roi) in enumerate(zip(top_5, roi_cells, strict=True), start=1):
        prioritize.prioritize_use_case(
            eng,
            use_case_id=uc.id,
            rice_score=rice_scores[uc.id],
            roi_cell=roi,
            rank=rank,
        )
    prioritize.render_impact_effort_matrix(eng, "/tmp/iem-acme.md")
    prioritize.request_review(eng, "Top-5 selected, RoiCells ready")

    # Stage 5 — roadmap (5 steps + 2 baselines + 1 pilot of 3 designed)
    roadmap = RoadmapStage()
    roadmap.run(eng)
    for step in _roadmap_steps():
        roadmap.propose_roadmap_step(eng, step)
    chatbot_baseline = _baseline()
    sme_baseline = _baseline_sme()
    roadmap.capture_baseline(eng, chatbot_baseline)
    roadmap.capture_baseline(eng, sme_baseline)
    pilot = _pilot(chatbot_baseline, _adoption())
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
        output_dir="/tmp/acme-bank",
    )
    roadmap.request_review(eng, "Roadmap + baselines + pilot ready")
    roadmap.conclude(
        eng,
        top_pilot="uc-chatbot-tier1",
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

    Pairs with build_acme_bank_engagement() — the engagement carries the
    journal events; this function carries the typed Pydantic objects the
    templates iterate over (since the journal stores serialized payloads,
    not Pydantic objects).
    """
    from core.orchestrator import build_roi_totals

    thesis = _thesis()
    use_cases = _use_cases()
    top_5 = use_cases[:5]
    roi_cells = _roi_cells(top_5)
    rice_scores = {
        "uc-chatbot-tier1": 18.2,
        "uc-sme-credit-ml": 17.4,
        "uc-fraud-ml": 12.6,
        "uc-churn-early-warn": 8.9,
        "uc-aml-automation": 7.7,
    }
    chatbot_baseline = _baseline()
    pilot = _pilot(chatbot_baseline, _adoption())

    return {
        "thesis": thesis,
        "dimensions": _maturity_dimensions(),
        "capabilities": _capability_cells(),
        "use_cases": use_cases,
        "frameworks_applied": [
            "mit-cisr-digital",
            "rice",
            "real-options",
            "three-horizons",
            "wsjf",
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
            for rank, (uc, roi) in enumerate(zip(top_5, roi_cells, strict=True), start=1)
        ],
        "top_n": 5,
        "roi_cells": roi_cells,
        "discount_rate": Decimal("0.16"),
        **build_roi_totals(roi_cells),
        "assumptions": [
            "Customer-base steady (±5%) over pilot duration",
            "No regulatory shift on AI usage in retail banking",
            "Cloud/vendor pricing within ±10% of forecast",
        ],
        "roadmap_steps": _roadmap_steps(),
        "pilot": pilot,
        "generated_at": "2026-06-10",
    }


def findings_for_test() -> list[Finding]:
    """Expose the synthetic-finding list for E2E tests that assert count."""
    return _findings()


__all__ = [
    "ACME_BANK_CANARY_TOKENS",
    "acme_bank_tenant",
    "build_acme_bank_engagement",
    "deliverable_extras",
    "findings_for_test",
]


# Silence the EventKind unused-import warning without burying the symbol.
_EVENT_KIND_REF = EventKind  # noqa: F841
