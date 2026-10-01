"""The System 1 gate, end to end through the registered wrapper: every stage's
positive and negative case, the flags, dedup and the caps, the subagent and
compaction stages, and what the decisions log may and may not hold."""
from __future__ import annotations

import json

import pytest

import s1_support as S


@pytest.fixture
def gate(world, tmp_path):
    S.write_corpus(world)
    r = S.build(world)
    assert r.returncode == 0, r.stderr
    world.params = S.write_params(tmp_path, S.LOW_FLOORS)
    return world


GATE_PY = lambda w: w.broomva / "scripts" / "gate.py"
#: The sources of the items that cite scripts/gate.py and may be offered for it.
CITERS = ("[research/entities/pattern/gate-that-cannot-fail.md]", "[docs/specs/2026-09-01-gate-design.html]",
          "memory/gate-rule.md]")


def cites_gate(text):
    lines = (text or "").splitlines()[1:]
    return bool(lines) and all(any(c in line for c in CITERS) for line in lines)


# --------------------------------------------------------------------------
# Flags: every stage is off unless named

def test_a_stage_is_off_without_the_flag(gate):
    r = S.run_s1("pre-edit", S.edit("s0", gate.broomva, GATE_PY(gate)), gate.params, on=False)
    assert (r.rc, r.stdout) == (0, "")
    assert S.decisions(gate) == []


def test_a_stage_not_listed_is_off(gate):
    r = S.run_s1("pre-edit", S.edit("s0", gate.broomva, GATE_PY(gate)), gate.params, stages="prompt,post-read")
    assert (r.rc, r.stdout) == (0, "")
    assert S.decisions(gate) == []


def test_all_turns_every_stage_on_and_the_kill_file_turns_them_off(gate):
    r = S.run_s1("pre-edit", S.edit("s0", gate.broomva, GATE_PY(gate)), gate.params, stages="all")
    assert r.context
    kill = gate.home / ".config" / "ctx" / "s1-off"
    kill.write_text("")
    r = S.run_s1("pre-edit", S.edit("s1", gate.broomva, GATE_PY(gate)), gate.params, stages="all")
    assert (r.rc, r.stdout) == (0, "")


def test_the_shipped_parameters_abstain_on_everything(gate):
    """No floor, no injection: the spec's start state (§6.2). Decisions are
    still logged, with their top candidates, so a shadow run has data."""
    r = S.run_s1("pre-edit", S.edit("s0", gate.broomva, GATE_PY(gate)), params=None)
    assert (r.rc, r.stdout) == (0, "")
    d = S.decisions(gate)[-1]
    assert d["outcome"] == "abstain" and d["reason"] == "no-floor" and d["top"]


def test_shadow_logs_the_injection_and_prints_nothing(gate):
    r = S.run_s1("pre-edit", S.edit("s0", gate.broomva, GATE_PY(gate)), gate.params,
                 env={"CTX_S1_SHADOW": "1"})
    assert (r.rc, r.stdout) == (0, "")
    d = S.decisions(gate)[-1]
    assert d["mode"] == "shadow" and d["outcome"] == "inject" and d["injected"]


# --------------------------------------------------------------------------
# Each stage: a positive and a negative case

def test_pre_edit_injects_claims_that_cite_the_file(gate):
    r = S.run_s1("pre-edit", S.edit("s1", gate.broomva, GATE_PY(gate)), gate.params)
    assert r.rc == 0 and r.event == "PreToolUse"
    ctx = r.context
    assert ctx.startswith("[ctx claims] Recorded facts in this scope that cite scripts/gate.py:")
    assert cites_gate(ctx)  # every line is a claim from an item that cites the file
    assert ctx.count("\n- ") <= 2  # at most 2 claims per mid-turn event


def test_pre_edit_abstains_on_a_file_nothing_cites(gate):
    r = S.run_s1("pre-edit", S.edit("s1", gate.broomva, gate.broomva / "scripts" / "other.py"), gate.params)
    assert (r.rc, r.stdout) == (0, "")
    assert S.decisions(gate)[-1]["reason"] in ("no-candidate", "below-floor")


def test_the_edited_file_is_never_offered_for_itself(gate):
    """The entity cites its own path, so it is a candidate for that path; it
    must not be offered for an edit or a read of itself."""
    ent = gate.broomva / "research/entities/pattern/gate-that-cannot-fail.md"
    r = S.run_s1("pre-edit", S.edit("s1", gate.broomva, ent), gate.params)
    assert "A gate whose only branch is pass" not in (r.context or "")
    r = S.run_s1("post-read", S.read("s1b", gate.broomva, ent), gate.params)
    assert "A gate whose only branch is pass" not in (r.context or "")
    assert any("gate-that-cannot-fail" in str(t) for d in S.decisions(gate) for t in d["top"])  # it WAS a candidate


