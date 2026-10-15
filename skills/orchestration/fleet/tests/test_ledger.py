"""The write-ahead ledger (spec §5.7): appends, the record schema, corruption,
the concurrency of appends from separate processes, and the folds."""
from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

import pytest

from fleetlib import ledger

BASE = {"scope": "broomva", "tick": 1, "dry_run": True, "by": "tick"}


def test_an_append_is_stamped_and_read_back(tmp_path):
    rec = ledger.append(tmp_path, dict(BASE, kind="tick_fire", detail="gh: keyring"))
    assert rec["v"] == 1 and rec["ts"].endswith("Z") and rec["id"] == "1-1"
    records, corrupt = ledger.read(tmp_path)
    assert records == [rec] and corrupt == 0
    assert oct((tmp_path / "ledger.jsonl").stat().st_mode & 0o777) == "0o600"
    second = ledger.append(tmp_path, dict(BASE, kind="runner_exit", exit=0))
    assert second["id"] == "1-2"  # unique per record
    owner = ledger.append(tmp_path, dict(BASE, tick=None, by="owner:tty", kind="ack", of="1-1", asks="all"))
    assert owner["id"].startswith("owner-") and owner["tick"] is None


@pytest.mark.parametrize("bad", [
    {"kind": "nonsense"},
    {"kind": "intent", "verb": "mail"},                       # no key
    {"kind": "intent", "verb": "merge", "key": "k"},          # not a verb
    {"kind": "failed", "verb": "mail", "of": "1-1", "reason": "because"},
    {"kind": "seen", "result": {}},                           # answers no intent
    {"kind": "tick_fire", "tick": "3"},                       # tick not an int
])
def test_invalid_records_are_refused(tmp_path, bad):
    with pytest.raises(ledger.LedgerError):
        ledger.append(tmp_path, dict(BASE, **bad))
    with pytest.raises(ledger.LedgerError):
        ledger.append(tmp_path, {"kind": "tick_fire", "scope": "broomva", "tick": 1, "dry_run": True})  # no by


def test_owner_records_in_one_millisecond_get_distinct_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger.time, "time", lambda: 1_790_000_000.0)
    ids = [ledger.append(tmp_path, dict(BASE, tick=None, by="owner:t", kind="ack", of="1-1", asks="all"))["id"]
           for _ in range(3)]
    assert len(set(ids)) == 3 and ids[0] == "owner-1790000000000"


def test_a_corrupt_line_is_counted_not_silently_skipped(tmp_path):
    ledger.append(tmp_path, dict(BASE, kind="tick_fire"))
    with (tmp_path / "ledger.jsonl").open("a") as fh:
        fh.write('{"kind": "intent", "verb": "ma')  # a torn write, no newline
    ledger.append(tmp_path, dict(BASE, kind="runner_exit", exit=0))
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
        lg.append(Path(path), {"scope": "broomva", "tick": k, "dry_run": True, "by": "tick", "kind": "tick_fire",
                               "detail": "w%d-%d" % (k, i)})


def test_concurrent_appends_from_separate_processes_lose_nothing_and_ids_stay_unique(tmp_path):
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        pool.map(_worker, [(str(tmp_path), 50, k) for k in range(4)])
    records, corrupt = ledger.read(tmp_path)
    assert corrupt == 0 and len(records) == 200
    assert len({r["detail"] for r in records}) == 200 and len({r["id"] for r in records}) == 200


def _ask(tmp_path, tick, asks):
    return ledger.append(tmp_path, dict(BASE, tick=tick, kind="intent", verb="ask", key="scope:broomva",
                                        target={"batch": "/x/asks/%05d.md" % tick, "asks": asks}))


def test_ask_batches_fold_seen_and_answers(tmp_path):
    b1 = _ask(tmp_path, 1, [{"id": "a1", "key": "k1", "class": "3", "question": "q1"},
                            {"id": "a2", "key": "k2", "class": "7", "question": "q2"}])
    ledger.append(tmp_path, dict(BASE, kind="seen", of=b1["id"], result={"button": None, "gave_up": True}))
    b2 = _ask(tmp_path, 2, [{"id": "a1", "key": "k3", "class": "github", "question": "q3"}])
    records, _ = ledger.read(tmp_path)
    b = ledger.ask_batches(records)
    assert [x["tick"] for x in b] == [1, 2] and len(b[0]["shown"]) == 1 and not b[0]["seen"]
    assert set(ledger.open_by_key(records)) == {"k1", "k2", "k3"}
    ledger.append(tmp_path, dict(BASE, tick=None, by="owner:t", kind="ack", of=b1["id"], asks=["a1"]))
    records, _ = ledger.read(tmp_path)
    assert [a["id"] for a in ledger.open_asks(ledger.ask_batches(records)[0])] == ["a2"]
    assert set(ledger.open_by_key(records)) == {"k2", "k3"}
    ledger.append(tmp_path, dict(BASE, kind="seen", of=b2["id"], result={"button": "Seen", "gave_up": False}))
    ledger.append(tmp_path, dict(BASE, tick=None, by="owner:t", kind="ack", of=b1["id"], asks="all"))
    ledger.append(tmp_path, dict(BASE, tick=None, by="owner:t", kind="ack", of=b2["id"], asks="all"))
    records, _ = ledger.read(tmp_path)
    assert ledger.ask_batches(records)[1]["seen"] and ledger.open_by_key(records) == {}


def test_a_resolution_closes_a_key_without_answering_it(tmp_path):
    _ask(tmp_path, 1, [{"id": "a1", "key": "k1", "class": "3", "question": "q"}])
    ledger.append(tmp_path, dict(BASE, tick=2, kind="ack", keys=["k1"], resolved=True))
    records, _ = ledger.read(tmp_path)
    assert ledger.key_states(records)["k1"]["state"] == "resolved" and ledger.open_by_key(records) == {}
    assert ledger.open_asks(ledger.ask_batches(records)[0])  # the batch itself was never answered


def test_only_live_done_spawns_make_a_fleet_key(tmp_path):
    live = dict(BASE, dry_run=False, by="act", kind="intent", verb="spawn", key="broomva-workspace-pr7",
                target={"name": "broomva-workspace-pr7"})
    i1 = ledger.append(tmp_path, live)
    ledger.append(tmp_path, dict(BASE, dry_run=False, by="act", kind="done", verb="spawn", of=i1["id"],
                                 result={"session_id": "s-1"}))
    i2 = ledger.append(tmp_path, dict(live, dry_run=True, key="broomva-workspace-pr8"))
    ledger.append(tmp_path, dict(BASE, by="act", kind="done", verb="spawn", of=i2["id"], result={"would": True}))
    ledger.append(tmp_path, dict(live, key="broomva-workspace-pr9"))  # intent, never closed
    records, _ = ledger.read(tmp_path)
    assert ledger.spawned(records) == {"broomva-workspace-pr7": ["s-1"]}
