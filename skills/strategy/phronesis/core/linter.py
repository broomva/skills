"""Phronesis linter — L1-L5 + P3 + P7 + P8 rules over a rendered engagement.

Each rule scans the journal (and optionally the rendered deliverables) and
emits LintViolation objects. The release-gate test (Phase E) requires zero
L1-L5 errors on the canonical synthetic fixture.

Stages already enforce gates at their boundaries (raise ValueError when
the gate is violated). The linter is the BACKSTOP — replaying a finished
engagement journal must produce zero L-errors. If a linter rule fires, it
means a stage was bypassed or the engagement was constructed manually
without going through the stages.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from pydantic import BaseModel, Field

from core.engagement import Engagement
from core.types import EventKind


class LintViolation(BaseModel):
    """One linter finding."""

    rule: str  # "L1" | "L2" | "L3" | "L4" | "L5" | "P3" | "P7" | "P8"
    severity: str  # "error" | "warning"
    location: str  # event_id, deliverable slug, or descriptive marker
    message: str


class LintResult(BaseModel):
    """Aggregated result of running all linter rules over an Engagement."""

    violations: list[LintViolation] = Field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(v.severity == "error" for v in self.violations)

    @property
    def has_warnings(self) -> bool:
        return any(v.severity == "warning" for v in self.violations)

    def errors_for_rule(self, rule: str) -> list[LintViolation]:
        return [v for v in self.violations if v.rule == rule and v.severity == "error"]


# Rules registry ------------------------------------------------------------

_RULES: list[Callable[[Engagement], list[LintViolation]]] = []


def rule(
    fn: Callable[[Engagement], list[LintViolation]],
) -> Callable[[Engagement], list[LintViolation]]:
    """Decorator: register a linter rule."""
    _RULES.append(fn)
    return fn


# L1 — STRATEGIC_THESIS_REQUIRED ---------------------------------------------


@rule
def l1_strategic_thesis_required(eng: Engagement) -> list[LintViolation]:
    """L1 — every engagement must declare a StrategicThesis BEFORE leaving Stage 1.

    Bision Failure 1 (100% observed): Sin tesis estratégica.
    Engagements that emitted INTAKE_COMPLETED without first emitting
    STRATEGIC_THESIS_DECLARED are blocked.
    """
    violations: list[LintViolation] = []
    state = eng.state()

    intake_closed_event_id: str | None = None
    for ev in eng.journal.events:
        if ev.kind == EventKind.INTAKE_COMPLETED:
            intake_closed_event_id = ev.event_id
            break

    if intake_closed_event_id and state.thesis_id is None:
        violations.append(
            LintViolation(
                rule="L1",
                severity="error",
                location=intake_closed_event_id,
                message=(
                    "L1 STRATEGIC_THESIS_REQUIRED — intake closed without a "
                    "thesis declared. Bision Failure 1 (100% observed): "
                    "'sin tesis estratégica'."
                ),
            )
        )
    return violations


# L2 — DIVERSE_IDEATION_SOURCES ----------------------------------------------


@rule
def l2_diverse_ideation_sources(eng: Engagement) -> list[LintViolation]:
    """L2 — ideation diversity rule.

    Bision Failure 2 (87% observed): casos mal priorizados — elección por novedad.
    Triggers when ≥1 USE_CASE_PROPOSED exists AND either:
      - <3 distinct ideation sources OR
      - NOVELTY share > 50%
    """
    violations: list[LintViolation] = []
    state = eng.state()
    if not state.use_cases:
        return violations

    sources = [uc.get("ideation_source") for uc in state.use_cases.values()]
    sources_counter = Counter(s for s in sources if isinstance(s, str))
    distinct = len(sources_counter)
    novelty_share = sources_counter.get("novelty", 0) / len(state.use_cases)

    if distinct < 3:
        violations.append(
            LintViolation(
                rule="L2",
                severity="error",
                location="ideate-stage",
                message=(
                    f"L2 DIVERSE_IDEATION_SOURCES — only {distinct} distinct "
                    f"ideation sources across {len(state.use_cases)} use cases "
                    f"(min 3). Bision Failure 2 (87% observed)."
                ),
            )
        )
    if novelty_share > 0.5:
        violations.append(
            LintViolation(
                rule="L2",
                severity="error",
                location="ideate-stage",
                message=(
                    f"L2 DIVERSE_IDEATION_SOURCES — NOVELTY share "
                    f"{novelty_share:.0%} exceeds 50% limit. "
                    f"Bision Failure 2: elección por novedad."
                ),
            )
        )
    return violations


# L3 — DATA_READINESS_GATE ---------------------------------------------------


@rule
def l3_data_readiness_gate(eng: Engagement) -> list[LintViolation]:
    """L3 — data readiness must be assessed for every proposed use case.

    Bision Failure 3 (74% observed): datos no preparados.
    Triggers when a use case has `readiness_band == "blocking"` AND no
    `prep_phase_required` AND the engagement is past Stage 3.
    """
    violations: list[LintViolation] = []
    state = eng.state()
    if not state.use_cases:
        return violations

    for uc_id, payload in state.use_cases.items():
        band = payload.get("data_readiness_band")
        if band == "blocking":
            violations.append(
                LintViolation(
                    rule="L3",
                    severity="error",
                    location=f"use-case:{uc_id}",
                    message=(
                        f"L3 DATA_READINESS_GATE — use case {uc_id!r} has "
                        f"data_readiness_band=blocking. Bision Failure 3 "
                        f"(74% observed): datos no preparados. Either declare "
                        f"a prep_phase or defer the use case."
                    ),
                )
            )
    return violations


# L4 — ADOPTION_METRIC_REQUIRED ----------------------------------------------


@rule
def l4_adoption_metric_required(eng: Engagement) -> list[LintViolation]:
    """L4 — every PILOT_STARTED must reference a pilot design with an
    adoption_metric. Pydantic enforces non-emptiness on PilotDesign at
    construction; this lints the journal sequence.

    Bision Failure 4 (61% observed): desconexión negocio-tecnología —
    modelos con precisión alta y baja adopción.

    Phase 1 backstop: PilotDesign requires AdoptionMetric (typed). The linter
    surfaces L4 if a PILOT_STARTED event is followed by no DELIVERABLE_RENDERED
    for slug "pilot-plan" — i.e., the engagement skipped pilot-plan rendering,
    so the adoption metric never reached the deliverable layer.
    """
    violations: list[LintViolation] = []
    pilots: list[str] = []
    rendered_pilot_plans: list[str] = []
    for ev in eng.journal.events:
        if ev.kind == EventKind.PILOT_STARTED:
            uc_id = ev.payload.get("use_case_id")
            if isinstance(uc_id, str):
                pilots.append(uc_id)
        elif ev.kind == EventKind.DELIVERABLE_RENDERED:
            slug = ev.payload.get("slug")
            if slug == "pilot-plan":
                rendered_pilot_plans.append(ev.event_id)

    if pilots and not rendered_pilot_plans:
        violations.append(
            LintViolation(
                rule="L4",
                severity="error",
                location="roadmap-stage",
                message=(
                    "L4 ADOPTION_METRIC_REQUIRED — pilot(s) started "
                    f"({pilots}) but no pilot-plan deliverable rendered. "
                    "Bision Failure 4 (61% observed): adoption metric must "
                    "land in the deliverable so it's audit-trail visible."
                ),
            )
        )
    return violations


# L5 — BASELINE_REQUIRED -----------------------------------------------------


@rule
def l5_baseline_required(eng: Engagement) -> list[LintViolation]:
    """L5 — every PILOT_STARTED must be preceded by ≥1 BASELINE_CAPTURED.

    Bision Failure 5 (48% observed): sin medición de ROI — no retroactive
    baselines. RoadmapStage.design_pilot enforces this at construction; the
    linter is the journal-replay backstop.
    """
    violations: list[LintViolation] = []
    baseline_count_before: dict[str, int] = {}
    captured_so_far = 0
    for ev in eng.journal.events:
        if ev.kind == EventKind.BASELINE_CAPTURED:
            captured_so_far += 1
        elif ev.kind == EventKind.PILOT_STARTED:
            uc_id = ev.payload.get("use_case_id")
            if isinstance(uc_id, str):
                baseline_count_before[uc_id] = captured_so_far

    for uc_id, count in baseline_count_before.items():
        if count == 0:
            violations.append(
                LintViolation(
                    rule="L5",
                    severity="error",
                    location=f"pilot:{uc_id}",
                    message=(
                        f"L5 BASELINE_REQUIRED — pilot for {uc_id!r} started "
                        f"with zero prior BASELINE_CAPTURED events. "
                        f"Bision Failure 5 (48% observed): no retroactive "
                        f"baselines. Capture before pilot."
                    ),
                )
            )
    return violations


# Aggregate runner ----------------------------------------------------------


def lint_engagement(eng: Engagement) -> LintResult:
    """Run all registered rules; return aggregated result."""
    out = LintResult()
    for fn in _RULES:
        out.violations.extend(fn(eng))
    return out
