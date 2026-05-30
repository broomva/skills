"""`operate` CLI — the operator entry point.

Subcommands:
  tick       Run one tick (cron / /loop friendly). Exit 0 if the canary passed
             this tick, 1 otherwise — so a scheduler can alert on failure.
  run        Continuous daemon: tick every --interval seconds.
  status     Print the current operator state as JSON.
  positions  Print current net positions.
  reset      Clear a hard halt (operator-acknowledged recovery).

Wiring (P19 mechanism cube):
  - in-session, internal  : `/loop 60s operate tick`
  - across-session, cron   : `schedule` / CronCreate -> `operate tick`
  - across-session, external: `persist iterate` with `operate tick` in PROMPT.md
  - true daemon            : `operate run --interval 60` under launchd/systemd

The CLI constructs its own mock-mode Dispatcher + ledgers pointing at the same
DB paths as the bridge, so the canary exercises the real dispatch pipeline.
Paper-only / mock-default — identical safety envelope to the bridge.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ..dispatch import Dispatcher
from ..idempotency import IdempotencyStore, default_db_path
from ..logging_setup import configure_logging
from ..orders import OrderLedger, default_orders_db_path
from ..settings import assert_paper_only, get_settings
from .canary import CanaryProbe
from .loop import OperatorLoop
from .positions import PositionManager
from .state import OperatorState


def default_state_path() -> Path:
    """Operator state JSON, next to the bridge DBs by default."""
    import os

    override = os.environ.get("TVBRIDGE_OPERATOR_STATE_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".tradingview-bridge" / "operator-state.json"


def _build_loop(args: argparse.Namespace) -> tuple[OperatorLoop, OrderLedger, Path]:
    """Construct the operator loop + its dependencies, mock-mode + paper-only."""
    settings = get_settings()
    assert_paper_only(settings)  # never operate outside paper mode

    idem_path = Path(settings.db_path).expanduser() if settings.db_path else default_db_path()
    idempotency = IdempotencyStore(db_path=idem_path)
    order_ledger = OrderLedger(db_path=default_orders_db_path())

    dispatcher = Dispatcher(
        broker_mode=settings.broker_mode,
        idempotency_store=idempotency,
        order_ledger=order_ledger,
    )
    probe_url = getattr(args, "probe_url", None)
    canary = CanaryProbe(dispatcher, http_url=probe_url)
    positions = PositionManager(order_ledger)
    state_path = default_state_path()
    loop = OperatorLoop(
        canary=canary,
        positions=positions,
        state_path=state_path,
        medium_every=args.medium_every,
        slow_every=args.slow_every,
        max_open_positions=args.max_open_positions,
        halt_after_failures=args.halt_after_failures,
    )
    return loop, order_ledger, state_path


def _add_loop_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--medium-every", type=int, default=5, help="ticks between position checks")
    p.add_argument("--slow-every", type=int, default=1440, help="ticks between drift reports")
    p.add_argument("--max-open-positions", type=int, default=20, help="position-count cap")
    p.add_argument("--halt-after-failures", type=int, default=3, help="hard-halt threshold")
    p.add_argument(
        "--probe-url",
        type=str,
        default=None,
        help="bridge base URL for the HTTP /health canary check (e.g. http://127.0.0.1:8787)",
    )


async def _cmd_tick(args: argparse.Namespace) -> int:
    loop, _, _ = _build_loop(args)
    state = await loop.tick()
    print(json.dumps(state.to_dict(), indent=2))  # noqa: T201 — CLI output
    return 0 if state.last_canary_passed else 1


async def _cmd_run(args: argparse.Namespace) -> int:
    loop, _, _ = _build_loop(args)
    await loop.run_forever(interval_s=args.interval)
    return 0


async def _cmd_status(args: argparse.Namespace) -> int:
    state = OperatorState.load(default_state_path())
    print(json.dumps(state.to_dict(), indent=2))  # noqa: T201
    return 0


async def _cmd_positions(args: argparse.Namespace) -> int:
    order_ledger = OrderLedger(db_path=default_orders_db_path())
    positions = await order_ledger.net_positions()
    print(json.dumps({sym: str(qty) for sym, qty in positions.items()}, indent=2))  # noqa: T201
    return 0


async def _cmd_reset(args: argparse.Namespace) -> int:
    path = default_state_path()
    state = OperatorState.load(path)
    state.reset()
    state.save(path)
    print(json.dumps(state.to_dict(), indent=2))  # noqa: T201
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="operate",
        description="Autonomous operator for the tradingview-bridge (paper-only, mock-default).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_tick = sub.add_parser("tick", help="run one tick (cron/loop friendly)")
    _add_loop_args(p_tick)

    p_run = sub.add_parser("run", help="continuous daemon")
    _add_loop_args(p_run)
    p_run.add_argument("--interval", type=float, default=60.0, help="seconds between ticks")

    sub.add_parser("status", help="print operator state")
    sub.add_parser("positions", help="print net positions")
    sub.add_parser("reset", help="clear a hard halt")

    return parser


def main(argv: list[str] | None = None) -> int:
    # Logs -> stderr so stdout stays a clean JSON data channel (`operate tick | jq`).
    configure_logging(stream=sys.stderr)
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "tick": _cmd_tick,
        "run": _cmd_run,
        "status": _cmd_status,
        "positions": _cmd_positions,
        "reset": _cmd_reset,
    }
    handler = handlers[args.command]
    return asyncio.run(handler(args))


if __name__ == "__main__":
    sys.exit(main())
