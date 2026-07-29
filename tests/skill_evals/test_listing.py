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


# ---------------------------------------------------------------------------
# defects found by cross-review of PR #113 — each with the shape that produced it
# ---------------------------------------------------------------------------


def test_skill_masses_sees_through_symlinks(tmp_path):
    """THE blocker. `Path.rglob` does not descend into symlinked directories, and a
    skill install root is almost entirely symlinks — 125 of 129 entries under
    ~/.claude/skills. rglob found 3 SKILL.md files there; iterdir finds 128.

    The rglob version measured a population 60% composed of skills that have never
    been listed, while missing 84 of the 146 the roster carries.
    """
    real = tmp_path / "src" / "kg"
    real.mkdir(parents=True)
    (real / "SKILL.md").write_text("---\nname: kg\ndescription: real one\n---\n")
    root = tmp_path / "install"
    root.mkdir()
    (root / "kg").symlink_to(real, target_is_directory=True)

    names = {m.name for m in L.skill_masses([root])}
    assert names == {"kg"}, "a symlinked skill must be counted"


def test_nested_bundles_are_not_counted(tmp_path):
    """`<root>/<skill>/.skills/<sub>` is not a roster entry; counting it inflates
    the total, which is the other half of what rglob got wrong."""
    root = tmp_path / "install"
    top = root / "gstack"
    (top / ".skills" / "plan-tune").mkdir(parents=True)
    (top / "SKILL.md").write_text("---\nname: gstack\ndescription: top\n---\n")
    (top / ".skills" / "plan-tune" / "SKILL.md").write_text(
        "---\nname: plan-tune\ndescription: nested\n---\n")
    assert {m.name for m in L.skill_masses([root])} == {"gstack"}


def test_budget_is_scoped_to_the_roster(tmp_path):
    """A skill on disk that never appears in a listing costs nothing, so folding it
    into the total overstates the overshoot AND puts it on the trim list, where
    removing it would save nothing."""
    root = tmp_path / "install"
    root.mkdir()
    for name, desc in (("listed", "x" * 100), ("never-listed", "y" * 5000)):
        d = root / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n")

    rep = L.budget_report([root], roster=["listed"])
    assert rep["skills"] == 1
    assert rep["on_disk_not_in_roster"] == 1
    assert rep["effective_mass"] < 200
    assert [h["skill"] for h in rep["heaviest"]] == ["listed"]

    unscoped = L.budget_report([root])
    assert unscoped["effective_mass"] > 5000, "control: unscoped still counts everything"


def test_a_roster_skill_missing_from_disk_is_reported(tmp_path):
    root = tmp_path / "install"
    root.mkdir()
    d = root / "here"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: here\ndescription: x\n---\n")
    rep = L.budget_report([root], roster=["here", "gone"])
    assert rep["in_roster_not_on_disk"] == ["gone"]


def test_latest_listing_prefers_the_full_roster_over_an_increment(tmp_path):
    """A session emits an initial full listing then INCREMENTAL 1-skill ones. Taking
    the last attachment reported `0 BARE (0.0%)` on a machine where 110 of 146 are
    bare — a clean bill of health produced by reading the wrong record."""
    f = tmp_path / "66666666-6666-6666-6666-666666666666.jsonl"
    full = {"type": "user", "attachments": [{"type": "skill_listing",
            "names": ["alpha", "beta"], "content": "- alpha: described.\n- beta\n",
            "skillCount": 2, "isInitial": True}]}
    incr = {"type": "user", "attachments": [{"type": "skill_listing",
            "names": ["gamma"], "content": "- gamma: described.\n",
            "skillCount": 1, "isInitial": False}]}
    f.write_text(json.dumps(full) + "\n" + json.dumps(incr) + "\n", encoding="utf-8")

    lst = L.latest_listing(tmp_path)
    assert lst.skill_count == 2
    assert L.classify(lst).bare == ["beta"]


