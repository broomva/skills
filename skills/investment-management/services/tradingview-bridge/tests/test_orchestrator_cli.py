"""Tests for the `research` CLI (cli.py) — bars I/O, handlers, end-to-end main."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

import pytest

from tradingview_bridge.orchestrator.cli import (
    _cmd_leaderboard,
    _cmd_run,
    _configure_logging,
    bars_from_csv,
    build_parser,
    default_roster,
    synthetic_bars,
)


@pytest.fixture(autouse=True)
def _logs_to_stderr() -> None:
    """Route logs to stderr so stdout stays a clean data channel — exactly what
    main() does at startup. Calling _cmd_run directly bypasses main(), so without
    this the runner's structlog line would land on stdout and corrupt --json."""
    _configure_logging()


def test_synthetic_bars_deterministic_and_sized() -> None:
    a = synthetic_bars(60)
    b = synthetic_bars(60)
    assert len(a) == 60
    assert [bar.close for bar in a] == [bar.close for bar in b]  # reproducible, no RNG


def test_default_roster_is_three_named_strategies() -> None:
    names = [s.name for s in default_roster()]
    assert names == ["sma-crossover-5-20", "rsi-mean-reversion-14", "donchian-breakout-20"]


def test_bars_from_csv_reads_close(tmp_path: Path) -> None:
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text("close\n100\n101.5\n99.25\n")
    bars = bars_from_csv(csv_path)
    assert len(bars) == 3
    assert [b.close for b in bars] == [Decimal("100"), Decimal("101.5"), Decimal("99.25")]
    # open/high/low default to close when columns are absent
    assert bars[0].open == bars[0].high == bars[0].low == bars[0].close


def test_bars_from_csv_uses_ohlc_when_present(tmp_path: Path) -> None:
    csv_path = tmp_path / "ohlc.csv"
    csv_path.write_text("open,high,low,close\n99,102,98,101\n")
    bars = bars_from_csv(csv_path)
    assert bars[0].open == Decimal("99")
    assert bars[0].high == Decimal("102")
    assert bars[0].low == Decimal("98")
    assert bars[0].close == Decimal("101")


def test_bars_from_csv_empty_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("close\n")  # header only, no rows
    with pytest.raises(ValueError, match="no rows"):
        bars_from_csv(csv_path)


def _run_ns(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "symbol": "TEST",
        "asset_class": "stock",
        "n_windows": 4,
        "trust": 0.6,
        "bars_csv": None,
        "no_record": True,
        "json": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


async def test_cmd_run_table_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TVBRIDGE_PERFORMANCE_DB_PATH", str(tmp_path / "perf.sqlite"))
    rc = await _cmd_run(_run_ns())
    assert rc == 0
    out = capsys.readouterr().out
    assert "Leaderboard" in out
    assert "Recommendation:" in out
    assert "human-gated : True" in out


async def test_cmd_run_json_output_is_human_gated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TVBRIDGE_PERFORMANCE_DB_PATH", str(tmp_path / "perf.sqlite"))
    rc = await _cmd_run(_run_ns(json=True))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["recommendation"]["requires_human_approval"] is True
    assert len(payload["leaderboard"]) == 3
    assert payload["leaderboard"][0]["rank"] == 1


async def test_cmd_run_from_csv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TVBRIDGE_PERFORMANCE_DB_PATH", str(tmp_path / "perf.sqlite"))
    csv_path = tmp_path / "bars.csv"
    closes = "\n".join(str(100 + (i % 7) - 3) for i in range(120))
    csv_path.write_text("close\n" + closes + "\n")
    rc = await _cmd_run(_run_ns(bars_csv=str(csv_path)))
    assert rc == 0
    assert "Leaderboard" in capsys.readouterr().out


async def test_cmd_leaderboard_after_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TVBRIDGE_PERFORMANCE_DB_PATH", str(tmp_path / "perf.sqlite"))
    await _cmd_run(_run_ns(no_record=False))  # record so the ledger has rows
    capsys.readouterr()  # drain
    rc = await _cmd_leaderboard(argparse.Namespace(symbol="TEST", limit=20))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Recorded evaluations" in out
    assert "walk_forward" in out


def test_build_parser_routes_run_args() -> None:
    args = build_parser().parse_args(["run", "--symbol", "MSFT", "--trust", "0.7", "--json"])
    assert args.command == "run"
    assert args.symbol == "MSFT"
    assert args.trust == 0.7
    assert args.json is True


def test_trust_arg_rejects_out_of_range() -> None:
    parser = build_parser()
    for bad in ["5", "-0.1", "1.5"]:
        with pytest.raises(SystemExit):  # argparse converts ArgumentTypeError → SystemExit(2)
            parser.parse_args(["run", "--trust", bad])


def test_trust_arg_accepts_in_range() -> None:
    args = build_parser().parse_args(["run", "--trust", "0.8"])
    assert args.trust == 0.8


def test_build_parser_routes_leaderboard_args() -> None:
    args = build_parser().parse_args(["leaderboard", "--symbol", "BTC", "--limit", "5"])
    assert args.command == "leaderboard"
    assert args.symbol == "BTC"
    assert args.limit == 5


def test_configure_logging_falls_back_without_trading_settings() -> None:
    """The conftest purges TVBRIDGE_* env, so the bridge settings are absent —
    _configure_logging must fall back to minimal stderr logging, not crash (the
    research tool never trades, so it must not require trading secrets)."""
    _configure_logging()  # raises if the fallback path is broken
