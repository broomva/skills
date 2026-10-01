"""The lock never blocks a session.

fcntl.flock with LOCK_NB, retried for at most 150 ms (40 ms inside a hook, except StopFailure).
If it is still not acquired, the append is skipped and the hook exits 0. Two cases: a writer that
holds the lock for seconds, and two writers appending at the same time.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time

import ctx
from conftest import HOOK_WALL_S, SCRIPTS, World

HOLDER = textwrap.dedent("""
    import fcntl, os, sys, time
    fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    print("held", flush=True)
    time.sleep(float(sys.argv[2]))
""")

WRITER = textwrap.dedent("""
    import json, sys, time
    sys.path.insert(0, sys.argv[1])
    import ctx
    scope = ctx.resolve_scope(sys.argv[2])
    go = float(sys.argv[4])
    while time.time() < go:
        time.sleep(0.001)
    worst, written = 0.0, 0
    for i in range(int(sys.argv[3])):
        ev = ctx.make_event("session.stop", scope, "%s-%d" % (sys.argv[5], i), {})
        t0 = time.monotonic()
        ok = ctx.append(scope, ev)
        worst = max(worst, time.monotonic() - t0)
        written += ok
    print(json.dumps({"worst": worst, "written": written}))
""")


def _hold(world: World, seconds: float) -> subprocess.Popen:
    world.store("broomva").mkdir(parents=True, exist_ok=True)
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(world.store("broomva") / "events.lock"),
                               str(seconds)], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    return holder


def test_a_held_lock_skips_the_append_and_the_hook_returns_in_time(timed: World) -> None:
    timed.start("s-seed", timed.broomva)
    before = len(timed.events("broomva"))
    holder = _hold(timed, 5)
    try:
        for run in (timed.stop("s-1", timed.broomva, "ARC-STATUS: DONE"), timed.start("s-2", timed.broomva),
                    timed.died("s-3", timed.broomva)):
            assert run.rc == 0 and run.stderr == ""
            assert run.elapsed < HOOK_WALL_S, "a hook blocked %.0f ms on a held lock" % (run.elapsed * 1000)
        assert len(timed.events("broomva")) == before, "an append went through a held lock"

        scope = ctx.resolve_scope(str(timed.broomva))
        t0 = time.monotonic()
        assert ctx.append(scope, ctx.make_event("session.stop", scope, "s-4", {})) is False
        waited = time.monotonic() - t0
        # It gives up at its budget, and not long after: it never blocks.
        assert ctx.LOCK_BUDGET_S <= waited < ctx.LOCK_BUDGET_S + 0.1, waited
    finally:
        holder.kill()
        holder.wait()
    assert timed.stop("s-5", timed.broomva).rc == 0
    assert timed.events("broomva")[-1]["session_id"] == "s-5", "the lock was not released with its holder"


def test_two_concurrent_writers_neither_blocks_and_no_line_tears(timed: World) -> None:
    timed.start("s-seed", timed.broomva)
    n, go = 40, time.time() + 0.5
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, str(SCRIPTS), str(timed.broomva), str(n), str(go), tag],
                              stdout=subprocess.PIPE, text=True) for tag in ("a", "b")]
    results = [json.loads(p.communicate(timeout=60)[0]) for p in procs]
    for r in results:
        assert r["worst"] < HOOK_WALL_S, "a writer blocked %.0f ms" % (r["worst"] * 1000)

    raw = (timed.store("broomva") / "events.jsonl").read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.decode().splitlines()
    assert all(json.loads(line) for line in lines), "a torn or interleaved line"
    written = sum(r["written"] for r in results)
    assert len(lines) == 1 + written
    assert all(r["written"] > 0 for r in results), "a writer never got the lock: %s" % results
    board, complete = ctx.read_board(ctx.resolve_scope(str(timed.broomva)))
    assert complete and ctx.board_bytes(board) == ctx.board_bytes(ctx.rebuild("broomva", raw))


def test_a_skipped_append_is_recorded_as_a_miss(timed: World) -> None:
    """A lock-skipped session.died would otherwise leave a ghost live row for 6 h
    with nothing anywhere saying why."""
    timed.start("s-seed", timed.broomva)
    holder = _hold(timed, 5)
    try:
        run = timed.died("s-1", timed.broomva)
        assert (run.rc, run.stdout) == (0, "")
    finally:
        holder.kill()
        holder.wait()
    misses = (timed.home / ".local" / "state" / "ctx" / "hook-misses.jsonl").read_text().splitlines()
    rec = json.loads(misses[-1])
    assert (rec["event"], rec["stage"]) == ("stop-failure", "lock")


def test_the_lock_is_held_only_for_the_append(timed: World) -> None:
    """The board is not touched under the lock, so its size cannot lengthen the
    hold: under 5 ms with a 10,000-session board.json in place."""
    scope = ctx.resolve_scope(str(timed.broomva))
    elsewhere = scope._replace(where=scope.where._replace(branch="filler", cwd="/elsewhere"))
    scope.store.mkdir(parents=True, exist_ok=True)
    with open(scope.log, "ab") as fh:
        for i in range(10000):
            ev = ctx.make_event("session.start", elsewhere, "s-%05d" % i, {})
            fh.write((json.dumps(ev, sort_keys=True, separators=(",", ":")) + "\n").encode())
    board, _ = ctx.read_board(scope)
    assert len(board["sessions"]) == 10000 and scope.board_path.stat().st_size > 1 << 20
    holds = []
    for i in range(20):
        assert ctx.append(scope, ctx.make_event("session.stop", scope, "s-hold", {}))
        holds.append(ctx.LAST_LOCK_HOLD)
    assert sorted(holds)[len(holds) // 2] < 0.005, "median hold %.1f ms" % (sorted(holds)[10] * 1000)
    assert max(holds) < 0.05, holds
