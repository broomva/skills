"""
The Nous judge must not re-open the junk-promotion path the grounding floor
closed (BRO-2506 x BRO-2614).

The two changes land in different stages and came from different arcs:

  BRO-2614 (#235)  a deterministic GROUNDING FLOOR at the promote door — the
                   derived claim, minus the item's section heading, must name
                   the slug's head noun. Fixture: the workspace#789 cohort.
  BRO-2506 (#224)  the LLM judge in `score_item`, for the ambiguous 3-6 band.
                   It had never executed once; wiring it changes SCORES.

THE HAZARD IS THE INTERACTION, not either change. The judge can lift an item
from below the promote threshold to above it, so the door now receives items
that never reached it before. If the floor were upstream of scoring, or keyed
off the score at all, a generous judge would walk the #789 junk straight back
in.

What is deliberately NOT done here: the fixture's recorded `core_claim` values
came from full Layer-2 bodies and do not re-derive from (heading, claim) alone
— replaying them through `derive_core_claim` would build a strawman item and
then congratulate the floor for refusing it. So the fixture is used at the
PREDICATE level, where its recorded values are exactly what the floor saw in
production, and the end-to-end path uses the item constructions
`test_grounding_floor.py` already proves reach the door.
"""
import json
from pathlib import Path

import pytest

import bookkeeping
from bookkeeping import RawItem, ScoredItem, passes_grounding_floor, promote_item

FIXTURE = Path(__file__).parent / "fixtures" / "pr789" / "entities.json"
ENTITIES = json.loads(FIXTURE.read_text())["entities"]
JUNK = [e for e in ENTITIES if e["verdict"] == "junk"]
KEPT = [e for e in ENTITIES if e["verdict"] == "kept"]

BODY_TAIL = (" The team measured it twice against the published figures and"
             " recorded both runs in the attached analysis file.")


def _key(e):
    return f"{e['type']}/{e['slug']}"


@pytest.fixture
def door(tmp_path, monkeypatch):
    """The real promote door, isolated from the coherence transport, so a
    refusal here is the grounding floor's and not the coherence gate's."""
    entities = tmp_path / "research" / "entities"
    for et in bookkeeping.ENTITY_TYPES:
        (entities / et).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
    monkeypatch.setenv(bookkeeping.COHERENCE_GATE_ENV, "0")
    bookkeeping.reset_grounding_run_state()
    return entities


@pytest.fixture
def maximal_judge(monkeypatch):
    """The judge, wired, returning the strongest possible promote signal.

    3/3/3 on purpose: a weaker stub would not discriminate. The claim under
    test is that NO score, however high, buys grounding.
    """
    bookkeeping.set_judge_enabled(True)
    bookkeeping.reset_judge_run_state()
    monkeypatch.setattr(
        bookkeeping, "score_item_claude_cli",
        lambda item, slugs: ScoredItem(
            item=item, novelty=3, specificity=3, relevance=3, total=9,
            promote=True, candidate_entities=[], scoring_method="claude_cli",
            reasoning={}))
    monkeypatch.setattr(bookkeeping, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bookkeeping, "score_item_llm", lambda *a, **k: None)
    yield
    bookkeeping.set_judge_enabled(False)
    bookkeeping.reset_judge_run_state()


def _section(heading, body, item_id="jg000001"):
    """An item exactly as Format-2 ingest builds it — the construction
    test_grounding_floor.py proves reaches the door."""
    return RawItem(item_id=item_id, source_id="2026-09-27-judge-grounding-raw",
                   source_type="research", content=f"{heading}\n\n{body}",
                   quote="", author="",
                   timestamp="2026-09-27T00:00:00+00:00",
                   metadata={bookkeeping._SECTION_HEADING_METADATA_KEY: heading})


# ── the judge is genuinely wired (guards every assertion below) ──────────────

def test_the_stubbed_judge_actually_runs(maximal_judge):
    """
    If the judge silently did not run, every refusal below would prove nothing
    — the floor would just be facing the heuristic score it already faced
    before BRO-2506. That is precisely how this path looked for 7,765 runs.
    """
    scored = bookkeeping.score_item_with_judge(
        _section("Items", "Verified against the paper." + BODY_TAIL), [])
    assert scored is not None, "the judge produced no score"
    assert scored.scoring_method == "claude_cli"
    assert scored.total == 9


