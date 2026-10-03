"""pm_store.py — the Claude Code credential store, named, locked and read the way Claude Code does.

Facts this module encodes (Claude Code 2.1.280, read from the bundled source):

- Item name: `Claude Code-credentials` when CLAUDE_CONFIG_DIR is unset, otherwise
  `Claude Code-credentials-<sha256(config dir)[:8]>`. CLAUDE_SECURESTORAGE_CONFIG_DIR overrides both.
  Account: $USER.
- With no `<configDir>/.credentials.json`, sessions re-read that item before their requests, through
  a 30 s cache. Writing it changes the credential of every running session within about 30 s.
- Refreshes run under a proper-lockfile lock: the directory `<configDir>/.oauth_refresh.lock`, then the
  legacy `<realpath(configDir)>.lock`. Stale after 60 s.
- `security -i` takes commands up to 4032 characters; longer payloads go through argv (hex), exactly
  as Claude Code itself does. A store item carrying several MCP tokens takes that path: the payload is
  visible to same-user `ps` for the duration of the call.

Nothing here prints or logs a secret. Token comparison is constant-time and returns a bool.
"""

import hashlib
import hmac
import json
import os
import re
import shlex
import subprocess
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

ORCA_SERVICE = "Orca Claude Code Managed Credentials"
STORE_BASE = "Claude Code-credentials"
NOT_FOUND_RC = 44
SECURITY_STDIN_LIMIT = 4032
EXPIRY_BUFFER_MS = 300_000  # Claude Code refreshes inside the last 5 minutes
LOCK_STALE_SECONDS = 60.0   # proper-lockfile's `stale` in Claude Code's refresh lock
LOCK_MAX_HOLD_SECONDS = 30.0  # never hold Claude Code's lock anywhere near its stale age


class StoreError(RuntimeError):
    """The store could not be read or written; callers must stop, not guess."""


class StoreBusy(StoreError):
    """The item kept changing between reads; nothing was written."""


class LockBusy(RuntimeError):
    """A Claude Code process holds its refresh lock."""


class Read(NamedTuple):
    status: str  # "ok" | "absent" | "error"
    data: Optional[Dict[str, Any]]
    detail: str = ""


def run_cmd(cmd: List[str], input_str: Optional[str] = None, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_str, text=True, capture_output=True, check=False, timeout=timeout)


def current_username() -> str:
    user = os.environ.get("USER") or os.environ.get("LOGNAME")
    if not user:
        try:
            import getpass

            user = getpass.getuser()
        except Exception:
            user = "claude-code-user"
    if not all(c.isalnum() or c in "._-" for c in user):
        user = "claude-code-user"
    return user


def _nfc(path: Any) -> str:
    return unicodedata.normalize("NFC", str(path))


