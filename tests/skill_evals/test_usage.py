"""Tests for scripts/skill_evals/usage.py — the skill-usage measurement.

Every test here pins a decision that, if silently reverted, would make the
ranking wrong in a way nobody would notice — which is the failure mode the whole
eval arc exists to catch. Two are direct regression guards for contamination
traps that materially changed the measured ranking.
"""
from __future__ import annotations

import json

from skill_evals import usage as U


# --- realistic transcript rows ------------------------------------------------
# Shapes copied from real Claude Code 2.1.x transcripts (2026-11): one API response
# is split across rows that repeat its message id and usage; a Skill call's input
# also appears in `wireToolInputs`; the skill body arrives as an isMeta user row.

def resp(mid, blocks, usage=(10, 0, 100, 5)):
    u = dict(zip(("input_tokens", "cache_creation_input_tokens",
                  "cache_read_input_tokens", "output_tokens"), usage))
    return [{"type": "assistant", "isSidechain": False,
             "message": {"id": mid, "usage": u, "content": [b]}} for b in blocks]


def skill_call(mid, tid, name, usage=(10, 0, 100, 5)):
    rows = resp(mid, [{"type": "tool_use", "id": tid, "name": "Skill", "input": {"skill": name}}],
                usage)
    rows[0]["wireToolInputs"] = {tid: {"skill": name}}
    return rows + [
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "content": f"Launching skill: {name}"}]}},
        {"type": "user", "isMeta": True, "sourceToolUseID": tid,
         "message": {"content": [{"type": "text",
                                  "text": f"Base directory for this skill: /s/{name}\n# {name}"}]}},
    ]


def typed(name, args=""):
    return [
        {"type": "user", "message": {"content":
            f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>"
            + (f"\n<command-args>{args}</command-args>" if args else "")}},
        {"type": "user", "isMeta": True, "message": {"content": [
            {"type": "text", "text": f"{args} Base directory for this skill: /s/{name}\n# {name}"}]}},
    ]


def prompt(text="next"):
    return [{"type": "user", "message": {"content": text}}]


def lines(*groups):
    return b"".join(json.dumps(r).encode() + b"\n" for g in groups for r in g)


