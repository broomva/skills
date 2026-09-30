#!/usr/bin/env python3
"""
provider_manager.py — Autonomous Provider & Subscription Credential Manager

Manages Claude Code and Orca subscription credentials, enabling seamless
account discovery, switching, headless browser OAuth login, and automatic
failover rotation when rate limits are approached or encountered.
"""

import argparse
import getpass
import json
import os
import re
import select
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ORCA_DATA_PATH = Path.home() / "Library/Application Support/orca/profiles/local-default/orca-data.json"
CLAUDE_CONFIG_PATH = Path.home() / ".claude.json"
CLAUDE_CREDS_PATH = Path.home() / ".claude/.credentials.json"
KEYCHAIN_ORCA_SERVICE = "Orca Claude Code Managed Credentials"
KEYCHAIN_CLAUDE_SCOPED = "Claude Code-credentials-d098dafb"
KEYCHAIN_CLAUDE_UNSCOPED = "Claude Code-credentials"
SCRIPT_DIR = Path(__file__).resolve().parent
AUTH_HELPER_PATH = SCRIPT_DIR / "auth_helper.js"

USAGE_CACHE_PATH = Path.home() / ".cache/broomva-provider-usage.json"
USAGE_API_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_ENDPOINT_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CACHE_TTL_SECONDS = 60.0


def run_cmd(cmd: List[str], input_str: Optional[str] = None, check: bool = True, timeout: Optional[float] = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        input=input_str,
        text=True,
        capture_output=True,
        check=check,
        timeout=timeout
    )


def get_current_username() -> str:
    user = os.environ.get("USER")
    if not user:
        try:
            user = getpass.getuser()
        except Exception:
            user = "claude-code-user"
    if not re.match(r"^[a-zA-Z0-9._-]+$", user):
        user = "claude-code-user"
    return user


