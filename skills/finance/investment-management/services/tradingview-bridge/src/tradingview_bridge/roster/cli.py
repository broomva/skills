"""`roster` CLI — the promotion registry (closes the self-improving loop, human-gated).

  roster propose --family sma-crossover   optimize a family; if it generalizes,
                                          record a PROPOSED entry (automatic).
  roster propose --all                    propose across every built-in family.
  roster list [--status proposed]         show registry entries + their evidence.
  roster promote <id>                     HUMAN gate: proposed → active.
  roster reject <id> [--note ...]         HUMAN gate: decline an entry.
  roster active                           show the effective active roster (what
                                          the orchestrator would measure).

Safety: `propose` only records OOS-validated candidates; `promote` is the human
gate that activates params; even an active entry only changes what the orchestrator
*measures* — allocation to capital stays a separate human gate. Logs → stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import structlog
from pydantic import ValidationError

from ..barsource import bars_from_csv, synthetic_bars
from ..logging_setup import configure_logging
from ..optimize.egri import optimize_walk_forward
from ..optimize.space import BUILTIN_SPACES
from ..strategy.types import Bar
from .promotion import promote, propose_from_optimization, reject
from .store import RosterStore, default_roster_db_path
from .types import RosterEntry


def _configure_logging() -> None:
    try:
        configure_logging(stream=sys.stderr)
    except ValidationError:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.__stderr__),
        )


def _store(args: argparse.Namespace) -> RosterStore:
    db = Path(args.db).expanduser() if args.db else default_roster_db_path()
    return RosterStore(db_path=db)


def _bars(args: argparse.Namespace) -> list[Bar]:
    if args.bars_csv:
        return bars_from_csv(Path(args.bars_csv).expanduser())
    return synthetic_bars(args.bars)


def _print(text: str) -> None:
    print(text)  # noqa: T201 — CLI data channel


def _fmt_entry(e: RosterEntry) -> str:
    return (
        f"  [{e.entry_id}] {e.status:<10} {e.strategy_name:<24} "
        f"train {e.train_score:.3f}  test {e.test_score:.3f}  gap {e.generalization_gap:+.3f}"
    )


async def _cmd_propose(args: argparse.Namespace) -> int:
    store = _store(args)
    families = sorted(BUILTIN_SPACES) if args.all else [args.family]
    bars = _bars(args)
    lines: list[str] = []
    for family in families:
        result = optimize_walk_forward(
            BUILTIN_SPACES[family],
            bars,
            symbol=args.symbol,
            asset_class=args.asset_class,
            train_frac=args.train_frac,
            n_windows=args.n_windows,
            min_test_score=args.min_test,
            max_gap=args.max_gap,
        )
        entry = propose_from_optimization(result)
        if entry is None:
            lines.append(
                f"  {family:<20} did NOT generalize (test {result.test_score:.3f}, "
                f"gap {result.generalization_gap:+.3f}) — not proposed"
            )
            continue
        new_id = await store.record(entry)
        lines.append(
            f"  {family:<20} PROPOSED as [{new_id}] {entry.strategy_name} "
            f"(test {entry.test_score:.3f}, gap {entry.generalization_gap:+.3f})"
        )
    _print("Proposals:\n" + "\n".join(lines))
    _print("\nReview with `roster list --status proposed`, then `roster promote <id>`.")
    return 0


async def _cmd_list(args: argparse.Namespace) -> int:
    store = _store(args)
    entries = await store.list_entries(status=args.status)
    label = args.status or "all"
    if not entries:
        _print(f"No roster entries (status={label}).")
        return 0
    _print(f"Roster entries (status={label}):")
    _print("\n".join(_fmt_entry(e) for e in entries))
    return 0


async def _cmd_promote(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        entry = await promote(store, args.id)
    except ValueError as exc:
        _print(f"cannot promote: {exc}")
        return 1
    _print(f"PROMOTED [{entry.entry_id}] {entry.strategy_name} → active.")
    _print("The orchestrator will now measure these params when run with --roster-db.")
    return 0


async def _cmd_reject(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        entry = await reject(store, args.id, note=args.note or "")
    except ValueError as exc:
        _print(f"cannot reject: {exc}")
        return 1
    _print(f"REJECTED [{entry.entry_id}] {entry.strategy_name}.")
    return 0


async def _cmd_active(args: argparse.Namespace) -> int:
    store = _store(args)
    entries = await store.active_entries()
    if not entries:
        _print("No active roster entries — the orchestrator uses its built-in default roster.")
        return 0
    _print("Active roster (the orchestrator measures these when run with --roster-db):")
    _print("\n".join(_fmt_entry(e) for e in entries))
    return 0


def _train_frac_arg(value: str) -> float:
    parsed = float(value)
    if not 0.0 < parsed < 1.0:
        raise argparse.ArgumentTypeError(f"--train-frac must be in (0, 1), got {parsed}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roster",
        description="Strategy roster promotion registry (human-gated).",
    )
    parser.add_argument("--db", default=None, help="roster SQLite path (else the default)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prop = sub.add_parser("propose", help="optimize a family and propose it if it generalizes")
    grp = p_prop.add_mutually_exclusive_group()
    grp.add_argument("--family", default="sma-crossover", choices=sorted(BUILTIN_SPACES))
    grp.add_argument("--all", action="store_true", help="propose across all families")
    p_prop.add_argument("--symbol", default="AAPL")
    p_prop.add_argument(
        "--asset-class",
        default="stock",
        choices=["stock", "etf", "bond", "fx", "crypto", "prediction"],
    )
    p_prop.add_argument("--train-frac", type=_train_frac_arg, default=0.7)
    p_prop.add_argument("--n-windows", type=int, default=4)
    p_prop.add_argument("--bars", type=int, default=500)
    p_prop.add_argument("--bars-csv", default=None)
    p_prop.add_argument("--min-test", type=float, default=0.5)
    p_prop.add_argument("--max-gap", type=float, default=0.25)

    p_list = sub.add_parser("list", help="show registry entries")
    p_list.add_argument(
        "--status", default=None, choices=["proposed", "active", "rejected", "superseded"]
    )

    p_prom = sub.add_parser("promote", help="HUMAN gate: proposed → active")
    p_prom.add_argument("id", type=int)

    p_rej = sub.add_parser("reject", help="HUMAN gate: decline an entry")
    p_rej.add_argument("id", type=int)
    p_rej.add_argument("--note", default=None)

    sub.add_parser("active", help="show the effective active roster")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = build_parser().parse_args(argv)
    handlers = {
        "propose": _cmd_propose,
        "list": _cmd_list,
        "promote": _cmd_promote,
        "reject": _cmd_reject,
        "active": _cmd_active,
    }
    return asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
