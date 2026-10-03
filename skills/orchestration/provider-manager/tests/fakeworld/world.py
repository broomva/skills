"""A scratch machine for provider-manager tests: HOME, keychain, Orca roster, Anthropic stub.

Works against both the current scripts and an older checkout (PM_IMPL_DIR): it patches only the module
constants that exist, and it reaches the code through `security`, `claude` and urllib, the same
seams in either version.
"""

import json
import os
import sys
import urllib.request
import uuid
from pathlib import Path

import fake_anthropic
import fake_net
import keychain_db
from sim import ClaudeCodeSim

FAKEWORLD_DIR = Path(__file__).resolve().parent
ORCA_SERVICE = "Orca Claude Code Managed Credentials"
USER = "tester"


def _shim(path, target):
    path.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, target))
    path.chmod(0o755)


def default_paths(home):
    home = Path(home)
    return {
        "ORCA_DATA_PATH": home / "Library/Application Support/orca/profiles/local-default/orca-data.json",
        "CLAUDE_CONFIG_PATH": home / ".claude.json",
        "CLAUDE_CREDS_PATH": home / ".claude/.credentials.json",
        "USAGE_CACHE_PATH": home / ".cache/broomva-provider-usage.json",
        "PROVIDER_EVENTS_PATH": home / ".cache/broomva-provider-events.jsonl",
        "STATE_PATH": home / ".cache/broomva-provider-state.json",
        "BALANCER_LOCK_PATH": home / ".cache/broomva-provider-balancer.lock",
        "STALLED_PATH": home / ".cache/broomva-provider-stalled.jsonl",
        "CONFIG_PATH": home / ".config/broomva/provider-manager.json",
    }


