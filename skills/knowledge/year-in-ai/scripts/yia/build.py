"""Assemble the payload: discover stores, stream them, fold, and emit.

This module is the only place that knows about all the readers at once, and it
is deliberately the only place allowed to decide that a section is *absent*.
A section derived from an unavailable store is omitted from the payload
entirely rather than emitted as an empty or zeroed structure, so a downstream
card can never render "0" for something that was simply never measured.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from . import SCHEMA, __version__
from .aura import compute as compute_aura
from .discovery import Stores
from .metrics import Aggregator
from .model import SourceReport, Window
from .personality import classify
from .readers import bridged, claude_code, codex, git_repos, knowledge, prompt_history


def window_for_year(year: int | None, since: str | None, until: str | None) -> Window:
    """Build the requested window from CLI arguments."""

    def parse(value: str | None) -> _dt.datetime | None:
        if not value:
            return None
        return _dt.datetime.fromisoformat(value).replace(tzinfo=_dt.timezone.utc)

    if year is not None:
        start = _dt.datetime(year, 1, 1, tzinfo=_dt.timezone.utc)
        end = _dt.datetime(year + 1, 1, 1, tzinfo=_dt.timezone.utc)
        return Window(start=start, end=end, label=str(year))
    start, end = parse(since), parse(until)
    if start or end:
        label = f"{start.date() if start else 'start'} → {end.date() if end else 'now'}"
        return Window(start=start, end=end, label=label)
    return Window(label="all time")


def build_payload(
    stores: Stores,
    window: Window,
    *,
    git_author: str | None = None,
    include_outcomes: bool = True,
) -> dict[str, Any]:
    """Run every reader and fold the result into a single payload dict."""
    agg = Aggregator(window)
    coverage: list[SourceReport] = []

    for report, stream in (
        claude_code.read(stores.claude_projects, window),
        codex.read(stores.codex_sessions, window),
        prompt_history.read(stores.claude_history, window),
    ):
        coverage.append(report)
        for event in stream:
            agg.add(event)

    bridged_report, sessions = bridged.read(stores.bridged_roots, window)
    coverage.append(bridged_report)

    outcomes: dict[str, Any] = {}
    if include_outcomes:
        kg_report, kg_stats = knowledge.read_kg(stores.kg_entities)
        mem_report, mem_stats = knowledge.read_memory(stores.memory_dir)
        git_report, git_stats = git_repos.read(stores.git_roots, window, git_author)
        coverage.extend([kg_report, mem_report, git_report])
        if kg_stats is not None:
            outcomes["knowledge_graph"] = kg_stats.to_dict()
        if mem_stats is not None:
            outcomes["memory"] = mem_stats.to_dict()
        if git_stats is not None:
            outcomes["git"] = git_stats.to_dict()

    # Bridged files are the only wall-clock record; keep them as a cross-check
    # against the gap-based estimate rather than replacing it.
    if sessions:
        durations = [s.duration_minutes for s in sessions if s.duration_minutes is not None]
        outcomes["bridged"] = {
            "sessions": len(sessions),
            "with_duration": len(durations),
            "reported_minutes": sum(durations) if durations else None,
            "note": (
                "Wall-clock as recorded by the session bridge. The headline "
                "'active minutes' is measured independently from event gaps."
            ),
        }

    build, explore, delegate = agg.tool_family_counts()
    personality = classify(agg.personality_signals())
    aura = compute_aura(
        build=build,
        explore=explore,
        delegate=delegate,
        by_hour=agg.by_hour,
        total_tokens=sum(agg.tokens.values()),
        median_session_minutes=agg.median_session_minutes(),
    )

    identity: dict[str, Any] = {
        "tool_families": {"build": build, "explore": explore, "delegate": delegate},
    }
    if personality is not None:
        identity["personality"] = personality.to_dict()
    else:
        identity["personality_unavailable"] = (
            "At least one axis had no measurable signal in this window."
        )
    if aura is not None:
        identity["aura"] = aura.to_dict()

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generator_version": __version__,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "window": window.to_dict(),
        "coverage": [r.to_dict() for r in coverage],
        "totals": agg.totals(),
        "rankings": agg.rankings(),
        "rhythm": agg.rhythm(),
        "identity": identity,
        "moments": agg.moments(),
        "share_safe": False,
    }
    if outcomes:
        payload["outcomes"] = outcomes

    payload["honesty"] = _honesty_notes(payload, coverage)
    return payload


def _honesty_notes(payload: dict[str, Any], coverage: list[SourceReport]) -> dict[str, Any]:
    """State plainly what this run could and could not see.

    A deck titled "Your Year in AI" implies twelve months. When the corpus does
    not stretch that far, the payload has to say so, in the payload itself,
    where every renderer will trip over it.
    """
    window = payload["window"]
    observed_days = window.get("observed_days")
    unavailable = [r.name for r in coverage if not r.available]
    available = [r for r in coverage if r.available]
    return {
        "observed_days": observed_days,
        "covers_full_year": bool(observed_days and observed_days >= 365),
        "sources_available": [r.name for r in available],
        "sources_unavailable": unavailable,
        "no_percentiles": (
            "No stat here is a percentile. A local corpus contains one person, "
            "so there is no population to rank against."
        ),
        "active_time_method": (
            "Active minutes sum the gaps between consecutive events in a session, "
            "discarding any gap over 30 minutes."
        ),
    }
