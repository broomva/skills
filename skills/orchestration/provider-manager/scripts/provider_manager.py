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
import subprocess
import sys
import time
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


def run_cmd(cmd: List[str], input_str: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        input=input_str,
        text=True,
        capture_output=True,
        check=check
    )


def read_keychain_generic_password(service: str, account: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
    try:
        with open(ORCA_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        sys.stderr.write(f"Error saving {ORCA_DATA_PATH}: {e}\n")
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
    try:
        with open(CLAUDE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        sys.stderr.write(f"Error saving {CLAUDE_CONFIG_PATH}: {e}\n")
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

        is_active = (acc_id == active_id) or (active_email and email == active_email)

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
    write_keychain_generic_password(KEYCHAIN_CLAUDE_SCOPED, username, creds)
    write_keychain_generic_password(KEYCHAIN_CLAUDE_UNSCOPED, username, creds)

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
    target_email = email or detected_email

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
    start_time = time.time()
    while time.time() - start_time < 20:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
            continue

        output_lines.append(line)
        match = re.search(r"https://claude\.com/cai/oauth/authorize\S+", line)
        if match:
            auth_url = match.group(0).rstrip(".")
            break

    if not auth_url:
        proc.kill()
        raise RuntimeError("Failed to capture OAuth authorization URL from claude auth login output.")

    sys.stdout.write(f"[*] Authorization URL generated. Requesting autonomous approval...\n")

    # 3. Call auth_helper to execute the authorization grant
    approve_cmd = ["node", str(AUTH_HELPER_PATH), "approve-oauth", auth_url, org_uuid, browser]
    if profile:
        approve_cmd.append(profile)

    appr_res = run_cmd(approve_cmd)
    if appr_res.returncode != 0:
        proc.kill()
        raise RuntimeError(f"Autonomous OAuth approval failed: {appr_res.stderr}")

    appr_data = json.loads(appr_res.stdout)
    formatted_code = appr_data.get("formattedInput")
    if not formatted_code:
        proc.kill()
        raise RuntimeError("No formatted authorization code returned.")

    sys.stdout.write(f"[*] Authorization code obtained. Injecting into login process...\n")

    # 4. Inject formatted code into claude process
    proc.stdin.write(f"{formatted_code}\n")
    proc.stdin.flush()

    stdout_rem, stderr_rem = proc.communicate(timeout=15)
    full_output = "".join(output_lines) + stdout_rem + stderr_rem

    if "Login successful" not in full_output and proc.returncode != 0:
        raise RuntimeError(f"claude auth login did not report success: {full_output}")

    sys.stdout.write("[*] Login confirmed by Claude Code.\n")

    # 5. Sync fresh credentials into Orca Keychain & orca-data.json
    fresh_creds = read_keychain_generic_password(KEYCHAIN_CLAUDE_SCOPED)
    if not fresh_creds:
        fresh_creds = read_keychain_generic_password(KEYCHAIN_CLAUDE_UNSCOPED)

    orca = get_orca_data()
    managed = orca.get("settings", {}).get("claudeManagedAccounts", [])
    matching_acc = next((a for a in managed if a.get("email", "").lower() == target_email.lower()), None)

    target_uuid = matching_acc.get("id") if matching_acc else session_info.get("accountUuid")

    if fresh_creds and target_uuid:
        write_keychain_generic_password(KEYCHAIN_ORCA_SERVICE, target_uuid, fresh_creds)
        orca.setdefault("settings", {})["activeClaudeManagedAccountId"] = target_uuid
        if matching_acc:
            matching_acc["lastAuthenticatedAt"] = int(time.time() * 1000)
            matching_acc["updatedAt"] = int(time.time() * 1000)
        save_orca_data(orca)
        sys.stdout.write(f"[*] Synced updated credentials to Orca Keychain (id: {target_uuid}).\n")

    status = get_claude_auth_status()
    return {
        "success": True,
        "email": target_email,
        "organizationUuid": org_uuid,
        "authStatus": status
    }


def rotate_account(reason: str = "rate_limit", dry_run: bool = False) -> Dict[str, Any]:
    """Rotate to the next available configured account when a rate limit occurs."""
    accounts = list_accounts()
    if len(accounts) < 2:
        return {
            "success": False,
            "error": "Cannot rotate: only 1 account configured in managed accounts roster."
        }

    active = next((a for a in accounts if a["isActive"]), None)
    candidates = [a for a in accounts if not a["isActive"]]

    # Pick candidate with fresh credentials or stored credentials
    chosen = next((c for c in candidates if c["hasStoredCredentials"]), candidates[0])

    if dry_run:
        return {
            "success": True,
            "dryRun": True,
            "currentAccount": active["email"] if active else None,
            "nextAccount": chosen["email"],
            "reason": reason
        }

    sys.stdout.write(f"[*] Rotating provider from {active['email'] if active else 'unknown'} to {chosen['email']} (reason: {reason})...\n")
    try:
        switch_res = switch_account(chosen["id"])
        return {
            "success": True,
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
                    sub_tier = a.get("subscriptionType") or "max" if a["isActive"] else "-"
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
