"""Unit tests for resume_scan — the forensic core of the `resume` skill."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import resume_scan as rs  # noqa: E402


# ------------------------------------------------------------------ helpers

LAUNCH = (
    "Async agent launched successfully. (This tool result is internal metadata.)\n"
    "agentId: {aid} (internal ID - do not mention to user.)\n"
    "The agent is working in the background.\n"
    "output_file: {out}\n"
)


def assistant(*blocks, **kw):
    return dict(type="assistant", message={"content": list(blocks)}, **kw)


def user(*blocks, **kw):
    return dict(type="user", message={"content": list(blocks)}, **kw)


def spawn_block(tid, desc, tool="Agent", prompt="do the thing"):
    return {"type": "tool_use", "id": tid, "name": tool,
            "input": {"description": desc, "prompt": prompt,
                      "subagent_type": "general-purpose"}}


def launch_result(tid, aid, out="/tmp/nope.output"):
    return {"type": "tool_result", "tool_use_id": tid,
            "content": LAUNCH.format(aid=aid, out=out)}


def notification(task_id, tool_use_id="toolu_x", status="completed", summary="done"):
    return {"type": "text", "text":
            f"<task-notification>\n<task-id>{task_id}</task-id>\n"
            f"<tool-use-id>{tool_use_id}</tool-use-id>\n"
            f"<status>{status}</status>\n<summary>{summary}</summary>\n"
            "</task-notification>"}


def write_session(tmp_path, records, name="s.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return str(p)


# ------------------------------------------------------------------ locating

def test_mangle_matches_claude_code_encoding():
    assert rs.mangle("/Users/b/orca/x") == "-Users-b-orca-x"
    # dots and underscores are non-alphanumeric and collapse to dashes too
    assert rs.mangle("/a/b.c_d") == "-a-b-c-d"


def _sess(path, cwd="/w/x"):
    path.write_text(json.dumps({"type": "user", "cwd": cwd}), encoding="utf-8")


def test_find_session_prefers_newest(tmp_path):
    proj = tmp_path / "projects" / rs.mangle("/w/x")
    proj.mkdir(parents=True)
    old, new = proj / "old.jsonl", proj / "new.jsonl"
    _sess(old); _sess(new)
    os.utime(old, (1, 1))
    os.utime(new, (10**9, 10**9))
    assert rs.find_session("/w/x", str(tmp_path / "projects")) == str(new)


def test_find_session_previous_skips_the_live_one(tmp_path):
    """After a crash the operator lands in a FRESH session, so the newest
    transcript is the one they are sitting in, not the one that died."""
    proj = tmp_path / "projects" / rs.mangle("/w/x")
    proj.mkdir(parents=True)
    died, live = proj / "died.jsonl", proj / "live.jsonl"
    _sess(died); _sess(live)
    os.utime(died, (10**9, 10**9))
    os.utime(live, (10**9 + 500, 10**9 + 500))
    root = str(tmp_path / "projects")
    assert rs.find_session("/w/x", root) == str(live)
    assert rs.find_session("/w/x", root, skip=1) == str(died)


def test_find_sessions_lists_newest_first(tmp_path):
    proj = tmp_path / "projects" / rs.mangle("/w/x")
    proj.mkdir(parents=True)
    a, b = proj / "a.jsonl", proj / "b.jsonl"
    _sess(a); _sess(b)
    os.utime(a, (1, 1)); os.utime(b, (10**9, 10**9))
    assert rs.find_sessions("/w/x", str(tmp_path / "projects")) == [str(b), str(a)]


def test_primary_path_still_verifies_cwd(tmp_path):
    """mangle() collapses '/', '.', '_' and '-' alike, so the mangled dir is
    not proof of ownership. A session for another cwd must not be returned."""
    proj = tmp_path / "projects" / rs.mangle("/w/x")
    proj.mkdir(parents=True)
    _sess(proj / "other.jsonl", cwd="/w/SOMEONE-ELSE")
    assert rs.find_session("/w/x", str(tmp_path / "projects")) is None


def test_fallback_finds_match_behind_a_newer_unrelated_session(tmp_path):
    """The fallback must consider EVERY transcript, not each dir's newest."""
    proj = tmp_path / "projects" / "unexpected-dir"
    proj.mkdir(parents=True)
    match, newer = proj / "match.jsonl", proj / "newer.jsonl"
    _sess(match, cwd="/w/real"); _sess(newer, cwd="/w/other")
    os.utime(match, (1, 1)); os.utime(newer, (10**9, 10**9))
    assert rs.find_session("/w/real", str(tmp_path / "projects")) == str(match)


def test_find_session_falls_back_to_declared_cwd(tmp_path):
    """A worktree may not mangle to the dir you expect; cwd in the record wins."""
    proj = tmp_path / "projects" / "unexpected-dir-name"
    proj.mkdir(parents=True)
    f = proj / "s.jsonl"
    f.write_text(json.dumps({"type": "user", "cwd": "/w/real"}), encoding="utf-8")
    assert rs.find_session("/w/real", str(tmp_path / "projects")) == str(f)


def test_find_session_returns_none_when_nothing_matches(tmp_path):
    (tmp_path / "projects").mkdir()
    assert rs.find_session("/w/absent", str(tmp_path / "projects")) is None


# ------------------------------------------------------------------ spawns

def test_async_spawn_is_parsed_with_id_and_output():
    recs = [assistant(spawn_block("t1", "diagnose CI")),
            user(launch_result("t1", "aXYZ", "/tmp/aXYZ.output"))]
    spawns = rs.find_spawns(recs)
    assert len(spawns) == 1
    assert spawns[0]["worker_id"] == "aXYZ"
    assert spawns[0]["output_file"] == "/tmp/aXYZ.output"
    assert spawns[0]["description"] == "diagnose CI"


