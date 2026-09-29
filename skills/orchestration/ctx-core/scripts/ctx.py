#!/usr/bin/env python3
"""ctx: the shared context core, phase 1 (the read-only shared board).

The single writer and reader of a per-scope event log, plus its CLI. Every
Claude Code hook and every command goes through this module. It never writes
anything else.

    store      ~/.local/state/ctx/<scope-id>/events.jsonl   append-only, one
               JSON object per line (schema: references/event-schema.md)
    derived    ~/.local/state/ctx/<scope-id>/board.json     the log folded;
               maintained on every write, never edited by hand
    config     ~/.config/ctx/scopes.yaml                    scope id -> repos

A scope is resolved from the realpath of `git rev-parse --git-common-dir`, so
every worktree of a repo lands in the same scope as its main checkout. A repo
with no scope makes every command and every hook a silent no-op.

This is COORDINATION, not a security boundary. A session with Bash can write
the log directly. GitHub rulesets are the boundary; see SKILL.md.

board.json is updated under the lock by the writer that appends: it records
how many log bytes it has folded (`log_offset`), so a write folds only the new
bytes. `ctx board --rebuild` folds the whole log from scratch, and the two
paths give byte-identical boards. A hook never parses the whole log: the
SessionStart brief is rendered from the cached board.json.

Commands:
    ctx [-C DIR] board [--json] [--rebuild]
    ctx [-C DIR] doctor
    ctx doctor --unscoped [--days N]

Stdlib only, Python 3.9+. The hook entry is ctx_hook.py, beside this file.
Imports are kept cheap (no argparse, dataclasses, tempfile or typing on the
hook path): on a slow interpreter they were most of the 200 ms budget.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import zlib
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

TYPE_CHECKING = False
if TYPE_CHECKING:  # annotations only; `typing` is not imported at run time
    from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1

#: Event types phase 1 writes. A reader skips types it does not know, so later
#: phases can add types without breaking an older board.
EVENT_TYPES = ("session.start", "session.stop", "session.died")

#: The fcntl lock is tried non-blocking and retried until this much time has
#: passed. If it still isn't acquired, the append is skipped. A session is never
#: blocked on another session's write.
LOCK_BUDGET_S = 0.150
LOCK_RETRY_S = 0.005

#: The SessionStart brief is capped here (Claude Code's own cap is 10,000).
BRIEF_CAP = 4000

#: A session is shown as live when it has no died event and its last event is
#: this recent. Stop fires at the end of every turn, so a working session keeps
#: publishing.
LIVE_WINDOW_S = 6 * 3600

#: Bounds on what one event can carry.
MAX_STR = 400
MAX_LINE = 8192

#: A hook folds at most this many log bytes that board.json has not seen. Past
#: that, the board is left for the next writer or `ctx board --rebuild`, so a
#: hook's time never grows with the log.
FOLD_CAP = 64 * 1024
#: board.json's `log_tail` signs this many bytes before `log_offset`, so a log
#: that was replaced or truncated is detected rather than folded from a wrong
#: offset.
TAIL_BYTES = 64

SCOPE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
#: The last `ARC-STATUS: <WORD> ...` line of an assistant message. Markdown
#: emphasis or a quote marker in front of it is tolerated.
ARC_STATUS_RE = re.compile(r"^[ \t>*_`]*ARC-STATUS:[ \t]*([A-Z][A-Z0-9_-]*)\b[^\n]*$", re.M)


class ConfigError(ValueError):
    """scopes.yaml exists but cannot be used. Hooks treat this as no scope."""


# --------------------------------------------------------------------------
# Paths

def home() -> Path:
    return Path(os.environ.get("HOME") or os.path.expanduser("~"))


def config_path() -> Path:
    return home() / ".config" / "ctx" / "scopes.yaml"


def state_root() -> Path:
    return home() / ".local" / "state" / "ctx"


def now_ts(now: Optional[float] = None) -> str:
    t = time.time() if now is None else now
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (dt.microsecond // 1000)


def parse_ts(ts: str) -> float:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()


# --------------------------------------------------------------------------
# scopes.yaml: a deliberately tiny YAML subset, parsed with the stdlib so the
# hook needs no third-party import and behaves the same under `python3 -I`.
#
#   version: 1              # optional
#   scopes:
#     broomva:
#       - ~/broomva         # a repo root, or its .git directory
#       - ~/broomva/skills
#     sri:
#       - ~/broomva/work/stimulus/sri

def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def parse_scopes(text: str) -> Dict[str, List[str]]:
    """Parse scopes.yaml into {scope_id: [raw repo paths]}. Raises ConfigError."""
    scopes: Dict[str, List[str]] = {}
    in_scopes = False
    scope_indent: Optional[int] = None
    current: Optional[str] = None
    for n, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ConfigError("line %d: tabs are not allowed in indentation" % n)
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if indent == 0:
            current, scope_indent = None, None
            if body == "scopes:":
                in_scopes = True
            elif re.fullmatch(r"version:\s*1", body):
                in_scopes = False
            else:
                raise ConfigError("line %d: unknown top-level key %r" % (n, body))
            continue
        if not in_scopes:
            raise ConfigError("line %d: indented line outside `scopes:`" % n)
        if body.startswith("- ") or body == "-":
            if current is None or indent <= (scope_indent or 0):
                raise ConfigError("line %d: list item outside a scope" % n)
            value = _unquote(body[1:])
            if not value:
                raise ConfigError("line %d: empty repo path" % n)
            scopes[current].append(value)
            continue
        m = re.fullmatch(r"([^:\s]+):", body)
        if not m:
            raise ConfigError("line %d: expected `<scope-id>:` or `- <path>`" % n)
        if scope_indent is None:
            scope_indent = indent
        elif indent != scope_indent:
            raise ConfigError("line %d: inconsistent indentation" % n)
        sid = _unquote(m.group(1))
        if not SCOPE_ID_RE.match(sid):
            raise ConfigError("line %d: invalid scope id %r (lowercase, digits, - and _)" % (n, sid))
        if sid in scopes:
            raise ConfigError("line %d: scope %r defined twice" % (n, sid))
        scopes[sid] = []
        current = sid
    return scopes


def _entry_common_dir(raw: str) -> str:
    """A configured repo path, normalised to the realpath of its git common dir."""
    p = Path(os.path.expanduser(raw))
    if p.name != ".git" and (p / ".git").is_dir():
        p = p / ".git"
    return os.path.realpath(str(p))


def load_scopes() -> Dict[str, str]:
    """{realpath(git common dir): scope_id}. Empty when there is no config file.

    Raises ConfigError for an unreadable or ambiguous config. Callers that must
    stay silent (hooks, unscoped commands) treat that as no scope.
    """
    path = config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError("%s: %s" % (path, exc))
    mapping: Dict[str, str] = {}
    for sid, entries in parse_scopes(text).items():
        for raw in entries:
            key = _entry_common_dir(raw)
            other = mapping.get(key)
            if other and other != sid:
                raise ConfigError("%s is in two scopes: %s and %s" % (key, other, sid))
            mapping[key] = sid
    return mapping


# --------------------------------------------------------------------------
# Where a session is: one `git rev-parse`, bounded by the caller's deadline.

#: Where a session is: its cwd, the worktree top level, the realpath of the
#: git common dir (the scope key) and the branch (None when unborn/unknown).
Where = namedtuple("Where", "cwd toplevel common_dir branch")


_CHILD: Optional[subprocess.Popen] = None


def kill_child() -> None:
    """Called by the hook's deadline handler, so a hung git is not orphaned."""
    child = _CHILD
    if child is not None:
        try:
            child.kill()
        except Exception:
            pass


