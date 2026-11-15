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
    for item in fields:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise typer.BadParameter(f"expected key=value, got {item!r}")
        if key.strip() in ("date", "at"):
            raise typer.BadParameter(f"{key!r} is set by the command; use --date")
        try:
            parsed[key.strip()] = parse_value(key.strip(), value)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    if day is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise typer.BadParameter(f"--date must be YYYY-MM-DD, got {day!r}")
    try:
        when = date.fromisoformat(day).isoformat() if day else date.today().isoformat()
    except ValueError as exc:
        raise typer.BadParameter(f"--date is not a real date: {day!r}") from exc
    j = _journal(journal)
    try:
        entry = j.record(when, parsed, at=datetime.now().strftime("%H:%M"))
    except JournalLockTimeout as exc:
        typer.echo(f"not recorded: {exc}", err=True)
        raise typer.Exit(3) from exc
    for line in j.unparsed:
        typer.echo(f"kept a journal line that does not parse: {line[:80]}", err=True)
    typer.echo(json.dumps(entry, ensure_ascii=False))


@app.command("show")
def show(
    days: int = typer.Option(7, "--days", min=1, help="How many recent entries (at least 1)."),
    journal: Path | None = typer.Option(None, "--journal"),
) -> None:
    """The last N entries, one JSON object per line."""
    for entry in _journal(journal).recent(days):
        typer.echo(json.dumps(entry, ensure_ascii=False))
