"""Tests for the skill trigger-eval harness (scripts/skill_evals/, BRO-2005).

Every deterministic part of the harness is covered here: prompt-set schema
validation, stream parsing and the two trigger detectors, check-registry
dispatch, trial grading (including the RECOVERED and INVISIBLE anti-vacuity
outcomes), distribution aggregation, threshold/exit-code logic, workspace
isolation, and the replay guard refusing to green on empty fixtures.

No test here calls the live model. That is the point of the Runner seam — but it
is also the risk the harness is built against, so the guards that keep replay
honest are themselves tested (``test_replay_*``), and the live path is covered by
argv construction plus a launch-failure test rather than left unexercised.

Hermetic: every fixture is built in a tmp dir.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import checks as checks_mod  # noqa: E402
from skill_evals import runner as R  # noqa: E402
from skill_evals import transcript as transcript_mod  # noqa: E402
from skill_evals.transcript import Transcript, normalize_skill_name  # noqa: E402

RUNNER_PY = SCRIPTS / "skill_evals" / "runner.py"


# ---------------------------------------------------------------------------
# stream builders — synthetic stream-json matching the shape observed live
# ---------------------------------------------------------------------------


def ev_init(skills=("demo",), **kw):
    ev = {"type": "system", "subtype": "init", "skills": list(skills),
          "cwd": "/tmp/ws", "model": "claude-haiku", "tools": ["Read", "Skill"]}
    ev.update(kw)
    return ev


def ev_text(text):
    return {"type": "assistant", "parent_tool_use_id": None,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def ev_tool_use(name, tool_input, tid="toolu_01", parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"role": "assistant",
                        "content": [{"type": "tool_use", "id": tid, "name": name,
                                     "input": tool_input, "caller": {"type": "direct"}}]}}


def ev_tool_result(tid="toolu_01", command_name="demo", success=True):
    return {"type": "user",
            "message": {"role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": tid,
                                     "content": f"Launching skill: {command_name}"}]},
            "tool_use_result": {"success": success, "commandName": command_name}}


def ev_base_dir(path="/tmp/ws/.claude/skills/demo"):
    return {"type": "user",
            "message": {"role": "user",
                        "content": [{"type": "text", "text": f"Base directory for this skill: {path}"}]}}


def ev_result(text="All done, here is the answer.", is_error=False, cost=0.0202,
              duration=4900, turns=3, denials=None):
    return {"type": "result",
            "subtype": "error_during_execution" if is_error else "success",
            "is_error": is_error, "result": text, "total_cost_usd": cost,
            "duration_ms": duration, "num_turns": turns,
            "permission_denials": denials or []}


def ndjson(*events):
    return "".join(json.dumps(e) + "\n" for e in events)


def triggering_stream(skill="demo", final="Verified the source and wrote docs/finding.md."):
    return ndjson(
        ev_init(skills=(skill,)),
        ev_tool_use("Skill", {"skill": skill, "args": ""}),
        ev_tool_result("toolu_01", skill),
        ev_base_dir(f"/tmp/ws/.claude/skills/{skill}"),
        ev_text(final),
        ev_result(final),
    )


def quiet_stream(skill="demo", final="That is a straightforward fix; here it is."):
    return ndjson(ev_init(skills=(skill,)), ev_text(final), ev_result(final))


def transcript(text, **kw):
    return Transcript.from_ndjson(text, **kw)


# ---------------------------------------------------------------------------
# prompt-set fixtures
# ---------------------------------------------------------------------------


def prompt_set_doc(skill="demo", cases=None):
    if cases is None:
        cases = [
            {"id": "golden-01", "prompt": "here is an artifact, wdyt",
             "should_trigger": True, "origin": "golden",
             "expected_checks": ["final_answer_non_empty"]},
            {"id": "negative-01", "prompt": "just fix the null deref in parser.py",
             "should_trigger": False, "origin": "negative", "expected_checks": ["final_answer_non_empty"]},
        ]
    return {"skill": skill, "version": 1, "notes": "unit fixture", "cases": cases}


def make_skill(tmp: Path, name="demo", bucket="research", with_evals=True) -> Path:
    d = tmp / "skills" / bucket / name
    (d / "references").mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: demo\n---\n# body\n", encoding="utf-8")
    (d / "references" / "notes.md").write_text("ref\n", encoding="utf-8")
    if with_evals:
        (d / "evals").mkdir(parents=True, exist_ok=True)
        (d / "evals" / "prompts.json").write_text(
            json.dumps(prompt_set_doc(name)), encoding="utf-8")
    return d


def case(cid="c1", prompt="p", should_trigger=True, checks=(), origin="golden"):
    return R.Case(id=cid, prompt=prompt, should_trigger=should_trigger,
                  expected_checks=list(checks), origin=origin)


# ===========================================================================
# 1. prompt-set schema validation
# ===========================================================================


def test_valid_prompt_set_has_no_errors():
    errors, _ = R.validate_prompt_set(prompt_set_doc())
    assert errors == []


def test_prompt_set_requires_object():
    errors, _ = R.validate_prompt_set(["not", "an", "object"])
    assert any("JSON object" in e for e in errors)


def test_prompt_set_rejects_wrong_version():
    doc = prompt_set_doc()
    doc["version"] = 2
    errors, _ = R.validate_prompt_set(doc)
    assert any("'version'" in e for e in errors)


def test_prompt_set_rejects_empty_cases():
    doc = prompt_set_doc(cases=[])
    doc["cases"] = []
    errors, _ = R.validate_prompt_set(doc)
    assert any("non-empty list" in e for e in errors)


def test_prompt_set_rejects_duplicate_case_ids():
    c = {"id": "dup", "prompt": "x", "should_trigger": True, "expected_checks": ["final_answer_non_empty"]}
    errors, _ = R.validate_prompt_set(prompt_set_doc(cases=[dict(c), dict(c)]))
    assert any("duplicate case id" in e for e in errors)


def test_prompt_set_rejects_non_boolean_should_trigger():
    errors, _ = R.validate_prompt_set(prompt_set_doc(cases=[
        {"id": "a", "prompt": "x", "should_trigger": "yes", "expected_checks": ["final_answer_non_empty"]}]))
    assert any("'should_trigger'" in e for e in errors)


def test_prompt_set_rejects_unknown_check_id():
    errors, _ = R.validate_prompt_set(prompt_set_doc(cases=[
        {"id": "a", "prompt": "x", "should_trigger": True,
         "expected_checks": ["no_such_check"]}]))
    assert any("unknown check id" in e and "no_such_check" in e for e in errors)


def test_prompt_set_rejects_a_case_with_no_expected_checks():
    """B2: emptying expected_checks was the one edit that gutted a case silently.

    MEASURED before this error existed: emptying negative-05's expected_checks, and
    then ALL SIX negatives', left ``--validate-only`` printing "prompt set OK" at
    exit 0. A case with no assertions rests entirely on the runner's trigger /
    non-trigger control flow, which is precisely what a near-miss is supposed to be
    more than.
    """
    for expected in ([], None):
        raw = {"id": "a", "prompt": "x", "should_trigger": True}
        if expected is not None:
            raw["expected_checks"] = expected
        errors, _ = R.validate_prompt_set(prompt_set_doc(cases=[raw]))
        assert any("'expected_checks' is empty" in e for e in errors), (
            f"a case with expected_checks={expected!r} validated clean: {errors}")


def test_parse_prompt_set_raises_on_a_case_with_no_expected_checks():
    """Enforced at the parse boundary too, so every loader inherits it."""
    with pytest.raises(R.PromptSetError, match="'expected_checks' is empty"):
        R.parse_prompt_set(prompt_set_doc(cases=[
            {"id": "a", "prompt": "x", "should_trigger": True, "expected_checks": []}]))


def test_prompt_set_accepts_a_declared_artifact_alias():
    """FALSE-POSITIVE PROOF: a real alias must not be rejected by the noise guard."""
    errors, _ = R.validate_prompt_set(prompt_set_doc(cases=[
        {"id": "a", "prompt": "https://x.com/u/status/2079165300625330317 thoughts?",
         "should_trigger": True, "expected_checks": ["final_answer_non_empty"],
         "artifact_aliases": ["https://x.com/i/article/2079141496981184512"]},
        {"id": "b", "prompt": "unrelated", "should_trigger": False,
         "expected_checks": ["final_answer_non_empty"]}]))
    assert errors == []


def test_prompt_set_rejects_an_artifact_alias_that_scopes_nothing():
    """The alias field is additive, not a hole: an alias must carry a real token."""
    errors, _ = R.validate_prompt_set(prompt_set_doc(cases=[
        {"id": "a", "prompt": "x", "should_trigger": True,
         "expected_checks": ["final_answer_non_empty"],
         "artifact_aliases": ["https://github.com/"]}]))
    assert any("yields no distinctive token" in e for e in errors)


def test_prompt_set_rejects_non_string_artifact_aliases():
    errors, _ = R.validate_prompt_set(prompt_set_doc(cases=[
        {"id": "a", "prompt": "x", "should_trigger": True,
         "expected_checks": ["final_answer_non_empty"], "artifact_aliases": [7]}]))
    assert any("'artifact_aliases' must be a list of strings" in e for e in errors)


def test_prompt_set_warns_when_prompt_contains_literal_skill_name():
    _, warnings = R.validate_prompt_set(prompt_set_doc(cases=[
        {"id": "a", "prompt": "run the demo skill on this", "should_trigger": True,
         "expected_checks": ["final_answer_non_empty"]},
        {"id": "b", "prompt": "unrelated", "should_trigger": False, "expected_checks": ["final_answer_non_empty"]}]))
    assert any("name-matching" in w for w in warnings)


def test_prompt_set_warns_when_no_negative_cases():
    errors, warnings = R.validate_prompt_set(prompt_set_doc(cases=[
        {"id": "a", "prompt": "x", "should_trigger": True, "expected_checks": ["final_answer_non_empty"]}]))
    assert any("no negative cases" in w for w in warnings)
    assert errors == []  # a positives-only suite still measures something


def test_prompt_set_rejects_a_suite_with_no_positive_cases():
    """BLOCKER: negatives-only is a perfect score for a skill that can never fire."""
    errors, _ = R.validate_prompt_set(prompt_set_doc(cases=[
        {"id": "n1", "prompt": "fix the null deref", "should_trigger": False,
         "expected_checks": ["final_answer_non_empty"]},
        {"id": "n2", "prompt": "rename this variable", "should_trigger": False,
         "expected_checks": ["final_answer_non_empty"]}]))
    assert any("no positive cases" in e for e in errors)


def test_parse_prompt_set_raises_on_a_negatives_only_suite():
    """The error is enforced at the parse boundary, not only in the validator."""
    with pytest.raises(R.PromptSetError, match="no positive cases"):
        R.parse_prompt_set(prompt_set_doc(cases=[
            {"id": "n1", "prompt": "x", "should_trigger": False, "expected_checks": ["final_answer_non_empty"]}]))


# ---------------------------------------------------------------------------
# artifact fingerprinting (the fixture <-> SKILL.md binding)
# ---------------------------------------------------------------------------


def test_parse_frontmatter_description_handles_plain_and_folded_forms():
    plain = "---\nname: d\ndescription: one two three\n---\nbody\n"
    folded = "---\nname: d\ndescription: >\n  one two\n  three\n---\nbody\n"
    literal = "---\nname: d\ndescription: |\n  one two\n  three\nother: x\n---\nbody\n"
    assert R.parse_frontmatter_description(plain) == "one two three"
    assert R.parse_frontmatter_description(folded) == "one two three"
    assert R.parse_frontmatter_description(literal) == "one two three"


def test_parse_frontmatter_description_ignores_body_and_nested_keys():
    assert R.parse_frontmatter_description("# no frontmatter\ndescription: x\n") == ""
    nested = "---\nname: d\nmeta:\n  description: nested\ndescription: real one\n---\n"
    assert R.parse_frontmatter_description(nested) == "real one"


def test_skill_fingerprint_moves_when_the_description_moves(tmp_path):
    skill_dir = make_skill(tmp_path)
    before = R.skill_fingerprint(skill_dir)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: something else entirely\n---\n# body\n", encoding="utf-8")
    after = R.skill_fingerprint(skill_dir)
    assert before["description_sha256"] != after["description_sha256"]
    assert before["skill_md_sha256"] != after["skill_md_sha256"]


def test_skill_fingerprint_description_hash_survives_a_pure_rewrap(tmp_path):
    """Re-flowing the same words is not a description change; the body hash still moves."""
    skill_dir = make_skill(tmp_path)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: alpha beta gamma\n---\n# body\n", encoding="utf-8")
    a = R.skill_fingerprint(skill_dir)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: >\n  alpha beta\n  gamma\n---\n# body\n", encoding="utf-8")
    b = R.skill_fingerprint(skill_dir)
    assert a["description_sha256"] == b["description_sha256"]
    assert a["skill_md_sha256"] != b["skill_md_sha256"]


def test_skill_fingerprint_refuses_a_skill_with_no_skill_md(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(R.SkillArtifactError, match="no SKILL.md"):
        R.skill_fingerprint(tmp_path / "empty")


def test_skill_fingerprint_refuses_a_skill_with_no_description(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: demo\n---\n# body\n", encoding="utf-8")
    with pytest.raises(R.SkillArtifactError, match="no frontmatter 'description:'"):
        R.skill_fingerprint(d)


def test_parse_prompt_set_raises_on_errors():
    with pytest.raises(R.PromptSetError):
        R.parse_prompt_set({"skill": "", "version": 9, "cases": []})


def test_load_prompt_set_roundtrip(tmp_path):
    p = tmp_path / "prompts.json"
    p.write_text(json.dumps(prompt_set_doc()), encoding="utf-8")
    ps = R.load_prompt_set(p)
    assert ps.skill == "demo"
    assert [c.id for c in ps.cases] == ["golden-01", "negative-01"]
    assert len(ps.positives) == 1 and len(ps.negatives) == 1


def test_load_prompt_set_reports_bad_json(tmp_path):
    p = tmp_path / "prompts.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(R.PromptSetError, match="not valid JSON"):
        R.load_prompt_set(p)


def test_find_skill_dir_walks_buckets(tmp_path):
    d = make_skill(tmp_path, name="demo", bucket="research")
    assert R.find_skill_dir(tmp_path / "skills", "demo") == d


def test_find_skill_dir_raises_when_absent(tmp_path):
    (tmp_path / "skills").mkdir()
    with pytest.raises(R.PromptSetError, match="no skill named"):
        R.find_skill_dir(tmp_path / "skills", "ghost")


# ===========================================================================
# 2. transcript parsing + trigger detectors
# ===========================================================================


def test_detector_a_assistant_tool_use():
    t = transcript(ndjson(ev_init(), ev_tool_use("Skill", {"skill": "demo"}), ev_result()))
    assert t.skill_invocations() == ["demo"]
    assert t.triggered("demo") is True


def test_detector_b_tool_use_result_alone():
    t = transcript(ndjson(ev_init(), ev_tool_result("toolu_9", "demo"), ev_result()))
    assert t.skill_launches() == ["demo"]
    assert t.triggered("demo") is True


def test_detector_b_ignores_failed_launch():
    t = transcript(ndjson(ev_init(), ev_tool_result("toolu_9", "demo", success=False), ev_result()))
    assert t.skill_launches() == []
    assert t.triggered("demo") is False


def test_no_trigger_when_skill_never_fires():
    assert transcript(quiet_stream()).triggered("demo") is False


def test_trigger_matching_is_case_and_namespace_insensitive():
    t = transcript(ndjson(ev_init(), ev_tool_use("Skill", {"skill": "plugin:Demo"}), ev_result()))
    assert t.triggered("demo") is True


def test_normalize_skill_name():
    assert normalize_skill_name(" Bstack:KG ") == "kg"
    assert normalize_skill_name("checkit") == "checkit"


def test_roster_precheck_matches_plugin_namespaced_entries():
    """A plugin-provided skill lists as 'plugin:name' — that must not read INVISIBLE."""
    stream = ndjson(ev_init(skills=("plugin:demo",)),
                    ev_tool_use("Skill", {"skill": "plugin:demo"}),
                    ev_tool_result("toolu_01", "plugin:demo"),
                    ev_result("A complete and correct final answer for this case."))
    r = R.grade_trial(case(should_trigger=True, checks=["final_answer_non_empty"]),
                      transcript(stream), "demo")
    assert r.outcome == R.PASS


def test_parser_tolerates_unknown_event_types_and_bad_lines():
    text = (
        json.dumps(ev_init()) + "\n"
        + '{"type":"rate_limit_event","x":1}\n'
        + "this is not json at all\n"
        + json.dumps({"type": "system", "subtype": "thinking_tokens"}) + "\n"
        + json.dumps(ev_tool_use("Skill", {"skill": "demo"})) + "\n"
        + json.dumps(ev_result()) + "\n"
    )
    t = transcript(text)
    assert t.parse_errors == 1
    assert t.triggered("demo") is True


def test_skill_roster_none_when_init_lacks_skills_array():
    t = transcript(ndjson({"type": "system", "subtype": "init", "cwd": "/tmp"}, ev_result()))
    assert t.skill_roster() is None


def test_result_metadata_surfaced():
    t = transcript(triggering_stream())
    assert t.cost_usd == pytest.approx(0.0202)
    assert t.duration_ms == 4900
    assert t.num_turns == 3
    assert t.is_error is False


def test_is_error_when_result_missing():
    t = transcript(ndjson(ev_init(), ev_text("hi")))
    assert t.is_error is True
    assert "no result event" in t.error_reason


def test_base_dir_proves_which_copy_loaded():
    t = transcript(triggering_stream())
    assert t.skill_base_dirs() == ["/tmp/ws/.claude/skills/demo"]


def test_read_skill_content_detects_disk_recovery():
    t = transcript(ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": "/tmp/ws/.claude/skills/demo/SKILL.md"}),
        ev_result("I read the file and did the thing."),
    ))
    assert t.read_skill_content("demo") is True


def test_read_skill_content_false_for_unrelated_reads():
    t = transcript(ndjson(
        ev_init(), ev_tool_use("Read", {"file_path": "/tmp/ws/notes.txt"}), ev_result()))
    assert t.read_skill_content("demo") is False


def test_output_text_excludes_tool_results():
    """Checks must grade the agent's output, not SKILL.md echoed back by a tool."""
    t = transcript(ndjson(
        ev_init(),
        ev_tool_result("toolu_01", "demo"),
        ev_text("my own words"),
        ev_result("my own words"),
    ))
    assert "Launching skill" not in t.output_text()
    assert "my own words" in t.output_text()


