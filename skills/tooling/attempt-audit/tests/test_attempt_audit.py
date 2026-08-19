"""Tests for attempt-audit.

The positive and dogfood tests assert the REASON -- which function, which guard,
which returned value. The negative tests assert an empty finding list, which is a
one-bit check; what gives those teeth is tests/mutation_proof.sh, where each arm
removes a behaviour and names the test that must go red.

An earlier version of this docstring claimed every assertion checked the reason.
Two lines below, `assert len(f) == 1` refuted it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
SCRIPT = HERE.parent / "scripts" / "attempt_audit.py"


def run(*args) -> tuple[int, dict]:
    p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args), "--json"],
                       capture_output=True, text=True)
    return p.returncode, json.loads(p.stdout)


def audit(name: str) -> list[dict]:
    return run(FIXTURES / name)[1]["findings"]


# --- true positive ---------------------------------------------------------

def test_flags_work_skipped_by_a_switch():
    f = audit("positive_skipped_work.py")
    assert len(f) == 1, f
    assert f[0]["function"] == "load_thing"
    assert f[0]["guard"] == "allow_extra", "must name the switch that was skipped"
    assert f[0]["returns"] == "('', [])"


# --- true negatives --------------------------------------------------------

def test_ignores_a_recorded_skip():
    assert audit("negative_records_skip.py") == [], "recording the skip makes it honest"


def test_ignores_a_validation_chain():
    """Every guard runs; nothing is skipped; None means all checks passed."""
    assert audit("negative_validation_chain.py") == []


def test_ignores_a_guard_on_the_subject_being_examined():
    """`isinstance(entry, dict)` narrows the DATA; nothing was skipped."""
    assert audit("negative_type_narrowing.py") == [], (
        "a name used inside the guard body is the subject, not a switch")


def test_ignores_a_call_that_lives_only_in_the_guard_test():
    """`if len(text) < 5: return True` -- the body does no work."""
    assert audit("negative_call_in_test_only.py") == [], (
        "work must be in the guard BODY, not merely in its test")


def test_ignores_a_guard_followed_by_an_alternative_path():
    """Work between the guard and the sentinel means something WAS attempted."""
    assert audit("negative_alternative_path.py") == [], (
        "the guard must be the last statement before the sentinel")


def test_ignores_a_search_loop():
    """Searched and not found is not the same as never searched."""
    assert audit("negative_search_loop.py") == []


# --- the self-referential requirement --------------------------------------

def test_unreadable_files_are_reported_not_silently_skipped(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text((FIXTURES / "broken_syntax.py.txt").read_text())
    code, out = run(tmp_path)
    assert out["unreadable"], "a file it could not parse must be named"
    assert "bad.py" in out["unreadable"][0]["file"]
    assert "SyntaxError" in out["unreadable"][0]["reason"]


def test_scanning_nothing_is_not_a_clean_result(tmp_path):
    (tmp_path / "notpython.txt").write_text("hello")
    code, out = run(tmp_path)
    assert out["scanned"] == 0
    assert code == 2, "exit 2 -- scanned nothing must not look like scanned-and-clean"


def test_clean_scan_exits_zero_and_is_distinct_from_scanning_nothing(tmp_path):
    (tmp_path / "ok.py").write_text("def f(x):\n    return x + 1\n")
    code, out = run(tmp_path)
    assert out["scanned"] == 1 and out["findings"] == []
    assert code == 0, "clean is exit 0; scanned-nothing is exit 2; they must differ"


def test_plain_output_says_a_clean_scan_is_not_a_guarantee(tmp_path):
    (tmp_path / "ok.py").write_text("def f(x):\n    return x + 1\n")
    p = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)],
                       capture_output=True, text=True)
    assert "not the same as every absence being evidenced" in p.stdout


# --- integration: the case that motivated the tool -------------------------

def test_dogfood_catches_the_reference_case():
    real = Path.home() / "broomva" / "scripts" / "video_ingest.py"
    if not real.exists():
        import pytest
        pytest.skip("video_ingest.py not present in this checkout")
    f = run(real)[1]["findings"]
    hits = [x for x in f if x["function"] == "load_transcript"]
    assert hits, "must flag load_transcript -- the defect this tool exists for"
    assert hits[0]["guard"] == "allow_whisper"


def test_an_incomplete_scan_never_exits_zero(tmp_path):
    """A directory it could not enter means exit 0 is unavailable."""
    (tmp_path / "ok.py").write_text("def f(x):\n    return x + 1\n")
    locked = tmp_path / "locked"
    (locked / "inner").mkdir(parents=True)
    (locked / "inner" / "d.py").write_text("def g(a, flag):\n    if flag:\n        r = w(a)\n        if r:\n            return r\n    return None\n")
    locked.chmod(0o000)
    try:
        code, out = run(tmp_path)
        assert out["walk_errors"], "an unreadable directory must be reported"
        assert code == 2, "an incomplete scan must not exit 0"
    finally:
        locked.chmod(0o755)


def test_unreadable_file_also_blocks_exit_zero(tmp_path):
    (tmp_path / "ok.py").write_text("def f(x):\n    return x + 1\n")
    (tmp_path / "bad.py").write_text((FIXTURES / "broken_syntax.py.txt").read_text())
    code, out = run(tmp_path)
    assert out["unreadable"] and code == 2, "a file it could not parse must block exit 0"