def calls(*names):
    return lines(*[skill_call(f"m{i}", f"t{i}", n) for i, n in enumerate(names)])


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
    payload = calls("autonomous")
    (root / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(payload)
    (root / "agent-deadbeef.jsonl").write_bytes(calls(*["autonomous"] * 5))
    (root / "journal.jsonl").write_bytes(calls(*["autonomous"] * 5))

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
        calls(*["autonomous"] * 99, "checkit"))

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
        calls("autonomous", "impeccable", "claude-api"))

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
        calls(*["kg"] * 2, *["autonomous"] * 9, *["handoff"] * 5))
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
    (tr / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(calls("autonomous"))
    assert U.main(["--transcripts", str(tmp_path / "projects"),
                   "--skills-root", str(sr), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["owned_invocations"] == 1
    assert payload["ranked"][0]["skill"] == "autonomous"


# --- BRO-4111: structural counting, who chose it, and what it cost ----------------

def _rows(payload: bytes) -> list[dict]:
    return [json.loads(x) for x in payload.splitlines() if x.strip()]


def test_one_call_counts_once_despite_its_input_appearing_twice():
    """REGRESSION. The byte regex counted a call's `input` AND its `wireToolInputs`,
    and any later text that quoted the call. A real transcript with 2 Skill calls
    scored 5."""
    rows = _rows(calls("kg")) + prompt('they ran {"skill": "kg"} earlier')
    invs = U.session_invocations(rows)
    assert [i["skill"] for i in invs] == ["kg"]


def test_a_typed_command_is_counted_as_chosen_by_the_user():
    """REGRESSION. `/checkit` typed by a person is never a Skill tool call, so the
    regex never saw it: the skill the owner types most read as almost unused."""
    invs = U.session_invocations(_rows(lines(typed("checkit", "https://x.com/a"))))
    assert invs == [{"skill": "checkit", "invoked_by": "user", "cost": None}]


def test_an_agent_call_is_not_also_counted_from_its_skill_body():
    """The body row of an agent call carries sourceToolUseID; counting it as a typed
    load would double every agent invocation."""
    invs = U.session_invocations(_rows(calls("kg")))
    assert [(i["skill"], i["invoked_by"]) for i in invs] == [("kg", "agent")]


def test_a_split_response_is_costed_once():
    """REGRESSION. One API response spans several rows repeating the same usage;
    summing rows multiplies the cost."""
    rows = _rows(lines(
        skill_call("m0", "t0", "kg", usage=(5, 0, 1000, 10)),
        resp("m1", [{"type": "text", "text": "a"}, {"type": "text", "text": "b"},
                    {"type": "tool_use", "id": "x", "name": "Bash", "input": {}}],
             usage=(3, 200, 1000, 40)),
        prompt(),
    ))
    cost = U.session_invocations(rows)[0]["cost"]
    assert cost["turns"] == 1
    assert cost["output_tokens"] == 40
    assert cost["cache_write_tokens"] == 200


def test_the_window_ends_at_the_next_human_prompt():
    rows = _rows(lines(
        skill_call("m0", "t0", "kg"),
        resp("m1", [{"type": "text", "text": "done"}], usage=(1, 0, 0, 7)),
        prompt(),
        resp("m2", [{"type": "text", "text": "unrelated"}], usage=(1, 0, 0, 999)),
    ))
    cost = U.session_invocations(rows)[0]["cost"]
    assert cost["turns"] == 1 and cost["output_tokens"] == 7


def test_the_window_ends_at_the_next_skill_load():
    rows = _rows(lines(
        skill_call("m0", "t0", "kg"),
        resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 7)),
        skill_call("m2", "t1", "p9"),
        resp("m3", [{"type": "text", "text": "y"}], usage=(1, 0, 0, 11)),
    ))
    first, second = U.session_invocations(rows)
    # The response that calls p9 (5 output tokens) was produced inside kg's window,
    # so it is charged there; p9's window starts after it.
    assert first["cost"]["turns"] == 2 and first["cost"]["output_tokens"] == 7 + 5
    assert second["cost"]["output_tokens"] == 11


def test_context_added_is_the_growth_in_total_input():
    rows = _rows(lines(
        skill_call("m0", "t0", "kg", usage=(10, 0, 1000, 5)),
        resp("m1", [{"type": "text", "text": "x"}], usage=(2, 800, 1010, 5)),
    ))
    assert U.session_invocations(rows)[0]["cost"]["context_added"] == (2 + 800 + 1010) - (10 + 0 + 1000)


def test_context_added_after_a_compaction_is_unmeasured_not_negative():
    rows = _rows(lines(
        skill_call("m0", "t0", "kg", usage=(10, 0, 90000, 5)),
        resp("m1", [{"type": "text", "text": "x"}], usage=(2, 500, 1000, 5)),
    ))
    assert U.session_invocations(rows)[0]["cost"]["context_added"] is None


def test_a_load_with_no_response_after_it_has_null_cost_not_zeros():
    """A session interrupted right after the load: nothing was measured, and a row of
    zeros would read as a free skill."""
    invs = U.session_invocations(_rows(calls("kg")))
    assert invs[0]["cost"] is None
    assert U.cost_summary(invs) is None


def test_subagent_rows_are_ignored():
    side = skill_call("s0", "ts", "kg")
    for r in side:
        r["isSidechain"] = True
    assert U.session_invocations(_rows(lines(side))) == []


def test_the_report_carries_who_chose_it_and_the_median_cost(tmp_path):
    sr = tmp_path / "skills"
    _skill(sr, "research", "checkit")
    tr = tmp_path / "projects" / "p"
    tr.mkdir(parents=True)
    (tr / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(lines(
        typed("checkit"), resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 30)),
        prompt(), skill_call("m2", "t2", "checkit"),
        resp("m3", [{"type": "text", "text": "y"}], usage=(1, 0, 0, 50)),
    ))
    row = U.build_report(tmp_path / "projects", sr)["ranked"][0]
    assert row["invocations"] == 2
    assert row["invoked_by"] == {"agent": 1, "user": 1}
    assert row["cost"]["measured_invocations"] == 2
    assert row["cost"]["median_output_tokens"] == 40.0