def test_synchronous_result_is_not_in_flight():
    """A tool_result that is a real answer means the agent already reported."""
    recs = [assistant(spawn_block("t1", "quick lookup")),
            user({"type": "tool_result", "tool_use_id": "t1",
                  "content": "here is the answer"})]
    assert rs.find_spawns(recs) == []


def test_non_spawn_tools_ignored():
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Read",
                       "input": {"file_path": "/x"}}),
            user(launch_result("t1", "aXYZ"))]
    assert rs.find_spawns(recs) == []


def test_background_shell_is_detected():
    """The ONLY class that can outlive the parent — and the class the
    liveness guard is advertised for. It was invisible to the scan."""
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "railway up", "run_in_background": True}}),
            user({"type": "tool_result", "tool_use_id": "t1", "content":
                  "Command running in background with ID: bgABC. "
                  "Output is being written to: /tmp/bgABC.output"})]
    spawns = rs.find_spawns(recs)
    assert len(spawns) == 1
    assert spawns[0]["worker_id"] == "bgABC"
    assert spawns[0]["kind"] == "background-shell"
    assert spawns[0]["output_file"] == "/tmp/bgABC.output"


def test_foreground_bash_is_not_a_spawn():
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "ls"}}),
            user({"type": "tool_result", "tool_use_id": "t1", "content": "a\nb"})]
    assert rs.find_spawns(recs) == []


# ------------------------------------------------------------- completions

def test_completion_notification_parsed():
    recs = [user(notification("aXYZ", status="completed", summary="all green"))]
    done = rs.find_completions(recs)
    assert done["aXYZ"]["status"] == "completed"
    assert done["aXYZ"]["summary"] == "all green"


def test_spawn_with_completion_is_reported(tmp_path):
    recs = [assistant(spawn_block("t1", "d")),
            user(launch_result("t1", "aXYZ")),
            user(notification("aXYZ"))]
    res = rs.scan(write_session(tmp_path, recs))
    assert res["spawns_total"] == 1
    assert len(res["unreported"]) == 0
    assert res["reported"][0]["status"] == "completed"


def test_spawn_without_completion_is_unreported(tmp_path):
    """The core detection: launched, never reported back = died mid-flight."""
    recs = [assistant(spawn_block("t1", "diagnose PR 357")),
            user(launch_result("t1", "aXYZ"))]
    res = rs.scan(write_session(tmp_path, recs))
    assert len(res["unreported"]) == 1
    u = res["unreported"][0]
    assert u["description"] == "diagnose PR 357"
    assert u["prompt"] == "do the thing"  # re-spawnable


def test_completion_matched_by_tool_use_id(tmp_path):
    """Background shells key the notification on tool-use-id, not agent id."""
    recs = [assistant(spawn_block("t1", "bg build", tool="Task")),
            user(launch_result("t1", "bgid")),
            user(notification("some-other-task-id", tool_use_id="t1"))]
    res = rs.scan(write_session(tmp_path, recs))
    assert len(res["unreported"]) == 0


# ------------------------------------------------------------ termination

@pytest.mark.parametrize("text,kind", [
    ("API Error: 529 Overloaded. This is a server-side issue.", "api_overload"),
    ("API Error: Unable to connect to API (ENOTFOUND)", "network"),
    ("API Error: 500 Internal server error.", "api_5xx"),
    ("Login expired · Please run /login", "auth_expired"),
    ("[Request interrupted by user]", "user_interrupt"),
    ("Claude usage limit reached, resets at 12:20pm", "usage_limit"),
])
def test_real_terminations_detected(text, kind):
    assert rs.find_termination([assistant({"type": "text", "text": text})])["kind"] == kind


def test_prose_about_errors_is_not_a_termination():
    """REGRESSION: an error pattern in prose is not an error.

    Measured against a live session whose only '529' was text it had itself
    written into a Linear ticket describing past failures.
    """
    prose = (
        "## Problem\n\nWhen Claude Code dies mid-arc on an external fault "
        "(API 529/500, ENOTFOUND, ConnectionRefused, expired login), the "
        "operator restarts and types `resume`."
    )
    assert rs.find_termination([assistant({"type": "text", "text": prose})])["kind"] == \
        "clean_or_unknown"


def test_prose_quoting_a_rendered_error_is_not_a_termination():
    """REGRESSION: pins the START anchor, not merely the absence of keywords.

    The previous prose fixture said "API 529/500", which never matches the
    rendered prefix "API Error:" — so it passed even with the anchor loosened
    from .match to .search. A mutation proved it vacuous. This fixture quotes
    the rendered string verbatim mid-paragraph, exactly as this skill's own
    documentation does, so only a start-anchored matcher passes.
    """
    prose = (
        "The dominant cause is an interrupted request. A transcript line reading "
        "`API Error: 529 Overloaded` immediately before a resume turn is the "
        "signature we counted 44 times."
    )
    assert rs.find_termination([assistant({"type": "text", "text": prose})])["kind"] == \
        "clean_or_unknown"


def test_digest_bound_holds_for_one_oversized_block(tmp_path):
    """The cap must survive a SINGLE block larger than the budget."""
    f = tmp_path / "one.output"
    f.write_text(json.dumps(assistant({"type": "text", "text": "Z" * 9000})), encoding="utf-8")
    assert len(rs.digest_output(str(f), max_chars=250)["final_text"]) == 250


