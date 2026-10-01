"""Time, paths, the text guard and atomic writes, shared by every module."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import ctx  # ctx-core, from the same checkout (fleet_reconcile.py puts it on sys.path)

SCHEMA_VERSION = 1


def home() -> Path:
    return ctx.home()


def expand(path: str) -> Path:
    """`~` against $HOME, which tests point at a scratch directory."""
    if path == "~" or path.startswith("~/"):
        return home() / path[2:]
    return Path(path)


def tilde(path: Any) -> str:
    if not isinstance(path, str) or not path:
        return "-"
    h = str(home())
    return "~" + path[len(h):] if path == h or path.startswith(h + "/") else path


def ts(t: float) -> str:
    """UTC YYYY-MM-DDTHH:MM:SS.mmmZ, the ledger's and the core's format."""
    return ctx.now_ts(t)


def parse_iso(value: Any) -> Optional[float]:
    """Epoch seconds from the ISO shapes the surfaces use (a trailing Z, an
    offset, 0-6 fraction digits), or None."""
    if not isinstance(value, str) or not value:
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?([+-]\d{2}:\d{2})?", s)
    if not m:
        return None
    frac = (m.group(2) or "")[:6].ljust(6, "0")
    try:
        d = _dt.datetime.fromisoformat(m.group(1) + "." + frac + (m.group(3) or "+00:00"))
    except ValueError:
        return None
    return d.timestamp()


def age(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    s = max(0, int(seconds))
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % (s // 60)
    if s < 172800:
        return "%dh" % (s // 3600)
    return "%dd" % (s // 86400)


# --------------------------------------------------------------------------
# The text guard. Session names, job details and PR titles are other sessions'
# words. They reach a report only flattened to one line, clipped, and through
# the core's guard (credential-shaped tokens, crm/ paths); what fails the guard
# is withheld, not truncated.

WITHHELD = "[withheld]"
_FLAT = {c: " " for c in list(range(0x20)) + list(range(0x7F, 0xA0)) + [0x2028, 0x2029]}
_CRM = re.compile(r"(?:^|[^A-Za-z0-9])crm(?:/|$)", re.IGNORECASE)


def safe_text(value: Any, cap: int = 80) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    flat = " ".join(value.translate(_FLAT).split())
    if not ctx.guard_ok(flat) or _CRM.search(flat):
        return WITHHELD
    return flat if len(flat) <= cap else flat[: cap - 1] + "…"


def safe_path(value: Any) -> Optional[str]:
    """A path, or None when it is a crm/ path or credential-shaped."""
    if not isinstance(value, str) or not value:
        return None
    flat = value.translate(_FLAT)
    if flat != value or not ctx.guard_ok(value + "/") or _CRM.search(value):
        return None
    return value


# --------------------------------------------------------------------------
# Files

def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def write_atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    ensure_dir(path.parent)
    tmp = path.parent / (".%s.%d.%d.tmp" % (path.name, os.getpid(), time.monotonic_ns()))
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))


def write_json(path: Path, obj: Any) -> None:
    write_atomic(path, (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


def read_tail(path: Path, max_bytes: int = 256 * 1024) -> bytes:
    """The last `max_bytes` of a file, from the start of a whole line (one it
    starts exactly on included)."""
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        start = max(0, size - max_bytes)
        fh.seek(max(0, start - 1))  # one byte early: a newline there means the window starts a line
        data = fh.read()
    if start:
        cut = data.find(b"\n")
        data = data[cut + 1:] if cut != -1 else b""
    return data