# --- P20 #335 round 1: what a window is, measured on real row shapes ----------------

def test_scan_keeps_its_three_value_contract(tmp_path):
    """listing.py unpacks three values; the records live in scan_records()."""
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(calls("kg"))
    out = U.scan(tmp_path)
    assert len(out) == 3 and out[0]["kg"] == 1


def _note(text):
    return [{"type": "user", "message": {"content": text}}]


def test_injected_user_rows_do_not_end_a_window():
    """A task notification, local command output or a compaction summary is written
    by the harness, not typed by a person (727, 41 and 68 such rows in the corpus)."""
    for injected in ("<task-notification>\n<task-id>x</task-id>",
                     "<local-command-stdout>ok</local-command-stdout>",
                     "This session is being continued from a previous conversation that ran out"):
        rows = _rows(lines(
            skill_call("m0", "t0", "kg"),
            _note(injected),
            resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 9)),
        ))
        assert U.session_invocations(rows)[0]["cost"]["output_tokens"] == 9, injected


def test_an_image_prompt_ends_a_window():
    image = [{"type": "user", "message": {"content": [{"type": "image", "source": {}}]}}]
    rows = _rows(lines(
        skill_call("m0", "t0", "kg"),
        resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 7)),
        image,
        resp("m2", [{"type": "text", "text": "y"}], usage=(1, 0, 0, 900)),
    ))
    assert U.session_invocations(rows)[0]["cost"]["output_tokens"] == 7


def test_a_tool_result_with_injected_text_does_not_end_a_window():
    mixed = [{"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "ok"},
        {"type": "text", "text": "<system-reminder>note</system-reminder>"}]}}]
    rows = _rows(lines(
        skill_call("m0", "t0", "kg"),
        resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 4)),
        mixed,
        resp("m2", [{"type": "text", "text": "y"}], usage=(1, 0, 0, 5)),
    ))
    assert U.session_invocations(rows)[0]["cost"]["output_tokens"] == 9


def test_synthetic_assistant_rows_are_not_api_responses():
    synthetic = resp("syn", [{"type": "text", "text": "No response requested."}], usage=(0, 0, 0, 0))
    synthetic[0]["message"]["model"] = "<synthetic>"
    rows = _rows(lines(skill_call("m0", "t0", "kg"), synthetic))
    assert U.session_invocations(rows)[0]["cost"] is None


def test_two_skills_loaded_by_one_response_share_its_window():
    """REGRESSION: by row order the first got cost null and the second got all of it."""
    both = resp("m0", [
        {"type": "tool_use", "id": "t0", "name": "Skill", "input": {"skill": "kg"}},
        {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "p9"}},
    ])
    rows = _rows(lines(both, resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 10))))
    first, second = U.session_invocations(rows)
    assert first["cost"] == second["cost"]
    assert first["cost"]["output_tokens"] == 5 and first["cost"]["shared_with"] == 1


def test_block_order_inside_a_response_does_not_move_cost():
    """REGRESSION: a text block placed before the next Skill block changed the
    previous invocation's cost with identical API usage."""
    def session(order):
        blocks = {"kg": {"type": "tool_use", "id": "a", "name": "Skill", "input": {"skill": "kg"}},
                  "text": {"type": "text", "text": "now p9"},
                  "p9": {"type": "tool_use", "id": "b", "name": "Skill", "input": {"skill": "p9"}}}
        return _rows(lines(resp("m0", [blocks[k] for k in order]),
                           resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 8))))
    a = U.session_invocations(session(["kg", "p9", "text"]))
    b = U.session_invocations(session(["kg", "text", "p9"]))
    assert a == b


def test_context_added_across_a_compaction_is_unmeasured():
    boundary = [{"type": "system", "subtype": "compact_boundary"}]
    rows = _rows(lines(
        skill_call("m0", "t0", "kg", usage=(10, 0, 100, 5)),
        boundary,
        resp("m1", [{"type": "text", "text": "x"}], usage=(2, 0, 188, 5)),
    ))
    assert U.session_invocations(rows)[0]["cost"]["context_added"] is None


