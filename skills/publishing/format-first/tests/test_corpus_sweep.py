"""Tests for corpus_sweep.

The sweep exists to make a false-positive claim reproducible, so its own counting must be
provably right: a sweep that under-reports would certify a noisy widening as clean.
"""
import json
import subprocess
import sys
from pathlib import Path

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
