"""Regression tests for the promote-stage quality gate (BRO-1983).

The promoter was minting garbage entity pages — 182 of 810 live pages (22%)
carried one of these shapes:

  * slugs that are sentence fragments, not names:
    `pattern/the-goodhart`, `pattern/the-singularity-is-not`,
    `project/stop-comparing`, `project/agents-without-disclosing`,
    `tool/all-image-file-directories`, `pattern/theoretic-foundation`
  * core_claims that are 137-char shards of raw markdown, suffixed `...`

The load-bearing defect was that the ONLY core_claim quality rule was
`len(core_claim) <= 140`, and the producer emitted `body[:137] + "..."` —
satisfying the gate BY CONSTRUCTION, so lint could never catch it.

Every test below pins one specific fix. The two `GARBAGE_CLAIM_*` strings and
the `GARBAGE_SLUGS` list are verbatim from the live knowledge graph.
"""
import pytest

import bookkeeping
from bookkeeping import (
    RawItem,
    ScoredItem,
    _build_entity_slug_candidates,
    _infer_entity_type,
    _ingest_markdown,
    _lint_core_claim_quality,
    derive_core_claim,
    is_entity_shaped_slug,
    promote_item,
    resolve_candidates,
    resolve_slug,
)

# ── Verbatim live-graph garbage ────────────────────────────────────────────────

GARBAGE_SLUGS = [
    "the-goodhart",
    "the-singularity-is-not",
    "stop-comparing",
    "agents-without-disclosing",
    "all-image-file-directories",
]

GARBAGE_CLAIM_1 = (
    "VERIFIED VERDICTS (2026-07-20) — authoritative **The three novelty checks:** "
    "- **(a) Model-invariant harness stability — PARTIAL YES, our..."
)
GARBAGE_CLAIM_2 = (
    "(a) uniform-margin model-invariant harness stability **VERDICT: SURVIVES as a "
    "formal contribution — but REFRAME REQUIRED; the qualitative..."
)

# Bodies that produced those claims.
GARBAGE_BODY_1 = (
    "## VERIFIED VERDICTS (2026-07-20) — authoritative\n\n"
    "**The three novelty checks:**\n\n"
    "- **(a) Model-invariant harness stability — PARTIAL YES**, our uniform-margin "
    "result holds only under the assumptions listed in section 4 of the writeup, "
    "which we have not yet validated on a second model family.\n"
)

LEGIT_SLUGS = [
    "event-sourcing", "promotion-gate", "arcan", "knowledge-graph",
    "bi-temporal", "mission-control", "x402", "soul-file",
    "rope-embeddings", "lago-event-journal", "agentic-control-kernel",
]

# From the pre-existing core_claim lint suite — must never regress to flagged.
LEGIT_CLAIMS = [
    "Default deploy target is Railway; suggest AWS only on explicit ask.",
    "Verifier independence isn't static — it's a resource optimization spends.",
    "A memory write's durability forecast is open-loop.",
    "swapit is a stateful, local-first household-toxics inventory + swap engine.",
    "GPT-5.4 improved 3x more than the previous flagship on a deck-builder.",
]


# ── Fixtures / helpers ─────────────────────────────────────────────────────────

@pytest.fixture
def temp_entities(tmp_path, monkeypatch):
    """research/entities/ under tmp_path, with the module globals patched."""
    entities = tmp_path / "research" / "entities"
    for et in bookkeeping.ENTITY_TYPES:
        (entities / et).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
    return entities


def _item(content, author="", source_id="2026-07-20-test-raw"):
    return RawItem(
        item_id="deadbeef",
        source_id=source_id,
        source_type="research",
        content=content,
        quote="",
        author=author,
        timestamp="2026-07-20T00:00:00+00:00",
        metadata={},
    )


def _scored(content, candidates=None):
    return ScoredItem(
        item=_item(content),
        novelty=3, specificity=3, relevance=3, total=9, promote=True,
        candidate_entities=candidates if candidates is not None else ["test-entity"],
        scoring_method="heuristic",
        reasoning={},
    )