def test_a_transcript_written_with_json_spacing_is_still_read(tmp_path):
    (tmp_path / "p").mkdir()
    row = {"type": "assistant", "message": {"id": "m0", "usage": {"output_tokens": 1},
           "content": [{"type": "tool_use", "id": "t0", "name": "Skill", "input": {"skill": "kg"}}]}}
    (tmp_path / "p" / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_text(
        json.dumps(row, separators=(", ", ": ")) + "\n")
    assert U.scan(tmp_path)[0]["kg"] == 1


def test_a_row_whose_message_is_not_an_object_is_skipped():
    rows = [{"type": "assistant", "message": ["not", "an", "object"]},
            {"type": "user", "message": "text"}] + _rows(calls("kg"))
    assert [i["skill"] for i in U.session_invocations(rows)] == ["kg"]


# --- P20 #335 round 2 ----------------------------------------------------------------

def test_the_response_that_calls_the_next_skill_is_charged_to_the_previous_window():
    """REGRESSION: it sat at both windows' boundary and was charged to neither
    (13 real responses, 8,729 output tokens)."""
    calls_gamma = resp("m1", [{"type": "tool_use", "id": "t1", "name": "Skill",
                               "input": {"skill": "gamma"}}], usage=(1, 0, 0, 40))
    rows = _rows(lines(typed("beta"), calls_gamma,
                       resp("m2", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 11))))
    beta, gamma = U.session_invocations(rows)
    assert beta["cost"]["output_tokens"] == 40
    assert gamma["cost"]["output_tokens"] == 11


def test_an_interrupt_beside_a_tool_result_ends_the_window():
    interrupt = [{"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "cancelled"},
        {"type": "text", "text": "[Request interrupted by user for tool use]"}]}}]
    rows = _rows(lines(skill_call("m0", "t0", "kg"),
                       resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 9)),
                       interrupt,
                       resp("m2", [{"type": "text", "text": "y"}], usage=(1, 0, 0, 50))))
    assert U.session_invocations(rows)[0]["cost"]["output_tokens"] == 9


def test_a_plain_interrupt_ends_the_window():
    rows = _rows(lines(skill_call("m0", "t0", "kg"),
                       resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 9)),
                       _note("[Request interrupted by user]"),
                       resp("m2", [{"type": "text", "text": "y"}], usage=(1, 0, 0, 50))))
    assert U.session_invocations(rows)[0]["cost"]["output_tokens"] == 9


def test_local_command_stderr_is_injected_not_a_prompt():
    rows = _rows(lines(skill_call("m0", "t0", "kg"),
                       _note("<local-command-stderr>boom</local-command-stderr>"),
                       resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 9))))
    assert U.session_invocations(rows)[0]["cost"]["output_tokens"] == 9


def test_subagent_responses_are_not_charged_to_the_parent_window():
    side = resp("s1", [{"type": "text", "text": "sub"}], usage=(1, 0, 0, 500))
    for r in side:
        r["isSidechain"] = True
    rows = _rows(lines(skill_call("m0", "t0", "kg"), side,
                       resp("m1", [{"type": "text", "text": "x"}], usage=(1, 0, 0, 9))))
    assert U.session_invocations(rows)[0]["cost"]["output_tokens"] == 9


def test_a_shared_window_reports_its_turns():
    both = resp("m0", [
        {"type": "tool_use", "id": "t0", "name": "Skill", "input": {"skill": "kg"}},
        {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "p9"}}])
    rows = _rows(lines(both, resp("m1", [{"type": "text", "text": "x"}]),
                       resp("m2", [{"type": "text", "text": "y"}])))
    assert [i["cost"]["turns"] for i in U.session_invocations(rows)] == [2, 2]


def test_ranking_ties_are_broken_by_name(tmp_path):
    sr = tmp_path / "skills"
    for n in ("alpha", "beta"):
        _skill(sr, "x", n)
    tr = tmp_path / "projects" / "p"
    tr.mkdir(parents=True)
    (tr / "2772651f-25f3-4aee-8b5d-b44a9cd2dbfb.jsonl").write_bytes(calls("beta", "alpha"))
    assert [r["skill"] for r in U.build_report(tmp_path / "projects", sr)["ranked"]] == ["alpha", "beta"]
