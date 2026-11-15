"""Regressions for the final round (findings at 9e92a07)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from test_reader_contract import _codex_sid, iso, turn, write_jsonl  # noqa: E402

from yia.ledger import make_row  # noqa: E402
from yia.ledger import sources as S  # noqa: E402
from yia.ledger import store as L  # noqa: E402

T0 = 1793000000.0


def _codex_rollout(root, turns, compress):
    name = f"rollout-x-{_codex_sid('s1')}.jsonl"
    lines = [{"type": "session_meta", "timestamp": iso(T0 - 60),
              "payload": {"originator": "Codex Desktop", "source": "vscode"}}]
    for t in turns:
        lines.append({"type": "event_msg", "timestamp": iso(t["ts"]),
                      "payload": {"type": "user_message", "message": t["prompt"]}})
    path = root / "2026" / "10" / name
    write_jsonl(path, lines)
    if compress:
        subprocess.run([shutil.which("zstd") or S.find_zstd(), "-q", "--rm", str(path)], check=True)
    return path


@pytest.mark.skipif(not S.find_zstd(), reason="zstd not installed")
def test_a_missing_zstd_is_reported_never_silent(tmp_path, monkeypatch):
    root = tmp_path / "codex"
    _codex_rollout(root, [turn(1), turn(2)], compress=True)
    monkeypatch.setattr(S, "find_zstd", lambda: None)
    report, rows = S.read_codex_sessions([root], None)
    assert list(rows) == []
    assert report.skipped == 1 and "zstd not found" in report.reason


@pytest.mark.skipif(not S.find_zstd(), reason="zstd not installed")
def test_harvest_exits_non_zero_when_transcripts_were_skipped(tmp_path):
    root = tmp_path / "codex"
    _codex_rollout(root, [turn(1)], compress=True)
    env = dict(os.environ, HOME=str(tmp_path / "home"), PATH="/nonexistent")
    # Hide zstd entirely: an empty PATH and no standard locations.
    code = ("import sys; sys.path.insert(0, %r); from yia.ledger import sources as S; "
            "S.ZSTD_LOCATIONS = (); import year_in_ai; "
            "sys.exit(year_in_ai.main(sys.argv[1:]))" % str(SCRIPTS))
    run = subprocess.run([sys.executable, "-c", code, "harvest", "--backfill", "--no-defaults",
                          "--root", f"codex_sessions={root}", "--ledger", str(tmp_path / "ledger")],
                         capture_output=True, text=True, env=env, cwd=str(SCRIPTS))
    assert run.returncode == 4, run.stderr
    assert "zstd" in run.stderr and "incomplete" in run.stderr


def test_zstd_is_found_off_path(tmp_path, monkeypatch):
    fake = tmp_path / "bin" / "zstd"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(S.shutil, "which", lambda name: None)
    monkeypatch.setattr(S, "ZSTD_LOCATIONS", (str(tmp_path / "missing"), str(fake)))
    assert S.find_zstd() == str(fake)


@pytest.mark.parametrize("bad_ts", [1e20, float("nan"), float("inf"), -5.0])
def test_out_of_range_timestamps_are_malformed_rows(tmp_path, bad_ts):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    good = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="valid", session="s", author="human",
                    occurrence="m")
    ledger.write([good])
    broken = dict(good, id="z" * 20, o="w" * 16, ts=bad_ts)
    with ledger._month_file(T0).open("a") as handle:
        handle.write(json.dumps(broken) + "\n")
    rows = list(ledger.rows())
    assert [r["id"] for r in rows] == [good["id"]] and ledger.malformed_lines == 1
