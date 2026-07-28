"""Tests for the listing-delivery detector (scripts/skill_evals/listing.py, BRO-2014).

The arc's premise was that a skill's description is what the model sees. It usually
is not: the listing attachment is capped, and three quarters of our skills arrive as
a bare name. This module reads the attachment the model actually received.

The parsing is the delicate part, and it has a known way of being wrong in BOTH
directions — a name character class that includes ``:`` (needed for plugin skills
like ``paper-desktop:code-to-design``) greedily eats the ``name: description``
delimiter and reports every described skill as bare. That produced a false
"everything is bare" reading during the investigation, so it gets its own test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import listing as L  # noqa: E402


def listing(names, content):
    return L.Listing(names=tuple(names), content=content, source="t.jsonl")


# ---------------------------------------------------------------------------
# the root predicate
# ---------------------------------------------------------------------------


def test_described_and_bare_entries_are_told_apart():
    lst = listing(
        ["alpha", "beta"],
        "- alpha: Use when the user wants alpha things.\n- beta\n",
    )
    cls = L.classify(lst)
    assert cls.states == {"alpha": L.FULL, "beta": L.BARE}
    assert cls.bare == ["beta"]


def test_a_plugin_name_containing_a_colon_is_not_read_as_bare():
    """THE parsing bug. A name class that includes ':' — which plugin names force —
    swallows the delimiter and reports every described skill as bare. Anchoring on
    the attachment's own `names` array is what makes this correct."""
    lst = listing(
        ["paper-desktop:code-to-design", "plain"],
        "- paper-desktop:code-to-design: Convert code into a design file.\n"
        "- plain: Ordinary skill.\n",
    )
    cls = L.classify(lst)
    assert cls.states["paper-desktop:code-to-design"] == L.FULL
    assert cls.bare == []


def test_the_longest_matching_name_wins():
    """`ui-ux-pro-max` and `ui-ux-pro-max:ui-ux-pro-max` both exist in the real
    roster; a shortest-match parser attributes the second entry to the first."""
    lst = listing(
        ["ui-ux-pro-max", "ui-ux-pro-max:ui-ux-pro-max"],
        "- ui-ux-pro-max: short one.\n- ui-ux-pro-max:ui-ux-pro-max: the plugin one.\n",
    )
    cls = L.classify(lst)
    assert cls.states["ui-ux-pro-max"] == L.FULL
    assert cls.states["ui-ux-pro-max:ui-ux-pro-max"] == L.FULL


def test_a_dash_line_inside_a_description_is_continuation_not_a_new_entry():
    """Descriptions contain markdown lists. Only a line naming a KNOWN skill opens
    an entry — otherwise a description's own bullet splits it and the remainder is
    attributed to a skill that does not exist."""
    lst = listing(
        ["alpha", "beta"],
        "- alpha: Use when:\n- first thing\n- second thing\n- beta: Another skill.\n",
    )
    cls = L.classify(lst)
    assert cls.states == {"alpha": L.FULL, "beta": L.FULL}
    assert cls.unparsed == []


def test_truncation_is_distinguished_from_a_full_description():
    lst = listing(
        ["alpha", "beta"],
        f"- alpha: a very long description that ran out of room{L.ELLIPSIS}\n"
        "- beta: a short one.\n",
    )
    cls = L.classify(lst)
    assert cls.states["alpha"] == L.TRUNCATED
    assert cls.states["beta"] == L.FULL
    assert cls.truncated == ["alpha"]


def test_a_name_in_the_roster_but_absent_from_the_content_is_bare():
    """The state this module exists to surface: the model got the name and nothing
    else. Counting only rendered entries would silently drop these."""
    lst = listing(["alpha", "ghost"], "- alpha: present.\n")
    cls = L.classify(lst)
    assert cls.states["ghost"] == L.BARE
    assert cls.to_dict()["skills"] == 2


