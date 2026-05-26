"""Bookkeeping journal hook — subprocess-shells out to the workspace bookkeeping CLI.

Every accepted alert journals a one-line note to the workspace's
research/entities/pattern/strategy-{strategy_name}.md via the
broomva/bookkeeping skill (P6). When the CLI isn't on PATH or the
workspace isn't reachable, this hook degrades gracefully — logs a
warning and returns; never blocks the request.

Design intent:
- Fire-and-forget (asyncio.create_task) so the webhook response isn't blocked
- Idempotent at the journal level (bookkeeping handles dedup of identical entries)
- Cross-repo: this service is in skills/investment-management/services/, but
  the bookkeeping CLI lives in the workspace (~/broomva/skills/bookkeeping/)
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

import structlog

from .clients.base import OrderReceipt
from .schemas import TVAlert

log = structlog.get_logger("tradingview_bridge.bookkeeping")

# Strong refs to fire-and-forget tasks so asyncio doesn't GC them mid-flight.
# Tasks remove themselves from this set when they finish (done_callback below).
_background_tasks: set[asyncio.Task[None]] = set()


def _resolve_bookkeeping_cli() -> Path | None:
    """Find the bookkeeping CLI script, or None if not reachable.

    Order:
      1. TVBRIDGE_BOOKKEEPING_CLI env var (explicit override)
      2. ~/broomva/skills/bookkeeping/scripts/bookkeeping.py (workspace default)
      3. PATH lookup for `bookkeeping`
    """
    override = os.environ.get("TVBRIDGE_BOOKKEEPING_CLI")
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None

    workspace_path = (
        Path.home() / "broomva" / "skills" / "bookkeeping" / "scripts" / "bookkeeping.py"
    )
    if workspace_path.exists():
        return workspace_path

    on_path = shutil.which("bookkeeping")
    if on_path:
        return Path(on_path)

    return None


async def journal_alert(alert: TVAlert, receipt: OrderReceipt) -> None:
    """Append a one-line journal entry for an accepted alert.

    Non-blocking: launched via asyncio.create_task by the webhook handler
    so the response returns immediately. Errors are logged but never
    raised back to the caller.
    """
    cli = _resolve_bookkeeping_cli()
    if cli is None:
        log.warning(
            "bookkeeping_cli_not_found",
            alert_id=alert.alert_id,
            note="set TVBRIDGE_BOOKKEEPING_CLI or run from broomva workspace",
        )
        return

    content = (
        f"Strategy `{alert.strategy_name}` fired alert `{alert.alert_id}` — "
        f"{alert.action} {alert.size} {alert.symbol} ({alert.asset_class}) "
        f"via {receipt.broker} (order {receipt.order_id})."
    )

    cmd = [
        "python3",
        str(cli),
        "file",
        "--content",
        content,
        "--slug",
        f"strategy-{alert.strategy_name}",
        "--type",
        "pattern",
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)
        if process.returncode != 0:
            log.warning(
                "bookkeeping_subprocess_nonzero",
                alert_id=alert.alert_id,
                returncode=process.returncode,
                stderr=stderr.decode("utf-8", errors="replace")[:500],
            )
            return
        log.info("bookkeeping_journaled", alert_id=alert.alert_id, strategy=alert.strategy_name)
    except (TimeoutError, OSError) as e:
        log.warning(
            "bookkeeping_subprocess_failed",
            alert_id=alert.alert_id,
            error=str(e),
        )


def schedule_journal(alert: TVAlert, receipt: OrderReceipt) -> None:
    """Fire-and-forget wrapper. Schedules journal_alert without awaiting it.

    Called from the webhook handler; the request returns immediately while
    the journal subprocess runs in the background event loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Not in an event loop (e.g., called from sync test code) — skip.
        log.debug("bookkeeping_no_running_loop", alert_id=alert.alert_id)
        return
    task = loop.create_task(journal_alert(alert, receipt))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def journal_callable_for_tests() -> Any:
    """Test hook — returns the function tests should patch with AsyncMock."""
    return journal_alert