def test_tool_result_mentioning_an_error_is_not_a_termination():
    """A tool result carrying error text is data, not this session dying."""
    recs = [user({"type": "tool_result", "tool_use_id": "t1",
                  "content": "API Error: 529 Overloaded"})]
    assert rs.find_termination(recs)["kind"] == "clean_or_unknown"


def test_termination_found_when_not_the_last_record():
    """The scan looks back over a window, not just at the final record.

    A session rarely dies on its very last line: hooks, snapshots and
    queue-operations are appended afterwards. Pins the tail window.
    """
    recs = [assistant({"type": "text", "text": "API Error: 529 Overloaded"})]
    recs += [assistant({"type": "text", "text": "ok"}) for _ in range(12)]
    assert rs.find_termination(recs)["kind"] == "api_overload"


def test_termination_window_is_bounded():
    """An error far outside the window is NOT reported as how this ended."""
    recs = [assistant({"type": "text", "text": "API Error: 529 Overloaded"})]
    recs += [assistant({"type": "text", "text": "ok"}) for _ in range(12)]
    assert rs.find_termination(recs, tail=3)["kind"] == "clean_or_unknown"


def test_api_error_flag_is_trusted_anywhere_in_the_record():
    rec = assistant({"type": "text", "text": "x" * 500 + " ENOTFOUND"},
                    isApiErrorMessage=True)
    assert rs.find_termination([rec])["kind"] == "network"


def test_usage_limit_wins_over_rate_limit_ordering():
    """Signature order matters: 'usage limit' must not be eaten by 'limit'."""
    kinds = [k for k, _ in rs.TERMINATION_SIGNATURES]
    assert kinds.index("usage_limit") < kinds.index("rate_limited")


def test_most_recent_termination_wins():
    recs = [assistant({"type": "text", "text": "API Error: 529 Overloaded"}),
            assistant({"type": "text", "text": "Login expired · Please run /login"})]
    assert rs.find_termination(recs)["kind"] == "auth_expired"


# ---------------------------------------------------------------- recovery

def test_digest_is_bounded(tmp_path):
    """Never return the whole file — these reach 1.3 MB and overflow context."""
    big = tmp_path / "big.output"
    lines = [json.dumps(assistant({"type": "text", "text": "R" * 5000}))
             for _ in range(200)]
    big.write_text("\n".join(lines), encoding="utf-8")
    d = rs.digest_output(str(big), max_chars=300)
    assert d["recoverable"] is True
    assert len(d["final_text"]) <= 300
    assert d["bytes"] > 300_000


def test_digest_reports_files_and_tools(tmp_path):
    f = tmp_path / "a.output"
    recs = [assistant({"type": "tool_use", "id": "x", "name": "Edit",
                       "input": {"file_path": "/repo/a.ts"}}),
            assistant({"type": "text", "text": "fixed the migration collision"})]
    f.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    d = rs.digest_output(str(f))
    assert d["files_touched"] == ["/repo/a.ts"]
    assert d["tool_counts"]["Edit"] == 1
    assert "migration collision" in d["final_text"]


def test_digest_missing_file():
    d = rs.digest_output("/nonexistent/x.output")
    assert d["recoverable"] is False
    assert "no longer on disk" in d["reason"]


def test_digest_empty_file(tmp_path):
    f = tmp_path / "e.output"
    f.write_text("", encoding="utf-8")
    assert rs.digest_output(str(f))["recoverable"] is False


def test_digest_none_path():
    assert rs.digest_output(None)["recoverable"] is False


# ------------------------------------------------------------------- render

def test_render_names_unreported_agents(tmp_path):
    recs = [assistant(spawn_block("t1", "diagnose PR 357")),
            user(launch_result("t1", "aXYZ"))]
    out = rs.render(rs.scan(write_session(tmp_path, recs)))
    assert "UNREPORTED" in out
    assert "diagnose PR 357" in out


def test_render_clean_session_does_not_suggest_wrapping_up(tmp_path):
    out = rs.render(rs.scan(write_session(tmp_path, [assistant({"type": "text", "text": "hi"})])))
    assert "not a signal to wrap up" in out


def test_main_exits_2_without_session(tmp_path, capsys):
    assert rs.main(["--cwd", str(tmp_path), "--projects-dir", str(tmp_path / "none")]) == 2