def test_empty_description_after_the_colon_is_bare():
    lst = listing(["alpha"], "- alpha: \n")
    assert L.classify(lst).states["alpha"] == L.BARE


# ---------------------------------------------------------------------------
# reading the attachment out of a transcript
# ---------------------------------------------------------------------------


def _write_transcript(path: Path, names, content, extra_lines=()):
    record = {
        "type": "user",
        "message": {"role": "user", "content": "hi"},
        "attachments": [
            {"type": "skill_listing", "names": list(names),
             "content": content, "skillCount": len(names), "isInitial": True}
        ],
    }
    lines = [json.dumps(record)] + [json.dumps(e) for e in extra_lines]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_listing_is_found_at_any_nesting_depth(tmp_path):
    f = tmp_path / "0dbdfde7-7b47-47e0-82b5-0dbdfde70000.jsonl"
    _write_transcript(f, ["alpha"], "- alpha: described.\n")
    found = L.listings_in(f)
    assert len(found) == 1
    assert found[0].names == ("alpha",)
    assert found[0].skill_count == 1


def test_only_real_session_transcripts_are_read(tmp_path):
    """Workflow subagent artifacts sit in the same tree and carry the same records.
    Reuses usage.is_session_transcript rather than re-implementing the predicate."""
    real = tmp_path / "0dbdfde7-7b47-47e0-82b5-0dbdfde70000.jsonl"
    fake = tmp_path / "agent-a05c676ceffa8bbe3.jsonl"
    journal = tmp_path / "journal.jsonl"
    for p in (real, fake, journal):
        _write_transcript(p, ["alpha"], "- alpha: described.\n")
    names = {p.name for p in L.iter_transcripts(tmp_path)}
    assert names == {real.name}


def test_latest_listing_prefers_the_most_recent_session(tmp_path):
    import os
    import time

    old = tmp_path / "11111111-1111-1111-1111-111111111111.jsonl"
    new = tmp_path / "22222222-2222-2222-2222-222222222222.jsonl"
    _write_transcript(old, ["old"], "- old: stale.\n")
    _write_transcript(new, ["new"], "- new: fresh.\n")
    past = time.time() - 5000
    os.utime(old, (past, past))
    assert L.latest_listing(tmp_path).names == ("new",)


def test_no_transcripts_is_not_a_crash(tmp_path):
    assert L.latest_listing(tmp_path) is None


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------


def _skill(root: Path, name: str, description: str, **fm):
    """Keys are written VERBATIM. An earlier version rewrote ``_`` to ``-`` and so
    emitted ``when-to-use``, which is not the field real skills use (``when_to_use``,
    4 occurrences on disk) — the test then passed on a mass of zero."""
    d = root / name
    d.mkdir(parents=True)
    extra = "".join(f"{k}: {v}\n" for k, v in fm.items())
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra}---\n# body\n",
        encoding="utf-8",
    )


def test_mass_counts_the_whole_rendered_entry(tmp_path):
    _skill(tmp_path, "alpha", "x" * 100)
    masses = L.skill_masses([tmp_path])
    assert len(masses) == 1
    # description + "- alpha: " + newline
    assert masses[0].effective == 100 + len("- alpha: ") + 1


def test_when_to_use_is_counted(tmp_path):
    """Measuring `description` alone undercounts the model-visible surface, and the
    gap grows as more skills adopt the field. Measuring the wrong quantity is how a
    budget report becomes decoration."""
    _skill(tmp_path, "alpha", "x" * 50)
    _skill(tmp_path, "beta", "x" * 50, **{"when_to_use": "y" * 40})
    by_name = {m.name: m for m in L.skill_masses([tmp_path])}
    assert by_name["beta"].effective > by_name["alpha"].effective


def test_a_skill_that_opted_out_costs_nothing(tmp_path):
    """A skill with disable-model-invocation is not in the listing at all, so
    counting it would overstate the overshoot."""
    _skill(tmp_path, "alpha", "x" * 50)
    _skill(tmp_path, "quiet", "x" * 5000, **{"disable-model-invocation": "true"})
    names = {m.name for m in L.skill_masses([tmp_path])}
    assert names == {"alpha"}


