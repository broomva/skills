"""Shared plumbing for the case stubs: where the case lives, its config, its log.

Every stub runs as ``python3 -I <stub>.py`` from a wrapper the harness writes into
the case's ``~/.local/bin``, and the wrapper sets ``CTXABL_CASE_ROOT``. A stub with
no case root refuses to run: a ``gh`` stub that fell through to defaults outside a
case would be indistinguishable from the real thing to whoever called it.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def case_root() -> Path:
    raw = os.environ.get("CTXABL_CASE_ROOT", "")
    if not raw:
        sys.stderr.write("eval stub: CTXABL_CASE_ROOT is not set; refusing to run\n")
        sys.exit(97)
    return Path(raw)


def config(name: str) -> dict[str, Any]:
    path = case_root() / "stubs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    section = data.get(name) if isinstance(data, dict) else None
    return section if isinstance(section, dict) else {}


def log(name: str, record: dict[str, Any]) -> None:
    """Append one line to ``<case>/stub-logs/<name>.jsonl``. The graders read it."""
    logs = case_root() / "stub-logs"
    logs.mkdir(parents=True, exist_ok=True)
    record = {"ts": round(time.time(), 3), "cwd": os.getcwd(), **record}
    with open(logs / f"{name}.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def state_path(name: str) -> Path:
    d = case_root() / "stub-state"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.json"


def load_state(name: str) -> dict[str, Any]:
    try:
        data = json.loads(state_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(name: str, data: dict[str, Any]) -> None:
    state_path(name).write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
