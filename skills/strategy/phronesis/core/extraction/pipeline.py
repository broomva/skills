"""Extraction pipeline — engagement journal → candidates → bookkeeping P8 → queue.

The end-to-end flow:

  1. `extract_industry_patterns(engagement)` + `extract_framework_refinements(engagement)`
     produce a list of `ExtractionCandidate` objects, each pre-anonymized
     via `EngagementAnonymizer`.
  2. Each candidate is wrapped as a bookkeeping `RawItem` and passed to
     `bookkeeping.score_item()` — the SAME 9-point Nous gate the rest of
     the workspace uses (no duplicate scoring math).
  3. Candidates that score ≥5/9 (`bookkeeping.PROMOTE_THRESHOLD`) land in
     the review queue at `~/.config/phronesis/extraction-queue/` as JSON
     records. They do NOT go directly to `research/entities/` — every
     candidate must clear a human review pass first (anti-pattern in the
     handoff: "don't file entities directly").
  4. Candidates that score <5 are also persisted in the queue (under
     `low-score/`) for forensic visibility — never silently dropped.

The reflexive trigger lives in `on_engagement_concluded()` — called by the
engagement model whenever an `ENGAGEMENT_CONCLUDED` event is emitted. This
makes the flow Pillar-1 (recursive self-improvement) automatic: every
completed engagement contributes to the knowledge graph without manual
invocation.

Test isolation: the queue + entity-graph paths read from env vars
`PHRONESIS_EXTRACTION_QUEUE_ROOT` and `PHRONESIS_ENTITY_GRAPH_ROOT`, both
defaulting to the operator's home. Tests set them to `tmp_path` so the
suite never touches the real knowledge graph.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.anonymize import AnonymizationPolicy
from core.engagement import Engagement
from core.extraction.anonymizer import (
    EngagementAnonymizer,
    _collect_engagement_redact_terms,
)
from core.extraction.candidates import (
    ExtractionCandidate,
    extract_framework_refinements,
    extract_industry_patterns,
)

# ----------------------------------------------------------------------------
# Configuration — sandboxable via env vars for test isolation.
# ----------------------------------------------------------------------------


def _resolve_queue_root() -> Path:
    """Resolve the review-queue root.

    Override via PHRONESIS_EXTRACTION_QUEUE_ROOT. Defaults to
    `~/.config/phronesis/extraction-queue/`.
    """
    env = os.environ.get("PHRONESIS_EXTRACTION_QUEUE_ROOT")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config" / "phronesis" / "extraction-queue"


def _resolve_entity_graph_root() -> Path:
    """Resolve the entity graph root.

    Override via PHRONESIS_ENTITY_GRAPH_ROOT. Defaults to
    `~/broomva/research/entities/` — the workspace knowledge graph.
    """
    env = os.environ.get("PHRONESIS_ENTITY_GRAPH_ROOT")
    if env:
        return Path(env).expanduser()
    return Path.home() / "broomva" / "research" / "entities"


# Module-level constants for backward compatibility. Tests should call the
# resolver functions directly when they need fresh env-var reads.
EXTRACTION_QUEUE_ROOT = _resolve_queue_root()
ENTITY_GRAPH_ROOT = _resolve_entity_graph_root()


# ----------------------------------------------------------------------------
# Bookkeeping interop — optional import, deterministic fallback.
# ----------------------------------------------------------------------------


def _bookkeeping_module() -> Any | None:
    """Try to import the bookkeeping module.

    Returns `None` if the module isn't installed (test environments,
    minimal CI runners). When None, `_score_candidate()` falls back to a
    deterministic stub heuristic.

    The old comment here said the stub was "never used in production". It was
    the ONLY path ever taken: this resolved `~/broomva/skills/bookkeeping/
    scripts`, which does not exist — the bookkeeping skill lives under
    `skills/knowledge/`. Every entity phronesis has ever published therefore
    carries `method: stub-deterministic` and a score that is a function of the
    candidate's TYPE rather than its content. Probe both layouts, and prefer
    an explicit override so a relocation degrades loudly instead of silently
    re-arming the stub.
    """
    candidates: list[Path] = []
    override = os.environ.get("PHRONESIS_BOOKKEEPING_PATH")
    if override:
        candidates.append(Path(override).expanduser())

    # Repo-relative FIRST. bookkeeping is a sibling skill in this same
    # repository, so resolving from __file__ works in a CI checkout, in a
    # worktree, and under any clone path — none of which `Path.home()` does.
    # Resolving via home is what made the original path dead on every machine
    # whose checkout is not exactly ~/broomva/skills.
    #   .../skills/strategy/phronesis/core/extraction/pipeline.py
    #   parents[4] == .../skills   (the dir holding strategy/ and knowledge/)
    here = Path(__file__).resolve()
    if len(here.parents) > 4:
        candidates.append(here.parents[4] / "knowledge" / "bookkeeping" / "scripts")

    # Installed-skill layouts, for a phronesis vendored outside the monorepo.
    home = Path.home() / "broomva" / "skills"
    candidates.append(home / "skills" / "knowledge" / "bookkeeping" / "scripts")
    candidates.append(home / "bookkeeping" / "scripts")
    candidates.append(Path.home() / ".claude" / "skills" / "bookkeeping" / "scripts")

    bookkeeping_path = next((c for c in candidates if c.exists()), None)
    if bookkeeping_path is None:
        return None
    if str(bookkeeping_path) not in sys.path:
        sys.path.insert(0, str(bookkeeping_path))
    try:
        import bookkeeping  # type: ignore[import-not-found]

        return bookkeeping
    except ImportError:
        return None


class _CandidateScore(BaseModel):
    """Score record attached to a candidate before queue persistence."""

    total: int
    novelty: int
    specificity: int
    relevance: int
    promote: bool
    scoring_method: str
    reasoning: dict[str, Any] = Field(default_factory=dict)


def _stub_score(candidate: ExtractionCandidate) -> _CandidateScore:
    """Deterministic fallback scorer for environments without bookkeeping.

    Conservative — promotes when the candidate has rich signals (≥3 signal
    keys) AND non-empty quote AND content > 200 chars. Otherwise low score.

    Intentionally simple — the real bookkeeping P8 path is the source of
    truth in production. This stub keeps the pipeline + tests independent
    of LLM availability.
    """
    novelty = 2 if candidate.entity_type == "framework-refinement" else 1
    specificity = 2 if candidate.signals else 1
    relevance = 2 if candidate.industry or candidate.framework_ref else 1
    total = novelty + specificity + relevance
    if len(candidate.content) > 200 and candidate.quote:
        total += 1
    if len(candidate.signals) >= 3:
        total += 1

    return _CandidateScore(
        total=total,
        novelty=novelty,
        specificity=specificity,
        relevance=relevance,
        promote=total >= 5,
        scoring_method="stub-deterministic",
        reasoning={
            "rule": "stub-fallback when bookkeeping module unavailable",
        },
    )


def _score_candidate(candidate: ExtractionCandidate) -> _CandidateScore:
    """Score an extraction candidate via bookkeeping P8 (Nous gate).

    Tries the real bookkeeping module first; falls back to the
    deterministic stub if bookkeeping isn't importable. Honors the
    PHRONESIS_EXTRACTION_STUB_SCORER env var (set to "1" by tests to
    force the deterministic path).
    """
    if os.environ.get("PHRONESIS_EXTRACTION_STUB_SCORER") == "1":
        return _stub_score(candidate)

    bk = _bookkeeping_module()
    if bk is None:
        return _stub_score(candidate)

    timestamp = datetime.now(UTC).isoformat()
    raw_item = bk.RawItem(
        item_id=f"phronesis-{candidate.slug}-{timestamp}",
        source_id=f"phronesis-extraction:{candidate.slug}",
        source_type="phronesis-engagement",
        content=candidate.content,
        quote=candidate.quote,
        author="phronesis-extraction-pipeline",
        timestamp=timestamp,
        metadata={
            "entity_type": candidate.entity_type,
            "industry": candidate.industry,
            "framework_ref": candidate.framework_ref,
            "signals": candidate.signals,
            "provenance_event_ids": candidate.provenance_event_ids,
        },
    )

    try:
        existing_slugs = bk.existing_entity_slugs()
    except Exception:
        existing_slugs = []

    try:
        scored = bk.score_item(raw_item, existing_slugs)
    except Exception:
        # Network / API failure → stub fallback. Never block on transient
        # LLM failure; the candidate still lands in the review queue.
        return _stub_score(candidate)

    return _CandidateScore(
        total=int(scored.total),
        novelty=int(scored.novelty),
        specificity=int(scored.specificity),
        relevance=int(scored.relevance),
        promote=bool(scored.promote),
        scoring_method=str(scored.scoring_method),
        reasoning=dict(scored.reasoning) if isinstance(scored.reasoning, dict) else {},
    )


# ----------------------------------------------------------------------------
# Pipeline result
# ----------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """Result of an extraction pipeline run."""

    engagement_slug: str
    industry_pattern_candidates: int = 0
    framework_refinement_candidates: int = 0
    promoted_count: int = 0
    queued_count: int = 0
    queue_paths: list[Path] = Field(default_factory=list)
    promotion_paths: list[Path] = Field(default_factory=list)
    leaks: list[tuple[str, list[str]]] = Field(default_factory=list)
    # Entity pages that already existed and were therefore NOT overwritten.
    # Surfaced rather than silent so a run that changes nothing is legible.
    skipped_existing: list[Path] = Field(default_factory=list)
    # Candidates whose body yielded no self-contained claim within the cap.
    # They stay in the queue; minting a page with a truncated claim is the
    # defect BRO-1983 removed.
    unpromotable: list[str] = Field(default_factory=list)

    @property
    def total_candidates(self) -> int:
        return self.industry_pattern_candidates + self.framework_refinement_candidates


# ----------------------------------------------------------------------------
# Public entry points
# ----------------------------------------------------------------------------


def extract_and_queue(
    engagement: Engagement,
    *,
    queue_root: Path | None = None,
    entity_graph_root: Path | None = None,
    policy: AnonymizationPolicy | None = None,
    extra_redact_terms: Iterable[str] = (),
) -> ExtractionResult:
    """Run the extraction pipeline against `engagement`.

    Args:
        engagement: a concluded engagement (state.is_concluded == True).
            Non-concluded engagements still extract but the result is
            best-effort; calling code should gate on `is_concluded` if it
            cares.
        queue_root: review-queue directory; defaults to env-resolved.
        entity_graph_root: where promoted entities land; defaults to env-resolved.
        policy: anonymization policy; defaults to strict.
        extra_redact_terms: caller-supplied redact terms (project codenames
            the journal can't surface automatically).

    Returns:
        `ExtractionResult` summarizing what was queued + promoted + leaked.

    Side effects:
        Writes JSON queue records to `<queue_root>/<engagement_slug>/`.
        Writes promoted candidate stubs to
        `<entity_graph_root>/<entity_type>/<slug>.md` IF the bookkeeping
        score is ≥5 AND no canary leaks are detected post-redaction.
        The promoted file is a STUB — operator polishes before
        publishing. We never short-circuit the human review pass.
    """
    queue_root = queue_root or _resolve_queue_root()
    entity_graph_root = entity_graph_root or _resolve_entity_graph_root()
    policy = policy or AnonymizationPolicy()

    journal_terms = _collect_engagement_redact_terms(engagement)
    combined_terms = list(
        dict.fromkeys([*policy.redact_terms, *journal_terms, *extra_redact_terms])
    )
    effective_policy = policy.model_copy(update={"redact_terms": combined_terms})

    anonymizer = EngagementAnonymizer(tenant=engagement.tenant, policy=effective_policy)

    industry_candidates = extract_industry_patterns(engagement, anonymizer)
    framework_candidates = extract_framework_refinements(engagement, anonymizer)
    all_candidates = [*industry_candidates, *framework_candidates]

    result = ExtractionResult(
        engagement_slug=engagement.tenant.tenant_slug,
        industry_pattern_candidates=len(industry_candidates),
        framework_refinement_candidates=len(framework_candidates),
    )

    queue_dir = queue_root / engagement.tenant.tenant_slug
    queue_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    for candidate in all_candidates:
        # Defense-in-depth: re-check for tenant markers AFTER candidate
        # construction (in case a custom anonymizer wrapper was passed and
        # didn't strip something). Never queue a candidate that carries a
        # tenant marker — the canary release gate would catch it later
        # but we'd rather fail fast.
        # candidate.slug is checked because it becomes the entity FILENAME and
        # therefore a catalog-indexed field — the same surface as the
        # `phronesis:{tenant_slug}` source ref this change removes. Gating
        # content and quote while letting the slug through moves the leak
        # rather than closing it: redacted body, tenant name in the path.
        leaked = (
            anonymizer.carries_marker(candidate.content)
            + anonymizer.carries_marker(candidate.quote)
            + anonymizer.carries_marker(candidate.slug)
        )
        if leaked:
            result.leaks.append((candidate.slug, leaked))
            continue

        score = _score_candidate(candidate)
        promoted = score.promote

        record = {
            "candidate": candidate.model_dump(mode="json"),
            "score": score.model_dump(mode="json"),
            "engagement_slug": engagement.tenant.tenant_slug,
            "promoted_at": datetime.now(UTC).isoformat(),
        }

        sub_dir = "promoted" if promoted else "low-score"
        out_dir = queue_dir / sub_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{candidate.slug}-{timestamp}.json"
        out_path.write_text(json.dumps(record, indent=2, sort_keys=False, default=str))
        result.queue_paths.append(out_path)

        if promoted:
            entity_dir = entity_graph_root / candidate.entity_type
            entity_path = entity_dir / f"{candidate.slug}.md"

            # Two refusals, both of which this writer used to ignore.
            #
            # (1) An unpromotable claim. `derive_core_claim` returns None when
            #     it cannot produce a self-contained claim within the cap. The
            #     old code truncated instead, minting a page the linter rejects.
            #     Skipping is the documented behaviour (BRO-1983).
            #
            # (2) An entity that already exists. This module's own docstring
            #     says candidates "do NOT go directly to research/entities/ --
            #     every candidate must clear a human review pass first", yet
            #     line 338 was an unconditional write_text. It clobbered
            #     operator-polished pages: observed overwriting a core_claim
            #     authored by repair commit a1242b227. The queue record is
            #     still written either way, so nothing is lost -- the operator
            #     reconciles from `~/.config/phronesis/extraction-queue/`.
            core_claim = _derive_core_claim(candidate)
            if core_claim is None:
                result.unpromotable.append(candidate.slug)
                result.queued_count += 1
                continue
            rendered = _render_entity_stub(candidate, score, engagement, core_claim)
            # Atomic create. `exists()` then `write_text()` is a TOCTOU gap:
            # two concurrent extractions producing the same slug can both see
            # absence and the later clobbers the earlier. The skill is
            # symlinked live, so concurrent extraction is the normal case.
            # "x" fails closed on an existing file, which IS the refusal.
            entity_dir.mkdir(parents=True, exist_ok=True)
            try:
                with open(entity_path, "x", encoding="utf-8") as fh:
                    fh.write(rendered)
            except FileExistsError:
                result.skipped_existing.append(entity_path)
                continue
            # Counted only after the write succeeds, so the tally cannot claim
            # a page that was never written.
            result.promoted_count += 1
            result.promotion_paths.append(entity_path)
        else:
            result.queued_count += 1

    return result


def on_engagement_concluded(
    engagement: Engagement,
    *,
    enabled: bool | None = None,
    **kwargs: Any,
) -> ExtractionResult | None:
    """Reflexive hook — called when `ENGAGEMENT_CONCLUDED` fires.

    Per `feedback_bookkeeping_reflexive.md`: bookkeeping is reflexive,
    not opt-in. This hook runs without being asked.

    Set `PHRONESIS_EXTRACTION_ENABLED=0` to disable (e.g. during
    interactive debugging of a non-concluded fixture). Default: enabled.

    Returns the `ExtractionResult`, or `None` if disabled.
    """
    if enabled is None:
        enabled = os.environ.get("PHRONESIS_EXTRACTION_ENABLED", "1") != "0"
    if not enabled:
        return None
    if not engagement.state().is_concluded:
        # Best-effort idempotency: only fire on truly-concluded engagements.
        return None
    return extract_and_queue(engagement, **kwargs)


# ----------------------------------------------------------------------------
# Entity page stub renderer
# ----------------------------------------------------------------------------


def _yaml_scalar(value: Any) -> str:
    """Serialize a scalar as an explicitly-quoted YAML string.

    `json.dumps` with `ensure_ascii=True` gives correct escaping for free.

    The flag is load-bearing, not cosmetic. JSON is NOT a subset of YAML's
    double-quoted style for C0/C1 controls: with `ensure_ascii=False`,
    U+007F and U+0080-U+009F are emitted raw, PyYAML's reader rejects them
    outright ("unacceptable character #x007f"), and U+0085 (NEL) parses but
    silently folds to a space. Escaping them as backslash-uXXXX is valid in a
    YAML double-quoted scalar and round-trips exactly.

    This is not cosmetic. Interpolating a value bare leaves it a YAML *plain*
    scalar, and a plain scalar cannot contain ": ". A framework-refinement
    title like `RICE: business-pain weighting in construction` therefore
    rendered as unparseable frontmatter — `yaml.safe_load` raises
    `ScannerError: mapping values are not allowed here` — and every one of
    the seven `rice-*` entities this writer produced was unreadable by the
    knowledge graph until repaired by hand.
    """
    return json.dumps("" if value is None else str(value))


def _derive_core_claim(candidate: ExtractionCandidate) -> str | None:
    """Delegate to bookkeeping's canonical deriver; None means DO NOT PROMOTE.

    This used to be a hand-rolled `sentence[:139] + "…"`. That is precisely
    the producer BRO-1983 removed from bookkeeping itself, whose comment reads:
    "The original producer was `raw_claim[:137] + '...'` — a hard mid-word
    truncation sized precisely to clear the linter's `len(core_claim) <= 140`
    rule. A quality gate the producer satisfies BY CONSTRUCTION is not a gate
    ... A `...` suffix is never emitted, at any step." The linter enforces it:
    `_JUNK_CLAIM_PATTERNS` treats a trailing ellipsis as an ERROR. Re-deriving
    from the 20 bodies already on disk, the truncating version produced a
    lint-erroring claim for 3 of them.

    So there is exactly one implementation, and it lives in bookkeeping.
    `derive_core_claim` returns None when it cannot produce a self-contained
    claim within the cap; that is a promotion-blocking signal, not an
    invitation to truncate. The caller must skip the candidate rather than
    mint a page.
    """
    bk = _bookkeeping_module()
    if bk is None or not hasattr(bk, "derive_core_claim"):
        return None
    body = candidate.content or candidate.title or ""
    try:
        return bk.derive_core_claim(body)
    except Exception:
        return None


def _render_entity_stub(
    candidate: ExtractionCandidate,
    score: _CandidateScore,
    engagement: Engagement,
    core_claim: str,
) -> str:
    """Render a minimal entity-page stub for a promoted candidate.

    Format mirrors `~/broomva/skills/bookkeeping/templates/entity-page.md`
    minimally. The output carries no `bookkeeping lint` ERRORs — parseable
    frontmatter, a `core_claim` within the length cap, and a non-empty
    `sources` list. It still emits lint WARNINGS (notably no `tags`, which
    must come from the controlled vocabulary in `research/entities/_tags.md`
    and cannot be guessed from an extraction). Operator polishes before the
    entity surfaces in queries.

    Every interpolated scalar goes through `_yaml_scalar`; see its docstring
    for the failure this prevents.

    Stays in YAML frontmatter + plain markdown body. Per the workspace
    Format Discernment rule, entity pages are Category A (substrate),
    so this is markdown-only — never HTML.
    """
    industry_or_framework = (
        f"  industry: {_yaml_scalar(candidate.industry)}"
        if candidate.industry
        else f"  framework_ref: {_yaml_scalar(candidate.framework_ref)}"
    )
    signals_lines = "\n".join(
        f"  - {_yaml_scalar(k)}: {_yaml_scalar(v) if isinstance(v, str) else v}"
        for k, v in candidate.signals.items()
    )
    tenant_slug = engagement.tenant.tenant_slug
    # `sources` must be a non-empty list or lint errors. Name the extraction's
    # own provenance events rather than inventing a document slug that resolves
    # to nothing.
    #
    # The tenant slug is deliberately NOT in here. `sources` is one of the
    # fields `bookkeeping index` renders into docs/knowledge-index.md and that
    # `/kg` scores retrieval on, so putting the slug here moves it from a
    # frontmatter subtree no consumer reads into the workspace-wide index --
    # a new exposure against `AnonymizationPolicy.strip_tenant_slug = True`.
    # `provenance.engagement_slug` already carries it for forensic lookup.
    source_lines = "\n".join(
        f"  - {_yaml_scalar(f'phronesis:{eid}')}"
        for eid in candidate.provenance_event_ids
    ) or f"  - {_yaml_scalar('phronesis:unattributed')}"
    body = candidate.content

    return f"""---
type: {_yaml_scalar(candidate.entity_type)}
title: {_yaml_scalar(candidate.title)}
core_claim: {_yaml_scalar(core_claim)}
status: candidate
sources:
{source_lines}
provenance:
  source: phronesis-extraction
  engagement_slug: {_yaml_scalar(tenant_slug)}
  event_ids:
{chr(10).join(f"    - {_yaml_scalar(eid)}" for eid in candidate.provenance_event_ids)}
score:
  total: {score.total}/9
  novelty: {score.novelty}
  specificity: {score.specificity}
  relevance: {score.relevance}
  method: {_yaml_scalar(score.scoring_method)}
{industry_or_framework}
signals:
{signals_lines}
created_at: {_yaml_scalar(datetime.now(UTC).isoformat())}
---

# {candidate.title}

## Pattern (anonymized)

{body}

## Source quote

> {candidate.quote}

## Promotion gate

- Bookkeeping P8 score: {score.total}/9 ({score.scoring_method})
- Rule-of-three: this is one instance. Surface ≥2 more same-industry /
  same-framework engagements reproducing the pattern before treating as
  a stable graph node.
- Operator action: polish the body, verify the signals, confirm the
  anonymization holds, then promote `status` from `candidate` to `active`.
"""


__all__ = [
    "EXTRACTION_QUEUE_ROOT",
    "ENTITY_GRAPH_ROOT",
    "ExtractionResult",
    "extract_and_queue",
    "on_engagement_concluded",
]
