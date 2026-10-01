"""ctx doctor --compare: the phase-1 exit comparison (core spec §9 as merged
in broomva/workspace#842).

One scope, one fixed clock. Each session below is built to land in exactly
one bucket, so every reason on the ordered list is exercised; the pass bar is
the raw sets; the registration time is kept in compare.jsonl's first line; a
run writes none of the store's four files.
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
REG = ctx.now_ts(T - 5.5 * H)


def _sid(n: int) -> str:
    return "%08d-c0de-4000-8000-%012d" % (n, n)


def _event(world, etype: str, sid: str, cwd: Path, at: float) -> None:
    scope = ctx.resolve_scope(str(cwd))
    assert scope is not None
    ev = ctx.make_event(etype, scope, sid, {"error": "rate_limit"} if etype == "session.died" else {}, now=at)
    assert ctx.append(scope, ev)


def _transcript(world, sid: str, entry_at: float, cwd: Path = None, mtime: float = None) -> Path:
    """A transcript whose last timestamped entry is at `entry_at`, followed by
    the untimestamped records Claude Code appends later; mtime defaults to it."""
    d = world.home / ".claude" / "projects" / "-fixture-project"
    d.mkdir(parents=True, exist_ok=True)
    p = d / (sid + ".jsonl")
    head = json.dumps({"type": "user", "cwd": str(cwd or world.broomva), "timestamp": ctx.now_ts(entry_at - 60)})
    p.write_text(head + "\n" + json.dumps({"type": "assistant", "timestamp": ctx.now_ts(entry_at)}) + "\n"
                 + '{"type": "last-prompt"}\n{"type": "cost-state"}\n')
    m = mtime if mtime else entry_at
    os.utime(p, (m, m))
    return p


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
    s = {k: _sid(i) for i, k in enumerate("ABCDEFGHIJKLM", 1)}
    _event(world, "session.start", s["A"], b, T - 1 * H)           # both
    _transcript(world, s["A"], T - 0.5 * H)
    _event(world, "session.start", s["B"], wt, T - 1 * H)          # board: no transcript anywhere
    _event(world, "session.start", s["C"], b, T - 2 * H)           # board: transcript, not listed
    _transcript(world, s["C"], T - 2 * H)
    _event(world, "session.start", s["D"], b, T - 1 * H)           # board: listed, no entry in the window
    _transcript(world, s["D"], T - 8 * H, mtime=T - 0.5 * H)       # (its mtime moved; its entries didn't)
    _event(world, "session.start", s["J"], wt, T - 1 * H)          # both, cwd gone: placed by its row
    _transcript(world, s["J"], T - 0.2 * H)
    _event(world, "session.start", s["E"], b, T - 4 * H)
    _event(world, "session.died", s["E"], b, T - 3 * H)            # died, then went on
    _transcript(world, s["E"], T - 0.1 * H)
    _transcript(world, s["F"], T - 0.1 * H)                        # no event at all
    _transcript(world, s["G"], T - 5.8 * H)                        # before registration
    _event(world, "session.start", s["H"], b, T - 7 * H)           # one long turn
    _transcript(world, s["H"], T - 0.3 * H)
    _transcript(world, s["I"], T - 0.1 * H, cwd=world.sri)         # another scope
    _event(world, "session.start", s["K"], b, T - 2 * H)
    _event(world, "session.died", s["K"], b, T - 1 * H + 1)        # died after its last entry, stayed dead,
    _transcript(world, s["K"], T - 1 * H, mtime=T - 0.02 * H)      # though its mtime moved an hour later
    _transcript(world, s["L"], T - 0.4 * H)                        # in scope, on neither side (a finished claude -p)
    _event(world, "session.start", s["M"], b, T - 20 * H)          # an idle session: mtime moved, no entry in the window
    _transcript(world, s["M"], T - 20 * H, mtime=T - 0.1 * H)
    listing = [_row(s["A"], b), _row(s["D"], b), _row(s["J"], gone), _row(s["E"], b), _row(s["F"], b),
               _row(s["G"], b), _row(s["H"], b), _row(s["I"], world.sri), _row(s["K"], b), _row(s["M"], b)]
    lf = world.home / "listing.json"
    lf.write_text(json.dumps(listing))
    return s, lf


def _run(lf, **kw):
    return ctx_compare.compare("broomva", ctx_compare.load_listing(str(lf)), ctx_compare.transcripts(), T,
                               ctx.parse_ts(REG), **kw)


def test_every_reason_in_its_order_and_the_pass_bar_is_the_raw_sets(world, scene):
    s, lf = scene
    res = _run(lf)
    by = {d["session_id"]: d["reason"] for d in res["differences"]}
    assert by == {s["B"]: "no-transcript", s["C"]: "ended", s["D"]: "unexplained",
                  s["E"]: "died-then-continued", s["F"]: "no-event", s["G"]: "pre-registration",
                  s["H"]: "stale-in-turn", s["K"]: "died"}
    assert set(res["reasons"]) == set(ctx_compare.REASONS)
    assert (res["board_live"], res["sessions"], res["both"]) == (5, 7, 2)
    assert res["board_pct"] == pytest.approx(2 / 5, abs=1e-4)      # raw: no reason is taken out
    assert res["session_pct"] == pytest.approx(2 / 7, abs=1e-4)
    assert res["pass"] is False and res["evidence"] is True
    # M's mtime is in the window, its entries aren't: not on the session side.
    assert s["M"] not in by
    # L: in scope, an entry in the window, neither listed nor live: uncounted.
    assert res["neither_ids"] == [s["L"]] and res["neither"] == 1


def test_the_registration_time_is_kept_in_the_first_line(world, scene, capsys):
    s, lf = scene
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), now=T) == 2
    assert "pass --registered" in capsys.readouterr().out
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), registered=REG, now=T) == 1
    assert ctx_compare.registered_on_file("broomva") == REG
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), now=T) == 1  # read from the file
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), registered=ctx.now_ts(T - 9 * H),
                                     now=T) == 2
    assert "disagrees" in capsys.readouterr().out


def test_a_run_changes_none_of_the_store_files_and_appends_one_summary(world, scene, capsys):
    s, lf = scene
    store = world.store("broomva")
    before = _hashes(store)
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), registered=REG, now=T) == 1
    assert _hashes(store) == before
    lines = (store / "compare.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["pass"] is False
    assert "differences" not in json.loads(lines[0]) and "neither_ids" not in json.loads(lines[0])
    out = capsys.readouterr().out
    assert "FAIL" in out and "stale-in-turn" in out and "uncounted" in out


def test_a_matching_board_passes_with_exit_0(world):
    sid = _sid(1)
    _event(world, "session.start", sid, world.broomva, T - 1 * H)
    _transcript(world, sid, T - 0.5 * H)
    lf = world.home / "listing.json"
    lf.write_text(json.dumps([_row(sid, world.broomva)]))
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), registered=REG, now=T) == 0


def test_no_evidence_is_not_a_pass(world, capsys):
    _transcript(world, _sid(1), T - 0.1 * H, cwd=world.sri)
    lf = world.home / "listing.json"
    lf.write_text(json.dumps([_row(_sid(1), world.sri)]))
    res = ctx_compare.compare("broomva", ctx_compare.load_listing(str(lf)), ctx_compare.transcripts(), T,
                              ctx.parse_ts(REG))
    assert res["evidence"] is False and res["pass"] is False and res["board_pct"] is None
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), registered=REG, now=T) == 1
    assert "NO EVIDENCE" in capsys.readouterr().out


def test_an_unreadable_listing_or_transcripts_fail_and_say_so_on_disk(world, tmp_path, capsys):
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    assert ctx_compare.run_for_scope("broomva", listing_file=str(empty), registered=REG, now=T) == 1
    lf = world.home / "listing.json"
    lf.write_text(json.dumps([_row(_sid(1), world.broomva)]))
    assert not (world.home / ".claude" / "projects").exists()
    assert ctx_compare.run_for_scope("broomva", listing_file=str(lf), now=T) == 1
    assert capsys.readouterr().out.count("could not be read") == 2
    last = json.loads((world.store("broomva") / "compare.jsonl").read_text().splitlines()[-1])
    assert last["pass"] is False and last["error"]


def test_the_board_row_places_only_a_session_whose_cwd_is_gone(world):
    sid = _sid(1)
    _event(world, "session.start", sid, world.broomva, T - 1 * H)
    _transcript(world, sid, T - 0.5 * H)
    reg = ctx.parse_ts(REG)
    res = ctx_compare.compare("broomva", [_row(sid, world.other)], ctx_compare.transcripts(), T, reg)
    assert res["sessions"] == 0
    res = ctx_compare.compare("broomva", [_row(sid, world.home / "wt" / "removed")], ctx_compare.transcripts(), T, reg)
    assert res["sessions"] == 1 and res["both"] == 1


def test_the_last_timestamped_entry_is_read_past_untimestamped_records(world):
    p = _transcript(world, _sid(1), T - 2 * H, mtime=T - 1 * H)
    assert ctx_compare.last_entry_ts(str(p)) == pytest.approx(T - 2 * H, abs=0.01)
    assert ctx_compare.last_entry_ts(str(p) + ".missing") is None


def test_the_cli_runs_it_from_a_scoped_directory(world, scene):
    s, lf = scene
    proc = world.cli("doctor", "--compare", "--agents-json", str(lf), "--registered", REG, "--json",
                     cwd=world.broomva)
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["scope"] == "broomva"


def test_the_cli_says_so_outside_a_scope(world):
    proc = world.cli("doctor", "--compare", cwd=world.other)
    assert proc.returncode == 1 and "not in a scope" in proc.stdout
