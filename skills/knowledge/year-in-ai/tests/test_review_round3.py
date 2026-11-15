"""Regressions for the round-3 review of PR #290 (findings at a8464af)."""

from __future__ import annotations

import datetime as dt
import itertools
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from yia.ledger import attention as T  # noqa: E402
from yia.ledger import make_row as _make_row  # noqa: E402
from yia.ledger import store as L  # noqa: E402
from yia.model import Window  # noqa: E402
from yia.readers import _common  # noqa: E402

T0 = 1793000000.0
_n = itertools.count()


def row(**kw):
    kw.setdefault("occurrence", f"r3-{next(_n)}")
    return _make_row(**kw)


def test_a_torn_last_line_does_not_swallow_the_next_row(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    ledger.dir.mkdir(parents=True)
    fresh = row(src="t3", harness="t3", kind="prompt", ts=T0, text="after the crash", session="s", author="human")
    ledger._month_file(T0).write_text("{broken")  # an interrupted earlier write, no newline
    assert ledger.write([fresh]) == {ledger._month_file(T0).stem: 1}
    rows = list(ledger.rows())
    assert [r["id"] for r in rows] == [fresh["id"]]
    assert ledger.malformed_lines == 1


def test_a_legacy_row_in_any_month_refuses_the_write(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    ledger.dir.mkdir(parents=True)
    (ledger.dir / "2023-11.jsonl").write_text(json.dumps({"id": "old", "v": 3, "ts": 1700000000.0}) + "\n")
    with pytest.raises(L.LegacyLedgerError):
        ledger.write([row(src="t3", harness="t3", kind="prompt", ts=T0, text="new", session="s", author="human")])
    assert not ledger._month_file(T0).exists()


def test_rows_cut_by_the_text_only_cutoff_are_not_agent_activity():
    t3 = row(src="t3", harness="t3", kind="prompt", ts=T0, text="plan the recap", session="t", author="human")
    t3_reply = row(src="t3", harness="t3", kind="reply", ts=T0 + 5, text="Here is the plan.", session="t",
                   author="human", turn=t3["id"])
    bridged = row(src="bridged", harness="bridged", kind="prompt", ts=T0 + 30, text="plan the recap", session="b",
                  author="unknown")
    bridged_reply = row(src="bridged", harness="bridged", kind="reply", ts=T0 + 60, text="the plan, rendered",
                        session="b", author="unknown", turn=bridged["id"])
    summary = T.fold([t3, t3_reply, bridged, bridged_reply], text_only_until=T0 - 1)
    assert summary["read"]["reply_words_measured"] == 4
    assert summary["agents_own"] == {"replies": 0, "words": 0}


def test_unknown_author_sdk_sessions_are_not_agent_activity():
    p = row(src="claude_code", harness="claude:sdk-ts", kind="prompt", ts=T0, text="a T3-driven turn", session="c",
            author="unknown")
    r = row(src="claude_code", harness="claude:sdk-ts", kind="reply", ts=T0 + 5, text="done", session="c",
            author="unknown", turn=p["id"])
    assert T.fold([p, r])["agents_own"] == {"replies": 0, "words": 0}


def test_the_nearest_candidate_wins_when_it_is_earlier():
    first = row(src="t3", harness="t3", kind="prompt", ts=T0, text="yes", session="t", author="human")
    second = row(src="t3", harness="t3", kind="prompt", ts=T0 + 100, text="yes", session="t", author="human")
    second_reply = row(src="t3", harness="t3", kind="reply", ts=T0 + 105, text="ok", session="t", author="human",
                       turn=second["id"])
    bridged = row(src="bridged", harness="bridged", kind="prompt", ts=T0 + 10, text="yes", session="b",
                  author="unknown")
    bridged_reply = row(src="bridged", harness="bridged", kind="reply", ts=T0 + 20, text="done and pushed",
                        session="b", author="unknown", turn=bridged["id"])
    summary = T.fold([first, second, second_reply, bridged, bridged_reply])
    assert summary["written"]["prompts"] == 2
    assert summary["read"]["reply_words_measured"] == 3 + 1  # the bridged reply belongs to the first turn


def test_offset_timestamps_inside_the_window_are_kept(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{"type":"user","timestamp":"2026-01-01T00:30:00+02:00"}\n'  # 22:30Z, prefix after the bound
                    '{"type":"user","timestamp":"2025-12-31T17:40:00-05:00"}\n'  # 22:40Z, prefix before the bound
                    '{"type":"user","timestamp":"2026-01-01T03:30:00+02:00"}\n')  # 01:30Z, outside
    window = Window(start=dt.datetime(2025, 12, 31, 22, tzinfo=dt.timezone.utc),
                    end=dt.datetime(2025, 12, 31, 23, tzinfo=dt.timezone.utc))
    records = list(_common.iter_records(path, window))
    assert len(records) == 2


def test_a_turns_reply_is_its_final_revision_in_the_period_it_was_written():
    p = row(src="t3", harness="t3", kind="prompt", ts=100.0, text="question", session="s", author="human")
    early = row(src="t3", harness="t3", kind="reply", ts=199.0, text="one two three", session="s", author="human",
                turn=p["id"])
    final = row(src="t3", harness="t3", kind="reply", ts=201.0, text="one two three four", session="s",
                author="human", turn=p["id"])
    inside = T.fold([p, early, final], window=(100.0, 200.0))
    after = T.fold([p, early, final], window=(200.0, 300.0))
    assert inside["written"]["prompts"] == 1 and inside["read"]["reply_words_measured"] == 0
    assert after["read"]["reply_words_measured"] == 4  # read once, as its final revision, when it was written
