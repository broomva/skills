"""board.json is a cache of the log's fold, and nothing else.

Hooks only append; they never write board.json under the lock (Stop and
StopFailure never write it at all). Readers fold the log since the cache's
offset. Cache + tail equals a from-scratch rebuild, byte for byte. A hand edit
is detected and replaced. SessionStart never parses the whole log inside its
deadline: it folds at most FOLD_CAP past the cache and writes the cache back,
so it catches up across runs.
"""
from __future__ import annotations

import json
import time

import ctx
from conftest import World


def _drive(world: World) -> None:
    world.start("s-a", world.broomva, PASEO_AGENT_ID="agent-a")
    world.start("s-b", world.worktree)
    world.stop("s-a", world.broomva, "working\nARC-STATUS: IN_PROGRESS step 2")
    world.stop("s-b", world.worktree, "ARC-STATUS: BLOCKED needs owner\n\nARC-STATUS: MERGED https://github.com/o/r/pull/9")
    world.died("s-a", world.broomva, "overloaded")
    world.start("s-a", world.broomva, PASEO_AGENT_ID="agent-a")  # resume after the death
    world.stop("s-c", world.worktree)


def _log(world: World) -> bytes:
    return (world.store("broomva") / "events.jsonl").read_bytes()


def _scope(world: World) -> ctx.Scope:
    return ctx.resolve_scope(str(world.broomva))


def test_cache_plus_tail_equals_a_full_rebuild(world: World) -> None:
    world.start("s-0", world.broomva)
    assert world.cli("board", cwd=world.broomva).returncode == 0  # writes the cache
    cached = world.board("broomva")
    _drive(world)  # the cache is now behind the log
    assert world.board("broomva") == cached, "a hook wrote board.json"
    board, complete = ctx.read_board(_scope(world), refresh=1 << 30)
    assert complete and ctx.board_bytes(board) == ctx.board_bytes(ctx.rebuild("broomva", _log(world)))
    world.cli("board", cwd=world.broomva)
    res = world.cli("board", "--rebuild", cwd=world.broomva)
    assert "the cached board.json equalled a rebuild of what it had folded" in res.stdout


def test_the_same_log_gives_the_same_bytes(world: World) -> None:
    _drive(world)
    data = _log(world)
    first = ctx.board_bytes(ctx.rebuild("broomva", data))
    assert all(ctx.board_bytes(ctx.rebuild("broomva", data)) == first for _ in range(3))
    # Folding in any two pieces at a line boundary is the same fold.
    cuts = [i + 1 for i, b in enumerate(data) if b == 0x0A][:-1]
    for cut in cuts:
        board = ctx.rebuild("broomva", data[:cut])
        ctx.fold(board, data[cut:], cut, data[:cut][-ctx.TAIL_BYTES:])
        assert ctx.board_bytes(board) == first, cut


def test_the_board_folds_what_happened(world: World) -> None:
    _drive(world)
    b, _ = ctx.read_board(_scope(world))
    a, bb, c = b["sessions"]["s-a"], b["sessions"]["s-b"], b["sessions"]["s-c"]
    assert (a["state"], a["starts"], a["died_error"], a["paseo_agent_id"]) == ("started", 2, "overloaded", "agent-a")
    assert (a["arc_status"], bb["arc_status"]) == ("OTHER", "MERGED")  # IN_PROGRESS is not a kept keyword
    assert bb["arc_line"] == "ARC-STATUS: MERGED https://github.com/o/r/pull/9"
    assert (bb["branch"], c["starts"], c["state"]) == ("feat/x", 0, "stopped")
    assert b["events"] == 7 and b["skipped_lines"] == 0


def test_latest_state_is_by_timestamp_not_append_order(world: World) -> None:
    scope = _scope(world)
    t = time.time()
    ctx.append(scope, ctx.make_event("session.stop", scope, "s-x",
                                     {"arc_status": "DONE", "arc_line": "ARC-STATUS: DONE later"}, t + 5))
    ctx.append(scope, ctx.make_event("session.died", scope, "s-x", {"error": "server_error"}, t))
    row = ctx.read_board(scope)[0]["sessions"]["s-x"]
    assert (row["state"], row["arc_status"], row["last_ts"]) == ("stopped", "DONE", ctx.now_ts(t + 5))
    assert row["died_error"] == "server_error"


def test_a_torn_line_is_skipped_and_healed(world: World) -> None:
    world.start("s-1", world.broomva)
    with open(world.store("broomva") / "events.jsonl", "ab") as fh:
        fh.write(b'{"v":1,"type":"session.stop","ts":"2026-')  # a writer SIGKILLed mid-line
    world.stop("s-2", world.broomva)
    lines = _log(world).splitlines()
    assert json.loads(lines[-1])["session_id"] == "s-2", "the next append did not start on a fresh line"
    board, _ = ctx.read_board(_scope(world))
    assert (board["events"], board["skipped_lines"]) == (2, 1)
    assert ctx.board_bytes(board) == ctx.board_bytes(ctx.rebuild("broomva", _log(world)))