def test_post_read_injects_for_a_cited_path_and_abstains_otherwise(gate):
    r = S.run_s1("post-read", S.read("s2", gate.broomva, GATE_PY(gate)), gate.params)
    assert r.event == "PostToolUse" and "scripts/gate.py" in r.context
    r = S.run_s1("post-read", S.read("s3", gate.broomva, gate.broomva / "scripts" / "other.py"), gate.params)
    assert r.stdout == ""


def test_post_bash_keys_on_a_shell_read_a_search_and_a_push(gate):
    r = S.run_s1("post-bash", S.bash("s4", gate.broomva, "sed -n 1,5p scripts/gate.py"), gate.params)
    assert r.context.startswith("[ctx claims] Recorded facts in this scope linked to scripts/gate.py:")
    assert cites_gate(r.context)
    r = S.run_s1("post-bash", S.bash("s5", gate.broomva, "rg -l zebrafish research/"), gate.params)
    assert r.context and "zebrafish" in r.context.lower()
    # a push keys on the branch: the spec names feat/x
    r = S.run_s1("post-bash", S.bash("s6", gate.worktree, "git push -u origin HEAD"), gate.params)
    assert "Gate design" in (r.context or "")


def test_post_bash_abstains_on_a_command_with_no_key(gate):
    r = S.run_s1("post-bash", S.bash("s7", gate.broomva, "git status && ls -la"), gate.params)
    assert r.stdout == ""
    assert S.decisions(gate)[-1]["reason"] == "no-key"


def test_prompt_injects_on_matching_words_and_skips_harness_prompts(gate):
    r = S.run_s1("prompt", S.prompt("s8", gate.broomva, "why does the zebrafish gate refuse writes?"), gate.params)
    assert r.event == "UserPromptSubmit" and "zebrafish" in r.context.lower()
    r = S.run_s1("prompt", S.prompt("s9", gate.broomva, "<task-notification>zebrafish done</task-notification>"),
                 gate.params)
    assert r.stdout == ""
    r = S.run_s1("prompt", S.prompt("s10", gate.broomva, "what is the weather like on mars"), gate.params)
    assert r.stdout == ""


def test_session_start_keys_on_the_branch(gate):
    r = S.run_s1("session-start", S.start("s11", gate.worktree), gate.params)
    assert r.event == "SessionStart" and "Gate design" in r.context
    r = S.run_s1("session-start", S.start("s12", gate.broomva), gate.params)  # main: no item names it
    assert r.stdout == ""
    r = S.run_s1("session-start", S.start("s13", gate.worktree, source="compact"), gate.params)
    assert r.stdout == ""  # compaction is the compact stage's


def test_subagent_gets_the_parents_claims_once_and_reviewers_get_none(gate):
    S.run_s1("pre-edit", S.edit("s14", gate.broomva, GATE_PY(gate)), gate.params)
    r = S.run_s1("subagent", S.subagent("s14", gate.broomva, "agent-1"), gate.params)
    assert r.event == "SubagentStart" and r.context.startswith("[ctx claims] Claims the parent session received")
    again = S.run_s1("subagent", S.subagent("s14", gate.broomva, "agent-1"), gate.params)
    assert again.stdout == ""
    for i, reviewer in enumerate(("cross-review-stratum-b", "Explore")):  # P20's Stratum B runs as Explore
        rev = S.run_s1("subagent", S.subagent("s14", gate.broomva, "agent-r%d" % i, reviewer), gate.params)
        assert rev.stdout == ""
        assert S.decisions(gate)[-1]["reason"] == "independent-reviewer"


def test_a_subagent_gets_only_what_the_parent_received(gate):
    """Its header says the parent received these claims, so nothing else goes
    in: on feat/x the spec is branch-keyed, but a parent that got nothing gives
    its subagent nothing."""
    r = S.run_s1("subagent", S.subagent("s14b", gate.worktree, "agent-9"), gate.params)
    assert r.stdout == ""
    first = S.run_s1("session-start", S.start("s14c", gate.worktree), gate.params)
    assert "Gate design" in first.context
    r = S.run_s1("subagent", S.subagent("s14c", gate.worktree, "agent-10"), gate.params)
    assert "Gate design" in r.context
    parent = {l for l in first.context.splitlines()[1:]}
    assert {l for l in r.context.splitlines()[1:]} <= parent


