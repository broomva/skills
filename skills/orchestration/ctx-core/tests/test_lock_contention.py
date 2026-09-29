"""The lock never blocks a session.

fcntl.flock with LOCK_NB, retried for at most 150 ms. If it is still not
acquired, the append is skipped and the hook exits 0. Two cases: a writer that
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
        ok, _ = ctx.append(scope, ev)
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
        assert ctx.append(scope, ctx.make_event("session.stop", scope, "s-4", {})) == (False, None)
        waited = time.monotonic() - t0
        assert ctx.LOCK_BUDGET_S <= waited < HOOK_WALL_S, waited
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
    assert written >= n, "contention should skip a few appends, not most of them: %s" % results
    # The board was kept up to date under the same lock by whichever writer won.
    assert (timed.store("broomva") / "board.json").read_bytes() == ctx.board_bytes(ctx.rebuild("broomva", raw))