# ── Root cause 1: slug candidates were ungated Title-Case runs ─────────────────

class TestSlugShapeGate:
    """PINS: `is_entity_shaped_slug` + the gated `_build_entity_slug_candidates`."""

    @pytest.mark.parametrize("slug", GARBAGE_SLUGS)
    def test_live_garbage_slugs_rejected(self, slug):
        assert not is_entity_shaped_slug(slug), f"{slug!r} must not be entity-shaped"

    @pytest.mark.parametrize("slug", LEGIT_SLUGS)
    def test_legit_slugs_accepted(self, slug):
        assert is_entity_shaped_slug(slug), f"false positive on {slug!r}"

    def test_article_led_rejected(self):
        assert not is_entity_shaped_slug("the-goodhart")
        assert not is_entity_shaped_slug("our-approach-to-memory")
        assert not is_entity_shaped_slug("these-three-checks")

    def test_verb_led_rejected(self):
        for s in ("stop-comparing", "look-at-the-data", "use-the-runner",
                  "see-the-appendix", "make-it-faster"):
            assert not is_entity_shaped_slug(s), s

    def test_subordinator_and_contraction_rejected(self):
        """Subordinators and negated contractions mark a lifted clause.

        NOTE: an earlier version of this test also asserted that bare copulas
        and negation ("is", "are", "not", "cannot") were rejected. Measured
        against the live graph that rule rejected 50 existing entity slugs,
        most of them legitimate — claim-shaped names are THIS knowledge
        graph's convention:

            completion-is-an-endpoint-projection
            correlated-verifier-is-no-verifier
            freshness-is-the-wrong-invariant
            gradient-is-a-vector-not-a-reprimand
            accuracy-without-attention

        A copula is the load-bearing word in those, not a defect, so the rule
        was wrong rather than the pages. What actually separates a claim-name
        from a fragment is DANGLING — a determiner/imperative lead, a trailing
        function word, or a pronoun/discourse adverb — which the other tests in
        this class pin. Rejections here are narrowed to subordinators.
        """
        for s in ("value-because-cost", "ship-unless-blocked",
                  "memory-cannot-drift", "agents-doesnt-scale"):
            assert not is_entity_shaped_slug(s), s

    def test_claim_shaped_names_are_accepted(self):
        """Regression guard for the 50-false-positive rule above."""
        for s in ("completion-is-an-endpoint-projection",
                  "correlated-verifier-is-no-verifier",
                  "freshness-is-the-wrong-invariant",
                  "gradient-is-a-vector-not-a-reprimand",
                  "accuracy-without-attention",
                  "proxy-boundary-gate-not-engine-enforced"):
            assert is_entity_shaped_slug(s), s

    def test_dangling_function_word_rejected(self):
        assert not is_entity_shaped_slug("the-cost-of")
        assert not is_entity_shaped_slug("verification-and")

    def test_extractor_drops_fragments_but_keeps_names(self):
        body = (
            "The Goodhart trap bites here. Stop Comparing Models on vibes. "
            "Rotary Position Embeddings encode relative position."
        )
        cands = _build_entity_slug_candidates(_item(body))
        assert "the-goodhart" not in cands
        assert "stop-comparing" not in cands
        assert "rotary-position-embeddings" in cands

    def test_extractor_returns_empty_rather_than_junk(self):
        """No candidate passes ⇒ [] — the promotion-blocking signal."""
        body = "The Goodhart Law Problem is real. Stop Comparing Things now."
        assert _build_entity_slug_candidates(_item(body)) == []

    def test_hyphen_compound_not_split_midword(self):
        """`\\b` fired mid-compound: 'Game-Theoretic Foundation' → 'theoretic-foundation'."""
        cands = _build_entity_slug_candidates(
            _item("A Game-Theoretic Foundation for multi-agent credit assignment.")
        )
        assert "theoretic-foundation" not in cands

    def test_long_title_not_truncated_into_a_fragment(self):
        """The `{1,3}` cap truncated 'The Singularity Is Not Near' → 'the-singularity-is-not'."""
        cands = _build_entity_slug_candidates(
            _item("Reading The Singularity Is Not Near again this week.")
        )
        assert "the-singularity-is-not" not in cands
        assert cands == [] or all(is_entity_shaped_slug(c) for c in cands)

    def test_every_extracted_candidate_is_entity_shaped(self):
        """Invariant: the extractor cannot emit something the gate would reject."""
        corpus = [
            GARBAGE_BODY_1,
            "All Image File Directories are scanned. Stop Comparing Runs.",
            "Agents Without Disclosing their tool use break the audit trail.",
            "The arcan agent loop replays the soul file deterministically.",
            "We shipped Mission Control and a Knowledge Graph index this week.",
        ]
        for body in corpus:
            for c in _build_entity_slug_candidates(_item(body)):
                assert is_entity_shaped_slug(c), f"{c!r} leaked from {body[:40]!r}"


