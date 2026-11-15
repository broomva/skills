"""Where ledger rows live, and the harvest that fills them.

Layout under the ledger directory (default ``~/.local/share/year-in-ai/ledger``)::

    2026-11.jsonl      one row per line, appended, never rewritten
    harvests.jsonl     one line per harvest run: what each store contributed

A harvest is idempotent. Row ids are content-derived, so running it twice,
or over a live store and its archived copy, adds nothing the second time.

Store locations come from built-in defaults plus an optional JSON config at
``~/.config/year-in-ai/config.json``::

    {"roots": {"claude_projects": ["/Volumes/Archive/claude-projects"],
               "exports": ["/path/to/conversations.jsonl"]},
     "bridged_utc_offset_hours": -5}

Config roots are added to the defaults, never replace them.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set

from . import SCHEMA
from . import sources as S

DEFAULT_LEDGER = "~/.local/share/year-in-ai/ledger"
DEFAULT_CONFIG = "~/.config/year-in-ai/config.json"

#: Built-in candidate locations per store. Globs are allowed.
DEFAULT_ROOTS: Dict[str, List[str]] = {
    "t3_db": ["~/.t3/userdata/statev2.sqlite"],
    "conductor_db": ["~/Library/Application Support/com.conductor.app/conductor.db"],
    "claude_projects": ["~/.claude/projects"],
    "claude_history": ["~/.claude/history.jsonl"],
    "codex_sessions": ["~/.codex/sessions", "~/.codex/archived_sessions"],
    "codex_history": ["~/.codex/history.jsonl"],
    "gemini_tmp": ["~/.gemini/tmp"],
    "paseo_agents": ["~/.paseo/agents"],
    "bridged": [],
    "exports": [],
}


def expand_path(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def load_config(path: Optional[str] = None) -> dict:
    cfg = expand_path(path or DEFAULT_CONFIG)
    if not cfg.is_file():
        return {}
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_roots(config: dict, overrides: Optional[Dict[str, List[str]]] = None,
                  defaults: bool = True) -> Dict[str, List[Path]]:
    """Defaults, plus config roots, plus command-line roots; existing paths only, de-duplicated."""
    merged: Dict[str, List[str]] = {k: list(v) if defaults else [] for k, v in DEFAULT_ROOTS.items()}
    for source in ((config.get("roots") or {}), (overrides or {})):
        for key, values in source.items():
            if key in merged and values:
                merged[key].extend(values if isinstance(values, list) else [values])
    resolved: Dict[str, List[Path]] = {}
    for key, values in merged.items():
        seen: Set[str] = set()
        out: List[Path] = []
        for path in S.expand(values):
            real = os.path.realpath(path)
            if real not in seen:
                seen.add(real)
                out.append(path)
        resolved[key] = out
    return resolved


def readers(roots: Dict[str, List[Path]], since: Optional[float], bridged_offset: float = -5.0):
    """Every reader, wired to its resolved roots. Order sets dedupe priority in the fold."""
    paseo: Set[str] = set()
    for agents in roots.get("paseo_agents", []):
        paseo |= S.paseo_session_ids(agents)

    def each(key: str, reader, *extra):
        """One reader per configured file; an absent store still reports once."""
        paths = roots.get(key) or [None]
        return [reader(path, since, *extra) for path in paths]

    return [
        *each("t3_db", S.read_t3),
        S.read_claude_projects(roots["claude_projects"], since, paseo),
        *each("conductor_db", S.read_conductor),
        S.read_codex_sessions(roots["codex_sessions"], since),
        S.read_gemini(roots["gemini_tmp"], since),
        *each("claude_history", S.read_claude_history),
        S.read_exports(roots["exports"], since),
        S.read_bridged(roots["bridged"], since, bridged_offset),
        *each("codex_history", S.read_codex_history),
    ]


class Ledger:
    """Monthly JSONL files with id-level idempotency."""

    def __init__(self, directory: Optional[str] = None):
        self.dir = expand_path(directory or DEFAULT_LEDGER)

    def _month_file(self, ts: float) -> Path:
        return self.dir / (_dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m") + ".jsonl")

    def _ids(self, path: Path) -> Set[str]:
        ids: Set[str] = set()
        if not path.is_file():
            return ids
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    ids.add(json.loads(line)["id"])
                except (ValueError, KeyError):
                    continue
        return ids

    def write(self, rows: Iterable[dict]) -> Dict[str, int]:
        """Append rows not already present. Returns new-row counts per month file."""
        self.dir.mkdir(parents=True, exist_ok=True)
        known: Dict[Path, Set[str]] = {}
        pending: Dict[Path, List[str]] = {}
        added: Dict[str, int] = {}
        for row in rows:
            path = self._month_file(row["ts"])
            if path not in known:
                known[path] = self._ids(path)
            if row["id"] in known[path]:
                continue
            known[path].add(row["id"])
            pending.setdefault(path, []).append(json.dumps(row, separators=(",", ":"), sort_keys=True))
            if len(pending[path]) >= 5000:
                self._flush(path, pending.pop(path))
            added[path.stem] = added.get(path.stem, 0) + 1
        for path, lines in pending.items():
            self._flush(path, lines)
        return added

    @staticmethod
    def _flush(path: Path, lines: List[str]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def rows(self, since: Optional[float] = None, until: Optional[float] = None) -> Iterator[dict]:
        if not self.dir.is_dir():
            return
        for path in sorted(self.dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if since is not None and row["ts"] < since:
                        continue
                    if until is not None and row["ts"] >= until:
                        continue
                    yield row

    def log_harvest(self, entry: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / "harvests.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def harvest(ledger: Ledger, roots: Dict[str, List[Path]], since: Optional[float],
            bridged_offset: float = -5.0) -> dict:
    """Run every reader and append its rows. Returns the per-store coverage of this run."""
    started = time.time()
    reports = []
    added: Dict[str, int] = {}
    for report, rows in readers(roots, since, bridged_offset):
        for month, count in ledger.write(rows).items():
            added[month] = added.get(month, 0) + count
        reports.append(report.to_dict())
    entry = {
        "schema": SCHEMA,
        "started": _dt.datetime.fromtimestamp(started, _dt.timezone.utc).isoformat(),
        "seconds": round(time.time() - started, 1),
        "since": _dt.datetime.fromtimestamp(since, _dt.timezone.utc).isoformat() if since else None,
        "added": added,
        "sources": reports,
    }
    ledger.log_harvest(entry)
    return entry
