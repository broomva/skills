#!/usr/bin/env python3
"""
provider_manager.py — Claude subscription accounts: telemetry, one balancer, and a switch that
never kills a running session.

How a switch reaches running sessions (Claude Code 2.1.280, read from its bundled source and measured
with the real binary; see references/architecture.md): sessions re-read the credential store before
their requests, through a 30-second read cache, so whatever this tool writes there becomes every
running session's credential within about 30 s. A live credential is adopted in place. A stale one (a
consumed refresh token) kills every session at its next refresh. So:

- a switch writes only a target proven live (refreshed through its own copy, then identity-checked),
  and first saves the outgoing account's live tokens to its Orca item;
- it holds Claude Code's refresh lock while it rewrites the store item, and changes only
  claudeAiOauth (mcpOAuth untouched); the other item name (the mirror) is never written;
- this tool never refreshes a refresh token any store item holds, and refreshes only under the
  machine-wide lock, re-reading the store first;
- one balancer per machine (flock), an evaluation interval, a cooldown and hysteresis;
- telemetry that cannot be read is never a rate limit; "limited" is confirmed by a real probe;
- automatic switching runs only on Claude Code versions whose behaviour was measured.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import pm_state  # noqa: E402
from pm_store import (  # noqa: E402
    LockBusy,
    StoreBusy,
    StoreError,
    claude_config_dir,
    STORE_BASE,
    claude_refresh_lock,
    config_dir_override_running,
    current_username,
    expiring,
    fingerprint,
    LOCK_MAX_HOLD_SECONDS,
    keychain_delete,
    keychain_read,
    now_ms,
    oauth_of,
    read_orca,
    read_store,
    same_token,
    scoped_item_name,
    store_item_names,
    write_orca_oauth,
    write_store_oauth,
)

HOME = Path.home()
ORCA_DATA_PATH = HOME / "Library/Application Support/orca/profiles/local-default/orca-data.json"
CLAUDE_CONFIG_PATH = HOME / ".claude.json"
USAGE_CACHE_PATH = HOME / ".cache/broomva-provider-usage.json"
PROVIDER_EVENTS_PATH = HOME / ".cache/broomva-provider-events.jsonl"
STATE_PATH = HOME / ".cache/broomva-provider-state.json"
BALANCER_LOCK_PATH = HOME / ".cache/broomva-provider-balancer.lock"
STALLED_PATH = HOME / ".cache/broomva-provider-stalled.jsonl"
SETTLE_LOCK_PATH = HOME / ".cache/broomva-provider-settle.lock"
CONFIG_PATH = HOME / ".config/broomva/provider-manager.json"

USAGE_API_URL = "https://api.anthropic.com/api/oauth/usage"
PROFILE_API_URL = "https://api.anthropic.com/api/oauth/profile"
TOKEN_ENDPOINT_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
USER_AGENT = "Claude-Code/2.1.280"

CACHE_TTL_SECONDS = 90.0
CLAUDE_LOCK_WAIT_SECONDS = 5.0
LOCKED_IO_TIMEOUT = 5.0  # each keychain call made while holding Claude Code's refresh lock
LIMITED_HOLD_SECONDS = 3600.0  # a probe-confirmed limited account is not a failover target for this long
MODEL_WEEKLY_BUCKETS = ("seven_day_opus", "seven_day_sonnet")  # per-model weekly caps in the usage payload
_REFRESH_OUTCOME: Dict[str, str] = {}  # why the last refresh of an account did not happen (for messages)
PROBE_TIMEOUT_SECONDS = 90.0
PROBE_PROMPT = "Reply with the single word OK."
# The probe reads Claude Code's structured result first (`api_error_status`). These phrases are the
# fallback, matched against the result text and stderr only (never the whole JSON, whose numbers
# could contain "429"). Measured from the real 2.1.280 binary in tests/drill (probe scenario): a
# subscription limit prints "You've hit your session limit · resets 10:47pm (...)" with
# api_error_status 429; a dead grant prints "Failed to authenticate: OAuth session expired and could
# not be refreshed".
LIMIT_RE = re.compile(r"hit your [a-z ]*limit|usage limit reached|rate_limit_error|Request rejected \(429\)", re.I)
AUTH_DEAD_RE = re.compile(r"OAuth session expired and could not be refreshed|"
                          r"refresh token is no longer valid|invalid_grant", re.I)
VERIFIED_IDENTITY = ("orca_copy_match", "profile", "profile_cached")
# Claude Code versions whose credential behaviour (30 s store cache, refresh lock paths, item name,
# invalid_grant handling) was measured: binary source plus the tests/drill run. Automatic switching
# is observe-only on any other version until it is re-measured and added here or in the config.
MEASURED_CLAUDE_VERSIONS = ["2.1.280"]

DEFAULT_CONFIG: Dict[str, Any] = {
    "autoBalance": True,          # false: automatic evaluations log would_switch and never switch
    "threshold": 90.0,            # active 5-hour % that starts a proactive balance
    "weeklyThreshold": 97.0,      # active 7-day % that starts a proactive balance
    "standbyMax": 70.0,           # a standby must be at or under this 5-hour %...
    "margin": 25.0,               # ...and this many points under the active account
    "standbyWeeklyMax": 95.0,
    "cooldownMinutes": 30.0,      # between switches made for balance
    "failoverMinGapMinutes": 5.0,  # between switches made for a confirmed limit
    "evalIntervalSeconds": 120.0,  # hooks start at most one evaluation per interval, machine-wide
    "probeTtlSeconds": 600.0,
    "probeModel": None,           # None: Claude Code's default model, the one sessions run without --model
    "versionGate": True,          # automatic switching only on a measured Claude Code version
    "verifiedClaudeVersions": [],  # versions measured since (added to MEASURED_CLAUDE_VERSIONS)
}


class SwitchRefused(RuntimeError):
    """A switch was refused because it could break running sessions; the store is unchanged."""


# -- files ----------------------------------------------------------------------------------------

def _load_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(path: Path, data: Any, mode: Optional[int] = None) -> bool:
    """Atomic replace that writes through a symlink and keeps the file's mode (new files: 0600),
    unless a mode is given."""
    path = Path(os.path.realpath(str(path)))
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = os.stat(path).st_mode & 0o777
        except OSError:
            mode = 0o600
    tmp = path.with_name("%s.tmp.%d" % (path.name, os.getpid()))
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        return True
    except OSError as e:
        sys.stderr.write("Error saving %s: %s\n" % (path, e))
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _guarded_update(path: Path, fn) -> bool:
    """Read-modify-write a JSON file other programs also rewrite (~/.claude.json: every Claude Code
    session; orca-data.json: the Orca app). Skip when the file exists but does not parse (never
    replace a config with a fragment), and only write if nobody wrote it since this read."""
    for _ in range(3):
        try:
            before = os.stat(path).st_mtime_ns
        except OSError:
            before = None
        data = _load_json(path, None)
        if before is not None and not isinstance(data, dict):
            return False
        data = data if isinstance(data, dict) else {}
        fn(data)
        try:
            now_mtime = os.stat(path).st_mtime_ns
        except OSError:
            now_mtime = None
        if now_mtime == before:
            return _save_json(path, data)
        time.sleep(0.05)
    return False


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    loaded = _load_json(CONFIG_PATH, {})
    if isinstance(loaded, dict):
        cfg.update({k: v for k, v in loaded.items() if k in DEFAULT_CONFIG})
    if os.environ.get("PROVIDER_MANAGER_AUTO") == "0":
        cfg["autoBalance"] = False
    return cfg


def get_orca_data() -> Dict[str, Any]:
    data = _load_json(ORCA_DATA_PATH, None)
    if not isinstance(data, dict):
        return {"settings": {"claudeManagedAccounts": [], "activeClaudeManagedAccountId": None}}
    return data


def save_orca_data(data: Dict[str, Any]) -> bool:
    return _save_json(ORCA_DATA_PATH, data)


def get_claude_json() -> Dict[str, Any]:
    data = _load_json(CLAUDE_CONFIG_PATH, {})
    return data if isinstance(data, dict) else {}


def save_claude_json(data: Dict[str, Any]) -> bool:
    return _save_json(CLAUDE_CONFIG_PATH, data)


def read_usage_cache() -> Dict[str, Any]:
    data = _load_json(USAGE_CACHE_PATH, None)
    return data if isinstance(data, dict) else {"updatedAt": 0, "accounts": {}}


def save_usage_cache(data: Dict[str, Any]) -> bool:
    return _save_json(USAGE_CACHE_PATH, data, mode=0o600)


def log_provider_event(event_type: str, details: Dict[str, Any]) -> None:
    pm_state.log_event(PROVIDER_EVENTS_PATH, event_type, details)


def read_provider_events(limit: int = 20, kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    return pm_state.read_events(PROVIDER_EVENTS_PATH, limit=limit, kinds=kinds)


def load_state() -> Dict[str, Any]:
    return pm_state.load_state(STATE_PATH)


def update_state(fn) -> Dict[str, Any]:
    return pm_state.update_state(STATE_PATH, fn)


# -- network --------------------------------------------------------------------------------------

def _http(url: str, token: Optional[str] = None, body: Optional[Dict[str, Any]] = None,
          headers: Optional[Dict[str, str]] = None, timeout: float = 8.0) -> Tuple[Optional[int], Any, Dict[str, str]]:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        h["Authorization"] = "Bearer %s" % token
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return getattr(resp, "status", 200), (json.loads(raw) if raw else {}), dict(getattr(resp, "headers", {}) or {})
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read() or b"{}")
        except Exception:  # noqa: BLE001 - a body we cannot read is just absent
            payload = None
        return e.code, payload, dict(e.headers or {})
    except Exception:  # noqa: BLE001 - any transport failure is "unavailable"
        return None, None, {}


def fetch_profile(access_token: str) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """GET /api/oauth/profile (read-only; spends nothing). Same request Claude Code makes."""
    code, payload, _ = _http(PROFILE_API_URL, token=access_token,
                             headers={"Content-Type": "application/json", "Cache-Control": "no-cache"})
    return code, payload if isinstance(payload, dict) else None


def get_claude_auth_status() -> Dict[str, Any]:
    try:
        res = subprocess.run(["claude", "auth", "status"], text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return {"loggedIn": False, "error": type(e).__name__}
    match = re.search(r"\{[\s\S]*\}", res.stdout or "")
    if match:
        try:
            return json.loads(match.group(0))
        except ValueError:
            pass
    return {"loggedIn": False, "error": (res.stderr or "").strip()[:200]}


# -- accounts and the store's identity ------------------------------------------------------------

def roster() -> List[Dict[str, Any]]:
    return list(get_orca_data().get("settings", {}).get("claudeManagedAccounts", []) or [])


def orca_active_id() -> Optional[str]:
    return get_orca_data().get("settings", {}).get("activeClaudeManagedAccountId")


def _match_roster(profile: Dict[str, Any], accounts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The roster account a profile names, or None when it is ambiguous. With an email, the email
    must match exactly one account and that account's org (when both are known) must agree; the org
    alone decides only when the profile carries no email. Two people in one team org share an org."""
    email = ((profile.get("account") or {}).get("email") or "").lower()
    org = (profile.get("organization") or {}).get("uuid")
    if email:
        hits = [a for a in accounts if (a.get("email") or "").lower() == email]
        if len(hits) != 1:
            return None
        known_org = hits[0].get("organizationUuid")
        return hits[0] if not (org and known_org and org != known_org) else None
    by_org = [a for a in accounts if org and a.get("organizationUuid") == org]
    return by_org[0] if len(by_org) == 1 else None