def test_budget_report_flags_the_overshoot(tmp_path):
    for i in range(3):
        _skill(tmp_path, f"s{i}", "x" * 400)
    rep = L.budget_report([tmp_path])
    assert rep["skills"] == 3
    assert rep["effective_mass"] > 1200
    assert rep["budget"] == L.BUDGET_CHARS


def test_per_skill_cap_flags_a_description_that_will_be_truncated(tmp_path):
    _skill(tmp_path, "huge", "x" * (L.PER_SKILL_CHARS + 10))
    _skill(tmp_path, "small", "x" * 50)
    rep = L.budget_report([tmp_path])
    assert rep["over_per_skill_cap"] == ["huge"]


# ---------------------------------------------------------------------------
# red conditions
# ---------------------------------------------------------------------------


def test_red_conditions_fire_and_stay_quiet(tmp_path):
    _skill(tmp_path, "alpha", "x" * 50)
    quiet_budget = L.budget_report([tmp_path])
    clean = L.classify(listing(["alpha"], "- alpha: described.\n"))
    assert L.red_conditions(clean, quiet_budget) == []

    bare = L.classify(listing(["alpha", "beta"], "- alpha: described.\n- beta\n"))
    reds = L.red_conditions(bare, quiet_budget)
    assert len(reds) == 1 and reds[0].startswith("R1")


def test_calibration_detects_a_stale_constant(tmp_path, monkeypatch):
    """The constants are measurements and must stay measurements. This mechanism
    earned its keep immediately: its first real run rejected this module's own
    original BUDGET_CHARS (30,000, from a smaller sample) against an observed
    39,013."""
    f = tmp_path / "33333333-3333-3333-3333-333333333333.jsonl"
    _write_transcript(f, ["alpha"], "- alpha: " + "x" * 500 + "\n")
    monkeypatch.setattr(L, "BUDGET_CHARS", 10)
    cal = L.calibrate(tmp_path)
    assert cal["budget_constant_is_stale"] is True
    assert cal["observed_max_content_chars"] > 10

    monkeypatch.setattr(L, "BUDGET_CHARS", 10_000)
    assert L.calibrate(tmp_path)["budget_constant_is_stale"] is False


def test_calibrate_exits_nonzero_on_a_stale_constant(tmp_path, monkeypatch, capsys):
    f = tmp_path / "44444444-4444-4444-4444-444444444444.jsonl"
    _write_transcript(f, ["alpha"], "- alpha: " + "x" * 500 + "\n")
    monkeypatch.setattr(L, "BUDGET_CHARS", 10)
    rc = L.main(["--transcripts", str(tmp_path), "--calibrate"])
    capsys.readouterr()
    assert rc == 1


# ---------------------------------------------------------------------------
# the detector must not become a CI gate
# ---------------------------------------------------------------------------


def test_the_detector_is_advisory(tmp_path):
    """Its input is one machine's ~/.claude/projects, which does not exist on a
    runner — so a CI gate on it would be green by construction, which is the exact
    vacuity this arc exists to hunt. Exit 0 even with red conditions firing."""
    f = tmp_path / "55555555-5555-5555-5555-555555555555.jsonl"
    _write_transcript(f, ["alpha", "beta"], "- alpha: described.\n- beta\n")
    skills = tmp_path / "skills"
    _skill(skills, "alpha", "x" * 50)
    rc = L.main(["--transcripts", str(tmp_path), "--skill-root", str(skills)])
    assert rc == 0


def test_no_listing_anywhere_reports_rather_than_crashes(tmp_path):
    skills = tmp_path / "skills"
    _skill(skills, "alpha", "x" * 50)
    rc = L.main(["--transcripts", str(tmp_path), "--skill-root", str(skills)])
    assert rc == 2  # nothing to classify — distinct from "classified, all fine"
