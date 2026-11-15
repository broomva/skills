"""Regressions for the CodeRabbit review of PR #290 (findings still valid at e976a6d)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from yia.ledger import archive as A  # noqa: E402
from yia.ledger import store as L  # noqa: E402
from yia.model import Window  # noqa: E402
from yia.readers import _common  # noqa: E402
from yia.redact import redact  # noqa: E402

TERM = "acmesecretclient"


def test_archive_refuses_a_target_inside_its_source(tmp_path):
    source = tmp_path / "projects"
    (source / "p").mkdir(parents=True)
    (source / "p" / "a.jsonl").write_text("{}\n")
    with pytest.raises(ValueError):
        A.archive(source, targets=[(str(source), "claude-projects")])  # root/claude-projects is inside the source
    assert not (source / "claude-projects").exists()


def test_archive_refuses_a_target_that_contains_its_source(tmp_path):
    root = tmp_path / "archive"
    source = root / "claude-projects" / "live"
    source.mkdir(parents=True)
    with pytest.raises(ValueError):
        A.archive(root, targets=[(str(source), "claude-projects")])


def test_every_configured_history_file_is_read(tmp_path):
    files = []
    for i in range(2):
        path = tmp_path / f"history-{i}.jsonl"
        path.write_text(json.dumps({"display": f"prompt number {i}", "timestamp": 1793000000000 + i,
                                    "project": "/p", "sessionId": f"s{i}"}) + "\n")
        files.append(path)
    roots = {k: [] for k in L.DEFAULT_ROOTS}
    roots["claude_history"] = files
    ledger = L.Ledger(str(tmp_path / "ledger"))
    entry = L.harvest(ledger, roots, since=None)
    assert sum(entry["added"].values()) == 2
    assert len([s for s in entry["sources"] if s["source"] == "claude_history" and s["available"]]) == 2


def test_share_safe_output_relabels_note_titles_and_hides_the_terms():
    payload = {"outcomes": {"memory": {"most_linked": [
        {"slug": f"{TERM}-deal", "inbound": 4, "title": f"Notes on {TERM} renewal"},
        {"slug": "public-note", "inbound": 2, "title": "A public note"},
    ]}}}
    out = redact(payload, extra_terms=[TERM])
    text = json.dumps(out).lower()
    assert TERM not in text
    assert out["redaction"]["extra_terms_count"] == 1
    # Titles are free text: every one is replaced, keyword or not, and counts survive.
    assert [r["title"] for r in out["outcomes"]["memory"]["most_linked"]] == ["note 1", "note 2"]
    assert [r["inbound"] for r in out["outcomes"]["memory"]["most_linked"]] == [4, 2]


def test_timestamp_prefilter_accepts_spaced_json(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text('{"type": "user", "timestamp": "2026-06-01T12:00:00Z"}\n'
                    '{"type":"user","timestamp":"2026-06-01T12:05:00Z"}\n')
    records = list(_common.iter_records(path, Window()))
    assert len(records) == 2