def test_an_injection_too_late_to_deliver_is_not_recorded(gate, monkeypatch):
    """The deadline is checked before the state is written, so the session's
    record never lists a claim the hook did not print."""
    import ctx_s1

    monkeypatch.setenv("CTX_S1", "1")
    monkeypatch.setenv("CTX_S1_STAGES", "pre-edit")
    monkeypatch.setenv("CTX_S1_PARAMS", str(gate.params))
    monkeypatch.setattr(ctx_s1, "DELIVERY_MARGIN_S", 3600.0)  # every injection is "too late"
    import time as _t
    out = ctx_s1.run_stage("pre-edit", json.dumps(S.edit("late", gate.broomva, GATE_PY(gate))),
                           deadline=_t.monotonic() + 60)
    assert out == ""
    d = S.decisions(gate)[-1]
    assert d["reason"] == "deadline" and d["top"]
    state = json.loads((gate.store("broomva") / "s1-sessions" / "late.json").read_text())
    assert state["injected"] == {} and state["counts"].get("total", 0) == 0


def test_compact_reinjects_what_the_session_had_and_may_repeat(gate):
    first = S.run_s1("pre-edit", S.edit("s15", gate.broomva, GATE_PY(gate)), gate.params)
    r = S.run_s1("compact", S.start("s15", gate.broomva, source="compact"), gate.params)
    assert r.event == "SessionStart"
    for line in first.context.splitlines()[1:]:
        assert line in r.context
    r2 = S.run_s1("compact", S.start("s15", gate.broomva, source="compact"), gate.params)
    assert r2.context == r.context  # the one stage that may repeat a claim
    fresh = S.run_s1("compact", S.start("s16", gate.broomva, source="compact"), gate.params)
    assert fresh.stdout == ""  # nothing received, nothing to re-inject


def test_post_compact_only_measures(gate):
    first = S.run_s1("pre-edit", S.edit("s17", gate.broomva, GATE_PY(gate)), gate.params)
    injected = S.decisions(gate)[-1]["injected"]
    src = first.context.splitlines()[1].rsplit("[", 1)[1].rstrip("]")  # the first claim's source
    r = S.run_s1("post-compact", {"session_id": "s17", "cwd": str(gate.broomva), "hook_event_name": "PostCompact",
                                  "trigger": "auto", "compact_summary": "We edited scripts/gate.py; see %s." % src},
                 gate.params)
    assert r.stdout == ""
    d = S.decisions(gate)[-1]
    assert d["outcome"] == "measure" and d["kept"] == [injected[0]] and len(injected) == 2


def test_tool_stages_abstain_inside_a_subagent(gate):
    r = S.run_s1("pre-edit", S.edit("s18", gate.broomva, GATE_PY(gate), agent_id="a1", agent_type="Explore"),
                 gate.params)
    assert r.stdout == ""
    assert S.decisions(gate)[-1]["reason"] == "in-subagent"


# --------------------------------------------------------------------------
# Dedup and rate limits

def test_a_claim_is_never_injected_twice_in_a_session(gate):
    a = S.run_s1("pre-edit", S.edit("s20", gate.broomva, GATE_PY(gate)), gate.params)
    b = S.run_s1("post-read", S.read("s20", gate.broomva, GATE_PY(gate)), gate.params)
    first = {l for l in a.context.splitlines()[1:]}
    assert not first & {l for l in (b.context or "").splitlines()[1:]}
    # another session gets them again
    c = S.run_s1("pre-edit", S.edit("s21", gate.broomva, GATE_PY(gate)), gate.params)
    assert c.context


def test_a_path_is_injected_for_once_per_session_per_stage(gate, tmp_path):
    p = S.write_params(tmp_path, {"stages": {"pre-edit": {"floor": 0.01, "max": 1}}})
    a = S.run_s1("pre-edit", S.edit("s22", gate.broomva, GATE_PY(gate)), p)
    assert a.context
    b = S.run_s1("pre-edit", S.edit("s22", gate.broomva, GATE_PY(gate)), p)
    assert b.stdout == ""
    assert S.decisions(gate)[-1]["reason"] in ("path-seen", "dedup")


def test_the_per_stage_session_cap(gate, tmp_path):
    p = S.write_params(tmp_path, {"stages": {"post-bash": {"floor": 0.01, "max": 1, "per_session": 1}}})
    a = S.run_s1("post-bash", S.bash("s23", gate.broomva, "rg -l zebrafish research/"), p)
    assert a.context
    b = S.run_s1("post-bash", S.bash("s23", gate.broomva, "sed -n 1p scripts/gate.py"), p)
    assert b.stdout == ""
    assert S.decisions(gate)[-1]["reason"] == "stage-cap"