def read_keychain_generic_password(service: str, account: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if account is None and service.startswith("Claude Code"):
        account = get_current_username()

    cmd = ["security", "find-generic-password", "-s", service]
    if account:
        cmd.extend(["-a", account])
    cmd.append("-w")

    res = run_cmd(cmd, check=False)
    if res.returncode != 0:
        return None

    raw = res.stdout.strip()
    if not raw:
        return None

    # Handle hex-encoded output from macOS security tool
    if not raw.startswith("{"):
        try:
            raw = bytes.fromhex(raw).decode("utf-8")
        except Exception:
            return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def write_keychain_generic_password(service: str, account: str, data: Dict[str, Any]) -> bool:
    payload = json.dumps(data)
    # macOS SecurityTool interactive mode (security -i) has a fixed line-buffer limit (<1024 bytes)
    # which truncates larger payloads. Use interactive mode for small payloads,
    # and direct argv for larger payloads or as fallback.
    if len(payload) < 800:
        payload_hex = payload.encode("utf-8").hex()
        command = " ".join([
            "add-generic-password", "-U",
            "-s", shlex.quote(service),
            "-a", shlex.quote(account),
            "-X", payload_hex,
        ])
        res = run_cmd(["security", "-i"], input_str=command + "\n", check=False)
        if res.returncode == 0:
            return True

    cmd = [
        "security", "add-generic-password",
        "-U",
        "-s", service,
        "-a", account,
        "-w", payload
    ]
    res = run_cmd(cmd, check=False)
    return res.returncode == 0


def get_orca_data() -> Dict[str, Any]:
    if not ORCA_DATA_PATH.exists():
        return {"settings": {"claudeManagedAccounts": [], "activeClaudeManagedAccountId": None}}
    try:
        with open(ORCA_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to read {ORCA_DATA_PATH}: {e}\n")
        return {"settings": {"claudeManagedAccounts": [], "activeClaudeManagedAccountId": None}}


def save_orca_data(data: Dict[str, Any]) -> bool:
    if not ORCA_DATA_PATH.parent.exists():
        ORCA_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = ORCA_DATA_PATH.with_suffix(f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, ORCA_DATA_PATH)
        return True
    except Exception as e:
        sys.stderr.write(f"Error saving {ORCA_DATA_PATH}: {e}\n")
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def get_claude_json() -> Dict[str, Any]:
    if not CLAUDE_CONFIG_PATH.exists():
        return {}
    try:
        with open(CLAUDE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_claude_json(data: Dict[str, Any]) -> bool:
    if not CLAUDE_CONFIG_PATH.parent.exists():
        CLAUDE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CLAUDE_CONFIG_PATH.with_suffix(f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CLAUDE_CONFIG_PATH)
        return True
    except Exception as e:
        sys.stderr.write(f"Error saving {CLAUDE_CONFIG_PATH}: {e}\n")
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def get_claude_auth_status() -> Dict[str, Any]:
    res = run_cmd(["claude", "auth", "status"], check=False)
    if res.returncode != 0:
        return {"loggedIn": False, "error": res.stderr.strip()}
    out = res.stdout.strip()
    match = re.search(r"\{[\s\S]*\}", out)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"loggedIn": False, "raw": out}


def list_accounts() -> List[Dict[str, Any]]:
    orca = get_orca_data()
    managed = orca.get("settings", {}).get("claudeManagedAccounts", [])
    active_id = orca.get("settings", {}).get("activeClaudeManagedAccountId")

    claude_cfg = get_claude_json()
    active_oauth = claude_cfg.get("oauthAccount", {})
    active_email = active_oauth.get("emailAddress")

    accounts = []
    for acc in managed:
        acc_id = acc.get("id")
        email = acc.get("email")
        org_name = acc.get("organizationName")
        org_uuid = acc.get("organizationUuid")

        # Check Keychain credentials
        creds = read_keychain_generic_password(KEYCHAIN_ORCA_SERVICE, acc_id)
        has_creds = creds is not None and "claudeAiOauth" in creds
        token_valid = False
        expires_at = None

        if has_creds:
            oauth = creds.get("claudeAiOauth", {})
            expires_at = oauth.get("expiresAt")
            if expires_at:
                token_valid = expires_at > (time.time() * 1000)

        is_active = (acc_id == active_id) if active_id else bool(active_email and email == active_email)

        accounts.append({
            "id": acc_id,
            "email": email,
            "organizationName": org_name,
            "organizationUuid": org_uuid,
            "isActive": is_active,
            "hasStoredCredentials": has_creds,
            "expiresAt": expires_at,
            "isTokenFresh": token_valid,
            "subscriptionType": active_oauth.get("organizationType") if is_active else None
        })

    return accounts


def read_usage_cache() -> Dict[str, Any]:
    cache_path = Path(USAGE_CACHE_PATH)
    if not cache_path.exists():
        return {"updatedAt": 0, "accounts": {}}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updatedAt": 0, "accounts": {}}


def save_usage_cache(data: Dict[str, Any]) -> bool:
    cache_path = Path(USAGE_CACHE_PATH)
    if not cache_path.parent.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, cache_path)
        return True
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return False


def refresh_account_token(account_id: str) -> Optional[Dict[str, Any]]:
    """Refresh expired OAuth credentials for account_id via RFC 6749 refresh grant.
    
    Persists rotated refresh_token and new access_token to Keychain and orca-data.json.
    """
    creds = read_keychain_generic_password(KEYCHAIN_ORCA_SERVICE, account_id)
    if not creds or "claudeAiOauth" not in creds:
        return None

    oauth = creds.get("claudeAiOauth", {})
    refresh_token = oauth.get("refreshToken")
    if not refresh_token:
        return None

    payload = json.dumps({
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_ENDPOINT_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Claude-Code/2.1.280",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to refresh OAuth token for {account_id}: {e}\n")
        return None

    new_access_token = token_data.get("access_token")
    if not new_access_token:
        return None

    new_refresh_token = token_data.get("refresh_token") or refresh_token
    expires_in = token_data.get("expires_in", 3600)
    new_expires_at = int((time.time() + expires_in) * 1000)

    oauth["accessToken"] = new_access_token
    oauth["refreshToken"] = new_refresh_token
    oauth["expiresAt"] = new_expires_at
    creds["claudeAiOauth"] = oauth

    # 1. Update Orca Keychain
    if not write_keychain_generic_password(KEYCHAIN_ORCA_SERVICE, account_id, creds):
        sys.stderr.write(f"Error: Failed to persist refreshed OAuth credentials for {account_id}\n")
        return None

    # 2. If this account is currently active, mirror to Claude Keychains
    orca_data = get_orca_data()
    active_id = orca_data.get("settings", {}).get("activeClaudeManagedAccountId")
    username = get_current_username()
    if active_id == account_id:
        write_keychain_generic_password(KEYCHAIN_CLAUDE_SCOPED, username, creds)
        write_keychain_generic_password(KEYCHAIN_CLAUDE_UNSCOPED, username, creds)

    # 3. Update updatedAt in orca-data.json
    for acc in orca_data.get("settings", {}).get("claudeManagedAccounts", []):
        if acc.get("id") == account_id:
            acc["updatedAt"] = int(time.time() * 1000)
            break
    save_orca_data(orca_data)

    return creds


def fetch_account_usage(account_id: str, force_refresh: bool = False, max_retries: int = 1) -> Optional[Dict[str, Any]]:
    """Fetch 5-hour and 7-day usage telemetry for a specific account.
    
    Reads from local cache if within TTL (60s), or queries https://api.anthropic.com/api/oauth/usage.
    Automatically handles 401 token expiration by invoking refresh_account_token.
    """
    now = time.time()
    cache = read_usage_cache()
    acc_cache = cache.get("accounts", {}).get(account_id)

    if not force_refresh and acc_cache:
        cached_at = acc_cache.get("cachedAt", 0)
        if (now - cached_at) < CACHE_TTL_SECONDS:
            return acc_cache

    creds = read_keychain_generic_password(KEYCHAIN_ORCA_SERVICE, account_id)
    if not creds or "claudeAiOauth" not in creds:
        return None

    oauth = creds.get("claudeAiOauth", {})
    token = oauth.get("accessToken")
    expires_at = oauth.get("expiresAt")

    # If token is locally known to be expired, refresh before calling
    if token and expires_at and expires_at <= (now * 1000):
        refreshed = refresh_account_token(account_id)
        if refreshed:
            token = refreshed.get("claudeAiOauth", {}).get("accessToken")

    if not token:
        return None

    req = urllib.request.Request(
        USAGE_API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "Claude-Code/2.1.280",
            "anthropic-version": "2023-06-01",
            "Accept": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401 and max_retries > 0:
            refreshed = refresh_account_token(account_id)
            if refreshed:
                return fetch_account_usage(account_id, force_refresh=True, max_retries=max_retries - 1)
        elif e.code == 429:
            entry = {
                "id": account_id,
                "cachedAt": now,
                "isRateLimited": True,
                "status": "rate_limited",
                "error": "HTTP 429 Rate Limit"
            }
            cache.setdefault("accounts", {})[account_id] = entry
            cache["updatedAt"] = now
            save_usage_cache(cache)
            return entry
        return None
    except Exception:
        if acc_cache:
            acc_cache["stale"] = True
            return acc_cache
        return None

    fh = data.get("five_hour") or {}
    sd = data.get("seven_day") or {}

    fh_util = float(fh.get("utilization", fh.get("used_percentage", 0.0)) or 0.0)
    sd_util = float(sd.get("utilization", sd.get("used_percentage", 0.0)) or 0.0)

    if fh_util >= 95.0 or sd_util >= 98.0:
        status = "critical"
    elif fh_util >= 80.0 or sd_util >= 85.0:
        status = "warning"
    else:
        status = "ok"

    locked_reason = (data.get("five_hour") or {}).get("locked_reason")
    is_locked = bool(locked_reason or fh_util >= 99.0)
    prev_locked = acc_cache.get("isRateLimited", False) if acc_cache else False
    locked_at = acc_cache.get("lockedAt", 0.0) if acc_cache else 0.0
    locked_reason_prev = acc_cache.get("lockedReason") if acc_cache else None

    if prev_locked and not is_locked:
        if (now - locked_at) < 300.0:
            is_locked = True
            if not locked_reason:
                locked_reason = locked_reason_prev or "rate_limit_lock"

    entry = {
        "id": account_id,
        "cachedAt": now,
        "five_hour": {
            "utilization": round(fh_util, 1),
            "resets_at": fh.get("resets_at")
        },
        "seven_day": {
            "utilization": round(sd_util, 1),
            "resets_at": sd.get("resets_at")
        },
        "isRateLimited": is_locked,
        "lockedReason": locked_reason if is_locked else None,
        "lockedAt": (locked_at or now) if is_locked else None,
        "status": status,
        "raw": data
    }

    cache.setdefault("accounts", {})[account_id] = entry
    cache["updatedAt"] = now
    save_usage_cache(cache)
    return entry


def fetch_all_usage(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetch usage telemetry for all accounts configured in the roster."""
    accounts = list_accounts()
    results = []
    for acc in accounts:
        acc_id = acc["id"]
        usage = fetch_account_usage(acc_id, force_refresh=force_refresh)
        acc_info = dict(acc)
        if usage:
            acc_info["usage"] = usage
            acc_info["fiveHourUtil"] = usage.get("five_hour", {}).get("utilization")
            acc_info["sevenDayUtil"] = usage.get("seven_day", {}).get("utilization")
            acc_info["fiveHourResetsAt"] = usage.get("five_hour", {}).get("resets_at")
            acc_info["sevenDayResetsAt"] = usage.get("seven_day", {}).get("resets_at")
            acc_info["usageStatus"] = usage.get("status", "unknown")
            acc_info["isRateLimited"] = usage.get("isRateLimited", False)
        else:
            acc_info["usage"] = None
            acc_info["fiveHourUtil"] = None
            acc_info["sevenDayUtil"] = None
            acc_info["fiveHourResetsAt"] = None
            acc_info["sevenDayResetsAt"] = None
            acc_info["usageStatus"] = "unavailable"
            acc_info["isRateLimited"] = False
        results.append(acc_info)
    return results


def balance_accounts(threshold: float = 85.0, dry_run: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """Proactively balance accounts when active account exceeds threshold.
    
    If active account's 5-hour utilization >= threshold, automatically switches
    to the standby account with the lowest utilization.
    """
    accounts = fetch_all_usage()
    if len(accounts) < 2:
        return {
            "success": True,
            "action": "none",
            "reason": "single_account",
            "message": "Only 1 account configured in roster."
        }

    active = next((a for a in accounts if a["isActive"]), None)
    if not active:
        candidates = [a for a in accounts if a.get("hasStoredCredentials")]
        if candidates:
            best = min(candidates, key=lambda a: a.get("fiveHourUtil") if a.get("fiveHourUtil") is not None else 999.0)
            if dry_run:
                return {
                    "success": True,
                    "action": "would_switch",
                    "switchedTo": best["email"],
                    "reason": "no_active_account",
                    "dryRun": True
                }
            switch_res = switch_account(best["id"])
            return {
                "success": bool(switch_res.get("success", False)),
                "action": "switched",
                "switchedTo": best["email"],
                "reason": "no_active_account"
            }
        return {"success": False, "error": "No accounts with stored credentials available."}

    active_util = active.get("fiveHourUtil")
    active_email = active.get("email")
    active_rate_limited = active.get("isRateLimited", False)

    needs_balancing = active_rate_limited or (active_util is not None and active_util >= threshold)

    standbys = [
        a for a in accounts
        if not a["isActive"] and a.get("hasStoredCredentials") and not a.get("isRateLimited")
    ]

    if not standbys:
        return {
            "success": True,
            "action": "none",
            "activeAccount": active_email,
            "utilization": active_util,
            "reason": "no_available_standby",
            "message": "No alternative standby account with stored credentials available."
        }

    def standby_sort_key(a):
        fh = a.get("fiveHourUtil")
        sd = a.get("sevenDayUtil")
        return (fh if fh is not None else 999.0, sd if sd is not None else 999.0)

    best_standby = min(standbys, key=standby_sort_key)
    best_util = best_standby.get("fiveHourUtil")
    best_email = best_standby.get("email")

    if needs_balancing:
        if best_util is None or (active_util is None) or best_util < active_util:
            if dry_run:
                return {
                    "success": True,
                    "action": "would_switch",
                    "dryRun": True,
                    "fromAccount": active_email,
                    "toAccount": best_email,
                    "activeUtilization": active_util,
                    "standbyUtilization": best_util,
                    "reason": "active_rate_limited" if active_rate_limited else "active_exceeded_threshold"
                }

            if verbose:
                sys.stdout.write(f"[*] Proactive balancing: rotating from {active_email} ({active_util}%) to {best_email} ({best_util}%)...\n")
            switch_res = switch_account(best_standby["id"])
            return {
                "success": bool(switch_res.get("success", False)),
                "action": "switched",
                "fromAccount": active_email,
                "toAccount": best_email,
                "activeUtilization": active_util,
                "standbyUtilization": best_util,
                "reason": "active_rate_limited" if active_rate_limited else "active_exceeded_threshold",
                "switchResult": switch_res
            }

    return {
        "success": True,
        "action": "none",
        "activeAccount": active_email,
        "utilization": active_util,
        "standbyAccount": best_email,
        "standbyUtilization": best_util,
        "reason": "within_budget"
    }


def switch_account(identifier: str) -> Dict[str, Any]:
    """Switch active credentials in both Claude Code and Orca to target email or UUID."""
    accounts = list_accounts()
    target = None
    for acc in accounts:
        if acc["id"] == identifier or acc["email"].lower() == identifier.lower():
            target = acc
            break

    if not target:
        raise ValueError(f"Account '{identifier}' not found in managed accounts roster.")

    target_id = target["id"]
    target_email = target["email"]

    # 1. Read target credentials from Orca Keychain
    creds = read_keychain_generic_password(KEYCHAIN_ORCA_SERVICE, target_id)
    if not creds or "claudeAiOauth" not in creds:
        raise RuntimeError(
            f"No credentials stored in Keychain for account {target_email} ({target_id}). "
            f"Run 'login-headless --email {target_email}' first."
        )

    # 2. Write credentials to Claude Code Keychains
    username = os.environ.get("USER") or os.environ.get("LOGNAME") or getpass.getuser()
    ok_scoped = write_keychain_generic_password(KEYCHAIN_CLAUDE_SCOPED, username, creds)
    ok_unscoped = write_keychain_generic_password(KEYCHAIN_CLAUDE_UNSCOPED, username, creds)
    if not (ok_scoped or ok_unscoped):
        raise RuntimeError(
            f"Failed to write credentials to macOS Keychain for account {target_email} ({username})."
        )

    # 3. Update ~/.claude.json oauthAccount
    claude_cfg = get_claude_json()
    oauth_acc = claude_cfg.get("oauthAccount", {})
    oauth_acc["emailAddress"] = target_email
    oauth_acc["organizationUuid"] = target.get("organizationUuid")
    oauth_acc["organizationName"] = target.get("organizationName")
    oauth_acc["profileFetchedAt"] = int(time.time() * 1000)
    claude_cfg["oauthAccount"] = oauth_acc
    save_claude_json(claude_cfg)

    # 4. Update Orca data
    orca_data = get_orca_data()
    orca_data.setdefault("settings", {})["activeClaudeManagedAccountId"] = target_id
    for acc in orca_data["settings"].get("claudeManagedAccounts", []):
        if acc.get("id") == target_id:
            acc["updatedAt"] = int(time.time() * 1000)
    save_orca_data(orca_data)

    # 5. Verify status
    status = get_claude_auth_status()
    return {
        "success": status.get("loggedIn") is True,
        "switchedTo": target_email,
        "accountId": target_id,
        "authStatus": status
    }


def login_headless(email: Optional[str] = None, browser: str = "arc", profile: Optional[str] = None) -> Dict[str, Any]:
    """Autonomous OAuth login via browser session extraction and PKCE grant injection."""
    if not AUTH_HELPER_PATH.exists():
        raise FileNotFoundError(f"auth_helper.js not found at {AUTH_HELPER_PATH}")

    # 1. Discover browser session
    cmd = ["node", str(AUTH_HELPER_PATH), "find-session", browser]
    if profile:
        cmd.append(profile)

    res = run_cmd(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to find browser session: {res.stderr}")

    session_info = json.loads(res.stdout).get("session", {})
    detected_email = session_info.get("email")
    org_uuid = session_info.get("organizationUuid")

    if email and detected_email and email.strip().lower() != detected_email.strip().lower():
        raise ValueError(
            f"Active browser session is for '{detected_email}', but requested login for '{email}'. "
            f"Please switch the browser profile or specify the correct --profile."
        )
    target_email = email or detected_email

    orca = get_orca_data()
    managed = orca.get("settings", {}).get("claudeManagedAccounts", [])
    matching_acc = next((a for a in managed if a.get("email", "").lower() == target_email.lower()), None)
    if matching_acc and matching_acc.get("organizationUuid"):
        org_uuid = matching_acc.get("organizationUuid")

    if not org_uuid:
        raise RuntimeError(f"No organization UUID resolved for session ({detected_email}).")

    sys.stdout.write(f"[*] Detected active browser session for {detected_email} (org: {org_uuid})\n")

    # 2. Spawn claude auth login process
    login_cmd = ["claude", "auth", "login", "--claudeai"]
    if target_email:
        login_cmd.extend(["--email", target_email])

    proc = subprocess.Popen(
        login_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    auth_url = None
    output_lines = []

    # Read output until the authorize URL is emitted
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        rlist, _, _ = select.select([proc.stdout], [], [], 0.5)
        if proc.stdout in rlist:
            line = proc.stdout.readline()
            if not line:
                break
            output_lines.append(line)
            match = re.search(r"https://claude\.com/cai/oauth/authorize\S+", line)
            if match:
                auth_url = match.group(0).rstrip(".")
                break

    if not auth_url:
        proc.kill()
        proc.communicate()
        raise RuntimeError("Failed to capture OAuth authorization URL from claude auth login output.")

    sys.stdout.write(f"[*] Authorization URL generated. Requesting autonomous approval...\n")

    # 3. Call auth_helper to execute the authorization grant
    approve_cmd = ["node", str(AUTH_HELPER_PATH), "approve-oauth", auth_url, org_uuid, browser]
    if profile:
        approve_cmd.append(profile)

    appr_res = run_cmd(approve_cmd, check=False)
    formatted_code = None
    if appr_res.returncode == 0:
        try:
            appr_data = json.loads(appr_res.stdout)
            formatted_code = appr_data.get("formattedInput")
        except json.JSONDecodeError:
            pass

    if formatted_code:
        sys.stdout.write(f"[*] Authorization code obtained autonomously. Notifying login listener...\n")
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.write(f"{formatted_code}\n")
                proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
    else:
        err_msg = appr_res.stderr.strip() if appr_res else "No code returned"
        sys.stdout.write(f"[*] Autonomous grant approval unavailable ({err_msg}).\n")
        sys.stdout.write(f"[*] Local listener active; waiting up to 90s for browser sign-in completion...\n")

    # 4. Wait for login process to complete (either via injected code or browser redirect callback)
    try:
        stdout_rem, stderr_rem = proc.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise TimeoutError("claude auth login timed out waiting to complete authentication.")

    full_output = "".join(output_lines) + stdout_rem + stderr_rem

    if proc.returncode != 0 or "Login successful" not in full_output:
        raise RuntimeError(f"claude auth login did not report success (exit code {proc.returncode}): {full_output}")

    sys.stdout.write("[*] Login confirmed by Claude Code.\n")

    # 5. Sync fresh credentials into Orca Keychain & orca-data.json
    username = get_current_username()
    fresh_creds = None
    for s in [KEYCHAIN_CLAUDE_UNSCOPED, KEYCHAIN_CLAUDE_SCOPED]:
        candidate = read_keychain_generic_password(s, username)
        if candidate and candidate.get("claudeAiOauth", {}).get("accessToken"):
            fresh_creds = candidate
            break
    if not fresh_creds:
        fresh_creds = read_keychain_generic_password(KEYCHAIN_CLAUDE_UNSCOPED, username) or read_keychain_generic_password(KEYCHAIN_CLAUDE_SCOPED, username)

    orca = get_orca_data()
    managed = orca.get("settings", {}).get("claudeManagedAccounts", [])
    matching_acc = next((a for a in managed if a.get("email", "").lower() == target_email.lower()), None)

    if not fresh_creds or not fresh_creds.get("claudeAiOauth", {}).get("accessToken"):
        raise RuntimeError("Login succeeded in CLI, but no valid credentials found in Claude Keychain.")

    target_uuid = matching_acc.get("id") if matching_acc else session_info.get("accountUuid")
    if not target_uuid:
        raise RuntimeError(f"Could not resolve target account ID for {target_email}.")

    ok = write_keychain_generic_password(KEYCHAIN_ORCA_SERVICE, target_uuid, fresh_creds)
    if not ok:
        raise RuntimeError(f"Failed to sync credentials to Orca Keychain for {target_uuid}.")

    # Mirror fresh creds across both Claude Keychains so they remain synchronized
    ok_unscoped = write_keychain_generic_password(KEYCHAIN_CLAUDE_UNSCOPED, username, fresh_creds)
    ok_scoped = write_keychain_generic_password(KEYCHAIN_CLAUDE_SCOPED, username, fresh_creds)
    if not (ok_unscoped and ok_scoped):
        sys.stderr.write(f"Warning: Partial keychain synchronization (unscoped={ok_unscoped}, scoped={ok_scoped})\n")

    orca.setdefault("settings", {})["activeClaudeManagedAccountId"] = target_uuid
    if matching_acc:
        matching_acc["lastAuthenticatedAt"] = int(time.time() * 1000)
        matching_acc["updatedAt"] = int(time.time() * 1000)
    save_orca_data(orca)
    sys.stdout.write(f"[*] Synced updated credentials to Orca Keychain (id: {target_uuid}).\n")

    status = get_claude_auth_status()
    return {
        "success": bool(status.get("loggedIn") is True),
        "email": target_email,
        "organizationUuid": org_uuid,
        "authStatus": status
    }


def rotate_account(reason: str = "rate_limit", dry_run: bool = False) -> Dict[str, Any]:
    """Rotate to the next available configured account when a rate limit occurs.
    
    Uses live usage telemetry when available to pick the standby account with lowest utilization.
    """
    accounts = list_accounts()
    if len(accounts) < 2:
        return {
            "success": False,
            "error": "Cannot rotate: only 1 account configured in managed accounts roster."
        }

    active_idx = next((i for i, a in enumerate(accounts) if a["isActive"]), 0)
    active = accounts[active_idx] if accounts else None

    # Fetch usage telemetry to make an intelligent selection
    usage_list = fetch_all_usage()
    standby_candidates = [
        a for a in usage_list
        if not a["isActive"] and a.get("hasStoredCredentials") and not a.get("isRateLimited")
    ]

    chosen = None
    if standby_candidates:
        def sort_key(a):
            fh = a.get("fiveHourUtil")
            sd = a.get("sevenDayUtil")
            return (fh if fh is not None else 999.0, sd if sd is not None else 999.0)
        chosen = min(standby_candidates, key=sort_key)

    if not chosen:
        # Fallback to cyclic round-robin order of remaining candidates
        ordered_candidates = [accounts[(active_idx + i) % len(accounts)] for i in range(1, len(accounts))]
        chosen = next((c for c in ordered_candidates if c.get("isTokenFresh")), None)
        if not chosen:
            chosen = next((c for c in ordered_candidates if c.get("hasStoredCredentials")), ordered_candidates[0])

    if dry_run:
        return {
            "success": True,
            "dryRun": True,
            "currentAccount": active["email"] if active else None,
            "nextAccount": chosen["email"],
            "reason": reason
        }

    # Mark active account as rate-limited in usage cache when performing actual rotation
    if active:
        cache = read_usage_cache()
        acc_cache = cache.get("accounts", {}).get(active["id"], {})
        acc_cache["isRateLimited"] = True
        acc_cache["lockedReason"] = reason
        acc_cache["lockedAt"] = time.time()
        cache.setdefault("accounts", {})[active["id"]] = acc_cache
        save_usage_cache(cache)

    sys.stdout.write(f"[*] Rotating provider from {active['email'] if active else 'unknown'} to {chosen['email']} (reason: {reason})...\n")
    try:
        switch_res = switch_account(chosen["id"])
        return {
            "success": bool(switch_res.get("success", False)),
            "rotatedFrom": active["email"] if active else None,
            "rotatedTo": chosen["email"],
            "reason": reason,
            "status": switch_res
        }
    except Exception as e:
        sys.stderr.write(f"Failed to switch to {chosen['email']}: {e}\n")
        return {
            "success": False,
            "attempted": chosen["email"],
            "error": str(e)
        }


def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    parser = argparse.ArgumentParser(description="Autonomous Provider & Subscription Manager", parents=[common_parser])
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List all managed accounts and status", parents=[common_parser])

    # status
    subparsers.add_parser("status", help="Show active provider and auth status", parents=[common_parser])

    # usage
    usage_parser = subparsers.add_parser("usage", help="Show usage telemetry and rate limit status for all accounts", parents=[common_parser])
    usage_parser.add_argument("--force", action="store_true", help="Bypass cache and force fresh API fetch")

    # balance
    balance_parser = subparsers.add_parser("balance", help="Proactively balance accounts based on usage utilization", parents=[common_parser])
    balance_parser.add_argument("--threshold", type=float, default=85.0, help="5-hour utilization threshold to trigger rotation (default: 85.0)")
    balance_parser.add_argument("--dry-run", action="store_true", help="Preview balancing action without switching")

    # switch
    switch_parser = subparsers.add_parser("switch", help="Switch active credentials to an account", parents=[common_parser])
    switch_parser.add_argument("account", help="Account email or UUID")

    # login-headless
    login_parser = subparsers.add_parser("login-headless", help="Autonomous headless OAuth login via browser session", parents=[common_parser])
    login_parser.add_argument("--email", help="Target email address")
    login_parser.add_argument("--browser", default="arc", choices=["arc", "chrome"], help="Browser to extract session from")
    login_parser.add_argument("--profile", help="Browser profile directory (e.g. 'Profile 3')")

    # rotate
    rotate_parser = subparsers.add_parser("rotate", help="Rotate to next available account (rate limit failover)", parents=[common_parser])
    rotate_parser.add_argument("--reason", default="rate_limit", help="Reason for rotation (e.g. rate_limit, quota)")
    rotate_parser.add_argument("--dry-run", action="store_true", help="Preview rotation without applying")

    args = parser.parse_args()

    try:
        if args.command == "list":
            accounts = list_accounts()
            if args.json:
                print(json.dumps(accounts, indent=2))
            else:
                print(f"{'ACTIVE':<8} {'EMAIL':<28} {'SUBSCRIPTION':<14} {'STORED CREDS':<14} {'UUID'}")
                print("-" * 85)
                for a in accounts:
                    active_marker = " * " if a["isActive"] else "   "
                    sub_tier = (a.get("subscriptionType") or "unknown") if a["isActive"] else "-"
                    creds_status = "Yes (Fresh)" if a.get("isTokenFresh") else ("Yes" if a.get("hasStoredCredentials") else "No")
                    print(f"{active_marker:<8} {a['email']:<28} {sub_tier:<14} {creds_status:<14} {a['id']}")

        elif args.command == "status":
            status = get_claude_auth_status()
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                print(f"Logged In:     {status.get('loggedIn')}")
                print(f"Active Email:  {status.get('email')}")
                print(f"Organization:  {status.get('orgName')} ({status.get('orgId')})")
                print(f"Subscription:  {status.get('subscriptionType')}")

        elif args.command == "usage":
            accounts = fetch_all_usage(force_refresh=args.force)
            if args.json:
                print(json.dumps(accounts, indent=2))
            else:
                print(f"{'ACTIVE':<8} {'EMAIL':<28} {'5-HOUR UTIL':<22} {'7-DAY UTIL':<22} {'STATUS'}")
                print("-" * 92)
                for a in accounts:
                    active_marker = " * " if a["isActive"] else "   "
                    fh_str = f"{a['fiveHourUtil']}%" if a['fiveHourUtil'] is not None else "-"
                    if a.get('fiveHourResetsAt'):
                        fh_reset = a['fiveHourResetsAt'].split('T')[-1][:5]
                        fh_str += f" ({fh_reset})"
                    sd_str = f"{a['sevenDayUtil']}%" if a['sevenDayUtil'] is not None else "-"
                    if a.get('sevenDayResetsAt'):
                        sd_reset = a['sevenDayResetsAt'].split('T')[0]
                        sd_str += f" ({sd_reset})"
                    status = a.get("usageStatus", "unknown").upper()
                    if a.get("isRateLimited"):
                        status = "RATE_LIMITED"
                    print(f"{active_marker:<8} {a['email']:<28} {fh_str:<22} {sd_str:<22} {status}")

        elif args.command == "balance":
            res = balance_accounts(threshold=args.threshold, dry_run=args.dry_run, verbose=True)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                action = res.get("action")
                if action == "switched":
                    print(f"Balanced: Switched active account from {res.get('fromAccount')} to {res.get('toAccount')}")
                    print(f"Utilizations: Previous {res.get('activeUtilization')}%, New {res.get('standbyUtilization')}%")
                elif action == "would_switch":
                    print(f"Dry run: Would switch active account from {res.get('fromAccount')} ({res.get('activeUtilization')}%) to {res.get('toAccount')} ({res.get('standbyUtilization')}%)")
                elif res.get("reason") == "within_budget":
                    active_acc = res.get('activeAccount', 'unknown')
                    util = res.get('utilization')
                    util_str = f"{util}%" if util is not None else "N/A"
                    print(f"Balanced: Active account ({active_acc}) utilization is within budget ({util_str} < {args.threshold}%). No switch needed.")
                elif not res.get("success", False):
                    print(f"Balance check: {res.get('error') or res.get('message') or 'Unable to balance accounts.'}")
                else:
                    print(f"Balance check: {res.get('message') or res.get('reason') or 'No switch performed.'}")

        elif args.command == "switch":
            res = switch_account(args.account)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Successfully switched to {res['switchedTo']} (ID: {res['accountId']})")
                print(f"Active Status: Logged in as {res['authStatus'].get('email')} ({res['authStatus'].get('subscriptionType')})")

        elif args.command == "login-headless":
            res = login_headless(email=args.email, browser=args.browser, profile=args.profile)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"Successfully logged in as {res['email']}!")
                print(f"Organization: {res['organizationUuid']}")

        elif args.command == "rotate":
            res = rotate_account(reason=args.reason, dry_run=args.dry_run)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                if res.get("dryRun"):
                    print(f"Dry run: Would rotate from {res.get('currentAccount')} to {res.get('nextAccount')}")
                elif res.get("success"):
                    print(f"Successfully rotated provider: {res.get('rotatedFrom')} -> {res.get('rotatedTo')}")
                else:
                    print(f"Rotation failed: {res.get('error')}")

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