# ===========================================================================
# 3. check-registry dispatch
# ===========================================================================


def ctx_for(stream_text, skill="demo", expected=()):
    return checks_mod.CheckContext(
        case={"id": "c", "prompt": "p", "should_trigger": True},
        skill=skill,
        transcript=transcript(stream_text),
    )


def test_registry_is_populated_and_callable():
    assert "skill_triggered" in checks_mod.CHECK_REGISTRY
    assert all(callable(fn) for fn in checks_mod.CHECK_REGISTRY.values())


def test_run_checks_dispatches_by_id():
    results = checks_mod.run_checks(["skill_triggered", "final_answer_non_empty"],
                                    ctx_for(triggering_stream()))
    assert [r.check_id for r in results] == ["skill_triggered", "final_answer_non_empty"]
    assert all(r.passed for r in results)


def test_run_checks_fails_loudly_on_unknown_id():
    (res,) = checks_mod.run_checks(["nope"], ctx_for(triggering_stream()))
    assert res.passed is False
    assert "unknown check id" in res.detail


def test_run_checks_treats_a_raising_check_as_failure(monkeypatch):
    def boom(ctx):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(checks_mod.CHECK_REGISTRY, "boom", boom)
    (res,) = checks_mod.run_checks(["boom"], ctx_for(triggering_stream()))
    assert res.passed is False
    assert "kaboom" in res.detail


def test_unknown_checks_helper():
    assert checks_mod.unknown_checks(["skill_triggered", "ghost"]) == ["ghost"]


def test_check_final_answer_non_empty_rejects_stub():
    ctx = ctx_for(ndjson(ev_init(), ev_result("ok")))
    assert checks_mod.CHECK_REGISTRY["final_answer_non_empty"](ctx).passed is False


def test_check_no_permission_denials():
    ok = ctx_for(ndjson(ev_init(), ev_result("fine")))
    bad = ctx_for(ndjson(ev_init(), ev_result("fine", denials=[{"tool": "Bash"}])))
    assert checks_mod.CHECK_REGISTRY["no_permission_denials"](ok).passed is True
    assert checks_mod.CHECK_REGISTRY["no_permission_denials"](bad).passed is False


def test_check_mentions_source_verification():
    yes = ctx_for(ndjson(ev_init(), ev_result("I verified the claim against the primary source.")))
    no = ctx_for(ndjson(ev_init(), ev_result("Cool project, seems useful and modern.")))
    fn = checks_mod.CHECK_REGISTRY["mentions_source_verification"]
    assert fn(yes).passed is True
    assert fn(no).passed is False


def test_check_produces_ranked_next_steps_needs_enumeration():
    yes = ctx_for(ndjson(ev_init(), ev_result(
        "Next steps:\n1. wire the runner\n2. record fixtures\n3. flip the gate")))
    no = ctx_for(ndjson(ev_init(), ev_result("You could probably do something about it later.")))
    fn = checks_mod.CHECK_REGISTRY["produces_ranked_next_steps"]
    assert fn(yes).passed is True
    assert fn(no).passed is False


def test_check_no_clarifying_question_bounced_back():
    fn = checks_mod.CHECK_REGISTRY["no_clarifying_question_bounced_back"]
    bounced = ctx_for(ndjson(ev_init(), ev_result("Which repo did you mean, and what output do you want?")))
    answered = ctx_for(ndjson(ev_init(), ev_result(
        "The repo is a Rust workspace; here is how it maps onto our runner, plus what I would change.")))
    assert fn(bounced).passed is False
    assert fn(answered).passed is True


def test_check_documents_finding_accepts_tool_or_text_evidence():
    fn = checks_mod.CHECK_REGISTRY["documents_finding"]
    by_tool = ctx_for(ndjson(ev_init(), ev_tool_use("Write", {"file_path": "/x/note.md"}), ev_result("ok")))
    by_text = ctx_for(ndjson(ev_init(), ev_result("Filed the finding at research/notes/2026-07-28-x.md")))
    neither = ctx_for(ndjson(ev_init(), ev_result("Interesting, that is all.")))
    assert fn(by_tool).passed is True
    assert fn(by_text).passed is True
    assert fn(neither).passed is False


# -- MAJOR: outcome checks must read tool INPUTS, not tool names --------------

BLAND = "All done, here is the answer to the question you asked me about that."

INPUT_BLIND_CHECKS = [
    "ingests_full_artifact_not_metadata",
    "walks_repo_tree_and_canonical_files",
    "documents_finding",
]


def test_a_transcript_whose_only_tool_call_is_echo_hi_fails_every_outcome_check():
    """The proven vacuity: tool-NAME checks collapse into 'called any tool at all'."""
    ctx = ctx_for(ndjson(ev_init(), ev_tool_use("Bash", {"command": "echo hi"}), ev_result(BLAND)))
    for res in checks_mod.run_checks(INPUT_BLIND_CHECKS, ctx):
        assert res.passed is False, f"{res.check_id} still passes on `echo hi`: {res.detail}"


def test_documents_finding_rejects_a_write_to_a_non_document_path():
    fn = checks_mod.CHECK_REGISTRY["documents_finding"]
    unrelated = ctx_for(ndjson(ev_init(),
                               ev_tool_use("Edit", {"file_path": "/x/unrelated.txt"}),
                               ev_result(BLAND)))
    doc = ctx_for(ndjson(ev_init(),
                         ev_tool_use("Edit", {"file_path": "/x/research/finding.md"}),
                         ev_result(BLAND)))
    assert fn(unrelated).passed is False
    assert fn(doc).passed is True


def test_reading_the_skills_own_file_never_counts_as_ingesting_the_artifact():
    """Resolves the contradiction: this exact Read is what DEFINES the RECOVERED leak."""
    stream = ndjson(ev_init(),
                    ev_tool_use("Read", {"file_path": "/tmp/ws/.claude/skills/demo/SKILL.md"}),
                    ev_result(BLAND))
    ctx = ctx_for(stream)
    assert transcript(stream).read_skill_content("demo") is True
    for res in checks_mod.run_checks(INPUT_BLIND_CHECKS, ctx):
        assert res.passed is False, f"{res.check_id} counted the SKILL.md read as evidence"


def test_real_artifact_tool_use_still_passes():
    """The tightening must not turn every genuine run red."""
    stream = ndjson(
        ev_init(),
        ev_tool_use("WebFetch", {"url": "https://arxiv.org/abs/2602.12670"}, tid="t1"),
        ev_tool_use("Bash", {"command": "ls -la src/"}, tid="t2"),
        ev_tool_use("Write", {"file_path": "research/notes/2026-07-28-x.md"}, tid="t3"),
        ev_result(BLAND),
    )
    for res in checks_mod.run_checks(INPUT_BLIND_CHECKS, ctx_for(stream)):
        assert res.passed is True, f"{res.check_id} rejected genuine evidence: {res.detail}"


def test_bash_evidence_requires_a_command_that_touches_something():
    fetch = checks_mod.CHECK_REGISTRY["ingests_full_artifact_not_metadata"]
    walk = checks_mod.CHECK_REGISTRY["walks_repo_tree_and_canonical_files"]
    curl = ctx_for(ndjson(ev_init(),
                          ev_tool_use("Bash", {"command": "curl -sL https://example.com/p.pdf"}),
                          ev_result(BLAND)))
    noop = ctx_for(ndjson(ev_init(),
                          ev_tool_use("Bash", {"command": "true"}),
                          ev_result(BLAND)))
    find = ctx_for(ndjson(ev_init(),
                          ev_tool_use("Bash", {"command": "find . -name '*.rs'"}),
                          ev_result(BLAND)))
    assert fetch(curl).passed is True
    assert fetch(noop).passed is False
    assert walk(find).passed is True
    assert walk(noop).passed is False


def test_judge_seam_raises_rather_than_stubbing_a_pass():
    spec = checks_mod.JudgeSpec(check_id="engages_with_argument", rubric="does it engage?")
    with pytest.raises(NotImplementedError):
        checks_mod.make_judge_check(spec)
    assert "engages_with_argument" not in checks_mod.CHECK_REGISTRY
    assert checks_mod.JUDGE_SCHEMA["required"] == ["passed", "confidence", "evidence", "reasoning"]


# ===========================================================================
# 4. grading
# ===========================================================================


def test_grade_positive_pass():
    r = R.grade_trial(case(should_trigger=True, checks=["final_answer_non_empty"]),
                      transcript(triggering_stream()), "demo")
    assert r.outcome == R.PASS
    assert r.triggered is True
    assert r.cost_usd == pytest.approx(0.0202)


def test_grade_positive_fail_when_never_triggers():
    r = R.grade_trial(case(should_trigger=True), transcript(quiet_stream()), "demo")
    assert r.outcome == R.FAIL
    assert "did not trigger" in r.detail


def test_grade_positive_pass_ignores_which_turn_it_fired_on():
    """Outcomes, not paths: firing on turn 5 is worth exactly as much as turn 1."""
    late = ndjson(
        ev_init(), ev_text("thinking"), ev_tool_use("Grep", {"pattern": "x"}),
        ev_text("still thinking"), ev_tool_use("Skill", {"skill": "demo"}, tid="toolu_09"),
        ev_tool_result("toolu_09", "demo"), ev_result("A complete and correct final answer here."),
    )
    r = R.grade_trial(case(should_trigger=True, checks=["final_answer_non_empty"]),
                      transcript(late), "demo")
    assert r.outcome == R.PASS


def test_grade_recovered_when_skill_read_off_disk():
    leaked = ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": "/tmp/ws/.claude/skills/demo/SKILL.md"}),
        ev_result("I followed the procedure in the file and produced the answer."),
    )
    r = R.grade_trial(case(should_trigger=True), transcript(leaked), "demo")
    assert r.outcome == R.RECOVERED
    assert r.passed is False


def test_grade_invisible_when_skill_absent_from_roster():
    stream = ndjson(ev_init(skills=("other",)), ev_result("nope"))
    r = R.grade_trial(case(should_trigger=True), transcript(stream), "demo")
    assert r.outcome == R.INVISIBLE


def test_grade_invisible_also_guards_negative_cases():
    """A negative that 'passed' because the skill never loaded is a vacuous pass."""
    stream = ndjson(ev_init(skills=("other",)), ev_result("answered directly"))
    r = R.grade_trial(case(should_trigger=False), transcript(stream), "demo")
    assert r.outcome == R.INVISIBLE