def test_main_json_output(tmp_path, capsys):
    recs = [assistant(spawn_block("t1", "d")), user(launch_result("t1", "aXYZ"))]
    p = write_session(tmp_path, recs)
    assert rs.main(["--session", p, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["spawns_total"] == 1


# ==================================================================
# Round-2 coverage. Strata B ran 22 mutations against the previous
# suite and 20 SURVIVED — constants, the render contract and the whole
# possibly_live feature were unpinned. Each test below kills one.
# ==================================================================

def test_every_spawn_tool_is_detected():
    """Kills: dropping any name from the spawn-tool list.

    'Workflow' in particular — workflows-in-flight are a large share of the
    measured cases, and losing that alias is invisible without this.
    """
    for tool in ("Agent", "Task", "Workflow"):
        recs = [assistant(spawn_block("t1", "d", tool=tool)),
                user(launch_result("t1", "aX"))]
        assert len(rs.find_spawns(recs)) == 1, f"{tool} not detected"


def test_in_process_agent_is_never_possibly_live(tmp_path):
    """Kills: possibly_live hardcoded True.

    Agent/Task/Workflow run inside the parent and cannot outlive it, so a
    fresh mtime means the PARENT died recently — not that the worker lives.
    """
    out = tmp_path / "a.output"
    out.write_text(json.dumps(assistant({"type": "text", "text": "hi"})), encoding="utf-8")
    recs = [assistant(spawn_block("t1", "d")),
            user(launch_result("t1", "aX", str(out)))]
    res = rs.scan(write_session(tmp_path, recs))
    u = res["unreported"][0]
    assert u["possibly_live"] is False
    assert u["liveness"] == "dead-with-parent"


def test_background_shell_that_wrote_after_death_is_possibly_live(tmp_path):
    """Kills: possibly_live hardcoded False — the guard that stops a live
    deploy being re-run."""
    out = tmp_path / "bg.output"
    out.write_text("building...", encoding="utf-8")
    recs = [
        dict(type="assistant", timestamp="2020-01-01T00:00:00Z",
             message={"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                   "input": {"command": "railway up", "run_in_background": True}}]}),
        user({"type": "tool_result", "tool_use_id": "t1", "content":
              f"Command running in background with ID: bgX. "
              f"Output is being written to: {out}"}),
    ]
    res = rs.scan(write_session(tmp_path, recs))
    u = res["unreported"][0]
    assert u["liveness"] == "possibly-live"
    assert "POSSIBLY STILL RUNNING" in rs.render(res)


def test_possibly_live_flag_tracks_liveness_for_background_shells(tmp_path):
    """Kills: possibly_live pinned to False.

    `liveness` was covered but the derived boolean the render and SKILL.md
    both key on was not — pinning one field and not its sibling is how a
    guard goes inert while the suite stays green.
    """
    out = tmp_path / "bg.output"
    out.write_text("building", encoding="utf-8")
    recs = [
        dict(type="assistant", timestamp="2020-01-01T00:00:00Z",
             message={"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                   "input": {"command": "railway up", "run_in_background": True}}]}),
        user({"type": "tool_result", "tool_use_id": "t1", "content":
              f"Command running in background with ID: bgZ. "
              f"Output is being written to: {out}"}),
    ]
    u = rs.scan(write_session(tmp_path, recs))["unreported"][0]
    assert u["possibly_live"] is True


def test_recoverable_false_when_nothing_survived(tmp_path):
    """Kills: recoverable hardcoded True.

    Uses a file that EXISTS and parses but carries nothing, so the check
    reaches the return statement instead of an early-out on a missing file.
    """
    f = tmp_path / "blank.output"
    f.write_text(json.dumps({"type": "user", "message": {"content": []}}), encoding="utf-8")
    d = rs.digest_output(str(f))
    assert d["recoverable"] is False


def test_render_labels_the_prompt_block(tmp_path):
    """Kills: deleting the prompt HEADER while its lines still print.

    Asserting only that the prompt text appears let the labelled contract be
    removed — an agent reading the output could not tell prompt from prose.
    """
    recs = [assistant(spawn_block("t1", "d", prompt="RESPAWN-ME")),
            user(launch_result("t1", "aX"))]
    out = rs.render(rs.scan(write_session(tmp_path, recs)))
    assert "orig prompt" in out
    assert "complete" in out
    assert "RESPAWN-ME" in out


def test_hour_limit_form_without_the_resets_clause():
    """Kills: removing the 'hit your <N> limit' branch.

    The other branch ('resets Aug 10 at') covers the common phrasing, so a
    form carrying ONLY this branch is needed — a rule spelled per-branch is
    forgotten per-branch.
    """
    rec = assistant({"type": "text", "text": "You've hit your 5-hour limit"},
                    isApiErrorMessage=True)
    assert rs.find_termination([rec])["kind"] == "usage_limit"


def test_missing_output_file_is_unknown_not_dead(tmp_path):
    """Kills: treating an absent output file as 'safe to re-spawn'."""
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "deploy", "run_in_background": True}}),
            user({"type": "tool_result", "tool_use_id": "t1", "content":
                  "Command running in background with ID: bgY."})]
    res = rs.scan(write_session(tmp_path, recs))
    assert res["unreported"][0]["liveness"] == "unknown-no-output-file"
    assert "UNKNOWN" in rs.render(res)


def test_default_max_chars_is_enforced(tmp_path):
    """Kills: raising the DEFAULT cap. Every other cap test passes the value
    explicitly, so the shipped default was unfalsified."""
    f = tmp_path / "big.output"
    f.write_text("\n".join(
        json.dumps(assistant({"type": "text", "text": "Q" * 4000})) for _ in range(50)),
        encoding="utf-8")
    assert len(rs.digest_output(str(f))["final_text"]) <= 1200


def test_digest_reads_a_deep_tail(tmp_path):
    """Kills: shrinking tail_records to a handful — the last words would be
    lost for any worker that logged steadily before dying."""
    f = tmp_path / "t.output"
    recs = [assistant({"type": "tool_use", "id": f"x{i}", "name": "Bash",
                       "input": {"command": "true"}}) for i in range(300)]
    recs.append(assistant({"type": "text", "text": "FINAL VERDICT"}))
    f.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    d = rs.digest_output(str(f))
    assert "FINAL VERDICT" in d["final_text"]
    assert d["tool_counts"].get("Bash", 0) >= 200


def test_unrecoverable_is_reported_as_unrecoverable(tmp_path):
    """Kills: hardcoding recoverable=True."""
    assert rs.digest_output(str(tmp_path / "nope.output"))["recoverable"] is False


def test_truncated_window_is_flagged(tmp_path):
    """Kills: truncated_window hardcoded False."""
    f = tmp_path / "w.output"
    f.write_text("\n".join(json.dumps(assistant({"type": "text", "text": "x"}))
                           for _ in range(900)), encoding="utf-8")
    assert rs.digest_output(str(f))["truncated_window"] is True


def test_files_touched_is_bounded(tmp_path):
    """Kills: unbounded files_touched — 40 long paths serialized to 16 KB in
    a payload whose advertised cap was 1200 chars."""
    f = tmp_path / "many.output"
    recs = [assistant({"type": "tool_use", "id": f"i{i}", "name": "Edit",
                       "input": {"file_path": "/very/long/path/" + "s" * 300 + f"/f{i}.ts"}})
            for i in range(60)]
    f.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    d = rs.digest_output(str(f))
    assert 0 < len(d["files_touched"]) <= 20
    assert all(len(x) <= 200 for x in d["files_touched"])


def test_render_carries_the_prompt_and_the_triage(tmp_path):
    """Kills: deleting the rendered prompt block or the triage block — both
    are the render contract SKILL.md step 4 depends on."""
    recs = [assistant(spawn_block("t1", "diagnose", prompt="RESPAWN-ME")),
            user(launch_result("t1", "aX"))]
    out = rs.render(rs.scan(write_session(tmp_path, recs)))
    assert "RESPAWN-ME" in out
    assert "triage" in out


def test_termination_evidence_is_not_blank():
    """Kills: blanking the evidence field — the operator needs the string."""
    t = rs.find_termination([assistant({"type": "text", "text": "API Error: 529 Overloaded"})])
    assert "529" in t["evidence"] or "Overloaded" in t["evidence"]


# ---------------------------------------------- notification record shapes

def test_completion_in_queue_operation_record(tmp_path):
    """Kills: reading notifications only out of message.content.

    Measured 23 queue-operation / 7 attachment / 7 user in one production
    session; parsing only the last missed 37% of completions corpus-wide and
    reported finished agents as dead.
    """
    recs = [assistant(spawn_block("t1", "d")), user(launch_result("t1", "aX")),
            {"type": "queue-operation",
             "content": "<task-notification><task-id>aX</task-id>"
                        "<status>completed</status><summary>ok</summary></task-notification>"}]
    res = rs.scan(write_session(tmp_path, recs))
    assert res["unreported"] == []


def test_completion_in_attachment_record(tmp_path):
    recs = [assistant(spawn_block("t1", "d")), user(launch_result("t1", "aX")),
            {"type": "attachment", "attachment": {"prompt":
             "<task-notification><task-id>aX</task-id>"
             "<status>completed</status><summary>ok</summary></task-notification>"}}]
    res = rs.scan(write_session(tmp_path, recs))
    assert res["unreported"] == []


# ------------------------------------------------------- failed completions

def test_failed_completion_is_not_an_all_clear(tmp_path):
    """A worker that reported FAILURE reported — and still needs attention.
    Folding it into the silent 'reported' bucket printed 'Nothing died'."""
    recs = [assistant(spawn_block("t1", "deploy prod")),
            user(launch_result("t1", "aX")),
            user(notification("aX", status="failed", summary="crashed on step 2"))]
    res = rs.scan(write_session(tmp_path, recs))
    assert len(res["reported_failed"]) == 1
    out = rs.render(res)
    assert "Nothing died mid-flight" not in out
    assert "REPORTED FAILURE" in out


def test_killed_completion_is_not_an_all_clear(tmp_path):
    recs = [assistant(spawn_block("t1", "build")), user(launch_result("t1", "aX")),
            user(notification("aX", status="killed"))]
    assert len(rs.scan(write_session(tmp_path, recs))["reported_failed"]) == 1


# ------------------------------------------------- unclassified api errors

def test_weekly_limit_is_classified():
    """The dominant production form — 53 of 61 sampled api-error records."""
    rec = assistant({"type": "text",
                     "text": "You've hit your weekly limit · resets Aug 10 at 7am (America/Bogota)"},
                    isApiErrorMessage=True)
    assert rs.find_termination([rec])["kind"] == "usage_limit"


@pytest.mark.parametrize("text", [
    "API Error: 522 ",
    "API Error: Connection closed mid-response",
    "API Error: Response stalled mid-stream",
])
def test_real_network_forms_classified(text):
    rec = assistant({"type": "text", "text": text}, isApiErrorMessage=True)
    assert rs.find_termination([rec])["kind"] == "network"


def test_unrecognised_api_error_does_not_read_as_clean():
    """Silent degradation to clean_or_unknown is the wrap-up framing this
    skill exists to prevent."""
    rec = assistant({"type": "text", "text": "Something entirely novel went wrong"},
                    isApiErrorMessage=True)
    assert rs.find_termination([rec])["kind"] == "api_error_unclassified"


# -------------------------------------------------------- durable recovery

def test_durable_transcript_preferred_over_wiped_tmp(tmp_path):
    """The launch receipt points into /private/tmp, which the crash wipes —
    measured, 92% of unreported spawns had no output file. The harness also
    writes a durable copy that survives."""
    sess = tmp_path / "sid.jsonl"
    dur = tmp_path / "sid" / "subagents"
    dur.mkdir(parents=True)
    (dur / "agent-aX.jsonl").write_text(
        json.dumps(assistant({"type": "text", "text": "DURABLE RESULT"})), encoding="utf-8")
    recs = [assistant(spawn_block("t1", "d")),
            user(launch_result("t1", "aX", "/private/tmp/gone/aX.output"))]
    sess.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    res = rs.scan(str(sess))
    assert "DURABLE RESULT" in res["unreported"][0]["digest"]["final_text"]


def test_durable_transcript_absent_is_fine(tmp_path):
    assert rs.durable_transcript(str(tmp_path / "s.jsonl"), "aX") is None
    assert rs.durable_transcript(str(tmp_path / "s.txt"), "aX") is None


# ------------------------------------------------------ hostile-input guards

def test_non_dict_json_lines_do_not_crash(tmp_path):
    """Raw stdout is valid JSON per line: a bare `381` from `wc -l` parsed to
    an int and raised AttributeError on 11% of real .output files."""
    f = tmp_path / "raw.output"
    f.write_text("381\n[1,2,3]\n\"a string\"\nplain log line\n", encoding="utf-8")
    d = rs.digest_output(str(f))
    assert d["recoverable"] is True
    assert d["shape"] == "raw-stdout"


def test_non_dict_lines_counted_as_unusable(tmp_path):
    p = write_session(tmp_path, [assistant({"type": "text", "text": "ok"})])
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("\n42\n")
    recs, bad = rs.load(p)
    assert bad == 1 and len(recs) == 1


def test_truncated_tail_is_reported_not_swallowed(tmp_path):
    """A crash truncates the line it was mid-write on — the literal signature
    of the failure this skill targets."""
    p = tmp_path / "t.jsonl"
    good = json.dumps(assistant({"type": "text", "text": "working"}))
    p.write_text(good + "\n" + good[:40], encoding="utf-8")
    res = rs.scan(str(p))
    assert res["unparsable_records"] == 1
    assert "UNUSABLE" in rs.render(res)


def test_zero_records_is_not_an_all_clear(tmp_path):
    f = tmp_path / "empty.jsonl"
    f.write_text("not json at all\n", encoding="utf-8")
    out = rs.render(rs.scan(str(f)))
    assert "NO PARSEABLE RECORDS" in out
    assert "Nothing died mid-flight" not in out


def test_directory_is_refused_with_exit_2(tmp_path):
    assert rs.main(["--session", str(tmp_path)]) == 2


def test_fifo_is_refused(tmp_path):
    fifo = tmp_path / "f.fifo"
    try:
        os.mkfifo(str(fifo))
    except (AttributeError, OSError):
        pytest.skip("mkfifo unavailable")
    assert rs.main(["--session", str(fifo)]) == 2


def test_null_timestamp_does_not_crash(tmp_path):
    recs = [dict(type="assistant", timestamp=None,
                 message={"content": [{"type": "text", "text": "x"}]})]
    assert rs.scan(write_session(tmp_path, recs))["records"] == 1


def test_message_as_list_does_not_crash(tmp_path):
    recs = [{"type": "assistant", "message": ["not", "a", "dict"]}]
    assert rs.scan(write_session(tmp_path, recs))["records"] == 1


def test_max_chars_zero_rejected(tmp_path):
    p = write_session(tmp_path, [assistant({"type": "text", "text": "x"})])
    assert rs.main(["--session", p, "--max-chars", "0"]) == 2


# ------------------------------------------------------------- redaction

@pytest.mark.parametrize("secret", [
    "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAA",
    "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "github_pat_AAAAAAAAAAAAAAAAAAAAAAAA",
    "AKIAIOSFODNN7EXAMPLE",
    "xoxb-1234567890-abcdefghij",
])
def test_secrets_are_masked_in_recovered_text(tmp_path, secret):
    """Recovered text is printed into an agent's context and then summarised
    into a report. 22 of 671 real .output files carried secret-shaped strings."""
    f = tmp_path / "s.output"
    f.write_text(json.dumps(assistant({"type": "text", "text": f"token is {secret}"})),
                 encoding="utf-8")
    d = rs.digest_output(str(f))
    assert secret not in d["final_text"]
    assert "[REDACTED:" in d["final_text"]
    assert d["redacted"]


def test_ordinary_text_is_not_mangled_by_redaction():
    out, found = rs.redact("a normal sentence with sk- and a hyphen")
    assert out == "a normal sentence with sk- and a hyphen"
    assert found == []


# ==================================================================
# Round-3 coverage. Verify round found the round-2 "fix" made the prompt
# claim WORSE (cut at 880 chars AND labelled complete, with a test pinning
# the word "complete"), plus 12 of 31 independent mutants surviving. The
# structural response is LIMITS: every bound named once and asserted here.
# ==================================================================

def test_long_prompt_is_labelled_truncated_not_complete(tmp_path):
    """The blocker. Round 1 cut the prompt silently at 2,000 chars; round 2 cut
    it at 880 and ASSERTED completeness — measured wrong on 46 of 46 real
    prompts. A render that lies about completeness is worse than one that cuts.
    """
    long_prompt = "L" * 9000
    recs = [assistant(spawn_block("t1", "d", prompt=long_prompt)),
            user(launch_result("t1", "aX"))]
    out = rs.render(rs.scan(write_session(tmp_path, recs)))
    assert "TRUNCATED" in out
    assert "9000 chars" in out
    assert "chars, complete" not in out
    assert "more chars" in out


def test_short_prompt_is_labelled_complete_and_is_whole(tmp_path):
    recs = [assistant(spawn_block("t1", "d", prompt="line one\nline two")),
            user(launch_result("t1", "aX"))]
    out = rs.render(rs.scan(write_session(tmp_path, recs)))
    assert "complete" in out and "TRUNCATED" not in out
    assert "line one" in out and "line two" in out


def test_json_carries_the_prompt_whole(tmp_path):
    """The render may cut; --json is what the agent re-spawns from."""
    long_prompt = "P" * 9000
    recs = [assistant(spawn_block("t1", "d", prompt=long_prompt)),
            user(launch_result("t1", "aX"))]
    res = rs.scan(write_session(tmp_path, recs))
    assert len(res["unreported"][0]["prompt"]) == 9000


def test_render_keeps_more_of_a_long_prompt_than_eight_lines(tmp_path):
    """Kills: re-introducing a line-count cap. 46 of 46 real prompts had >8
    lines, so the tail was dropped every time."""
    recs = [assistant(spawn_block("t1", "d", prompt="\n".join(f"line{i}" for i in range(60)))),
            user(launch_result("t1", "aX"))]
    out = rs.render(rs.scan(write_session(tmp_path, recs)))
    assert "line40" in out


def test_foreground_bash_echoing_the_receipt_is_not_a_worker():
    """The tool CALL is authoritative, not its stdout. A grep over this corpus
    prints the launch string, and that forged a live background worker."""
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "grep -c 'Command running in background'"}}),
            user({"type": "tool_result", "tool_use_id": "t1", "content":
                  "Command running in background with ID: fake123. "
                  "Output is being written to: /tmp/fake123.output"})]
    assert rs.find_spawns(recs) == []


