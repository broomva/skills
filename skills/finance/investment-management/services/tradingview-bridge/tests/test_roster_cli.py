"""Tests for the `roster` CLI. Async handlers are called directly (not main, which
would asyncio.run → leak an event loop under pytest-asyncio)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tradingview_bridge.roster.cli import (
    _cmd_active,
    _cmd_list,
    _cmd_promote,
    _cmd_propose,
    _cmd_reject,
    _configure_logging,
    build_parser,
)


@pytest.fixture(autouse=True)
def _isolated_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Per-test roster DB + logs routed to stderr so stdout stays a clean channel."""
    monkeypatch.setenv("TVBRIDGE_ROSTER_DB_PATH", str(tmp_path / "roster.sqlite"))
    _configure_logging()


def _propose_ns(**kw: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "db": None,
        "family": "sma-crossover",
        "all": False,
        "symbol": "AAPL",
        "asset_class": "stock",
        "train_frac": 0.7,
        "n_windows": 4,
        "bars": 300,
        "bars_csv": None,
        "min_test": 0.5,
        "max_gap": 0.25,
    }
    base.update(kw)
    return argparse.Namespace(**base)


async def test_propose_promote_active_flow(capsys: pytest.CaptureFixture[str]) -> None:
    assert await _cmd_propose(_propose_ns()) == 0
    assert "PROPOSED as [1]" in capsys.readouterr().out

    assert await _cmd_list(argparse.Namespace(db=None, status="proposed")) == 0
    assert "proposed" in capsys.readouterr().out

    # before promotion, no active roster
    assert await _cmd_active(argparse.Namespace(db=None)) == 0
    assert "No active roster" in capsys.readouterr().out

    # the human gate
    assert await _cmd_promote(argparse.Namespace(db=None, id=1)) == 0
    assert "PROMOTED [1]" in capsys.readouterr().out

    # now active
    assert await _cmd_active(argparse.Namespace(db=None)) == 0
    out = capsys.readouterr().out
    assert "Active roster" in out
    assert "sma-crossover-5-20" in out


async def test_propose_all_families(capsys: pytest.CaptureFixture[str]) -> None:
    assert await _cmd_propose(_propose_ns(all=True)) == 0
    out = capsys.readouterr().out
    # every family is at least considered (proposed or not-generalize line)
    for family in ("sma-crossover", "rsi-mean-reversion", "donchian-breakout"):
        assert family in out


async def test_promote_missing_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    rc = await _cmd_promote(argparse.Namespace(db=None, id=999))
    assert rc == 1
    assert "cannot promote" in capsys.readouterr().out


async def test_reject_flow(capsys: pytest.CaptureFixture[str]) -> None:
    await _cmd_propose(_propose_ns())
    capsys.readouterr()
    assert await _cmd_reject(argparse.Namespace(db=None, id=1, note="nope")) == 0
    assert "REJECTED [1]" in capsys.readouterr().out


def test_build_parser_propose() -> None:
    args = build_parser().parse_args(["propose", "--family", "donchian-breakout"])
    assert args.command == "propose"
    assert args.family == "donchian-breakout"


def test_build_parser_promote_takes_int_id() -> None:
    args = build_parser().parse_args(["promote", "5"])
    assert args.id == 5


def test_build_parser_train_frac_validated() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["propose", "--train-frac", "1.5"])
