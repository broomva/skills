"""Tests for the `optimize` CLI (cli.py). main() is sync (no asyncio) → safe to call."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingview_bridge.optimize.cli import build_parser, main

# Logs are routed to stderr by main()'s own _configure_logging(); the conftest
# _isolate_structlog_stream fixture resets structlog after each test so the
# capsys-bound stream never leaks. stdout therefore stays a clean --json channel.


def test_build_parser_routes_run_args() -> None:
    args = build_parser().parse_args(
        ["run", "--family", "donchian-breakout", "--symbol", "BTC", "--json"]
    )
    assert args.command == "run"
    assert args.family == "donchian-breakout"
    assert args.json is True


def test_train_frac_rejects_out_of_range() -> None:
    for bad in ["0", "1", "1.5", "-0.1"]:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["run", "--train-frac", bad])


def test_build_parser_routes_schedule_args() -> None:
    args = build_parser().parse_args(["schedule", "--budget", "8", "--symbol", "X"])
    assert args.command == "schedule"
    assert args.budget == 8


def test_main_schedule_table(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["schedule", "--budget", "8", "--symbol", "T", "--bars", "300"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "UCB1 schedule" in out
    assert "Allocation" in out
    assert "human-gated : True" in out
    assert "generalizes" in out


def test_main_schedule_json_is_human_gated(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["schedule", "--budget", "8", "--bars", "300", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requires_human_approval"] is True
    assert payload["n_evaluated"] == 8
    assert sum(a["pulls"] for a in payload["allocation"]) == 8
    assert "best" in payload
    assert "test_score" in payload


def test_unknown_family_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--family", "not-a-strategy"])


def test_main_run_table(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["run", "--family", "donchian-breakout", "--symbol", "T", "--bars", "300"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "EGRI optimize" in out
    assert "generalizes" in out
    assert "human-gated  : True" in out
    assert "TEST score" in out


def test_main_run_json_is_human_gated(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["run", "--family", "donchian-breakout", "--bars", "300", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requires_human_approval"] is True
    assert "test_score" in payload
    assert "generalization_gap" in payload
    assert payload["best"]["strategy"].startswith("donchian-breakout-")


def test_main_run_from_csv(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    csv_path = tmp_path / "bars.csv"
    closes = "\n".join(str(100 + (i % 9) - 4) for i in range(300))
    csv_path.write_text("close\n" + closes + "\n")
    rc = main(["run", "--family", "donchian-breakout", "--bars-csv", str(csv_path)])
    assert rc == 0
    assert "EGRI optimize" in capsys.readouterr().out
