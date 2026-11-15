"""The check-in journal's storage contract (BRO-3751): merge per date, lock, atomic, owner-only."""

from __future__ import annotations

import fcntl
import json
import multiprocessing as mp
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from broomva_health.adapters.repositories import journal as journal_mod
from broomva_health.adapters.repositories.journal import (
    JournalLockTimeout,
    JsonlJournal,
    parse_value,
    private_dir_problems,
)


def _lines(p: Path) -> list[str]:
    return p.read_text().splitlines()


def test_first_record_creates_an_owner_only_file_and_dir(tmp_path: Path) -> None:
    j = JsonlJournal(tmp_path / "data" / "journal.jsonl")
    j.record("2026-01-15", {"body": "Okay", "body_score": 5})
    assert stat.S_IMODE(j.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(j.path.parent.stat().st_mode) == 0o700
    assert [json.loads(line) for line in _lines(j.path)] == [
        {"body": "Okay", "body_score": 5, "date": "2026-01-15"}
    ]


def test_a_later_record_merges_and_never_erases_earlier_answers(tmp_path: Path) -> None:
    j = JsonlJournal(tmp_path / "journal.jsonl")
    j.record("2026-01-15", {"body": "Okay", "mind": "Calm"})
    j.record("2026-01-15", {"mind": "Low or flat", "note": "late"})
    assert j.read()["2026-01-15"] == {
        "body": "Okay",
        "mind": "Low or flat",
        "note": "late",
        "date": "2026-01-15",
    }
    assert len(_lines(j.path)) == 1


def test_dates_are_one_line_each_sorted(tmp_path: Path) -> None:
    j = JsonlJournal(tmp_path / "journal.jsonl")
    for d in ("2026-01-17", "2026-01-15", "2026-01-16"):
        j.record(d, {"x": d})
    assert [json.loads(line)["date"] for line in _lines(j.path)] == [
        "2026-01-15",
        "2026-01-16",
        "2026-01-17",
    ]


def test_an_unparsable_line_is_kept_verbatim_in_place(tmp_path: Path) -> None:
    p = tmp_path / "journal.jsonl"
    p.write_text(
        '{"date": "2026-01-15", "a": 1}\nnot json at all\n{"date": "2026-01-17", "c": 3}\n'
    )
    j = JsonlJournal(p)
    j.record("2026-01-16", {"b": 2})
    assert j.unparsed == ["not json at all"]
    assert _lines(p)[1] == "not json at all"
    assert sorted(j.read()) == ["2026-01-15", "2026-01-16", "2026-01-17"]


def _writer(path: str, key: str) -> None:
    JsonlJournal(Path(path), lock_timeout_s=30).record("2026-01-15", {key: 1})


def test_concurrent_writers_lose_nothing(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_writer, args=(str(path), f"k{i}")) for i in range(8)]
    for pr in procs:
        pr.start()
    for pr in procs:
        pr.join(60)
    assert all(pr.exitcode == 0 for pr in procs)
    lines = _lines(path)
    assert len(lines) == 1
    assert {f"k{i}" for i in range(8)} <= set(json.loads(lines[0]))


def test_a_held_lock_times_out_and_writes_nothing(tmp_path: Path) -> None:
    j = JsonlJournal(tmp_path / "journal.jsonl", lock_timeout_s=0.2)
    j.record("2026-01-15", {"a": 1})
    before = j.path.read_bytes()
    with open(tmp_path / "journal.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        with pytest.raises(JournalLockTimeout):
            j.record("2026-01-15", {"b": 2})
    assert j.path.read_bytes() == before


def test_a_failed_replace_leaves_the_journal_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    j = JsonlJournal(tmp_path / "journal.jsonl")
    j.record("2026-01-15", {"a": 1})
    before = j.path.read_bytes()

    def boom(*_a: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(journal_mod.os, "replace", boom)
    with pytest.raises(OSError):
        j.record("2026-01-15", {"b": 2})
    assert j.path.read_bytes() == before
    assert not list(tmp_path.glob(".journal-*"))


def test_private_dir_problems(tmp_path: Path) -> None:
    ok = tmp_path / "ok"
    ok.mkdir(mode=0o700)
    os.chmod(ok, 0o700)
    assert private_dir_problems(ok) == []
    loose = tmp_path / "loose"
    loose.mkdir()
    os.chmod(loose, 0o755)
    assert any("readable by other users" in p for p in private_dir_problems(loose))
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "notes").mkdir()
    os.chmod(repo / "notes", 0o700)
    assert any("git work tree" in p for p in private_dir_problems(repo / "notes"))
    cloud = tmp_path / "Library" / "Mobile Documents" / "x"
    cloud.mkdir(parents=True)
    os.chmod(cloud, 0o700)
    assert any("cloud-synced" in p for p in private_dir_problems(cloud))


def test_parse_value() -> None:
    assert parse_value("8") == 8
    assert parse_value("2.5") == 2.5
    assert parse_value("yes") is True
    assert parse_value("No") is False
    assert parse_value("Calm, clear") == "Calm, clear"


def test_cli_record_and_show_use_the_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from broomva_health.cli.checkin import app

    monkeypatch.setenv("BROOMVA_HEALTH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("BROOMVA_HEALTH_JOURNAL", raising=False)
    runner = CliRunner()
    r = runner.invoke(app, ["record", "body=Okay", "body_score=5", "--date", "2026-01-15"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["record", "note=late walk", "--date", "2026-01-15"])
    assert r.exit_code == 0, r.output
    entry = json.loads((tmp_path / "data" / "journal.jsonl").read_text())
    assert entry["body_score"] == 5
    assert entry["note"] == "late walk"
    r = runner.invoke(app, ["show", "--days", "3"])
    assert json.loads(r.output.strip())["body"] == "Okay"


def test_cli_refuses_an_unsafe_journal_location(tmp_path: Path) -> None:
    from broomva_health.cli.checkin import app

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    r = CliRunner().invoke(app, ["record", "a=1", "--journal", str(repo / "journal.jsonl")])
    assert r.exit_code != 0
    assert not (repo / "journal.jsonl").exists()


def test_cli_rejects_reserved_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from broomva_health.cli.checkin import app

    monkeypatch.setenv("BROOMVA_HEALTH_DATA_DIR", str(tmp_path / "data"))
    r = CliRunner().invoke(app, ["record", "date=2026-01-01"])
    assert r.exit_code != 0