def test_an_absent_by_design_arm_does_not_score_invisible():
    """An absent-by-design arm must not be scored as a visibility bug.

    UPDATED BY BRO-2006. This used to assert PASS on a NEGATIVE case, which was the
    seam behaving as a skip switch — and a negative in the absent arm asserts
    nothing at all, since an uninstalled skill cannot over-trigger. It is now
    NOT_COMPARABLE, which is excluded from the graded count rather than counted as
    a structural sweep.
    """
    stream = ndjson(ev_init(skills=("other",)), ev_result("answered without the skill"))
    r = R.grade_trial(case(should_trigger=False), transcript(stream), "demo", expect_visible=False)
    assert r.outcome == R.NOT_COMPARABLE
    assert r.outcome in R.NON_PASS_ERRORS


def test_a_positive_in_the_absent_arm_is_graded_on_outcome_only():
    stream = ndjson(ev_init(skills=("other",)),
                    ev_text("Here is a complete answer."),
                    ev_result("Here is a complete answer."))
    r = R.grade_trial(
        case(should_trigger=True, checks=["final_answer_non_empty"]),
        transcript(stream), "demo", expect_visible=False,
    )
    assert r.outcome == R.PASS
    assert "outcome-only" in r.detail


def test_a_trigger_dependent_check_is_skipped_not_failed_in_the_absent_arm():
    """Counting it failed zeroes the baseline (lift too high — the original
    vacuity); counting it passed inflates it (lift too low, so a load-bearing skill
    reads as absorbed). It is recorded with passed=None."""
    answer = "The parser returns None on an empty buffer; guard it and add a test."
    stream = ndjson(ev_init(skills=("other",)), ev_text(answer), ev_result(answer))
    r = R.grade_trial(
        case(should_trigger=True, checks=["skill_triggered", "final_answer_non_empty"]),
        transcript(stream), "demo", expect_visible=False,
    )
    assert r.outcome == R.PASS
    by_id = {c["check_id"]: c for c in r.checks}
    assert by_id["skill_triggered"]["passed"] is None
    assert by_id["skill_triggered"]["skipped"] is True
    assert by_id["final_answer_non_empty"]["passed"] is True


def test_a_skill_that_leaks_into_the_baseline_is_not_a_zero_lift_result():
    """THE contamination guard. Before BRO-2006 expect_visible=False asserted
    NOTHING about visibility, so a leaked skill scored as an ordinary baseline
    result and the lift came out at zero — indistinguishable from absorption, i.e.
    a recommendation to delete a load-bearing skill."""
    stream = ndjson(ev_init(skills=("demo",)), ev_result("answered"))
    r = R.grade_trial(case(should_trigger=True), transcript(stream), "demo", expect_visible=False)
    assert r.outcome == R.LEAKED
    assert r.outcome in R.NON_PASS_ERRORS

    fired = R.grade_trial(
        case(should_trigger=True), transcript(triggering_stream()), "demo", expect_visible=False)
    assert fired.outcome == R.LEAKED


def test_grade_negative_fails_on_over_trigger():
    r = R.grade_trial(case(should_trigger=False), transcript(triggering_stream()), "demo")
    assert r.outcome == R.FAIL
    assert "over-triggered" in r.detail


def test_grade_negative_passes_when_quiet():
    r = R.grade_trial(case(should_trigger=False), transcript(quiet_stream()), "demo")
    assert r.outcome == R.PASS


def test_grade_fail_when_triggered_but_checks_fail():
    stream = ndjson(ev_init(), ev_tool_use("Skill", {"skill": "demo"}),
                    ev_tool_result("toolu_01", "demo"), ev_result("ok"))
    r = R.grade_trial(case(should_trigger=True, checks=["final_answer_non_empty"]),
                      transcript(stream), "demo")
    assert r.outcome == R.FAIL
    assert "final_answer_non_empty" in r.detail
    assert r.triggered is True


def test_grade_error_on_empty_transcript():
    r = R.grade_trial(case(), Transcript.from_ndjson("", exit_code=1, stderr="boom"), "demo")
    assert r.outcome == R.ERROR


def test_grade_error_when_cli_reports_failure():
    stream = ndjson(ev_init(), ev_result("Not logged in", is_error=True))
    r = R.grade_trial(case(), transcript(stream), "demo")
    assert r.outcome == R.ERROR
    assert "Not logged in" in r.detail


def test_grade_error_when_stream_shape_changes():
    """No 'skills' array means detection cannot be trusted — fail loudly, not quietly."""
    stream = ndjson({"type": "system", "subtype": "init", "cwd": "/tmp"}, ev_result("hi"))
    r = R.grade_trial(case(), transcript(stream), "demo")
    assert r.outcome == R.ERROR
    assert "stream shape" in r.detail


# ===========================================================================
# 5. distribution aggregation
# ===========================================================================


def case_result(cid, should_trigger, outcomes, origin="golden"):
    cr = R.CaseResult(case_id=cid, should_trigger=should_trigger, origin=origin)
    for i, outcome in enumerate(outcomes, start=1):
        cr.trials.append(R.TrialResult(case_id=cid, trial=i, outcome=outcome,
                                       cost_usd=0.02, duration_ms=5000))
    return cr


def test_case_pass_rate_is_a_distribution_not_a_verdict():
    cr = case_result("c", True, [R.PASS, R.PASS, R.FAIL])
    assert cr.trial_count == 3
    assert cr.pass_count == 2
    assert cr.pass_rate == pytest.approx(2 / 3)
    assert cr.outcome_counts == {R.PASS: 2, R.FAIL: 1}


def test_zero_trials_is_never_a_pass():
    cr = R.CaseResult(case_id="c", should_trigger=True, origin="golden")
    assert cr.pass_rate == 0.0


def test_aggregate_splits_positives_and_negatives():
    agg = R.aggregate([
        case_result("p1", True, [R.PASS, R.PASS, R.PASS]),
        case_result("p2", True, [R.PASS, R.FAIL, R.FAIL]),
        case_result("n1", False, [R.PASS, R.PASS, R.FAIL], origin="negative"),
    ], case_threshold=0.6)
    assert agg["cases"] == 3
    assert agg["trials"] == 9
    assert agg["passes"] == 6
    assert agg["trial_pass_rate"] == pytest.approx(6 / 9, abs=1e-4)
    assert agg["positive"]["pass_rate"] == pytest.approx(4 / 6, abs=1e-4)
    assert agg["negative"]["pass_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert agg["cases_at_threshold"] == 2  # p2 is at 0.33
    assert agg["outcomes"] == {R.PASS: 6, R.FAIL: 3}


def test_aggregate_counts_errors_and_costs():
    agg = R.aggregate([case_result("p1", True, [R.PASS, R.ERROR, R.INVISIBLE])])
    assert agg["errors"] == 2
    assert agg["total_cost_usd"] == pytest.approx(0.06)
    assert agg["mean_duration_ms"] == 5000


def test_aggregate_of_nothing_is_empty_not_green():
    agg = R.aggregate([])
    assert agg["trials"] == 0
    assert agg["trial_pass_rate"] == 0.0
    assert R.decide_exit_code(agg, 0.0) == R.EXIT_FIXTURES


# ===========================================================================
# 6. threshold / exit-code logic
# ===========================================================================


def test_exit_zero_at_or_above_threshold():
    agg = R.aggregate([case_result("p", True, [R.PASS, R.PASS, R.PASS, R.PASS, R.FAIL])])
    assert agg["trial_pass_rate"] == pytest.approx(0.8)
    assert R.decide_exit_code(agg, 0.80) == R.EXIT_OK


def test_exit_one_below_threshold():
    agg = R.aggregate([case_result("p", True, [R.PASS, R.FAIL, R.FAIL])])
    assert R.decide_exit_code(agg, 0.80) == R.EXIT_BELOW_THRESHOLD


def test_errors_fail_the_run_even_above_threshold():
    agg = R.aggregate([case_result("p", True, [R.PASS] * 9 + [R.ERROR])])
    assert agg["trial_pass_rate"] == pytest.approx(0.9)
    assert R.decide_exit_code(agg, 0.80) == R.EXIT_BELOW_THRESHOLD
    assert R.decide_exit_code(agg, 0.80, allow_errors=True) == R.EXIT_OK


def test_fixture_integrity_outranks_allow_errors_and_a_zero_threshold(tmp_path):
    """Adjacent edge opened by the artifact binding, and closed here.

    Stale fixtures raise FixtureError, which run_case scores as ERROR. ERROR is
    exactly what --allow-errors forgives — so `--allow-errors --threshold 0`
    turned a fixture set bound to a DIFFERENT description back into exit 0. A
    fixture that cannot vouch for itself is absent evidence, not a scoring error.
    """
    skill_dir, _ = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: xxxx\n---\n# body\n", encoding="utf-8")
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(fixtures), "--trials", "3",
                            "--allow-errors", "--threshold", "0.0")
    assert rc == R.EXIT_FIXTURES
    assert "integrity failure" in err

    # unit-level: the ordering in decide_exit_code is what enforces it. Note the
    # first assertion USED to expect EXIT_OK "on the scoring path" — that was the
    # D1 hole pinned as a feature: --allow-errors --threshold 0.0 greened a run of
    # nothing but ERROR trials whenever the fixtures_unusable flag happened not to
    # be set (a live run whose CLI cannot launch never sets it).
    agg = R.aggregate([case_result("p", True, [R.ERROR] * 3)])
    assert agg["graded_trials"] == 0
    assert R.decide_exit_code(agg, 0.0, allow_errors=True) == R.EXIT_FIXTURES
    assert R.decide_exit_code(agg, 0.0, allow_errors=True,
                              fixtures_unusable=True) == R.EXIT_FIXTURES


def test_replay_runner_records_every_integrity_failure_it_raises(tmp_path):
    write_fixture(tmp_path, "c1", 1, triggering_stream(), description_sha256="c" * 64)
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError):
        rr.run("p", tmp_path, case_id="c1", trial=1)
    with pytest.raises(R.FixtureError):
        rr.run("p", tmp_path, case_id="ghost", trial=1)
    assert len(rr.integrity_failures) == 2


def test_allow_errors_cannot_suppress_an_invisible_trial():
    """--allow-errors forgives a CLI/fixture failure; it must never forgive vacuity."""
    agg = R.aggregate([case_result("p", True, [R.PASS] * 9 + [R.INVISIBLE])])
    assert agg["invisible"] == 1
    assert R.decide_exit_code(agg, 0.80) == R.EXIT_BELOW_THRESHOLD
    assert R.decide_exit_code(agg, 0.80, allow_errors=True) == R.EXIT_BELOW_THRESHOLD


def test_a_suite_with_no_positive_trials_can_never_exit_zero():
    """BLOCKER: negatives-only trials are a perfect score for a skill that never fires."""
    agg = R.aggregate([case_result(f"n{i}", False, [R.PASS] * 3) for i in range(5)])
    assert agg["trial_pass_rate"] == 1.0
    assert agg["positive"]["trials"] == 0
    assert R.decide_exit_code(agg, 0.80) == R.EXIT_BELOW_THRESHOLD


def test_positive_pass_rate_is_gated_independently_of_the_aggregate():
    """A negative-heavy suite must not carry a positive arm that never fires."""
    agg = R.aggregate(
        [case_result("p1", True, [R.FAIL] * 3)]
        + [case_result(f"n{i}", False, [R.PASS] * 3) for i in range(5)]
    )
    assert agg["trial_pass_rate"] == pytest.approx(15 / 18, abs=1e-4)  # 0.833, above 0.80
    assert agg["positive"]["pass_rate"] == 0.0
    assert R.decide_exit_code(agg, 0.80) == R.EXIT_BELOW_THRESHOLD
    # ... and the gate is a real threshold, not a "any positive pass" rubber stamp
    ok = R.aggregate([case_result("p1", True, [R.PASS] * 3),
                      case_result("n1", False, [R.PASS] * 3)])
    assert R.decide_exit_code(ok, 0.80) == R.EXIT_OK