def test_assistant_prose_cannot_forge_a_completion(tmp_path):
    """A transcript DISCUSSING the notification format — this repo's own
    fixtures do — must not close a worker."""
    recs = [assistant(spawn_block("t1", "d")), user(launch_result("t1", "aX")),
            assistant({"type": "text", "text":
                       "<task-notification><task-id>aX</task-id>"
                       "<status>completed</status></task-notification>"})]
    assert len(rs.scan(write_session(tmp_path, recs))["unreported"]) == 1


def test_idless_tool_use_does_not_capture_an_unrelated_result():
    recs = [assistant({"type": "tool_use", "name": "Agent",
                       "input": {"description": "FIRST", "prompt": "a"}}),
            assistant({"type": "tool_use", "name": "Agent",
                       "input": {"description": "SECOND", "prompt": "b"}}),
            user({"type": "tool_result", "content": "Async agent launched successfully.\n"
                  "agentId: aX\noutput_file: /tmp/x.output\n"})]
    assert rs.find_spawns(recs) == []


# ------------------------------------------------ real termination forms

@pytest.mark.parametrize("text,kind", [
    ("You've hit your session limit · resets 1:50pm (America/Bogota)", "usage_limit"),
    ("You've hit your weekly limit · resets Aug 10 at 7am", "usage_limit"),
    ("Failed to authenticate: OAuth session expired and could not be refreshed", "auth_expired"),
    ("Your computer went to sleep mid-response.", "machine_slept"),
    ("Prompt is too long", "context_too_long"),
    ("API Error: The response stopped arriving.", "stalled"),
])
def test_forms_the_harness_actually_emits(text, kind):
    """51 of 801 real api-error records were unclassified after round 2 — the
    signatures were still written to the sample, not to the class."""
    rec = assistant({"type": "text", "text": text}, isApiErrorMessage=True)
    assert rs.find_termination([rec])["kind"] == kind