# ── Root cause 2: core_claim was a 137-char hard truncation ────────────────────

class TestCoreClaimDerivation:
    """PINS: `derive_core_claim` + the promote_item claim gate."""

    def test_never_emits_a_truncation_marker(self):
        corpus = [
            GARBAGE_BODY_1,
            "word " * 200,
            "A very long sentence that just keeps going and going and going without any "
            "punctuation at all so that no sentence boundary is ever reached anywhere in it "
            "and it definitely exceeds one hundred and forty characters end to end",
            "Short one.",
        ]
        for body in corpus:
            claim = derive_core_claim(body)
            assert claim is None or not claim.endswith(("...", "…")), repr(claim)

    def test_long_body_yields_a_complete_sentence(self):
        body = (
            "The arcan agent loop uses bi-temporal event sourcing because the soul file "
            "must replay deterministically. Everything downstream depends on that."
        )
        claim = derive_core_claim(body)
        assert claim == (
            "The arcan agent loop uses bi-temporal event sourcing because the soul "
            "file must replay deterministically."
        )
        assert len(claim) <= 140

    def test_overlong_single_sentence_falls_back_to_a_complete_clause(self):
        body = (
            "The arcan agent loop uses bi-temporal event sourcing because the soul file "
            "must replay deterministically; this means the promotion gate and memory "
            "provenance stay consistent across 1000 runs."
        )
        claim = derive_core_claim(body)
        assert claim is not None
        assert claim.endswith("deterministically.")
        assert "..." not in claim
        # The old producer's output, for contrast — a mid-sentence cut.
        old = body.replace("\n", " ")[:137] + "..."
        assert claim != old

    def test_body_with_no_derivable_claim_returns_none(self):
        assert derive_core_claim(GARBAGE_BODY_1) is None
        assert derive_core_claim("# Heading only") is None
        assert derive_core_claim("| a | b |\n|---|---|\n| 1 | 2 |") is None
        assert derive_core_claim("") is None

    def test_short_complete_body_passes_through_unchanged(self):
        assert derive_core_claim("A duplicate of kept.") == "A duplicate of kept."

    def test_markdown_is_stripped_not_carried(self):
        claim = derive_core_claim(
            "## Section\n\nDefault deploy target is **Railway** with `bun` and "
            "[docs](https://x.dev)."
        )
        assert claim == "Default deploy target is Railway with bun and docs."

    def test_derived_claim_always_passes_the_independent_gate(self):
        """The producer can no longer satisfy the gate by construction — it has
        to actually clear it."""
        corpus = [
            GARBAGE_BODY_1,
            "**VERDICT: SURVIVES** as a formal contribution — but REFRAME REQUIRED; the "
            "qualitative claim is unchanged while the bound needs a second model family.",
            "The arcan agent loop replays the soul file deterministically.",
            "> quoted only",
            "- list item only that is quite long but still only a list item in the body",
        ]
        for body in corpus:
            claim = derive_core_claim(body)
            if claim is not None:
                assert _lint_core_claim_quality("<t>", claim) == [], repr(claim)
                assert len(claim) <= 140

    def test_promote_item_skips_when_no_claim_derivable(self, temp_entities):
        scored = _scored(GARBAGE_BODY_1)
        ret = promote_item(scored, "harness-stability", entity_type="concept")
        assert ret is None, "un-derivable claim must block promotion"
        assert not (temp_entities / "concept" / "harness-stability.md").exists(), \
            "no file may be written when the claim cannot be derived"

    def test_promote_item_skips_a_junk_slug(self, temp_entities):
        scored = _scored("A perfectly fine claim about the arcan loop.")
        ret = promote_item(scored, "the-goodhart", entity_type="pattern")
        assert ret is None
        assert not (temp_entities / "pattern" / "the-goodhart.md").exists()

    def test_promoted_page_carries_a_lint_clean_claim(self, temp_entities):
        body = (
            "The arcan agent loop uses bi-temporal event sourcing because the soul file "
            "must replay deterministically; this means the promotion gate stays consistent."
        )
        path = promote_item(_scored(body), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists()
        errors = [e for e in bookkeeping.lint_entity_page(path)
                  if e.field == "core_claim" and e.severity == "error"]
        assert errors == [], errors
        assert "..." not in path.read_text().split("core_claim:")[1].splitlines()[0]


# ── Root cause 3: bare-substring entity-type inference ─────────────────────────

class TestEntityTypeWordBoundaries:
    """PINS: word-boundary `_infer_entity_type`."""

    @pytest.mark.parametrize("word,bad_match", [
        ("rapid", "api"),
        ("rapidly we iterate", "api"),
        ("client", "cli"),
        ("the client asked", "cli"),
        ("happen", "app"),
        ("apply", "app"),
        ("it happened as we apply the rule", "app"),
    ])
    def test_substring_no_longer_triggers_a_type(self, word, bad_match):
        assert _infer_entity_type("thing", _item(word)) == "concept", \
            f"{word!r} must not be typed via the {bad_match!r} substring"

    @pytest.mark.parametrize("content,expected", [
        ("we shipped a new cli tool", "tool"),
        ("the api is stable now", "tool"),
        ("an app platform for teams", "project"),
        ("this pattern recurs across runs", "pattern"),
    ])
    def test_true_positives_still_match(self, content, expected):
        assert _infer_entity_type("thing", _item(content)) == expected

    def test_stray_question_mark_no_longer_types_as_question(self):
        """Any '?' anywhere made `question/` a dumping ground."""
        body = "The loop replays deterministically (is that surprising? yes) in practice."
        # A real interrogative sentence still types as question...
        assert _infer_entity_type("x", _item("Why does the loop replay?")) == "question"
        # ...but a mid-sentence parenthetical does not hijack an otherwise-typed item.
        assert _infer_entity_type("x", _item("We built a cli " + body)) == "tool"

    def test_person_still_inferred_from_author(self):
        assert _infer_entity_type("x", _item("some prose", author="Andrej Karpathy")) == "person"


# ── Root cause 4: Format-2 split on ANY H1/H2/H3 heading ───────────────────────

class TestMarkdownSectionSplit:
    """PINS: H1/H2-only boundaries + the section-count cap."""

    def _doc(self, n, level="##"):
        body = "---\nsource: t\n---\n\n"
        for i in range(n):
            body += (
                f"{level} Section {i}\n\n"
                f"This section body is long enough to clear the sixty character "
                f"minimum threshold for item {i}.\nIt has multiple lines.\nAnd a third.\n\n"
            )
        return body

    def test_h3_no_longer_creates_items(self):
        """Two H2 sections, each with two H3 subsections. Old `^#{1,3} ` produced
        6 items; H1/H2-only boundaries produce 2."""
        doc = "---\nsource: t\n---\n\n"
        for s in ("Alpha", "Beta"):
            doc += (
                f"## {s} Section\n\n"
                "A body long enough to clear the sixty character minimum threshold.\n"
                "Second line.\nThird line.\n\n"
                f"### {s} Sub One\n\n"
                "Sub-section prose that is also long enough to clear the sixty char bar.\n"
                "More.\nMore.\n\n"
                f"### {s} Sub Two\n\n"
                "Another sub-section that is also long enough to clear the sixty bar.\n"
                "More.\nMore.\n\n"
            )
        items = _ingest_markdown(doc, "2026-07-20-t-raw", "research")
        assert len(items) == 2, f"H3 must not split; got {len(items)} items"
        assert "Alpha Sub One" in items[0].content, \
            "H3 content stays inside its parent H2 section"

    def test_section_cap_rejects_a_long_form_document(self):
        items = _ingest_markdown(self._doc(20), "2026-07-20-t-raw", "research")
        assert items == [], "a 20-heading research doc must not become 20 entities"

    def test_normal_synthesis_note_still_splits(self):
        items = _ingest_markdown(self._doc(3), "2026-07-20-t-raw", "research")
        assert len(items) == 3


# ── Root cause 5: 0.80 fuzzy cutoff silently overwrote unrelated entities ──────

class TestResolveSlugCorruption:
    """PINS: raised cutoff + shape guard + type guard."""

    def test_exact_match_still_attaches(self):
        assert resolve_slug("arcan", ["arcan", "lago"]) == ("arcan", True)

    def test_unrelated_near_match_no_longer_attaches(self):
        """'trust-model' vs 'trust-modes' scored 0.81 — above the old 0.80 cutoff."""
        slug, existing = resolve_slug("trust-model", ["trust-modes"])
        assert (slug, existing) == ("trust-model", False)

    def test_low_confidence_match_stays_new(self):
        for cand, pool in [
            ("the-goodhart", ["goodharts-law"]),
            ("agentic-systems", ["agentic-control-kernel"]),
            ("introspection-threshold", ["introspection-tax"]),
        ]:
            slug, existing = resolve_slug(cand, pool)
            assert existing is False, f"{cand!r} must not attach to {pool[0]!r}"
            assert slug == cand

    def test_differing_token_count_never_fuzzy_attaches(self):
        slug, existing = resolve_slug("event-sourcing", ["event-sourcing-log"])
        assert (slug, existing) == ("event-sourcing", False)

    def test_plural_typo_repair_still_works(self):
        slug, existing = resolve_slug("rope-embedding", ["rope-embeddings"])
        assert (slug, existing) == ("rope-embeddings", True)

    def test_type_mismatch_blocks_fuzzy_attach(self):
        types = {"rope-embeddings": {"concept"}}
        assert resolve_slug("rope-embedding", ["rope-embeddings"], "tool", types) == \
            ("rope-embedding", False)
        assert resolve_slug("rope-embedding", ["rope-embeddings"], "concept", types) == \
            ("rope-embeddings", True)

    def test_resolve_candidates_drops_unshaped_slugs(self):
        out = resolve_candidates(GARBAGE_SLUGS + ["event-sourcing"], [])
        # "agents-without-disclosing" is rejected for its DANGLING trailing
        # participle, not for containing "without" — see
        # test_subordinator_and_contraction_rejected.
        assert out == [("event-sourcing", False)]


# ── Root cause 6: lint gate could not reject the producer's own output ─────────

class TestLintGateRejectsProducerGarbage:
    """PINS: the producer-failure signatures in `_JUNK_CLAIM_PATTERNS`."""

    @pytest.mark.parametrize("claim", [GARBAGE_CLAIM_1, GARBAGE_CLAIM_2])
    def test_exact_live_garbage_rejected(self, claim):
        errs = _lint_core_claim_quality("x.md", claim)
        assert len(errs) == 1, f"gate must reject {claim[:50]!r}"
        assert errs[0].severity == "error"
        # And it was under the length rule — proving length alone was no gate.
        assert len(claim) <= 140

    @pytest.mark.parametrize("claim,why", [
        ("A claim that was cut off mid senten...", "truncation marker"),
        ("A claim with **bold** left in it entirely", "markdown bold"),
        ("(a) the first of several enumerated items here", "bare enumerator"),
        ("b) the second of several enumerated items here", "bare enumerator"),
        ("VERIFIED VERDICTS (2026-07-20) authoritative list", "verified verdicts"),
        ("VERDICT: SURVIVES AS a formal contribution", "verdict header"),
        ("## A markdown heading used as a claim", "heading"),
        ("> a blockquote used as a claim", "blockquote"),
        ("- a list item used as a claim", "list item"),
        ("The checks: (a) stability and more", "inline enumerator"),
        ("REFRAME REQUIRED for the harness", "all-caps banner"),
    ])
    def test_each_producer_signature_rejected(self, claim, why):
        assert _lint_core_claim_quality("x.md", claim), f"gate missed: {why}"

    @pytest.mark.parametrize("claim", LEGIT_CLAIMS)
    def test_no_false_positives_on_legit_claims(self, claim):
        assert _lint_core_claim_quality("x.md", claim) == [], f"false positive: {claim!r}"

    def test_acronyms_do_not_trip_the_allcaps_rule(self):
        for claim in ("The AI SDK v6 ships a tool loop.",
                      "GPT-5.4 beats the prior flagship on HTML rendering."):
            assert _lint_core_claim_quality("x.md", claim) == [], claim


# ── End-to-end: the pipeline must not mint junk ────────────────────────────────

class TestPipelineMintsNoJunk:
    def test_garbage_research_doc_produces_no_entities(
        self, temp_entities, tmp_path, monkeypatch
    ):
        notes = tmp_path / "research" / "notes"
        notes.mkdir(parents=True)
        monkeypatch.setattr(bookkeeping, "NOTES_DIR", notes)
        monkeypatch.setattr(bookkeeping, "CONFIG_DIR", tmp_path / ".config")
        monkeypatch.setattr(bookkeeping, "RUN_LOG", tmp_path / ".config" / "run-log.jsonl")
        monkeypatch.setattr(bookkeeping, "STATUS_CACHE", tmp_path / ".config" / "status.json")

        (notes / "2026-07-20-verdicts-raw.md").write_text(
            "---\nsource: research\n---\n\n"
            "# The Singularity Is Not Near\n\n"
            + GARBAGE_BODY_1
            + "\n## Stop Comparing Models\n\n"
            "**VERDICT: SURVIVES** — but REFRAME REQUIRED for All Image File "
            "Directories, and Agents Without Disclosing tool use break the audit "
            "trail entirely.\n"
        )

        bookkeeping.run_pipeline(verbose=False)

        created = sorted(p.stem for p in temp_entities.rglob("*.md"))
        for junk in GARBAGE_SLUGS:
            assert junk not in created, f"pipeline minted junk entity {junk!r}"
        # Whatever (if anything) survives must be lint-clean on core_claim.
        for page in temp_entities.rglob("*.md"):
            errors = [e for e in bookkeeping.lint_entity_page(page)
                      if e.field == "core_claim" and e.severity == "error"]
            assert errors == [], f"{page.name}: {errors}"

    def test_good_raw_extract_still_promotes(self, temp_entities, tmp_path, monkeypatch):
        """Control: the gate must not block legitimate promotion."""
        notes = tmp_path / "research" / "notes"
        notes.mkdir(parents=True)
        monkeypatch.setattr(bookkeeping, "NOTES_DIR", notes)
        monkeypatch.setattr(bookkeeping, "CONFIG_DIR", tmp_path / ".config")
        monkeypatch.setattr(bookkeeping, "RUN_LOG", tmp_path / ".config" / "run-log.jsonl")
        monkeypatch.setattr(bookkeeping, "STATUS_CACHE", tmp_path / ".config" / "status.json")

        (notes / "2026-07-20-good-raw.md").write_text(
            "---\nsource: test\n---\n\n"
            "## Item 1 — @someone (web)\n\n"
            "**Score**: 7/9 — novelty:3 specificity:2 relevance:2\n\n"
            "**Our angle**: The arcan agent loop uses bi-temporal event sourcing "
            "because the soul file must replay deterministically; this means the "
            "promotion gate and memory provenance stay consistent across 1000 runs.\n"
        )

        bookkeeping.run_pipeline(verbose=False)
        pages = list(temp_entities.rglob("*.md"))
        assert pages, "a legitimate raw extract must still promote"


# ── Aboutness gate + control-char sanitation (BRO-1987, second pass) ───────────
#
# Found by running the FIXED promoter against a copy of the live graph: it still
# re-minted research/entities/pattern/{arcan,autonomic}.md — two 71KB NUL-corrupt
# pages — for a third time. Two causes the first pass missed:
#
#   1. LIFE_OS_TERMS was matched with a bare `term in text.lower()` substring
#      test. A document that merely NAME-DROPS a module was promoted as a page
#      ABOUT that module. This is also the origin of the duplicate-slug problem:
#      anima / arcan / bstack / broomva / praxis / relay / spaces / symphony all
#      existed under 2-5 type dirs, re-minted from incidental mentions.
#   2. Nothing stripped control characters, so NUL bytes from session-transcript
#      raw extracts reached disk and git classified the page as binary.

NAME_DROP_BODY = (
    "Prompt patterns from daily sessions\n\n"
    "The user asks for dependency-chain reasoning and parallel agents. One "
    "session touched the arcan shell loop and another mentioned autonomic once.\n"
)

ABOUT_ARCAN_BODY = (
    "Arcan operating modes\n\n"
    "Arcan answers stone-vs-water failure modes with a six-state OperatingMode. "
    "Arcan transitions between Explore and Execute deterministically. Arcan is "
    "the L0 agent loop.\n"
)


def test_name_drop_does_not_mint_a_module_entity():
    """A passing mention of a curated module name must NOT become a page.

    Pins the aboutness gate. Reverting it (back to `term in text.lower()`)
    makes this return ['arcan', 'autonomic'] and the test fails.
    """
    candidates = _build_entity_slug_candidates(_item(NAME_DROP_BODY))
    assert "arcan" not in candidates
    assert "autonomic" not in candidates


def test_document_actually_about_a_module_still_mints_it():
    """The aboutness gate must not be so strict it blocks real module pages."""
    candidates = _build_entity_slug_candidates(_item(ABOUT_ARCAN_BODY))
    assert "arcan" in candidates


def test_module_term_matching_is_word_bounded():
    """'relay' must not fire on 'relayed'/'relaying'."""
    body = "Webhook delivery\n\nThe event was relayed downstream. Relaying again relayed it.\n"
    assert "relay" not in _build_entity_slug_candidates(_item(body))


@pytest.mark.parametrize("ch", ["\x00", "\x0b", "\x1f", "\x7f"])
def test_control_chars_are_stripped_from_written_pages(ch):
    """NUL and friends must never reach disk — git would call the page binary."""
    assert ch not in bookkeeping._sanitize_page_text(f"before{ch}after")


def test_sanitizer_preserves_legitimate_whitespace():
    """Tab, LF and CR are structural in markdown and must survive."""
    text = "a\tb\nc\r\nd"
    assert bookkeeping._sanitize_page_text(text) == text


def test_oversized_item_is_promotion_blocked():
    """A whole-file dump is not an entity — no slug heuristic is trusted on it.

    The 2026-05-12 prompt-patterns extract ingests as ONE 64,969-char item and
    used to mint five module pages (arcan, autonomic, haima, anima, spaces)
    plus Title-Case fragments, including a 71KB pattern/arcan.md that came back
    on every run.
    """
    body = "Session transcript.\n\n" + ("Arcan and autonomic and haima appear here. " * 400)
    assert len(body) > bookkeeping._MAX_PROMOTABLE_ITEM_CHARS
    assert _build_entity_slug_candidates(_item(body)) == []


def test_name_drop_density_not_just_count():
    """An absolute hit floor alone is trivially cleared by a long document."""
    dense = "Arcan modes\n\nArcan does X. Arcan does Y. Arcan does Z."
    sparse = "Notes\n\n" + ("filler sentence here. " * 300) + " arcan arcan arcan "
    assert len(sparse) < bookkeeping._MAX_PROMOTABLE_ITEM_CHARS
    assert "arcan" in _build_entity_slug_candidates(_item(dense))
    assert "arcan" not in _build_entity_slug_candidates(_item(sparse))