def test_latest_listing_falls_back_to_the_largest_when_no_initial_flag(tmp_path):
    f = tmp_path / "77777777-7777-7777-7777-777777777777.jsonl"
    recs = [
        {"type": "user", "attachments": [{"type": "skill_listing", "names": ["a", "b"],
         "content": "- a: x\n- b\n", "skillCount": 2}]},
        {"type": "user", "attachments": [{"type": "skill_listing", "names": ["c"],
         "content": "- c: y\n", "skillCount": 1}]},
    ]
    f.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    assert L.latest_listing(tmp_path).skill_count == 2


def test_an_unparseable_listing_is_not_a_clean_bill_of_health():
    """R0. A 39,013-char attachment that parsed to zero entries reported
    `0 BARE (0.0%)` with no red condition — absence of parsed entries is absence of
    a MEASUREMENT, not absence of bare skills."""
    lst = L.Listing(names=(), content="garbage\n" * 200, source="t.jsonl")
    cls = L.classify(lst)
    assert cls.states == {}
    reds = L.red_conditions(cls, L.budget_report([]), lst)
    assert reds and reds[0].startswith("R0")
    assert "not a measurement" in reds[0]


def test_a_healthy_listing_does_not_fire_r0():
    """FALSE-POSITIVE control."""
    lst = L.Listing(names=("alpha",), content="- alpha: described.\n", source="t.jsonl")
    reds = L.red_conditions(L.classify(lst), L.budget_report([]), lst)
    assert not any(r.startswith("R0") for r in reds), reds


def test_frontmatter_field_ignores_the_body(tmp_path):
    """`design-taste-frontend` has no `when_to_use` in its frontmatter but does have
    the string on line 872 of its BODY; the whole-file scan charged it 110 phantom
    characters."""
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\nname: x\ndescription: d\n---\n\n# body\n\n"
        'when_to_use: "Landing pages with one strong asset"\n'
    )
    assert L._frontmatter_field(md.read_text(), "when_to_use") == ""


def test_frontmatter_field_reads_a_block_scalar(tmp_path):
    """`p9`, `swapit` and `procurer` all use `when_to_use: |`; taking everything
    after the colon measured the single character `|`, charging 4 instead of 320."""
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\nname: x\ndescription: d\nwhen_to_use: |\n"
        "  first line of the block\n  second line of the block\nother: y\n---\n# body\n"
    )
    got = L._frontmatter_field(md.read_text(), "when_to_use")
    assert "first line of the block" in got and "second line" in got
    assert len(got) > 40, got


# ---------------------------------------------------------------------------
# round-2 verification findings
# ---------------------------------------------------------------------------


def test_a_total_parse_failure_fires_r0_on_a_POPULATED_roster():
    """R0 did not fire for the failure it is named after.

    `classify` defaults every name in the attachment to BARE, so `states` is
    non-empty whenever `names` is — the old `not cls.states` predicate was true only
    for an EMPTY names array (2 of 1,203 real listings). On the REACHABLE shape — the
    CLI changes the line format, so a populated 146-name listing whose descriptions
    all arrived parses to nothing — it reported "146 of 146 BARE", the exact opposite
    diagnosis, with the disclaimer suppressed.
    """
    names = tuple(f"skill{i}" for i in range(146))
    content = "\n".join(f"* skill{i}: a real description that DID reach the model"
                        for i in range(146))
    lst = L.Listing(names=names, content=content, source="fmt-change.jsonl", is_initial=True)
    cls = L.classify(lst)

    assert cls.parsed_entries == 0
    assert cls.count(L.BARE) == 146, "the misleading count is still produced..."
    reds = L.red_conditions(cls, L.budget_report([]), lst)
    assert reds and reds[0].startswith("R0"), "...but R0 must now lead and disclaim it"
    assert "not a measurement" in reds[0]


def test_r0_uses_gte_because_one_bad_line_per_skill_is_the_norm():
    """The canonical total-failure shape is exactly one unreadable line per skill, so
    a strict `>` missed it by one."""
    names = ("a", "b")
    lst = L.Listing(names=names, content="? a: x\n? b: y\n", source="t.jsonl")
    cls = L.classify(lst)
    assert len(cls.unparsed) == len(cls.states) == 2
    assert any(r.startswith("R0") for r in L.red_conditions(cls, L.budget_report([]), lst))


