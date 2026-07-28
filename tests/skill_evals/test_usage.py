"""Tests for scripts/skill_evals/usage.py — the skill-usage measurement.

Every test here pins a decision that, if silently reverted, would make the
ranking wrong in a way nobody would notice — which is the failure mode the whole
eval arc exists to catch. Two are direct regression guards for contamination
traps that materially changed the measured ranking.
"""
from __future__ import annotations

import json

from skill_evals import usage as U


# --- trap 1: workflow artifacts are not sessions -----------------------------

def test_only_uuid_named_transcripts_count_as_sessions():
    """REGRESSION. `agent-*.jsonl` / `journal.jsonl` are workflow subagent
    artifacts living in the same tree. An agent that merely DISCUSSES a skill
    name in a prompt matches the same byte pattern as an invocation.

    Including them inflated a long tail of ~34 skills to a uniform
    '4 invocations / 3 sessions' — a completely fictitious ranking.
    """
    assert U.is_session_transcript("2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl")
    assert U.is_session_transcript("00000000-0000-0000-0000-000000000000.jsonl")

    for artifact in ("agent-a918613d766d16172.jsonl", "journal.jsonl",
                     "agent-ac1d0e608a85deacf.jsonl"):
        assert not U.is_session_transcript(artifact), artifact


def test_session_predicate_requires_the_full_uuid_shape():
    """A loose predicate re-admits the artifacts this exists to exclude."""
    for bad in ("2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.json",   # wrong extension
                "2772651f-25f3-4aee-8b5d.jsonl",                # truncated
                "2772651f25f34aee8b5db44a9cd2dbfb.jsonl",       # no hyphens
                "x2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl",  # prefixed
                "2772651F-25F3-4AEE-8B5D-B44A9CD2DBFB.jsonl"):  # uppercase
        assert not U.is_session_transcript(bad), bad


