"""``health checkin`` — record and read the holistic daily check-in (BRO-3751).

The protocol (what to ask, how to reflect, the safety table) is ``Workflows/CheckIn.md``.
This command is the only writer of the journal, so its storage rules hold whichever agent
or person runs the check-in.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import typer

from broomva_health.adapters.repositories.journal import (
    JournalLockTimeout,
    JsonlJournal,
    parse_value,
    private_dir_problems,
)
from broomva_health.config.paths import HealthPaths

__all__ = ["app"]

app = typer.Typer(
    no_args_is_help=True, help="Holistic daily check-in journal (physical, mental, spiritual)."
)


def _journal(journal: Path | None) -> JsonlJournal:
    """The journal to use. Every location, the default included, must pass the privacy checks."""
    env = os.environ.get("BROOMVA_HEALTH_JOURNAL")
    chosen = journal or (Path(env) if env else None)
    if chosen is None:
        chosen = HealthPaths.discover().data_dir / "journal.jsonl"
    chosen = chosen.expanduser()
    problems = private_dir_problems(chosen.parent)
    if chosen.is_symlink():
        problems.append(f"{chosen} is a symlink")
    elif chosen.exists() and not chosen.is_file():
        problems.append(f"{chosen} is not a regular file")
    if problems:
        raise typer.BadParameter("refusing this journal location: " + "; ".join(problems))
    return JsonlJournal(chosen)


@app.command("record")
def record(
    fields: list[str] = typer.Argument(
        ..., help="key=value pairs, e.g. body=Okay body_score=5 note='good walk'"
    ),
    day: str | None = typer.Option(
        None, "--date", help="ISO date for a late check-in. Default: today."
    ),
    journal: Path | None = typer.Option(
        None, "--journal", help="Journal file (owner-only, no git, no cloud sync)."
    ),
) -> None:
    """Merge answers into a day's entry (new keys win, earlier answers stay)."""
    parsed: dict[str, object] = {}
    for position, item in enumerate(fields, start=1):
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise typer.BadParameter(f"argument {position} is not key=value")
        if key.strip() in ("date", "at"):
            raise typer.BadParameter("date and at are set by the command; use --date")
        try:
            parsed[key.strip()] = parse_value(key.strip(), value)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    if parsed.get("safety_stop") is True and set(parsed) != {"safety_stop"}:
        # A safety stop stores the marker and nothing else (Workflows/CheckIn.md).
        raise typer.BadParameter("safety_stop=yes is recorded alone, with no other answers")
    if day is not None and (
        not day.isascii() or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day)
    ):
        raise typer.BadParameter("--date must be YYYY-MM-DD")
    try:
        when = date.fromisoformat(day).isoformat() if day else date.today().isoformat()
    except ValueError as exc:
        raise typer.BadParameter("--date is not a real date") from exc
    j = _journal(journal)
    try:
        entry = j.record(when, parsed, at=datetime.now().strftime("%H:%M"))
    except JournalLockTimeout as exc:
        typer.echo(f"not recorded: {exc}", err=True)
        raise typer.Exit(3) from exc
    except (OSError, ValueError) as exc:
        typer.echo(f"not recorded: {type(exc).__name__}", err=True)  # no journal content in errors
        raise typer.Exit(1) from exc
    if j.unparsed:
        # A count only: journal lines are private and never go to logs or stderr.
        typer.echo(f"kept {len(j.unparsed)} journal line(s) that do not parse, unchanged", err=True)
    typer.echo(json.dumps(entry, ensure_ascii=False))


@app.command("show")
def show(
    days: int = typer.Option(7, "--days", min=1, help="How many recent entries (at least 1)."),
    journal: Path | None = typer.Option(None, "--journal"),
) -> None:
    """The last N entries, one JSON object per line."""
    try:
        entries = _journal(journal).recent(days)
    except OSError as exc:
        typer.echo(f"cannot read the journal: {type(exc).__name__}", err=True)
        raise typer.Exit(1) from exc
    for entry in entries:
        typer.echo(json.dumps(entry, ensure_ascii=False))