def _git(cwd: str, args: List[str], timeout: float) -> Optional[str]:
    global _CHILD
    if timeout <= 0:
        return None
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    try:
        proc = subprocess.Popen(
            ["git", "-C", cwd] + args,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env,
        )
    except OSError:
        return None
    _CHILD = proc
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return None
    finally:
        _CHILD = None
    if proc.returncode != 0:
        return None
    return out.decode("utf-8", "replace")


def _read_branch(git_dir: str) -> Optional[str]:
    try:
        head = Path(git_dir, "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if head.startswith("ref: refs/heads/"):
        return head[len("ref: refs/heads/"):]
    if re.fullmatch(r"[0-9a-f]{40,64}", head):
        return "detached@" + head[:12]
    return None


def locate(cwd: str, timeout: float = 0.5) -> Optional[Where]:
    out = _git(cwd, ["rev-parse", "--path-format=absolute",
                     "--git-common-dir", "--git-dir", "--show-toplevel"], timeout)
    if not out:
        return None
    lines = out.splitlines()
    if len(lines) != 3:
        return None
    common, git_dir, top = lines
    return Where(
        cwd=os.path.realpath(cwd),
        toplevel=os.path.realpath(top),
        common_dir=os.path.realpath(common),
        branch=_read_branch(git_dir),
    )


# --------------------------------------------------------------------------
# Exclusions and redaction. Applied to every event before it is written.

#: A path segment that makes a path secret-shaped.
_SECRET_SEGMENT = re.compile(
    r"^(?:\.env(?:\..+)?|.+\.(?:pem|key|p12|pfx|jks|keystore|kdbx|ovpn)"
    r"|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|\.netrc|\.npmrc|\.pypirc|\.pgpass"
    r"|\.ssh|\.aws|\.gnupg|\.docker|\.kube|credentials(?:\..+)?|secrets?(?:\..+)?"
    r"|.*keychain.*|.*\.secret(?:s)?(?:\..+)?)$",
    re.I,
)
_EXCLUDED_SEGMENT = re.compile(r"^crm$", re.I)


def excluded_path(path: str) -> bool:
    """True for a path under crm/ or with a secret-shaped segment."""
    for seg in re.split(r"[/\\]+", path):
        if seg and (_EXCLUDED_SEGMENT.match(seg) or _SECRET_SEGMENT.match(seg)):
            return True
    return False


_REDACTED = "[REDACTED]"
#: Every value pattern tries an existing marker first, so a second pass is a
#: no-op instead of eating the character after it.
_V = r"(?:\[REDACTED\]|"
_SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S),
     _REDACTED),
    (re.compile(r"(?i)\b(authorization|proxy-authorization|x-api-key|api-key|cookie|set-cookie)"
                r"(\s*[:=]\s*)(?:(?:bearer|basic|token|digest)\s+)?" + _V + r"[^\s,;\"'&]+)"),
     r"\1\2" + _REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{4,}"), "Bearer " + _REDACTED),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})"), _REDACTED),
    (re.compile(r"\bsk-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_-]{16,}"), _REDACTED),
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}"), _REDACTED),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{8,}"), _REDACTED),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), _REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), _REDACTED),
    (re.compile(r"\b(?:npm|lin_api|shpat|shpss|whsec|hf|dop_v1)_[A-Za-z0-9]{20,}"), _REDACTED),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), _REDACTED),
    (re.compile(r"\bpypi-[A-Za-z0-9_-]{40,}"), _REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}"), _REDACTED),
    # userinfo in a URL: scheme://user:secret@host
    (re.compile(r"(\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)[^@\s/]+@", re.I), r"\1" + _REDACTED + "@"),
    # URL query parameters that carry credentials
    (re.compile(r"(?i)([?&](?:access_token|token|api_key|apikey|key|secret|password|sig|signature|auth)=)" + _V + r"[^&\s#]+)"),
     r"\1" + _REDACTED),
    # key=value and key: value where the key names a secret
    (re.compile(r"(?i)\b((?:[a-z0-9]+[_.-])*(?:token|secret|passw(?:or)?d|pwd|passphrase|credentials?"
                r"|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|session[_-]?token|key))"
                r"([\"']?\s*[:=]\s*)" + _V + r"\"[^\"]*\"|'[^']*'|[^\s,;&\"']+)"),
     r"\1\2" + _REDACTED),
]
_PATH_TOKEN = re.compile(r"[^\s\"'<>()\[\]{},;`|]+")