def test_a_healthy_listing_still_does_not_fire_r0():
    """FALSE-POSITIVE control for both R0 branches."""
    lst = L.Listing(names=("a", "b"), content="- a: x\n- b\n", source="t.jsonl")
    cls = L.classify(lst)
    assert cls.parsed_entries == 2
    assert not any(r.startswith("R0") for r in L.red_conditions(cls, L.budget_report([]), lst))


def test_the_affordable_mean_uses_the_ROSTER_as_denominator(tmp_path):
    """22 of 146 listed names are CLI built-ins that exist nowhere on disk, yet 13 of
    them arrived FULL and consumed 21% of the rendered listing. Dividing the cap by
    the measurable 124 gave 315 chars; the listing must fit 146 entries, so an author
    trimming to 315 on that guidance still overflows. Honest value: 267."""
    root = tmp_path / "install"
    root.mkdir()
    d = root / "onlyone"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: onlyone\ndescription: x\n---\n")

    rep = L.budget_report([root], roster=["onlyone"] + [f"builtin{i}" for i in range(9)])
    assert rep["skills"] == 1
    assert rep["roster_size"] == 10
    assert rep["in_roster_not_on_disk_count"] == 9
    assert rep["effective_mass_is_a_floor"] is True
    assert rep["affordable_mean_chars"] == round(L.BUDGET_CHARS / 10)


def test_a_fully_measurable_roster_is_not_flagged_as_a_floor(tmp_path):
    """FALSE-POSITIVE control — the floor caveat must not appear when nothing is missing."""
    root = tmp_path / "install"
    root.mkdir()
    for n in ("a", "b"):
        d = root / n
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {n}\ndescription: x\n---\n")
    rep = L.budget_report([root], roster=["a", "b"])
    assert rep["effective_mass_is_a_floor"] is False
    assert rep["in_roster_not_on_disk_count"] == 0
    assert rep["affordable_mean_chars"] == round(L.BUDGET_CHARS / 2)


def test_the_budget_output_names_the_excluded_skills(tmp_path, capsys):
    """FIX 3 of round 2 shipped with no test, which round-3 review flagged as the one
    hardest to notice regressing: deleting the naming block left the suite green.

    Also pins the two ways the line misled: a trailing ellipsis when the list was
    already complete, and asserting "(CLI built-ins)" as the cause when a mistyped
    --skill-root produces the identical state.
    """
    root = tmp_path / "install"
    root.mkdir()
    d = root / "present"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: present\ndescription: x\n---\n")

    tr = tmp_path / "tr"
    tr.mkdir()
    _write_transcript(
        tr / "88888888-8888-8888-8888-888888888888.jsonl",
        ["present", "builtin-one", "builtin-two"],
        "- present: described.\n- builtin-one: also described.\n- builtin-two\n",
    )

    rc = L.main(["--transcripts", str(tr), "--skill-root", str(root), "--budget"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 listed skill(s) are NOT on disk" in out
    assert "builtin-one" in out and "builtin-two" in out
    assert "builtin-two…" not in out, "no ellipsis when the whole list is shown"
    assert "(CLI built-ins)" not in out, "the cause must not be asserted as fact"
    assert "a FLOOR" in out, "the mass must be labelled a floor when skills are missing"


def test_a_complete_roster_reports_no_missing_line(tmp_path, capsys):
    """FALSE-POSITIVE control — the caveat must be absent when nothing is missing."""
    root = tmp_path / "install"
    root.mkdir()
    for n in ("a", "b"):
        d = root / n
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {n}\ndescription: x\n---\n")
    tr = tmp_path / "tr"
    tr.mkdir()
    _write_transcript(tr / "99999999-9999-9999-9999-999999999999.jsonl",
                      ["a", "b"], "- a: x\n- b: y\n")

    L.main(["--transcripts", str(tr), "--skill-root", str(root), "--budget"])
    out = capsys.readouterr().out
    assert "NOT on disk" not in out
    assert "a FLOOR" not in out
