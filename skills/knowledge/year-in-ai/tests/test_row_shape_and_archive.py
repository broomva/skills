"""Structural guards: rows are text-free by shape, and the archive never loses bytes.

These replace phrase-grepping checks, which passed even with hashing turned
off. Every row from every registered reader must have the exact shape of a
text-free row: identifiers are fixed-length hex, labels come from fixed sets.
"""

from __future__ import annotations

import itertools
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from test_reader_contract import BUILDERS, turn  # noqa: E402

from yia.ledger import ATTR_VALUES, AUTHORS, KINDS, row_fields  # noqa: E402
from yia.ledger import archive as A  # noqa: E402
from yia.ledger import attention as T  # noqa: E402
from yia.ledger import make_row as _make_row  # noqa: E402

HEX16 = re.compile(r"^[0-9a-f]{16}$")
HEX20 = re.compile(r"^[0-9a-f]{20}$")
HARNESS = re.compile(r"^[a-z0-9-]+(:[A-Za-z0-9 _.-]+)?$")
SECRET = "zebra-quartz-session-secret"
_n = itertools.count()


def assert_text_free(row: dict) -> None:
    assert set(row) == set(row_fields())
    assert HEX20.match(row["id"]) and HEX16.match(row["h"]) and HEX16.match(row["o"])
    for key in ("sess", "k", "ph"):
        assert row[key] is None or HEX16.match(row[key]), (key, row[key])
    assert row["turn"] is None or HEX20.match(row["turn"])
    assert row["kind"] in KINDS and row["author"] in AUTHORS
    assert HARNESS.match(row["harness"]), row["harness"]
    if ":" in row["harness"]:
        assert row["harness"].split(":", 1)[1] in set().union(*ATTR_VALUES.values()) | {"other", "history"}
    for key, value in row["attr"].items():
        assert value in ATTR_VALUES[key] | {"other"}
    assert set(row["flags"]) <= {"marker"}
    for key in ("chars", "words", "authored_chars", "authored_words"):
        assert isinstance(row[key], int) and row[key] >= 0
    assert isinstance(row["ts"], float) and isinstance(row["v"], int) and isinstance(row["src"], str)


@pytest.mark.parametrize("store", sorted(BUILDERS))
def test_every_reader_emits_only_text_free_rows(store, tmp_path):
    turns = [turn(1, sess=SECRET), turn(2, sess=SECRET, prompt=f"{SECRET} in a prompt")]
    for hostile in (False, True):
        d = tmp_path / f"h{hostile}"
        d.mkdir()
        _report, rows = BUILDERS[store](d, turns, hostile)()
        rows = list(rows)
        assert rows
        for row in rows:
            assert_text_free(row)
            assert SECRET not in json.dumps(row)


# ------------------------------------------------------------------ archive


def _files(root: Path):
    return {p.relative_to(root).as_posix(): p.read_text() for p in root.rglob("*") if p.is_file()}


def test_a_rewritten_source_is_kept_as_a_revision_and_the_archive_is_untouched(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    f = src / "p" / "s.jsonl"
    f.write_text("old_record1\nold_record2\n")
    A.copy_additive(src, dst)
    f.write_text("old_record2\nnew_record3\n")  # pruned at the front, then appended to
    counts = A.copy_additive(src, dst)
    files = _files(dst)
    assert files["p/s.jsonl"] == "old_record1\nold_record2\n"
    revisions = [v for k, v in files.items() if ".rev-" in k]
    assert revisions == ["old_record2\nnew_record3\n"]
    assert counts["revisions"] == 1
    assert A.copy_additive(src, dst)["revisions"] == 0  # the same revision is not stored twice


def test_a_shorter_source_never_replaces_the_archive(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    f = src / "p" / "s.jsonl"
    f.write_text("a\nb\nc\n")
    A.copy_additive(src, dst)
    f.write_text("a\n")
    A.copy_additive(src, dst)
    assert (dst / "p" / "s.jsonl").read_text() == "a\nb\nc\n"


def test_a_grown_source_replaces_the_archive(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    f = src / "p" / "s.jsonl"
    f.write_text("a\n")
    A.copy_additive(src, dst)
    f.write_text("a\nb\n")
    counts = A.copy_additive(src, dst)
    assert counts["copied"] == 1 and (dst / "p" / "s.jsonl").read_text() == "a\nb\n"
    assert not [k for k in _files(dst) if ".rev-" in k]


def test_same_size_rewrite_is_a_revision_not_an_overwrite(tmp_path):
    import os
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    f = src / "p" / "s.jsonl"
    f.write_text("aaaa\n")
    A.copy_additive(src, dst)
    f.write_text("bbbb\n")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    A.copy_additive(src, dst)
    assert (dst / "p" / "s.jsonl").read_text() == "aaaa\n"
    assert [v for k, v in _files(dst).items() if ".rev-" in k] == ["bbbb\n"]


# ------------------------------------------------------------------ the fold


def row(**kw):
    kw.setdefault("occurrence", f"shape-{next(_n)}")
    return _make_row(**kw)


def test_reply_estimates_come_from_the_same_harness_family():
    rows = []
    for i in range(100):  # CLI replies are short, T3 replies long
        p = row(src="claude_code", harness="claude-cli", kind="prompt", ts=1793000000.0 + i, text=f"cli {i}",
                session="c", author="human")
        rows += [p, row(src="claude_code", harness="claude-cli", kind="reply", ts=1793000000.5 + i, text="two words",
                        session="c", author="human", turn=p["id"])]
        q = row(src="t3", harness="t3:claudeAgent", kind="prompt", ts=1793100000.0 + i, text=f"t3 {i}", session="t",
                author="human")
        rows += [q, row(src="t3", harness="t3:claudeAgent", kind="reply", ts=1793100000.5 + i,
                        text=" ".join(["word"] * 50), session="t", author="human", turn=q["id"])]
    rows.append(row(src="claude_history", harness="claude-cli", kind="prompt", ts=1793200000.0, text="history only",
                    session="h", author="human"))
    assert T.fold(rows)["read"]["reply_words_estimated"] == 2


def test_the_ratio_uses_authored_words_not_pasted_text():
    p = row(src="t3", harness="t3", kind="prompt", ts=1793000000.0,
            text="look at this <pasted_content>" + " log" * 1000 + "</pasted_content>", session="s", author="human")
    r = row(src="t3", harness="t3", kind="reply", ts=1793000005.0, text=" ".join(["w"] * 30), session="s",
            author="human", turn=p["id"])
    s = T.fold([p, r])
    assert s["written"]["authored_words"] == 3
    assert s["ratio_read_to_written"] == round(round(30 * 0.65) / 3, 2)


def test_typed_probes_are_human_writing():
    for text in ("say hello", "what is 1+1? just the number", "reply with ok please"):
        p = row(src="claude_history", harness="claude-cli", kind="prompt", ts=1793000000.0, text=text, session="s",
                author="human")
        assert T.fold([p])["written"]["prompts"] == 1, text


def test_an_unknown_store_key_is_an_error(tmp_path):
    run = subprocess.run([sys.executable, str(SCRIPTS / "year_in_ai.py"), "harvest", "--no-defaults",
                          "--root", "no_such_store=/tmp/nowhere", "--ledger", str(tmp_path / "l")],
                         capture_output=True, text=True)
    assert run.returncode == 2 and "unknown store" in run.stderr
