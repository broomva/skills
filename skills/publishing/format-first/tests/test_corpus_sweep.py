"""Tests for corpus_sweep.

The sweep exists to make a false-positive claim reproducible, so its own counting must be
provably right: a sweep that under-reports would certify a noisy widening as clean.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import corpus_sweep as cs  # noqa: E402
import format_lint as fl  # noqa: E402

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "corpus_sweep.py"
LEDGER = fl.load_ledger()

CLEAN = "Ranking is a weighted sum of predicted engagement probabilities.\n"
DIRTY = "Mosseri said the polished, perfect aesthetic is dead.\n"


def _tree(tmp_path, files):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return tmp_path


def test_walk_recurses_and_honours_the_extension(tmp_path):
    _tree(tmp_path, {"a.md": CLEAN, "nested/b.md": CLEAN, "c.txt": DIRTY})
    got = {p.name for p in cs.walk([str(tmp_path)], ".md")}
    assert got == {"a.md", "b.md"}


def test_walk_accepts_an_explicit_file_not_only_a_dir(tmp_path):
    _tree(tmp_path, {"a.md": CLEAN})
    assert [p.name for p in cs.walk([str(tmp_path / "a.md")], ".md")] == ["a.md"]


def test_scan_counts_each_distinct_finding_once(tmp_path):
    _tree(tmp_path, {"a.md": DIRTY, "b.md": DIRTY})
    keys, crashes = cs.scan(cs.walk([str(tmp_path)], ".md"), LEDGER)
    assert crashes == 0
    assert len(keys) == 2, "the same claim in two files is two findings"
    assert {k[2] for k in keys} == {"polished-aesthetic-dead"}


def test_scan_reports_a_crash_instead_of_silently_dropping_the_file(tmp_path, monkeypatch):
    """A swallowed exception would let a broken linter report a clean corpus."""
    _tree(tmp_path, {"a.md": CLEAN})

    def boom(*_a, **_k):
        raise RuntimeError("lint exploded")

    monkeypatch.setattr(cs.fl, "lint_text", boom)
    keys, crashes = cs.scan(cs.walk([str(tmp_path)], ".md"), LEDGER)
    assert (len(keys), crashes) == (0, 1)


def test_compare_reports_added_and_removed_against_a_second_ledger(tmp_path):
    _tree(tmp_path, {"a.md": DIRTY})
    narrowed = json.loads(json.dumps(LEDGER))
    narrowed["refuted"] = [r for r in narrowed["refuted"] if r["id"] != "polished-aesthetic-dead"]
    old = tmp_path / "old.json"
    old.write_text(json.dumps(narrowed))

    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path), "--compare", str(old), "--json"],
        capture_output=True, text=True, check=True,
    )
    rep = json.loads(out.stdout)
    assert rep["crashes"] == 0
    assert [r["id"] for r in rep["added"]] == ["polished-aesthetic-dead"]
    assert rep["removed"] == []


def test_compare_is_symmetric_removed_is_populated_when_a_rule_is_lost(tmp_path):
    """Removed must not be dead code — a widening that LOSES coverage has to show up."""
    _tree(tmp_path, {"a.md": DIRTY})
    narrowed = json.loads(json.dumps(LEDGER))
    narrowed["refuted"] = [r for r in narrowed["refuted"] if r["id"] != "polished-aesthetic-dead"]
    cur = tmp_path / "narrow.json"
    cur.write_text(json.dumps(narrowed))

    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path), "--ledger", str(cur),
         "--compare", str(fl.LEDGER), "--json"],
        capture_output=True, text=True, check=True,
    )
    rep = json.loads(out.stdout)
    assert rep["added"] == []
    assert [r["id"] for r in rep["removed"]] == ["polished-aesthetic-dead"]


def test_an_empty_corpus_is_an_error_not_a_clean_report(tmp_path):
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True
    )
    assert out.returncode == 2
    assert "no *.md" in out.stderr


def test_an_uncompilable_pattern_is_rejected_at_load_not_swallowed_per_file(tmp_path):
    """A broken rule must be an error, not "this ledger found nothing"."""
    broken = json.loads(json.dumps(LEDGER))
    broken["refuted"][0]["pattern"] = "("
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken))
    with pytest.raises(SystemExit) as exc:
        fl.load_ledger(path)
    assert "invalid pattern" in str(exc.value)


def test_compare_against_a_crashing_old_ledger_fails_loudly(tmp_path):
    """The reviewer's case: if every old scan crashes, the old set is empty and every
    current finding reads as newly ADDED — a widening certifying itself as pure gain."""
    _tree(tmp_path, {"a.md": DIRTY})
    old = tmp_path / "old.json"
    old.write_text(json.dumps(LEDGER).replace('"refuted": [', '"refuted": ['))

    # Force old-side crashes without tripping load_ledger's compile check, by breaking the
    # pattern only after load — the path a caller could still hit.
    import corpus_sweep as cs_mod

    real_scan = cs_mod.scan
    calls = {"n": 0}

    def flaky(files, ledger):
        calls["n"] += 1
        if calls["n"] == 2:      # the comparison ledger's pass
            return set(), len(files)
        return real_scan(files, ledger)

    cs_mod.scan = flaky
    try:
        rc = cs_mod.main([str(tmp_path), "--compare", str(old), "--json"])
    finally:
        cs_mod.scan = real_scan
    assert rc == 1, "a crashing comparison side must not exit 0"


def test_a_clean_compare_still_exits_zero(tmp_path):
    _tree(tmp_path, {"a.md": DIRTY})
    old = tmp_path / "old.json"
    old.write_text(json.dumps(LEDGER))
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path), "--compare", str(old), "--json"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    rep = json.loads(out.stdout)
    assert rep["old_crashes"] == 0 and rep["crashes"] == 0


def test_current_side_crashes_also_fail(tmp_path, monkeypatch):
    _tree(tmp_path, {"a.md": CLEAN})

    def boom(*_a, **_k):
        raise RuntimeError("lint exploded")

    monkeypatch.setattr(cs.fl, "lint_text", boom)
    assert cs.main([str(tmp_path), "--json"]) == 1
