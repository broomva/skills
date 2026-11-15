"""Regressions for fresh round 2, Stratum A (findings at 4a80aee)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from test_reader_contract import _claude_records, turn, write_jsonl  # noqa: E402

from yia.ledger import archive as A  # noqa: E402
from yia.ledger import attention as T  # noqa: E402
from yia.ledger import make_row  # noqa: E402
from yia.ledger import sources as S  # noqa: E402
from yia.ledger import store as L  # noqa: E402

T0 = 1793000000.0


def prompt(text, ts=T0, occurrence="m1"):
    return make_row(src="t3", harness="t3", kind="prompt", ts=ts, text=text, session="s", author="human",
                    occurrence=occurrence)


def test_a_revision_that_returns_to_earlier_text_is_the_latest(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    for text in ("alpha", "beta gamma", "alpha"):
        ledger.write([prompt(text)])
    rows = list(ledger.rows())
    assert len(rows) == 3
    assert T.fold(rows)["written"]["words"] == 1  # "alpha" again, not "beta gamma"
    assert ledger.write([prompt("alpha")]) == {}  # unchanged since the last harvest


def test_revision_order_is_harvest_order_not_month_order(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    ledger.write([prompt("one", ts=T0)])  # November
    ledger.write([prompt("two words", ts=T0 - 40 * 86400)])  # the same message, re-dated into September
    rows = list(ledger.rows())  # September's file is read first
    assert T.fold(rows)["written"]["words"] == 2


def test_a_same_size_rewrite_with_its_old_mtime_restored_is_still_archived(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    f = src / "p" / "s.jsonl"
    f.write_text("aaaa\n")
    A.copy_additive(src, dst)
    before = f.stat()
    time.sleep(0.01)
    f.write_text("bbbb\n")
    os.utime(f, ns=(before.st_atime_ns, before.st_mtime_ns))  # a restore that keeps the old timestamp
    A.copy_additive(src, dst)
    archived = sorted(p.read_text() for p in (dst / "p").iterdir())
    assert archived == ["aaaa\n", "bbbb\n"]


def test_a_diverged_transcript_that_keeps_growing_extends_one_revision(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    f = src / "p" / "s.jsonl"
    f.write_text("a\nb\n")
    A.copy_additive(src, dst)
    f.write_text("x\n")  # rewritten: diverges from the archive
    A.copy_additive(src, dst)
    for line in ("y\n", "z\n", "w\n"):  # then grows normally, week after week
        with f.open("a") as handle:
            handle.write(line)
        A.copy_additive(src, dst)
    files = sorted(p.name for p in (dst / "p").iterdir())
    assert files == ["s.jsonl", "s.rev-1.jsonl"]
    assert (dst / "p" / "s.jsonl").read_text() == "a\nb\n"
    assert (dst / "p" / "s.rev-1.jsonl").read_text() == "x\ny\nz\nw\n"


def test_authored_words_are_counted_from_the_authored_text():
    text = " ".join(["authoredwordlong"] * 10) + " <pasted_content>" + " x" * 1000 + "</pasted_content>"
    row = prompt(text)
    assert row["authored_words"] == 10


def test_history_authored_words_exclude_the_paste(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(json.dumps({"display": "look at this [Pasted text #1 +40 lines]", "timestamp": int(T0 * 1000),
                                "project": "/p", "sessionId": "h",
                                "pastedContents": {"1": {"content": "log line\n" * 40}}}) + "\n")
    _report, rows = S.read_claude_history(path, None)
    (row,) = list(rows)
    assert row["authored_words"] == 3 and row["words"] > 80