def test_the_judge_lifts_an_item_across_the_promote_threshold(monkeypatch, maximal_judge):
    """
    THE NEW REACHABILITY this PR creates. A 4/9 item never reached the promote
    door before; with the judge wired it scores 9/9 and does. Without this, the
    reconciliation tests below would be guarding a path nothing travels.
    """
    monkeypatch.setattr(
        bookkeeping, "score_item_heuristic",
        lambda i: ScoredItem(item=i, novelty=2, specificity=1, relevance=1, total=4,
                             promote=False, candidate_entities=[],
                             scoring_method="heuristic", reasoning={}))
    item = _section("Items", "Verified against the paper." + BODY_TAIL)
    scored = bookkeeping.score_item(item, [])
    assert scored.scoring_method == "claude_cli"
    assert 4 < bookkeeping.PROMOTE_THRESHOLD <= scored.total


# ── the reconciliation, end to end ───────────────────────────────────────────

def test_a_lifted_item_is_still_refused_at_the_door(door, monkeypatch, maximal_judge):
    """The whole point: judge lifts 4 -> 9, door still refuses on grounding."""
    monkeypatch.setattr(
        bookkeeping, "score_item_heuristic",
        lambda i: ScoredItem(item=i, novelty=2, specificity=1, relevance=1, total=4,
                             promote=False, candidate_entities=[],
                             scoring_method="heuristic", reasoning={}))
    scored = bookkeeping.score_item(
        _section("Items", "Verified against the paper." + BODY_TAIL), [])
    assert scored.total == 9 and scored.promote is True

    assert promote_item(scored, "beata-halassy", "pattern") is None, (
        "a 9/9 judge score bought promotion past the grounding floor")
    assert not (door / "pattern" / "beata-halassy.md").exists()
    assert bookkeeping.grounding_stats()["refused"] == 1


def test_a_heading_derived_junk_slug_is_refused_with_the_judge_wired(door, maximal_judge):
    """The second #789 shape: the slug comes from the heading, not the claim."""
    h = '/checkit — "Build a Jev Judge" (Jev-as-judge + Opik tutorial), run live'
    scored = bookkeeping.score_item_with_judge(
        _section(h, "Eighth X-article ingest on the TypeSafe Jev arc." + BODY_TAIL), [])
    assert scored.total == 9
    assert promote_item(scored, "jev-judge", "tool") is None
    assert not (door / "tool" / "jev-judge.md").exists()


# ── the #789 cohort, at the predicate level, with the judge enabled ──────────

@pytest.mark.parametrize("e", JUNK, ids=_key)
def test_every_789_junk_page_still_fails_the_floor(e, maximal_judge):
    """
    The fixture's recorded (slug, claim, heading, type) — exactly what the
    floor saw in production — still fails while the judge is enabled.

    This is a guard against a FUTURE change making grounding score-aware: the
    floor's signature takes no score today, and this pins that the answer does
    not move when a maximal judge is live.
    """
    assert bookkeeping.judge_enabled() is True
    assert not passes_grounding_floor(
        e["slug"], e["core_claim"], e["section_heading"], e["type"])


@pytest.mark.parametrize("e", KEPT, ids=_key)
def test_both_kept_789_pages_still_pass_the_floor(e, maximal_judge):
    """Positive control: a floor that refuses everything also refuses junk."""
    assert passes_grounding_floor(
        e["slug"], e["core_claim"], e["section_heading"], e["type"])


# ── positive control through the real door, judge wired ─────────────────────

def test_a_grounded_page_still_promotes_with_the_judge_wired(door, maximal_judge):
    """
    If the judge's presence broke promotion outright, every refusal above would
    pass for the wrong reason.
    """
    scored = bookkeeping.score_item_with_judge(
        _section("Beata Halassy",
                 "A virologist who treated her own recurrent breast cancer." + BODY_TAIL),
        [])
    assert scored.total == 9
    assert promote_item(scored, "beata-halassy", "person") == \
        door / "person" / "beata-halassy.md"
    assert bookkeeping.grounding_stats()["refused"] == 0


# ── the structural reason: the floor never sees a score ─────────────────────

@pytest.mark.parametrize("total,n,s,r", [(0, 0, 0, 0), (4, 2, 1, 1), (6, 3, 3, 0), (9, 3, 3, 3)])
def test_the_floor_is_indifferent_to_the_score(total, n, s, r, door):
    """
    Grounding is a predicate over (slug, claim, heading, type) and never reads
    the score. Held across the whole range, so a gate that later consulted the
    score would break this.
    """
    item = _section("Items", "Verified against the paper." + BODY_TAIL)
    scored = ScoredItem(item=item, novelty=n, specificity=s, relevance=r, total=total,
                        promote=total >= bookkeeping.PROMOTE_THRESHOLD,
                        candidate_entities=[], scoring_method="heuristic", reasoning={})
    assert promote_item(scored, "beata-halassy", "pattern") is None
