"""Tests for run_mutants.py: the runner itself must not report a clean run it did not observe."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mutants  # noqa: E402


def outcomes(monkeypatch, baseline: str, mutant: str) -> list[str]:
    seen: list[str] = []

    def fake(mutant_pair):
        seen.append(mutant_pair[0])
        return mutant_pair[0], baseline if mutant_pair[0] == "the unchanged script" else mutant

    monkeypatch.setattr(run_mutants, "run_mutant", fake)
    return seen


def test_a_red_baseline_stops_the_run_before_any_mutant(monkeypatch, capsys):
    for red in ("killed", "TIMEOUT: the tests did not finish, so nothing was observed", "ERROR: x"):
        seen = outcomes(monkeypatch, baseline=red, mutant="killed")
        assert run_mutants.main(["strict"]) == 1
        assert seen == ["the unchanged script"]
        assert "BASELINE" in capsys.readouterr().out


def test_a_green_baseline_lets_the_mutants_run(monkeypatch, capsys):
    seen = outcomes(monkeypatch, baseline="SURVIVED", mutant="killed")
    assert run_mutants.main(["strict flag ignored"]) == 0
    assert seen[0] == "the unchanged script" and "strict flag ignored" in seen
    assert "mutants killed" in capsys.readouterr().out


def test_a_survivor_a_timeout_and_a_broken_mutant_each_fail_the_run(monkeypatch, capsys):
    for outcome in ("SURVIVED", "TIMEOUT: the tests did not finish, so nothing was observed", "BROKEN: x"):
        outcomes(monkeypatch, baseline="SURVIVED", mutant=outcome)
        assert run_mutants.main(["strict flag ignored"]) == 1, outcome
        assert outcome.split(":")[0] in capsys.readouterr().out


def test_every_hand_written_mutant_still_applies():
    mutants, problems = run_mutants.all_mutants()
    assert problems == []
    assert len(mutants) > len(run_mutants.CURATED) > 50
