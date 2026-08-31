"""The entity stub must emit a page the knowledge graph accepts.

Regression cover for BRO-2404.

WHAT THIS FILE LEARNED THE HARD WAY. The first version of these tests
re-derived the linter's rules locally — `len(claim) <= _CORE_CLAIM_MAX`,
`assert fm.get("core_claim")`, `isinstance(fm["sources"], list)`. Every one of
those proxies is weaker than the linter it stands in for, and the suite went
green over output the real linter rejects with a hard ERROR. A P20 mutation
sweep found 16 of 29 mutants surviving.

So the anchor test here imports `bookkeeping.lint_entity_page` and asserts zero
ERROR-severity findings over rendered output, including every real entity body
on disk. If the graph's rules change, this file fails — which is the point.
"""

from __future__ import annotations

import pytest
import yaml

from core.extraction.candidates import ExtractionCandidate
from core.extraction.pipeline import (
    _bookkeeping_module,
    _CandidateScore,
    _derive_core_claim,
    _render_entity_stub,
    _yaml_scalar,
)

pytestmark = pytest.mark.unit

CANARY_TENANT = "nova-construction"


class _Tenant:
    tenant_slug = CANARY_TENANT


class _Engagement:
    tenant = _Tenant()


GOOD_CLAIM = (
    "In a construction engagement 3 of 8 use cases came from business-pain "
    "ideation, suggesting RICE needs explicit source weighting."
)


