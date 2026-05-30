"""CLI tests — argparse wiring + paper-only guard + tick exit codes.

The command behaviour tests ``await`` the async ``_cmd_*`` handlers directly,
under pytest-asyncio's managed event loop. We deliberately avoid calling
``cli.main()`` (which spawns a fresh ``asyncio.run()`` per call) — repeated
``asyncio.run()`` in one test process leaks a macOS child-watcher socket that
trips the global ``filterwarnings = ["error"]``. In production the operator runs
exactly one ``asyncio.run`` per process (daemon, or one fresh process per cron
``operate tick``), so the pattern under test here is the real one.

DB + state paths are redirected into tmp dirs via env vars so nothing touches
the developer's home.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_bridge.operator import cli


@pytest.fixture
def operator_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Paper + mock, with all bridge/operator paths redirected into tmp."""
    monkeypatch.setenv("TVBRIDGE_TRADING_MODE", "paper")
    monkeypatch.setenv("TVBRIDGE_TV_WEBHOOK_SECRET", "cli-test-secret")
    monkeypatch.setenv("TVBRIDGE_BROKER_MODE", "mock")
    monkeypatch.setenv("TVBRIDGE_DB_PATH", str(tmp_path / "idem.sqlite"))
    monkeypatch.setenv("TVBRIDGE_ORDERS_DB_PATH", str(tmp_path / "orders.sqlite"))
    monkeypatch.setenv("TVBRIDGE_OPERATOR_STATE_PATH", str(tmp_path / "state.json"))


def _args(*argv: str) -> object:
    """Parse argv into the Namespace the handlers expect."""
    return cli.build_parser().parse_args(list(argv))


# ---- sync parser tests (no event loop) ----------------------------------


def test_parser_requires_subcommand() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_accepts_tick() -> None:
    args = _args("tick")
    assert args.command == "tick"
    assert args.medium_every == 5  # default


def test_parser_run_has_interval() -> None:
    args = _args("run", "--interval", "30")
    assert args.command == "run"
    assert args.interval == 30.0


# ---- async handler tests (pytest-asyncio managed loop) ------------------


@pytest.mark.asyncio
async def test_tick_exit_code_zero_on_pass(
    operator_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """A passing canary tick returns 0 (mock mode always dispatches accepted)."""
    rc = await cli._cmd_tick(_args("tick"))
    assert rc == 0
    assert '"last_canary_passed": true' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_status_after_tick(operator_env: None, capsys: pytest.CaptureFixture[str]) -> None:
    await cli._cmd_tick(_args("tick"))
    capsys.readouterr()  # drain
    rc = await cli._cmd_status(_args("status"))
    assert rc == 0
    assert '"tick_count": 1' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_positions_empty_initially(
    operator_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = await cli._cmd_positions(_args("positions"))
    assert rc == 0
    assert capsys.readouterr().out.strip() == "{}"


@pytest.mark.asyncio
async def test_reset_clears_state(operator_env: None, capsys: pytest.CaptureFixture[str]) -> None:
    await cli._cmd_tick(_args("tick"))
    capsys.readouterr()
    rc = await cli._cmd_reset(_args("reset"))
    assert rc == 0
    assert '"hard_halted": false' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_handler_refuses_live_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The operator must never run outside paper mode."""
    monkeypatch.setenv("TVBRIDGE_TRADING_MODE", "live")
    monkeypatch.setenv("TVBRIDGE_TV_WEBHOOK_SECRET", "x")
    monkeypatch.setenv("TVBRIDGE_OPERATOR_STATE_PATH", str(tmp_path / "state.json"))
    with pytest.raises(SystemExit):
        await cli._cmd_tick(_args("tick"))
