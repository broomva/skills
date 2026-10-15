"""pm_codex_login.py — autonomous login for OpenAI Codex using browser sessions.

Leverages active Arc/Chrome browser sessions to approve Codex OAuth flows
headlessly without manual user intervention.
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


def is_arc_available() -> bool:
    """Check if Arc browser is installed and accessible on macOS."""
    if sys.platform != "darwin":
        return False
    return Path("/Applications/Arc.app").exists()


def run_codex_autonomous_login(target_email: str, space_name: str = "Stimulus",
                               timeout: float = 40.0) -> Tuple[bool, str]:
    """Execute `codex login` and autonomously approve the OAuth flow in Arc browser.
    
    Returns (success, message).
    """
    target_email = target_email.strip().lower()
    if not is_arc_available():
        return False, "Arc browser not available for autonomous Codex login"

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
                            const btns = Array.from(document.querySelectorAll('button, a, div[role=\\\"button\\\"]'));
                            const t = btns.find(b => b.innerText.toLowerCase().includes('{target_email}') ||
                                                     (b.parentElement && b.parentElement.innerText.toLowerCase().includes('{target_email}')));
                            if (t) {{ t.click(); return 'clicked_account'; }}
                            return 'no_matching_btn';
                        }})()"
                    else if tabUrl contains "consent" then
                        set actionResult to execute javascript "(function() {{
                            const cont = Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim() === 'Continue');
                            if (cont) {{ cont.click(); return 'clicked_continue'; }}
                            return 'no_continue_btn';
                        }})()"
                    else if tabUrl contains "localhost" or tabUrl contains "success" then
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

    # Persist in Keychain
    rec = {"auth_mode": "chatgpt", "tokens": tokens, "email": logged_email}
    pm_store.write_orca_codex(logged_email, rec)
    acc_uuid = "d24aa235-8a59-5d76-852d-c66136a9c2fc" if "devteam" in logged_email else "dc906358-ff8c-5ad9-8e71-86e423b49425"
    pm_store.write_orca_codex(acc_uuid, rec)

    return True, f"Successfully authenticated and stored credentials for {logged_email}"