def test_a_hand_edited_cache_is_detected_and_replaced(world: World) -> None:
    _drive(world)
    world.cli("board", cwd=world.broomva)
    path = world.store("broomva") / "board.json"
    good = path.read_bytes()
    edited = json.loads(good)
    edited["sessions"]["s-a"]["arc_status"] = "MERGED"
    path.write_text(json.dumps(edited))
    report = world.cli("doctor", cwd=world.broomva)
    assert report.returncode == 1 and "differs from a rebuild of the log it claims to have folded" in report.stdout
    res = world.cli("board", "--rebuild", cwd=world.broomva)
    assert "differed from a rebuild (hand-edited or corrupt) and was replaced" in res.stdout
    assert path.read_bytes() == good


def test_a_replaced_log_is_detected_by_the_tail_signature(world: World) -> None:
    _drive(world)
    world.cli("board", cwd=world.broomva)
    log = world.store("broomva") / "events.jsonl"
    lines = log.read_bytes().splitlines(keepends=True)
    log.write_bytes(b"".join(reversed(lines)))  # same length, different content: the offset cannot tell
    board, _ = ctx.read_board(_scope(world))
    assert ctx.board_bytes(board) == ctx.board_bytes(ctx.rebuild("broomva", log.read_bytes()))


def test_stop_and_stop_failure_never_write_board_json(world: World) -> None:
    world.stop("s-1", world.broomva, "ARC-STATUS: DONE")
    world.died("s-1", world.broomva)
    assert not (world.store("broomva") / "board.json").exists()


def _filler(world: World, n: int) -> None:
    scope = ctx.resolve_scope(str(world.worktree))
    elsewhere = scope._replace(where=scope.where._replace(branch="filler", cwd="/elsewhere"))
    with open(scope.log, "ab") as fh:
        for i in range(n):
            ev = ctx.make_event("session.stop", elsewhere, "s-fill-%d" % (i % 50), {})
            fh.write((json.dumps(ev, sort_keys=True, separators=(",", ":")) + "\n").encode())


def test_session_start_reads_the_cache_and_never_the_whole_log(world: World, monkeypatch) -> None:
    """Round-4 finding: no full parse of events.jsonl inside the 200 ms deadline."""
    world.start("s-peer", world.worktree)
    _filler(world, 1500)
    scope = ctx.resolve_scope(str(world.worktree))
    ctx.read_board(scope)  # the CLI path: the cache is now current
    assert scope.log.stat().st_size > 3 * ctx.FOLD_CAP

    reads = []
    real_pread = ctx._pread_all
    monkeypatch.setattr(ctx, "_pread_all", lambda fd, n, off: reads.append(n) or real_pread(fd, n, off))
    monkeypatch.setattr(ctx, "read_log", lambda scope: (_ for _ in ()).throw(AssertionError("read the log")))
    monkeypatch.setattr(ctx, "rebuild", lambda *a: (_ for _ in ()).throw(AssertionError("full rebuild")))
    out = ctx.run_hook("session-start", json.dumps({"session_id": "s-new", "cwd": str(world.worktree)}),
                       deadline=time.monotonic() + 5)
    assert "s-peer" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert max(reads) <= ctx.MAX_LINE, "SessionStart read %d log bytes" % max(reads)


def test_session_start_catches_a_stale_cache_up_across_runs(world: World) -> None:
    """No cache and a log far past the fold cap: each SessionStart folds at most
    FOLD_CAP, writes the cache back and gives no brief (a `fold-cap` miss); the
    runs converge, and then the brief is back."""
    world.start("s-peer", world.worktree)
    _filler(world, 1500)
    size = (world.store("broomva") / "events.jsonl").stat().st_size
    offsets = []
    out = ""
    for i in range(12):
        out = ctx.run_hook("session-start", json.dumps({"session_id": "s-new-%d" % i, "cwd": str(world.worktree)}),
                           deadline=time.monotonic() + 5)
        offsets.append(world.board("broomva")["log_offset"])
        if out:
            break
        assert ctx.MISSED == "fold-cap"
    assert out and "s-peer" in out, offsets
    assert offsets == sorted(offsets) and len(offsets) >= size // ctx.FOLD_CAP


def test_ts_round_trips_without_datetime() -> None:
    for t in (0.0, 951782400.5, 1790700000.123, 4102444799.999, 1709164800.0):  # incl. 2000-02-29, 2024-02-29
        assert abs(ctx.parse_ts(ctx.now_ts(t)) - t) < 0.001, t
    assert ctx.now_ts(1709164800.0) == "2024-02-29T00:00:00.000Z"


def test_doctor_on_a_cache_far_behind_the_log(world: World) -> None:
    world.start("s-1", world.worktree)
    world.cli("board", cwd=world.worktree)
    _filler(world, 400)
    report = world.cli("doctor", cwd=world.worktree)
    assert report.returncode == 0 and "WARN      the cache is" in report.stdout  # it catches up by itself
    world.cli("board", cwd=world.worktree)
    assert "WARN      the cache is" not in world.cli("doctor", cwd=world.worktree).stdout