def test_positive_threshold_can_be_raised_but_zero_positive_trials_still_fails():
    agg = R.aggregate([case_result("p", True, [R.PASS, R.PASS, R.FAIL]),
                       case_result("n", False, [R.PASS] * 3)])
    assert agg["positive"]["pass_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert R.decide_exit_code(agg, 0.80, positive_threshold=0.60) == R.EXIT_OK
    assert R.decide_exit_code(agg, 0.80, positive_threshold=0.90) == R.EXIT_BELOW_THRESHOLD
    empty = R.aggregate([case_result("n", False, [R.PASS] * 3)])
    assert R.decide_exit_code(empty, 0.0, positive_threshold=0.0) == R.EXIT_BELOW_THRESHOLD


def test_missing_fixtures_outrank_a_perfect_pass_rate():
    agg = R.aggregate([case_result("p", True, [R.PASS, R.PASS, R.PASS])])
    assert agg["trial_pass_rate"] == 1.0
    assert R.decide_exit_code(agg, 0.80, fixtures_unusable=True) == R.EXIT_FIXTURES


# ===========================================================================
# 7. workspace isolation + the visibility seam
# ===========================================================================


def test_build_workspace_installs_skill_as_project_scope(tmp_path):
    skill_dir = make_skill(tmp_path)
    ws = R.build_workspace(tmp_path / "ws", skill_dir, "demo", R.VISIBILITY_REGISTRY["present"])
    assert (ws / ".claude" / "skills" / "demo" / "SKILL.md").is_file()
    assert (ws / ".claude" / "skills" / "demo" / "references" / "notes.md").is_file()


def test_build_workspace_excludes_the_answer_key(tmp_path):
    """evals/ holds should_trigger and rationales — copying it in is the answer key."""
    skill_dir = make_skill(tmp_path, with_evals=True)
    assert (skill_dir / "evals" / "prompts.json").is_file()
    ws = R.build_workspace(tmp_path / "ws", skill_dir, "demo", R.VISIBILITY_REGISTRY["present"])
    assert not (ws / ".claude" / "skills" / "demo" / "evals").exists()


def test_build_workspace_is_not_a_git_repo(tmp_path):
    ws = R.build_workspace(tmp_path / "ws", make_skill(tmp_path), "demo",
                           R.VISIBILITY_REGISTRY["present"])
    assert not (ws / ".git").exists()


def test_visibility_is_a_parameter_not_hardcoded(tmp_path):
    """BRO-2006 adds an 'absent' strategy; prove the seam accepts one today."""
    calls = []

    def materialize(ws, skill_dir, name):
        calls.append((Path(ws), Path(skill_dir), name))

    custom = R.Visibility(id="custom", expects_visible=False, materialize=materialize)
    ws = R.build_workspace(tmp_path / "ws", make_skill(tmp_path), "demo", custom)
    assert calls and calls[0][2] == "demo"
    assert not (ws / ".claude").exists()
    assert custom.expects_visible is False


def test_visibility_registry_ships_both_ablation_arms():
    """UPDATED BY BRO-2006, extended by BRO-2028 (the `bare` arm). The invariant
    that matters is not the count but that each arm declares the right visibility
    expectation, since that is what drives the INVISIBLE/LEAKED guards.

    `bare` is visible ON PURPOSE: the skill is installed and on the roster, only
    its description is gone. Declaring it invisible would disable the INVISIBLE
    check and let a loader that drops description-less skills read as a zero-lift
    result instead of a visibility bug."""
    assert sorted(R.VISIBILITY_REGISTRY) == ["absent", "bare", "present"]
    assert R.VISIBILITY_REGISTRY["present"].expects_visible is True
    assert R.VISIBILITY_REGISTRY["absent"].expects_visible is False
    assert R.VISIBILITY_REGISTRY["bare"].expects_visible is True


def test_the_absent_arm_installs_nothing(tmp_path):
    ws = R.build_workspace(
        tmp_path / "ws", make_skill(tmp_path), "demo", R.VISIBILITY_REGISTRY["absent"])
    assert not (ws / ".claude" / "skills" / "demo").exists()


# ===========================================================================
# 8. runners: live argv, replay behaviour, and the replay guard
# ===========================================================================


def test_live_runner_argv_matches_the_verified_invocation():
    argv = R.LiveRunner(cli="/bin/claude", model="haiku").build_argv("hello")
    assert argv[0] == "/bin/claude"
    assert argv[1:3] == ["-p", "hello"]
    for flag in ("--output-format", "stream-json", "--verbose", "--setting-sources", "project",
                 "--permission-mode", "bypassPermissions", "--no-session-persistence"):
        assert flag in argv
    assert "--disallowedTools" not in argv


def test_live_runner_can_block_recovery_tools():
    argv = R.LiveRunner(cli="/bin/claude", disallow_recovery_tools=True).build_argv("x")
    assert argv[argv.index("--disallowedTools") + 1] == "Read Grep Glob Bash"


def test_live_runner_mode_is_live_and_trials_are_as_requested():
    lr = R.LiveRunner(cli="/bin/claude")
    assert lr.mode == "live"
    assert lr.trials_for("any", 3) == 3


def test_missing_cli_binary_is_an_error_trial_not_a_pass(tmp_path):
    cfg = R.RunConfig(skill="demo", skill_dir=make_skill(tmp_path), trials=1)
    runner = R.LiveRunner(cli=str(tmp_path / "definitely-not-a-binary"))
    cr = R.run_case(runner, case(should_trigger=True), cfg)
    assert [t.outcome for t in cr.trials] == [R.ERROR]
    assert cr.pass_rate == 0.0


FP = {  # a stand-in artifact fingerprint for unit-level replay tests
    "skill_md_path": "/fake/SKILL.md",
    "skill_md_sha256": "a" * 64,
    "description_sha256": "b" * 64,
}


def write_fixture(root: Path, case_id: str, trial: int, text: str, prompt: str = "p",
                  fingerprint: dict | None = None, **overrides):
    """Write a fixture the way ``--record`` does: transcript + bound meta sidecar.

    Bound by default on purpose. An unbound fixture is now refused, so a helper
    that produced one would only ever be used to test the refusal.
    """
    import hashlib

    fp = FP if fingerprint is None else fingerprint
    d = root / "cases" / case_id
    d.mkdir(parents=True, exist_ok=True)
    (d / f"trial-{trial:02d}.jsonl").write_text(text, encoding="utf-8")
    meta = {
        "meta_version": R.FIXTURE_META_VERSION,
        "provenance": R.PROVENANCE_LIVE,
        "skill": "demo",
        "case_id": case_id,
        "trial": trial,
        "exit_code": 0,
        "wall_ms": 4900,
        "model": R.DEFAULT_MODEL,
        "cli_version": R.EXPECTED_CLI_VERSION,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "skill_md_sha256": fp["skill_md_sha256"],
        "description_sha256": fp["description_sha256"],
        "recorded_at": "2026-07-28T00:00:00Z",
    }
    meta.update(overrides)
    if meta.pop("_no_meta", False):
        (d / f"trial-{trial:02d}.meta.json").unlink(missing_ok=True)
        return
    (d / f"trial-{trial:02d}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def replay(root: Path, **kw) -> R.ReplayRunner:
    kw.setdefault("fingerprint", FP)
    return R.ReplayRunner(root=root, **kw)


def test_replay_runner_reads_recorded_transcript(tmp_path):
    write_fixture(tmp_path, "c1", 1, triggering_stream())
    rr = replay(tmp_path)
    assert rr.mode == "replay"
    assert rr.available("c1") == 1
    t = rr.run("p", tmp_path, case_id="c1", trial=1)
    assert t.triggered("demo") is True


def test_replay_runner_cannot_be_built_without_an_artifact_binding():
    """No default fingerprint: an unbound replay runner is not constructible."""
    with pytest.raises(TypeError):
        R.ReplayRunner(root=Path("/tmp"))  # type: ignore[call-arg]


def test_replay_runner_raises_on_missing_fixture(tmp_path):
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="missing replay fixture"):
        rr.run("p", tmp_path, case_id="ghost", trial=1)


def test_replay_runner_raises_on_empty_fixture(tmp_path):
    write_fixture(tmp_path, "c1", 1, "")
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="empty replay fixture"):
        rr.run("p", tmp_path, case_id="c1", trial=1)


def test_replay_runner_raises_on_unparseable_fixture(tmp_path):
    write_fixture(tmp_path, "c1", 1, "not json\nstill not json\n")
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="no parseable events"):
        rr.run("p", tmp_path, case_id="c1", trial=1)


# -- artifact binding: the fixture is bound to the SKILL.md it was recorded on --


def test_replay_refuses_a_fixture_recorded_against_a_different_description(tmp_path):
    """BLOCKER: this is the regression the whole harness exists to detect."""
    write_fixture(tmp_path, "c1", 1, triggering_stream(),
                  description_sha256="c" * 64)
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="STALE FIXTURE.*DESCRIPTION"):
        rr.run("p", tmp_path, case_id="c1", trial=1)


def test_replay_refuses_a_fixture_recorded_against_a_different_skill_body(tmp_path):
    write_fixture(tmp_path, "c1", 1, triggering_stream(), skill_md_sha256="d" * 64)
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="STALE FIXTURE.*SKILL.md"):
        rr.run("p", tmp_path, case_id="c1", trial=1)


def test_replay_refuses_a_fixture_with_no_meta_sidecar(tmp_path):
    """An unbound fixture cannot be told apart from a fabricated one."""
    write_fixture(tmp_path, "c1", 1, triggering_stream(), _no_meta=True)
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="no meta sidecar"):
        rr.run("p", tmp_path, case_id="c1", trial=1)


def test_replay_refuses_a_pre_binding_meta_version(tmp_path):
    write_fixture(tmp_path, "c1", 1, triggering_stream(), meta_version=1)
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="pre-dates artifact binding"):
        rr.run("p", tmp_path, case_id="c1", trial=1)


def test_replay_refuses_a_meta_with_no_skill_hash(tmp_path):
    write_fixture(tmp_path, "c1", 1, triggering_stream(), description_sha256="")
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="not bound to any artifact"):
        rr.run("p", tmp_path, case_id="c1", trial=1)


def test_replay_refuses_synthetic_fixtures_unless_opted_in(tmp_path):
    write_fixture(tmp_path, "c1", 1, triggering_stream(), provenance=R.PROVENANCE_SYNTHETIC)
    with pytest.raises(R.FixtureError, match="SYNTHETIC"):
        replay(tmp_path).run("p", tmp_path, case_id="c1", trial=1)
    t = replay(tmp_path, allow_synthetic=True).run("p", tmp_path, case_id="c1", trial=1)
    assert t.triggered("demo") is True


def test_replay_refuses_another_skills_fixture(tmp_path):
    """A fixture dir holding a different skill's transcripts grades neither one."""
    write_fixture(tmp_path, "c1", 1, triggering_stream(), skill="something-else")
    rr = replay(tmp_path, expected_skill="demo")
    with pytest.raises(R.FixtureError, match="recorded for skill 'something-else'"):
        rr.run("p", tmp_path, case_id="c1", trial=1)


def test_live_runner_refuses_to_record_an_unbound_fixture(tmp_path):
    """Recording without a fingerprint would write a fixture replay can never check."""
    lr = R.LiveRunner(cli="/bin/true", record_dir=tmp_path / "rec", skill="demo")
    with pytest.raises(R.SkillArtifactError, match="UNBOUND fixture"):
        lr._record("c1", 1, "p", triggering_stream(),
                   Transcript.from_ndjson(triggering_stream()))
    assert not (tmp_path / "rec" / "cases" / "c1" / "trial-01.jsonl").exists()


def test_replay_refuses_an_unrecognised_provenance(tmp_path):
    write_fixture(tmp_path, "c1", 1, triggering_stream(), provenance="hand-wave")
    with pytest.raises(R.FixtureError, match="provenance"):
        replay(tmp_path, allow_synthetic=True).run("p", tmp_path, case_id="c1", trial=1)


def test_replay_stale_prompt_hash_is_fatal(tmp_path):
    """A fixture recorded against a different prompt grades nothing useful."""
    write_fixture(tmp_path, "c1", 1, triggering_stream(), prompt="the ORIGINAL prompt")
    rr = replay(tmp_path)
    with pytest.raises(R.FixtureError, match="STALE FIXTURE"):
        rr.run("a DIFFERENT prompt", tmp_path, case_id="c1", trial=1)
    assert rr.stale_fixtures and "different prompt" in rr.stale_fixtures[0]


def test_replay_notes_model_and_cli_drift_and_strict_mode_makes_it_fatal(tmp_path):
    write_fixture(tmp_path, "c1", 1, triggering_stream(), model="opus", cli_version="1.0.0")
    rr = replay(tmp_path, expected_model="haiku", expected_cli_version="2.1.220")
    rr.run("p", tmp_path, case_id="c1", trial=1)
    assert any("model" in n for n in rr.provenance_notes)
    assert any("CLI version" in n for n in rr.provenance_notes)

    strict = replay(tmp_path, expected_model="haiku", expected_cli_version="2.1.220",
                    strict_prompt_hash=True)
    with pytest.raises(R.FixtureError, match="recorded on model"):
        strict.run("p", tmp_path, case_id="c1", trial=1)


def test_replay_trials_are_requested_not_clamped(tmp_path):
    """A shortfall is an ERROR, not a silent clamp — the old clamp hid n=1 runs."""
    write_fixture(tmp_path, "c1", 1, triggering_stream())
    write_fixture(tmp_path, "c1", 2, triggering_stream())
    rr = replay(tmp_path)
    assert rr.available("c1") == 2
    assert rr.trials_for("c1", 5) == 5
    assert rr.trials_for("c1", 1) == 1
    assert rr.trials_for("ghost", 3) == 3


def test_replay_short_fixture_set_errors_on_the_missing_trials(tmp_path):
    write_fixture(tmp_path / "fixtures", "c1", 1, triggering_stream())
    cfg = R.RunConfig(skill="demo", skill_dir=make_skill(tmp_path / "s"), trials=3)
    cr = R.run_case(replay(tmp_path / "fixtures"),
                    case(cid="c1", checks=["final_answer_non_empty"]), cfg)
    assert [t.outcome for t in cr.trials] == [R.PASS, R.ERROR, R.ERROR]
    assert "missing replay fixture" in cr.trials[1].detail
    assert R.decide_exit_code(R.aggregate([cr]), 0.0) == R.EXIT_BELOW_THRESHOLD


def test_replay_case_with_no_fixtures_errors_instead_of_passing(tmp_path):
    """The core replay guard: absent evidence must never read as a pass."""
    cfg = R.RunConfig(skill="demo", skill_dir=make_skill(tmp_path / "s"), trials=3)
    cr = R.run_case(replay(tmp_path / "fixtures"), case(cid="ghost"), cfg)
    assert [t.outcome for t in cr.trials] == [R.ERROR, R.ERROR, R.ERROR]
    assert cr.pass_rate == 0.0
    agg = R.aggregate([cr])
    # Zero graded trials is an ABSENCE OF EVIDENCE, so it reports as a fixture
    # problem (exit 3) rather than as a score below the bar (exit 1) — and it does
    # so with --threshold 0.0 and --allow-errors both set, which is the whole point.
    assert agg["graded_trials"] == 0
    assert R.decide_exit_code(agg, 0.0) == R.EXIT_FIXTURES
    assert R.decide_exit_code(agg, 0.0, allow_errors=True) == R.EXIT_FIXTURES


def test_replay_empty_fixture_errors_instead_of_passing(tmp_path):
    write_fixture(tmp_path / "fixtures", "c1", 1, "   \n")
    cfg = R.RunConfig(skill="demo", skill_dir=make_skill(tmp_path / "s"), trials=1)
    cr = R.run_case(replay(tmp_path / "fixtures"), case(cid="c1"), cfg)
    assert [t.outcome for t in cr.trials] == [R.ERROR]
    assert "empty replay fixture" in cr.trials[0].detail


def test_replay_grades_a_real_recorded_run(tmp_path):
    """Replay is not a rubber stamp in the other direction either — it can pass."""
    for trial in (1, 2, 3):
        write_fixture(tmp_path / "fixtures", "c1", trial, triggering_stream())
    cfg = R.RunConfig(skill="demo", skill_dir=make_skill(tmp_path / "s"), trials=3)
    cr = R.run_case(replay(tmp_path / "fixtures"),
                    case(cid="c1", checks=["final_answer_non_empty"]), cfg)
    assert [t.outcome for t in cr.trials] == [R.PASS, R.PASS, R.PASS]


def test_record_then_replay_roundtrip(tmp_path):
    """--record writes what --replay reads; the two halves of the seam agree."""
    rec = tmp_path / "rec"
    lr = R.LiveRunner(cli="/bin/true", record_dir=rec, skill="demo",
                      cli_version="2.1.220", fingerprint=FP)
    lr._record("c1", 1, "the prompt", triggering_stream(),
               Transcript.from_ndjson(triggering_stream(), wall_ms=1234))
    meta = json.loads((rec / "cases" / "c1" / "trial-01.meta.json").read_text())
    assert meta["skill_md_sha256"] == FP["skill_md_sha256"]
    assert meta["description_sha256"] == FP["description_sha256"]
    assert meta["provenance"] == R.PROVENANCE_LIVE
    assert meta["cli_version"] == "2.1.220"

    rr = replay(rec, expected_model=R.DEFAULT_MODEL, expected_cli_version="2.1.220")
    assert rr.available("c1") == 1
    t = rr.run("the prompt", tmp_path, case_id="c1", trial=1)
    assert t.triggered("demo") is True
    assert rr.stale_fixtures == [] and rr.provenance_notes == []