def test_the_session_cap_and_the_budget(gate):
    import ctx_s1

    state = {"injected": {}, "paths": {}, "counts": {"total": ctx_s1.SESSION_MAX}, "subagents": [], "opened": []}
    keys = {"p": ["p:scripts/gate.py"]}
    reader = ctx_s1.CacheReader(gate.store("broomva"))
    d = ctx_s1.decide("pre-edit", keys, set(), state, reader, S.LOW_FLOORS)
    assert d["reason"] == "session-cap"
    state["counts"]["total"] = 0
    tight = json.loads(json.dumps(S.LOW_FLOORS))
    tight["stages"]["pre-edit"]["budget"] = 40
    d = ctx_s1.decide("pre-edit", keys, set(), state, reader, tight)
    assert d["reason"] == "budget"  # a line that does not fit is dropped, never cut


def test_a_file_the_session_already_opened_is_not_offered(gate):
    control = S.run_s1("pre-edit", S.edit("s23", gate.broomva, GATE_PY(gate)), gate.params)
    first = control.context.splitlines()[1]
    src = first[first.rindex("[") + 1:-1]  # the source of the claim a fresh session gets first
    assert not src.startswith("memory/"), src
    S.run_s1("post-read", S.read("s24", gate.broomva, gate.broomva / src), gate.params)
    r = S.run_s1("pre-edit", S.edit("s24", gate.broomva, GATE_PY(gate)), gate.params)
    assert "[%s]" % src not in (r.context or "")


# --------------------------------------------------------------------------
# What is stored, and what is injected

def test_person_crm_and_credential_shaped_items_are_never_candidates(gate):
    for sid, stage, payload in (("s30", "pre-edit", S.edit("s30", gate.broomva, GATE_PY(gate))),
                                ("s31", "prompt", S.prompt("s31", gate.broomva, "alice acme gate token renews"))):
        r = S.run_s1(stage, payload, gate.params)
        for bad in ("Alice", "Bob Example", "Carol", "Acme", "ghp_", "Bogota"):
            assert bad not in (r.context or "")
    meta = json.loads((gate.store("broomva") / "rank-current" / "meta.json").read_text())
    # three person entities (by directory, untyped; by type, elsewhere) and the user-type memory file
    assert meta["excluded"].get("person", 0) == 4
    blob = "".join(p.read_text() for p in (gate.store("broomva") / "rank-current").rglob("*.json"))
    for bad in ("alice", "bob example", "carol", "acme", "ghp_", "bogota", "crm/leads", "owner-profile"):
        assert bad not in blob.lower(), bad


def test_the_decisions_log_holds_no_prompt_text_and_no_key(gate):
    S.run_s1("prompt", S.prompt("s32", gate.broomva, "zebrafish quokka-marker gate"), gate.params)
    log = (gate.store("broomva") / "s1-decisions.jsonl").read_text()
    assert "quokka" not in log and "zebrafish" not in log
    d = S.decisions(gate)[-1]
    assert set(d["key_kinds"]) <= {"p", "d", "f", "b", "pr", "t", "w", "s"}


def test_claims_are_statements_not_instructions(gate):
    r = S.run_s1("prompt", S.prompt("s33", gate.broomva, "zebrafish gate writes ops"), gate.params)
    text = r.context
    assert text.startswith("[ctx claims] ")
    for bad in ("you must", "you should", "always ", "never ", "please", "do not", "make sure"):
        assert bad not in text.lower().split("\n", 1)[0], bad
    assert 'Memory rule gate-rule records: "' in text  # a memory rule is quoted, as data


def test_a_sri_session_never_reads_broomvas_cache(gate):
    r = S.run_s1("pre-edit", S.edit("s34", gate.sri, gate.sri / "scripts" / "gate.py"), gate.params)
    assert r.stdout == ""
    assert S.decisions(gate, "sri")[-1]["reason"] == "no-cache"
    assert all(d.get("session") != "s34" for d in S.decisions(gate, "broomva"))


def test_an_unscoped_repo_is_a_silent_no_op(gate):
    r = S.run_s1("pre-edit", S.edit("s35", gate.other, gate.other / "x.py"), gate.params)
    assert (r.rc, r.stdout) == (0, "")
    assert not (gate.home / ".local" / "state" / "ctx" / "other").exists()
