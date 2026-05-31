"""`research` CLI — the autoresearch orchestrator entry point.

Subcommands:
  run          Evaluate the strategy roster over bars → leaderboard + recommendation.
  leaderboard  Print the recorded evaluation history for a symbol (newest first).

Bars: ``--bars-csv FILE`` (a CSV with at least a ``close`` column) or, by
default, a deterministic synthetic multi-regime series so the loop is runnable
out of the box. Live market-data integration (`market_data.py`) is deferred —
the orchestration logic is independent of where bars come from.

Safety: this command only *measures and recommends*. The recommendation is
always human-gated; nothing here places an order or allocates capital. Logs go
to stderr so stdout stays a clean data channel (`research run --json | jq`).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import structlog
from pydantic import ValidationError

# bars_from_csv / synthetic_bars are re-exported here (imported from the shared
# barsource module) so existing `from orchestrator.cli import synthetic_bars`
# call sites keep working after the extraction.
from ..barsource import bars_from_csv, synthetic_bars
from ..evaluation.ledger import PerformanceLedger
from ..logging_setup import configure_logging
from ..roster.promotion import active_roster
from ..roster.store import RosterStore
from ..strategy.base import Strategy
from ..strategy.library import DonchianBreakout, RSIMeanReversion, SMACrossover
from .runner import AutoResearch, ResearchReport

__all__ = ["bars_from_csv", "build_parser", "default_roster", "main", "synthetic_bars"]


def default_roster() -> list[Strategy]:
    """The built-in strategies to evaluate (one per Pine template family)."""
    return [SMACrossover(5, 20), RSIMeanReversion(14), DonchianBreakout(20)]


def _trust_arg(value: str) -> float:
    """Parse --trust and enforce the [0, 1] range. Fail loud rather than clamp:
    --trust governs the promote/reject gate, so silently coercing a bad value
    (e.g. 5 → everything rejected, -1 → everything promoted) would mask intent."""
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(f"--trust must be in [0, 1], got {parsed}")
    return parsed


def _format_report(report: ResearchReport) -> str:
    board = report.leaderboard
    n_strat = len(board.ranked)
    lines = [
        f"Leaderboard {board.symbol} — {n_strat} strategies, {report.n_recorded} recorded",
        f"{'#':<3}{'strategy':<24}{'score':>7}{'consist':>9}{'sharpe':>8}{'mret%':>9}{'wDD%':>8}",
        "-" * 68,
    ]
    for r in board.ranked:
        wf = r.evaluation.walk_forward
        lines.append(
            f"{r.rank:<3}{r.evaluation.strategy:<24}{r.evaluation.score.overall:>7.3f}"
            f"{float(wf.consistency_pct):>7.0f}% {wf.mean_sharpe:>7.2f}"
            f"{float(wf.mean_return_pct):>9.2f}{float(wf.worst_window_drawdown_pct):>8.2f}"
        )
    rec = report.recommendation
    lines += [
        "",
        f"Recommendation: {rec.action.upper()}",
        f"  strategy    : {rec.strategy}",
        f"  confidence  : {rec.confidence:.3f}  (trust gate {rec.trust_threshold:.2f})",
        f"  human-gated : {rec.requires_human_approval}  (live capital is always a human decision)",
        f"  rationale   : {rec.rationale}",
    ]
    if rec.live_reality is not None:
        g = rec.live_reality
        lines.append(
            f"  live-reality: sim({g.sim_kind}) {g.sim_return_pct}% vs live {g.live_return_pct}% "
            f"→ gap {g.return_gap_pct}%"
        )
    return "\n".join(lines)


async def _resolve_roster(args: argparse.Namespace) -> list[Strategy]:
    """The strategies the orchestrator evaluates. With --roster-db, use the
    human-promoted active roster (falling back to the built-in defaults when none
    is active); otherwise the built-in defaults."""
    if not args.roster_db:
        return default_roster()
    store = RosterStore(db_path=Path(args.roster_db).expanduser())
    entries = await store.active_entries()
    return active_roster(entries, fallback=default_roster())


async def _cmd_run(args: argparse.Namespace) -> int:
    bars = bars_from_csv(Path(args.bars_csv).expanduser()) if args.bars_csv else synthetic_bars()
    orchestrator = AutoResearch()
    report = await orchestrator.run(
        await _resolve_roster(args),
        bars,
        symbol=args.symbol,
        asset_class=args.asset_class,
        n_windows=args.n_windows,
        trust_threshold=args.trust,
        record=not args.no_record,
    )
    if args.json:
        rec = report.recommendation
        payload = {
            "symbol": report.symbol,
            "n_recorded": report.n_recorded,
            "leaderboard": [
                {
                    "rank": r.rank,
                    "strategy": r.evaluation.strategy,
                    "overall": r.evaluation.score.overall,
                    "consistency_pct": float(r.evaluation.walk_forward.consistency_pct),
                    "mean_sharpe": r.evaluation.walk_forward.mean_sharpe,
                    "mean_return_pct": float(r.evaluation.walk_forward.mean_return_pct),
                }
                for r in report.leaderboard.ranked
            ],
            "recommendation": {
                "action": rec.action,
                "strategy": rec.strategy,
                "confidence": rec.confidence,
                "trust_threshold": rec.trust_threshold,
                "requires_human_approval": rec.requires_human_approval,
                "rationale": rec.rationale,
            },
        }
        print(json.dumps(payload, indent=2))  # noqa: T201 — CLI data channel
    else:
        print(_format_report(report))  # noqa: T201 — CLI data channel
    return 0


async def _cmd_leaderboard(args: argparse.Namespace) -> int:
    ledger = PerformanceLedger()
    records = list(reversed(await ledger.history(symbol=args.symbol)))
    lines = [f"Recorded evaluations — {args.symbol}  ({len(records)} rows, newest first)"]
    lines.append(f"{'created_at':<34}{'strategy':<24}{'kind':<14}{'ret%':>9}{'sharpe':>8}")
    lines.append("-" * 89)
    for rec in records[: args.limit]:
        consistency = "" if rec.consistency_pct is None else f"  consist {rec.consistency_pct}%"
        lines.append(
            f"{rec.created_at.isoformat():<34}{rec.strategy:<24}{rec.kind:<14}"
            f"{float(rec.return_pct):>9.2f}{rec.sharpe:>8.2f}{consistency}"
        )
    print("\n".join(lines))  # noqa: T201 — CLI data channel
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research",
        description="Autoresearch orchestrator — evaluate, rank, and recommend (human-gated).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="evaluate the roster → leaderboard + recommendation")
    p_run.add_argument("--symbol", default="AAPL", help="symbol label for the run")
    p_run.add_argument(
        "--asset-class",
        default="stock",
        choices=["stock", "etf", "bond", "fx", "crypto", "prediction"],
        help="asset class label",
    )
    p_run.add_argument("--n-windows", type=int, default=5, help="walk-forward window count")
    p_run.add_argument("--trust", type=_trust_arg, default=0.6, help="trust-gate threshold (0-1)")
    p_run.add_argument(
        "--bars-csv", default=None, help="CSV with a 'close' column (else synthetic)"
    )
    p_run.add_argument("--no-record", action="store_true", help="do not write to the ledger")
    p_run.add_argument(
        "--roster-db",
        default=None,
        help="use the human-promoted active roster from this RosterStore (else built-in defaults)",
    )
    p_run.add_argument("--json", action="store_true", help="emit JSON instead of a table")

    p_lb = sub.add_parser("leaderboard", help="print recorded evaluation history for a symbol")
    p_lb.add_argument("--symbol", default="AAPL", help="symbol to show history for")
    p_lb.add_argument("--limit", type=int, default=20, help="max rows to show")

    return parser


def _configure_logging() -> None:
    """Route logs to stderr so stdout stays a clean data channel.

    The research tool never trades, so it must NOT require the bridge's trading
    settings (trading_mode / webhook secret) just to print a leaderboard. When
    those settings are present (e.g. inside the deployed bridge env) we use the
    shared config; when absent (standalone `research run`) we fall back to a
    minimal stderr config rather than crashing on missing trading secrets.
    """
    try:
        configure_logging(stream=sys.stderr)
    except ValidationError:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"run": _cmd_run, "leaderboard": _cmd_leaderboard}
    return asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