class World:
    def __init__(self, tmp_path, monkeypatch, pm):
        self.pm = pm
        self.tmp = Path(tmp_path)
        self.home = self.tmp / "home"
        self.config_dir = self.home / ".claude"
        for d in (self.config_dir, self.home / ".cache", self.home / ".config/broomva",
                  self.home / "Library/Application Support/orca/profiles/local-default"):
            d.mkdir(parents=True, exist_ok=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir(exist_ok=True)
        _shim(self.bin / "security", FAKEWORLD_DIR / "fake_security.py")
        _shim(self.bin / "claude", FAKEWORLD_DIR / "fake_claude.py")
        (self.bin / "node").write_text("#!/bin/sh\necho 'fake node: refused (test guard)' >&2\nexit 99\n")
        (self.bin / "node").chmod(0o755)
        self.db = str(self.tmp / "keychain.json")
        self.api = str(self.tmp / "anthropic.json")

        for k in ("CLAUDE_CONFIG_DIR", "CLAUDE_SECURESTORAGE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.setenv("USER", USER)
        monkeypatch.setenv("LOGNAME", USER)
        monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % self.bin)
        monkeypatch.setenv("FAKE_SECURITY_DB", self.db)
        monkeypatch.setenv("FAKE_ANTHROPIC_STATE", self.api)
        monkeypatch.setenv("PYTHONPATH", str(FAKEWORLD_DIR))
        monkeypatch.setenv("CLAUDECODE", "1")  # hooks run inside sessions; the probe must strip it
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-under-test")
        self.paths = default_paths(self.home)
        for name, value in self.paths.items():
            if hasattr(pm, name):
                monkeypatch.setattr(pm, name, value)
        monkeypatch.setattr(urllib.request, "urlopen", fake_net.fake_urlopen)
        self.accounts = {}
        self._orca = {"settings": {"activeClaudeManagedAccountId": None, "claudeManagedAccounts": []}}
        self._save_orca()

    # -- names ---------------------------------------------------------------------------------
    def store_items(self):
        """(primary, [mirrors]) as the module under test names them."""
        if hasattr(self.pm, "store_item_names"):
            return self.pm.store_item_names()
        return self.pm.KEYCHAIN_CLAUDE_UNSCOPED, [self.pm.KEYCHAIN_CLAUDE_SCOPED]

    @property
    def primary(self):
        return self.store_items()[0]

    @property
    def mirror(self):
        return self.store_items()[1][0]

    # -- roster --------------------------------------------------------------------------------
    def _save_orca(self):
        p = self.paths["ORCA_DATA_PATH"]
        p.write_text(json.dumps(self._orca, indent=2))

    def _load_orca(self):
        self._orca = json.loads(self.paths["ORCA_DATA_PATH"].read_text())
        return self._orca

    def add_account(self, email, five_hour=10.0, seven_day=20.0, at_ttl=3600.0):
        acc_id = str(uuid.uuid4())
        org = str(uuid.uuid4())
        fake_anthropic.add_account(email, str(uuid.uuid4()), org, five_hour, seven_day)
        creds = fake_anthropic.mint(email, at_ttl)
        keychain_db.write_json(self.db, ORCA_SERVICE, acc_id, {"claudeAiOauth": creds})
        self._load_orca()
        self._orca["settings"]["claudeManagedAccounts"].append({
            "id": acc_id, "email": email, "organizationUuid": org,
            "organizationName": "%s's Organization" % email, "lastAuthenticatedAt": 1790000000000,
        })
        self._save_orca()
        self.accounts[email] = {"id": acc_id, "org": org}
        return acc_id

    def activate(self, email, mcp=None):
        """Put email's Orca copy in the store (as a fresh login would) and mark it active."""
        creds = self.orca_creds(email)
        primary, mirrors = self.store_items()
        for item in [primary] + list(mirrors):
            value = {"claudeAiOauth": dict(creds["claudeAiOauth"])}
            if mcp is not None:
                value["mcpOAuth"] = json.loads(json.dumps(mcp))
            keychain_db.write_json(self.db, item, USER, value)
        self._load_orca()
        self._orca["settings"]["activeClaudeManagedAccountId"] = self.accounts[email]["id"]
        self._save_orca()
        self.paths["CLAUDE_CONFIG_PATH"].write_text(json.dumps({"oauthAccount": {"emailAddress": email}}))

    def orca_active_email(self):
        active = self._load_orca()["settings"].get("activeClaudeManagedAccountId")
        for e, a in self.accounts.items():
            if a["id"] == active:
                return e
        return None

    # -- credentials ---------------------------------------------------------------------------
    def orca_creds(self, email):
        return keychain_db.read_json(self.db, ORCA_SERVICE, self.accounts[email]["id"])

    def set_orca_creds(self, email, value):
        keychain_db.write_json(self.db, ORCA_SERVICE, self.accounts[email]["id"], value)

    def store(self, item=None):
        return keychain_db.read_json(self.db, item or self.primary, USER)

    def store_raw(self, item=None):
        return keychain_db.read_raw(self.db, item or self.primary, USER)

    def store_email(self):
        at = ((self.store() or {}).get("claudeAiOauth") or {}).get("accessToken")
        return fake_anthropic.email_for_access(at) if at else None

    def make_orca_copy_stale(self, email):
        """The account was active, Claude Code rotated its refresh token, and nobody wrote the new one
        back: the Orca copy now holds a consumed refresh token and an expired access token."""
        creds = self.orca_creds(email)
        o = creds["claudeAiOauth"]
        fake_anthropic.consume(o["refreshToken"])
        fake_anthropic.expire_access(o["accessToken"])
        o["expiresAt"] = fake_anthropic.now_ms() - 60_000
        self.set_orca_creds(email, creds)

    def expire_store_access(self, item=None):
        """Bring the store's access token inside Claude Code's 5-minute refresh window."""
        def bump(cur):
            cur["claudeAiOauth"]["expiresAt"] = fake_anthropic.now_ms() + 60_000
            return cur
        keychain_db.update_json(self.db, item or self.primary, USER, bump)

    def faults(self, **kw):
        keychain_db.set_faults(self.db, **kw)

    def set_usage(self, email, **kw):
        fake_anthropic.set_account(email, **kw)

    # -- observation ---------------------------------------------------------------------------
    def events(self, kind=None):
        p = self.paths["PROVIDER_EVENTS_PATH"]
        if not p.exists():
            return []
        out = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        return [e for e in out if kind is None or e.get("event") == kind]

    def switches(self):
        return self.events("switch")

    def session(self, name="S1"):
        return ClaudeCodeSim(self.db, self.config_dir, USER, name=name, store_item="Claude Code-credentials")

    def env(self):
        return dict(os.environ)