# ------------------------------------------------------- LIMITS are real

def test_every_limit_is_a_positive_int():
    assert rs.LIMITS and all(isinstance(v, int) and v > 0 for v in rs.LIMITS.values())


# Each bound below asserts a HARDCODED expected value. The previous versions
# fed an input sized from the constant and asserted against the same constant,
# so widening the constant widened the input too and the assertion could never
# fail — seven entries survived a 10x widening with the whole suite green.
# Duplicating the literal here is the point: the test is the second opinion.

def test_termination_tail_bound_is_400():
    err = assistant({"type": "text", "text": "API Error: 529 Overloaded"})
    ok = assistant({"type": "text", "text": "ok"})
    assert rs.LIMITS["termination_tail"] == 400
    # exactly inside the window: error + 399 later records
    assert rs.find_termination([err] + [ok] * 399)["kind"] == "api_overload"
    # one past it: error + 400 later records
    assert rs.find_termination([err] + [ok] * 400)["kind"] == "clean_or_unknown"


def test_summary_bound_is_300(tmp_path):
    recs = [assistant(spawn_block("t1", "d")), user(launch_result("t1", "aX")),
            user(notification("aX", status="failed", summary="S" * 5000))]
    f = rs.scan(write_session(tmp_path, recs))["reported_failed"][0]
    assert rs.LIMITS["summary_chars"] == 300
    assert len(f["summary"]) == 300


