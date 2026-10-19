"""pm_codex_login.py — autonomous login for OpenAI Codex using an Arc browser session.

Runs `codex login`, opens its authorize URL in an Arc space, and clicks through the account chooser
and the consent page. Measured 2026-10-19:

- without `prompt=login` OpenAI signs in whichever account the Arc space's web session holds, so a
  login for any other account fails with an email mismatch; with it, the account chooser is shown;
- Arc's AppleScript can hang while a macOS permission prompt is pending, so a short responsiveness
  check runs before anything is opened;
- the CLI has one live seat: this login revokes the other account's saved copy.

Writes no keychain item itself: the caller snapshots ~/.codex/auth.json into the right account.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import pm_store

CODEX_AUTH_URL_RE = re.compile(r"https://auth\.openai\.com/oauth/authorize\S+")
ARC_CHECK_TIMEOUT_SECONDS = 3.0


def is_arc_available() -> bool:
    """Check if Arc browser is installed and accessible on macOS."""
    if sys.platform != "darwin":
        return False
    return Path("/Applications/Arc.app").exists()


def arc_responsive(timeout: float = ARC_CHECK_TIMEOUT_SECONDS) -> Tuple[bool, str]:
    """Is Arc running and answering AppleScript within `timeout`? A pending permission prompt makes
    every Arc AppleScript call hang; this says so in seconds instead of hanging a login. Never starts
    Arc (`tell application` would)."""
    try:
        running = subprocess.run(["pgrep", "-x", "Arc"], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return False, "cannot tell whether Arc is running (%s)" % type(e).__name__
    if running.returncode != 0:
        return False, "Arc is not running"
    try:
        res = subprocess.run(["osascript", "-e", 'tell application "Arc" to count windows'],
                             capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, ("Arc not answering AppleScript (no reply in %gs; a macOS automation permission "
                       "prompt may be pending)" % timeout)
    except OSError as e:
        return False, "osascript unavailable (%s)" % type(e).__name__
    if res.returncode != 0:
        return False, "Arc AppleScript failed: %s" % (res.stderr or "").strip()[:160]
    try:
        windows = int((res.stdout or "0").strip() or 0)
    except ValueError:
        windows = 0
    if windows < 1:
        return False, "Arc has no open window"
    return True, "ok"


def arc_usable(timeout: float = ARC_CHECK_TIMEOUT_SECONDS) -> Tuple[bool, str]:
    """Installed, running and answering AppleScript: the preconditions of a browser re-login."""
    if not is_arc_available():
        return False, "Arc is not installed"
    return arc_responsive(timeout)


def with_account_chooser(auth_url: str) -> str:
    """Force OpenAI's account chooser: without it the Arc space's current web session is signed in."""
    if re.search(r"[?&]prompt=", auth_url):
        return auth_url
    return auth_url + ("&" if "?" in auth_url else "?") + "prompt=login"


def run_codex_autonomous_login(target_email: str, space_name: str = "Stimulus",
                               timeout: float = 40.0) -> Tuple[bool, str]:
    """Execute `codex login` and autonomously approve the OAuth flow in Arc browser.
    
    Returns (success, message).
    """
    target_email = target_email.strip().lower()
    usable, detail = arc_usable()
    if not usable:
        return False, detail

    sys.stdout.write(f"[*] Starting autonomous Codex login for {target_email} in Arc space '{space_name}'...\n")
    sys.stdout.flush()

    try:
        proc = subprocess.Popen(
            ["codex", "login"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except Exception as e:
        return False, f"Failed to spawn codex login: {e}"

    auth_url: Optional[str] = None
    output_lines = []

    # Read lines until auth URL is found
    start_capture = time.time()
    while time.time() - start_capture < 15.0:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
            continue
        output_lines.append(line)
        m = CODEX_AUTH_URL_RE.search(line)
        if m:
            auth_url = m.group(0).rstrip(".")
            break

    if not auth_url:
        proc.kill()
        return False, "Failed to capture authorization URL from codex login output"
    auth_url = with_account_chooser(auth_url)

    sys.stdout.write(f"[*] Authorization URL generated. Opening in Arc '{space_name}' space...\n")
    sys.stdout.flush()

    ascript_open = f'''
    tell application "Arc"
        tell front window
            try
                focus space "{space_name}"
            end try
            make new tab with properties {{URL:"{auth_url}"}}
        end tell
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", ascript_open], check=True, capture_output=True, timeout=10)
    except Exception as e:
        proc.kill()
        return False, f"Failed to open auth tab in Arc: {e}"

    # Poll and automate interaction
    start_interaction = time.time()
    auth_succeeded = False

    while time.time() - start_interaction < timeout:
        if proc.poll() is not None:
            auth_succeeded = proc.returncode == 0
            break

        time.sleep(0.6)

        js_driver = f'''
        tell application "Arc"
            try
                tell active tab of front window
                    set tabUrl to URL
                    set actionResult to "none"
                    if tabUrl contains "choose-an-account" then
                        set actionResult to execute javascript "(function() {{
                            const btns = Array.from(document.querySelectorAll('button'));
                            const t = btns.find(b => b.innerText.toLowerCase().includes('{target_email}') && !b.getAttribute('aria-label'));
                            if (t) {{ t.click(); return 'clicked_account'; }}
                            return 'no_matching_btn';
                        }})()"
                    else if tabUrl contains "consent" then
                        set actionResult to execute javascript "(function() {{
                            const cont = Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim().toLowerCase().includes('continue'));
                            if (cont) {{ cont.click(); return 'clicked_continue'; }}
                            return 'no_continue_btn';
                        }})()"
                    else if tabUrl starts with "http://localhost" or tabUrl starts with "http://127.0.0.1" then
                        set actionResult to "callback_reached"
                        close
                    end if
                    return tabUrl & " ==> " & actionResult
                end tell
            on error err
                return "error: " & err
            end try
        end tell
        '''
        try:
            res = subprocess.run(["osascript", "-e", js_driver], text=True, capture_output=True, timeout=5)
            line_res = res.stdout.strip()
            if "callback_reached" in line_res:
                auth_succeeded = True
                break
        except Exception:
            pass

    # Ensure tab is closed if callback wasn't cleanly reached
    try:
        subprocess.run(["osascript", "-e", 'tell application "Arc" to close active tab of front window'],
                       check=False, capture_output=True, timeout=3)
    except Exception:
        pass

    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

    # Read and verify newly saved tokens
    auth_res = pm_store.read_codex_auth()
    if auth_res.status != "ok" or not auth_res.data:
        return False, "Login completed but ~/.codex/auth.json was not updated"

    tokens = auth_res.data.get("tokens", {})
    ident = pm_store.extract_codex_identity(tokens)
    logged_email = (ident.get("email") or "").lower()

    if logged_email != target_email:
        return False, f"Logged in email '{logged_email}' does not match target '{target_email}'"

    return True, f"Logged the Codex CLI in as {logged_email} (Arc space '{space_name}')"
