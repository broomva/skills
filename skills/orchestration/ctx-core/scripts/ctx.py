#!/usr/bin/env python3
"""ctx: the shared context core, phase 1 (the read-only shared board).

The single writer and reader of a per-scope event log, plus its CLI. Every
Claude Code hook and every command goes through this module.

    store      ~/.local/state/ctx/<scope-id>/events.jsonl   append-only, one
               JSON object per line (schema: references/event-schema.md)
    derived    ~/.local/state/ctx/<scope-id>/board.json     the log folded;
               maintained on every write, never edited by hand
    config     ~/.config/ctx/scopes.yaml                    scope id -> repos

A scope is keyed by the realpath of the repo's git common dir, so every
worktree of a repo lands in the same scope as its main checkout. A repo with no
scope makes every command and every hook a silent no-op.

This is COORDINATION, not a security boundary. A session with Bash can write
the log directly. GitHub rulesets are the boundary; see SKILL.md.

board.json records how many log bytes it has folded (`log_offset`), so the
writer that appends folds only the new bytes, under the same lock. `ctx board
--rebuild` folds the log from scratch, and the two paths give byte-identical
boards. A hook never parses the whole log, and the SessionStart
brief is rendered from the cached board.json.

Commands:
    ctx [-C DIR] board [--json] [--rebuild]
    ctx [-C DIR] doctor
    ctx doctor --unscoped [--days N]

Stdlib only, Python 3.9+. The hook entry is ctx_hook.py, beside this file.
Imports on the hook path are kept cheap: no argparse, subprocess, datetime,
dataclasses, tempfile or typing. On a loaded machine the imports alone were
most of the 200 ms budget.

No retention in phase 1: the log and board.json only grow. Retention and
compaction are phase 2 of the design (broomva/workspace#825, round 7).
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import sys
import time
import zlib
from collections import namedtuple
from pathlib import Path

TYPE_CHECKING = False
if TYPE_CHECKING:  # annotations only; `typing` is not imported at run time
    from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1

#: Event types phase 1 writes. A reader skips types it does not know, so later
#: phases can add types without breaking an older board.
EVENT_TYPES = ("session.start", "session.stop", "session.died")

#: The fcntl lock is tried non-blocking and retried until this much time has
#: passed; then the append is skipped. A session is never blocked on another
#: session's write. Hooks wait less: an append holds the lock for a few ms, and
#: the rest of the hook's 80 ms is needed for the fold and the brief.
LOCK_BUDGET_S = 0.150
HOOK_LOCK_BUDGET_S = 0.040
LOCK_RETRY_S = 0.005

#: The SessionStart brief is capped here (Claude Code's own cap is 10,000).
BRIEF_CAP = 4000

#: Live: no died event, and an event this recent. Stop fires at the end of
#: every turn, so a working session keeps publishing. This is also the window
#: of the phase-1 exit comparator (live rows vs Paseo agents whose transcript
#: moved in the last 6 h). Rows that are not live appear in the brief only if
#: they are RECENT_WINDOW_S recent.
LIVE_WINDOW_S = 6 * 3600
RECENT_WINDOW_S = 48 * 3600

#: Bounds on what one event can carry.
MAX_STR = 400
MAX_LINE = 8192

#: A hook does not parse a board.json bigger than this. json.loads/dumps are C
#: calls the deadline alarm cannot interrupt, so this is what makes the hook's
#: deadline hard: 2 MiB is about 3,000 sessions and ~15 ms of parse + dump. With
#: no retention in phase 1 the board grows past it in time; hooks then skip the
#: fold and the brief (recorded as a miss), and `ctx doctor` reports it.
HOOK_BOARD_CAP = 2 * 1024 * 1024
#: The pre-cap bounds regex time on a long string before redaction.
PRECAP = 8 * MAX_STR

#: A hook folds at most this many log bytes that board.json has not seen. Past
#: that it leaves the board alone (its time must not grow with the log); `ctx
#: board` and `ctx board --rebuild` catch it up, and `ctx doctor` reports the
#: lag as a problem.
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

#: Where the running hook is, for the deadline-miss record ctx_hook.py writes.
STAGE = "loaded"
#: Set by run_hook when it finished in time but skipped work (a busy lock, a
#: board over its cap): ctx_hook.py records it as a miss too.
MISSED: Optional[str] = None


class ConfigError(ValueError):
    """scopes.yaml exists but cannot be parsed or read. Hooks treat this as no
    scope; `ctx doctor` reports it from any directory."""


# --------------------------------------------------------------------------
# Paths and time

def home() -> Path:
    return Path(os.environ.get("HOME") or os.path.expanduser("~"))


def config_path() -> Path:
    return home() / ".config" / "ctx" / "scopes.yaml"


def state_root() -> Path:
    return home() / ".local" / "state" / "ctx"


def misses_path() -> Path:
    return state_root() / "hook-misses.jsonl"


def now_ts(now: Optional[float] = None) -> str:
    t = time.time() if now is None else now
    whole = int(t)
    ms = min(999, int((t - whole) * 1000))
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(whole)) + ".%03dZ" % ms


def _days_from_civil(y: int, m: int, d: int) -> int:
    # H. Hinnant's algorithm; avoids importing datetime, whose strptime alone
    # cost 200 ms on a loaded machine.
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def parse_ts(ts: str) -> float:
    return (_days_from_civil(int(ts[0:4]), int(ts[5:7]), int(ts[8:10])) * 86400
            + int(ts[11:13]) * 3600 + int(ts[14:16]) * 60 + int(ts[17:19]) + int(ts[20:23]) / 1000.0)


# --------------------------------------------------------------------------
# scopes.yaml: a strict subset of YAML, parsed with the stdlib so the hook
# needs no third-party import and behaves the same under `python3 -I`. Every
# rejection is reported by `ctx doctor`, from any directory.
#
#   version: 1              # optional
#   scopes:
#     broomva:
#       - ~/broomva         # a repo root, or its .git
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


def _gitdir_from_file(dotgit: str) -> Optional[str]:
    """The target of a `.git` FILE (a linked worktree or a submodule)."""
    try:
        with open(dotgit, encoding="utf-8") as fh:
            text = fh.read(4096).strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("gitdir:"):
        return None
    return os.path.normpath(os.path.join(os.path.dirname(dotgit), text[len("gitdir:"):].strip()))


def _common_of(gitdir: str) -> str:
    """A git dir's common dir: its `commondir` file if it has one (a linked
    worktree), else itself. The same rule `git rev-parse --git-common-dir` uses."""
    try:
        with open(os.path.join(gitdir, "commondir"), encoding="utf-8") as fh:
            rel = fh.read(4096).strip()
    except (OSError, UnicodeDecodeError):
        return os.path.realpath(gitdir)
    return os.path.realpath(os.path.join(gitdir, rel))


def _entry_common_dir(raw: str) -> str:
    """A configured repo path, normalised to the realpath of its git common dir.
    A worktree or submodule path is followed through its `.git` file."""
    p = os.path.expanduser(raw)
    if os.path.basename(os.path.normpath(p)) == ".git" and os.path.isdir(p):
        return _common_of(p)
    dotgit = os.path.join(p, ".git")
    if os.path.isdir(dotgit):
        return _common_of(dotgit)
    if os.path.isfile(dotgit):
        target = _gitdir_from_file(dotgit)
        if target:
            return _common_of(target)
    return os.path.realpath(p)


#: Scopes: {realpath(common dir): scope id}, with None for a repo listed in two
#: scopes. An ambiguous repo has no scope; the other repos are unaffected.
Scopes = namedtuple("Scopes", "by_repo ambiguous")


def load_scopes() -> Scopes:
    """Empty when there is no config file. Raises ConfigError when the file
    exists and cannot be read or parsed."""
    path = config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Scopes({}, {})
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError("%s: %s" % (path, exc))
    by_repo: Dict[str, Optional[str]] = {}
    ambiguous: Dict[str, List[str]] = {}
    for sid, entries in parse_scopes(text).items():
        for raw in entries:
            key = _entry_common_dir(raw)
            if key in by_repo and by_repo.get(key) != sid:
                ambiguous.setdefault(key, [s for s in [by_repo[key]] if s]).append(sid)
                by_repo[key] = None
            elif key not in by_repo:
                by_repo[key] = sid
    return Scopes(by_repo, ambiguous)


# --------------------------------------------------------------------------
# Where a session is. Read from the filesystem the way git does, so a hook
# spawns no process and imports no subprocess. git itself is used only when
# GIT_DIR / GIT_WORK_TREE / GIT_COMMON_DIR redirect it, or for a reftable
# repo's branch. A test checks this resolver agrees with `git rev-parse` on
# every layout it handles.

#: Where a session is: its cwd, the worktree top level, the realpath of the
#: git common dir (the scope key) and the branch (None when unknown).
Where = namedtuple("Where", "cwd toplevel common_dir branch")

_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")
_CHILD = None
_TMP: Optional[str] = None


def on_deadline() -> None:
    """Called by the hook's deadline handler before os._exit: a hung git is
    killed rather than orphaned, and a half-written board temp file removed."""
    child, tmp = _CHILD, _TMP
    if child is not None:
        try:
            child.kill()
        except Exception:
            pass
    if tmp:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _git(cwd: str, args: List[str], timeout: float) -> Optional[str]:
    global _CHILD
    if timeout <= 0:
        return None
    import subprocess  # the fallback path only

    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    try:
        proc = subprocess.Popen(["git", "-C", cwd] + args, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
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


_REFNAME = re.compile(r"[^\x00-\x20\x7f~^:?*\[\\]{1,200}")


def _read_branch(git_dir: str, toplevel: str, timeout: float) -> Optional[str]:
    try:
        with open(os.path.join(git_dir, "HEAD"), encoding="utf-8") as fh:
            head = fh.read(4096).strip()
    except (OSError, UnicodeDecodeError):
        return None
    if head.startswith("ref: refs/heads/"):
        name = head[len("ref: refs/heads/"):]
        if name != ".invalid":
            # git's own refname rules, roughly: no controls, spaces or ~^:?*[\
            return name if _REFNAME.fullmatch(name) else None
        # A reftable repo keeps HEAD as a stub; ask git.
        out = _git(toplevel, ["symbolic-ref", "-q", "--short", "HEAD"], timeout)
        return out.strip() if out and out.strip() else None
    if re.fullmatch(r"[0-9a-f]{40,64}", head):
        return "detached@" + head[:12]
    return None


def _is_bare(d: str) -> bool:
    return (os.path.isfile(os.path.join(d, "HEAD")) and os.path.isdir(os.path.join(d, "objects"))
            and os.path.isdir(os.path.join(d, "refs")))


def _locate_with_git(cwd: str, timeout: float) -> Optional[Where]:
    out = _git(cwd, ["rev-parse", "--path-format=absolute",
                     "--git-common-dir", "--git-dir", "--show-toplevel"], timeout)
    lines = out.splitlines() if out else []
    if len(lines) != 3:
        return None
    common, git_dir, top = lines
    return Where(os.path.realpath(cwd), os.path.realpath(top), os.path.realpath(common),
                 _read_branch(git_dir, top, timeout))


def locate(cwd: str, timeout: float = 0.5) -> Optional[Where]:
    """The repo a directory is in, or None: not a directory, not in a work
    tree, inside a .git dir or a bare repo."""
    if any(os.environ.get(k) for k in _GIT_ENV):
        return _locate_with_git(cwd, timeout)
    d = os.path.realpath(cwd)
    if not os.path.isdir(d):
        return None
    cur = d
    while True:
        dotgit = os.path.join(cur, ".git")
        if os.path.isdir(dotgit):
            git_dir: Optional[str] = dotgit
            break
        if os.path.isfile(dotgit):
            git_dir = _gitdir_from_file(dotgit)
            break
        if _is_bare(cur):
            return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    if not git_dir or not os.path.isfile(os.path.join(git_dir, "HEAD")):
        return None
    return Where(d, cur, _common_of(git_dir), _read_branch(git_dir, cur, timeout))


# --------------------------------------------------------------------------
# Exclusions and redaction. Applied to every string of every event before it
# is written, and before any clipping.
#
# Redaction is a best-effort denylist, not a guarantee: a secret in a shape it
# does not know is written. What bounds the exposure is the narrow surface (an
# ARC-STATUS line, an error string, and metadata) and the 0600 files.

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
    """True for a local path under crm/ or with a secret-shaped segment."""
    for seg in re.split(r"[/\\]+", path):
        if seg and (_EXCLUDED_SEGMENT.match(seg) or _SECRET_SEGMENT.match(seg)):
            return True
    return False


_REDACTED = "[REDACTED]"
#: Every value pattern tries an existing marker first, so a second pass is a
#: no-op instead of eating the character after it.
_V = r"(?:\[REDACTED\]|"
_R = r"\1\2" + _REDACTED
_SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S),
     _REDACTED),
    # headers
    (re.compile(r"(?i)\b(authorization|proxy-authorization|x-api-key|api-key|cookie|set-cookie)"
                r"(\s*[:=]\s*)(?:(?:bearer|basic|token|digest)\s+)?" + _V + r"[^\s,;\"'&]+)"), _R),
    (re.compile(r"(?i)\bbearer\s+(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{12,}"), "Bearer " + _REDACTED),
    # vendor token shapes
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})"), _REDACTED),
    (re.compile(r"\bsk-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_-]{16,}"), _REDACTED),
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}"), _REDACTED),
    (re.compile(r"\b(?:xox[abposr]|xapp)-[A-Za-z0-9-]{8,}"), _REDACTED),
    (re.compile(r"hooks\.slack\.com/(?:services|workflows|triggers)/[A-Za-z0-9/_-]+"), "hooks.slack.com/" + _REDACTED),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), _REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), _REDACTED),
    (re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}"), _REDACTED),
    (re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"), _REDACTED),
    (re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}"), _REDACTED),  # Telegram bot
    (re.compile(r"\b(?:npm|lin_api|lin_oauth|shpat|shpss|whsec|hf|dop_v1|sbp|gsk|xai|pplx)_[A-Za-z0-9]{20,}"),
     _REDACTED),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"), _REDACTED),
    (re.compile(r"\bpypi-[A-Za-z0-9_-]{40,}"), _REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}"), _REDACTED),
    # userinfo in a URL, and credentials in a URL query
    (re.compile(r"(\b[a-z][a-z0-9+.-]{0,30}://[^/\s:@]+:)[^@\s/]+@", re.I), r"\1" + _REDACTED + "@"),
    (re.compile(r"(?i)([?&](?:access_token|token|api_key|apikey|key|secret|password|sig|signature|auth)=)"
                + _V + r"[^&\s#]+)"), r"\1" + _REDACTED),
    # command lines: --password x, --token=x, curl -u user:pass
    (re.compile(r"(?i)(--(?:password|passwd|pass|token|secret|api-key|apikey|access-token|auth-token)"
                r")([= ]+)" + _V + r"[^\s\"']+)"), _R),
    (re.compile(r"(\s(?:-u|--user)\s+[^\s:]+)(:)" + _V + r"[^\s\"']+)"), _R),
    # key=value / key: value where the key names a secret (camelCase included).
    # Bare values need 6+ characters, so prose like "sort key: ts" or "missing
    # token: see PR 12" is left alone.
    (re.compile(r"(?i)\b([a-z0-9_.-]{0,24}?(?:token|secret|passw(?:or)?d|passwd|pwd|passphrase|credentials?"
                r"|(?:api|access|secret|private|signing|client|master|encryption)[_.-]?key))"
                r"([\"']?\s*[:=]\s*)" + _V + r"\"[^\"]+\"|'[^']+'|[^\s,;&\"'()\[\]{}]{6,})"), _R),
    # SHOUTY_ENV_VAR_KEY=value
    (re.compile(r"\b([A-Z][A-Z0-9_]*_KEY)(\s*[:=]\s*)" + _V + r"\"[^\"]+\"|'[^']+'|[^\s,;&\"']+)"), _R),
    # a credential named in prose: "token abc123...", "password is hunter2"
    (re.compile(r"(?i)\b(token|bearer|secret|api key|password|passwd)(\s+(?:is\s+|was\s+|=\s*)?)"
                r"(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{16,}"), _R),
    (re.compile(r"(?i)\b(passw(?:or)?d)(\s+is\s+)" + _V + r"\S+)"), _R),
    # an unknown vendor's token: an unbroken run of 32+ letters and digits that
    # mixes upper case, lower case and at least four digits. Git SHAs, UUIDs and
    # hex digests are lower-case; hyphenated names are broken into short runs;
    # camelCase identifiers ("handleOAuth2Callback...") rarely carry four digits.
    (re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[a-z])(?=(?:[A-Za-z]*\d){4})"
                r"[A-Za-z0-9]{32,}(?![A-Za-z0-9])"), _REDACTED),
]
_PATH_TOKEN = re.compile(r"[^\s\"'<>()\[\]{},;`|]+")
_URL = re.compile(r"^[a-z][a-z0-9+.-]{0,30}://", re.I)


def _redact_paths(s: str) -> str:
    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if _URL.match(tok):  # a URL is not a local path; only its secrets are redacted
            return tok
        looks_like_path = "/" in tok or "\\" in tok or tok.startswith((".", "~"))
        if looks_like_path and excluded_path(tok.rstrip(".:")):
            return "[excluded-path]"
        return tok
    return _PATH_TOKEN.sub(repl, s)


#: The patterns that anchor on a keyword run only when one of their keywords
#: is in the text. On text without one (almost every status line) they cost
#: nothing; with one, their bounded prefixes keep them linear.
_NEEDS = {
    id(pat): words for pat, words in (
        (_SECRET_PATTERNS[1][0], ("authorization", "api-key", "cookie")),
        (_SECRET_PATTERNS[2][0], ("bearer",)),
        (_SECRET_PATTERNS[17][0], ("://",)),
        (_SECRET_PATTERNS[-5][0], ("token", "secret", "passw", "pwd", "passphrase", "credential", "key")),
        (_SECRET_PATTERNS[-4][0], ("_key",)),
        (_SECRET_PATTERNS[-3][0], ("token", "bearer", "secret", "api key", "password", "passwd")),
        (_SECRET_PATTERNS[-2][0], ("passw",)),
    )
}


def redact_text(s: str) -> str:
    low = s.lower()
    for pat, repl in _SECRET_PATTERNS:
        words = _NEEDS.get(id(pat))
        if words and not any(w in low for w in words):
            continue
        s = pat.sub(repl, s)
        low = s.lower() if words else low
    return _redact_paths(s)


def _flat(s: Any, cap: int = MAX_STR) -> str:
    """One line: every C0 and C1 control character (newline, tab, NEL included)
    and U+2028/U+2029 become a space, so no field can start a line of its own in
    another session's brief: whatever str.splitlines() splits on is gone."""
    s = re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]", " ", str(s))
    return s if len(s) <= cap else s[: cap - 1] + "…"