def test_command_bound_is_400():
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "x" * 5000, "run_in_background": True}}),
            user({"type": "tool_result", "tool_use_id": "t1",
                  "content": "Command running in background with ID: bgQ."})]
    assert rs.LIMITS["command_chars"] == 400
    assert len(rs.find_spawns(recs)[0]["command"]) == 400


def test_last_words_bound_is_12_lines(tmp_path):
    f = tmp_path / "many.output"
    f.write_text(json.dumps(assistant({"type": "text",
                 "text": "\n".join(f"row{i}" for i in range(400))})), encoding="utf-8")
    recs = [assistant(spawn_block("t1", "d")), user(launch_result("t1", "aX", str(f)))]
    out = rs.render(rs.scan(write_session(tmp_path, recs)))
    assert rs.LIMITS["last_words_lines"] == 12
    assert out.count("    | row") == 12


def test_cwd_probe_bound_is_40(tmp_path):
    proj = tmp_path / "p" / rs.mangle("/w/x")
    proj.mkdir(parents=True)
    pad = [json.dumps({"type": "user"}) for _ in range(45)]
    pad.append(json.dumps({"type": "user", "cwd": "/w/x"}))
    (proj / "s.jsonl").write_text("\n".join(pad), encoding="utf-8")
    assert rs.LIMITS["cwd_probe_lines"] == 40
    assert rs.find_session("/w/x", str(tmp_path / "p")) is None


