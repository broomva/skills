"""The owner channel as a ledger (fleetlib/ledger_ask.py, BRO-2908)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fleetlib import ledger_ask


@pytest.fixture
def sec(tmp_path, monkeypatch):
    monkeypatch.setenv(ledger_ask.LOCK_ROOT_ENV, str(tmp_path / "locks"))
    return {"scope": "sri", "state_dir": str(tmp_path / "state")}


def _open(key, cls="observe", q=None, of="b1", tick=7, ask_id="a1"):
    return {key: {"ask": {"id": ask_id, "class": cls, "question": q or "Question about %s?" % key},
                  "of": of, "tick": tick, "ts": "2026-10-08T10:00:00Z"}}


def _all(*opens):
    """Every open occurrence, `(key, batch)`, as fleet_reconcile passes them."""
    return [(k, v["of"]) for d in opens for k, v in d.items()]


def answer_as_maestro(sec, uid, option=None, note="", status="resolved"):
    """Maestro's minimal edit (server/control-asks.ts upsertKey): `key: <JSON>` lines after the entry's id."""
    p = ledger_ask.path(sec)
    lines = p.read_text().splitlines()
    at = next(i for i, ln in enumerate(lines) if ln == '  - id: "%s"' % uid)
    add = ['    answer: %s' % json.dumps(note), '    answered_at: "2026-10-08T12:00:00Z"',
           '    answered_by: "owner:maestro"', '    status: "%s"' % status]
    if option:
        add.insert(0, '    answer_option: "%s"' % option)
    p.write_text("\n".join(lines[:at + 1] + add + lines[at + 1:]) + "\n")


def test_each_open_ask_is_one_entry_kept_from_tick_to_tick_and_a_prompt_blocks(sec):
    asks = {**_open("prompt:s1:x", cls="3", ask_id="a1"), **_open("rules:acme/app", cls="github", ask_id="a2")}
    assert ledger_ask.sync(sec, asks, _all(asks)) == (2, 0)
    assert ledger_ask.sync(sec, asks, _all(asks)) == (0, 0)  # the same occurrences: nothing added
    entries = ledger_ask.read(ledger_ask.path(sec))["asks"]
    assert [(e["fleet"]["key"], e["blocking"], e["class"]) for e in entries] == [
        ("prompt:s1:x", True, "fleet"), ("rules:acme/app", False, "fleet")]
    assert all(e["id"] == e["uid"] and [o["id"] for o in e["options"]] == ["ack"] for e in entries)
    assert oct(ledger_ask.path(sec).stat().st_mode & 0o777) == "0o600"


def test_an_open_question_is_refreshed_and_one_no_longer_open_withdrawn_but_an_answer_is_never_touched(sec):
    both = {**_open("k1"), **_open("k2", ask_id="a2")}
    ledger_ask.sync(sec, both, _all(both))
    u1, u2 = ledger_ask.uid("sri", "k1", "b1"), ledger_ask.uid("sri", "k2", "b1")
    answer_as_maestro(sec, u2, option="ack", note="seen")
    # Still open, reworded: refreshed. k2 is no longer open, but it was answered: untouched.
    assert ledger_ask.sync(sec, _open("k1", q="Reworded?"), _all(_open("k1"))) == (0, 0)
    by = {e["uid"]: e for e in ledger_ask.read(ledger_ask.path(sec))["asks"]}
    assert by[u1]["headline"] == "Reworded?" and ledger_ask.is_open(by[u1])
    assert by[u2]["answer"] == "seen" and by[u2]["status"] == "resolved" and "resolution" not in by[u2]
    # Nothing open any more: k1 is withdrawn.
    assert ledger_ask.sync(sec, {}, []) == (0, 1)
    assert {e["uid"]: e for e in ledger_ask.read(ledger_ask.path(sec))["asks"]}[u1]["status"] == "withdrawn"


def test_an_occurrence_left_open_by_a_skipped_step_is_withdrawn_when_its_condition_comes_back(sec):
    ledger_ask.sync(sec, _open("k1", of="b1"), _all(_open("k1", of="b1")))
    # The b1 occurrence ended and k1 came back as b9 between two ask steps: b1 is no longer open.
    again = _open("k1", of="b9", tick=12)
    assert ledger_ask.sync(sec, again, _all(again)) == (1, 1)
    entries = ledger_ask.read(ledger_ask.path(sec))["asks"]
    assert [(e["fleet"]["batch"], e.get("status")) for e in entries] == [("b1", "withdrawn"), ("b9", None)]


def test_a_condition_that_ends_and_comes_back_is_a_new_entry_beside_the_old_answer(sec):
    ledger_ask.sync(sec, _open("k1", of="b1"), _all(_open("k1", of="b1")))
    answer_as_maestro(sec, ledger_ask.uid("sri", "k1", "b1"), option="ack")
    again = _open("k1", of="b9", tick=12)
    ledger_ask.sync(sec, again, _all(again))
    entries = ledger_ask.read(ledger_ask.path(sec))["asks"]
    assert [e["fleet"]["batch"] for e in entries] == ["b1", "b9"] and ledger_ask.is_open(entries[1])


def test_answers_come_back_with_their_batch_and_ask_and_alerts_are_not_asks(sec):
    one = _open("k1", of="b1", ask_id="a3")
    ledger_ask.sync(sec, one, _all(one))
    ledger_ask.alert(sec, "tick-observe", "tick 9 failed at observe")
    assert ledger_ask.answers(sec) == []
    answer_as_maestro(sec, ledger_ask.uid("sri", "k1", "b1"), option="ack", note="on it")
    alert = next(e for e in ledger_ask.read(ledger_ask.path(sec))["asks"] if e["class"] == "alert")
    answer_as_maestro(sec, alert["uid"], option="ack")
    (got,) = ledger_ask.answers(sec)
    assert (got["batch"], got["ask"], got["option"], got["answer"]) == ("b1", "a3", "ack", "on it")


def test_one_open_alert_per_kind_is_refreshed_and_a_new_one_follows_an_answer(sec):
    first = ledger_ask.alert(sec, "tick-observe", "tick 9 failed")
    assert ledger_ask.alert(sec, "tick-observe", "tick 10 failed") == first
    assert ledger_ask.alert(sec, "lock", "held for 3h") != first
    alerts = [e for e in ledger_ask.read(ledger_ask.path(sec))["asks"] if e["class"] == "alert"]
    # Not blocking: the failing tick is Maestro's own fleet health notice, counted there once.
    assert len(alerts) == 2 and "tick 10 failed" in alerts[0]["headline"] and alerts[0]["blocking"] is False
    answer_as_maestro(sec, first, option="ack")
    time.sleep(1.1)  # the new entry's uid carries the second it was raised
    assert ledger_ask.alert(sec, "tick-observe", "tick 11 failed") != first


def test_a_line_outside_the_subset_fails_loudly_and_nothing_is_written_over_it(sec):
    p = ledger_ask.path(sec)
    p.parent.mkdir(parents=True)
    # A hand edit in plain YAML (an unquoted string) and a block scalar: each fails the read, and the file stays.
    for text in ("arc: fleet-sri\nasks:\n  - id: x\n    headline: Plain words, unquoted\n",
                 "arc: fleet-sri\nasks:\n  - id: x\n    note: |\n      block scalar\n"):
        p.write_text(text)
        with pytest.raises(ledger_ask.LedgerError):
            ledger_ask.sync(sec, _open("k1"), _all(_open("k1")))
        assert p.read_text() == text


def test_the_lock_is_maestros_key_and_a_live_holder_keeps_it_but_a_dead_one_is_reclaimed(sec, tmp_path):
    p = ledger_ask.path(sec)
    p.parent.mkdir(parents=True)
    key = hashlib.sha256(("%s/%s" % (os.path.realpath(p.parent), p.name)).encode()).hexdigest()[:16]
    assert ledger_ask.lock_key(p) == key
    held = Path(os.environ[ledger_ask.LOCK_ROOT_ENV]) / ("%s.d" % key)
    held.mkdir(parents=True)
    (held / "pid").write_text("%d %d\n" % (os.getpid(), ledger_ask._start_of(os.getpid()) or 0))
    old = time.time() - 600
    os.utime(held, (old, old))
    with pytest.raises(ledger_ask.LedgerError):
        with ledger_ask.locked(p, wait=0.2):
            pass
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (held / "pid").write_text("%d 1\n" % dead.pid)
    os.utime(held, (old, old))
    with ledger_ask.locked(p, wait=1.0):
        assert (held / "token").is_file()
    assert not held.exists()


def test_a_fresh_lock_of_a_dead_writer_is_still_waited_on(sec):
    p = ledger_ask.path(sec)
    p.parent.mkdir(parents=True)
    held = Path(os.environ[ledger_ask.LOCK_ROOT_ENV]) / ("%s.d" % ledger_ask.lock_key(p))
    held.mkdir(parents=True)
    (held / "pid").write_text("999999 1\n")  # dead, but under LOCK_STALE_S old
    with pytest.raises(ledger_ask.LedgerError):
        with ledger_ask.locked(p, wait=0.2):
            pass


def test_an_ask_answered_from_a_terminal_closes_in_the_ledger_too(sec):
    ledger_ask.sync(sec, _open("k1"), _all(_open("k1")))
    ledger_ask.sync(sec, {}, [], [("k1", "b1")])
    (e,) = ledger_ask.read(ledger_ask.path(sec))["asks"]
    assert e["status"] == "resolved" and "fleet ack" in e["resolution"] and not ledger_ask.is_open(e)
    assert ledger_ask.answers(sec) == []  # not the owner's answer in Maestro: nothing to read back


def test_an_answer_holding_a_raw_line_separator_reads_back(sec):
    """JS's JSON.stringify leaves U+2028, U+2029 and U+0085 raw: one pasted note must not break the channel."""
    ledger_ask.sync(sec, _open("k1"), _all(_open("k1")))
    p = ledger_ask.path(sec)
    lines = p.read_text().split("\n")
    at = next(i for i, ln in enumerate(lines) if ln.startswith("  - id: "))
    lines.insert(at + 1, '    answer: "one\u2028two\u2029three\u0085four"')
    lines.insert(at + 1, '    answer_option: "ack"')
    p.write_text("\n".join(lines))
    (got,) = ledger_ask.answers(sec)
    assert got["answer"] == "one\u2028two\u2029three\u0085four"
    assert ledger_ask.sync(sec, _open("k1"), _all(_open("k1"))) == (0, 0)  # and the next sync still reads it


def test_a_lock_taken_over_before_the_write_writes_nothing(sec):
    p = ledger_ask.path(sec)
    p.parent.mkdir(parents=True)
    p.write_text("arc: \"fleet-sri\"\nasks:\n")
    with ledger_ask.locked(p) as still_ours:
        held = Path(os.environ[ledger_ask.LOCK_ROOT_ENV]) / ("%s.d" % ledger_ask.lock_key(p))
        (held / "token").write_text("another writer\n")
        with pytest.raises(ledger_ask.LedgerError):
            ledger_ask._write(p, {"asks": [{"id": "x"}]}, "sri", still_ours)
    assert p.read_text() == "arc: \"fleet-sri\"\nasks:\n" and held.exists()  # and theirs is left alone