def redact(value: Any) -> Any:
    """Redact every string in a JSON-shaped value; keys are left alone.

    Redaction runs BEFORE the clip. Clipping first could cut a token in half
    and leave a prefix too short for any pattern to recognise. The pre-cap that
    bounds regex time can cut one too, so a cut string also loses its trailing
    partial word before it is redacted.
    """
    if isinstance(value, str):
        if len(value) > PRECAP:
            value = re.sub(r"\S*$", "", value[:PRECAP])
        return _flat(redact_text(value))
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

    None when: there is no config or it is unusable, cwd is not in a git work
    tree, the repo is not configured or is listed in two scopes, or cwd is
    excluded (crm/ or a secret-shaped path).
    """
    try:
        scopes = load_scopes()
    except ConfigError:
        return None
    if not scopes.by_repo:
        return None
    where = locate(cwd, timeout)
    if where is None:
        return None
    sid = scopes.by_repo.get(where.common_dir)
    if sid is None or excluded_path(where.cwd):
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
        event["paseo_agent_id"] = _flat(agent, 128)
    # Only the payload is free text. The identifiers come from git and the
    # filesystem (an excluded cwd never gets this far); running them through
    # the text redaction made `fix/credentials` read as `[excluded-path]`, so
    # stored and live branches stopped matching. They are flattened instead.
    for key in ("cwd", "repo", "branch"):
        if isinstance(event[key], str):
            event[key] = _flat(event[key], 1024)
    event["payload"] = redact(payload)
    return event


def _acquire(fd: int, budget: float) -> bool:
    deadline = time.monotonic() + max(0.0, budget)
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


def _open_lock(scope: Scope) -> int:
    scope.store.mkdir(parents=True, exist_ok=True, mode=0o700)
    return os.open(str(scope.lock_path), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)


def append(scope: Scope, event: Dict[str, Any], budget: float = LOCK_BUDGET_S,
           fold_cap: Optional[int] = FOLD_CAP,
           board_cap: Optional[int] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Append one event under the lock, then fold the new log bytes into
    board.json under the same lock. Returns (written, board).

    written is False, and nothing is written, when the lock is not acquired
    within min(budget, LOCK_BUDGET_S) or the event is not writable. board is
    None when board.json was not brought up to date (more than fold_cap unseen
    bytes, or a board.json over board_cap: MISSED says which).

    A writer killed mid-write can leave a line without its newline. The next
    append starts on a fresh line, so the damage is one skipped line, never a
    corrupted neighbour.
    """
    global STAGE
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or excluded_path(cwd):
        return False, None
    line = (json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(line) > MAX_LINE:
        return False, None
    lock_fd = _open_lock(scope)
    try:
        STAGE = "lock"
        if not _acquire(lock_fd, min(budget, LOCK_BUDGET_S)):
            return False, None
        STAGE = "write"
        # Opened by path, under the lock.
        fd = os.open(str(scope.log), os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            size = os.fstat(fd).st_size
            if size and os.pread(fd, 1, size - 1) != b"\n":
                line = b"\n" + line
            view = memoryview(line)
            while view:
                view = view[os.write(fd, view):]
            STAGE = "fold"
            try:
                board = _sync_board(scope, fd, size + len(line), fold_cap, board_cap)
            except BoardTooBig:
                _missed("board-cap")
                return True, None
            if board is None:
                _missed("fold-cap")
            return True, board
        finally:
            os.close(fd)
    finally:
        os.close(lock_fd)


def _missed(what: str) -> None:
    global MISSED
    MISSED = MISSED or what


def read_log(scope: Scope) -> bytes:
    try:
        return scope.log.read_bytes()
    except FileNotFoundError:
        return b""


def _valid_event(ev: Any) -> bool:
    if not (isinstance(ev, dict) and type(ev.get("v")) is int and ev["v"] == SCHEMA_VERSION
            and isinstance(ev.get("type"), str)
            and isinstance(ev.get("ts"), str) and TS_RE.match(ev["ts"])
            and isinstance(ev.get("session_id"), str) and SESSION_ID_RE.match(ev["session_id"])
            and isinstance(ev.get("cwd"), str) and isinstance(ev.get("repo"), str)
            and (ev.get("branch") is None or isinstance(ev["branch"], str))
            and ("paseo_agent_id" not in ev or isinstance(ev["paseo_agent_id"], str))
            and isinstance(ev.get("payload"), dict)):
        return False
    return all(v is None or isinstance(v, (str, int, float, bool)) for v in ev["payload"].values())


# --------------------------------------------------------------------------
# board.json: the log folded, in log order.
#
# The fold is one function on every path. `rebuild` folds every complete line
# from byte 0; a write folds only the lines after `log_offset`. Folding lines
# 0..k and then k..n is folding 0..n, so the incremental board and the full
# rebuild are byte-identical (a test pins this). Nothing reads a clock.
#
# "Latest" fields move only for an event whose ts is >= the row's own ts for
# that field, and counters are sums, so two writers whose appends landed out
# of timestamp order still leave the true latest state.

_STATES = {"session.start": "started", "session.stop": "stopped", "session.died": "died"}
_BOARD_INTS = ("log_offset", "events", "skipped_lines", "ignored_events")


def _empty_board(scope_id: str) -> Dict[str, Any]:
    return {"v": SCHEMA_VERSION, "scope": scope_id, "events": 0, "skipped_lines": 0,
            "ignored_events": 0, "last_ts": None, "log_offset": 0, "log_tail": None, "sessions": {}}


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
            "paseo_agent_id": None, "agent_ts": None, "fleet_role": None, "arc_status": None,
            "arc_line": None, "arc_ts": None, "died_ts": None, "died_reason": None, "died_error": None,
        }
    row["first_ts"] = min(row["first_ts"], ts)
    if row["last_event"] is None or ts >= row["last_ts"]:
        row.update(last_ts=ts, last_event=etype, state=_STATES[etype],
                   cwd=ev["cwd"], repo=ev["repo"], branch=ev.get("branch"))
    agent = ev.get("paseo_agent_id")
    if agent and (row["agent_ts"] is None or ts >= row["agent_ts"]):
        row.update(paseo_agent_id=agent, agent_ts=ts)
    if etype == "session.start":
        row["starts"] += 1
        if row["started_ts"] is None or ts >= row["started_ts"]:
            row["started_ts"] = ts
            if isinstance(p.get("fleet_role"), str):
                row["fleet_role"] = p["fleet_role"]
    elif etype == "session.stop":
        row["stops"] += 1
    elif row["died_ts"] is None or ts >= row["died_ts"]:
        # The only terminal event: Stop fires every turn, so session.stop is a
        # heartbeat. The redacted error text is kept on the row so a reader of
        # the board (fleet-reconcile's usage-limit class) has it without the log;
        # splitting died from failed, and extracting reset times, is phase 2.
        row["died_ts"] = ts
        row["died_reason"] = p["error_type"] if isinstance(p.get("error_type"), str) else "unknown"
        row["died_error"] = p["error"] if isinstance(p.get("error"), str) else None
    if isinstance(p.get("arc_status"), str) and (row["arc_ts"] is None or ts >= row["arc_ts"]):
        row.update(arc_status=p["arc_status"],
                   arc_line=p["arc_line"] if isinstance(p.get("arc_line"), str) else None, arc_ts=ts)
    if board["last_ts"] is None or ts > board["last_ts"]:
        board["last_ts"] = ts


def _fold_line(board: Dict[str, Any], raw: bytes) -> Optional[Dict[str, Any]]:
    """Fold one line; return the event when it was applied."""
    if not raw.strip():
        return None
    try:
        ev = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        board["skipped_lines"] += 1
        return None
    if not _valid_event(ev):
        board["skipped_lines"] += 1
        return None
    if ev["type"] not in EVENT_TYPES:  # a later phase's type
        board["ignored_events"] += 1
        return None
    board["events"] += 1
    _apply(board, ev)
    return ev


def fold(board: Dict[str, Any], chunk: bytes, base_offset: int, prior: bytes = b"") -> None:
    """Fold the complete lines of `chunk` (the log from `base_offset` on) into
    `board`. `prior` is the log's bytes just before base_offset, for the tail
    signature. A trailing fragment with no newline is an append in progress or
    a torn write; it is left for the next fold."""
    end = chunk.rfind(b"\n") + 1
    if end == 0:
        return
    for raw in chunk[:end].split(b"\n")[:-1]:
        _fold_line(board, raw)
    board["log_offset"] = base_offset + end
    board["log_tail"] = _tail_sig((prior + chunk[:end])[-TAIL_BYTES:])


def rebuild(scope_id: str, data: bytes) -> Dict[str, Any]:
    """The pure full rebuild: every complete line of the log, from byte 0."""
    board = _empty_board(scope_id)
    fold(board, data, 0)
    return board


def board_bytes(board: Dict[str, Any]) -> bytes:
    # Compact: a hook re-serialises the whole board on every write.
    return (json.dumps(board, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _valid_board(board: Any, scope_id: str) -> bool:
    return (
        isinstance(board, dict) and board.get("v") == SCHEMA_VERSION and board.get("scope") == scope_id
        and isinstance(board.get("sessions"), dict)
        and all(isinstance(board.get(k), int) and board[k] >= 0 for k in _BOARD_INTS)
        and all(isinstance(r, dict) and isinstance(r.get("last_ts"), str) and isinstance(r.get("session_id"), str)
                for r in board["sessions"].values())
    )


class BoardTooBig(Exception):
    """board.json is over the cap a hook may parse."""


def load_board(scope: Scope, cap: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """The cached board.json, or None when missing or malformed. This is what
    SessionStart reads; it never parses the log. Raises BoardTooBig when the
    file is over `cap` bytes, which is checked before it is read."""
    try:
        if cap is not None and scope.board_path.stat().st_size > cap:
            raise BoardTooBig()
        board = json.loads(scope.board_path.read_bytes().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return board if _valid_board(board, scope.id) else None


def _write_atomic(path: Path, data: bytes) -> None:
    global _TMP
    tmp = str(path.parent / (".%s.%d.%d.tmp" % (path.name, os.getpid(), time.monotonic_ns())))
    _TMP = tmp
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    finally:
        _TMP = None


def write_board(scope: Scope, board: Dict[str, Any]) -> None:
    scope.store.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_atomic(scope.board_path, board_bytes(board))


def _sync_board(scope: Scope, fd: int, size: int, cap: Optional[int], board_cap: Optional[int] = None,
                board: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Bring board.json up to `size` log bytes. Call with the lock held.

    Starts from `board` if given (the CLI builds one outside the lock), else
    from the cached board.json. Folds only the bytes after its log_offset,
    when its tail signature still matches the log; otherwise (no board, a
    malformed one, or a log that was replaced) it refolds the log from byte 0.
    Returns None, leaving board.json alone, when that means reading more than
    `cap` log bytes; raises BoardTooBig when board.json is over `board_cap`.
    """
    if board is None:
        board = load_board(scope, board_cap)
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


def check_board(scope: Scope) -> Tuple[str, int, bytes]:
    """Is the cached board.json exactly the fold of what it claims to have
    folded? Read-only and lock-free: the board is read BEFORE the log, and the
    log only grows, so the prefix it covers is always there.

    Returns (status, lag_bytes, log); status is "ok", "missing", "differs" or
    "stale-log" (the log no longer starts with what the board folded)."""
    board = load_board(scope)
    data = read_log(scope)
    if board is None:
        return ("missing" if not scope.board_path.exists() else "differs"), len(data), data
    off = board["log_offset"]
    if off > len(data) or _tail_sig(data[max(0, off - TAIL_BYTES):off]) != board.get("log_tail"):
        return "stale-log", len(data), data
    expected = rebuild(scope.id, data[:off])
    if board_bytes(expected) != board_bytes(board):
        return "differs", len(data) - off, data
    return "ok", len(data) - off, data


def sync_board(scope: Scope, full: bool = False, wait: float = 2.0) -> Optional[Dict[str, Any]]:
    """CLI path: bring board.json up to date with no size cap. With `full`, or
    when the cached board is missing or unusable, the whole log is folded
    OUTSIDE the lock, on a read of the log; under the lock only the bytes
    appended since are folded, so hooks are not made to skip their appends
    while the CLI works. The lock is retried for up to `wait` seconds; None if
    it stayed busy."""
    board = None if full else load_board(scope)
    if board is None:
        board = rebuild(scope.id, read_log(scope))
    lock_fd = _open_lock(scope)
    try:
        deadline = time.monotonic() + wait
        while not _acquire(lock_fd, LOCK_BUDGET_S):
            if time.monotonic() >= deadline:
                return None
        fd = os.open(str(scope.log), os.O_RDONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            return _sync_board(scope, fd, os.fstat(fd).st_size, None, board=board)
        finally:
            os.close(fd)
    finally:
        os.close(lock_fd)


# --------------------------------------------------------------------------
# Rendering. Every sentence is a statement of fact from the store. The spike
# (2026-09-29) found models treat imperative hook text as prompt injection, so
# nothing here tells the reader to do anything. Every interpolated field is
# flattened to one line; other sessions' words appear only as a quoted string.

def _age(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % (s // 60)
    if s < 172800:
        return "%dh" % (s // 3600)
    return "%dd" % (s // 86400)


def _short(sid: Any) -> str:
    return _flat(str(sid or "-")[:8])


def _tilde(path: Any) -> str:
    if not isinstance(path, str) or not path:
        return "-"
    h = str(home())
    return _flat("~" + path[len(h):] if path == h or path.startswith(h + "/") else path, 160)


def is_live(row: Dict[str, Any], now: float) -> bool:
    return row.get("state") != "died" and str(row.get("last_ts") or "") >= now_ts(now - LIVE_WINDOW_S)


def _row_sentence(row: Dict[str, Any], now: float) -> str:
    bits = ["session %s" % _short(row["session_id"])]
    if row.get("paseo_agent_id"):
        bits.append("Paseo agent %s" % _short(row["paseo_agent_id"]))
    if row.get("fleet_role"):
        bits.append("role, quoted: %s" % json.dumps(_flat(row["fleet_role"], 32), ensure_ascii=False))
    bits.append("branch %s" % _flat(row.get("branch") or "-", 80))
    bits.append("cwd %s" % _tilde(row.get("cwd")))
    bits.append("last event %s ago (%s)" % (_age(now - parse_ts(row["last_ts"])), _flat(row.get("last_event"), 20)))
    if row.get("state") == "died":
        bits.append("died: %s" % _flat(row.get("died_reason"), 40))
        if row.get("died_error"):
            bits.append("error text, quoted: %s" % json.dumps(_flat(row["died_error"], 160), ensure_ascii=False))
    if row.get("arc_line"):
        bits.append("status line, quoted: %s" % json.dumps(_flat(row["arc_line"], 200), ensure_ascii=False))
    return "- " + ", ".join(bits) + "."


def render_brief(board: Dict[str, Any], me: Where, session_id: str, now: float,
                 cap: int = BRIEF_CAP) -> str:
    """The SessionStart brief: other live sessions on this branch first, then
    other rows for this branch or this cwd from the last 48 h. Empty when there
    are none. One pass over the rows, and rows are rendered only until the cap."""
    live_cut, recent_cut = now_ts(now - LIVE_WINDOW_S), now_ts(now - RECENT_WINDOW_S)
    live: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for r in board.get("sessions", {}).values():
        if r.get("session_id") == session_id:
            continue
        same_branch = bool(me.branch) and r.get("repo") == me.common_dir and r.get("branch") == me.branch
        if not same_branch and r.get("cwd") != me.cwd:
            continue
        lts = str(r.get("last_ts") or "")
        if same_branch and r.get("state") != "died" and lts >= live_cut:
            live.append(r)
        elif lts >= recent_cut:
            rest.append(r)
    if not live and not rest:
        return ""
    key = lambda r: (str(r.get("last_ts")), str(r.get("session_id")))
    live.sort(key=key, reverse=True)
    rest.sort(key=key, reverse=True)
    out = "\n".join([
        "Shared board facts (ctx scope %s, %d events, last event %s). These rows were recorded "
        "by hooks in other sessions of this scope; quoted status lines are those sessions' own "
        "words, reproduced as data." % (_flat(board.get("scope"), 64), board.get("events", 0),
                                        _flat(board.get("last_ts") or "-", 24)),
        "This session: %s, branch %s, cwd %s." % (_short(session_id), _flat(me.branch or "-", 80), _tilde(me.cwd)),
    ])
    sections = []
    if live:
        sections.append(("Other live sessions on branch %s in this repo (live: no died event, an event "
                         "in the last %dh): %d." % (_flat(me.branch, 80), LIVE_WINDOW_S // 3600, len(live)), live))
    if rest:
        sections.append(("Other board rows for this branch or this cwd, last %dh: %d."
                         % (RECENT_WINDOW_S // 3600, len(rest)), rest))
    total, shown = len(live) + len(rest), 0
    where = _tilde(str(state_root() / str(board.get("scope")) / "board.json"))
    for header, rows in sections:
        for line in [header] + rows:
            text = line if isinstance(line, str) else _row_sentence(line, now)
            tail = "\n%d more rows are omitted here; the full board is %s." % (total - shown, where)
            if len(out) + 1 + len(text) + len(tail) > cap:
                return (out + tail)[:cap]
            out += "\n" + text
            shown += 0 if isinstance(line, str) else 1
    return out[:cap]


def render_table(board: Dict[str, Any], now: float) -> str:
    rows = sorted(board.get("sessions", {}).values(), key=lambda r: (r["last_ts"], r["session_id"]), reverse=True)
    live = [r for r in rows if is_live(r, now)]
    lines = ["scope %s: %d sessions (%d live: no session.died and an event in the last %dh; %d of them with a "
             "Paseo agent), %d events, %d skipped lines, last event %s" % (
                 board.get("scope"), len(rows), len(live), LIVE_WINDOW_S // 3600,
                 sum(1 for r in live if r.get("paseo_agent_id")), board.get("events", 0),
                 board.get("skipped_lines", 0), board.get("last_ts") or "-")]
    if not rows:
        return lines[0]
    hdr = ("SESSION", "AGENT", "STATE", "LIVE", "LAST", "BRANCH", "STATUS", "CWD")
    table = [hdr]
    for r in rows:
        table.append((
            _short(r["session_id"]), _short(r.get("paseo_agent_id")), _flat(r.get("state") or "-", 10),
            "yes" if is_live(r, now) else "no", _age(now - parse_ts(r["last_ts"])),
            _flat(r.get("branch") or "-", 40), _flat(r.get("arc_status") or "-", 20), _tilde(r.get("cwd")),
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


def _died_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """StopFailure's error class and detail. Claude Code 2.1.280 sends the class
    in `error` and the text in `error_details`; the hooks reference documents
    `error_type` (class) and `error` (text). Both shapes are read."""
    if isinstance(data.get("error_type"), str):
        cls, detail = data["error_type"], data.get("error")
    else:
        cls, detail = data.get("error"), data.get("error_details")
    payload: Dict[str, Any] = {"error_type": cls if isinstance(cls, str) and cls else "unknown"}
    if isinstance(detail, str) and detail:
        payload["error"] = detail
    payload.update(_extract_arc(data.get("last_assistant_message")))
    return payload


def run_hook(event: str, raw: str, deadline: float, now: Optional[float] = None) -> str:
    """Handle one hook event. Returns the text for stdout ("" for none).

    `deadline` is a time.monotonic() value. Work that cannot finish before it
    is skipped, and skipped work is named in MISSED for the wrapper to record;
    the wrapper's alarm is the backstop.
    """
    global STAGE, MISSED
    STAGE, MISSED = "parse", None
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
    STAGE = "scope"
    # git runs only on the fallback path; it gets what the budget has left, less
    # a margin for the append.
    scope = resolve_scope(cwd, timeout=left() - 0.03)
    if scope is None or left() <= 0.01:
        return ""
    STAGE = "event"
    if event == "session-start":
        payload: Dict[str, Any] = {}
        for key in ("source", "model", "agent_type"):
            if isinstance(data.get(key), str):
                payload[key] = data[key]
        role = os.environ.get("FLEET_ROLE")
        if role:
            payload["fleet_role"] = role
        ev = make_event("session.start", scope, session_id, payload, now)
    elif event == "stop":
        ev = make_event("session.stop", scope, session_id, _extract_arc(data.get("last_assistant_message")), now)
    elif event == "stop-failure":
        ev = make_event("session.died", scope, session_id, _died_payload(data), now)
    else:
        return ""
    # session.died is the only terminal event and the one a burst (an
    # account-wide limit) makes contend: it may wait for the lock with all the
    # budget has left. The others wait HOOK_LOCK_BUDGET_S at most.
    wait = left() - 0.02 if event == "stop-failure" else min(HOOK_LOCK_BUDGET_S, left() - 0.02)
    written, board = append(scope, ev, budget=wait, board_cap=HOOK_BOARD_CAP)
    if not written:
        _missed("lock")
    if event != "session-start":
        return ""
    STAGE = "brief"
    if board is None and MISSED != "board-cap":
        try:
            board = load_board(scope, HOOK_BOARD_CAP)  # the cached board; the log is never parsed here
        except BoardTooBig:
            _missed("board-cap")
    if board is None or left() <= 0.005:
        return ""
    brief = render_brief(board, scope.where, session_id, time.time() if now is None else now)
    if not brief:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                              "additionalContext": brief}}, ensure_ascii=False)


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


def recent_sessions(days: float, now: float) -> Tuple[Dict[str, Dict[str, Any]], int, int]:
    """Claude Code sessions (transcripts) modified in the last `days`, grouped
    by repo common dir. Returns (by_repo, sessions_in_gone_cwds,
    sessions_outside_git)."""
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
        slot = by_repo.setdefault(where.common_dir, {"sessions": 0, "last": 0.0, "cwds": set()})
        slot["sessions"] += len(recent)
        slot["last"] = max(slot["last"], recent[0][0])
        slot["cwds"].add(cwd)
    return by_repo, gone, outside


def _misses(now: float, days: float = 1.0) -> Dict[str, int]:
    """Misses recorded by ctx_hook.py in the window, by stage: runs out of time,
    and runs that skipped work (a busy lock, a board over its cap). The file is
    rotated to .1 at 1 MiB, so both are read. Records carry no path: they are
    machine-wide, not per scope."""
    out: Dict[str, int] = {}
    lines: List[str] = []
    for path in (Path(str(misses_path()) + ".1"), misses_path()):
        try:
            lines += path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            pass
    for line in lines:
        try:
            rec = json.loads(line)
            if now - float(rec["ts"]) <= days * 86400:
                out[str(rec.get("stage"))] = out.get(str(rec.get("stage")), 0) + 1
        except (ValueError, KeyError, TypeError):
            continue
    return out


def doctor_config() -> Tuple[List[str], int, Optional[Scopes]]:
    try:
        scopes = load_scopes()
    except ConfigError as exc:
        return ["config    %s: ERROR %s (every repo is unscoped until it is fixed)" % (config_path(), exc)], 1, None
    lines = ["config    %s: %s" % (config_path(), "%d scopes, %d repos" % (
        len({s for s in scopes.by_repo.values() if s}), len(scopes.by_repo))
        if scopes.by_repo else "absent or empty (every repo is unscoped)")]
    problems = 0
    for repo, sids in sorted(scopes.ambiguous.items()):
        lines.append("  ERROR   %s is listed in scopes %s: it has no scope until one is removed"
                     % (_tilde(repo), ", ".join(sids)))
        problems += 1
    for repo in sorted(r for r in scopes.by_repo if not os.path.isdir(r)):
        lines.append("  WARN    %s does not exist" % _tilde(repo))
    return lines, problems, scopes


def doctor_scoped(scope: Scope, scopes: Scopes, now: float) -> Tuple[List[str], int]:
    out = ["scope     %s" % scope.id,
           "  repo      %s (branch %s)" % (scope.where.common_dir, scope.where.branch or "-"),
           "  store     %s" % scope.store]
    problems = 0
    status, lag, data = check_board(scope)
    lines = data.split(b"\n")[:-1]
    board = rebuild(scope.id, data)
    out.append("  log       %d bytes, %d events, %d skipped lines, %d ignored events"
               % (len(data), board["events"], board["skipped_lines"], board["ignored_events"]))
    out.append("  lock      %s" % _lock_state(scope))
    size = scope.board_path.stat().st_size if scope.board_path.exists() else 0
    if size > HOOK_BOARD_CAP:
        problems += 1
        out.append("  PROBLEM   board.json is %d bytes, over the %d a hook will parse: hooks append but no longer "
                   "fold or brief (no retention in phase 1; retention is phase 2)" % (size, HOOK_BOARD_CAP))
    elif size > HOOK_BOARD_CAP // 2:
        out.append("  WARN      board.json is %d bytes, over half the %d a hook will parse" % (size, HOOK_BOARD_CAP))
    if status == "ok" and lag <= FOLD_CAP:
        out.append("  board     %d bytes, %d sessions; equals a rebuild of what it folded%s"
                   % (size, len(board["sessions"]), (", %d bytes behind (the next write folds them)" % lag) if lag else ""))
    elif status == "ok":
        problems += 1
        out.append("  PROBLEM   board.json is %d bytes behind the log, past the %d bytes a hook folds; "
                   "hooks no longer update it (`ctx board` catches it up)" % (lag, FOLD_CAP))
    elif status == "missing":
        out.append("  board     not built yet")
        if len(data) > FOLD_CAP:
            problems += 1
            out.append("  PROBLEM   no board.json and the log is past %d bytes, so hooks will not build one "
                       "(`ctx board` builds it)" % FOLD_CAP)
    else:
        problems += 1
        out.append("  PROBLEM   board.json %s (`ctx board --rebuild` replaces it)" % (
            "differs from a rebuild of the log it claims to have folded" if status == "differs"
            else "was folded from a log that has since been replaced or truncated"))
    stray = sorted(p.name for p in scope.store.glob(".*.tmp")) if scope.store.exists() else []
    if stray:
        out.append("  WARN      %d stray temp files: %s" % (len(stray), ", ".join(stray[:3])))
    last: Dict[str, str] = {}
    oldest = None
    for raw in lines:
        try:
            ev = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if _valid_event(ev) and ev["type"] in EVENT_TYPES:
            if ev["ts"] > last.get(ev["type"], ""):
                last[ev["type"]] = ev["ts"]
            oldest = ev["ts"] if oldest is None or ev["ts"] < oldest else oldest
    out.append("  retention no retention in phase 1: the log and board.json only grow%s (compaction is phase 2)"
               % ((", oldest event %s" % oldest[:10]) if oldest else ""))
    # The BRO-2019 failure: a hook that silently stopped firing. Transcripts tell
    # an idle scope from a dead hook.
    by_repo, _, _ = recent_sessions(1.0, now)
    repos = {r for r, s in scopes.by_repo.items() if s == scope.id}
    seen = sum(slot["sessions"] for r, slot in by_repo.items() if r in repos)
    newest = max(last.values()) if last else None
    fresh = newest is not None and now - parse_ts(newest) <= 86400
    for etype, hook in (("session.start", "SessionStart"), ("session.stop", "Stop"),
                        ("session.died", "StopFailure")):
        ts = last.get(etype)
        out.append("  %-12s %s" % (hook, ("last event %s ago" % _age(now - parse_ts(ts))) if ts else "no event in the log"))
    misses = _misses(now)
    if misses:
        out.append("  misses    %d hook runs in 24h ran out of time or skipped work, machine-wide (misses carry "
                   "no path), by stage: %s" % (
                       sum(misses.values()), ", ".join("%s %d" % kv for kv in sorted(misses.items()))))
    out.append("  sessions  %d Claude Code sessions in this scope's repos in the last 24h (transcripts)" % seen)
    if seen and not fresh:
        problems += 1
        out.append("  PROBLEM   sessions ran in this scope in the last 24h but no hook event was recorded: "
                   "%s" % ("the hooks are running out of time or skipping work (see misses)" if misses
                           else "the hooks are not registered, or not firing"))
    return out, problems


def doctor_unscoped(scopes: Optional[Scopes], days: float, now: float) -> List[str]:
    """Repos that have Claude Code sessions in the window but no scope."""
    mapped = scopes.by_repo if scopes else {}
    by_repo, gone, outside = recent_sessions(days, now)
    unscoped = {r: s for r, s in by_repo.items() if not mapped.get(r)}
    out = ["sessions  Claude Code transcripts under %s, last %g days" % (_tilde(str(_claude_projects_dir())), days),
           "unscoped repos with sessions: %d" % len(unscoped)]
    for repo, slot in sorted(unscoped.items(), key=lambda kv: (-kv[1]["sessions"], kv[0])):
        out.append("  %-60s %4d sessions, last %s ago, %d cwds" % (
            _tilde(repo), slot["sessions"], _age(now - slot["last"]), len(slot["cwds"])))
    out.append("  (%d sessions in a cwd that no longer exists; %d outside any git repo)" % (gone, outside))
    return out


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
                   help="refold the log from scratch and replace board.json")
    d = sub.add_parser("doctor", help="config, store, board and hook health")
    d.add_argument("--unscoped", action="store_true",
                   help="list repos that have sessions but no scope (works from any directory)")
    d.add_argument("--days", type=float, default=14.0, help="session window for --unscoped (default 14)")
    args = ap.parse_args(argv)
    cwd = os.path.realpath(args.directory or os.getcwd())
    now = time.time()

    if args.cmd == "doctor":
        cfg_lines, problems, scopes = doctor_config()
        if args.unscoped:
            print("\n".join(cfg_lines + doctor_unscoped(scopes, args.days, now)))
            return 1 if problems else 0
        scope = resolve_scope(cwd)
        if scope is None:
            if problems:  # a broken config is reported from anywhere
                print("\n".join(cfg_lines))
                return 1
            return 0  # no scope: silent
        lines, more = doctor_scoped(scope, scopes, now)
        print("\n".join(cfg_lines + lines))
        return 1 if problems + more else 0

    scope = resolve_scope(cwd)
    if scope is None:
        return 0  # no scope: every command is a silent no-op

    before = None
    if args.rebuild:
        status, _, _ = check_board(scope)
        before = status
    board = sync_board(scope, full=args.rebuild)
    if board is None:
        print("ctx: events.lock stayed busy; board.json was not updated", file=sys.stderr)
        return 1
    if args.rebuild and not args.json:
        print("rebuilt from the log; the cached board.json %s" % {
            "ok": "equalled a rebuild of what it had folded",
            "missing": "did not exist",
            "differs": "differed from a rebuild (hand-edited or corrupt) and was replaced",
            "stale-log": "was folded from a replaced or truncated log and was replaced",
        }[before])
    if args.json:
        sys.stdout.write(board_bytes(board).decode("utf-8"))
    else:
        print(render_table(board, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
