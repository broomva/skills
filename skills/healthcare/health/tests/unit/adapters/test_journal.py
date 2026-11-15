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


def test_parse_value_keeps_answers_verbatim_and_only_scores_are_numbers() -> None:
    assert parse_value("spirit", "Yes") == "Yes"
    assert parse_value("note", "No") == "No"
    assert parse_value("note", "007") == "007"
    assert parse_value("body_score", "8") == 8
    assert parse_value("body_score", "2.5") == 2.5
    assert parse_value("safety_stop", "yes") is True
    for bad in ("nan", "inf", "-inf", "eight"):
        with pytest.raises(ValueError):
            parse_value("mind_score", bad)
    with pytest.raises(ValueError):
        parse_value("safety_stop", "no")


def test_lock_file_is_owner_only(tmp_path: Path) -> None:
    j = JsonlJournal(tmp_path / "journal.jsonl")
    j.record("2026-01-15", {"a": "1"})
    assert stat.S_IMODE((tmp_path / "journal.lock").stat().st_mode) == 0o600


def test_a_symlinked_journal_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real.jsonl"
    real.write_text("")
    link = tmp_path / "journal.jsonl"
    link.symlink_to(real)
    with pytest.raises(ValueError):
        JsonlJournal(link).record("2026-01-15", {"a": "1"})


def test_bad_dates_and_bad_bytes_are_kept_not_trusted(tmp_path: Path) -> None:
    p = tmp_path / "journal.jsonl"
    p.write_bytes(b'{"date": "~x", "a": 1}\n\xff\xfe broken\n{"date": "2026-01-15", "b": 2}\n')
    j = JsonlJournal(p)
    j.record("2026-01-16", {"c": "3"})
    raw = p.read_bytes().splitlines()
    assert raw[0] == b'{"date": "~x", "a": 1}'
    assert raw[1] == b"\xff\xfe broken"
    assert sorted(j.read()) == ["2026-01-15", "2026-01-16"]
    with pytest.raises(ValueError):
        j.record("2026-1-5", {"x": "1"})


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


def test_cli_checks_the_default_data_dir_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from broomva_health.cli.checkin import app

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("BROOMVA_HEALTH_DATA_DIR", str(repo / "health"))
    monkeypatch.delenv("BROOMVA_HEALTH_JOURNAL", raising=False)
    r = CliRunner().invoke(app, ["record", "a=1"])
    assert r.exit_code != 0
    assert not (repo / "health").exists()


def test_cli_validates_dates_days_and_scores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from broomva_health.cli.checkin import app

    monkeypatch.setenv("BROOMVA_HEALTH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("BROOMVA_HEALTH_JOURNAL", raising=False)
    runner = CliRunner()
    for args in (
        ["record", "a=1", "--date", "2026-13-01"],
        ["record", "a=1", "--date", "2026-W03-4"],
        ["record", "mind_score=nan"],
        ["show", "--days", "0"],
        ["show", "--days", "-1"],
    ):
        r = runner.invoke(app, args)
        assert r.exit_code == 2, (args, r.output)
    r = runner.invoke(app, ["record", "spirit=Yes", "note=No", "--date", "2026-01-15"])
    assert r.exit_code == 0, r.output
    entry = json.loads((tmp_path / "data" / "journal.jsonl").read_text())
    assert entry["spirit"] == "Yes"
    assert entry["note"] == "No"


def test_impossible_dates_are_refused_and_kept_not_trusted(tmp_path: Path) -> None:
    p = tmp_path / "journal.jsonl"
    p.write_text('{"date": "2026-02-30", "a": 1}\n{"date": "2026-01-01", "s": NaN}\n')
    j = JsonlJournal(p)
    with pytest.raises(ValueError):
        j.record("2026-02-30", {"a": "1"})
    j.record("2026-01-15", {"b": "2"})
    assert sorted(j.read()) == ["2026-01-15"]
    assert len(j.unparsed) == 2


def test_a_directory_is_not_a_journal(tmp_path: Path) -> None:
    from broomva_health.cli.checkin import app

    d = tmp_path / "private"
    (d / "journal.jsonl").mkdir(parents=True)
    os.chmod(d, 0o700)
    with pytest.raises(ValueError):
        JsonlJournal(d / "journal.jsonl").record("2026-01-15", {"a": "1"})
    r = CliRunner().invoke(app, ["record", "a=1", "--journal", str(d / "journal.jsonl")])
    assert r.exit_code == 2
    assert not (d / "journal.lock").exists()


def test_stderr_never_carries_journal_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from broomva_health.cli.checkin import app

    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    os.chmod(data, 0o700)
    (data / "journal.jsonl").write_text("secret words that do not parse\n")
    monkeypatch.setenv("BROOMVA_HEALTH_DATA_DIR", str(data))
    monkeypatch.delenv("BROOMVA_HEALTH_JOURNAL", raising=False)
    r = CliRunner().invoke(app, ["record", "a=1", "--date", "2026-01-15"])
    assert r.exit_code == 0, r.output
    assert "secret" not in r.output
    assert "kept 1 journal line" in r.output
