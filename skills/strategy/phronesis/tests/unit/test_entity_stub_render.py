"""The entity stub renderer must emit frontmatter the knowledge graph can read.

Regression cover for BRO-2404. `_render_entity_stub` interpolated every scalar
bare, so any value containing ": " produced a YAML *plain* scalar that cannot
hold a colon. The seven `rice-*` framework-refinement entities all carry titles
of the form `RICE: business-pain weighting in construction`, and every one of
them reached `research/entities/` as unparseable frontmatter — invisible to the
catalog, unreadable by lint, repaired only by hand.

The renderer's docstring claimed the output was "just enough for the file to be
lint-clean". Nothing checked that claim, which is why it stayed false: the stub
also omitted `core_claim` and `sources`, both hard lint ERRORs.

These tests check the claim rather than restating it.
"""

from __future__ import annotations

import pytest
import yaml

from core.extraction.candidates import ExtractionCandidate
from core.extraction.pipeline import (
    _CORE_CLAIM_MAX,
    _CandidateScore,
    _derive_core_claim,
    _render_entity_stub,
    _yaml_scalar,
)

pytestmark = pytest.mark.unit


class _Tenant:
    tenant_slug = "nova-construction"


class _Engagement:
    tenant = _Tenant()


def _candidate(**over) -> ExtractionCandidate:
    kwargs = dict(
        slug="rice-business-pain-weight-construction",
        entity_type="framework-refinement",
        content=(
            "Framework refinement candidate: in this construction engagement, 3 of 8 "
            "use cases originated from ideation source 'business-pain'. RICE assumes "
            "uniform-priority sourcing; over-represented sources may need explicit "
            "weighting in same-industry calibrations."
        ),
        quote="3/8 use cases from 'business-pain'",
        title="RICE: business-pain weighting in construction",
        provenance_event_ids=["01M0V1W6VGVMBJ5W99EWKYN29H"],
        industry=None,
        framework_ref="framework:rice",
        signals={"ideation_source": "business-pain", "share": 0.375},
    )
    kwargs.update(over)
    return ExtractionCandidate(**kwargs)


def _score() -> _CandidateScore:
    return _CandidateScore(
        total=6, novelty=3, specificity=3, relevance=0,
        promote=True, scoring_method="heuristic",
    )


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---", 2)[1])


class TestEntityStubFrontmatter:
    def test_colon_bearing_title_still_parses(self):
        """The exact shape that broke all seven rice-* entities."""
        fm = _frontmatter(_render_entity_stub(_candidate(), _score(), _Engagement()))
        assert fm["title"] == "RICE: business-pain weighting in construction"

    # NOTE: `framework_ref` / `industry` are emitted with a two-space indent, so
    # they land nested under `score:` rather than at the top level. That is
    # pre-existing and every entity already on main carries the same shape
    # (`score.framework_ref`), so these tests pin the placement as-is rather than
    # silently re-shaping published entities. The misplacement is real — a
    # consumer reading `entity.framework_ref` gets nothing — but moving it is a
    # schema migration, not a quoting fix.
    def test_colon_in_framework_ref_parses(self):
        fm = _frontmatter(_render_entity_stub(_candidate(), _score(), _Engagement()))
        assert fm["score"]["framework_ref"] == "framework:rice"

    def test_colon_in_industry_parses(self):
        cand = _candidate(industry="banking: mid-market", framework_ref=None)
        fm = _frontmatter(_render_entity_stub(cand, _score(), _Engagement()))
        assert fm["score"]["industry"] == "banking: mid-market"

    def test_framework_ref_placement_matches_entities_already_on_main(self):
        """Guard the migration: if this ever moves, published entities must move too."""
        fm = _frontmatter(_render_entity_stub(_candidate(), _score(), _Engagement()))
        assert "framework_ref" not in fm, "top-level placement is a schema migration"
        assert "framework_ref" in fm["score"]

    def test_colon_in_signal_value_parses(self):
        cand = _candidate(signals={"note": "ratio: three of eight"})
        fm = _frontmatter(_render_entity_stub(cand, _score(), _Engagement()))
        assert {"note": "ratio: three of eight"} in fm["signals"]

    @pytest.mark.parametrize(
        "hostile",
        [
            'quote "inside" the title',
            "trailing colon:",
            "hash # not a comment",
            "line\nbreak",
            "backslash \\ and tab \t",
            "{brace} [bracket] *star* &amp !bang",
            "unicode — em dash · middot",
        ],
    )
    def test_hostile_titles_round_trip(self, hostile):
        """A quoting fix is only real if it survives more than the one case."""
        fm = _frontmatter(_render_entity_stub(_candidate(title=hostile), _score(), _Engagement()))
        assert fm["title"] == hostile

    def test_required_lint_fields_present(self):
        """core_claim and a non-empty sources list are hard lint ERRORs if absent."""
        fm = _frontmatter(_render_entity_stub(_candidate(), _score(), _Engagement()))
        assert fm.get("core_claim")
        assert isinstance(fm.get("sources"), list) and fm["sources"]

    def test_core_claim_within_lint_cap(self):
        fm = _frontmatter(_render_entity_stub(_candidate(), _score(), _Engagement()))
        assert len(fm["core_claim"]) <= _CORE_CLAIM_MAX

    def test_sources_name_the_real_provenance_events(self):
        fm = _frontmatter(_render_entity_stub(_candidate(), _score(), _Engagement()))
        assert fm["sources"] == ["phronesis:nova-construction:01M0V1W6VGVMBJ5W99EWKYN29H"]


class TestDeriveCoreClaim:
    def test_takes_the_first_sentence(self):
        cand = _candidate(content="First sentence here. Second one follows.")
        assert _derive_core_claim(cand) == "First sentence here."

    def test_long_sentence_is_clipped_under_the_cap(self):
        cand = _candidate(content="word " * 200)
        claim = _derive_core_claim(cand)
        assert len(claim) <= _CORE_CLAIM_MAX
        assert claim.endswith("…")

    def test_clip_does_not_split_a_word(self):
        cand = _candidate(content="alpha " * 100)
        claim = _derive_core_claim(cand)
        assert "alph…" not in claim

    def test_falls_back_to_title_when_content_empty(self):
        cand = _candidate(content="", title="Fallback title")
        assert _derive_core_claim(cand) == "Fallback title"

    def test_never_returns_empty(self):
        cand = _candidate(content="", title="", slug="")
        assert _derive_core_claim(cand).strip()


class TestYamlScalar:
    def test_none_becomes_empty_string_not_the_word_none(self):
        assert yaml.safe_load(f"k: {_yaml_scalar(None)}")["k"] == ""

    def test_result_is_always_quoted(self):
        assert _yaml_scalar("plain").startswith('"')
