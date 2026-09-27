"""Grounding floor at the promote door (BRO-2614).

Fixture: tests/fixtures/pr789/entities.json — the 14 new entities of
broomva/workspace#789 as the scheduled synthesis opened it (c051914e1e), plus
the reviewer's rewrite of person/beata-halassy as merged (0cc2d0a91):

  junk (13)  the 12 pages review dropped, and pattern/beata-halassy as
             auto-promoted (claim "Verified against the paper.") — the page the
             reviewer could only keep by rewriting its type and claim.
  kept (2)   pattern/nested-watchdog-inherits-the-skip (merged as-is) and
             person/beata-halassy (the rewrite).

`section_heading` is the heading of the item each junk page was derived from,
re-read from its Layer-2 note by the current ingest; "" where that note no
longer ingests (multimodal-system-one: 8-section cap) and for the kept pages,
whose claims were written by hand, not derived.
"""
import json
from pathlib import Path

import pytest

import bookkeeping
from bookkeeping import (
    RawItem,
    ScoredItem,
    entity_grounding,
    passes_grounding_floor,
    passes_nous_gate,
    promote_item,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pr789" / "entities.json"
ENTITIES = json.loads(FIXTURE.read_text())["entities"]
JUNK = [e for e in ENTITIES if e["verdict"] == "junk"]
KEPT = [e for e in ENTITIES if e["verdict"] == "kept"]

# The ledger's list of what review dropped (~/.config/broomva/fleet/pr-drain-autokg.md).
DROPPED_BY_REVIEW = {
    "concept/computer-programmers", "concept/jacob-coxon",
    "concept/path-towards-autonomous-machine-intelligence", "concept/current-lago",
    "pattern/insane-method", "pattern/instagram-reel",
    "pattern/statisticsmaxxing-knowledge", "pattern/webber-wentzel",
    "project/multimodal-system-one", "project/system-one", "project/via-vercel",
    "tool/jev-judge",
}


def _key(e):
    return f"{e['type']}/{e['slug']}"


def _grounded(e):
    return passes_grounding_floor(e["slug"], e["core_claim"], e["section_heading"], e["type"])


# ── The fixture is what it claims to be ──────────────────────────────────────

def test_fixture_is_the_789_cohort():
    assert len(ENTITIES) == 15
    assert {_key(e) for e in JUNK} == DROPPED_BY_REVIEW | {"pattern/beata-halassy"}
    assert {_key(e) for e in KEPT} == {
        "person/beata-halassy", "pattern/nested-watchdog-inherits-the-skip"}


def test_floor_is_on_by_default():
    assert bookkeeping.GROUNDING_FLOOR == 1


# ── The acceptance test ──────────────────────────────────────────────────────

@pytest.mark.parametrize("e", JUNK, ids=_key)
def test_every_789_junk_page_is_refused(e):
    assert entity_grounding(e["slug"], e["core_claim"], e["section_heading"], e["type"]) == 0
    assert not _grounded(e)


@pytest.mark.parametrize("e", KEPT, ids=_key)
def test_both_kept_789_pages_pass(e):
    """Positive control: a floor that refuses everything also 'refuses the junk'."""
    assert _grounded(e)


# ── Why the floor is not on (n, s, r) ────────────────────────────────────────

def test_nous_axes_cannot_separate_the_789_cohort():
    """The requested shape of fix — a per-axis floor on the Nous scores —
    measured against the same fixture. The scores are note-level: the kept
    person page and two junk pages from its note carry identical triples, so
    no predicate over (n, s, r) can split them."""
    by_key = {_key(e): e["nous"] for e in ENTITIES}
    kept_person = by_key["person/beata-halassy"]
    assert kept_person == by_key["pattern/insane-method"] \
        == by_key["pattern/beata-halassy"] == {"n": 3, "s": 3, "r": 0}

    def axis_floor(nous):  # relevance >= 1 and specificity >= 1
        return passes_nous_gate(**{"novelty": nous["n"], "specificity": nous["s"],
                                   "relevance": nous["r"]}) \
            and nous["r"] >= 1 and nous["s"] >= 1

    assert not axis_floor(kept_person)                       # refuses a kept page
    admitted = {_key(e) for e in JUNK if e["nous"] and axis_floor(e["nous"])}
    assert admitted == {"concept/current-lago", "project/via-vercel",
                        "pattern/webber-wentzel"}            # and admits 3 junk


# ── Predicate properties ─────────────────────────────────────────────────────

def test_heading_that_is_the_entity_grounds_it():
    assert entity_grounding("beata-halassy", "Items shrank 63%.", "Beata Halassy") == 2


def test_heading_that_begins_with_the_entity_grounds_it():
    h = "Beata Halassy: a Croatian virologist's oncolytic-virotherapy case report"
    assert entity_grounding("beata-halassy", h + " Her tumour shrank.", h, "person") == 2
    # the name must LEAD: a title merely containing it does not
    assert entity_grounding("insane-method", "x",
                            "Kurzgesagt on an Insane Method for curing cancer") == 0


def test_slug_lifted_from_a_larger_title_is_not_grounded_by_it():
    # insane-method's heading contains the slug but is a video title, not the entity
    h = 'Layer-2 extract — Kurzgesagt "This Woman Cured Her Cancer with an Insane Method"'
    assert entity_grounding("insane-method", "Ingested 2026-09-15.", h) == 0


def test_heading_prefix_is_stripped_only_when_the_claim_starts_with_it():
    h = '/checkit — "Build a Jev Judge" (Jev-as-judge + Opik tutorial), run live'
    claim = ("/checkit — 'Build a Jev Judge' (Jev-as-judge + Opik tutorial), "
             "run live Eighth X-article ingest on the TypeSafe Jev arc.")
    assert entity_grounding("jev-judge", claim, h) == 0
    # without a recorded heading the same text reads as a claim naming it
    assert entity_grounding("jev-judge", claim, "") == 1


def test_a_short_name_is_named_by_every_word():
    # P20 round 2 (Codex): a head noun alone is a generic collision
    assert entity_grounding("jev-judge", "The TypeSafe Jev arc.", "") == 0
    assert entity_grounding("jev-judge", "A judge that runs nowhere.", "") == 0
    assert entity_grounding("jev-judge", "A judge built on Jev.", "") == 1
    assert entity_grounding("design-review", "We review deployment choices.", "") == 0
    assert entity_grounding("design-review", "Design review caught it twice.", "") == 1


def test_a_person_is_named_by_surname():
    assert entity_grounding("beata-halassy", "Halassy's tumour shrank.", "", "person") == 1
    assert entity_grounding("beata-halassy", "Halassy's tumour shrank.", "", "pattern") == 0
    assert entity_grounding("beata-halassy", "Beata published it.", "", "person") == 0


def test_a_long_claim_shaped_slug_is_named_by_head_and_half():
    slug = "nested-watchdog-inherits-the-skip"
    assert entity_grounding(slug, "A nested arm inherits its skip.", "") == 1
    assert entity_grounding(slug, "A watchdog's skip is silent.", "") == 1    # 2 of 4 + head
    assert entity_grounding(slug, "The skip was silent.", "") == 0            # 1 of 4
    assert entity_grounding(slug, "A nested watchdog inherits it.", "") == 0  # no head


def test_plural_and_possessive_fold():
    assert entity_grounding("agent-key", "Three classes of Agent Keys.", "") == 1
    assert entity_grounding("data-policy", "Data policies changed.", "") == 1


def test_identity_needs_the_whole_word_not_a_prefix():
    # a 5-char prefix stem made corporal ~ corporate (P20 rounds 1-2, Codex)
    assert entity_grounding("corporal-punishment", "The policy changed.",
                            "Corporate Punishment") == 0
    assert entity_grounding("corporal-punishment", "Corporate punishment rose.", "") == 0
    assert entity_grounding("corporal-punishment", "Corporal punishment rose.", "") == 1
    assert entity_grounding("programming-language", "Programmers use a language.", "") == 0


def test_accents_fold():
    assert entity_grounding("maria-nunez", "Núñez published the result.", "", "person") == 1


def test_number_words_do_not_ground():
    assert entity_grounding("system-one", "One of the arms failed.", "") == 0
    assert entity_grounding("system-one", "System One beat chance.", "") == 1


# ── Through the real door ────────────────────────────────────────────────────

@pytest.fixture
def door(tmp_path, monkeypatch):
    entities = tmp_path / "research" / "entities"
    for et in bookkeeping.ENTITY_TYPES:
        (entities / et).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
    # Isolate the grounding floor from the coherence transport: the floor must
    # decide on its own, with no network either way.
    monkeypatch.setenv(bookkeeping.COHERENCE_GATE_ENV, "0")
    bookkeeping.reset_grounding_run_state()
    return entities


def _scored(content, heading=None):
    meta = {} if heading is None else {bookkeeping._SECTION_HEADING_METADATA_KEY: heading}
    item = RawItem(item_id="g0000001", source_id="2026-09-27-grounding-raw",
                   source_type="research", content=content, quote="", author="",
                   timestamp="2026-09-27T00:00:00+00:00", metadata=meta)
    return ScoredItem(item=item, novelty=3, specificity=3, relevance=0, total=6,
                      promote=True, candidate_entities=[], scoring_method="heuristic",
                      reasoning={})


def _section(heading, body):
    """An item exactly as Format-2 ingest builds it."""
    return _scored(f"{heading}\n\n{body}", heading=heading)


BODY_TAIL = (" The team measured it twice against the published figures and"
             " recorded both runs in the attached analysis file.")


def test_door_refuses_a_789_shaped_item(door):
    item = _section("Items", "Verified against the paper." + BODY_TAIL)
    assert promote_item(item, "beata-halassy", "pattern") is None
    assert not (door / "pattern" / "beata-halassy.md").exists()
    assert bookkeeping.grounding_stats()["refused"] == 1


def test_door_refuses_a_heading_derived_claim(door):
    h = '/checkit — "Build a Jev Judge" (Jev-as-judge + Opik tutorial), run live'
    item = _section(h, "Eighth X-article ingest on the TypeSafe Jev arc." + BODY_TAIL)
    assert promote_item(item, "jev-judge", "tool") is None
    assert not (door / "tool" / "jev-judge.md").exists()


def test_door_admits_a_section_about_the_entity(door):
    """Positive control through the door: grounding 2."""
    item = _section("Beata Halassy",
                    "A virologist who treated her own recurrent breast cancer." + BODY_TAIL)
    assert promote_item(item, "beata-halassy", "person") == door / "person" / "beata-halassy.md"
    assert bookkeeping.grounding_stats()["refused"] == 0


def test_door_admits_a_heading_that_begins_with_the_entity(door):
    h = "Beata Halassy: a Croatian virologist's case report"
    item = _section(h, "Her tumour shrank from 2.47 to 0.91 cm3." + BODY_TAIL)
    assert promote_item(item, "beata-halassy", "person") == door / "person" / "beata-halassy.md"


def test_door_admits_a_paragraph_item_naming_the_entity(door):
    """Positive control through the door: grounding 1, no heading recorded."""
    item = _scored("Halassy treated her own recurrent breast cancer with a virus." + BODY_TAIL)
    assert promote_item(item, "beata-halassy", "person") == door / "person" / "beata-halassy.md"


def test_floor_runs_before_the_coherence_call(door, monkeypatch):
    """A refused page never reaches the (fail-open) coherence transport."""
    monkeypatch.setenv(bookkeeping.COHERENCE_GATE_ENV, "1")
    calls = []
    monkeypatch.setattr(bookkeeping, "_coherence_transport",
                        lambda payload: calls.append(payload) or None)
    item = _section("Items", "Verified against the paper." + BODY_TAIL)
    assert promote_item(item, "beata-halassy", "pattern") is None
    assert calls == []


# ── Ingest records the heading the floor strips ──────────────────────────────

@pytest.mark.parametrize("text", [
    # Format-3 (paragraph) note whose frontmatter tries to supply the key
    "---\nsection_heading: Beata Halassy\n---\n\nThe deployment status changed today "
    "and nothing else happened; Beata Halassy appears only in the citations.\n",
    # Format-2 note: frontmatter must not override the real heading either
    "---\nsection_heading: Beata Halassy\n---\n\n# Items\n\nThe deployment status "
    "changed today, measured twice.\nline two.\nline three.\n\n# Other\n\n"
    "another section of text that is long enough to count.\nline two.\nline three.\n",
])
def test_a_source_cannot_forge_the_section_heading(tmp_path, text):
    """P20 round 2 (Codex): the heading can grant grounding 2, so it is reserved."""
    note = tmp_path / "2026-09-27-forged-raw.md"
    note.write_text(text)
    items = bookkeeping.ingest_file(note)
    assert items
    headings = {i.metadata.get(bookkeeping._SECTION_HEADING_METADATA_KEY) for i in items}
    assert "Beata Halassy" not in headings
    item = bookkeeping._make_item("s", "research", "x",
                                  metadata={bookkeeping._SECTION_HEADING_METADATA_KEY: "Forged"})
    assert bookkeeping._SECTION_HEADING_METADATA_KEY not in item.metadata


def test_format2_ingest_records_section_heading():
    text = ("## Beata Halassy\n\nA virologist who treated her own cancer with a virus,"
            " measured over two runs.\nSecond line.\nThird line.\n\n"
            "## Items\n\nVerified against the paper. Both runs recorded in the file.\n"
            "Second line.\nThird line.\n")
    items = bookkeeping._ingest_markdown(text, "2026-09-27-t-raw", "research")
    assert [i.metadata.get(bookkeeping._SECTION_HEADING_METADATA_KEY) for i in items] \
        == ["Beata Halassy", "Items"]


# ── Callers must not count a refusal as a promotion (P20 round 1, Codex) ─────

REFUSED_NOTE = (
    "---\nsource: checkit\n---\n\n"
    "# Items\n\n"
    "Verified against the paper. The case report by Beata Halassy gives tumour "
    "volumes of 2.47 and 0.91 cm3 (63%), measured on 2026-09-15 before and after "
    "the neoadjuvant course, per https://doi.org/10.3390/vaccines12091007.\n"
    "Second line of the section.\nThird line of the section.\n\n"
    # A second section: Format-2 ingest (the one that glues the heading onto
    # the item) only applies to a note with more than one section.
    "# Tooling observation\n\n"
    "the ingest missed a burned-in caption again, third time on this kind of video.\n"
    "a second line here.\na third line here.\n"
)
GROUNDED_NOTE = REFUSED_NOTE.replace(
    "Verified against the paper. The case report by Beata Halassy",
    "Beata Halassy treated her own recurrent cancer with a virus. The case report")


def _pipeline(door, tmp_path, monkeypatch, text):
    notes = tmp_path / "research" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    for old in notes.glob("*.md"):
        old.unlink()
    config = tmp_path / "config"
    monkeypatch.setattr(bookkeeping, "NOTES_DIR", notes)
    monkeypatch.setattr(bookkeeping, "CONFIG_DIR", config)
    monkeypatch.setattr(bookkeeping, "RUN_LOG", config / "run-log.jsonl")
    monkeypatch.setattr(bookkeeping, "STATUS_CACHE", config / "status.json")
    note = notes / "2026-09-27-grounding-raw.md"
    note.write_text(text)
    return note


def _first_item(note):
    items = bookkeeping._ingest_markdown(note.split("---\n", 2)[2],
                                         "2026-09-27-t-raw", "research")
    # Precondition, asserted so this suite cannot silently fall back to the
    # paragraph format (no heading in the item) and test nothing.
    assert items[0].metadata.get(bookkeeping._SECTION_HEADING_METADATA_KEY) == "Items"
    assert items[0].content.startswith("Items\n\n")
    return items[0]


def test_fixture_notes_go_through_format2():
    _first_item(REFUSED_NOTE)
    _first_item(GROUNDED_NOTE)


def test_title_case_run_never_crosses_a_line_break():
    cands = bookkeeping._build_entity_slug_candidates(_first_item(REFUSED_NOTE))
    assert "items-verified" not in cands     # heading + next line's first word
    assert "beata-halassy" in cands


def test_run_pipeline_dry_run_does_not_count_a_grounding_refusal(
        door, tmp_path, monkeypatch):
    _pipeline(door, tmp_path, monkeypatch, REFUSED_NOTE)
    entry = bookkeeping.run_pipeline(dry_run=True, verbose=False)
    assert entry["grounding"]["refused"] >= 1
    assert entry["entities_created"] == 0
    assert entry["items_promoted"] == 0
    # Control: the same note, grounded, IS counted as a would-be create.
    _pipeline(door, tmp_path, monkeypatch, GROUNDED_NOTE)
    entry = bookkeeping.run_pipeline(dry_run=True, verbose=False)
    assert entry["grounding"]["refused"] == 0
    assert entry["entities_created"] >= 1 and entry["items_promoted"] >= 1


def test_cmd_promote_dry_run_does_not_count_a_grounding_refusal(
        door, tmp_path, monkeypatch, capsys):
    import argparse
    note = _pipeline(door, tmp_path, monkeypatch, REFUSED_NOTE)
    bookkeeping.cmd_promote(argparse.Namespace(file=str(note), dry_run=True, verbose=False))
    assert "Done: 0 items promoted" in capsys.readouterr().out
    note = _pipeline(door, tmp_path, monkeypatch, GROUNDED_NOTE)
    bookkeeping.reset_grounding_run_state()
    bookkeeping.cmd_promote(argparse.Namespace(file=str(note), dry_run=True, verbose=False))
    assert "Done: 1 items promoted" in capsys.readouterr().out