def test_scan_ignores_workflow_artifacts_end_to_end(tmp_path):
    """The predicate is only worth what the scan does with it."""
    root = tmp_path / "projects" / "proj"
    root.mkdir(parents=True)
    payload = b'{"name":"Skill","input":{"skill":"autonomous"}}\n'
    (root / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(payload)
    (root / "agent-deadbeef.jsonl").write_bytes(payload * 5)
    (root / "journal.jsonl").write_bytes(payload * 5)

    counts, sessions, scanned = U.scan(tmp_path / "projects")
    assert scanned == 1, "workflow artifacts were counted as sessions"
    assert counts["autonomous"] == 1, "invocations leaked from a workflow artifact"
    assert len(sessions["autonomous"]) == 1


# --- trap 2: presence is not coverage ----------------------------------------

def _skill(root, bucket, name, *, cases=None):
    d = root / bucket / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: demo\n---\n#\n", encoding="utf-8")
    if cases is not None:
        (d / "evals").mkdir(exist_ok=True)
        (d / "evals" / "prompts.json").write_text(
            json.dumps({"skill": name, "version": 1, "cases": cases}), encoding="utf-8")
    return d


def test_empty_evals_dir_is_not_coverage(tmp_path):
    """REGRESSION for the BRO-2009 defect, in a second place.

    `skillify_check.py` scored an EMPTY evals/ dir as 'LLM evals: present',
    overstating our coverage 5x. This module must not repeat the conflation.
    """
    sr = tmp_path / "skills"
    d = _skill(sr, "orchestration", "autonomous")
    (d / "evals").mkdir()                                     # bare dir, no file
    assert U.has_evals(sr, "skills/orchestration/autonomous") is False

    (d / "evals" / "prompts.json").write_text(
        json.dumps({"skill": "autonomous", "version": 1, "cases": []}), encoding="utf-8")
    assert U.has_evals(sr, "skills/orchestration/autonomous") is False, "empty cases counted"

    (d / "evals" / "prompts.json").write_text(
        json.dumps({"skill": "autonomous", "version": 1,
                    "cases": [{"id": "a", "prompt": "go", "should_trigger": True}]}),
        encoding="utf-8")
    assert U.has_evals(sr, "skills/orchestration/autonomous") is True


def test_unparseable_prompt_set_is_not_coverage(tmp_path):
    sr = tmp_path / "skills"
    d = _skill(sr, "knowledge", "kg")
    (d / "evals").mkdir()
    (d / "evals" / "prompts.json").write_text("{ not json", encoding="utf-8")
    assert U.has_evals(sr, "skills/knowledge/kg") is False


# --- the headline metric ------------------------------------------------------

def test_coverage_is_invocation_weighted_not_skill_counted(tmp_path):
    """THE point of this module.

    '1 of 84 skills has evals' (1.2%) flatters us. The covered skill was
    `checkit` at 1 invocation while `autonomous` had 72 — so the share of actual
    USAGE covered was 0.8%. Weighting by invocations is the honest reading, and
    a silent switch to skill-counting would make a coverage push look done when
    it had barely started.
    """
    sr = tmp_path / "skills"
    _skill(sr, "orchestration", "autonomous")                                    # 99 inv, NO evals
    _skill(sr, "research", "checkit",
           cases=[{"id": "a", "prompt": "check this out", "should_trigger": True}])  # 1 inv, evals

    tr = tmp_path / "projects" / "p"
    tr.mkdir(parents=True)
    (tr / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(
        b'{"skill":"autonomous"}\n' * 99 + b'{"skill":"checkit"}\n')

    rep = U.build_report(tmp_path / "projects", sr)
    assert rep["owned_invocations"] == 100
    assert rep["skills_with_evals"] == 1
    # skill-counted would be 1/2 = 50%; invocation-weighted is 1/100.
    assert rep["invocation_coverage"] == 0.01, rep["invocation_coverage"]


def test_vendored_skills_are_reported_separately_never_ranked(tmp_path):
    """A skill we do not own cannot be given evals — editing it gets reverted by
    the next `npx skills update`. Mixing it into the ranking would send the next
    coverage push at files we cannot durably change.
    """
    sr = tmp_path / "skills"
    _skill(sr, "orchestration", "autonomous")
    tr = tmp_path / "projects" / "p"
    tr.mkdir(parents=True)
    (tr / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(
        b'{"skill":"autonomous"}\n{"skill":"impeccable"}\n{"skill":"claude-api"}\n')

    rep = U.build_report(tmp_path / "projects", sr)
    assert [r["skill"] for r in rep["ranked"]] == ["autonomous"]
    assert {r["skill"] for r in rep["external_not_ours"]} == {"impeccable", "claude-api"}
    assert rep["owned_invocations"] == 1, "a vendored skill leaked into the owned total"


def test_ranking_is_ordered_by_invocations(tmp_path):
    sr = tmp_path / "skills"
    for b, n in (("orchestration", "autonomous"), ("orchestration", "handoff"), ("knowledge", "kg")):
        _skill(sr, b, n)
    tr = tmp_path / "projects" / "p"
    tr.mkdir(parents=True)
    (tr / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(
        b'{"skill":"kg"}\n' * 2 + b'{"skill":"autonomous"}\n' * 9 + b'{"skill":"handoff"}\n' * 5)
    rep = U.build_report(tmp_path / "projects", sr)
    assert [r["skill"] for r in rep["ranked"]] == ["autonomous", "handoff", "kg"]


def test_missing_transcript_root_exits_nonzero_rather_than_reporting_zero(tmp_path):
    """Fail loudly. 'coverage 0%' and 'I could not find any transcripts' are
    different claims, and silently reporting the first would be the exact
    silent-success shape this arc keeps finding.
    """
    assert U.main(["--transcripts", str(tmp_path / "nope"),
                   "--skills-root", str(tmp_path / "skills")]) == 2


def test_json_mode_emits_parseable_output(tmp_path, capsys):
    sr = tmp_path / "skills"
    _skill(sr, "orchestration", "autonomous")
    tr = tmp_path / "projects" / "p"
    tr.mkdir(parents=True)
    (tr / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(b'{"skill":"autonomous"}\n')
    assert U.main(["--transcripts", str(tmp_path / "projects"),
                   "--skills-root", str(sr), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["owned_invocations"] == 1
    assert payload["ranked"][0]["skill"] == "autonomous"
