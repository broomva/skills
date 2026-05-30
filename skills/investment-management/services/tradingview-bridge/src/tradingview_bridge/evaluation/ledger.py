"""PerformanceLedger — the persistent scoreboard.

Records every evaluation of a strategy (a one-shot backtest, a walk-forward
aggregate, or a live-paper measurement) so the orchestration layer can compare
them over time. The single most honest comparison it surfaces is
``compare_sim_vs_live``: how a strategy's live-paper return diverges from its
backtest — the gap that tells you whether a backtest edge survived contact with
reality.

Cross-process safe (SQLite file), mirroring the OrderLedger pattern.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import aiosqlite
import structlog

log = structlog.get_logger("tradingview_bridge.evaluation.ledger")

EvaluationKind = Literal["backtest", "walk_forward", "live_paper"]


def default_ledger_db_path() -> Path:
    override = os.environ.get("TVBRIDGE_PERFORMANCE_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".tradingview-bridge" / "performance.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy         TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    n_trades         INTEGER NOT NULL,
    return_pct       TEXT NOT NULL,
    sharpe           REAL NOT NULL,
    max_drawdown_pct TEXT NOT NULL,
    win_rate_pct     TEXT NOT NULL,
    consistency_pct  TEXT,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_strategy ON evaluations(strategy);
CREATE INDEX IF NOT EXISTS idx_eval_kind ON evaluations(kind);
"""


@dataclass(frozen=True)
class EvaluationRecord:
    """One recorded evaluation of a strategy."""

    strategy: str
    symbol: str
    kind: EvaluationKind
    n_trades: int
    return_pct: Decimal
    sharpe: float
    max_drawdown_pct: Decimal
    win_rate_pct: Decimal
    consistency_pct: Decimal | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass(frozen=True)
class SimLiveGap:
    """Backtest/walk-forward vs live-paper — the reality check."""

    strategy: str
    sim_kind: str
    sim_return_pct: Decimal
    live_return_pct: Decimal
    sim_sharpe: float
    live_sharpe: float

    @property
    def return_gap_pct(self) -> Decimal:
        """live - sim. Negative (the usual case) = live underperformed backtest."""
        return self.live_return_pct - self.sim_return_pct


class PerformanceLedger:
    """Async SQLite store of strategy evaluations."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or default_ledger_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    @property
    def db_path(self) -> Path:
        return self._db_path

    async def _ensure_schema(self, db: aiosqlite.Connection) -> None:
        if not self._initialized:
            await db.executescript(SCHEMA)
            await db.commit()
            self._initialized = True

    async def record(self, rec: EvaluationRecord) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            await db.execute(
                "INSERT INTO evaluations (strategy, symbol, kind, n_trades, return_pct, "
                "sharpe, max_drawdown_pct, win_rate_pct, consistency_pct, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rec.strategy,
                    rec.symbol,
                    rec.kind,
                    rec.n_trades,
                    str(rec.return_pct),
                    rec.sharpe,
                    str(rec.max_drawdown_pct),
                    str(rec.win_rate_pct),
                    None if rec.consistency_pct is None else str(rec.consistency_pct),
                    rec.created_at.isoformat(),
                ),
            )
            await db.commit()
        log.info(
            "evaluation_recorded",
            strategy=rec.strategy,
            kind=rec.kind,
            return_pct=str(rec.return_pct),
        )

    async def history(
        self,
        strategy: str | None = None,
        kind: EvaluationKind | None = None,
    ) -> list[EvaluationRecord]:
        clauses: list[str] = []
        params: list[str] = []
        if strategy is not None:
            clauses.append("strategy = ?")
            params.append(strategy)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        # `where` is built only from literal column clauses ("strategy = ?" /
        # "kind = ?"); all values are parameterized below. No injection surface.
        query = (
            "SELECT strategy, symbol, kind, n_trades, return_pct, sharpe, "
            "max_drawdown_pct, win_rate_pct, consistency_pct, created_at "
            f"FROM evaluations{where} ORDER BY id ASC"
        )
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [_row_to_record(tuple(r)) for r in rows]

    async def latest(self, strategy: str, kind: EvaluationKind) -> EvaluationRecord | None:
        rows = await self.history(strategy=strategy, kind=kind)
        return rows[-1] if rows else None

    async def compare_sim_vs_live(self, strategy: str) -> SimLiveGap | None:
        """Compare a strategy's most recent sim evaluation to its latest live-paper."""
        sim = await self.latest(strategy, "walk_forward")
        sim_kind = "walk_forward"
        if sim is None:
            sim = await self.latest(strategy, "backtest")
            sim_kind = "backtest"
        live = await self.latest(strategy, "live_paper")
        if sim is None or live is None:
            return None
        return SimLiveGap(
            strategy=strategy,
            sim_kind=sim_kind,
            sim_return_pct=sim.return_pct,
            live_return_pct=live.return_pct,
            sim_sharpe=sim.sharpe,
            live_sharpe=live.sharpe,
        )

    async def clear(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            await db.execute("DELETE FROM evaluations")
            await db.commit()


def _row_to_record(r: tuple[Any, ...]) -> EvaluationRecord:
    consistency = r[8]
    kind: EvaluationKind = str(r[2])  # type: ignore[assignment]  # DB-constrained
    return EvaluationRecord(
        strategy=str(r[0]),
        symbol=str(r[1]),
        kind=kind,
        n_trades=int(r[3]),
        return_pct=Decimal(str(r[4])),
        sharpe=float(r[5]),
        max_drawdown_pct=Decimal(str(r[6])),
        win_rate_pct=Decimal(str(r[7])),
        consistency_pct=None if consistency is None else Decimal(str(consistency)),
        created_at=datetime.fromisoformat(str(r[9])),
    )
