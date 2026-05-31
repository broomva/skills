"""`optimize` CLI — the EGRI parameter-optimization entry point.

`optimize run --family sma-crossover --symbol AAPL` grid-searches a strategy
family's parameter space with a true train/test holdout, and reports the best
GENERALIZING params (selected in-sample, estimated on a held-out test segment)
plus the generalization gap.

Safety: this only *measures and recommends* params. It never trades, never
records, never auto-applies — promotion to the live roster or capital is
human-gated. Logs go to stderr so stdout stays a clean data channel.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog
from pydantic import ValidationError

from ..logging_setup import configure_logging
from ..orchestrator.cli import bars_from_csv, synthetic_bars
from ..strategy.types import Bar
from .egri import optimize_walk_forward
from .space import BUILTIN_SPACES
from .types import OptimizationResult


def _configure_logging() -> None:
    """Route logs to stderr; fall back to minimal config when the bridge's
    trading settings are absent (the optimizer never trades, so it must not
    require them just to print a result)."""
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


def _train_frac_arg(value: str) -> float:
    parsed = float(value)
    if not 0.0 < parsed < 1.0:
        raise argparse.ArgumentTypeError(f"--train-frac must be in (0, 1), got {parsed}")
    return parsed


def _bars(args: argparse.Namespace) -> list[Bar]:
    if args.bars_csv:
        return bars_from_csv(Path(args.bars_csv).expanduser())
    return synthetic_bars(args.bars)


def _format_result(result: OptimizationResult, top: int) -> str:
    shown = min(top, len(result.ranked))
    lines = [
        f"EGRI optimize — {result.family} on {result.symbol}",
        f"  {result.n_candidates} candidates · train/test split at bar {result.split_index} "
        f"(train_frac {result.train_frac})",
        "",
        f"Top {shown} by TRAIN score (selection is train-only):",
        f"  {'strategy':<26}{'train':>8}",
    ]
    for c in result.ranked[:top]:
        marker = "  ← winner" if c is result.best else ""
        lines.append(f"  {c.strategy_name:<26}{c.train_score:>8.3f}{marker}")
    lines += [
        "",
        "Out-of-sample holdout (the winner scored ONCE on the test segment):",
        f"  winner       : {result.best.strategy_name}   params={result.best.params}",
        f"  train score  : {result.best.train_score:.3f}",
        f"  TEST score   : {result.test_score:.3f}    (the honest estimate)",
        f"  gen. gap     : {result.generalization_gap:+.3f}    (train - test; lower is better)",
        f"  generalizes  : {result.generalizes}    (floor {result.min_test_score:.2f}, "
        f"max gap {result.max_gap:.2f})",
        f"  human-gated  : {result.requires_human_approval}",
        f"  rationale    : {result.rationale}",
    ]
    return "\n".join(lines)


def _cmd_run(args: argparse.Namespace) -> int:
    space = BUILTIN_SPACES[args.family]  # argparse choices guarantees membership
    result = optimize_walk_forward(
        space,
        _bars(args),
        symbol=args.symbol,
        asset_class=args.asset_class,
        train_frac=args.train_frac,
        n_windows=args.n_windows,
        min_test_score=args.min_test,
        max_gap=args.max_gap,
    )
    if args.json:
        payload = {
            "family": result.family,
            "symbol": result.symbol,
            "n_candidates": result.n_candidates,
            "train_frac": result.train_frac,
            "split_index": result.split_index,
            "best": {
                "params": result.best.params,
                "strategy": result.best.strategy_name,
                "train_score": result.best.train_score,
            },
            "test_score": result.test_score,
            "generalization_gap": result.generalization_gap,
            "generalizes": result.generalizes,
            "requires_human_approval": result.requires_human_approval,
            "ranked": [
                {"strategy": c.strategy_name, "params": c.params, "train_score": c.train_score}
                for c in result.ranked
            ],
        }
        print(json.dumps(payload, indent=2))  # noqa: T201 — CLI data channel
    else:
        print(_format_result(result, args.top))  # noqa: T201 — CLI data channel
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optimize",
        description="EGRI param-optimization with a true train/test holdout (human-gated).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="grid-search a strategy family with a train/test holdout")
    p.add_argument(
        "--family",
        default="sma-crossover",
        choices=sorted(BUILTIN_SPACES),
        help="strategy family to optimize",
    )
    p.add_argument("--symbol", default="AAPL", help="symbol label for the run")
    p.add_argument(
        "--asset-class",
        default="stock",
        choices=["stock", "etf", "bond", "fx", "crypto", "prediction"],
        help="asset class label",
    )
    p.add_argument(
        "--train-frac",
        type=_train_frac_arg,
        default=0.7,
        help="fraction of bars used for in-sample search (rest is the holdout)",
    )
    p.add_argument("--n-windows", type=int, default=4, help="walk-forward window count")
    p.add_argument("--bars", type=int, default=500, help="synthetic bar count (if no --bars-csv)")
    p.add_argument("--bars-csv", default=None, help="CSV with a 'close' column (else synthetic)")
    p.add_argument("--min-test", type=float, default=0.5, help="min OOS test score to 'generalize'")
    p.add_argument("--max-gap", type=float, default=0.25, help="max train-test gap to 'generalize'")
    p.add_argument("--top", type=int, default=8, help="how many train-ranked candidates to show")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = build_parser().parse_args(argv)
    return _cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
