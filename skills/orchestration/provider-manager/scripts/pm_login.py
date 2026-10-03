"""pm_login.py — drive `claude auth login` with a browser session's authorization (auth_helper.js).

Only the browser/PKCE mechanics live here. Where the new credential lands, and whether that
switches the machine, is decided by provider_manager.login_headless.
"""

import json
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
AUTH_HELPER_PATH = SCRIPT_DIR / "auth_helper.js"
AUTHORIZE_URL_RE = re.compile(r"https://claude\.com/cai/oauth/authorize\S+")


def find_browser_session(browser: str, profile: Optional[str]) -> Dict[str, Any]:
    if not AUTH_HELPER_PATH.exists():
        raise FileNotFoundError("auth_helper.js not found at %s" % AUTH_HELPER_PATH)
    cmd = ["node", str(AUTH_HELPER_PATH), "find-session", browser]
    if profile:
        cmd.append(profile)
    res = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError("Failed to find browser session: %s" % res.stderr.strip()[:300])
    return json.loads(res.stdout).get("session", {})


def run_claude_login(email: str, org_uuid: str, browser: str, profile: Optional[str],
                     env: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """Run `claude auth login --claudeai --email <email>` in env and approve it with the browser
    session. Returns (succeeded, combined output)."""
    login_cmd = ["claude", "auth", "login", "--claudeai", "--email", email]
    proc = subprocess.Popen(login_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    auth_url: List[str] = []
    output: List[str] = []
    url_ready = threading.Event()

    def read_stdout():
        for line in iter(proc.stdout.readline, ""):
            output.append(line)
            if not auth_url:
                m = AUTHORIZE_URL_RE.search(line)
                if m:
                    auth_url.append(m.group(0).rstrip("."))
                    url_ready.set()

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    url_ready.wait(timeout=15.0)
    if not auth_url:
        proc.kill()
        reader.join(timeout=2.0)
        raise RuntimeError("Failed to capture OAuth authorization URL from claude auth login output.")

    sys.stdout.write("[*] Authorization URL generated. Requesting autonomous approval...\n")
    approve_cmd = ["node", str(AUTH_HELPER_PATH), "approve-oauth", auth_url[0], org_uuid, browser]
    if profile:
        approve_cmd.append(profile)
    try:
        appr = subprocess.run(approve_cmd, text=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        proc.kill()  # never leave a login listener behind (it could finish into a deleted scratch dir)
        reader.join(timeout=2.0)
        raise
    code = None
    if appr.returncode == 0:
        try:
            code = json.loads(appr.stdout).get("formattedInput")
        except ValueError:
            code = None
    if code:
        sys.stdout.write("[*] Authorization code obtained autonomously. Notifying login listener...\n")
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.write("%s\n" % code)
                proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
    else:
        sys.stdout.write("[*] Autonomous grant approval unavailable (%s).\n" % (appr.stderr.strip()[:200] or "no code"))
        sys.stdout.write("[*] Local listener active; waiting up to 90s for browser sign-in completion...\n")
    try:
        proc.wait(timeout=90)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise TimeoutError("claude auth login timed out waiting to complete authentication.")
    finally:
        reader.join(timeout=5.0)
    text = "".join(output)
    return proc.returncode == 0 and "Login successful" in text, text
