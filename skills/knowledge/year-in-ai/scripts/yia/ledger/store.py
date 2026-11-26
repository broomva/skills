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
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

from . import ROW_VERSION, SCHEMA, exclusive_lock, revision_identity, valid_row
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


class ConfigError(ValueError):
    """A config that exists but cannot be used. Never read as an empty config."""


def load_config(path: Optional[str] = None) -> dict:
    """The config as a dict. Only an absent *default* config is empty.

    A config named with ``--config`` that does not exist, one that cannot be
    read, and one that is not a JSON object all raise :class:`ConfigError`:
    reading them as ``{}`` would silently drop every configured store.
    """
    cfg = expand_path(path or DEFAULT_CONFIG)
    try:
        text = cfg.read_text(encoding="utf-8")
    except FileNotFoundError:
        if path:
            raise ConfigError(f"config {cfg} does not exist")
        return {}
    except OSError as exc:
        raise ConfigError(f"config {cfg} cannot be read: {exc.strerror or exc}")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ConfigError(f"config {cfg} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise ConfigError(f"config {cfg} is not a JSON object")
    return data


def resolve_roots(config: dict, overrides: Optional[Dict[str, List[str]]] = None,
                  defaults: bool = True) -> Dict[str, List[Path]]:
    """Defaults, plus config roots, plus command-line roots; existing paths only, de-duplicated."""
    merged: Dict[str, List[str]] = {k: list(v) if defaults else [] for k, v in DEFAULT_ROOTS.items()}
    for origin, source in (("config", config.get("roots") or {}), ("--root", overrides or {})):
        for key, values in source.items():
            if key not in merged:
                raise ValueError(f"{origin}: unknown store {key!r}; known stores: {', '.join(sorted(merged))}")
            if values:
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


def fingerprint(row: dict) -> str:
    """What makes a stored row out of date: its text and how it is attributed."""
    return f"{row['h']}|{row.get('author')}|{row.get('harness')}"


class LegacyLedgerError(RuntimeError):
    """The ledger directory holds rows written under another schema version."""


class Ledger:
    """Monthly JSONL files with id-level idempotency."""

    def __init__(self, directory: Optional[str] = None):
        self.dir = expand_path(directory or DEFAULT_LEDGER)
        #: Rows of another schema version seen by the last :meth:`rows` read.
        #: They are never folded: their ids, hashes and metadata follow other
        #: rules, so mixing them would double-count turns.
        self.legacy_rows = 0
        #: Lines that were not valid JSON (a torn write) in the last read.
        self.malformed_lines = 0

    def _month_file(self, ts: float) -> Path:
        return self.dir / (_dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m") + ".jsonl")

    def _scan(self) -> Tuple[Set[str], Dict[str, Tuple[int, str, int, str]], int]:
        """Every stored id, each occurrence's latest revision, and the highest sequence.

        Refuses a directory holding rows of another schema version, in any month.
        """
        ids: Set[str] = set()
        latest: Dict[str, Tuple[int, str, int, str]] = {}  # occurrence -> (seq, hash, revisions so far, id)
        top = 0
        if not self.dir.is_dir():
            return ids, latest, top
        for path in sorted(self.dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if row.get("v") == ROW_VERSION and not valid_row(row):
                        continue  # well-formed JSON but not a row: skipped, as rows() counts it
                    if row.get("v") != ROW_VERSION:
                        raise LegacyLedgerError(
                            f"{path} holds rows of schema v{row.get('v')}; this code writes v{ROW_VERSION}. "
                            "Move the old ledger aside and run `harvest --backfill` to rebuild it from the "
                            "stores and the archive."
                        )
                    ids.add(row["id"])
                    # A row without a sequence (hand-edited, or from a crash) is older
                    # than every sequenced row; ties break by id, never by month file.
                    seq = row.get("seq") if isinstance(row.get("seq"), int) else -1
                    top = max(top, seq)
                    prior = latest.get(row["o"])
                    if prior is None or (seq, row["id"]) > (prior[0], prior[3]):
                        latest[row["o"]] = (seq, fingerprint(row), (prior[2] + 1) if prior else 1, row["id"])
                    else:
                        latest[row["o"]] = (prior[0], prior[1], prior[2] + 1, prior[3])
        return ids, latest, top

    def check_schema(self) -> None:
        """Refuse a ledger directory that holds rows of another schema version, in any month."""
        self._scan()

    def write(self, rows: Iterable[dict]) -> Dict[str, int]:
        """Append each row unless its occurrence's latest stored revision already has its text.

        Every written row gets the next harvest sequence (``seq``), which is
        what the fold orders revisions by, independent of month files. An
        occurrence that returns to an earlier text (A, B, A) is a new row,
        identified by :func:`revision_identity`. Returns new-row counts per month.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        with exclusive_lock(self.dir, ".write.lock"):
            return self._write_locked(rows)

    def _write_locked(self, rows: Iterable[dict]) -> Dict[str, int]:
        ids, latest, seq = self._scan()
        pending: Dict[Path, List[str]] = {}
        added: Dict[str, int] = {}
        for row in rows:
            if not valid_row(row):
                continue  # what rows() would drop must never be appended, or every write re-appends it
            prior = latest.get(row["o"])
            # Unchanged means same text AND same attribution: a session found
            # later to be Paseo's moves its turns from human to agent.
            if prior is not None and prior[1] == fingerprint(row):
                continue  # unchanged since the last harvest
            n = prior[2] if prior else 0
            row = dict(row)
            if n and row["id"] in ids:
                row["id"] = revision_identity(row["o"], fingerprint(row), n)
            if row["id"] in ids:
                continue
            seq += 1
            row["seq"] = seq
            ids.add(row["id"])
            latest[row["o"]] = (seq, fingerprint(row), n + 1, row["id"])
            path = self._month_file(row["ts"])
            pending.setdefault(path, []).append(json.dumps(row, separators=(",", ":"), sort_keys=True))
            if len(pending[path]) >= 5000:
                self._flush(path, pending.pop(path))
            added[path.stem] = added.get(path.stem, 0) + 1
        for path, lines in pending.items():
            self._flush(path, lines)
        return added

    @staticmethod
    def _flush(path: Path, lines: List[str]) -> None:
        # An interrupted earlier write can leave a final line without its newline.
        # Appending straight after it would glue the first new row onto the torn
        # one and lose both; start on a fresh line instead. The torn line stays
        # as one malformed line, which ``rows()`` counts.
        torn = False
        if path.is_file() and path.stat().st_size:
            with path.open("rb") as handle:
                handle.seek(-1, os.SEEK_END)
                torn = handle.read(1) != b"\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(("\n" if torn else "") + "\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def rows(self, since: Optional[float] = None, until: Optional[float] = None) -> Iterator[dict]:
        self.legacy_rows = 0
        self.malformed_lines = 0
        if not self.dir.is_dir():
            return
        for path in sorted(self.dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        self.malformed_lines += 1
                        continue
                    if not isinstance(row, dict) or (row.get("v") == ROW_VERSION and not valid_row(row)):
                        self.malformed_lines += 1
                        continue
                    if row.get("v") != ROW_VERSION:
                        self.legacy_rows += 1
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
