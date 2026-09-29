"""Every hook finishes in under 200 ms of wall time, measured from outside the
process, including interpreter start-up. Slow dependencies are cut off rather
than waited on: a git that hangs, a log far past the fold cap, a store with no
cached board.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from pathlib import Path

import ctx
from conftest import HOOK_WALL_S, World


def test_the_normal_path_is_inside_the_deadline(timed: World) -> None:
    for i in range(5):
        for run in (timed.start("s-%d" % i, timed.worktree),
                    timed.stop("s-%d" % i, timed.worktree, "ARC-STATUS: DONE"),
                    timed.died("s-%d" % i, timed.worktree)):
            assert run.rc == 0 and run.elapsed < HOOK_WALL_S, "%.0f ms" % (run.elapsed * 1000)
    assert len(timed.events("broomva")) == 15, "the budget is so tight that appends were dropped"


def test_hooks_do_not_run_git_and_a_hanging_git_is_killed(timed: World, tmp_path: Path, monkeypatch) -> None:
    """A hook resolves the repo from the filesystem; git runs only when GIT_DIR
    and friends redirect it, and then it is bounded and killed."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pidfile = tmp_path / "git.pid"
    fake = bindir / "git"
    fake.write_text('#!/bin/sh\n[ "$1" = warm ] && exit 0\necho $$ >> %s\nexec sleep 30\n' % pidfile)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    # macOS scans a freshly written executable on its first exec, which alone
    # can outlast the ~70 ms git budget. Warm it, so the timed runs measure a
    # git that starts and then hangs.
    for _ in range(3):
        subprocess.run([str(fake), "warm"], check=True)
    env = {"PATH": "%s:%s" % (bindir, os.environ.get("PATH", ""))}
    for event in ("session-start", "stop", "stop-failure"):
        run = timed.hook(event, {"session_id": "s-1", "cwd": str(timed.broomva)}, env=env)
        assert (run.rc, run.stdout, run.stderr) == (0, "", "")
        assert run.elapsed < HOOK_WALL_S, "%.0f ms" % (run.elapsed * 1000)
    assert not pidfile.exists(), "a hook ran git on the normal path"
    assert len(timed.events("broomva")) == 3
    env["GIT_DIR"] = str(timed.broomva / ".git")
    for event in ("session-start", "stop", "stop-failure"):
        run = timed.hook(event, {"session_id": "s-2", "cwd": str(timed.broomva)}, env=env)
        assert (run.rc, run.stdout, run.stderr) == (0, "", "")
        assert run.elapsed < HOOK_WALL_S, "%s waited %.0f ms on git" % (event, run.elapsed * 1000)
    time.sleep(0.05)
    pids = [int(p) for p in pidfile.read_text().split()]
    assert len(pids) == 3, "the fake git never ran on the GIT_DIR path: the test is vacuous"
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise AssertionError("git %d outlived its hook" % pid)
    assert len(timed.events("broomva")) == 3
    # The inner layer on its own: git is bounded by its own timeout and killed,
    # without relying on the wrapper's alarm.
    monkeypatch.setenv("PATH", env["PATH"])
    t0 = time.monotonic()
    assert ctx._git(str(timed.broomva), ["rev-parse"], timeout=0.05) is None
    assert time.monotonic() - t0 < 0.5


def _grow(world: World, n: int, sessions: int = 50) -> None:
    scope = ctx.resolve_scope(str(world.worktree))
    elsewhere = scope._replace(where=scope.where._replace(branch="filler", cwd="/elsewhere"))
    with open(scope.log, "ab") as fh:
        for i in range(n):
            ev = ctx.make_event("session.stop", elsewhere, "s-fill-%d" % (i % sessions),
                                {"arc_status": "DONE", "arc_line": "ARC-STATUS: DONE " + "x " * 50})
            fh.write((json.dumps(ev, sort_keys=True, separators=(",", ":")) + "\n").encode())


def test_a_large_log_does_not_slow_session_start(timed: World) -> None:
    timed.start("s-peer", timed.worktree)
    _grow(timed, 20000)  # ~11 MB of log from 50 sessions: many turns, as in real use
    scope = ctx.resolve_scope(str(timed.worktree))
    ctx.read_board(scope)
    for i in range(3):
        run = timed.start("s-new-%d" % i, timed.worktree)
        assert run.rc == 0 and run.elapsed < HOOK_WALL_S, "%.0f ms" % (run.elapsed * 1000)
        assert "s-peer" in run.context


def test_a_large_log_with_no_cached_board_is_cut_off_not_parsed(timed: World) -> None:
    timed.start("s-peer", timed.worktree)
    _grow(timed, 20000)
    assert not (timed.store("broomva") / "board.json").exists()  # hooks never wrote one
    for event in ("session-start", "stop"):
        run = timed.hook(event, {"session_id": "s-late", "cwd": str(timed.worktree)})
        assert (run.rc, run.stdout) == (0, "")
        assert run.elapsed < HOOK_WALL_S, "%.0f ms" % (run.elapsed * 1000)


def test_a_board_over_the_cap_is_not_parsed_and_the_cut_off_is_recorded(timed: World) -> None:
    """20,000 distinct sessions make a board.json well over HOOK_BOARD_CAP. A
    json.loads that size is one C call the alarm cannot interrupt (216 ms on a
    macOS runner in round 2), so SessionStart must not start it: it appends its
    event, gives no brief, and records why. Stop and StopFailure never read the
    board at all."""
    timed.start("s-peer", timed.worktree)
    _grow(timed, 20000, sessions=20000)
    scope = ctx.resolve_scope(str(timed.worktree))
    ctx.read_board(scope)
    assert scope.board_path.stat().st_size > ctx.HOOK_BOARD_CAP
    for event in ("session-start", "stop", "stop-failure"):
        run = timed.hook(event, {"session_id": "s-new", "cwd": str(timed.worktree)})
        assert (run.rc, run.stdout, run.stderr) == (0, "", "")
        assert run.elapsed < HOOK_WALL_S, "%.0f ms" % (run.elapsed * 1000)
    assert [e["session_id"] for e in timed.events("broomva")[-3:]] == ["s-new"] * 3, "the appends were lost"
    stages = [json.loads(line)["stage"] for line in
              (timed.home / ".local" / "state" / "ctx" / "hook-misses.jsonl").read_text().splitlines()]
    assert stages == ["board-cap"]
    report = timed.cli("doctor", cwd=timed.worktree)
    assert report.returncode == 1 and "over the %d a hook will parse" % ctx.HOOK_BOARD_CAP in report.stdout
    assert "move events.jsonl aside by hand" in report.stdout and "ctx board --rebuild" in report.stdout