def test_digest_bound_is_1200(tmp_path):
    f = tmp_path / "b.output"
    f.write_text("\n".join(json.dumps(assistant({"type": "text", "text": "Q" * 4000}))
                           for _ in range(50)), encoding="utf-8")
    assert rs.LIMITS["digest_chars"] == 1200
    assert len(rs.digest_output(str(f))["final_text"]) == 1200


def test_evidence_bound_is_160():
    """Had no test at all."""
    assert rs.LIMITS["evidence_chars"] == 160
    long_tail = "API Error: 529 Overloaded " + ("z" * 5000)
    t = rs.find_termination([assistant({"type": "text", "text": long_tail})])
    assert len(t["evidence"]) <= 60 + 160


def test_live_window_bound_is_90():
    """Had no test at all — and it guards 'do not re-run a live deploy'."""
    assert rs.LIMITS["live_window_s"] == 90


# ------------------------------------------------------------- workflows

def test_real_workflow_receipt_is_detected():
    """The receipt string is copied byte-for-byte from a production transcript.

    169 real workflow receipts existed in the corpus and 100% were dropped:
    the text carries neither `agentId:` nor the background-shell wording, so
    it fell through to "already reported". The test that was supposed to pin
    this handed tool="Workflow" an AGENT receipt — a fixture written to fit
    the regex rather than copied from the harness, which is the exact defect
    it was meant to catch.
    """
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Workflow",
                       "input": {"name": "audit", "description": "audit keel"}}),
            user({"type": "tool_result", "tool_use_id": "t1", "content":
                  "Workflow launched in background. Task ID: wi666ztu1\n"
                  "Summary: Audit Keel across 6 dimensions\n"
                  "Transcript dir: /tmp/wf_7fb5aef4-ebc"})]
    spawns = rs.find_spawns(recs)
    assert len(spawns) == 1
    assert spawns[0]["worker_id"] == "wi666ztu1"
    assert spawns[0]["kind"] == "workflow"


def test_workflow_liveness_is_unknown_not_dead(tmp_path):
    """The corpus does not settle whether workflows outlive the parent, so the
    scan must not assert either. Calling a live workflow dead invites
    re-running work that is still going."""
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Workflow",
                       "input": {"name": "deploy"}}),
            user({"type": "tool_result", "tool_use_id": "t1", "content":
                  "Workflow launched in background. Task ID: wfX\n"
                  "Transcript dir: /tmp/nonexistent-wf"})]
    res = rs.scan(write_session(tmp_path, recs))
    u = res["unreported"][0]
    assert u["liveness"] == "unknown-workflow"
    assert u["possibly_live"] is False
    assert "UNKNOWN" in rs.render(res)
    assert rs.LIMITS and all(isinstance(v, int) and v > 0 for v in rs.LIMITS.values())







@pytest.mark.parametrize("rec", [
    {"type": "assistant", "timestamp": 1723471200,
     "message": {"content": [{"type": "text", "text": "x"}]}},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": 123}]}},
])
def test_hostile_value_types_do_not_crash(tmp_path, rec):
    assert rs.scan(write_session(tmp_path, [rec]))["records"] == 1


def test_dict_prompt_does_not_crash(tmp_path):
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Agent",
                       "input": {"description": "d", "prompt": {"not": "a string"}}}),
            user(launch_result("t1", "aX"))]
    out = rs.render(rs.scan(write_session(tmp_path, recs)))
    assert "UNREPORTED" in out


# ----------------------------------------------------------- redaction

def test_redaction_covers_the_real_header_forms():
    for secret in ["Authorization: Bearer abcdefghijklmnop1234",
                   "Bearer sk-ant-oat01-AAAAAAAAAAAAAAAAAAAA",
                   "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA",
                   "Authorization: Basic dXNlcjpwYXNzd29yZA==",
                   "glpat-AAAAAAAAAAAAAAAAAAAA"]:
        out, kinds = rs.redact(secret)
        assert "[REDACTED:" in out and kinds, f"missed {secret[:24]}"


def test_redaction_does_not_mask_ordinary_prose():
    """It over-masked a URL path and a short sk- token in prose."""
    for benign in ["see https://api.example.com/v1/sk-abcdefghij for details",
                   "the sk- prefix denotes a secret key"]:
        out, kinds = rs.redact(benign)
        assert out == benign and kinds == [], benign


def test_skill_md_test_count_matches_reality():
    """The count SKILL.md advertises must be the count pytest reports.

    Added because dogfooding caught SKILL.md claiming 31 tests when 35 existed
    — a doc that drifted the moment tests were added, with nothing to notice.

    Counts what pytest COLLECTS, not `def test_` lines: one test here is
    parametrized six ways, so the two numbers differ by five. The first version
    of this test counted defs and disagreed with the suite it was policing,
    which is the same class of error it exists to catch.
    """
    import re as _re
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    skill = open(os.path.join(here, "..", "SKILL.md"), encoding="utf-8").read()
    claimed = _re.search(r"(\d+) unit tests", skill)
    assert claimed, "SKILL.md no longer states a test count"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", here],
        capture_output=True, text=True, timeout=120,
    )
    collected = _re.search(r"(\d+) tests? collected", proc.stdout)
    assert collected, f"could not read collection count from:\n{proc.stdout[-500:]}"
    assert int(claimed.group(1)) == int(collected.group(1)), (
        f"SKILL.md claims {claimed.group(1)} tests, pytest collects {collected.group(1)}"
    )
