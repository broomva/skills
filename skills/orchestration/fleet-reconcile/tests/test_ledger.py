"""The write-ahead ledger (spec §5.7): appends, validation, corruption, the
concurrency of appends from separate processes, and the folds."""
from __future__ import annotations

import json
import multiprocessing
import sys
from pathlib import Path

import pytest

from fleetlib import ledger

BASE = {"scope": "broomva", "tick": 1, "dry_run": True}


def test_an_append_is_stamped_and_read_back(tmp_path):
    rec = ledger.append(tmp_path, dict(BASE, kind="tick_fire", detail="gh: keyring"))
    assert rec["v"] == 1 and rec["ts"].endswith("Z")
    records, corrupt = ledger.read(tmp_path)
    assert records == [rec] and corrupt == 0
    assert oct((tmp_path / "ledger.jsonl").stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("bad", [
    {"kind": "nonsense"},
    {"kind": "intent", "verb": "mail"},                       # no id
    {"kind": "intent", "verb": "merge", "id": "1-1"},         # not a verb
    {"kind": "failed", "verb": "mail", "id": "1-1", "reason": "because"},
])
def test_invalid_records_are_refused(tmp_path, bad):
    with pytest.raises(ledger.LedgerError):
        ledger.append(tmp_path, dict(BASE, **bad))
    with pytest.raises(ledger.LedgerError):
        ledger.append(tmp_path, {"kind": "tick_fire"})  # no scope, tick or dry_run


def test_a_corrupt_line_is_counted_not_silently_skipped(tmp_path):
    ledger.append(tmp_path, dict(BASE, kind="tick_fire"))
    with (tmp_path / "ledger.jsonl").open("a") as fh:
        fh.write('{"kind": "intent", "verb": "ma')  # a torn write, no newline
    ledger.append(tmp_path, dict(BASE, kind="runner_exit", exit_code=0))
    records, corrupt = ledger.read(tmp_path)
    assert [r["kind"] for r in records] == ["tick_fire", "runner_exit"] and corrupt == 1


def test_detail_text_passes_the_guard(tmp_path):
    rec = ledger.append(tmp_path, dict(BASE, kind="tick_fire", detail="token ghp_" + "a" * 36))
    assert rec["detail"] == "[withheld]"


def _worker(args):
    path, n, k = args
    sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "scripts"),
                    str(Path(__file__).resolve().parents[2] / "ctx-core" / "scripts")]
    from fleetlib import ledger as lg

    for i in range(n):
        lg.append(Path(path), {"scope": "broomva", "tick": k, "dry_run": True, "kind": "tick_fire",
                               "detail": "w%d-%d" % (k, i)})


def test_concurrent_appends_from_separate_processes_lose_nothing(tmp_path):
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        pool.map(_worker, [(str(tmp_path), 50, k) for k in range(4)])
    records, corrupt = ledger.read(tmp_path)
    assert corrupt == 0 and len(records) == 200
    assert len({r["detail"] for r in records}) == 200


def _ask_intent(tick, asks, rid="1-1"):
    return dict(BASE, tick=tick, kind="intent", verb="ask", id=rid, key="asks:%d" % tick,
                target={"batch": "/x/asks/%05d.md" % tick, "asks": asks})


def test_ask_batches_fold_with_notifications_and_acks(tmp_path):
    a1 = [{"id": "a1", "key": "k1", "class": "3", "question": "q1"},
          {"id": "a2", "key": "k2", "class": "7", "question": "q2"}]
    ledger.append(tmp_path, _ask_intent(1, a1, "1-1"))
    ledger.append(tmp_path, dict(BASE, kind="done", verb="ask", id="1-1", result={"notified": True}))
    ledger.append(tmp_path, _ask_intent(2, [{"id": "a1", "key": "k3", "class": "github", "question": "q3"}], "2-1"))
    records, _ = ledger.read(tmp_path)
    b = ledger.ask_batches(records)
    assert [x["tick"] for x in b] == [1, 2] and len(b[0]["notified"]) == 1 and b[1]["notified"] == []
    assert len(ledger.unacked(records)) == 2
    ledger.append(tmp_path, dict(BASE, tick=1, kind="ack", acks={"tick": 1, "asks": ["a1"]}))
    records, _ = ledger.read(tmp_path)
    assert [a["id"] for a in ledger.open_asks(ledger.ask_batches(records)[0])] == ["a2"]
    ledger.append(tmp_path, dict(BASE, tick=1, kind="ack", acks={"tick": 1, "asks": "all"}))
    ledger.append(tmp_path, dict(BASE, tick=2, kind="ack", acks={"tick": 2, "asks": "all"}))
    records, _ = ledger.read(tmp_path)
    assert ledger.unacked(records) == []


def test_only_live_done_spawns_make_a_fleet_key(tmp_path):
    live = dict(BASE, dry_run=False, kind="intent", verb="spawn", id="3-1", key="broomva-workspace-pr7",
                target={"name": "broomva-workspace-pr7"})
    ledger.append(tmp_path, live)
    ledger.append(tmp_path, dict(BASE, dry_run=False, kind="done", verb="spawn", id="3-1",
                                 result={"session_id": "s-1"}))
    ledger.append(tmp_path, dict(live, dry_run=True, id="3-2", key="broomva-workspace-pr8"))
    ledger.append(tmp_path, dict(BASE, dry_run=True, kind="done", verb="spawn", id="3-2",
                                 result={"session_id": "s-2"}))
    ledger.append(tmp_path, dict(live, id="3-3", key="broomva-workspace-pr9"))  # intent, never closed
    records, _ = ledger.read(tmp_path)
    assert ledger.spawned(records) == {"broomva-workspace-pr7": ["s-1"]}
