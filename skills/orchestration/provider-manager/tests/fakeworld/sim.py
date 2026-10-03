"""A running Claude Code session, reduced to its credential behaviour.

Modelled on Claude Code 2.1.280's bundled source (`ed`/`gD`/`zy`/`rdo`, read from the binary):

- With no `<configDir>/.credentials.json`, every API request clears the token memo and re-reads the
  store. The real binary reads through a 30-second keychain cache; this model has none, so it adopts
  a switch (and dies of a stale one) sooner than the binary does, never later.
- A token within 5 minutes of `expiresAt` is refreshed under the refresh lock
  (`<configDir>/.oauth_refresh.lock` plus the legacy `<configDir>.lock`, proper-lockfile). The store is
  re-read inside the lock: if its access token changed, another process refreshed and the session
  adopts the change.
- An `invalid_grant` marks the refresh token dead. When the access token is then unusable, the turn
  fails with "OAuth session expired and could not be refreshed". In this model, that failure is a
  death.
- A 429 ends the turn (StopFailure `rate_limit`). The session is stalled, not dead.

What this model does not claim: proper-lockfile's exact retry schedule (it retries 5 times, briefly),
the 30 s read cache, or Claude Code's handling of MCP tokens. The real-binary drill (tests/drill) runs
the binary itself for the switch scenarios and the probe.
"""

import os
import time
from pathlib import Path

import fake_anthropic
import keychain_db

EXPIRY_BUFFER_MS = 300_000
DEATH = "Failed to authenticate: OAuth session expired and could not be refreshed"


class SessionDied(Exception):
    pass


class ClaudeCodeSim:
    def __init__(self, db_path, config_dir, user, name="S1", store_item="Claude Code-credentials"):
        self.db_path = db_path
        self.config_dir = Path(config_dir)
        self.user = user
        self.name = name
        self.store_item = store_item
        self.dead = None
        self.served = []
        self.stalled = []
        self.dead_rts = set()
        self.refreshes = 0

    # -- store ---------------------------------------------------------------------------------
    def _oauth(self):
        s = keychain_db.read_json(self.db_path, self.store_item, self.user)
        return (s or {}).get("claudeAiOauth") or None

    @staticmethod
    def _expiring(oauth):
        exp = oauth.get("expiresAt")
        return exp is not None and fake_anthropic.now_ms() + EXPIRY_BUFFER_MS >= exp

    def _lock(self):
        new = self.config_dir / ".oauth_refresh.lock"
        legacy = Path(os.path.realpath(str(self.config_dir)) + ".lock")
        for _ in range(5):
            try:
                os.mkdir(new)
            except FileExistsError:
                time.sleep(0.02)
                continue
            try:
                os.mkdir(legacy)
            except FileExistsError:
                os.rmdir(new)
                time.sleep(0.02)
                continue
            return (new, legacy)
        return None

    @staticmethod
    def _unlock(paths):
        for p in reversed(paths):
            try:
                os.rmdir(p)
            except OSError:
                pass

    def _refresh(self, force=False):
        t = self._oauth()
        if not force:
            if t and not self._expiring(t):
                return "not_needed"
        if not t or not t.get("refreshToken"):
            return "no_refresh_token"
        if t["refreshToken"] in self.dead_rts:
            return "known_dead_refresh_token"
        m = t.get("accessToken")
        d = self._oauth()
        if d and d.get("accessToken") != m:
            return "refreshed"
        if not force and d and not self._expiring(d):
            return "not_needed"
        lock = self._lock()
        if lock is None:
            return "lock_busy"
        try:
            z = self._oauth()
            if not z or not z.get("refreshToken"):
                return "no_refresh_token"
            posted = z["refreshToken"]
            if z.get("accessToken") != m:
                return "refreshed"
            status, body = fake_anthropic.token_refresh(posted)
            if status == 200:
                new = dict(z)
                new.update({
                    "accessToken": body["access_token"],
                    "refreshToken": body["refresh_token"],
                    "expiresAt": fake_anthropic.now_ms() + body["expires_in"] * 1000,
                })

                def put(cur):
                    cur = dict(cur or {})
                    cur["claudeAiOauth"] = new
                    return cur

                keychain_db.update_json(self.db_path, self.store_item, self.user, put)
                self.refreshes += 1
                return "refreshed"
            z2 = self._oauth()
            if z2 and z2.get("accessToken") != m:
                return "refreshed"
            if body.get("error") == "invalid_grant":
                self.dead_rts.add(posted)
                return "known_dead_refresh_token"
            return "refresh_failed"
        finally:
            self._unlock(lock)

    # -- one API request -----------------------------------------------------------------------
    def _die(self, why):
        self.dead = "%s [%s]" % (DEATH, why)
        raise SessionDied(self.dead)

    def request(self):
        if self.dead:
            raise SessionDied(self.dead)
        self._refresh()
        t = self._oauth()
        if not t or not t.get("accessToken"):
            self._die("no access token in store")
        status, body = fake_anthropic.messages(t["accessToken"])
        if status == 401:
            outcome = self._refresh(force=True)
            t2 = self._oauth()
            if outcome != "refreshed" or not t2:
                self._die("401, refresh outcome %s" % outcome)
            status, body = fake_anthropic.messages(t2["accessToken"])
            if status == 401:
                self._die("401 after refresh")
        if status == 429:
            self.stalled.append(time.time())
            return "rate_limit"
        self.served.append(body["served_by"])
        return "ok"

    def run(self, n):
        out = []
        for _ in range(n):
            out.append(self.request())
        return out