def _redact_paths(s: str) -> str:
    def repl(m: re.Match) -> str:
        tok = m.group(0)
        looks_like_path = "/" in tok or "\\" in tok or tok.startswith((".", "~"))
        if looks_like_path and excluded_path(tok.rstrip(".:")):
            return "[excluded-path]"
        return tok
    return _PATH_TOKEN.sub(repl, s)


def redact_text(s: str) -> str:
    for pat, repl in _SECRET_PATTERNS:
        s = pat.sub(repl, s)
    return _redact_paths(s)


def _clip(s: str, cap: int = MAX_STR) -> str:
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", s)
    return s if len(s) <= cap else s[: cap - 1] + "…"


def redact(value: Any) -> Any:
    """Redact every string in a JSON-shaped value; keys are left alone.

    Redaction runs BEFORE the clip. Clipping first could cut a token in half
    and leave a prefix too short for any pattern to recognise. The pre-cap only
    bounds regex time: whatever it cuts lies far past the final clip.
    """
    if isinstance(value, str):
        return _clip(redact_text(value[: 8 * MAX_STR]))
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


# --------------------------------------------------------------------------
# Scope resolution

class Scope(namedtuple("Scope", "id store where")):
    """A resolved scope: its id, its store dir, and where the session is."""

    __slots__ = ()

    @property
    def log(self) -> Path:
        return self.store / "events.jsonl"

    @property
    def board_path(self) -> Path:
        return self.store / "board.json"

    @property
    def lock_path(self) -> Path:
        return self.store / "events.lock"


def resolve_scope(cwd: str, timeout: float = 0.5) -> Optional[Scope]:
    """The scope for a working directory, or None (the silent no-op).

    None when: there is no config or it is unusable, cwd is not in a git repo,
    the repo's common dir is not configured, or cwd is excluded (crm/ or a
    secret-shaped path).
    """
    try:
        mapping = load_scopes()
    except ConfigError:
        return None
    if not mapping:
        return None
    where = locate(cwd, timeout)
    if where is None:
        return None
    sid = mapping.get(where.common_dir)
    if sid is None:
        return None
    if excluded_path(where.cwd):
        return None
    return Scope(id=sid, store=state_root() / sid, where=where)


# --------------------------------------------------------------------------
# Events: build, append (the single writer), read

def make_event(etype: str, scope: Scope, session_id: str, payload: Dict[str, Any],
               now: Optional[float] = None) -> Dict[str, Any]:
    if etype not in EVENT_TYPES:
        raise ValueError("unknown event type %r" % etype)
    w = scope.where
    event: Dict[str, Any] = {
        "v": SCHEMA_VERSION,
        "type": etype,
        "ts": now_ts(now),
        "session_id": session_id,
        "cwd": w.cwd,
        "repo": w.common_dir,
        "branch": w.branch,
        "payload": payload,
    }
    agent = os.environ.get("PASEO_AGENT_ID")
    if agent:
        event["paseo_agent_id"] = agent
    return redact(event)


def _acquire(fd: int, budget: float) -> bool:
    deadline = time.monotonic() + max(0.0, min(budget, LOCK_BUDGET_S))
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                return False
        left = deadline - time.monotonic()
        if left <= 0:
            return False
        time.sleep(min(LOCK_RETRY_S, left))


