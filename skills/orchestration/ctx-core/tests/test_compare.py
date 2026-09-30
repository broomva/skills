"""ctx doctor --compare: the phase-1 exit comparison (core spec §9).

One scope, one fixed clock. Each session below is built to land in exactly one
bucket, so every reason on the fixed list is exercised, the excluded reasons
are shown not to count toward the 95%, and the store's four files are shown
unchanged by a run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import ctx
import ctx_compare
import pytest

T = 1_790_000_000.0  # the fixed "now"
H = 3600.0


def _sid(n: int) -> str:
    return "%08d-c0de-4000-8000-%012d" % (n, n)


def _event(world, etype: str, sid: str, cwd: Path, at: float, payload=None) -> None:
    scope = ctx.resolve_scope(str(cwd))
    assert scope is not None
    ev = ctx.make_event(etype, scope, sid, payload if payload is not None else (
        {"error": "rate_limit"} if etype == "session.died" else {}), now=at)
    assert ctx.append(scope, ev)


def _transcript(world, sid: str, at: float) -> None:
    d = world.home / ".claude" / "projects" / "-fixture-project"
    d.mkdir(parents=True, exist_ok=True)
    p = d / (sid + ".jsonl")
    p.write_text("{}\n")
    os.utime(p, (at, at))


def _row(sid: str, cwd: Path) -> dict:
    return {"sessionId": sid, "cwd": str(cwd), "kind": "interactive", "name": "n-" + sid[:4],
            "startedAt": int((T - 20 * H) * 1000)}


def _hashes(store: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(store.iterdir())
            if p.name in ("events.jsonl", "events.lock", "board.json", "board-snapshot.json")}


@pytest.fixture
def scene(world):
    b, wt = world.broomva, world.worktree
    gone = world.home / "wt" / "removed-after-merge"
    s = {k: _sid(i) for i, k in enumerate("ABCDEFGHIJK", 1)}
    # Board-live rows
    _event(world, "session.start", s["A"], b, T - 1 * H)           # both
    _transcript(world, s["A"], T - 0.5 * H)
    _event(world, "session.start", s["B"], wt, T - 1 * H)          # no transcript anywhere
    _event(world, "session.start", s["C"], b, T - 2 * H)           # transcript, not listed
    _transcript(world, s["C"], T - 2 * H)
    _event(world, "session.start", s["D"], b, T - 1 * H)           # listed, transcript stale
    _transcript(world, s["D"], T - 8 * H)
    _event(world, "session.start", s["J"], wt, T - 1 * H)          # both, cwd gone: placed by its row
    _transcript(world, s["J"], T - 0.2 * H)
    # Listed sessions that are not board-live
    _event(world, "session.start", s["E"], b, T - 4 * H)
    _event(world, "session.died", s["E"], b, T - 3 * H)            # died, then went on
    _transcript(world, s["E"], T - 0.1 * H)
    _transcript(world, s["F"], T - 0.1 * H)                        # no event at all
    _transcript(world, s["G"], T - 5.8 * H)                        # before registration
    _event(world, "session.start", s["H"], b, T - 7 * H)           # a long turn
    _transcript(world, s["H"], T - 0.3 * H)
    _transcript(world, s["I"], T - 0.1 * H)                        # sri: another scope
    _event(world, "session.start", s["K"], b, T - 2 * H)
    _event(world, "session.died", s["K"], b, T - 1 * H)            # died, and stayed dead
    _transcript(world, s["K"], T - 1 * H + 30)                     # the death's own write
    listing = [_row(s["A"], b), _row(s["D"], b), _row(s["J"], gone), _row(s["E"], b), _row(s["F"], b),
               _row(s["G"], b), _row(s["H"], b), _row(s["I"], world.sri), _row(s["K"], b)]
    lf = world.home / "listing.json"
    lf.write_text(json.dumps(listing))
    return s, lf


def test_every_reason_is_exercised_and_the_excluded_ones_do_not_count(world, scene):
    s, lf = scene
    res = ctx_compare.compare("broomva", ctx_compare.load_listing(str(lf)), ctx_compare.transcript_times(), T,
                              hours=6, registered=T - 5.5 * H)
    by = {d["session_id"]: d["reason"] for d in res["differences"]}
    assert by == {s["B"]: "no-transcript", s["C"]: "ended", s["D"]: "unexplained",
                  s["E"]: "died-then-continued", s["F"]: "no-event", s["G"]: "pre-registration",
                  s["H"]: "stale-event", s["K"]: "died"}
    assert set(res["reasons"]) == set(ctx_compare.REASONS)
    assert (res["board_live"], res["sessions"], res["both"]) == (5, 7, 2)
    # Board side: A and J of five, less B and C (excluded) -> 2/3.
    assert res["board_pct"] == pytest.approx(2 / 3, abs=1e-4)
    assert res["board_raw_pct"] == pytest.approx(2 / 5, abs=1e-4)
    # Session side: A and J of seven, less G and K (excluded) -> 2/5.
    assert res["session_pct"] == pytest.approx(2 / 5, abs=1e-4)
    assert res["pass"] is False and res["evidence"] is True


def test_a_run_changes_none_of_the_store_files_and_appends_one_summary(world, scene, capsys):
    s, lf = scene
    store = world.store("broomva")
    before = _hashes(store)
    rc = ctx_compare.run_for_scope("broomva", hours=6, listing_file=str(lf),
                                   registered=ctx.now_ts(T - 5.5 * H), now=T)
    assert rc == 1  # under 95%
    assert _hashes(store) == before
    lines = (store / "compare.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["pass"] is False
    assert "differences" not in json.loads(lines[0])
    out = capsys.readouterr().out
    assert "FAIL" in out and "died-then-continued" in out


def test_a_matching_board_passes_with_exit_0(world):
    b = world.broomva
    sid = _sid(1)
    _event(world, "session.start", sid, b, T - 1 * H)
    _transcript(world, sid, T - 0.5 * H)
    lf = world.home / "listing.json"
    lf.write_text(json.dumps([_row(sid, b)]))
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), now=T) == 0


def test_an_unreadable_listing_fails(world, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert ctx_compare.run_for_scope("broomva", listing_file=str(bad), now=T) == 1
    assert "could not be read" in capsys.readouterr().out


def test_the_cli_runs_it_from_a_scoped_directory(world, scene):
    s, lf = scene
    proc = world.cli("doctor", "--compare", "--agents-json", str(lf), "--json", cwd=world.broomva)
    assert proc.returncode in (0, 1), proc.stderr
    res = json.loads(proc.stdout)
    assert res["scope"] == "broomva" and "differences" in res


def test_the_cli_says_so_outside_a_scope(world):
    proc = world.cli("doctor", "--compare", cwd=world.other)
    assert proc.returncode == 1 and "not in a scope" in proc.stdout


def test_no_evidence_is_not_a_pass(world, tmp_path, capsys):
    # A listing with only another scope's session, and an empty board: nothing
    # to count on either side.
    lf = world.home / "listing.json"
    _transcript(world, _sid(1), T - 0.1 * H)
    lf.write_text(json.dumps([_row(_sid(1), world.sri)]))
    res = ctx_compare.compare("broomva", ctx_compare.load_listing(str(lf)), ctx_compare.transcript_times(), T)
    assert res["evidence"] is False and res["pass"] is False and res["board_pct"] is None
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), now=T) == 1
    assert "NO EVIDENCE" in capsys.readouterr().out


def test_an_empty_listing_or_unreadable_transcripts_fail(world, tmp_path, capsys):
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    assert ctx_compare.run_for_scope("broomva", listing_file=str(empty), now=T) == 1
    lf = world.home / "listing.json"
    lf.write_text(json.dumps([_row(_sid(1), world.broomva)]))
    # No ~/.claude/projects at all in this HOME: the transcripts can't be read.
    assert not (world.home / ".claude" / "projects").exists()
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), now=T) == 1
    assert capsys.readouterr().out.count("could not be read") == 2


def test_the_board_row_places_only_a_session_whose_cwd_is_gone(world):
    b = world.broomva
    sid = _sid(1)
    _event(world, "session.start", sid, b, T - 1 * H)
    _transcript(world, sid, T - 0.5 * H)
    listing = [_row(sid, world.other)]  # the cwd exists and is another repo: not placed by the board row
    res = ctx_compare.compare("broomva", listing, ctx_compare.transcript_times(), T)
    assert res["sessions"] == 0
    listing = [_row(sid, world.home / "wt" / "removed")]  # gone: the row places it
    res = ctx_compare.compare("broomva", listing, ctx_compare.transcript_times(), T)
    assert res["sessions"] == 1 and res["both"] == 1