def _candidate(**over) -> ExtractionCandidate:
    kwargs = dict(
        slug="rice-business-pain-weight-construction",
        entity_type="framework-refinement",
        content=GOOD_CLAIM,
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


def _render(cand=None, claim=GOOD_CLAIM) -> str:
    return _render_entity_stub(cand or _candidate(), _score(), _Engagement(), claim)


def _frontmatter(text: str) -> dict:
    """Split on a line-anchored delimiter, not a bare '---' substring.

    `text.split("---", 2)[1]` slices on the first two occurrences ANYWHERE,
    so a '---' inside a scalar mis-slices mid-value and the helper reports a
    failure production does not have. Anchor on the line.
    """
    assert text.startswith("---\n")
    body = text[4:]
    end = body.index("\n---\n")
    return yaml.safe_load(body[:end])


def _lint_errors(rendered: str, slug: str, entity_type: str, tmp_path) -> list:
    """Run the REAL linter and return only ERROR-severity findings."""
    bk = _bookkeeping_module()
    if bk is None:
        pytest.fail(
            "bookkeeping is not importable, so this suite would silently "
            "exercise the stub instead of the real gate — the exact condition "
            "that let 20 pages ship with stub scores."
        )
    d = tmp_path / "research" / "entities" / entity_type
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{slug}.md"
    f.write_text(rendered, encoding="utf-8")
    return [e for e in bk.lint_entity_page(f) if getattr(e, "severity", None) == "error"]


# ---------------------------------------------------------------------------
# The anchor: the claim the docstring makes, checked by the thing that judges it
# ---------------------------------------------------------------------------


class TestLintClean:
    def test_rendered_stub_has_no_lint_errors(self, tmp_path):
        errs = _lint_errors(_render(), "rice-x", "framework-refinement", tmp_path)
        assert errs == [], [str(e) for e in errs]

    # DELETED: test_every_real_entity_body_on_disk_renders_lint_clean.
    #
    # It walked ~/broomva/research/entities and re-derived each page's
    # core_claim. A P20 mutation sweep measured its marginal value as ZERO:
    # replacing `failures += 1` with `pass` — so it could report nothing —
    # left all 500 tests green. Every mutant it might have caught was already
    # caught by test_rendered_stub_has_no_lint_errors above.
    #
    # It was also actively harmful in two ways. It fed each page's EXISTING
    # core_claim back in as content, so `derive_core_claim` returned all 20
    # unchanged — it asserted that 20 valid claims are valid. And on a clean
    # machine the corpus it walked was the suite's OWN output, because eight
    # test files wrote into that directory first: ground truth produced by the
    # arm under test. It is why the suite touched the live graph at all.
    #
    # Deleting it removed a blocker, a major, and three mutation survivors at
    # the cost of no measured coverage.

# ---------------------------------------------------------------------------
# Anonymization: sources must not carry the tenant into the indexed surface
# ---------------------------------------------------------------------------


class TestAnonymization:
    def test_sources_do_not_carry_the_tenant_slug(self):
        """`sources` is rendered into docs/knowledge-index.md and scored by /kg.

        `provenance.engagement_slug` is not read by the indexer; `sources` is.
        Putting the slug there moved it into the workspace-wide retrieval
        surface — 0 to 20 occurrences in the catalog, measured.
        """
        fm = _frontmatter(_render())
        assert fm["sources"] == ["phronesis:01M0V1W6VGVMBJ5W99EWKYN29H"]
        for src in fm["sources"]:
            assert CANARY_TENANT not in src

    def test_empty_event_ids_still_yields_a_tenant_free_source(self):
        """The fallback branch — reachable when a payload lacks `_event_id`."""
        fm = _frontmatter(_render(_candidate(provenance_event_ids=[])))
        assert fm["sources"] == ["phronesis:unattributed"]
        assert CANARY_TENANT not in str(fm["sources"])


# ---------------------------------------------------------------------------
# Quoting — the actual bug this change exists to fix
# ---------------------------------------------------------------------------


class TestQuoting:
    def test_colon_bearing_title_still_parses(self):
        assert _frontmatter(_render())["title"] == (
            "RICE: business-pain weighting in construction"
        )

    @pytest.mark.parametrize("field,value,read", [
        ("title", "has: a colon", lambda fm: fm["title"]),
        ("title", "hash # not a comment", lambda fm: fm["title"]),
        ("title", "before --- after", lambda fm: fm["title"]),
        ("title", "no", lambda fm: fm["title"]),
        ("title", "1.0", lambda fm: fm["title"]),
        ("title", 'quote "inside"', lambda fm: fm["title"]),
        ("title", "line\nbreak", lambda fm: fm["title"]),
        ("title", "backslash \\ and tab \t", lambda fm: fm["title"]),
        ("title", "control \x7f DEL", lambda fm: fm["title"]),
        ("title", "nel \x85 char", lambda fm: fm["title"]),
    ])
    def test_hostile_values_round_trip(self, field, value, read):
        """Includes the C0/C1 controls `ensure_ascii=False` let through raw:
        U+007F is rejected by PyYAML outright, U+0085 silently folds to a
        space. Both round-trip once escaped."""
        assert read(_frontmatter(_render(_candidate(**{field: value})))) == value

    def test_type_field_is_quoted(self):
        """`type:` was one of two fields the first fix missed while its
        docstring claimed every scalar was covered.

        A hostile value is NOT constructible — `entity_type` is a pydantic
        Literal, so pydantic rejects a colon-bearing type before the renderer
        sees it. Asserting the round-trip would be a test of an unreachable
        fixture. Assert the structural property instead: the field is quoted,
        so a future widening of that Literal cannot silently reintroduce the
        bug."""
        line = next(line for line in _render().split("\n") if line.startswith("type:"))
        assert line.split(":", 1)[1].strip().startswith('"'), line

    def test_colon_in_framework_ref_parses(self):
        assert _frontmatter(_render())["score"]["framework_ref"] == "framework:rice"

    def test_colon_SPACE_in_framework_ref_parses(self):
        """`framework:rice` has no colon-SPACE, so it is a legal plain scalar
        and parses whether or not the field is quoted — the old test could not
        fail. `framework_ref` is a free `str` on the model (unlike
        `entity_type`, which is a Literal), so a colon-space value is
        reachable and reproduces the original BRO-2404 ScannerError."""
        cand = _candidate(framework_ref="rice: v2 weighting")
        assert _frontmatter(_render(cand))["score"]["framework_ref"] == "rice: v2 weighting"

    def test_colon_in_industry_parses(self):
        cand = _candidate(industry="banking: mid-market", framework_ref=None)
        assert _frontmatter(_render(cand))["score"]["industry"] == "banking: mid-market"

    def test_framework_ref_placement_matches_entities_already_on_main(self):
        """`framework_ref`/`industry` nest under `score:` (two-space indent).

        Pre-existing and shared by every published entity. Moving it is a
        schema migration; this guards it from moving silently.
        """
        fm = _frontmatter(_render())
        assert "framework_ref" not in fm
        assert "framework_ref" in fm["score"]

    def test_colon_in_signal_key_and_value_parse(self):
        cand = _candidate(signals={"ratio: pct": "three: of eight"})
        assert {"ratio: pct": "three: of eight"} in _frontmatter(_render(cand))["signals"]

    def test_numeric_signals_stay_numeric(self):
        """The isinstance guard: floats must not silently become strings."""
        signals = _frontmatter(_render())["signals"]
        share = next(d["share"] for d in signals if "share" in d)
        assert isinstance(share, float) and share == 0.375

    @pytest.mark.parametrize("field", ["engagement_slug", "method", "created_at"])
    def test_every_scalar_field_is_quoted(self, field):
        """These four sites were changed by the fix and had no test at all —
        each could be reverted to bare interpolation with the suite green."""
        line = next(line for line in _render().split("\n") if line.strip().startswith(f"{field}:"))
        assert line.split(":", 1)[1].strip().startswith('"'), line

    def test_event_ids_are_quoted(self):
        line = next(
            line for line in _render().split("\n")
            if line.strip().startswith("- 01M0") or '\"01M0' in line
        )
        assert '"' in line, line

    def test_slug_field_is_not_emitted(self):
        """workspace#530 (BRO-2361) deleted `slug:` across 402 pages as
        redundant with the filename stem. Re-emitting it undoes that."""
        assert "slug" not in _frontmatter(_render())


# ---------------------------------------------------------------------------
# Claim derivation is DELEGATED — no second implementation
# ---------------------------------------------------------------------------


class TestDeriveCoreClaim:
    def test_delegates_to_bookkeeping(self):
        bk = _bookkeeping_module()
        assert bk is not None and hasattr(bk, "derive_core_claim")
        cand = _candidate(content=GOOD_CLAIM)
        assert _derive_core_claim(cand) == bk.derive_core_claim(GOOD_CLAIM)

    def test_unpromotable_body_returns_none_rather_than_truncating(self):
        """The whole point. BRO-1983: 'A `...` suffix is never emitted, at any
        step.' The previous implementation returned `sentence[:139] + "…"`,
        which the linter rejects as a hard ERROR."""
        cand = _candidate(content="word " * 200)
        assert _derive_core_claim(cand) is None

    def test_never_emits_a_truncation_marker(self):
        for body in ["word " * 200, "alphabet " * 40, "x" * 400, GOOD_CLAIM]:
            claim = _derive_core_claim(_candidate(content=body))
            if claim is not None:
                assert not claim.rstrip().endswith(("…", "..."))

    def test_returns_none_when_bookkeeping_is_unavailable(self, monkeypatch):
        """Fail CLOSED. If the canonical deriver cannot be imported, the answer
        is None (block promotion) — never "" and never a local truncation.

        This is the branch that let 20 pages ship with stub scores: the module
        path was dead, the fallback was silent, and nothing noticed.
        """
        import core.extraction.pipeline as pipeline

        monkeypatch.setattr(pipeline, "_bookkeeping_module", lambda: None)
        assert pipeline._derive_core_claim(_candidate()) is None

    def test_returns_none_when_bookkeeping_lacks_the_deriver(self, monkeypatch):
        import core.extraction.pipeline as pipeline

        monkeypatch.setattr(pipeline, "_bookkeeping_module", lambda: object())
        assert pipeline._derive_core_claim(_candidate()) is None

    # NOTE: the integration edge — that the page `extract_and_queue` WRITES
    # carries the claim `_derive_core_claim` returned — cannot be closed from
    # here, because this file only ever calls the renderer directly. The
    # previous test at this spot computed `claim`, passed it into `_render`,
    # and asserted the output equalled `claim`: a tautology that could not
    # fail, whose docstring claimed it closed that edge. A mutation proved the
    # edge was still open (rendering a hardcoded string left all 500 green).
    # The real assertion lives in tests/integration/test_extraction_pipeline.py
    # ::test_promoted_page_carries_the_derived_claim, which reads the file off
    # disk after a real run.


class TestYamlScalar:
    def test_none_becomes_empty_string_not_the_word_none(self):
        assert yaml.safe_load(f"k: {_yaml_scalar(None)}")["k"] == ""

    @pytest.mark.parametrize("value", ["plain", 1, 1.5, True, None])
    def test_result_is_always_quoted(self, value):
        assert _yaml_scalar(value).startswith('"')