def _pread_all(fd: int, size: int, offset: int) -> bytes:
    chunks, got = [], 0
    while got < size:
        chunk = os.pread(fd, size - got, offset + got)
        if not chunk:
            break
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def append(scope: Scope, event: Dict[str, Any], budget: float = LOCK_BUDGET_S,
           fold_cap: Optional[int] = FOLD_CAP) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Append one event under the lock, then fold the new log bytes into
    board.json under the same lock. Returns (written, board).

    written is False, and nothing is written, when the lock is not acquired
    within the budget or the event is not writable. board is None when
    board.json was not brought up to date (more than fold_cap unseen bytes).

    A writer killed mid-write can leave a line without its newline. The next
    append starts on a fresh line, so the damage is one skipped line, never a
    corrupted neighbour.
    """
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or excluded_path(cwd):
        return False, None
    line = (json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(line) > MAX_LINE:
        return False, None
    scope.store.mkdir(parents=True, exist_ok=True, mode=0o700)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    lock_fd = os.open(str(scope.lock_path), os.O_RDWR | os.O_CREAT | nofollow, 0o600)
    try:
        if not _acquire(lock_fd, budget):
            return False, None
        fd = os.open(str(scope.log), os.O_RDWR | os.O_APPEND | os.O_CREAT | nofollow, 0o600)
        try:
            size = os.fstat(fd).st_size
            if size and os.pread(fd, 1, size - 1) != b"\n":
                line = b"\n" + line
            view = memoryview(line)
            while view:
                view = view[os.write(fd, view):]
            return True, _sync_board(scope, fd, size + len(line), fold_cap)
        finally:
            os.close(fd)
    finally:
        os.close(lock_fd)


def read_log(scope: Scope) -> bytes:
    try:
        return scope.log.read_bytes()
    except FileNotFoundError:
        return b""


def _valid_event(ev: Any) -> bool:
    return (
        isinstance(ev, dict)
        and ev.get("v") == SCHEMA_VERSION
        and isinstance(ev.get("type"), str)
        and isinstance(ev.get("ts"), str) and bool(TS_RE.match(ev["ts"]))
        and isinstance(ev.get("session_id"), str) and bool(SESSION_ID_RE.match(ev["session_id"]))
        and isinstance(ev.get("payload"), dict)
    )


# --------------------------------------------------------------------------
# board.json: the log folded, in log order.
#
# The fold is the same function on both paths. `rebuild` folds every complete
# line from byte 0; a write folds only the lines after `log_offset`. Folding
# lines 0..k and then k..n is folding 0..n, so the incremental board and the
# full rebuild are byte-identical (a test pins this). Nothing reads a clock.
#
# "Latest" fields move only for an event whose ts is >= the row's, so two
# writers whose appends landed out of timestamp order still leave the true
# latest state. Counters are sums and do not depend on order.

_STATES = {"session.start": "started", "session.stop": "stopped", "session.died": "died"}


def _empty_board(scope_id: str) -> Dict[str, Any]:
    return {"v": SCHEMA_VERSION, "scope": scope_id, "events": 0, "skipped_lines": 0,
            "ignored_events": 0, "last_ts": None, "log_offset": 0, "log_tail": None,
            "sessions": {}}


def _tail_sig(tail: bytes) -> Optional[str]:
    # A consistency check against a replaced or truncated log, not a security
    # measure: crc32 is enough, and zlib is far cheaper to import than hashlib.
    return "%08x" % zlib.crc32(tail) if tail else None


def _apply(board: Dict[str, Any], ev: Dict[str, Any]) -> None:
    ts, sid, etype, p = ev["ts"], ev["session_id"], ev["type"], ev["payload"]
    row = board["sessions"].get(sid)
    if row is None:
        row = board["sessions"][sid] = {
            "session_id": sid, "first_ts": ts, "last_ts": ts, "last_event": None, "state": None,
            "cwd": None, "repo": None, "branch": None, "starts": 0, "stops": 0, "started_ts": None,
            "paseo_agent_id": None, "fleet_role": None, "arc_status": None, "arc_line": None,
            "arc_ts": None, "died_ts": None, "died_reason": None,
        }
    row["first_ts"] = min(row["first_ts"], ts)
    if row["last_event"] is None or ts >= row["last_ts"]:
        row.update(last_ts=ts, last_event=etype, state=_STATES[etype],
                   cwd=ev.get("cwd"), repo=ev.get("repo"), branch=ev.get("branch"))
        if ev.get("paseo_agent_id"):
            row["paseo_agent_id"] = ev["paseo_agent_id"]
    elif ev.get("paseo_agent_id") and not row["paseo_agent_id"]:
        row["paseo_agent_id"] = ev["paseo_agent_id"]
    if etype == "session.start":
        row["starts"] += 1
        if row["started_ts"] is None or ts >= row["started_ts"]:
            row["started_ts"] = ts
            if p.get("fleet_role"):
                row["fleet_role"] = p["fleet_role"]
    elif etype == "session.stop":
        row["stops"] += 1
    elif row["died_ts"] is None or ts >= row["died_ts"]:
        row["died_ts"] = ts
        row["died_reason"] = p.get("error_type") or "unknown"
    if p.get("arc_status") and (row["arc_ts"] is None or ts >= row["arc_ts"]):
        row.update(arc_status=p["arc_status"], arc_line=p.get("arc_line"), arc_ts=ts)
    if board["last_ts"] is None or ts > board["last_ts"]:
        board["last_ts"] = ts


def fold(board: Dict[str, Any], chunk: bytes, base_offset: int, prior: bytes = b"") -> None:
    """Fold the complete lines of `chunk` (the log from `base_offset` on) into
    `board`. `prior` is the log's bytes just before base_offset, for the tail
    signature. A trailing fragment with no newline is an append in progress or
    a torn write; it is left for the next fold."""
    end = chunk.rfind(b"\n") + 1
    if end == 0:
        return
    for raw in chunk[:end].split(b"\n")[:-1]:
        if not raw.strip():
            continue
        try:
            ev = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            board["skipped_lines"] += 1
            continue
        if not _valid_event(ev):
            board["skipped_lines"] += 1
            continue
        if ev["type"] not in EVENT_TYPES:
            board["ignored_events"] += 1
            continue
        board["events"] += 1
        _apply(board, ev)
    board["log_offset"] = base_offset + end
    board["log_tail"] = _tail_sig((prior + chunk[:end])[-TAIL_BYTES:])


def rebuild(scope_id: str, data: bytes) -> Dict[str, Any]:
    """The pure full rebuild: every complete line of the log, from byte 0."""
    board = _empty_board(scope_id)
    fold(board, data, 0)
    return board


def board_bytes(board: Dict[str, Any]) -> bytes:
    return (json.dumps(board, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _valid_board(board: Any, scope_id: str) -> bool:
    return (
        isinstance(board, dict) and board.get("v") == SCHEMA_VERSION and board.get("scope") == scope_id
        and isinstance(board.get("sessions"), dict)
        and all(isinstance(board.get(k), int) and board[k] >= 0
                for k in ("log_offset", "events", "skipped_lines", "ignored_events"))
        and all(isinstance(r, dict) and isinstance(r.get("last_ts"), str) for r in board["sessions"].values())
    )


def load_board(scope: Scope) -> Optional[Dict[str, Any]]:
    """The cached board.json, or None when it is missing or malformed. This is
    what SessionStart reads; it never parses the log."""
    try:
        board = json.loads(scope.board_path.read_bytes().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return board if _valid_board(board, scope.id) else None


def write_board(scope: Scope, board: Dict[str, Any]) -> bool:
    """Atomically replace board.json when its bytes differ. True if written."""
    data = board_bytes(board)
    try:
        if scope.board_path.read_bytes() == data:
            return False
    except OSError:
        pass
    scope.store.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = str(scope.store / (".board.%d.%d.tmp" % (os.getpid(), time.monotonic_ns())))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, str(scope.board_path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def _sync_board(scope: Scope, fd: int, size: int, cap: Optional[int]) -> Optional[Dict[str, Any]]:
    """Bring board.json up to `size` log bytes. Call with the lock held.

    Folds only the bytes after the cached board's log_offset, when its tail
    signature still matches the log. Otherwise (no board, a malformed one, or a
    log that was replaced) it folds from byte 0. Either way it reads at most
    `cap` bytes; past that it returns None and leaves board.json alone.
    """
    board = load_board(scope)
    if board is not None:
        off = board["log_offset"]
        if off <= size:
            n = min(TAIL_BYTES, off)
            prior = _pread_all(fd, n, off - n)
            if _tail_sig(prior) == board.get("log_tail"):
                if cap is not None and size - off > cap:
                    return None
                fold(board, _pread_all(fd, size - off, off), off, prior)
                write_board(scope, board)
                return board
    if cap is not None and size > cap:
        return None
    board = rebuild(scope.id, _pread_all(fd, size, 0))
    write_board(scope, board)
    return board


def sync_board(scope: Scope, full: bool = False, wait: float = 2.0) -> Tuple[Optional[Dict[str, Any]], bool]:
    """CLI path: bring board.json up to date with no size cap (`full` refolds the
    whole log). Returns (board, matched): matched is whether the cached
    board.json already equalled the result."""
    before = None
    try:
        before = scope.board_path.read_bytes()
    except OSError:
        pass
    if not scope.log.exists():
        board = rebuild(scope.id, b"")
        return board, before == board_bytes(board)
    lock_fd = os.open(str(scope.lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + wait
        while not _acquire(lock_fd, LOCK_BUDGET_S):
            if time.monotonic() >= deadline:
                return load_board(scope), False
        fd = os.open(str(scope.log), os.O_RDONLY)
        try:
            size = os.fstat(fd).st_size
            if full:
                board = rebuild(scope.id, _pread_all(fd, size, 0))
                matched = before == board_bytes(board)
                write_board(scope, board)
            else:
                board = _sync_board(scope, fd, size, None)
                matched = before == board_bytes(board) if board else False
            return board, matched
        finally:
            os.close(fd)
    finally:
        os.close(lock_fd)


# --------------------------------------------------------------------------
# Rendering. Every sentence is a statement of fact from the store. The spike
# (2026-09-29) found models treat imperative hook text as prompt injection, so
# nothing here tells the reader to do anything.

def _age(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % (s // 60)
    if s < 172800:
        return "%dh" % (s // 3600)
    return "%dd" % (s // 86400)


def _short(sid: Optional[str]) -> str:
    return (sid or "-")[:8]


def _tilde(path: Optional[str]) -> str:
    if not path:
        return "-"
    h = str(home())
    return "~" + path[len(h):] if path == h or path.startswith(h + "/") else path


def is_live(row: Dict[str, Any], now: float) -> bool:
    if row.get("state") == "died":
        return False
    try:
        return now - parse_ts(row["last_ts"]) <= LIVE_WINDOW_S
    except (KeyError, TypeError, ValueError):
        return False


def _row_sentence(row: Dict[str, Any], now: float) -> str:
    bits = ["session %s" % _short(row["session_id"])]
    if row.get("paseo_agent_id"):
        bits.append("Paseo agent %s" % _short(row["paseo_agent_id"]))
    if row.get("fleet_role"):
        bits.append("role %s" % row["fleet_role"])
    bits.append("branch %s" % (row.get("branch") or "-"))
    bits.append("cwd %s" % _tilde(row.get("cwd")))
    bits.append("last event %s ago (%s)" % (_age(now - parse_ts(row["last_ts"])), row.get("last_event")))
    if row.get("state") == "died":
        bits.append("died: %s" % row.get("died_reason"))
    if row.get("arc_line"):
        bits.append("status line, quoted: %s" % json.dumps(_clip(row["arc_line"], 200), ensure_ascii=False))
    return "- " + ", ".join(bits) + "."


def render_brief(board: Dict[str, Any], me: Where, session_id: str, now: float,
                 cap: int = BRIEF_CAP) -> str:
    """The SessionStart brief: board rows for this branch and this cwd, with the
    other live sessions on the same branch first. Empty when there are none."""
    others = [r for r in board.get("sessions", {}).values() if r["session_id"] != session_id]
    same_branch = [r for r in others
                   if me.branch and r.get("repo") == me.common_dir and r.get("branch") == me.branch]
    same_cwd = [r for r in others if r.get("cwd") == me.cwd and r not in same_branch]
    live = [r for r in same_branch if is_live(r, now)]
    rest = [r for r in same_branch if r not in live] + same_cwd
    if not live and not rest:
        return ""
    newest_first = lambda rs: sorted(rs, key=lambda r: (r["last_ts"], r["session_id"]), reverse=True)
    head = [
        "Shared board facts (ctx scope %s, %d events, last event %s). These rows were "
        "recorded by hooks in other sessions of this scope; quoted status lines are "
        "those sessions' own words, reproduced as data." % (
            board.get("scope"), board.get("events", 0), board.get("last_ts") or "-"),
        "This session: %s, branch %s, cwd %s." % (_short(session_id), me.branch or "-", _tilde(me.cwd)),
    ]
    body: List[str] = []
    if live:
        body.append("Other live sessions on branch %s in this repo (live: no died event, "
                    "an event in the last %dh): %d." % (me.branch, LIVE_WINDOW_S // 3600, len(live)))
        body += [_row_sentence(r, now) for r in newest_first(live)]
    if rest:
        body.append("Other board rows for this branch or this cwd: %d." % len(rest))
        body += [_row_sentence(r, now) for r in newest_first(rest)]
    out = "\n".join(head)
    shown = 0
    rows_total = len(live) + len(rest)
    for i, line in enumerate(body):
        omitted = rows_total - shown
        tail = "\n%d more rows are omitted here; the full board is %s." % (
            omitted, _tilde(str(state_root() / str(board.get("scope")) / "board.json")))
        if len(out) + 1 + len(line) + len(tail) > cap:
            if omitted > 0:
                out += tail
            break
        out += "\n" + line
        if line.startswith("- "):
            shown += 1
    return out[:cap]


def render_table(board: Dict[str, Any], now: float) -> str:
    rows = sorted(board.get("sessions", {}).values(), key=lambda r: (r["last_ts"], r["session_id"]), reverse=True)
    lines = ["scope %s: %d sessions, %d events, %d skipped lines, last event %s" % (
        board.get("scope"), len(rows), board.get("events", 0), board.get("skipped_lines", 0),
        board.get("last_ts") or "-")]
    if not rows:
        return lines[0]
    hdr = ("SESSION", "AGENT", "STATE", "LIVE", "LAST", "BRANCH", "STATUS", "CWD")
    table = [hdr]
    for r in rows:
        table.append((
            _short(r["session_id"]), _short(r.get("paseo_agent_id")), r.get("state") or "-",
            "yes" if is_live(r, now) else "no", _age(now - parse_ts(r["last_ts"])),
            _clip(r.get("branch") or "-", 40), r.get("arc_status") or "-", _tilde(r.get("cwd")),
        ))
    widths = [max(len(str(row[i])) for row in table) for i in range(len(hdr) - 1)]
    for row in table:
        lines.append("  ".join(str(c).ljust(w) for c, w in zip(row, widths)) + "  " + str(row[-1]))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Hooks. ctx_hook.py wraps this with the deadline, the output guard and exit 0.

def _extract_arc(message: Any) -> Dict[str, str]:
    if not isinstance(message, str) or "ARC-STATUS:" not in message:
        return {}
    found = list(ARC_STATUS_RE.finditer(message))
    if not found:
        return {}
    m = found[-1]
    # Not clipped here: make_event redacts first, then clips.
    return {"arc_status": m.group(1), "arc_line": m.group(0).strip().strip("*_`> \t")}


def run_hook(event: str, raw: str, deadline: float, now: Optional[float] = None) -> str:
    """Handle one hook event. Returns the text for stdout ("" for none).

    `deadline` is a time.monotonic() value. Work that cannot finish before it
    is skipped; the wrapper's alarm is the backstop.
    """
    data = json.loads(raw) if raw.strip() else None
    if not isinstance(data, dict):
        return ""
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        return ""
    cwd = data.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        return ""
    left = lambda: deadline - time.monotonic()
    # git gets what the budget has left, less a margin for the append; with the
    # registered 120 ms budget that is roughly 70 ms.
    scope = resolve_scope(cwd, timeout=left() - 0.03)
    if scope is None or left() <= 0.02:
        return ""

    if event == "session-start":
        payload: Dict[str, Any] = {}
        for key in ("source", "model", "agent_type"):
            if isinstance(data.get(key), str):
                payload[key] = data[key]
        role = os.environ.get("FLEET_ROLE")
        if role:
            payload["fleet_role"] = role
        _, board = append(scope, make_event("session.start", scope, session_id, payload, now),
                          budget=min(LOCK_BUDGET_S, left() - 0.02))
        if board is None:
            board = load_board(scope)  # the cached board; the log is never parsed here
        if board is None or left() <= 0.01:
            return ""
        brief = render_brief(board, scope.where, session_id, time.time() if now is None else now)
        if not brief:
            return ""
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                  "additionalContext": brief}}, ensure_ascii=False)

    if event == "stop":
        payload = _extract_arc(data.get("last_assistant_message"))
        append(scope, make_event("session.stop", scope, session_id, payload, now),
               budget=min(LOCK_BUDGET_S, left() - 0.02))
        return ""

    if event == "stop-failure":
        payload = {"error_type": data.get("error_type") if isinstance(data.get("error_type"), str) else "unknown"}
        if isinstance(data.get("error"), str):
            payload["error"] = data["error"]
        payload.update(_extract_arc(data.get("last_assistant_message")))
        append(scope, make_event("session.died", scope, session_id, payload, now),
               budget=min(LOCK_BUDGET_S, left() - 0.02))
        return ""

    return ""


# --------------------------------------------------------------------------
# Doctor

def _lock_state(scope: Scope) -> str:
    try:
        fd = os.open(str(scope.lock_path), os.O_RDWR)
    except FileNotFoundError:
        return "absent (no append yet)"
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return "held by another process right now"
        fcntl.flock(fd, fcntl.LOCK_UN)
        return "free"
    finally:
        os.close(fd)


def doctor_scoped(scope: Scope, now: float) -> Tuple[List[str], int]:
    out = ["scope %s" % scope.id,
           "  repo      %s (branch %s)" % (scope.where.common_dir, scope.where.branch or "-"),
           "  config    %s" % config_path(),
           "  store     %s" % scope.store]
    problems = 0
    data = read_log(scope)
    lines = data.split(b"\n")[:-1]
    board = rebuild(scope.id, data)
    out.append("  log       %d bytes, %d events, %d skipped lines, %d ignored events"
               % (len(data), board["events"], board["skipped_lines"], board["ignored_events"]))
    out.append("  lock      %s" % _lock_state(scope))
    try:
        on_disk = scope.board_path.read_bytes()
        out.append("  board     %d bytes, %d sessions (no retention in phase 1; SessionStart parses this file)"
                   % (len(on_disk), len(board["sessions"])))
        if on_disk == board_bytes(board):
            out.append("  board     equals a full rebuild of the log")
        else:
            cached = load_board(scope)
            behind = (cached is not None and cached["log_offset"] < board["log_offset"])
            out.append("  board     %s" % ("behind the log by %d bytes (caught up by the next write or `ctx board`)"
                                           % (board["log_offset"] - cached["log_offset"]) if behind else
                                           "WARN: differs from a full rebuild (`ctx board --rebuild` replaces it)"))
            problems += 0 if behind else 1
    except FileNotFoundError:
        out.append("  board     not built yet")
    stray = sorted(p.name for p in scope.store.glob(".board.*.tmp")) if scope.store.exists() else []
    if stray:
        out.append("  WARN      %d stray board temp files: %s" % (len(stray), ", ".join(stray[:3])))
    # The BRO-2019 failure: a hook that silently stopped firing.
    last: Dict[str, str] = {}
    for raw in lines:
        try:
            ev = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if _valid_event(ev) and ev["type"] in EVENT_TYPES and ev["ts"] > last.get(ev["type"], ""):
            last[ev["type"]] = ev["ts"]
    for etype, hook in (("session.start", "SessionStart"), ("session.stop", "Stop"),
                        ("session.died", "StopFailure")):
        ts = last.get(etype)
        if ts is None:
            note = "never fired" + ("" if etype == "session.died" else " (hooks not registered?)")
            if etype != "session.died":
                problems += 1
            out.append("  %-12s %s" % (hook, note))
        else:
            age = now - parse_ts(ts)
            stale = age > 24 * 3600 and etype != "session.died"
            problems += 1 if stale else 0
            out.append("  %-12s last event %s ago%s" % (hook, _age(age), " (WARN: none in 24h)" if stale else ""))
    return out, problems


def _claude_projects_dir() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else home() / ".claude") / "projects"


def _transcript_cwd(path: Path) -> Optional[str]:
    try:
        with path.open("rb") as fh:
            for i, raw in enumerate(fh):
                if i >= 64:
                    break
                if b'"cwd"' not in raw:
                    continue
                try:
                    cwd = json.loads(raw.decode("utf-8")).get("cwd")
                except (ValueError, UnicodeDecodeError, AttributeError):
                    continue
                if isinstance(cwd, str) and cwd:
                    return cwd
    except OSError:
        return None
    return None


def doctor_unscoped(days: float, now: float) -> Tuple[List[str], int]:
    """Repos that have Claude Code sessions in the window but no scope."""
    out: List[str] = []
    problems = 0
    try:
        mapping = load_scopes()
        n_scopes = len(set(mapping.values()))
        out.append("config    %s: %s" % (config_path(), "%d scopes, %d repos" % (n_scopes, len(mapping))
                                          if mapping else "absent or empty (every repo is unscoped)"))
    except ConfigError as exc:
        mapping = {}
        problems += 1
        out.append("config    %s: ERROR %s (every repo is unscoped until fixed)" % (config_path(), exc))
    root = _claude_projects_dir()
    cutoff = now - days * 86400
    by_repo: Dict[str, Dict[str, Any]] = {}
    gone = outside = 0
    try:
        project_dirs = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        project_dirs = []
    for pdir in project_dirs:
        recent = []
        for t in pdir.glob("*.jsonl"):
            try:
                mt = t.stat().st_mtime
            except OSError:
                continue
            if mt >= cutoff:
                recent.append((mt, t))
        if not recent:
            continue
        recent.sort(reverse=True)
        cwd = None
        for _, t in recent[:3]:
            cwd = _transcript_cwd(t)
            if cwd:
                break
        if not cwd:
            continue
        if not os.path.isdir(cwd):
            gone += len(recent)
            continue
        where = locate(cwd, timeout=2.0)
        if where is None:
            outside += len(recent)
            continue
        if where.common_dir in mapping:
            continue
        slot = by_repo.setdefault(where.common_dir, {"sessions": 0, "last": 0.0, "cwds": set()})
        slot["sessions"] += len(recent)
        slot["last"] = max(slot["last"], recent[0][0])
        slot["cwds"].add(cwd)
    out.append("sessions  Claude Code transcripts under %s, last %g days" % (_tilde(str(root)), days))
    if by_repo:
        out.append("unscoped repos with sessions: %d" % len(by_repo))
        for repo, slot in sorted(by_repo.items(), key=lambda kv: (-kv[1]["sessions"], kv[0])):
            out.append("  %-60s %4d sessions, last %s ago, %d cwds" % (
                _tilde(repo), slot["sessions"], _age(now - slot["last"]), len(slot["cwds"])))
    else:
        out.append("unscoped repos with sessions: 0")
    out.append("  (%d sessions in a cwd that no longer exists; %d outside any git repo)" % (gone, outside))
    return out, problems


# --------------------------------------------------------------------------
# CLI

def main(argv: Optional[List[str]] = None) -> int:
    import argparse  # CLI only; never imported on the hook path

    ap = argparse.ArgumentParser(prog="ctx", description=__doc__.split("\n\n")[0])
    ap.add_argument("-C", dest="directory", default=None, help="run as if started in DIR")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("board", help="bring board.json up to date with the log and print it")
    b.add_argument("--json", action="store_true", help="print board.json itself")
    b.add_argument("--rebuild", action="store_true",
                   help="fold the whole log from scratch and replace board.json")
    d = sub.add_parser("doctor", help="health of this scope's store and hooks")
    d.add_argument("--unscoped", action="store_true",
                   help="list repos that have sessions but no scope (works from any directory)")
    d.add_argument("--days", type=float, default=14.0, help="session window for --unscoped (default 14)")
    args = ap.parse_args(argv)
    cwd = os.path.realpath(args.directory or os.getcwd())
    now = time.time()

    if args.cmd == "doctor" and args.unscoped:
        lines, problems = doctor_unscoped(args.days, now)
        print("\n".join(lines))
        return 1 if problems else 0

    scope = resolve_scope(cwd)
    if scope is None:
        return 0  # no scope: every command is a silent no-op

    if args.cmd == "board":
        board, matched = sync_board(scope, full=args.rebuild)
        if board is None:
            print("ctx: the log lock stayed busy; board.json was not updated", file=sys.stderr)
            return 1
        if args.rebuild and not args.json:
            print("rebuilt from the log; the cached board.json %s" % (
                "was identical" if matched else "differed and was replaced"))
        if args.json:
            sys.stdout.write(board_bytes(board).decode("utf-8"))
        else:
            print(render_table(board, now))
        return 0

    lines, problems = doctor_scoped(scope, now)
    print("\n".join(lines))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