def claude_config_dir() -> Path:
    secure = os.environ.get("CLAUDE_SECURESTORAGE_CONFIG_DIR")
    if secure is not None:
        return Path(_nfc(secure or Path.home() / ".claude"))
    return Path(_nfc(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"))


def scoped_item_name(config_dir: Any) -> str:
    return "%s-%s" % (STORE_BASE, hashlib.sha256(_nfc(config_dir).encode("utf-8")).hexdigest()[:8])


def store_item_names() -> Tuple[str, List[str]]:
    """(primary, mirrors): the item this environment's sessions read, then the other name for the
    same default config dir. Only the primary is ever written. Old provider-manager versions wrote
    both, so a mirror may still hold a chain an Orca copy also holds; the refresh interlock protects
    it whenever a running Claude Code process could be reading it (config_dir_override_running)."""
    secure = os.environ.get("CLAUDE_SECURESTORAGE_CONFIG_DIR")
    unscoped = (not secure) if secure is not None else not os.environ.get("CLAUDE_CONFIG_DIR")
    cfg = claude_config_dir()
    primary = STORE_BASE if unscoped else scoped_item_name(cfg)
    mirrors: List[str] = []
    if _nfc(cfg) == _nfc(Path.home() / ".claude"):
        mirrors.append(scoped_item_name(cfg) if unscoped else STORE_BASE)
    return primary, mirrors


_CLAUDE_CMD = re.compile(r"(^|/)claude(\s|$)|/claude/versions/\d+\.\d+\.\d+(\s|$)|/@anthropic-ai/claude-code/")
_ENV_START = re.compile(r"\s[A-Za-z_][A-Za-z0-9_]*=")
_OVERRIDE_VAR = re.compile(r"(?:^|\s)(?:CLAUDE_CONFIG_DIR|CLAUDE_SECURESTORAGE_CONFIG_DIR)=(\S+)")


def _same_dir(a: str, b: Any) -> bool:
    return os.path.realpath(os.path.expanduser(a)) == os.path.realpath(str(b))


def config_dir_override_running(config_dir: Any) -> bool:
    """Is a running Claude Code process reading the scoped item for config_dir, i.e. launched with
    CLAUDE_CONFIG_DIR (or CLAUDE_SECURESTORAGE_CONFIG_DIR) resolving to it? Read from `ps axeww`:
    the command part (before the first environment token) must be Claude Code, and the variable must
    be a real environment token with that value. If the process table cannot be read, the answer is
    yes, and the caller then protects the mirror."""
    try:
        res = run_cmd(["ps", "axeww", "-o", "command="], timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    if res.returncode != 0:
        return True
    for line in (res.stdout or "").splitlines():
        env_at = _ENV_START.search(line)
        command = line[:env_at.start()] if env_at else line
        if not _CLAUDE_CMD.search(command):
            continue
        for value in _OVERRIDE_VAR.findall(line[env_at.start():] if env_at else ""):
            if _same_dir(value.strip('"'), config_dir):
                return True
    return False


# -- keychain I/O ---------------------------------------------------------------------------------

def _decode(raw: str) -> Optional[Dict[str, Any]]:
    if not raw.startswith("{"):
        try:
            raw = bytes.fromhex(raw).decode("utf-8")
        except ValueError:
            return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def keychain_read(service: str, account: str, timeout: float = 30.0) -> Read:
    try:
        res = run_cmd(["security", "find-generic-password", "-s", service, "-a", account, "-w"], timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return Read("error", None, "security failed: %s" % type(e).__name__)
    if res.returncode == NOT_FOUND_RC:
        return Read("absent", None)
    if res.returncode != 0:
        return Read("error", None, "security rc %d: %s" % (res.returncode, (res.stderr or "").strip()[:120]))
    raw = (res.stdout or "").strip()
    if not raw:
        return Read("absent", None)
    data = _decode(raw)
    if data is None:
        return Read("error", None, "unparseable item")
    return Read("ok", data)


def keychain_write(service: str, account: str, data: Dict[str, Any], timeout: float = 30.0) -> bool:
    hexed = json.dumps(data, separators=(",", ":")).encode("utf-8").hex()
    command = "add-generic-password -U -a %s -s %s -X %s\n" % (shlex.quote(account), shlex.quote(service), hexed)
    try:
        if len(command) <= SECURITY_STDIN_LIMIT:
            res = run_cmd(["security", "-i"], input_str=command, timeout=timeout)
        else:
            res = run_cmd(["security", "add-generic-password", "-U", "-a", account, "-s", service, "-X", hexed],
                          timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0


def keychain_delete(service: str, account: str) -> bool:
    try:
        res = run_cmd(["security", "delete-generic-password", "-s", service, "-a", account])
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0


# -- tokens ---------------------------------------------------------------------------------------

def same_token(a: Any, b: Any) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(str(a), str(b))


def fingerprint(token: Any) -> Optional[str]:
    """One-way tag for a token (state files only; never printed)."""
    if not token:
        return None
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:16]


def now_ms() -> int:
    return int(time.time() * 1000)


def expiring(oauth: Optional[Dict[str, Any]], margin_ms: int = EXPIRY_BUFFER_MS) -> bool:
    if not oauth or not oauth.get("accessToken"):
        return True
    exp = oauth.get("expiresAt")
    return exp is not None and now_ms() + margin_ms >= int(exp)


def oauth_of(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    o = (data or {}).get("claudeAiOauth")
    return o if isinstance(o, dict) else None


# -- store items ----------------------------------------------------------------------------------

def read_store(item: str, account: Optional[str] = None, timeout: float = 30.0) -> Read:
    return keychain_read(item, account or current_username(), timeout)


def write_store_oauth(item: str, oauth: Dict[str, Any], account: Optional[str] = None,
                      timeout: float = 30.0, attempts: int = 3) -> None:
    """Replace claudeAiOauth in one store item and nothing else: the item's mcpOAuth (and any other
    key) is re-read and written back as it was. The item is read twice and written only if both reads
    agree, which narrows (it cannot close) the window in which an MCP token refresh by Claude Code,
    which does not take the OAuth refresh lock, could be overwritten. Raises StoreError."""
    account = account or current_username()
    for _ in range(attempts):
        cur = keychain_read(item, account, timeout)
        if cur.status == "error":
            raise StoreError("cannot read %s before writing it (%s)" % (item, cur.detail))
        data = dict(cur.data or {})
        data["claudeAiOauth"] = oauth
        again = keychain_read(item, account, timeout)
        if again.status == cur.status and again.data == cur.data:
            if not keychain_write(item, account, data, timeout):
                raise StoreError("cannot write %s" % item)
            return
    raise StoreBusy("%s kept changing while it was being written; nothing was written" % item)


def read_orca(account_id: str) -> Read:
    return keychain_read(ORCA_SERVICE, account_id)


def write_orca_oauth(account_id: str, oauth: Dict[str, Any], timeout: float = 30.0) -> bool:
    """Replace claudeAiOauth in an Orca account item, keeping its other keys, and read it back: a
    write-back that silently did not land would lose an account's only live chain."""
    cur = keychain_read(ORCA_SERVICE, account_id, timeout)
    if cur.status == "error":
        return False
    data = dict(cur.data or {})
    data["claudeAiOauth"] = oauth
    if not keychain_write(ORCA_SERVICE, account_id, data, timeout):
        return False
    check = oauth_of(keychain_read(ORCA_SERVICE, account_id, timeout).data)
    return bool(check) and same_token(check.get("refreshToken"), oauth.get("refreshToken"))


# -- Claude Code's refresh lock -------------------------------------------------------------------

def _reclaim_if_stale(path: Path) -> bool:
    """proper-lockfile's rule: a lock directory untouched for 60 s belongs to a dead holder."""
    try:
        age = time.time() - os.stat(path).st_mtime
        if age > LOCK_STALE_SECONDS:
            os.rmdir(path)
            return True
    except OSError:
        pass
    return False


def _lock_age(path: Path) -> str:
    try:
        return "%ds" % (time.time() - os.stat(path).st_mtime)
    except OSError:
        return "?"


@contextmanager
def claude_refresh_lock(config_dir: Optional[Path] = None, wait_seconds: float = 5.0):
    """Hold Claude Code's own refresh lock, so no session refreshes (and writes the store) while a
    switch rewrites it. Same two directories, same order, as Claude Code; a directory older than 60 s
    is reclaimed, as proper-lockfile does. Yields a function returning the seconds held: callers
    keep the hold far under the stale age, and if it ever passes 55 s the directories are left for
    stale reclamation rather than removed (by then Claude Code may own them). Raises LockBusy."""
    cfg = Path(config_dir or claude_config_dir())
    if not cfg.is_dir():
        raise StoreError("Claude config dir %s does not exist" % cfg)
    new = cfg / ".oauth_refresh.lock"
    legacy = Path(os.path.realpath(str(cfg)) + ".lock")
    deadline = time.monotonic() + wait_seconds
    held: List[Path] = []
    while True:
        try:
            os.mkdir(new)
            try:
                os.mkdir(legacy)
                held = [new, legacy]
                break
            except FileExistsError:
                os.rmdir(new)
                if _reclaim_if_stale(legacy):
                    continue
        except FileExistsError:
            if _reclaim_if_stale(new):
                continue
        if time.monotonic() >= deadline:
            raise LockBusy("a Claude Code process is refreshing its token (%s held for %s)" % (new.name, _lock_age(new)))
        time.sleep(0.1)
    start = time.monotonic()
    try:
        yield lambda: time.monotonic() - start
    finally:
        if time.monotonic() - start < LOCK_STALE_SECONDS - 5:
            for p in reversed(held):
                try:
                    os.rmdir(p)
                except OSError:
                    pass