def build_context(verify_identity: bool = True) -> Dict[str, Any]:
    """One read of everything a decision needs: roster, each Orca copy, the store items, and which
    account the store holds (and how we know)."""
    accounts = roster()
    copies = {a["id"]: read_orca(a["id"]) for a in accounts if a.get("id")}
    primary, mirrors = store_item_names()
    user = current_username()
    store = read_store(primary, user)
    mirror_reads = [read_store(m, user) for m in mirrors]
    # Protected unconditionally: the primary and, if it is the mirror, the unscoped item (what every
    # session without CLAUDE_CONFIG_DIR reads). A scoped mirror is protected only while a Claude Code
    # process is configured to read it (see refresh_account_token).
    unconditional = [store] + [r for m, r in zip(mirrors, mirror_reads) if m == STORE_BASE]
    scoped = [r for m, r in zip(mirrors, mirror_reads) if m != STORE_BASE]
    def rts(reads):
        return [o["refreshToken"] for o in (oauth_of(r.data) for r in reads) if o and o.get("refreshToken")]

    ctx = {
        "accounts": accounts, "copies": copies, "primary": primary, "mirrors": mirrors, "user": user,
        "store": store, "storeOauth": oauth_of(store.data), "storeRts": rts(unconditional),
        "mirrorRts": rts(scoped),
        "storeReadable": store.status != "error" and all(r.status != "error" for r in mirror_reads),
    }
    ctx["storeAccountId"], ctx["storeIdentity"] = identify_store_account(ctx, verify=verify_identity)
    return ctx


def identify_store_account(ctx: Dict[str, Any], verify: bool = True) -> Tuple[Optional[str], str]:
    oauth = ctx["storeOauth"]
    if ctx["store"].status == "error":
        return orca_active_id(), "store_unreadable"
    if not oauth:
        return None, "store_empty"
    rt = oauth.get("refreshToken")
    for acc in ctx["accounts"]:
        copy = oauth_of(ctx["copies"].get(acc.get("id")).data) if ctx["copies"].get(acc.get("id")) else None
        if copy and same_token(copy.get("refreshToken"), rt):
            return acc["id"], "orca_copy_match"
    cached = load_state().get("storeIdentity") or {}
    if rt and cached.get("fingerprint") == fingerprint(rt) and cached.get("accountId"):
        return cached["accountId"], "profile_cached"
    if verify and oauth.get("accessToken") and not expiring(oauth, 60_000):
        code, prof = fetch_profile(oauth["accessToken"])
        if code == 200 and prof:
            acc = _match_roster(prof, ctx["accounts"])
            if acc:
                update_state(lambda s: s.__setitem__("storeIdentity", {
                    "fingerprint": fingerprint(rt), "accountId": acc["id"], "verifiedAt": time.time()}))
                return acc["id"], "profile"
            return None, "profile_unknown_account"
    return orca_active_id(), "orca_setting_unverified"


