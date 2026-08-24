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


def test_find_session_prefers_newest(tmp_path):
    proj = tmp_path / "projects" / rs.mangle("/w/x")
    proj.mkdir(parents=True)
    old, new = proj / "old.jsonl", proj / "new.jsonl"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    os.utime(old, (1, 1))
    os.utime(new, (10**9, 10**9))
    assert rs.find_session("/w/x", str(tmp_path / "projects")) == str(new)


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
    assert spawns[0]["agent_id"] == "aXYZ"
    assert spawns[0]["output_file"] == "/tmp/aXYZ.output"
    assert spawns[0]["description"] == "diagnose CI"


def test_synchronous_result_is_not_in_flight():
    """A tool_result that is a real answer means the agent already reported."""
    recs = [assistant(spawn_block("t1", "quick lookup")),
            user({"type": "tool_result", "tool_use_id": "t1",
                  "content": "here is the answer"})]
    assert rs.find_spawns(recs) == []


def test_non_spawn_tools_ignored():
    recs = [assistant({"type": "tool_use", "id": "t1", "name": "Bash",
                       "input": {"command": "ls"}}),
            user(launch_result("t1", "aXYZ"))]
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
