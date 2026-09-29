"""board.json is the log folded, and nothing else.

The same log always gives the same bytes. The board kept up to date on every
write equals a from-scratch rebuild. A hand edit is replaced. SessionStart
reads the cached board and never parses the whole log inside its deadline
(Cross-Review round 4 on broomva/workspace#825).
"""
from __future__ import annotations

import json
import time

import ctx
from conftest import World


def _drive(world: World) -> None:
    world.start("s-a", world.broomva, PASEO_AGENT_ID="agent-a", FLEET_ROLE="driver")
    world.start("s-b", world.worktree)
    world.stop("s-a", world.broomva, "working\nARC-STATUS: IN_PROGRESS step 2")
    world.stop("s-b", world.worktree, "ARC-STATUS: BLOCKED needs owner\n\nARC-STATUS: MERGED https://github.com/o/r/pull/9")
    world.died("s-a", world.broomva, "overloaded")
    world.start("s-a", world.broomva, PASEO_AGENT_ID="agent-a")  # resume after the death
    world.stop("s-c", world.worktree)


def _log(world: World) -> bytes:
    return (world.store("broomva") / "events.jsonl").read_bytes()


def test_the_board_kept_on_write_equals_a_full_rebuild(world: World) -> None:
    _drive(world)
    on_disk = (world.store("broomva") / "board.json").read_bytes()
    assert on_disk == ctx.board_bytes(ctx.rebuild("broomva", _log(world)))
    res = world.cli("board", "--rebuild", cwd=world.broomva)
    assert "the cached board.json was identical" in res.stdout
    assert (world.store("broomva") / "board.json").read_bytes() == on_disk


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
    b = world.board("broomva")
    a, bb, c = b["sessions"]["s-a"], b["sessions"]["s-b"], b["sessions"]["s-c"]
    assert (a["state"], a["starts"], a["died_reason"], a["fleet_role"], a["paseo_agent_id"]) == \
        ("started", 2, "overloaded", "driver", "agent-a")
    assert (a["arc_status"], bb["arc_status"]) == ("IN_PROGRESS", "MERGED")
    assert bb["arc_line"] == "ARC-STATUS: MERGED https://github.com/o/r/pull/9"
    assert (bb["branch"], c["starts"], c["state"]) == ("feat/x", 0, "stopped")
    assert b["events"] == 7 and b["skipped_lines"] == 0


def test_latest_state_is_by_timestamp_not_append_order(world: World) -> None:
    scope = ctx.resolve_scope(str(world.broomva))
    t = time.time()
    ctx.append(scope, ctx.make_event("session.stop", scope, "s-x", {"arc_status": "DONE", "arc_line": "later"}, t + 5))
    ctx.append(scope, ctx.make_event("session.died", scope, "s-x", {"error_type": "server_error"}, t))
    row = world.board("broomva")["sessions"]["s-x"]
    assert (row["state"], row["arc_status"], row["last_ts"]) == ("stopped", "DONE", ctx.now_ts(t + 5))
    assert row["died_reason"] == "server_error"


def test_a_torn_line_is_skipped_and_healed(world: World) -> None:
    world.start("s-1", world.broomva)
    with open(world.store("broomva") / "events.jsonl", "ab") as fh:
        fh.write(b'{"v":1,"type":"session.stop","ts":"2026-')  # a writer SIGKILLed mid-line
    world.stop("s-2", world.broomva)
    lines = _log(world).splitlines()
    assert json.loads(lines[-1])["session_id"] == "s-2", "the next append did not start on a fresh line"
    board = world.board("broomva")
    assert (board["events"], board["skipped_lines"]) == (2, 1)
    assert ctx.board_bytes(board) == ctx.board_bytes(ctx.rebuild("broomva", _log(world)))


def test_a_hand_edited_board_is_replaced(world: World) -> None:
    _drive(world)
    path = world.store("broomva") / "board.json"
    good = path.read_bytes()
    edited = json.loads(good)
    edited["sessions"]["s-a"]["arc_status"] = "MERGED"
    path.write_text(json.dumps(edited))
    assert "differs from a full rebuild" in world.cli("doctor", cwd=world.broomva).stdout
    res = world.cli("board", "--rebuild", cwd=world.broomva)
    assert "differed and was replaced" in res.stdout
    assert path.read_bytes() == good


def test_a_replaced_log_is_detected_by_the_tail_signature(world: World) -> None:
    _drive(world)
    log = world.store("broomva") / "events.jsonl"
    lines = log.read_bytes().splitlines(keepends=True)
    # Same length, different content: the offset alone cannot tell.
    log.write_bytes(b"".join(reversed(lines)))
    world.stop("s-z", world.broomva)
    assert (world.store("broomva") / "board.json").read_bytes() == \
        ctx.board_bytes(ctx.rebuild("broomva", log.read_bytes()))


def test_session_start_reads_the_cached_board_and_never_the_whole_log(world: World, monkeypatch) -> None:
    """Round-4 finding: no full parse of events.jsonl inside the 200 ms deadline."""
    world.start("s-peer", world.worktree)
    scope = ctx.resolve_scope(str(world.worktree))
    # Grow the log well past the fold cap, keeping the cached board current.
    # Filler on another branch in another cwd: not relevant to the brief.
    elsewhere = scope._replace(where=scope.where._replace(branch="filler", cwd="/elsewhere"))
    filler = [ctx.make_event("session.stop", elsewhere, "s-fill-%d" % i, {}) for i in range(1500)]
    with open(scope.log, "ab") as fh:
        for ev in filler:
            fh.write((json.dumps(ev, sort_keys=True, separators=(",", ":")) + "\n").encode())
    board, _ = ctx.sync_board(scope)
    assert board and scope.log.stat().st_size > 3 * ctx.FOLD_CAP

    reads = []
    real_pread = ctx._pread_all
    monkeypatch.setattr(ctx, "_pread_all", lambda fd, n, off: reads.append(n) or real_pread(fd, n, off))
    monkeypatch.setattr(ctx, "read_log", lambda scope: (_ for _ in ()).throw(AssertionError("read the log")))
    monkeypatch.setattr(ctx, "rebuild", lambda *a: (_ for _ in ()).throw(AssertionError("full rebuild")))
    out = ctx.run_hook("session-start", json.dumps({"session_id": "s-new", "cwd": str(world.worktree)}),
                       deadline=time.monotonic() + 5)
    assert "s-peer" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert max(reads) <= ctx.MAX_LINE, "SessionStart read %d log bytes" % max(reads)

    # With no cached board and a log past the cap, the hook leaves the board
    # alone and injects nothing, rather than parse the log.
    scope.board_path.unlink()
    reads.clear()
    out = ctx.run_hook("session-start", json.dumps({"session_id": "s-new2", "cwd": str(world.worktree)}),
                       deadline=time.monotonic() + 5)
    assert out == "" and not scope.board_path.exists()
    assert max(reads, default=0) <= ctx.FOLD_CAP
    assert json.loads(scope.log.read_bytes().splitlines()[-1])["session_id"] == "s-new2", "registration was lost"