def list_accounts(ctx: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    ctx = ctx or build_context(verify_identity=False)
    health = load_state().get("health", {})
    out = []
    for acc in ctx["accounts"]:
        acc_id = acc.get("id")
        copy = oauth_of(ctx["copies"][acc_id].data) if acc_id in ctx["copies"] else None
        is_active = acc_id == ctx["storeAccountId"]
        source = ctx["storeOauth"] if is_active and ctx["storeOauth"] else copy
        out.append({
            "id": acc_id,
            "email": acc.get("email"),
            "organizationName": acc.get("organizationName"),
            "organizationUuid": acc.get("organizationUuid"),
            "isActive": is_active,
            "activeSource": ctx["storeIdentity"] if is_active else None,
            "hasStoredCredentials": bool(copy and copy.get("accessToken")),
            "expiresAt": (copy or {}).get("expiresAt"),
            "isTokenFresh": bool(copy) and not expiring(copy, 0),
            "subscriptionType": (source or {}).get("subscriptionType"),
            "needsLogin": bool((health.get(acc_id) or {}).get("needsLogin")),
        })
    return out


# -- refresh (never the store's chain) ------------------------------------------------------------

def _mark_health(account_id: str, needs_login: bool, reason: str) -> None:
    def put(s):
        h = s.setdefault("health", {})
        if needs_login:
            h[account_id] = {"needsLogin": True, "reason": reason, "since": time.time()}
        else:
            h.pop(account_id, None)
    update_state(put)


def refresh_account_token(account_id: str, allow_unverified: bool = False) -> Optional[Dict[str, Any]]:
    """Refresh an account's Orca copy and persist the rotated pair to that copy FIRST (read back).

    Runs only under the machine-wide balancer lock (non-blocking: if another provider-manager action
    holds it, nothing is refreshed), and re-reads every store item immediately before spending the
    refresh token, so a switch that just moved this account into the store is always seen. Refuses
    the store's account, any refresh token equal to one a store item holds, and, unless
    allow_unverified (the store credential was proven dead, or an operator forced it), any refresh
    while the store's account cannot be identified. Returns the new claudeAiOauth, or None."""
    with pm_state.balancer_lock(BALANCER_LOCK_PATH, blocking=False, holder="refresh") as held:
        if not held:
            _REFRESH_OUTCOME[account_id] = "balancer_busy"
            log_provider_event("refresh.deferred", {"accountId": account_id, "reason": "balancer_busy"})
            return None
        ctx = build_context(verify_identity=True)
        refusal = None
        if not ctx["storeReadable"]:
            refusal = "store_unreadable"
        elif ctx["storeAccountId"] and account_id == ctx["storeAccountId"]:
            refusal = "store_account"
        elif ctx["storeIdentity"] not in VERIFIED_IDENTITY + ("store_empty",) and not allow_unverified:
            refusal = "store_identity_unverified"
        copy = ctx["copies"].get(account_id)
        oauth = oauth_of(copy.data) if copy is not None and copy.status == "ok" else None
        if not refusal and (not oauth or not oauth.get("refreshToken")):
            return None
        if not refusal and any(same_token(oauth["refreshToken"], rt) for rt in ctx["storeRts"]):
            refusal = "refresh_token_in_store"
        if not refusal and any(same_token(oauth["refreshToken"], rt) for rt in ctx["mirrorRts"]) \
                and config_dir_override_running(claude_config_dir()):
            refusal = "refresh_token_in_mirror_with_a_reader"
        if refusal:
            _REFRESH_OUTCOME[account_id] = refusal
            log_provider_event("refresh.refused", {"accountId": account_id, "reason": refusal})
            return None
        code, payload, _ = _http(TOKEN_ENDPOINT_URL, body={
            "client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": oauth["refreshToken"]}, timeout=10.0)
        if code != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
            if code == 400 and isinstance(payload, dict) and payload.get("error") == "invalid_grant":
                now_copy = oauth_of(read_orca(account_id).data)
                if now_copy and not same_token(now_copy.get("refreshToken"), oauth["refreshToken"]):
                    log_provider_event("refresh.failed", {"accountId": account_id, "reason": "copy_changed_meanwhile"})
                    return None  # another writer refreshed this copy; it is not dead
                _REFRESH_OUTCOME[account_id] = "invalid_grant"
                _mark_health(account_id, True, "invalid_grant")
                log_provider_event("refresh.failed", {"accountId": account_id, "reason": "invalid_grant", "needsLogin": True})
            else:
                log_provider_event("refresh.failed", {"accountId": account_id, "reason": "http_%s" % code})
            return None
        new = dict(oauth)
        new["accessToken"] = payload["access_token"]
        new["refreshToken"] = payload.get("refresh_token") or oauth["refreshToken"]
        try:
            new["expiresAt"] = now_ms() + int(payload.get("expires_in", 3600)) * 1000
        except (TypeError, ValueError):
            new["expiresAt"] = now_ms() + 3600 * 1000
        if isinstance(payload.get("scope"), str) and payload["scope"]:
            new["scopes"] = payload["scope"].split()
        if not write_orca_oauth(account_id, new):
            log_provider_event("refresh.persist_failed", {"accountId": account_id, "severity": "critical"})
            return None
        _mark_health(account_id, False, "refreshed")
        log_provider_event("refresh", {"accountId": account_id})
        return new


# -- telemetry (unreadable is never "limited") ----------------------------------------------------

def _numbers_entry(account_id: str, data: Dict[str, Any], now: float) -> Optional[Dict[str, Any]]:
    """Usage numbers, or None when the payload is not the shape this code knows (never a guess)."""
    try:
        return _parse_numbers(account_id, data, now)
    except (TypeError, ValueError, AttributeError):
        return None


def _parse_numbers(account_id: str, data: Dict[str, Any], now: float) -> Dict[str, Any]:
    fh = data.get("five_hour") or {}
    sd = data.get("seven_day") or {}
    fh_util = float(fh.get("utilization", fh.get("used_percentage", 0.0)) or 0.0)
    sd_util = float(sd.get("utilization", sd.get("used_percentage", 0.0)) or 0.0)
    locked = fh.get("locked_reason") or sd.get("locked_reason")
    for lim in data.get("limits") or []:
        if lim.get("is_active") and (lim.get("percent") or 0) >= 100:
            locked = locked or "%s_limit_reached" % lim.get("group", "usage")
    for key, bucket in data.items():  # per-model weekly caps
        if key in MODEL_WEEKLY_BUCKETS and isinstance(bucket, dict) \
                and float(bucket.get("utilization", bucket.get("used_percentage", 0)) or 0) >= 100.0:
            locked = locked or "%s_limit_reached" % key
    limited = bool(locked or fh_util >= 100.0 or sd_util >= 100.0)
    if limited:
        status = "limited"
    elif fh_util >= 95.0 or sd_util >= 98.0:
        status = "critical"
    elif fh_util >= 80.0 or sd_util >= 85.0:
        status = "warning"
    else:
        status = "ok"
    return {
        "id": account_id, "cachedAt": now, "numbersAt": now, "telemetry": "ok", "stale": False,
        "five_hour": {"utilization": round(fh_util, 1), "resets_at": fh.get("resets_at")},
        "seven_day": {"utilization": round(sd_util, 1), "resets_at": sd.get("resets_at")},
        "isRateLimited": limited, "lockedReason": locked if limited else None, "status": status,
    }


def _degraded_entry(account_id: str, telemetry: str, prev: Optional[Dict[str, Any]], now: float,
                    error: str = "") -> Dict[str, Any]:
    """Telemetry failed. Keep the last numbers for display, marked stale, and claim nothing about
    limits: isRateLimited is False because it is unknown."""
    entry = {"id": account_id, "cachedAt": now, "telemetry": telemetry, "status": telemetry, "stale": True,
             "isRateLimited": False, "lockedReason": None, "error": error,
             "five_hour": None, "seven_day": None, "numbersAt": None}
    if prev and prev.get("numbersAt"):
        entry.update({k: prev.get(k) for k in ("five_hour", "seven_day", "numbersAt")})
    return entry


def _note_429(account_id: str, retry_after: Optional[str], now: float) -> float:
    holder: Dict[str, float] = {}

    def put(s):
        t = s.setdefault("telemetry", {}).setdefault(account_id, {})
        step = int(t.get("backoffStep", 0))
        try:
            wait = float(retry_after) if retry_after else min(1800.0, 120.0 * (2 ** step))
        except ValueError:
            wait = min(1800.0, 120.0 * (2 ** step))
        t.update({"backoffUntil": now + wait, "backoffStep": step + 1, "last429At": now})
        holder["until"] = now + wait
    update_state(put)
    return holder["until"]


def _clear_backoff(account_id: str) -> None:
    if (load_state().get("telemetry", {}).get(account_id) or {}).get("backoffStep"):
        update_state(lambda s: s.setdefault("telemetry", {}).pop(account_id, None))


def fetch_account_usage(account_id: str, force_refresh: bool = False, max_retries: int = 1,
                        ctx: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """5-hour/7-day usage for one account, with a `telemetry` status: ok | throttled | auth_expired
    | unavailable | no_credentials | needs_login. Only `ok` numbers can mark an account limited."""
    now = time.time()
    cache = read_usage_cache()
    prev = cache.get("accounts", {}).get(account_id)
    if not force_refresh and prev and (now - prev.get("cachedAt", 0)) < CACHE_TTL_SECONDS and "telemetry" in prev:
        return prev
    ctx = ctx or build_context(verify_identity=False)

    def done(entry):
        cache.setdefault("accounts", {})[account_id] = entry
        cache["updatedAt"] = now
        save_usage_cache(cache)
        return entry

    backoff = (load_state().get("telemetry", {}).get(account_id) or {}).get("backoffUntil", 0)
    if backoff > now:
        return done(_degraded_entry(account_id, "throttled", prev, now, "usage endpoint 429; backing off"))

    is_store_account = account_id == ctx["storeAccountId"]
    if is_store_account:
        oauth = ctx["storeOauth"]
        if not oauth or expiring(oauth, 0):
            # Claude Code refreshes this chain on its next request; this tool never does.
            return done(_degraded_entry(account_id, "auth_expired", prev, now, "store token expired"))
    else:
        copy = ctx["copies"].get(account_id)
        oauth = oauth_of(copy.data) if copy else None
        if not oauth:
            return done(_degraded_entry(account_id, "no_credentials", prev, now))
        if expiring(oauth, 60_000):
            fresh = refresh_account_token(account_id) if ctx["storeReadable"] else None
            if not fresh:
                needs = (load_state().get("health", {}).get(account_id) or {}).get("needsLogin")
                return done(_degraded_entry(account_id, "needs_login" if needs else "auth_expired", prev, now))
            oauth = fresh

    code, payload, headers = _http(USAGE_API_URL, token=oauth["accessToken"],
                                   headers={"anthropic-version": "2023-06-01"}, timeout=5.0)
    entry = _numbers_entry(account_id, payload, now) if code == 200 and isinstance(payload, dict) else None
    if entry:
        _clear_backoff(account_id)
        return done(entry)
    if code == 200:
        return done(_degraded_entry(account_id, "unavailable", prev, now, "usage payload not understood"))
    if code == 429:
        until = _note_429(account_id, headers.get("Retry-After") or headers.get("retry-after"), now)
        log_provider_event("telemetry.throttled", {"accountId": account_id, "backoffUntil": int(until)})
        return done(_degraded_entry(account_id, "throttled", prev, now, "usage endpoint 429"))
    if code == 401 and not is_store_account and max_retries > 0 and ctx["storeReadable"]:
        if refresh_account_token(account_id):
            return fetch_account_usage(account_id, True, max_retries - 1, build_context(verify_identity=False))
    if code == 401:
        return done(_degraded_entry(account_id, "auth_expired", prev, now, "usage endpoint 401"))
    return done(_degraded_entry(account_id, "unavailable", prev, now, "usage endpoint %s" % code))


def fetch_all_usage(force_refresh: bool = False, ctx: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    ctx = ctx or build_context(verify_identity=True)
    results = []
    for acc in list_accounts(ctx):
        usage = fetch_account_usage(acc["id"], force_refresh=force_refresh, ctx=ctx) or {}
        info = dict(acc)
        info["usage"] = usage or None
        info["telemetry"] = usage.get("telemetry", "unavailable")
        info["fiveHourUtil"] = (usage.get("five_hour") or {}).get("utilization")
        info["sevenDayUtil"] = (usage.get("seven_day") or {}).get("utilization")
        info["fiveHourResetsAt"] = (usage.get("five_hour") or {}).get("resets_at")
        info["sevenDayResetsAt"] = (usage.get("seven_day") or {}).get("resets_at")
        info["usageStatus"] = usage.get("status", "unavailable")
        info["isRateLimited"] = bool(usage.get("isRateLimited")) and usage.get("telemetry") == "ok"
        info["stale"] = bool(usage.get("stale"))
        results.append(info)
    return results


# -- probe (is the active account really limited?) ------------------------------------------------

def _probe_env() -> Dict[str, str]:
    """The hook's environment minus everything that ties a process to a session or changes auth.
    CLAUDE_CONFIG_DIR is kept as is, so the probe reads the same store as the sessions."""
    drop_prefixes = ("CLAUDE_CODE_",)
    drop = {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL"}
    env = {k: v for k, v in os.environ.items() if k not in drop and not k.startswith(drop_prefixes)}
    env["PROVIDER_MANAGER_PROBE"] = "1"
    return env


def probe_active_account() -> Tuple[str, str]:
    """Run one tiny real request through Claude Code itself, on the live store, with no hooks, tools
    or MCP servers, on the model the sessions use (Claude Code's default unless `probeModel` is set:
    a per-model weekly cap must not hide behind a cheaper model). Returns ("ok" | "limited" |
    "auth_dead" | "unknown", detail). "auth_dead": Claude Code itself was refused the store's refresh
    token, so that credential is dead."""
    claude = shutil.which("claude", path=os.environ.get("PATH")) or "claude"
    cmd = [claude, "-p", PROBE_PROMPT, "--tools", "", "--strict-mcp-config", "--setting-sources", "project",
           "--no-session-persistence", "--output-format", "json"]
    model = load_config().get("probeModel")
    if model:
        cmd += ["--model", str(model)]
    try:
        with tempfile.TemporaryDirectory(prefix="pm-probe-") as cwd:
            res = subprocess.run(cmd, cwd=cwd, env=_probe_env(), text=True, capture_output=True,
                                 timeout=PROBE_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as e:
        return "unknown", "probe failed to run: %s" % type(e).__name__
    text = res.stdout or ""
    result = None
    for line in reversed(text.strip().splitlines()):
        try:
            result = json.loads(line)
            break
        except ValueError:
            continue
    if res.returncode == 0 and isinstance(result, dict) and not result.get("is_error"):
        return "ok", "probe answered"
    if isinstance(result, dict) and result.get("api_error_status") == 429:
        return "limited", "probe got HTTP 429 (%s)" % str(result.get("result") or "")[:80]
    message = str(result.get("result") or "") if isinstance(result, dict) else text[-400:]
    blob = " ".join([message, (res.stderr or "")[-400:]])
    if LIMIT_RE.search(blob):
        return "limited", "probe hit a limit"
    if AUTH_DEAD_RE.search(blob):
        return "auth_dead", "Claude Code could not refresh the store's credential"
    return "unknown", "probe rc %d" % res.returncode


def probe_cached(account_id: str, ttl: float, fresh_after: float = 0.0,
                 resets_at: Optional[str] = None, five_hour: Optional[float] = None) -> Tuple[str, str]:
    """A probe result from the last `ttl` seconds (30 s for "unknown"), unless it predates
    fresh_after: a report newer than the cached probe gets a new probe. A probe is stamped with the
    time it STARTED, so a report that lands while it runs is never answered by it."""
    p = (load_state().get("probes") or {}).get(account_id) or {}
    age_ok = time.time() - p.get("at", 0) < (30.0 if p.get("result") == "unknown" else ttl)
    if p and age_ok and p.get("at", 0) >= fresh_after:
        return p.get("result", "unknown"), "cached"
    started = time.time()
    result, detail = probe_active_account()
    update_state(lambda s: s.setdefault("probes", {}).__setitem__(
        account_id, {"at": started, "result": result, "detail": detail, "resetsAt": resets_at,
                     "fiveHourAtProbe": five_hour}))
    log_provider_event("probe", {"accountId": account_id, "result": result, "detail": detail})
    return result, detail


def _claude_binary() -> Optional[str]:
    return shutil.which("claude", path=os.environ.get("PATH")) or shutil.which("claude", path=str(HOME / ".local/bin"))


def claude_version() -> Optional[str]:
    """`claude --version` of the binary on PATH (else ~/.local/bin), cached per resolved binary path
    for an hour; a failed check is cached for a minute only."""
    claude = _claude_binary()
    if not claude:
        return None
    real = os.path.realpath(claude)
    cached = load_state().get("claudeVersion") or {}
    ttl = 3600 if cached.get("version") else 60
    if cached.get("path") == real and time.time() - cached.get("at", 0) < ttl:
        return cached.get("version")
    try:
        res = subprocess.run([claude, "--version"], text=True, capture_output=True, timeout=20, env=_probe_env())
        m = re.search(r"\d+\.\d+\.\d+", res.stdout or "")
        version = m.group(0) if m else None
    except (OSError, subprocess.SubprocessError):
        version = None
    update_state(lambda s: s.__setitem__("claudeVersion", {"path": real, "version": version, "at": time.time()}))
    return version


def version_verified(cfg: Dict[str, Any], version: Optional[str] = None, check: bool = True) -> Tuple[bool, Optional[str]]:
    if not cfg.get("versionGate", True):
        return True, None
    if check:
        version = claude_version()
    return version in MEASURED_CLAUDE_VERSIONS + list(cfg.get("verifiedClaudeVersions") or []), version


def gate_status() -> Optional[str]:
    """A one-line warning when automatic switching is paused by the version gate, from the cached
    check only (no subprocess: the hook calls this). None when it is not paused."""
    cfg = load_config()
    cached = load_state().get("claudeVersion") or {}
    if not cached:
        return None
    ok, version = version_verified(cfg, cached.get("version"), check=False)
    if ok:
        return None
    return "automatic switching paused: Claude Code %s is not a measured version (%s)" % (
        version or "unknown", ", ".join(MEASURED_CLAUDE_VERSIONS + list(cfg.get("verifiedClaudeVersions") or [])))


# -- switch ---------------------------------------------------------------------------------------

def _validate_target(target: Dict[str, Any], allow_unverified: bool = False) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Prove the target's credential is live and is the target, without touching the store: refresh
    it through its own copy (proving the refresh token is unspent, and persisting the rotated pair to
    the copy first), then check that the new access token's profile names that account."""
    _REFRESH_OUTCOME.pop(target["id"], None)
    oauth = refresh_account_token(target["id"], allow_unverified=allow_unverified)
    if not oauth:
        why = _REFRESH_OUTCOME.get(target["id"], "refresh failed")
        hint = " (re-login it: login-headless --email %s)" % target["email"] if why == "invalid_grant" else ""
        return False, None, "its stored grant could not be refreshed: %s%s" % (why, hint)
    code, prof = fetch_profile(oauth["accessToken"])
    if code != 200 or not prof:
        return False, None, "its credential could not be verified (profile HTTP %s)" % code
    match = _match_roster(prof, roster())
    if not match or match.get("id") != target["id"]:
        return False, None, "its stored credential belongs to a different account"
    return True, oauth, "ok"


def _same_chain(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> bool:
    if not a or not b:
        return a == b
    return same_token(a.get("refreshToken"), b.get("refreshToken")) and same_token(a.get("accessToken"), b.get("accessToken"))


def switch_account(identifier: str, source: str = "manual", metadata: Optional[Dict[str, Any]] = None,
                   force: bool = False, store_proven_dead: bool = False) -> Dict[str, Any]:
    """Point the store (and so every running session) at another account, safely. Raises
    SwitchRefused, leaving the store untouched, when that could break a running session."""
    with pm_state.trace(), pm_state.balancer_lock(BALANCER_LOCK_PATH, blocking=True, timeout=60.0,
                                                  holder="switch:%s" % source) as held:
        if not held:
            raise SwitchRefused("another provider-manager action holds the balancer lock")
        try:
            return _switch_locked(identifier, source, metadata or {}, force, store_proven_dead)
        except SwitchRefused as e:
            log_provider_event("switch.refused", {"target": identifier, "source": source, "reason": str(e)})
            raise


def _switch_locked(identifier: str, source: str, metadata: Dict[str, Any], force: bool,
                   store_proven_dead: bool = False) -> Dict[str, Any]:
    accounts = roster()
    target = next((a for a in accounts if a.get("id") == identifier
                   or (a.get("email") or "").lower() == identifier.lower()), None)
    if not target:
        raise ValueError("Account '%s' not found in managed accounts roster." % identifier)
    ctx = build_context(verify_identity=True)
    if not ctx["storeReadable"]:
        raise SwitchRefused("the credential store could not be read (%s); nothing was written" % ctx["store"].detail)
    tcopy = ctx["copies"].get(target["id"])
    if tcopy is None or tcopy.status == "error":
        raise SwitchRefused("the target's stored credential could not be read")
    t_oauth = oauth_of(tcopy.data)
    if not t_oauth or not t_oauth.get("accessToken"):
        raise RuntimeError("No credentials stored in Keychain for account %s (%s). Run 'login-headless --email %s' first."
                           % (target["email"], target["id"], target["email"]))
    store_oauth = ctx["storeOauth"]
    out_id, how = ctx["storeAccountId"], ctx["storeIdentity"]
    out_email = next((a.get("email") for a in accounts if a.get("id") == out_id), None)

    if out_id == target["id"] and how in VERIFIED_IDENTITY:
        if how != "orca_copy_match" and store_oauth and not write_orca_oauth(target["id"], store_oauth):
            log_provider_event("writeback.failed", {"accountId": target["id"]})  # the store holds a newer link
        _record_active(target)
        return {"success": True, "switchedTo": target["email"], "accountId": target["id"], "alreadyActive": True}

    write_back = None
    if store_oauth and (store_oauth.get("refreshToken") or store_oauth.get("accessToken")):
        if how in ("profile", "profile_cached") and out_id:
            write_back = out_id
        elif how != "orca_copy_match":
            if not (force or store_proven_dead):
                raise SwitchRefused(
                    "the store holds a credential that matches no Orca copy and cannot be identified (%s); "
                    "switching would discard it. Run any `claude -p` to refresh it, or pass --force." % how)
            log_provider_event("switch.discard_unverified", {
                "identity": how, "why": "proven dead by the probe" if store_proven_dead else "--force"})

    if store_proven_dead:
        write_back = None  # Claude Code proved the store's chain dead: never bury the copy's under it
    ok, live_oauth, why = _validate_target(target, allow_unverified=bool(force or store_proven_dead))
    if not ok:
        raise SwitchRefused("%s is not safe to switch to: %s" % (target["email"], why))

    attempted = False
    try:
        with claude_refresh_lock(claude_config_dir(), CLAUDE_LOCK_WAIT_SECONDS) as held_for:
            now_store = read_store(ctx["primary"], ctx["user"], LOCKED_IO_TIMEOUT)
            if now_store.status == "error":
                raise SwitchRefused("the credential store became unreadable; nothing was written")
            if not _same_chain(oauth_of(now_store.data), store_oauth):
                raise SwitchRefused("the store changed while the switch was being prepared; retry")
            if write_back and not write_orca_oauth(write_back, store_oauth, LOCKED_IO_TIMEOUT):
                raise SwitchRefused("could not save the outgoing account's live tokens; nothing was switched")
            if held_for() > LOCK_MAX_HOLD_SECONDS:
                raise SwitchRefused("the keychain is too slow to switch safely inside Claude Code's refresh lock")
            try:
                attempted = True
                write_store_oauth(ctx["primary"], live_oauth, ctx["user"], LOCKED_IO_TIMEOUT, attempts=1)
            except StoreBusy as e:
                attempted = False  # nothing was written
                raise SwitchRefused("the store changed or could not be read while it was being written "
                                    "(%s); retry" % e)
            check = oauth_of(read_store(ctx["primary"], ctx["user"], LOCKED_IO_TIMEOUT).data)
            if not check or not same_token(check.get("refreshToken"), live_oauth.get("refreshToken")):
                raise StoreError("the store was written but did not read back the new credential; "
                                 "`list` shows which account it holds")
    except LockBusy as e:
        raise SwitchRefused(str(e))
    except StoreError as e:
        if attempted:  # the store may hold the target now: keep the cooldown, say so
            update_state(lambda s: s.__setitem__("lastSwitch", {
                "at": time.time(), "from": out_id, "to": target["id"], "source": source, "unverified": True}))
            log_provider_event("switch.unverified", {"toAccount": target["email"], "fromAccount": out_email,
                                                     "source": source, "error": str(e)})
        raise

    _record_active(target)
    now = time.time()
    update_state(lambda s: s.__setitem__("lastSwitch", {
        "at": now, "from": out_id, "to": target["id"], "source": source}))
    _mark_health(target["id"], False, "switched")
    event = {"toAccount": target["email"], "accountId": target["id"], "fromAccount": out_email,
             "source": source, "wroteBack": bool(write_back), "outgoingIdentity": how}
    event.update(metadata)
    log_provider_event("switch", event)
    return {"success": True, "switchedTo": target["email"], "accountId": target["id"],
            "fromAccount": out_email, "wroteBack": bool(write_back)}


def _record_active(target: Dict[str, Any]) -> None:
    """Display hints only (the store is the truth): ~/.claude.json's oauthAccount and Orca's active id."""
    def claude_hint(cfg):
        acc = cfg.get("oauthAccount") or {}
        acc.update({"emailAddress": target.get("email"), "organizationUuid": target.get("organizationUuid"),
                    "organizationName": target.get("organizationName"), "profileFetchedAt": now_ms()})
        cfg["oauthAccount"] = acc

    def orca_active(orca):
        orca.setdefault("settings", {})["activeClaudeManagedAccountId"] = target.get("id")
        for acc in orca["settings"].get("claudeManagedAccounts", []):
            if acc.get("id") == target.get("id"):
                acc["updatedAt"] = now_ms()
    for path, fn in ((CLAUDE_CONFIG_PATH, claude_hint), (ORCA_DATA_PATH, orca_active)):
        if not _guarded_update(path, fn):
            log_provider_event("record_active.skipped", {"file": path.name})


def _parse_ts(value: Any) -> Optional[float]:
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _window_reset_since(probe: Dict[str, Any], account: Dict[str, Any], now: float) -> bool:
    """Has the limit the probe found ended with a 5-hour window reset? Only when the 5-hour bucket
    was the limit at probe time (a per-model cap survives a 5-hour reset), and only by time: the reset
    seen at probe time has passed, or the account now reports a reset more than a minute later. The
    live endpoint returns microsecond timestamps that vary between calls, so strings are never compared."""
    if float(probe.get("fiveHourAtProbe") or 0) < 100.0:
        return False
    at_probe = _parse_ts(probe.get("resetsAt"))
    if at_probe is None:
        return False
    if at_probe <= now:
        return True
    current = _parse_ts(account.get("fiveHourResetsAt"))
    return current is not None and current > at_probe + 60


def _standby_ok(a: Dict[str, Any], cfg: Dict[str, Any], active_fh: Optional[float] = None) -> bool:
    """A standby the balancer may move to: readable numbers, a live grant, not limited, under
    standbyMax, and (for balance, not failover) at least `margin` points under the active account."""
    fh, sd = a.get("fiveHourUtil"), a.get("sevenDayUtil")
    return bool(a.get("telemetry") == "ok" and a.get("hasStoredCredentials") and not a.get("needsLogin")
                and not a.get("isRateLimited") and fh is not None and fh <= cfg["standbyMax"]
                and (sd is None or sd < cfg["standbyWeeklyMax"])
                and (active_fh is None or fh <= active_fh - cfg["margin"]))


# -- the balancer ---------------------------------------------------------------------------------

def balance_accounts(threshold: Optional[float] = None, dry_run: bool = False, verbose: bool = False,
                     source: str = "proactive_balance", signal: Optional[str] = None,
                     blocking: bool = True, automatic: bool = False) -> Dict[str, Any]:
    """Decide whether to move the machine to another account, and do it safely if so.

    Switches only when (a) the active account's readable numbers are over threshold and a standby is
    clearly healthier (hysteresis), outside the cooldown; or (b) the active account is limited, by
    readable numbers or a reported rate limit, AND a real probe confirms it; or (c) a session reported
    an auth failure AND the probe shows Claude Code itself cannot refresh the store's credential."""
    with pm_state.trace(), pm_state.balancer_lock(BALANCER_LOCK_PATH, blocking=blocking, timeout=30.0,
                                                  holder="balance:%s" % source) as held:
        if not held:
            return {"success": True, "action": "none", "reason": "busy"}
        res = _balance_locked(threshold, dry_run, verbose, source, signal, automatic)
        log_provider_event("balance.decision", {k: res.get(k) for k in (
            "action", "reason", "fromAccount", "toAccount", "activeAccount", "utilization",
            "standbyUtilization", "telemetry", "probe", "remainingSeconds") if res.get(k) is not None}
            | {"source": source, "signal": signal, "dryRun": dry_run})
        return res


def _balance_locked(threshold: Optional[float], dry_run: bool, verbose: bool, source: str,
                    signal: Optional[str], automatic: bool) -> Dict[str, Any]:
    cfg = load_config()
    threshold = float(threshold if threshold is not None else cfg["threshold"])
    now = time.time()
    state = load_state()
    if state.get("holdUntil", 0) > now:
        return {"success": True, "action": "none", "reason": "hold", "remainingSeconds": int(state["holdUntil"] - now)}
    # A reported limit stays pending until an evaluation can act on it (a switch, or a probe showing
    # the account is fine) or it expires; a cooldown, a busy lock or a dry run must not swallow it.
    pending = [p for p in state.get("pendingSignals", []) if now - p.get("at", 0) < 900]
    if pending:
        signal = signal or pending[-1].get("type")

    def resolve_signals():
        if pending and not dry_run:  # exactly the reports this evaluation saw; any other stays
            seen = [(p.get("type"), p.get("at"), p.get("sessionId")) for p in pending]
            update_state(lambda s: s.__setitem__("pendingSignals", [
                p for p in s.get("pendingSignals", []) if (p.get("type"), p.get("at"), p.get("sessionId")) not in seen]))

    ctx = build_context(verify_identity=True)
    accounts = fetch_all_usage(ctx=ctx)
    if len(accounts) < 2:
        return {"success": True, "action": "none", "reason": "single_account",
                "message": "Only 1 account configured in roster."}

    probes = state.get("probes") or {}

    def healthy(a, active_fh=None):
        p = probes.get(a.get("id")) or {}
        if p.get("result") == "limited" and now - p.get("at", 0) < LIMITED_HOLD_SECONDS \
                and not _window_reset_since(p, a, now):
            return False  # its numbers may look fine (a per-model cap); the probe said otherwise
        return _standby_ok(a, cfg, active_fh)

    def rank(a):
        return (a.get("fiveHourUtil"), a.get("sevenDayUtil") or 0.0)

    active = next((a for a in accounts if a.get("isActive")), None)
    if not active:
        if automatic:  # an empty store may be a deliberate /logout; never log back in on our own
            return {"success": True, "action": "none", "reason": "no_active_account"}
        cands = [a for a in accounts if healthy(a)]
        if not cands:
            return {"success": False, "action": "none", "reason": "no_active_account",
                    "error": "The store holds no roster account and no standby is healthy."}
        best = min(cands, key=rank)
        return _do_switch(best, None, "no_active_account", dry_run, automatic, cfg, source, {})

    fh, sd = active.get("fiveHourUtil"), active.get("sevenDayUtil")
    readable = active.get("telemetry") == "ok"
    limited_by_numbers = readable and active.get("isRateLimited")
    over = readable and ((fh is not None and fh >= threshold) or (sd is not None and sd >= cfg["weeklyThreshold"]))
    reported = signal in ("rate_limit", "auth_failed")
    base = {"activeAccount": active.get("email"), "utilization": fh, "telemetry": active.get("telemetry")}
    if not (limited_by_numbers or over or reported):
        reason = "within_budget" if readable else "telemetry_unavailable"
        return dict(base, success=True, action="none", reason=reason)

    limited_path = bool(limited_by_numbers or reported)
    margin_ref = fh if (readable and not limited_path) else None
    cands = [a for a in accounts if not a.get("isActive") and healthy(a, margin_ref)]
    if not cands:
        return dict(base, success=True, action="none", reason="no_healthy_standby")
    best = min(cands, key=rank)
    last = state.get("lastSwitch") or {}
    gap = (cfg["failoverMinGapMinutes"] if limited_path else cfg["cooldownMinutes"]) * 60.0
    since = now - float(last.get("at", 0) or 0)
    if since < gap:
        return dict(base, success=True, action="none", reason="cooldown", remainingSeconds=int(gap - since),
                    standbyAccount=best.get("email"))

    evidence = {"activeUtilization": fh, "standbyUtilization": best.get("fiveHourUtil")}
    if limited_path:
        newest_report = max([p.get("at", 0) for p in pending] or [0])
        resets = active.get("fiveHourResetsAt") if readable else None  # never a stale reading
        if (_parse_ts(resets) or 0) <= now:
            resets = None
        result, detail = probe_cached(active["id"], cfg["probeTtlSeconds"], fresh_after=newest_report,
                                      resets_at=resets, five_hour=fh if readable else None)
        evidence["probe"] = result
        if result == "ok":
            resolve_signals()
            if reported:
                log_provider_event("probe.disagrees", {"accountId": active["id"], "signal": signal})
            return dict(base, success=True, action="none", reason="probe_ok_not_limited", probe=result)
        if result == "limited":
            reason = "confirmed_rate_limited"
        elif result == "auth_dead":
            reason = "active_grant_dead"
            evidence["storeProvenDead"] = True
        else:
            return dict(base, success=True, action="none", reason="probe_inconclusive", probe=result)
    else:
        reason = "active_exceeded_threshold"
    if verbose:
        sys.stdout.write("[*] Balancing: %s (%s%%) -> %s (%s%%), %s\n" % (
            active.get("email"), fh, best.get("email"), best.get("fiveHourUtil"), reason))
    res = _do_switch(best, active, reason, dry_run, automatic, cfg, source, evidence)
    if res.get("action") == "switched" and res.get("success"):
        resolve_signals()
    return res


def _do_switch(best, active, reason, dry_run, automatic, cfg, source, evidence) -> Dict[str, Any]:
    res = {"fromAccount": active.get("email") if active else None, "toAccount": best.get("email"),
           "activeUtilization": evidence.get("activeUtilization"), "standbyUtilization": best.get("fiveHourUtil"),
           "reason": reason, "probe": evidence.get("probe")}
    if dry_run or (automatic and not cfg["autoBalance"]):
        return dict(res, success=True, action="would_switch", dryRun=dry_run, observeOnly=not dry_run)
    if automatic:
        verified, version = version_verified(cfg)
        if not verified:
            log_provider_event("version_unverified", {"claudeVersion": version, "measured": MEASURED_CLAUDE_VERSIONS})
            return dict(res, success=True, action="would_switch", observeOnly=True, reason="version_unverified",
                        claudeVersion=version)
    try:
        sw = switch_account(best["id"], source=source, metadata={
            "fromAccount": res["fromAccount"], "activeUtilization": res["activeUtilization"],
            "standbyUtilization": res["standbyUtilization"], "reason": reason, "probe": res["probe"]},
            store_proven_dead=bool(evidence.get("storeProvenDead")))
    except (SwitchRefused, RuntimeError, ValueError) as e:
        return dict(res, success=False, action="none", reason="switch_refused", error=str(e))
    return dict(res, success=bool(sw.get("success")), action="switched", switchResult=sw)


def run_auto(reason: str = "hook", signal: Optional[str] = None) -> Dict[str, Any]:
    """The hooks' entry point (normally in a detached process): at most one evaluation per interval,
    machine-wide, and never while another provider-manager action runs."""
    cfg = load_config()
    now = time.time()
    if not signal and now - load_state().get("lastEvalAt", 0) < cfg["evalIntervalSeconds"]:
        return {"success": True, "action": "none", "reason": "recent_evaluation"}
    if cfg.get("versionGate", True) and cfg.get("autoBalance", True):
        claude_version()  # outside the lock: keeps the cached version (and the visible gate) current
    with pm_state.balancer_lock(BALANCER_LOCK_PATH, blocking=False, holder="auto:%s" % reason) as held:
        if not held:
            return {"success": True, "action": "none", "reason": "busy"}
        if not signal and time.time() - load_state().get("lastEvalAt", 0) < cfg["evalIntervalSeconds"]:
            return {"success": True, "action": "none", "reason": "recent_evaluation"}
        update_state(lambda s: s.__setitem__("lastEvalAt", time.time()))
        return balance_accounts(source="auto_failover" if signal else "proactive_balance",
                                signal=signal, blocking=False, automatic=True)


TRANSIENT_REFUSALS = ("store changed", "refreshing its token", "holds the balancer lock")


def run_auto_until_settled(reason: str, signal: Optional[str], budget_seconds: float = 900.0) -> Dict[str, Any]:
    """For a reported limit (detached process only): when the evaluation could not act yet (lock
    busy, inside the failover gap, an inconclusive probe, a transient refusal), wait and try again
    for up to 15 minutes. Sessions stalled on the limit send no prompts, so nothing else would start
    it again. One such loop per machine (the report is in the state for it), and it stops as soon as
    any switch has happened."""
    if not signal:
        return run_auto(reason=reason)
    with pm_state.exclusive(SETTLE_LOCK_PATH) as mine:
        if not mine:
            return {"success": True, "action": "none", "reason": "settle_loop_running"}
        started = time.time()
        deadline = started + budget_seconds
        eval_started = time.time()
        res = run_auto(reason=reason, signal=signal)
        while time.time() < deadline:
            r = res.get("reason")
            transient = r == "switch_refused" and any(t in (res.get("error") or "") for t in TRANSIENT_REFUSALS)
            switched = float((load_state().get("lastSwitch") or {}).get("at", 0) or 0) >= started
            if switched or (r not in ("busy", "cooldown", "probe_inconclusive") and not transient):
                # a report that arrived during that evaluation was turned away by this loop's lock:
                # it is this loop's to handle before it lets go
                newer = [p for p in load_state().get("pendingSignals", []) if p.get("at", 0) > eval_started]
                if not newer:
                    break
                eval_started = time.time()
                res = run_auto(reason=reason, signal=newer[-1].get("type"))
                continue
            wait = res.get("remainingSeconds") if r == "cooldown" else (35 if r == "probe_inconclusive" else 15)
            time.sleep(max(5.0, min(float(wait or 15) + 1.0, deadline - time.time())))
            eval_started = time.time()
            res = run_auto(reason=reason, signal=signal)
        return res


def rotate_account(reason: str = "rate_limit", dry_run: bool = False, force: bool = False) -> Dict[str, Any]:
    """Operator/orchestrator failover: treat the active account as reported limited. The probe must
    confirm it and the minimum gap must have passed, unless force (which still switches safely)."""
    if force:
        with pm_state.balancer_lock(BALANCER_LOCK_PATH, blocking=True, timeout=60.0, holder="rotate") as held:
            if not held:
                return {"success": False, "reason": "busy", "error": "another provider-manager action holds the lock"}
            return _rotate_forced(reason, dry_run)
    res = balance_accounts(dry_run=dry_run, source="rate_limit_failover", signal="rate_limit")
    if res.get("action") == "switched":
        return {"success": bool(res.get("success")), "rotatedFrom": res.get("fromAccount"),
                "rotatedTo": res.get("toAccount"), "reason": reason, "status": res.get("switchResult")}
    if res.get("action") == "would_switch":
        return {"success": True, "dryRun": True, "currentAccount": res.get("fromAccount"),
                "nextAccount": res.get("toAccount"), "reason": reason}
    return {"success": False, "reason": res.get("reason"), "error": res.get("error") or res.get("reason")}


def _rotate_forced(reason: str, dry_run: bool) -> Dict[str, Any]:
    """Skip the probe and the gap, not the safety: the same standby rule (minus hysteresis) and the
    same safe switch."""
    accounts = fetch_all_usage(ctx=build_context(verify_identity=True))
    cfg = dict(load_config(), standbyMax=99.9)
    cands = [a for a in accounts if not a.get("isActive") and _standby_ok(a, cfg)]
    active = next((a for a in accounts if a.get("isActive")), None)
    current = active.get("email") if active else None
    if not cands:
        return {"success": False, "reason": "no_available_standby", "error": "No healthy standby account.",
                "currentAccount": current}
    best = min(cands, key=lambda a: (a.get("fiveHourUtil"), a.get("sevenDayUtil") or 0.0))
    if dry_run:
        return {"success": True, "dryRun": True, "currentAccount": current, "nextAccount": best["email"], "reason": reason}
    try:
        sw = switch_account(best["id"], source="rate_limit_failover", metadata={"reason": reason, "forced": True})
    except (SwitchRefused, RuntimeError, ValueError) as e:
        return {"success": False, "attempted": best["email"], "error": str(e)}
    return {"success": True, "rotatedFrom": sw.get("fromAccount"), "rotatedTo": sw["switchedTo"],
            "reason": reason, "status": sw}


# -- login ----------------------------------------------------------------------------------------

def login_headless(email: Optional[str] = None, browser: str = "arc", profile: Optional[str] = None,
                   force: bool = False) -> Dict[str, Any]:
    """Re-authorize an account from a browser session.

    For the account the store holds, `claude auth login` writes the live store (a fresh grant; running
    sessions adopt it). For any other account, the login runs in a throwaway config dir, so the live
    store is never touched and nothing switches; only that account's Orca copy is renewed. A store
    credential nobody can identify is never logged over silently: a probe either lets Claude Code
    refresh it (then it can be identified) or proves it dead; otherwise --force is required."""
    import pm_login

    with pm_state.balancer_lock(BALANCER_LOCK_PATH, blocking=True, timeout=60.0, holder="login") as held:
        if not held:
            raise SwitchRefused("another provider-manager action holds the balancer lock")
        session = pm_login.find_browser_session(browser, profile)
        detected = session.get("email")
        if email and detected and email.strip().lower() != detected.strip().lower():
            raise ValueError("Active browser session is for '%s', but requested login for '%s'. "
                             "Please switch the browser profile or specify the correct --profile." % (detected, email))
        target_email = email or detected
        if not target_email:
            raise RuntimeError("No account email resolved for the browser session.")
        account = next((a for a in roster() if (a.get("email") or "").lower() == target_email.lower()), None)
        org_uuid = (account or {}).get("organizationUuid") or session.get("organizationUuid")
        if not org_uuid:
            raise RuntimeError("No organization UUID resolved for session (%s)." % detected)
        target_id = (account or {}).get("id") or session.get("accountUuid")
        if not target_id:
            raise RuntimeError("Could not resolve target account ID for %s." % target_email)
        sys.stdout.write("[*] Detected active browser session for %s (org: %s)\n" % (detected, org_uuid))
        ctx = build_context(verify_identity=True)
        if ctx["storeOauth"] and ctx["storeIdentity"] not in VERIFIED_IDENTITY and not force:
            result, _ = probe_active_account()
            if result != "auth_dead":
                ctx = build_context(verify_identity=True)
                if ctx["storeIdentity"] not in VERIFIED_IDENTITY:
                    raise SwitchRefused("the store holds a credential no Orca copy or profile check can identify, "
                                        "and it is not proven dead; logging in could discard it. Pass --force.")
        is_store_account = target_id == ctx["storeAccountId"] or (
            ctx["storeIdentity"] not in VERIFIED_IDENTITY and target_id == orca_active_id())

        if is_store_account:
            ok, out = pm_login.run_claude_login(target_email, org_uuid, browser, profile)
            if not ok:
                raise RuntimeError("claude auth login did not report success: %s" % out[-500:])
            fresh = oauth_of(read_store(ctx["primary"], ctx["user"]).data)
            if not fresh or not fresh.get("accessToken"):
                raise RuntimeError("Login succeeded in CLI, but no valid credentials found in Claude Keychain.")
            _record_active(account or {"id": target_id, "email": target_email, "organizationUuid": org_uuid})
        else:
            scratch = tempfile.mkdtemp(prefix="pm-login-")
            item = scoped_item_name(scratch)
            env = dict(os.environ)
            env["CLAUDE_CONFIG_DIR"] = scratch
            env.pop("CLAUDE_SECURESTORAGE_CONFIG_DIR", None)
            try:
                ok, out = pm_login.run_claude_login(target_email, org_uuid, browser, profile, env=env)
                if not ok:
                    raise RuntimeError("claude auth login did not report success: %s" % out[-500:])
                got = keychain_read(item, ctx["user"])
                fresh = oauth_of(got.data) or oauth_of(_load_json(Path(scratch) / ".credentials.json", {}))
            finally:
                keychain_delete(item, ctx["user"])
                shutil.rmtree(scratch, ignore_errors=True)
            if not fresh or not fresh.get("accessToken"):
                raise RuntimeError("Login succeeded in an isolated config dir, but it left no credential to read.")
        if not write_orca_oauth(target_id, fresh):
            raise RuntimeError("Failed to sync credentials to Orca Keychain for %s." % target_id)
        _mark_health(target_id, False, "login")
        def stamp(orca):
            for acc in orca.get("settings", {}).get("claudeManagedAccounts", []):
                if acc.get("id") == target_id:
                    acc["lastAuthenticatedAt"] = now_ms()
                    acc["updatedAt"] = now_ms()
        _guarded_update(ORCA_DATA_PATH, stamp)
        log_provider_event("login", {"account": target_email, "accountId": target_id, "switched": False,
                                     "storeAccount": is_store_account})
        sys.stdout.write("[*] Synced updated credentials to Orca Keychain (id: %s).\n" % target_id)
        return {"success": True, "email": target_email, "organizationUuid": org_uuid,
                "storeAccount": is_store_account, "switched": False}


# -- CLI ------------------------------------------------------------------------------------------

def main() -> None:
    import pm_cli

    pm_cli.main(sys.modules[__name__])


if __name__ == "__main__":
    main()