def test_recorded_fixture_replays_against_the_real_skill_it_was_recorded_from(tmp_path):
    """End-to-end binding: record with a real fingerprint, edit SKILL.md, replay dies."""
    skill_dir = make_skill(tmp_path)
    fp = R.skill_fingerprint(skill_dir)
    rec = tmp_path / "rec"
    lr = R.LiveRunner(cli="/bin/true", record_dir=rec, skill="demo", fingerprint=fp)
    lr._record("c1", 1, "the prompt", triggering_stream(),
               Transcript.from_ndjson(triggering_stream()))

    replay(rec, fingerprint=fp).run("the prompt", tmp_path, case_id="c1", trial=1)

    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: xxxx\n---\n# body\n", encoding="utf-8")
    mutated = R.skill_fingerprint(skill_dir)
    with pytest.raises(R.FixtureError, match="STALE FIXTURE"):
        replay(rec, fingerprint=mutated).run("the prompt", tmp_path, case_id="c1", trial=1)


# ===========================================================================
# 9. end-to-end CLI behaviour (no live model calls)
# ===========================================================================


def run_cli(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, str(RUNNER_PY), *args],
                          capture_output=True, text=True, env={**os.environ})
    return proc.returncode, proc.stdout, proc.stderr


def scaffold(tmp_path, cases=None) -> tuple[Path, Path]:
    skill_dir = make_skill(tmp_path, with_evals=False)
    evals = skill_dir / "evals"
    evals.mkdir(parents=True, exist_ok=True)
    prompts = evals / "prompts.json"
    prompts.write_text(json.dumps(prompt_set_doc(cases=cases)), encoding="utf-8")
    return skill_dir, prompts


def bind(skill_dir: Path) -> dict:
    """The fingerprint the CLI will compute for a scaffolded skill."""
    return R.skill_fingerprint(skill_dir)


def full_fixtures(tmp_path, skill_dir, trials=3, positive=None, negative=None) -> Path:
    """A complete, bound fixture set for the two-case default prompt set."""
    fixtures = tmp_path / "fixtures"
    fp = bind(skill_dir)
    doc = prompt_set_doc()
    prompts = {c["id"]: c["prompt"] for c in doc["cases"]}
    for trial in range(1, trials + 1):
        write_fixture(fixtures, "golden-01", trial, positive or triggering_stream(),
                      prompt=prompts["golden-01"], fingerprint=fp)
        write_fixture(fixtures, "negative-01", trial, negative or quiet_stream(),
                      prompt=prompts["negative-01"], fingerprint=fp)
    return fixtures


def test_cli_prints_the_mode_on_every_invocation(tmp_path):
    _skill_dir, prompts = scaffold(tmp_path)
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(tmp_path / "nothing"), "--validate-only")
    assert rc == R.EXIT_OK
    assert "mode=REPLAY" in err


def test_cli_validate_only_reports_case_split(tmp_path):
    scaffold(tmp_path)
    rc, out, _err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(tmp_path), "--validate-only")
    assert rc == R.EXIT_OK
    assert "2 cases (1 positive / 1 negative)" in out


def test_cli_rejects_a_malformed_prompt_set(tmp_path):
    skill_dir, prompts = scaffold(tmp_path)
    prompts.write_text(json.dumps({"skill": "demo", "version": 1, "cases": [
        {"id": "a", "prompt": "x", "should_trigger": True,
         "expected_checks": ["does_not_exist"]}]}), encoding="utf-8")
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(tmp_path))
    assert rc == R.EXIT_USAGE
    assert "unknown check id" in err


def test_cli_replay_with_no_fixtures_exits_nonzero(tmp_path):
    """The named failure mode: an empty replay set must never look green."""
    scaffold(tmp_path)
    rc, out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                           "--replay", str(tmp_path / "empty-fixtures"))
    assert rc == R.EXIT_FIXTURES
    assert "FIXTURE GUARD" in err
    assert "PASS" not in out


def test_cli_replay_with_partial_fixtures_cannot_exit_zero(tmp_path):
    skill_dir, _ = scaffold(tmp_path)
    fixtures = tmp_path / "fixtures"
    write_fixture(fixtures, "golden-01", 1, triggering_stream(),
                  prompt="here is an artifact, wdyt", fingerprint=bind(skill_dir))
    # negative-01 has no fixture at all
    rc, out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                           "--replay", str(fixtures), "--threshold", "0.0", "--trials", "1")
    assert rc == R.EXIT_FIXTURES
    assert "FIXTURE GUARD" in err
    assert "negative-01" in err


def test_cli_replay_short_fixture_set_is_an_error_not_a_silent_clamp(tmp_path):
    """MAJOR: --trials 3 against one-trial-per-case fixtures used to exit 0 quietly."""
    skill_dir, _ = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir, trials=1)
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(fixtures), "--trials", "3")
    assert rc == R.EXIT_FIXTURES
    assert "fewer than the 3 requested trials" in err

    # and asking for what actually exists is honest, but is labelled an anecdote
    rc, out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                           "--replay", str(fixtures), "--trials", "1")
    assert rc == R.EXIT_OK
    assert "ANECDOTE (n=1" in out
    assert "is an anecdote, not a distribution" in err


def test_cli_replay_full_fixtures_green(tmp_path):
    skill_dir, _ = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir)
    rc, out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                           "--replay", str(fixtures), "--trials", "3")
    assert rc == R.EXIT_OK, f"{out}\n{err}"
    assert "trial pass-rate 1.000" in out
    assert "[distribution]" in out
    assert "mode=REPLAY" in err


def test_cli_replay_goes_red_when_the_description_changes(tmp_path):
    """THE mutation proof, as a standing test: green fixtures + edited description = RED.

    This is the property the adversarial review proved absent — a 5-line SKILL.md
    stub whose description was 'xxxx' still replayed 45/45 green.
    """
    skill_dir, _ = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir)
    args = ("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
            "--replay", str(fixtures), "--trials", "3")
    assert run_cli(*args)[0] == R.EXIT_OK

    original = (skill_dir / "SKILL.md").read_text()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: xxxx\n---\n# body\n", encoding="utf-8")
    rc, out, err = run_cli(*args)
    assert rc == R.EXIT_FIXTURES  # integrity failure, not a mere low score
    assert "STALE FIXTURE" in out
    assert "FIXTURE GUARD" in err

    (skill_dir / "SKILL.md").write_text(original, encoding="utf-8")
    assert run_cli(*args)[0] == R.EXIT_OK  # and it goes green again on revert


def test_cli_replay_reports_a_real_regression(tmp_path):
    """Mutation-shaped: swap the positive fixture for a non-triggering run."""
    skill_dir, _ = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir, positive=quiet_stream())
    rc, out, _err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(fixtures), "--trials", "3")
    assert rc == R.EXIT_BELOW_THRESHOLD
    assert "skill did not trigger" in out


def test_cli_json_report_shape(tmp_path):
    skill_dir, _ = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir, trials=2)
    report_path = tmp_path / "report.json"
    rc, out, _err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(fixtures), "--trials", "2", "--json",
                            "--report", str(report_path))
    assert rc == R.EXIT_OK
    payload = json.loads(out)
    assert payload["mode"] == "replay"
    assert payload["skill"] == "demo"
    assert payload["aggregate"]["trial_pass_rate"] == 1.0
    assert payload["aggregate"]["min_trials_per_case"] == 2
    assert payload["meta"]["description_sha256"] == bind(skill_dir)["description_sha256"]
    assert {c["case_id"] for c in payload["cases"]} == {"golden-01", "negative-01"}
    assert json.loads(report_path.read_text())["exit_code"] == 0


def test_cli_case_filter(tmp_path):
    skill_dir, _ = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir, trials=2)
    rc, out, _err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(fixtures), "--trials", "2",
                            "--case", "golden-01", "--json")
    assert rc == R.EXIT_OK
    assert [c["case_id"] for c in json.loads(out)["cases"]] == ["golden-01"]


def test_cli_rejects_a_skill_that_disagrees_with_the_prompt_set(tmp_path):
    """Grading a prompt set against another skill measures neither one."""
    skill_dir, prompts = scaffold(tmp_path)
    make_skill(tmp_path, name="other")
    rc, _out, err = run_cli("--skill", "other", "--skills-root", str(tmp_path / "skills"),
                            "--prompts", str(prompts), "--replay", str(tmp_path))
    assert rc == R.EXIT_USAGE
    assert "declares skill 'demo'" in err


def test_cli_rejects_a_negatives_only_prompt_set(tmp_path):
    """BLOCKER: an all-negative suite is the cheapest way to green this gate."""
    scaffold(tmp_path, cases=[
        {"id": f"negative-{i:02d}", "prompt": f"just fix bug {i}", "should_trigger": False,
         "origin": "negative", "expected_checks": ["final_answer_non_empty"]} for i in range(1, 6)])
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(tmp_path))
    assert rc == R.EXIT_USAGE
    assert "no positive cases" in err


def test_cli_refuses_a_skill_without_a_description(tmp_path):
    skill_dir, _ = scaffold(tmp_path)
    (skill_dir / "SKILL.md").write_text("---\nname: demo\n---\n# body\n", encoding="utf-8")
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(tmp_path), "--validate-only")
    assert rc == R.EXIT_USAGE
    assert "no frontmatter 'description:'" in err


def test_cli_banner_prints_the_artifact_binding(tmp_path):
    skill_dir, _ = scaffold(tmp_path)
    _rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                             "--replay", str(tmp_path), "--validate-only")
    fp = bind(skill_dir)
    assert f"skill_md={fp['skill_md_sha256'][:12]}" in err
    assert f"description={fp['description_sha256'][:12]}" in err


def test_cli_rejects_unknown_case_id(tmp_path):
    scaffold(tmp_path)
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(tmp_path), "--case", "nope")
    assert rc == R.EXIT_USAGE
    assert "no such case id" in err


def test_cli_rejects_record_with_replay(tmp_path):
    scaffold(tmp_path)
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(tmp_path), "--record", str(tmp_path / "rec"))
    assert rc == R.EXIT_USAGE
    assert "meaningless" in err


def test_cli_requires_skill_or_prompts():
    rc, _out, err = run_cli("--replay", "/tmp")
    assert rc == R.EXIT_USAGE
    assert "--skill or --prompts" in err


def test_cli_list_checks_enumerates_the_registry():
    rc, out, _err = run_cli("--list-checks")
    assert rc == R.EXIT_OK
    for check_id in checks_mod.CHECK_REGISTRY:
        assert check_id in out


# ===========================================================================
# 10. the shipped pilot prompt set is valid against this registry
# ===========================================================================


PILOT = REPO / "skills" / "research" / "checkit" / "evals" / "prompts.json"


def test_checkit_pilot_prompt_set_is_present_and_valid():
    """Contract test: the pilot set must stay loadable as checks.py evolves.

    Deliberately NOT skipped when the file is absent. A skip-on-missing turns
    "someone deleted the prompt set" into a green test — the contract is that the
    pilot exists, so its absence is the failure this test is for.

    B2, second hole: this test used to assert ONLY case counts and known check ids,
    so emptying any case's expected_checks left it green. Counts and ids say
    nothing about whether a case still asserts anything, which is the mutation the
    eval-set review actually performed.
    """
    assert PILOT.is_file(), f"pilot prompt set missing: {PILOT}"
    ps = R.load_prompt_set(PILOT)
    assert len(ps.cases) >= 15
    assert len(ps.positives) >= 5
    assert len(ps.negatives) >= 5
    assert all(c in checks_mod.CHECK_REGISTRY
               for case_ in ps.cases for c in case_.expected_checks)
    gutted = [c.id for c in ps.cases if not c.expected_checks]
    assert not gutted, f"cases assert nothing beyond trigger/no-trigger: {gutted}"


def test_checkit_skill_is_fingerprintable():
    """The artifact the pilot set grades must be bindable, or replay cannot be honest."""
    fp = R.skill_fingerprint(PILOT.parent.parent)
    assert len(fp["skill_md_sha256"]) == 64
    assert len(fp["description_sha256"]) == 64


# ===========================================================================
# 11. committed CI fixtures: the harness self-test set is real and graded
# ===========================================================================

SELFTEST = Path(__file__).resolve().parent / "fixtures" / "harness-selftest"


def test_selftest_fixture_set_is_committed_and_bound():
    """CI grades this set. If it is not bound to its skill, CI grades nothing."""
    fp = R.skill_fingerprint(SELFTEST / "skill")
    ps = R.load_prompt_set(SELFTEST / "evals" / "prompts.json")
    assert ps.positives and ps.negatives
    graded = 0
    for c in ps.cases:
        metas = sorted((SELFTEST / "cases" / c.id).glob("trial-*.meta.json"))
        assert len(metas) >= R.MIN_DISTRIBUTION_TRIALS, f"{c.id} is an anecdote"
        for m in metas:
            meta = json.loads(m.read_text())
            assert meta["skill_md_sha256"] == fp["skill_md_sha256"], f"{m} is stale"
            assert meta["description_sha256"] == fp["description_sha256"], f"{m} is stale"
            # Honesty: these are hand-authored, and say so.
            assert meta["provenance"] == R.PROVENANCE_SYNTHETIC
            graded += 1
    assert graded >= 12


def test_selftest_fixture_set_grades_green_end_to_end(tmp_path):
    rc, out, err = run_cli(
        "--skill-dir", str(SELFTEST / "skill"),
        "--prompts", str(SELFTEST / "evals" / "prompts.json"),
        "--replay", str(SELFTEST), "--trials", "3", "--allow-synthetic-fixtures")
    assert rc == R.EXIT_OK, f"{out}\n{err}"
    assert "[distribution]" in out
    assert "SYNTHETIC-FIXTURES-ALLOWED" in err


def test_selftest_fixture_set_is_refused_without_the_synthetic_opt_in():
    """A hand-authored fixture must never quietly stand in for a recorded one."""
    rc, out, _err = run_cli(
        "--skill-dir", str(SELFTEST / "skill"),
        "--prompts", str(SELFTEST / "evals" / "prompts.json"),
        "--replay", str(SELFTEST), "--trials", "3")
    assert rc == R.EXIT_FIXTURES
    assert "SYNTHETIC" in out


