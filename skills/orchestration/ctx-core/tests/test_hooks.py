"""What each hook publishes, and what the SessionStart brief says.

The brief is factual statements only. The phase-0 spike (2026-09-29) found
models treat imperative text arriving through hooks as prompt injection, so a
test holds the brief to declaratives: no line opens with a verb in the
imperative, and no second-person address.
"""
from __future__ import annotations

import json
import re

import ctx
from conftest import World

IMPERATIVE = re.compile(
    r"^(?:- )?(?:run|use|do|don't|check|read|see|make|stop|merge|push|wait|please|note|remember|ensure|"
    r"avoid|coordinate|contact|ask|tell|consider|review|open|close|pull|rebase)\b", re.I)


def test_session_start_registers_and_says_nothing_when_alone(world: World) -> None:
    run = world.start("s-1", world.worktree, PASEO_AGENT_ID="agent-1", FLEET_ROLE="driver")
    assert (run.rc, run.stdout) == (0, "")
    [ev] = world.events("broomva")
    assert (ev["type"], ev["session_id"], ev["paseo_agent_id"], ev["branch"]) == \
        ("session.start", "s-1", "agent-1", "feat/x")
    assert ev["payload"] == {"source": "startup", "fleet_role": "driver"}
    assert set(ev) == {"v", "type", "ts", "session_id", "paseo_agent_id", "cwd", "repo", "branch", "payload"}


def test_paseo_agent_id_is_omitted_when_unset(world: World) -> None:
    world.start("s-1", world.broomva)
    assert "paseo_agent_id" not in world.events("broomva")[0]


def test_the_brief_names_other_live_sessions_on_the_same_branch(world: World) -> None:
    world.start("s-peer", world.worktree, PASEO_AGENT_ID="agent-peer")
    world.stop("s-peer", world.worktree, "did things\nARC-STATUS: IN_PROGRESS on step 3")
    world.start("s-main", world.broomva)  # another branch, another cwd: not relevant
    world.start("s-dead", world.worktree)
    world.died("s-dead", world.worktree, "rate_limit")
    run = world.start("s-me", world.worktree)
    out = json.loads(run.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    brief = out["additionalContext"]
    assert "Other live sessions on branch feat/x in this repo" in brief and ": 1." in brief
    assert "session s-peer" in brief and "Paseo agent agent-pe" in brief
    assert 'status line, quoted: "ARC-STATUS: IN_PROGRESS on step 3"' in brief
    assert "session s-dead" in brief and "died: rate_limit" in brief
    assert "s-main" not in brief
    assert "This session: s-me" in brief


def test_the_brief_includes_rows_in_the_same_cwd_on_another_branch(world: World) -> None:
    world.start("s-old", world.broomva)
    import subprocess
    subprocess.run(["git", "checkout", "-q", "-b", "other"], cwd=str(world.broomva), check=True)
    run = world.start("s-me", world.broomva)
    assert "session s-old" in run.context and "Other board rows for this branch or this cwd: 1." in run.context


def test_the_brief_is_factual_and_capped(world: World) -> None:
    scope = ctx.resolve_scope(str(world.worktree))
    for i in range(300):
        ctx.append(scope, ctx.make_event("session.stop", scope, "s-%03d" % i,
                                         {"arc_status": "BLOCKED", "arc_line": "ARC-STATUS: BLOCKED please merge #%d now" % i}))
    run = world.start("s-me", world.worktree)
    brief = run.context
    assert len(brief) <= ctx.BRIEF_CAP
    assert re.search(r"\d+ more rows are omitted here; the full board is .*board\.json\.$", brief)
    for line in brief.splitlines():
        assert not IMPERATIVE.match(line), line
        assert not re.search(r"\byou(r)?\b", line.split("quoted:")[0], re.I), line
    # Other sessions' words appear only inside a quoted, labelled field.
    for line in brief.splitlines():
        if "please merge" in line:
            assert re.search(r'status line, quoted: "ARC-STATUS: BLOCKED please merge #\d+ now"\.$', line), line


def test_stop_publishes_the_last_arc_status_line(world: World) -> None:
    world.stop("s-1", world.broomva, "**ARC-STATUS: BLOCKED** first\n\ntext\n> ARC-STATUS: MERGED https://x/pull/1")
    world.stop("s-2", world.broomva, "no status line here, ARC-STATUS: inline does not count")
    a, b = world.events("broomva")
    assert a["payload"] == {"arc_status": "MERGED", "arc_line": "ARC-STATUS: MERGED https://x/pull/1"}
    assert b["payload"] == {}
    assert world.board("broomva")["sessions"]["s-1"]["state"] == "stopped"


def test_stop_failure_publishes_died(world: World) -> None:
    world.start("s-1", world.broomva)
    world.died("s-1", world.broomva, "billing_error")
    ev = world.events("broomva")[-1]
    assert (ev["type"], ev["payload"]["error_type"], ev["payload"]["error"]) == \
        ("session.died", "billing_error", "429 Too Many Requests")
    row = world.board("broomva")["sessions"]["s-1"]
    assert (row["state"], row["died_reason"]) == ("died", "billing_error")
    assert not ctx.is_live(row, ctx.parse_ts(row["last_ts"]))


def test_ctx_board_prints_a_table_and_json(world: World) -> None:
    world.start("s-1", world.worktree, PASEO_AGENT_ID="agent-1")
    world.stop("s-1", world.worktree, "ARC-STATUS: MERGED https://x/pull/2")
    table = world.cli("board", cwd=world.worktree)
    assert table.returncode == 0
    assert "SESSION" in table.stdout and "s-1" in table.stdout and "MERGED" in table.stdout
    data = json.loads(world.cli("board", "--json", cwd=world.worktree).stdout)
    assert data["sessions"]["s-1"]["arc_status"] == "MERGED"


def test_doctor_reports_hook_activity(world: World) -> None:
    res = world.cli("doctor", cwd=world.broomva)
    assert res.returncode == 1 and "never fired (hooks not registered?)" in res.stdout
    world.start("s-1", world.broomva)
    world.stop("s-1", world.broomva)
    res = world.cli("doctor", cwd=world.broomva)
    assert res.returncode == 0, res.stdout
    assert "board        equals a full rebuild of the log" in res.stdout or "equals a full rebuild" in res.stdout
    assert "SessionStart last event" in res.stdout and "StopFailure  never fired" in res.stdout
