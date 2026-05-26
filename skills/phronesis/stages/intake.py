"""Stage 1 — Intake.

Establishes scope, captures interviews/documents, declares the StrategicThesis
(L1 enforcement). Cannot exit without a thesis in the journal.

Reviewed by sponsor before transition to Stage 2 (Maturity Scan).
"""

from __future__ import annotations

from typing import ClassVar

from core.engagement import Engagement
from core.types import EventKind, StrategicThesis
from stages.base import StageBase


class IntakeStage(StageBase):
    """Stage 1 — Intake: scope + interviews + thesis declaration."""

    SLUG: ClassVar[str] = "intake"
    NEXT_STAGE: ClassVar[str] = "scan"

    def run(self, engagement: Engagement, **inputs: object) -> None:
        """Initialize intake — emit ENGAGEMENT_STARTED."""
        engagement.emit(
            EventKind.ENGAGEMENT_STARTED,
            "intake",
            {
                "tenant_slug": engagement.tenant.tenant_slug,
                "scope": engagement.tenant.engagement_scope,
                "sponsor": engagement.tenant.sponsor,
                "target_duration_weeks": engagement.tenant.target_duration_weeks,
            },
        )

    def log_interview(
        self,
        engagement: Engagement,
        *,
        interviewee: str,
        role: str,
        transcript_ref: str,
        key_findings: list[str],
    ) -> str:
        """Emit INTERVIEW_LOGGED. Returns the event_id."""
        return engagement.emit(
            EventKind.INTERVIEW_LOGGED,
            "intake",
            {
                "interviewee": interviewee,
                "role": role,
                "transcript_ref": transcript_ref,
                "key_findings": key_findings,
            },
        )

    def ingest_document(
        self,
        engagement: Engagement,
        *,
        path: str,
        kind: str,
        summary: str,
    ) -> str:
        """Emit DOCUMENT_INGESTED. `kind` must be one of
        interview/data/regulatory/report (validated by the typed payload)."""
        return engagement.emit(
            EventKind.DOCUMENT_INGESTED,
            "intake",
            {"path": path, "kind": kind, "summary": summary},
        )

    def declare_thesis(self, engagement: Engagement, thesis: StrategicThesis) -> str:
        """Emit STRATEGIC_THESIS_DECLARED. L1 milestone — gates the rest of the stage.

        Returns the event_id; caller may store this for journal reference.
        """
        return engagement.emit(
            EventKind.STRATEGIC_THESIS_DECLARED,
            "intake",
            {
                "thesis_id": thesis.thesis_id,
                "economic_lever": thesis.economic_lever,
                "lever_kind": thesis.lever_kind,
                "magnitude_estimate": str(thesis.magnitude_estimate),
                "horizon": thesis.strategic_horizon,
                "owner": thesis.decision_rights_owner,
            },
        )

    def request_review(self, engagement: Engagement, summary: str) -> None:
        """Emit STAGE_REVIEW_REQUESTED + INTAKE_COMPLETED.

        L1 GATE: cannot exit intake without a StrategicThesis. Bision Failure 1
        (100% observed) — 'hagamos algo de IA' is rejected. Caller must invoke
        declare_thesis() before request_review().
        """
        state = engagement.state()
        if state.thesis_id is None:
            raise ValueError(
                "L1 STRATEGIC_THESIS_REQUIRED — cannot exit intake without "
                "calling declare_thesis() first. Bision Failure 1 (100% "
                "observed): 'sin tesis estratégica'."
            )

        engagement.emit(
            EventKind.STAGE_REVIEW_REQUESTED,
            "intake",
            {
                "stage": "intake",
                "reviewer": engagement.tenant.sponsor,
                "summary": summary,
                "artifacts": [
                    "intake/strategic-thesis.md",
                    "intake/stakeholder-map.md",
                ],
                "deadline": None,
            },
        )
        engagement.emit(
            EventKind.INTAKE_COMPLETED,
            "intake",
            {
                "thesis_id": state.thesis_id,
                "frameworks_selected": state.frameworks_active,
            },
        )