def test_selftest_fixture_set_goes_red_when_its_description_is_mutated(tmp_path):
    """The CI mutation proof, run here too: this is what CI asserts on every PR."""
    scratch = tmp_path / "harness-selftest"
    shutil.copytree(SELFTEST, scratch)
    args = ("--skill-dir", str(scratch / "skill"),
            "--prompts", str(scratch / "evals" / "prompts.json"),
            "--replay", str(scratch), "--trials", "3", "--allow-synthetic-fixtures")
    assert run_cli(*args)[0] == R.EXIT_OK

    md = scratch / "skill" / "SKILL.md"
    original = md.read_text()
    md.write_text("---\nname: harness-selftest\ndescription: xxxx\n---\n# body\n",
                  encoding="utf-8")
    rc, out, _err = run_cli(*args)
    assert rc == R.EXIT_FIXTURES
    assert "STALE FIXTURE" in out

    md.write_text(original, encoding="utf-8")
    assert run_cli(*args)[0] == R.EXIT_OK


# ===========================================================================
# 12. round-3 review closures (D1-D7 + the over-strictness the eval set proved)
# ===========================================================================

# -- D1: zero graded trials cannot pass, under ANY flag combination ----------

ALL_FLAG_COMBOS = [
    {},
    {"allow_errors": True},
    {"positive_threshold": 0.0},
    {"allow_errors": True, "positive_threshold": 0.0},
]


def test_a_run_that_graded_zero_real_trials_cannot_pass_under_any_flag():
    """D1 root predicate: `graded_trials == 0` outranks every scoring knob.

    The round-2 fix hoisted only FixtureError into `fixtures_unusable`, which left
    every sibling ERROR source uncovered — the OSError arm in `run_case` most of
    all, since a LIVE run whose CLI cannot be launched errors every trial while
    `fixtures_unusable` stays False. The invariant is not "which error class was
    it", it is "did this run grade anything at all".
    """
    agg = R.aggregate([case_result("p", True, [R.ERROR] * 3),
                       case_result("n", False, [R.ERROR] * 3)])
    assert agg["trials"] == 6 and agg["graded_trials"] == 0
    for threshold in (0.0, 0.5, 0.8):
        for flags in ALL_FLAG_COMBOS:
            assert R.decide_exit_code(agg, threshold, **flags) == R.EXIT_FIXTURES, (
                f"threshold={threshold} flags={flags} greened a zero-evidence run")


def test_graded_trials_counts_signal_not_attempts():
    agg = R.aggregate([case_result("p", True, [R.PASS, R.FAIL, R.RECOVERED,
                                               R.ERROR, R.INVISIBLE])])
    assert agg["trials"] == 5
    assert agg["graded_trials"] == 3  # PASS + FAIL + RECOVERED carry signal
    assert agg["positive"]["graded_trials"] == 3


def test_one_graded_trial_is_enough_to_reach_the_scoring_path():
    """The floor must not swallow runs that DID measure something (no false-fail)."""
    agg = R.aggregate([case_result("p", True, [R.PASS] + [R.ERROR] * 4)])
    assert agg["graded_trials"] == 1
    assert R.decide_exit_code(agg, 0.0, allow_errors=True) == R.EXIT_OK


def test_cli_live_run_with_an_unlaunchable_cli_cannot_be_greened(tmp_path):
    """D1 end to end, on the exact reproduction the review gave.

    No --replay, so no fixture guard fires; every trial dies in the OSError arm
    with "could not launch runner". --allow-errors forgives ERROR and
    --threshold 0.0 forgives any rate, and the run must still be RED.
    """
    scaffold(tmp_path)
    rc, out, _err = run_cli(
        "--skill", "demo", "--skills-root", str(tmp_path / "skills"),
        "--cli", str(tmp_path / "definitely-not-a-binary"), "--no-version-check",
        "--trials", "2", "--allow-errors", "--threshold", "0.0")
    assert rc != R.EXIT_OK, out
    assert rc == R.EXIT_FIXTURES
    assert "could not launch runner" in out
    assert "0/4 trials produced ANY signal" in out


# -- D2: --threshold cannot lower the "did it ever fire?" floor --------------


def test_threshold_zero_cannot_green_a_total_trigger_failure():
    """D2: positives graded 0/N is the regression this harness exists to catch."""
    agg = R.aggregate([case_result("p", True, [R.FAIL] * 3),
                       case_result("n", False, [R.PASS] * 3)])
    assert agg["graded_trials"] == 6          # real evidence: D1 is satisfied
    assert agg["positive"]["passes"] == 0     # ...and the skill never once fired
    for flags in ALL_FLAG_COMBOS:
        assert R.decide_exit_code(agg, 0.0, **flags) == R.EXIT_BELOW_THRESHOLD, flags


def test_the_positive_floor_does_not_false_fail_a_partly_passing_arm():
    """A floor that also rejects 1/3 would be a gate that false-fails."""
    agg = R.aggregate([case_result("p", True, [R.PASS, R.FAIL, R.FAIL]),
                       case_result("n", False, [R.PASS] * 3)])
    assert agg["positive"]["passes"] == 1
    assert R.decide_exit_code(agg, 0.0) == R.EXIT_OK
    assert R.decide_exit_code(agg, 0.0, positive_threshold=0.0) == R.EXIT_OK


def test_cli_threshold_zero_cannot_green_a_replay_where_the_skill_never_fires(tmp_path):
    """D2 end to end: the positive fixture is a run that never triggered."""
    skill_dir, _prompts = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir, positive=quiet_stream())
    rc, out, _err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(fixtures), "--trials", "3",
                            "--allow-errors", "--threshold", "0.0")
    assert rc == R.EXIT_BELOW_THRESHOLD, out
    assert "ZERO POSITIVE PASSES" in out


def test_the_positive_arm_comment_is_true_of_the_code():
    """The source comment claimed a property the code did not have. Assert it.

    Not prose-matching: this asserts the BEHAVIOUR the comment describes — no
    knob, including the tests-only `positive_threshold`, reaches exit 0 through a
    positive arm that never once passed — so an edit that re-opens the hole fails
    here rather than leaving a lie in the source.
    """
    dead = R.aggregate([case_result("p", True, [R.FAIL] * 3)])
    for pt in (None, 0.0, 0.5, 1.0):
        assert R.decide_exit_code(dead, 0.0, positive_threshold=pt) == R.EXIT_BELOW_THRESHOLD


# -- D5: the frontmatter parser must agree with the real loader --------------

ALL_SKILL_MDS = sorted(p for p in (REPO / "skills").rglob("SKILL.md"))


def test_the_repo_actually_has_skill_mds_to_diff_against():
    """Guards the differential test below from passing on an empty iteration."""
    assert len(ALL_SKILL_MDS) >= 50


def test_hand_parser_agrees_with_pyyaml_on_every_real_skill_md():
    """D5: the fallback and the reference implementation must not disagree.

    The description hash binds a fixture to its artifact. A parser that disagrees
    with the real (YAML) loader both misses real changes and manufactures phantom
    ones — arcan-glass diverged by 159 characters because its description carries
    an inline YAML comment.
    """
    yaml = pytest.importorskip("yaml")
    divergent = []
    for path in ALL_SKILL_MDS:
        text = path.read_text(encoding="utf-8", errors="replace")
        block = R._frontmatter_block(text)
        if block is None:
            continue
        try:
            data = yaml.safe_load(block)
        except Exception:
            continue  # malformed frontmatter: the real loader rejects it too
        if not isinstance(data, dict) or not isinstance(data.get("description"), str):
            continue
        reference = " ".join(data["description"].split())
        hand = R._parse_frontmatter_description_fallback(text)
        if hand != reference:
            divergent.append((str(path), len(hand), len(reference)))
    assert not divergent, f"hand parser disagrees with PyYAML on: {divergent}"


def test_frontmatter_parser_truncates_at_an_inline_yaml_comment():
    """The measured arcan-glass shape: `#` after a space opens a YAML comment."""
    doc = "---\nname: x\ndescription: Brand tokens (AI Blue #0066FF) and more prose\n---\n"
    assert R.parse_frontmatter_description(doc) == "Brand tokens (AI Blue"
    assert R._parse_frontmatter_description_fallback(doc) == "Brand tokens (AI Blue"
    # ...but inside quotes and inside a block scalar it is content, not a comment
    quoted = '---\nname: x\ndescription: "AI Blue #0066FF"\n---\n'
    assert R.parse_frontmatter_description(quoted) == "AI Blue #0066FF"
    block = "---\nname: x\ndescription: |\n  AI Blue #0066FF\n---\n"
    assert R.parse_frontmatter_description(block) == "AI Blue #0066FF"


def test_frontmatter_parser_unquotes_like_the_real_loader():
    for doc, want in [
        ('---\nd: 1\ndescription: "quoted words"\n---\n', "quoted words"),
        ("---\nd: 1\ndescription: 'single quoted'\n---\n", "single quoted"),
        ("---\nd: 1\ndescription: 'it''s escaped'\n---\n", "it's escaped"),
        ('---\nd: 1\ndescription: "say \\"hi\\" now"\n---\n', 'say "hi" now'),
        ('---\nd: 1\ndescription: "spans\n  two lines"\n---\n', "spans two lines"),
    ]:
        assert R.parse_frontmatter_description(doc) == want, doc
        assert R._parse_frontmatter_description_fallback(doc) == want, doc


def test_parse_frontmatter_description_uses_the_fallback_without_pyyaml(monkeypatch):
    """PyYAML is preferred, not required: the harness still runs without it."""
    monkeypatch.setattr(R, "_yaml", None)
    doc = '---\nname: x\ndescription: "AI Blue #0066FF"\n---\n'
    assert R.parse_frontmatter_description(doc) == "AI Blue #0066FF"


def test_description_hash_is_stable_across_the_two_parser_paths(monkeypatch):
    """The binding hash must not depend on whether PyYAML happens to be installed."""
    yaml_path = R.skill_fingerprint(PILOT.parent.parent)["description_sha256"]
    monkeypatch.setattr(R, "_yaml", None)
    hand_path = R.skill_fingerprint(PILOT.parent.parent)["description_sha256"]
    assert yaml_path == hand_path


# -- D3/D4: the SKILL.md needle must be scoped to the skill under test -------

#: (tool, input, the prompt that names it) — somebody ELSE's SKILL.md, which is a
#: perfectly ordinary artifact to be asked about.
OTHER_SKILL_MD = [
    ("WebFetch", {"url": "https://github.com/someone/their-skill/blob/main/SKILL.md"},
     "wdyt https://github.com/someone/their-skill"),
    ("Read", {"file_path": "/downloads/somebodys-skill/SKILL.md"},
     "check this out, i dropped it at /downloads/somebodys-skill/SKILL.md"),
]


def test_a_different_skills_skill_md_is_not_this_skills_recovery_leak():
    """D4: read_skill_content returned True for ANY file named SKILL.md."""
    for _tool, tool_input, _prompt in OTHER_SKILL_MD:
        blob = json.dumps(tool_input)
        assert transcript_mod.refers_to_skill_content("demo", blob) is False, blob
        t = transcript(ndjson(ev_init(), ev_tool_use("Read", tool_input), ev_result(BLAND)))
        assert t.read_skill_content("demo") is False, tool_input


def test_a_different_skills_skill_md_is_valid_ingest_evidence():
    """D3: those same reads were being excluded from evidence for the same reason."""
    fn = checks_mod.CHECK_REGISTRY["ingests_full_artifact_not_metadata"]
    for tool, tool_input, prompt in OTHER_SKILL_MD:
        ctx = ctx_with_prompt(prompt, (tool, tool_input))
        assert fn(ctx).passed is True, f"{tool_input} was excluded as skill content"


def test_the_skills_own_materialised_copy_is_still_the_recovery_leak():
    """The tightening must not stop catching the leak it exists for."""
    for tool_input, tool in [
        ({"file_path": "/tmp/skilleval-x/.claude/skills/demo/SKILL.md"}, "Read"),
        ({"path": ".claude/skills/demo", "pattern": "USE WHEN"}, "Grep"),
        ({"command": "cat .claude/skills/demo/SKILL.md"}, "Bash"),
        ({"command": "cat .claude/skills/*/SKILL.md"}, "Bash"),
        ({"file_path": "demo/SKILL.md"}, "Read"),
        # the repo's own bucket layout, `skills/<bucket>/<skill>/`
        ({"file_path": "/repo/skills/research/demo/references/lens.md"}, "Read"),
        ({"pattern": "trigger", "path": "/repo/skills/research/demo"}, "Grep"),
    ]:
        t = transcript(ndjson(ev_init(), ev_tool_use(tool, tool_input), ev_result(BLAND)))
        assert t.read_skill_content("demo") is True, tool_input


def test_the_needle_does_not_match_a_neighbouring_skill_with_a_shared_prefix():
    """`\\b` matched `demo-notes`; a path component must end where the name ends."""
    for tool_input in [
        {"file_path": "/repo/skills/research/demo-notes/SKILL.md"},
        {"file_path": "/repo/skills/research/demonstration/README.md"},
    ]:
        t = transcript(ndjson(ev_init(), ev_tool_use("Read", tool_input), ev_result(BLAND)))
        assert t.read_skill_content("demo") is False, tool_input


def test_recovery_detection_can_be_scoped_to_the_case_workspace():
    ws = "/tmp/skilleval-c1-1-abc"
    t = transcript(ndjson(
        ev_init(),
        ev_tool_use("Read", {"file_path": f"{ws}/.claude/skills/demo/SKILL.md"}),
        ev_result(BLAND)))
    assert t.read_skill_content("demo", ws) is True


# -- D7: ingest evidence is scoped to the case's own artifact ---------------


def ctx_with_prompt(prompt: str, *tool_uses, skill="demo", aliases=()):
    events = [ev_init()]
    for i, (name, tool_input) in enumerate(tool_uses, start=1):
        events.append(ev_tool_use(name, tool_input, tid=f"t{i}"))
    events.append(ev_result(BLAND))
    return checks_mod.CheckContext(
        case={"id": "c", "prompt": prompt, "should_trigger": True,
              "artifact_aliases": list(aliases)},
        skill=skill,
        transcript=transcript(ndjson(*events)),
    )


ARTIFACT_PROMPT = "wdyt https://github.com/gepa-ai/gepa"


def test_ingest_evidence_rejects_a_read_of_an_unrelated_file():
    """D7 decision: a Read is scoped to the case's artifact, not accepted as such."""
    fn = checks_mod.CHECK_REGISTRY["ingests_full_artifact_not_metadata"]
    ctx = ctx_with_prompt(ARTIFACT_PROMPT, ("Read", {"file_path": "/etc/hosts"}))
    assert fn(ctx).passed is False


