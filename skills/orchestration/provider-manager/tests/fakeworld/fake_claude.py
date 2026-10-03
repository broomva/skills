#!/usr/bin/env python3
"""A stand-in `claude` for tests: `auth status` and the `-p` probe, against the scratch store.

It reads the credential item Claude Code 2.1.280 would read (`Claude Code-credentials`, suffixed with
sha256(config dir)[:8] when CLAUDE_CONFIG_DIR is set) from the fake keychain DB, and answers the probe
from fake_anthropic: OK, or the limit message on an exhausted account. Every probe is recorded as a
`probe` call so tests can count them.
"""

import hashlib
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_anthropic  # noqa: E402
import keychain_db  # noqa: E402


def _die(msg, rc):
    sys.stderr.write(msg + "\n")
    sys.exit(rc)


if not os.environ.get("FAKE_SECURITY_DB") or not os.environ.get("FAKE_ANTHROPIC_STATE"):
    _die("fake claude: FAKE_SECURITY_DB/FAKE_ANTHROPIC_STATE unset; refusing (test guard)", 99)


def store_item_name():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if not cfg:
        return "Claude Code-credentials"
    h = hashlib.sha256(unicodedata.normalize("NFC", cfg).encode("utf-8")).hexdigest()[:8]
    return "Claude Code-credentials-" + h


def read_store():
    try:
        with open(os.environ["FAKE_SECURITY_DB"], "r", encoding="utf-8") as f:
            items = json.load(f).get("items", {})
    except (OSError, ValueError):
        return None
    raw = items.get("%s\x00%s" % (store_item_name(), os.environ.get("USER", "")))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def auth_login(argv):
    """`claude auth login --claudeai --email X`: print the authorize URL, wait for `code-ok#<state>`
    on stdin, then store a fresh grant for X in the item this env selects."""
    import secrets

    email = argv[argv.index("--email") + 1] if "--email" in argv else None
    state = "st-" + secrets.token_hex(3)
    print("Opening browser to sign in...", flush=True)
    print("If it did not open, visit: https://claude.com/cai/oauth/authorize?code=true&client_id=x&state=%s" % state, flush=True)
    line = sys.stdin.readline().strip()
    if not email or line != "code-ok#" + state:
        print("Login failed: bad code", flush=True)
        return 1
    creds = fake_anthropic.mint(email)

    def put(cur):
        cur = dict(cur or {})
        cur["claudeAiOauth"] = creds
        return cur

    keychain_db.update_json(os.environ["FAKE_SECURITY_DB"], store_item_name(), os.environ.get("USER", ""), put)
    print("Login successful.", flush=True)
    return 0


def main(argv):
    if argv[:1] == ["--version"]:
        print("%s (Claude Code)" % os.environ.get("FAKE_CLAUDE_VERSION", "2.1.280"))
        return 0
    if argv[:2] == ["auth", "login"]:
        return auth_login(argv)
    if argv[:2] == ["auth", "status"]:
        creds = read_store() or {}
        at = (creds.get("claudeAiOauth") or {}).get("accessToken")
        email = fake_anthropic.email_for_access(at) if at else None
        if not at:
            print(json.dumps({"loggedIn": False}))
            return 1
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": email}))
        return 0
    if "-p" in argv or "--print" in argv:
        if os.environ.get("CLAUDECODE"):
            _die("fake claude: probe inherited CLAUDECODE from a session env", 98)
        creds = read_store() or {}
        oauth = creds.get("claudeAiOauth") or {}
        status, body = fake_anthropic.messages(oauth.get("accessToken"), kind="probe")
        if status == 401 and oauth.get("refreshToken"):
            # as Claude Code does: refresh with the store's refresh token under its lock, persist, retry once
            cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.environ["HOME"], ".claude")
            lock = os.path.join(cfg, ".oauth_refresh.lock")
            try:
                os.mkdir(lock)
            except FileExistsError:
                print(json.dumps({"type": "result", "is_error": True, "result":
                                  "Failed to refresh OAuth token: another Claude Code process is refreshing it"}))
                return 1
            try:
                code, fresh = fake_anthropic.token_refresh(oauth["refreshToken"])
            finally:
                os.rmdir(lock)
            if code == 200:
                oauth = dict(oauth, accessToken=fresh["access_token"], refreshToken=fresh["refresh_token"],
                             expiresAt=fake_anthropic.now_ms() + fresh["expires_in"] * 1000)
                keychain_db.update_json(os.environ["FAKE_SECURITY_DB"], store_item_name(), os.environ.get("USER", ""),
                                        lambda cur: dict(cur or {}, claudeAiOauth=oauth))
                status, body = fake_anthropic.messages(oauth["accessToken"], kind="probe")
        if status == 200:
            print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "OK"}))
            return 0
        if status == 429:
            print(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                              "result": "You've hit your limit · resets 5pm (UTC)"}))
            return 1
        print(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                          "result": "Failed to authenticate: OAuth session expired and could not be refreshed"}))
        return 1
    _die("fake claude: unsupported invocation %r" % (argv,), 99)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
