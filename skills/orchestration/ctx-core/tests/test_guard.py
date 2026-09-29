"""No free text is stored, and one cheap guard covers what is.

Phase 1 stores structured fields only: ids, paths, the branch, event types and
timestamps, the ARC-STATUS keyword with at most 120 characters of a strict
`ARC-STATUS: WORD` line, and the StopFailure error class. The guard drops any
field holding crm/, Bearer, ghp_, gho_, github_pat_, sk-, xox or AKIA at the
start of a token, or a run of 32+ ASCII letters and digits. It is substring
finds and one byte-translate scan: linear, which the 10 KB / 1 MB tests pin.
"""
from __future__ import annotations

import json
import time

import pytest

import ctx
from conftest import World

#: Synthetic, never-issued values, assembled from pieces so no secret-shaped
#: literal sits in the source (push protection rightly refuses one).
_J = "".join
CAUGHT = {
    "github classic": _J(["gh", "p_", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"]),
    "github oauth": _J(["gh", "o_", "A1b2C3d4E5f6G7h8I9j0"]),
    "github fine-grained": _J(["github", "_pat_", "11ABCDEFG0123456789_abc"]),
    "anthropic": _J(["sk", "-ant-api03-", "x" * 20]),
    "openai": _J(["sk", "-proj-", "Ab1" * 4]),
    "slack": _J(["xo", "xb-", "1234567890-", "AbCdEf"]),
    "aws": _J(["AK", "IA", "Z" * 16]),
    "bearer": _J(["Authorization: Bea", "rer ", "abc.def"]),
    "a long run": _J(["Zq9Xw8Ve7Ru6Tp5So4", "Rn3Qm2Pl1Ok0Nj9Mi8"]),
    "a commit sha": "427341c0b1e5f3a9d2c4b6a8e0f1d3c5b7a9e1f3",
    "crm path": "/Users/x/broomva/crm/deals/acme.md",
    "crm in a url": "file:///Users/x/crm/deals.md",
}
KEPT = [
    "https://github.com/broomva/skills/pull/246",
    "fix/task-list desk-top mycrm/notes flexoxo",
    "a run of 31 is fine: " + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p",
    "no secrets here, just a status",
]


def _arc(text: str) -> dict:
    return ctx._extract_arc("ARC-STATUS: BLOCKED " + text)


@pytest.mark.parametrize("name", sorted(CAUGHT))
def test_the_guard_drops_the_line_and_keeps_the_keyword(name: str) -> None:
    assert not ctx.guard_ok(CAUGHT[name])
    assert _arc("leaked %s here" % CAUGHT[name]) == {"arc_status": "BLOCKED"}


@pytest.mark.parametrize("text", KEPT)
def test_ordinary_text_passes(text: str) -> None:
    assert ctx.guard_ok(text)
    assert _arc(text)["arc_line"] == "ARC-STATUS: BLOCKED " + text


def test_needles_match_at_a_token_start_in_any_case() -> None:
    assert not ctx.guard_ok("x SK-abc") and not ctx.guard_ok("(bearer abc)") and not ctx.guard_ok("akiaz")
    assert ctx.guard_ok("task-abc") and ctx.guard_ok("desk-SK") and ctx.guard_ok("CRMs/")


def test_the_guard_sees_the_whole_line_before_the_cut() -> None:
    """A token straddling character 120 must not survive as a prefix."""
    for pad in range(90, 125):
        line = "x " * (pad // 2) + CAUGHT["github classic"]
        out = _arc(line)
        assert "arc_line" not in out, pad


def test_a_prose_message_stores_nothing_of_itself(world: World) -> None:
    prose = ("I looked at the diff and I think the owner should rotate the Stripe key; "
             "the password is hunter22 and the ticket is BRO-2591. Merging now.")
    world.stop("s-1", world.broomva, prose)
    world.stop("s-2", world.broomva, prose + "\nARC-STATUS: MERGED https://x/pull/3")
    world.died("s-3", world.broomva)
    raw = (world.store("broomva") / "events.jsonl").read_text()
    for word in ("hunter22", "Stripe", "rotate", "Merging", "resets at 5pm", "partial answer"):
        assert word not in raw, word
    assert [json.loads(line)["payload"] for line in raw.splitlines()] == [
        {}, {"arc_status": "MERGED", "arc_line": "ARC-STATUS: MERGED https://x/pull/3"}, {"error": "rate_limit"}]


def test_nothing_the_guard_catches_reaches_the_store_through_the_hooks(world: World) -> None:
    for i, value in enumerate(CAUGHT.values()):
        world.stop("s-%d" % i, world.broomva, "ARC-STATUS: DONE " + value)
    world.cli("board", cwd=world.broomva)
    store = "".join(p.read_text() for p in world.store("broomva").glob("*.json*"))
    for value in CAUGHT.values():
        assert value not in store, value
    assert store.count('"arc_status":"DONE"') >= len(CAUGHT)


@pytest.mark.parametrize("line", [
    # a free-text payload key
    {"type": "session.stop", "payload": {"arc_status": "DONE", "note": "free text"}},
    # a status line that is not the strict shape, or too long, or guard-failing
    {"type": "session.stop", "payload": {"arc_status": "DONE", "arc_line": "done, merged it"}},
    {"type": "session.stop", "payload": {"arc_status": "DONE", "arc_line": "ARC-STATUS: DONE " + "x " * 60}},
    {"type": "session.stop", "payload": {"arc_status": "DONE", "arc_line": "ARC-STATUS: DONE " + CAUGHT["aws"]}},
    {"type": "session.stop", "payload": {"arc_status": "SHIPPED"}},
    # an error that is text, not a class
    {"type": "session.died", "payload": {"error": "429 Too Many Requests"}},
    {"type": "session.died", "payload": {"error": "rate_limit", "error_details": "resets at 5pm"}},
    # a start with a payload, an unknown top-level key, a credential in an identifier
    {"type": "session.start", "payload": {"model": "claude"}},
    {"type": "session.start", "payload": {}, "note": "free text"},
    {"type": "session.start", "payload": {}, "cwd": "/w/" + CAUGHT["github classic"]},
])
def test_a_hand_written_line_with_free_text_is_skipped_on_read(line: dict) -> None:
    ev = {"v": 1, "ts": "2026-09-29T00:00:00.000Z", "session_id": "s-1", "cwd": "/w", "repo": "/w/.git",
          "branch": "main"}
    ev.update(line)
    board = ctx.rebuild("x", (json.dumps(ev) + "\n").encode())
    assert (board["events"], board["skipped_lines"], board["sessions"]) == (0, 1, {})


# ---------------------------------------------------------------- linear time

def _best(fn, arg, runs: int = 3) -> float:
    out = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn(arg)
        out.append(time.perf_counter() - t0)
    return min(out)


UNITS = ["a-", "sk-", "task-", "A", "xox", "crm/", "Bearer ", "x ", "a1-"]


@pytest.mark.parametrize("unit", UNITS)
@pytest.mark.parametrize("fn", [ctx.guard_ok, ctx._flat, ctx._extract_arc], ids=["guard", "flat", "extract"])
def test_linear_at_10kb_and_1mb(fn, unit: str) -> None:
    """100x the input must cost well under the 10,000x a quadratic path costs."""
    small = (unit * (10_000 // len(unit) + 1))[:10_000]
    big = (unit * (1_000_000 // len(unit) + 1))[:1_000_000]
    if fn is ctx._extract_arc:  # give the line scanner real lines to scan
        small, big = small.replace("x ", "\n"), big.replace("x ", "\n")
        small, big = "ARC-STATUS: DONE " + small, "ARC-STATUS: DONE " + big
    t_small, t_big = _best(fn, small), _best(fn, big)
    assert t_big < 1.0, "%.0f ms at 1 MB" % (t_big * 1000)
    assert t_big / max(t_small, 2e-5) < 400, "100x the input cost %.0fx" % (t_big / max(t_small, 2e-5))


def test_extracting_from_a_1mb_message_of_many_lines_is_linear() -> None:
    lines_small = "ARC-STATUS: DONE step\nnoise line\n" * 300
    lines_big = "ARC-STATUS: DONE step\nnoise line\n" * 30000
    t_small, t_big = _best(ctx._extract_arc, lines_small), _best(ctx._extract_arc, lines_big)
    assert t_big < 1.0 and t_big / max(t_small, 2e-5) < 400