def test_ingest_evidence_accepts_every_genuine_route_to_the_artifact():
    """The tightening must not false-fail a run that really did ingest it."""
    fn = checks_mod.CHECK_REGISTRY["ingests_full_artifact_not_metadata"]
    genuine = [
        ("WebFetch", {"url": "https://github.com/gepa-ai/gepa"}),
        ("WebFetch", {"url": "https://raw.githubusercontent.com/gepa-ai/gepa/main/README.md"}),
        ("WebSearch", {"query": "gepa-ai optimizer local GPU requirement"}),
        ("Read", {"file_path": "/tmp/clone/gepa/src/optimizer.py"}),
        ("Bash", {"command": "git clone https://github.com/gepa-ai/gepa /tmp/gepa"}),
    ]
    for name, tool_input in genuine:
        ctx = ctx_with_prompt(ARTIFACT_PROMPT, (name, tool_input))
        assert fn(ctx).passed is True, f"{name} {tool_input} rejected: {fn(ctx).detail}"
    # ...and one unrelated call alongside a genuine one still passes
    ctx = ctx_with_prompt(ARTIFACT_PROMPT,
                          ("Read", {"file_path": "/etc/hosts"}),
                          ("WebFetch", {"url": "https://github.com/gepa-ai/gepa"}))
    assert fn(ctx).passed is True


def test_ingest_evidence_stays_permissive_when_the_prompt_names_no_artifact():
    """A bare-topic case has nothing to scope to; failing it would be a false-fail."""
    fn = checks_mod.CHECK_REGISTRY["ingests_full_artifact_not_metadata"]
    ctx = ctx_with_prompt("check this out, i got CI from 11 minutes down to 90 seconds",
                          ("Read", {"file_path": "/tmp/notes.txt"}))
    assert fn(ctx).passed is True


def test_artifact_tokens_ignore_segments_that_discriminate_nothing():
    toks = checks_mod._artifact_tokens("look at https://github.com/gepa-ai/gepa/blob/main/README.md")
    assert "gepa-ai" in toks and "gepa" in toks
    for generic in ("github", "blob", "main", "readme.md", "com"):
        assert generic not in toks


# -- N2: artifact scoping must be ARTIFACT-level, never HOST-level ----------

INGEST_FN = checks_mod.CHECK_REGISTRY["ingests_full_artifact_not_metadata"]


def test_artifact_tokens_never_leak_the_dotted_host():
    """N2 root: `_PROMPT_PATH_RE` split `github.com/gepa-ai/gepa` and kept `github.com`.

    The stoplist could not catch it — it holds `github` and `com` as separate
    segments, and the dotted host is neither. Nor could it catch the STEM
    `www.youtube` that `www.youtube.com` produced.
    """
    leaks = {
        "wdyt https://github.com/gepa-ai/gepa": {"github.com"},
        "this paper, arxiv.org/abs/2602.12670. worth a look?": {"arxiv.org"},
        "https://www.youtube.com/watch?v=_R83pFpUWyM thoughts": {"www.youtube.com", "www.youtube"},
        "https://x.com/0xcodez/status/2079165300625330317 thoughts?": {"x.com"},
    }
    for prompt, hosts in leaks.items():
        toks = checks_mod._artifact_tokens(prompt)
        assert not (toks & hosts), f"host-level token survived in {prompt!r}: {toks & hosts}"
        assert toks, f"{prompt!r} lost ALL tokens — an empty set is VACUOUSLY permissive"


def test_artifact_tokens_keep_a_dotted_token_whose_own_parts_are_distinctive():
    """FALSE-POSITIVE PROOF: the dotted rule must not eat real artifact names."""
    assert "2602.12670" in checks_mod._artifact_tokens("arxiv.org/abs/2602.12670")
    assert "julianealborna" in checks_mod._artifact_tokens("https://www.julianealborna.com")
    assert "huxe" in checks_mod._artifact_tokens("https://www.huxe.com/")


def test_artifact_tokens_ignore_a_slash_used_as_prose():
    """`founder/creator` and `role/x` are not paths, and were minting real tokens."""
    toks = checks_mod._artifact_tokens(
        "lets research https://x.com/gethuxe https://www.huxe.com/\nAny OSS, reverse "
        "engineer approach or tracing down the founder/creator to find details?")
    assert "gethuxe" in toks and "huxe" in toks
    for prose in ("founder", "creator"):
        assert prose not in toks
    assert "role" not in checks_mod._artifact_tokens(
        "Check this out as it relates to the role/x skill https://github.com/gepa-ai/gepa")


def test_ingest_evidence_rejects_a_different_artifact_on_the_same_host():
    """MEASURED false-passes before the fix — every one of these scored PASS."""
    wrong = [
        ("wdyt https://github.com/gepa-ai/gepa",
         ("WebFetch", {"url": "https://github.com/torvalds/linux"})),
        ("this paper, arxiv.org/abs/2602.12670. worth a look?",
         ("WebFetch", {"url": "https://arxiv.org/abs/1706.03762"})),
        ("https://www.youtube.com/watch?v=_R83pFpUWyM thoughts",
         ("WebFetch", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})),
        ("wdyt https://github.com/gepa-ai/gepa",
         ("Read", {"file_path": "/var/log/github.com.log"})),
        ("https://x.com/0xcodez/status/2079165300625330317 thoughts?",
         ("WebFetch", {"url": "https://x.com/someoneelse/status/1234567890123456789"})),
        ("lets research the founder/creator behind https://www.huxe.com/",
         ("WebFetch", {"url": "https://techcrunch.com/2026/founder-interview"})),
    ]
    for prompt, tool in wrong:
        res = INGEST_FN(ctx_with_prompt(prompt, tool))
        assert res.passed is False, f"{tool} passed for {prompt!r}: {res.detail}"


#: golden-04's three realistic correct ingest routes. The status body is the empty
#: string and its raw_text is a bare t.co link, so the substance lives one
#: indirection away at x.com/i/article/… — a URL sharing NO token with the prompt
#: except the host. Host-level scoping is what used to let these through.
GOLDEN_04_PROMPT = "https://x.com/0xcodez/status/2079165300625330317 thoughts?"
GOLDEN_04_ALIASES = ["https://t.co/WVztfCUH4u",
                     "https://x.com/i/article/2079141496981184512"]
GOLDEN_04_ROUTES = [
    ("WebFetch", {"url": "https://x.com/0xcodez/status/2079165300625330317"}),
    ("WebFetch", {"url": "https://x.com/i/article/2079141496981184512"}),
    ("WebFetch", {"url": "https://api.fxtwitter.com/0xCodez/status/2079165300625330317"}),
]


def test_a_declared_alias_admits_the_indirection_route_and_nothing_else():
    """FALSE-POSITIVE PROOF for the alias field, plus proof it is not a hole."""
    for tool in GOLDEN_04_ROUTES:
        res = INGEST_FN(ctx_with_prompt(GOLDEN_04_PROMPT, tool, aliases=GOLDEN_04_ALIASES))
        assert res.passed is True, f"false-failed a correct route {tool}: {res.detail}"
    # The alias is additive: a DIFFERENT article on the same host still fails.
    for wrong in [("WebFetch", {"url": "https://x.com/i/article/9999999999999999999"}),
                  ("WebFetch", {"url": "https://x.com/someoneelse/status/1111111111111111111"})]:
        res = INGEST_FN(ctx_with_prompt(GOLDEN_04_PROMPT, wrong, aliases=GOLDEN_04_ALIASES))
        assert res.passed is False, f"the alias widened scope to {wrong}: {res.detail}"


def test_the_pilot_declares_the_alias_golden_04_depends_on():
    """The alias declaration must survive the check's withdrawal.

    `ingests_full_artifact_not_metadata` was withdrawn from every pilot case on
    2026-07-28 (see known_gaps.checks_withdrawn_2026_07_28) because it oscillated
    between host-level over-scoping and failing OPEN on one-slash references.
    The ALIAS data is orthogonal to that and stays: golden-04's substance sits
    behind a t.co redirect, so any future artifact-scoped check — regex or judge —
    needs the resolved URL declared or the correct route scores FAIL while a
    wrong-artifact fetch on the same host scores PASS.

    So this pins the data, and pins that the predicate still honours it, WITHOUT
    asserting the withdrawn check is wired into the case.
    """
    ps = R.load_prompt_set(PILOT)
    g4 = next(c for c in ps.cases if c.id == "golden-04")
    assert "ingests_full_artifact_not_metadata" not in g4.expected_checks, (
        "check is withdrawn; re-wiring it requires re-proving BOTH directions first"
    )
    assert g4.artifact_aliases, "golden-04 must keep its resolved-artifact aliases"
    for tool in GOLDEN_04_ROUTES:
        res = INGEST_FN(ctx_with_prompt(g4.prompt, tool, aliases=g4.artifact_aliases))
        assert res.passed is True, f"pilot golden-04 false-fails {tool}: {res.detail}"


def test_no_pilot_case_asserting_ingest_has_an_empty_token_set():
    """Over-tightening fails OPEN: zero tokens means `_hits_artifact` is vacuous.

    A stoplist entry too many would silently turn the strictest check in the set
    back into "did the agent call any content-pulling tool at all".
    """
    ps = R.load_prompt_set(PILOT)
    for c in ps.cases:
        if "ingests_full_artifact_not_metadata" not in c.expected_checks:
            continue
        toks = checks_mod._case_artifact_tokens(
            {"prompt": c.prompt, "artifact_aliases": c.artifact_aliases})
        assert toks, f"{c.id} asserts ingest scoping but scopes to nothing"


# -- over-strictness introduced in round 2 (both arms) ----------------------

BOUNCE_FN = checks_mod.CHECK_REGISTRY["no_clarifying_question_bounced_back"]
NON_EMPTY_FN = checks_mod.CHECK_REGISTRY["final_answer_non_empty"]

#: Bounded answers that close by offering a next step — SKILL.md's prescribed
#: shape on a NEGATIVE, and what the round-2 interrogative_stub arm false-failed.
ANSWER_THEN_OFFER = [
    "Nice, that is a 7x cut. Killing the docker layer rebuild is usually the single "
    "biggest win on a Python CI. Want me to write that up as a note?",
    "No local GPU needed. The optimizer loop calls an API endpoint, so a small box "
    "is fine. Should I sketch the instance sizing?",
    "Renamed and documented:\n\ndef acquire(leaseManager, key, ttl):\n    ...\n\n"
    "Logic untouched. Want the same treatment on the sibling helper?",
    "Hold it. Your adversarial round finds a blocker most times, and Friday means "
    "the fix lands on a weekend. Shall I queue the review for Monday morning?",
]

BOUNCES = [
    "Which repo did you mean, and what output do you want?",
    "Before I dig in — what exactly are you after here?",
    "Sure! Just to clarify, should I focus on the runtime or the docs?",
    "Got it. Which one?",
    "Happy to help. What would you like me to focus on: the optimizer, the API "
    "surface, the deployment story, or something else entirely?",
]


def test_no_clarifying_question_passes_a_bounded_answer_that_offers_a_next_step():
    """FALSE-POSITIVE PROOF: correct behaviour on a negative must not be scored FAIL."""
    for final in ANSWER_THEN_OFFER:
        ctx = ctx_for(ndjson(ev_init(), ev_result(final)))
        res = BOUNCE_FN(ctx)
        assert res.passed is True, f"false-failed a correct answer: {res.detail}\n{final}"


def test_no_clarifying_question_still_catches_a_real_bounce():
    for final in BOUNCES:
        ctx = ctx_for(ndjson(ev_init(), ev_result(final)))
        assert BOUNCE_FN(ctx).passed is False, f"missed a bounce: {final}"


def test_direction_seeking_is_scoped_to_the_trailing_question():
    """FALSE-POSITIVE PROOF for the direction rule: a mid-answer 'which' is fine."""
    for final in [
        "No local GPU needed, it calls an API endpoint. Which endpoint depends on "
        "your config, but that is a one-line change. Want the numbers?",
        "The optimizer loop is pure API. I pulled the benchmark table, which lives "
        "in the README, and it matches. Should I paste it here?",
        "Done. The layer cache was the whole story, which is why the 11-minute "
        "baseline collapsed to 90 seconds.",
    ]:
        res = BOUNCE_FN(ctx_for(ndjson(ev_init(), ev_result(final))))
        assert res.passed is True, f"false-failed: {res.detail}\n{final}"


def test_no_clarifying_question_catches_a_long_bounce_the_length_rule_would_miss():
    """The old rule only fired under 400 chars, so a verbose bounce sailed through."""
    final = ("So there are a few directions this could go, and they pull apart quite a "
             "lot depending on what you actually care about here. " + "x " * 200 +
             "Which of those would you like me to take?")
    assert len(final) > 400
    assert BOUNCE_FN(ctx_for(ndjson(ev_init(), ev_result(final)))).passed is False


# -- B1: a bounce is a QUESTION, and an offer is not one just for saying "which" --

#: CLASS A — declarative sentences that merely BEGIN with an interrogative word.
#: Zero question marks between them. The round-3 opener rule was a bare prefix
#: match with no interrogative requirement, so all seven scored "opens with a
#: clarifying question". This check is asserted on 17 of 17 pilot cases and is the
#: sole behavioural discriminator on all six negatives, so false-failing correct
#: behaviour here poisons the whole pilot.
DECLARATIVE_OPENERS = [
    "Which one wins depends on how often you bump the lockfile. At twice a week, leave it.",
    "Before we build a second image, note that the dep layer only invalidates on a lockfile bump.",
    "What would break first is the nightly job, not the CI run, so the split buys you very little.",
    "Which of these matters depends on your bump cadence, and yours is low.",
    "Should i-style hedging aside, the answer is: leave it as is for now.",
    "Do you want the short version: keep it. The cold-build cost is amortised on a weekly bump.",
    "How the layer cache behaves is the whole story here, and yours only invalidates twice a week.",
]

#: CLASS B — offers whose OBJECT clause contains the words the round-3 direction
#: rule searched for anywhere in the trailing question. The agent has already named
#: the action; the user only says yes or no. This is SKILL.md's prescribed closing
#: shape, and 6 of 8 realistic offers were being rejected.
OFFERS_WITH_A_WH_OBJECT = [
    "It ships as a Rust binary with a thin TS wrapper. Want me to benchmark which one is faster?",
    "The optimizer calls an API endpoint, no local GPU. Want me to check which of these "
    "actually ships a stable API?",
    "Layer caching was the whole story. Should I test which approach is cheaper?",
    "The regression landed in the reducer. Want me to bisect which direction it came from?",
    "It is a single upsert with a CAS predicate. Want me to write up which option we should take?",
    "No GPU needed. Should I sketch what I should focus on next week?",
    "Both ship a stable API. Want me to write up what you want the wrapper to expose?",
    "The cold path is the only loser here. How about I benchmark it and report back?",
]

#: A wh-question the agent ANSWERS ITSELF is a rhetorical device, not a bounce —
#: the user is never asked to supply anything. Nothing in the pilot may false-fail
#: on it, and it is the shape a "require an actual question" rule alone would break.
RHETORICAL_QUESTIONS = [
    "What breaks first? The nightly job, not the CI run, so the split buys you very little.",
    "So what actually changed? Three things: the lockfile order, the cache key, and the base image.",
]

#: Bounces the round-3 prefix/trailing rules MISSED — kept so the fix is proven to
#: be strictly more sensitive on real bounces, not merely more permissive.
BOUNCES_THE_OLD_RULES_MISSED = [
    "I can go either way on this one. Which repo did you mean? Let me know and I will start.",
    "The wrapper is thin. How do you want me to handle the retry path?",
]

#: Bounces that carry a real body, so no whole-turn arm can be what catches them.
BOUNCES_WITH_A_BODY = [
    "I skimmed both repos and they overlap a lot in scope. Which of the two should I start with?",
    "Before I dig in, what exactly are you after here? I can go either way.",
    "There are two readings of that. Could you clarify which one you meant?",
    "I have the repo open. What should I focus on first?",
]


def test_a_declarative_sentence_starting_with_which_is_not_a_clarifying_question():
    """B1 CLASS A: 7 of 7 answers containing ZERO questions were scored FAIL."""
    for final in DECLARATIVE_OPENERS:
        assert "?" not in final, f"corpus error, this one is a question: {final}"
        res = BOUNCE_FN(ctx_for(ndjson(ev_init(), ev_result(final))))
        assert res.passed is True, f"false-failed a question-free answer: {res.detail}\n{final}"


def test_an_offer_may_contain_a_wh_word_inside_its_object_clause():
    """B1 CLASS B: fronting, not presence, is what separates a bounce from an offer."""
    for final in OFFERS_WITH_A_WH_OBJECT:
        res = BOUNCE_FN(ctx_for(ndjson(ev_init(), ev_result(final))))
        assert res.passed is True, f"false-failed a correct offer: {res.detail}\n{final}"


def test_a_rhetorical_question_the_agent_answers_itself_is_not_a_bounce():
    for final in RHETORICAL_QUESTIONS:
        res = BOUNCE_FN(ctx_for(ndjson(ev_init(), ev_result(final))))
        assert res.passed is True, f"false-failed a rhetorical opener: {res.detail}\n{final}"


def test_a_bounce_with_a_substantive_body_is_still_a_bounce():
    """Length was never the discriminator, and neither is the whole-turn arm."""
    for final in BOUNCES_WITH_A_BODY + BOUNCES_THE_OLD_RULES_MISSED:
        res = BOUNCE_FN(ctx_for(ndjson(ev_init(), ev_result(final))))
        assert res.passed is False, f"missed a bounce: {final}"


def test_a_markdown_answer_is_not_read_as_one_sentence():
    """Line breaks end a sentence, or a bulleted answer's FIRST word is read as the
    head word of its closing question — the failure mode a wh-fronting rule opens
    if it is handed one giant blob."""
    final = ("What I found is this:\n- the dep layer invalidates on every commit\n"
             "- the lockfile copy fixes it\nWant me to file it?")
    res = BOUNCE_FN(ctx_for(ndjson(ev_init(), ev_result(final))))
    assert res.passed is True, f"false-failed a markdown answer + offer: {res.detail}"


def test_final_answer_non_empty_accepts_a_short_correct_answer():
    """FALSE-POSITIVE PROOF: the measured 34-char correct answer must pass."""
    final = "No, it just calls an API endpoint."
    assert len(final) == 34
    assert NON_EMPTY_FN(ctx_for(ndjson(ev_init(), ev_result(final)))).passed is True


def test_final_answer_non_empty_still_rejects_emptiness_and_acknowledgements():
    for final in ["", "   ", "ok", "Okay!", "done", "...", "See above.", "n/a", "Sure."]:
        res = NON_EMPTY_FN(ctx_for(ndjson(ev_init(), ev_result(final))))
        assert res.passed is False, f"scored {final!r} as a substantive answer"


# -- D6: stale_fixtures is reported, not write-only -------------------------


def test_cli_reports_fixtures_recorded_against_a_different_prompt(tmp_path):
    """D6: the field was appended to and never read. Now it has its own guard line."""
    skill_dir, prompts = scaffold(tmp_path)
    fixtures = full_fixtures(tmp_path, skill_dir)
    doc = json.loads(prompts.read_text())
    doc["cases"][0]["prompt"] = "a completely different prompt than was recorded"
    prompts.write_text(json.dumps(doc), encoding="utf-8")

    report = tmp_path / "report.json"
    rc, _out, err = run_cli("--skill", "demo", "--skills-root", str(tmp_path / "skills"),
                            "--replay", str(fixtures), "--trials", "3",
                            "--report", str(report))
    assert rc == R.EXIT_FIXTURES
    assert "recorded against a DIFFERENT PROMPT" in err
    meta = json.loads(report.read_text())["meta"]
    assert meta["stale_prompt_fixtures"], "stale_fixtures never reached the report"


# -- PIN THE EVAL DATA ------------------------------------------------------


def test_every_pilot_case_asserts_at_least_one_check():
    """A case with no expected_checks asserts nothing beyond trigger/no-trigger.

    The eval-set review's finding was that NOTHING PINNED THE FIX: the pilot
    contract test asserted only case counts and known check ids, so reverting all
    six negatives to `expected_checks: []` stayed green. On a negative that is the
    difference between "the skill stayed quiet" and "the skill stayed quiet AND
    the run still answered the user", which is the whole point of a near-miss.
    """
    ps = R.load_prompt_set(PILOT)
    bare = [c.id for c in ps.cases if not c.expected_checks]
    assert not bare, f"cases assert nothing beyond trigger/no-trigger: {bare}"
    bare_negatives = [c.id for c in ps.negatives if not c.expected_checks]
    assert not bare_negatives, f"negatives with no assertions: {bare_negatives}"


def test_pilot_negatives_assert_the_run_still_answered_the_user():
    """The specific assertions that make a negative more than an abstention check."""
    ps = R.load_prompt_set(PILOT)
    for c in ps.negatives:
        assert "final_answer_non_empty" in c.expected_checks, (
            f"{c.id} does not assert the run produced an answer at all")


# --- the invariant that made `completed_without_error` vacuous ---------------

def test_error_transcripts_never_reach_run_checks(monkeypatch):
    """WHY `completed_without_error` was deleted from CHECK_REGISTRY.

    It read `ok = not ctx.transcript.is_error`. But grade_trial returns
    out(ERROR, ...) on `if transcript.is_error:` BEFORE run_checks is reached, so
    the only condition it tested could never arrive at it — every invocation
    returned True. A structurally unfailable check, sitting in the registry of a
    harness built to catch exactly that, asserted on 11 cases across two prompt
    sets before two independent reviewers found it.

    This pins the ordering. If a refactor ever lets an errored transcript reach
    run_checks, a check keyed on is_error becomes meaningful again — and this
    test going RED is the signal to reconsider, rather than someone silently
    re-adding a predicate that cannot fail.
    """
    called: list[list[str]] = []
    real = checks_mod.run_checks
    monkeypatch.setattr(checks_mod, "run_checks",
                        lambda ids, ctx: called.append(list(ids)) or real(ids, ctx))

    stream = ndjson(ev_init(), ev_result("Not logged in", is_error=True))
    tr = transcript(stream)
    assert tr.is_error is True, "fixture must actually be an error transcript"

    r = R.grade_trial(case(), tr, "demo")
    assert r.outcome == R.ERROR, r.outcome
    assert called == [], "run_checks ran on an errored transcript — the ordering changed"


def test_completed_without_error_is_not_resurrectable_silently():
    """Removed from CHECK_REGISTRY deliberately, not by accident.

    Deletion (rather than leaving a no-op) is what makes a prompt set that still
    asserts it fail loudly with 'unknown check id' instead of quietly scoring a
    free pass on every case.
    """
    assert "completed_without_error" not in checks_mod.CHECK_REGISTRY
    pilots = sorted((REPO / "skills").rglob("evals/prompts.json"))
    assert pilots, "no prompt sets found — the guard below would be vacuous"
    for p in pilots:
        data = json.loads(p.read_text(encoding="utf-8"))
        for case in data.get("cases", []):
            assert "completed_without_error" not in case.get("expected_checks", []), (
                f"{p}: case {case.get('id')} still asserts the removed check"
            )


# ---------------------------------------------------------------------------
# BRO-2028: the `bare` visibility arm — does a skill trigger on its NAME alone?
# ---------------------------------------------------------------------------


def test_strip_description_removes_the_key_and_keeps_the_body_byte_identical():
    src = "---\nname: demo\ndescription: fires on X\nother: keep\n---\n# body\n\ntext\n"
    out = R.strip_frontmatter_description(src)
    assert R.parse_frontmatter_description(out) == ""
    assert "name: demo" in out and "other: keep" in out
    # the body is the contract: rationing truncates the LISTING, not the file
    assert out.split("---\n", 2)[2] == src.split("---\n", 2)[2]


@pytest.mark.parametrize("desc", [
    "description: >\n  folded line one\n  folded line two\n",
    "description: |\n  literal line one\n  literal line two\n",
    'description: "quoted with: a colon"\n',
    "description: plain that wraps\n  onto a second line\n",
])
def test_strip_description_consumes_every_scalar_shape(desc):
    """Each shape spans a different number of lines; a stripper that only removes
    the `description:` line leaves the continuation behind as stray YAML."""
    src = f"---\nname: demo\n{desc}trailing: kept\n---\n# body\n"
    out = R.strip_frontmatter_description(src)
    assert R.parse_frontmatter_description(out) == ""
    assert "trailing: kept" in out
    assert "folded" not in out and "literal" not in out and "wraps" not in out


def test_strip_description_refuses_when_there_is_nothing_to_strip():
    """The load-bearing guard: a silent no-op makes the bare arm identical to the
    present arm, and the experiment reports 'the name alone is sufficient' having
    never removed a description."""
    with pytest.raises(R.SkillArtifactError, match="no top-level 'description:'"):
        R.strip_frontmatter_description("---\nname: demo\n---\n# body\n")


def test_strip_description_refuses_without_frontmatter():
    with pytest.raises(R.SkillArtifactError, match="no YAML frontmatter"):
        R.strip_frontmatter_description("# just a body\n")


def test_strip_description_postcondition_holds_on_every_real_skill_md():
    """Property, not enumeration (this arc's lesson 6): assert the postcondition
    with the SAME parser the harness grades with, over the real corpus, rather
    than over the shapes the author happened to think of."""
    checked = 0
    for path in ALL_SKILL_MDS:
        text = path.read_text(encoding="utf-8")
        if not R.parse_frontmatter_description(text).strip():
            continue  # no description to strip; not this function's case
        out = R.strip_frontmatter_description(text)
        assert R.parse_frontmatter_description(out) == "", f"description survived in {path}"
        assert out.split("---\n", 2)[2:] == text.split("---\n", 2)[2:], f"body moved in {path}"
        checked += 1
    assert checked > 20, f"corpus too small to be meaningful ({checked})"


def test_materialize_bare_strips_the_copy_and_never_the_source(tmp_path):
    skill_dir = make_skill(tmp_path, name="demo")
    before = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    R._materialize_bare(ws, skill_dir, "demo")

    installed = ws / ".claude" / "skills" / "demo" / "SKILL.md"
    assert R.parse_frontmatter_description(installed.read_text(encoding="utf-8")) == ""
    # SOURCE untouched -> skill_fingerprint(skill_dir) is stable -> replay binding holds
    assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == before
    assert R.skill_fingerprint(skill_dir)["description_sha256"] == \
        R.skill_fingerprint(skill_dir)["description_sha256"]


def test_materialize_bare_keeps_the_body_so_RECOVERED_stays_distinguishable(tmp_path):
    """If the bare arm deleted the body, 'read SKILL.md without triggering' would
    collapse into FAIL and the experiment could not attribute a result to a
    mechanism."""
    skill_dir = make_skill(tmp_path, name="demo")
    ws = tmp_path / "ws"
    ws.mkdir()
    R._materialize_bare(ws, skill_dir, "demo")
    assert "# body" in (ws / ".claude" / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8")


def test_bare_is_registered_as_visible_so_anti_vacuity_still_applies():
    v = R.VISIBILITY_REGISTRY["bare"]
    # A bare skill IS on the roster. expects_visible=False would disable the
    # INVISIBLE check and let a loader that drops description-less skills read as
    # a zero-lift result instead of a visibility bug.
    assert v.expects_visible is True
    assert "bare" in R.ABLATION_BASELINES


def test_bare_arm_is_graded_on_triggering_not_outcome_only():
    """The absent arm grades outcome-only because 'did it fire' is unanswerable
    there. For bare it is THE question, so it must take the trigger-aware path."""
    stream = ndjson(ev_init(skills=("demo",)), ev_result("answered without the skill"))
    r = R.grade_trial(case(should_trigger=True), transcript(stream), "demo",
                      expect_visible=R.VISIBILITY_REGISTRY["bare"].expects_visible)
    assert r.outcome == R.FAIL
    assert "did not trigger" in r.detail
    assert "outcome-only" not in r.detail


def test_bare_arm_scores_invisible_if_the_loader_drops_descriptionless_skills():
    """A finding about the loader, not a zero-lift result — and it must not be
    readable as one."""
    stream = ndjson(ev_init(skills=("other",)), ev_result("nope"))
    r = R.grade_trial(case(should_trigger=True), transcript(stream), "demo",
                      expect_visible=R.VISIBILITY_REGISTRY["bare"].expects_visible)
    assert r.outcome == R.INVISIBLE


def test_baseline_cases_absent_drops_negatives_but_bare_keeps_them():
    """An uninstalled skill cannot over-trigger; a BARE one can — it is installed.
    Dropping its negatives would leave 'the name is a sufficient trigger' and 'the
    name is an indiscriminate one' indistinguishable."""
    ps = R.parse_prompt_set(prompt_set_doc("demo", cases=[
        {"id": "pos", "prompt": "p", "should_trigger": True, "origin": "golden",
         "expected_checks": ["final_answer_non_empty"]},
        {"id": "neg", "prompt": "n", "should_trigger": False, "origin": "negative",
         "expected_checks": ["final_answer_non_empty"]},
    ]))
    assert [c.id for c in R._baseline_cases(ps, "absent")] == ["pos"]
    assert sorted(c.id for c in R._baseline_cases(ps, "bare")) == ["neg", "pos"]
