"""BRO-3192, Codex side: the auth.json snapshot, revoked copies, a logged decision for every balance
outcome, the reason a standby is not a candidate, the forced account chooser and the Arc pre-check."""

import copy as _copy
import json
import time
from pathlib import Path

import pytest
import pm_cli
import pm_store
import provider_manager as pm
from test_codex_provider import _make_dummy_jwt

pytestmark = pytest.mark.new_only
# A small fake Codex machine: a dict keychain, ~/.codex/auth.json in the scratch HOME (conftest), the
# token and usage endpoints stubbed. Measured 2026-10-19: devteam@ and carlos@ are two users of one
# Team workspace, and only one of them holds a live Codex CLI seat at a time.


DEV = "devteam@getstimulus.ai"
CARLOS = "carlos@getstimulus.ai"
DEV_ID = "d24aa235-8a59-5d76-852d-c66136a9c2fc"
CARLOS_ID = "dc906358-ff8c-5ad9-8e71-86e423b49425"
WS = "45663a8d-d52d-4b55-8dd3-2af5ce5e6779"


class CodexWorld:
    def __init__(self, monkeypatch):
        self.kc = {}
        self.writes = []
        self.refreshed = []
        self.usage_calls = []
        self.revoked = set()
        self.usage_pct = {}
        self.limit_type = {}
        self.throttled = set()
        self.refresh_error = {}
        self.auth = pm_store.CODEX_AUTH_PATH
        monkeypatch.setattr(pm, "read_orca_codex", self._read)
        monkeypatch.setattr(pm, "write_orca_codex", self._write)
        monkeypatch.setattr(pm, "refresh_codex_token", self._refresh)
        monkeypatch.setattr(pm, "fetch_codex_usage_raw", self._usage)
        monkeypatch.setattr(pm, "_guarded_update", lambda path, fn: True)

    def tokens(self, email, rt, ttl=3600, ws=WS):
        return {
            "id_token": _make_dummy_jwt({"email": email, "sub": "sub-" + email.split("@")[0]}),
            "access_token": _make_dummy_jwt({"exp": int(time.time()) + ttl, "rt": rt,
                                             "https://api.openai.com/auth": {"chatgpt_account_id": ws}}),
            "refresh_token": rt,
            "account_id": ws,
        }

    def login(self, email, rt, **kw):
        """`codex login` as email: the CLI writes auth.json (and nothing else)."""
        tokens = self.tokens(email, rt, **kw)
        self.auth.parent.mkdir(parents=True, exist_ok=True)
        self.auth.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": tokens}))
        return tokens

    def save_copy(self, key, email, tokens):
        self.kc[key] = {"auth_mode": "chatgpt", "tokens": _copy.deepcopy(tokens), "email": email}

    def auth_tokens(self):
        return json.loads(self.auth.read_text())["tokens"]

    def _read(self, key):
        return pm_store.Read("ok", _copy.deepcopy(self.kc[key])) if key in self.kc else pm_store.Read("absent", None)

    def _write(self, key, data, timeout=30):
        self.writes.append(key)
        self.kc[key] = _copy.deepcopy(data)
        return True

    def _refresh(self, rt, client_id=None, timeout=30):
        self.refreshed.append(rt)
        if rt in self.refresh_error:
            return 400, None, "HTTP 400: " + json.dumps({"error": {"code": self.refresh_error[rt]}})
        email = DEV if "dev" in rt else CARLOS
        new = self.tokens(email, rt + "-r")
        return 200, {k: new[k] for k in ("id_token", "access_token", "refresh_token")}, ""

    def _usage(self, access_token, account_id):
        rt = pm_store.decode_jwt_unverified(access_token).get("rt")
        self.usage_calls.append(rt)
        if rt in self.revoked:
            return 401, None, "HTTP 401: " + json.dumps({"error": {"message": "Token revoked", "code": "token_revoked"}})
        if rt in self.throttled:
            return 429, None, "HTTP 429: slow down"
        pct = self.usage_pct.get(rt, 10)
        lim = self.limit_type.get(rt)
        return 200, {"plan_type": "team",
                     "rate_limit": {"allowed": lim is None, "limit_reached": lim is not None,
                                    "primary_window": {"used_percent": pct, "limit_window_seconds": 18000},
                                    "secondary_window": {"used_percent": 5, "limit_window_seconds": 604800}},
                     "rate_limit_reached_type": lim}, ""


@pytest.fixture
def cx(monkeypatch):
    return CodexWorld(monkeypatch)


def _events(kind):
    p = Path(pm.PROVIDER_EVENTS_PATH)
    if not p.exists():
        return []
    return [e for e in (json.loads(l) for l in p.read_text().splitlines() if l.strip()) if e.get("event") == kind]


def _rows():
    return {r["email"]: r for r in pm.fetch_codex_usage(force=True)}


def test_a_raw_codex_login_is_snapshotted_into_its_copy_and_only_when_it_changes(cx):
    cli = cx.login(CARLOS, "rt-carlos-1")  # a raw `codex login`: auth.json only
    rows = _rows()
    assert rows[CARLOS]["isActive"] and rows[CARLOS]["telemetry"] == "ok"
    for key in (CARLOS_ID, CARLOS):
        assert key in cx.kc, "auth.json was not snapshotted"
        assert cx.kc[key]["tokens"]["refresh_token"] == "rt-carlos-1" and cx.kc[key]["email"] == CARLOS
    assert _events("codex.snapshot")[-1]["reason"] == "copy_missing"
    n = len(cx.writes)
    _rows()
    assert len(cx.writes) == n, "an unchanged auth.json must not be written again"

    cx.login(CARLOS, "rt-carlos-2")  # the CLI refreshed its own grant
    pm.evaluate_codex_balance(dry_run=True)
    assert cx.kc[CARLOS_ID]["tokens"]["refresh_token"] == "rt-carlos-2"
    assert _events("codex.snapshot")[-1]["reason"] == "tokens_changed"
    assert cx.refreshed == [], "a snapshot never refreshes anything"
    assert cx.auth_tokens()["refresh_token"] == "rt-carlos-2", "auth.json is never written by a snapshot"


def test_token_revoked_marks_the_copy_revoked_and_stops_spending_calls_on_it(cx):
    dev = cx.tokens(DEV, "rt-dev-1")
    cx.save_copy(DEV_ID, DEV, dev)
    cx.login(CARLOS, "rt-carlos-1")
    cx.revoked.add("rt-dev-1")  # carlos@'s login revoked devteam@'s seat
    rows = _rows()
    assert rows[DEV]["telemetry"] == "revoked" and rows[DEV]["usageStatus"] == "REVOKED"
    assert rows[DEV]["healthReason"] == "token_revoked" and rows[DEV]["needsLogin"]
    assert "revoked (token_revoked)" in rows[DEV]["standbyReason"]
    assert "one Codex CLI seat" in rows[DEV]["standbyReason"]
    assert pm.load_state()["codexHealth"][DEV_ID]["status"] == "revoked"
    assert [a for a in pm.list_codex_accounts() if a["email"] == DEV][0]["health"] == "revoked"
    calls = cx.usage_calls.count("rt-dev-1")
    _rows()
    assert cx.usage_calls.count("rt-dev-1") == calls, "a revoked grant is not sent to the endpoint again"

    cx.login(DEV, "rt-dev-2")  # devteam@ logs in again: its new grant is snapshotted, the mark is left behind
    rows = _rows()
    assert rows[DEV]["telemetry"] == "ok" and rows[DEV]["isActive"]
    assert DEV_ID not in pm.load_state().get("codexHealth", {})


def test_a_dead_standby_refresh_grant_is_spent_once(cx):
    dev = cx.tokens(DEV, "rt-dev-1", ttl=10)  # expiring: the usage path refreshes a standby copy
    cx.save_copy(DEV_ID, DEV, dev)
    cx.login(CARLOS, "rt-carlos-1")
    cx.refresh_error["rt-dev-1"] = "refresh_token_reused"
    assert _rows()[DEV]["telemetry"] == "revoked"
    _rows()
    _rows()
    assert cx.refreshed.count("rt-dev-1") == 1


def test_codex_usage_429_is_never_a_rate_limit(cx):
    cx.login(CARLOS, "rt-carlos-1")
    cx.throttled.add("rt-carlos-1")
    rows = _rows()
    assert rows[CARLOS]["telemetry"] == "throttled" and rows[CARLOS]["isRateLimited"] is False
    res = pm.evaluate_codex_balance(dry_run=True)
    assert res["action"] == "hold" and res["code"] == "telemetry_unavailable"


def test_every_codex_balance_outcome_is_logged_with_its_reason(cx, monkeypatch):
    import pm_codex_login
    monkeypatch.setattr(pm_codex_login, "arc_usable", lambda timeout=3.0: (False, "Arc is not running"))
    cx.save_copy(DEV_ID, DEV, cx.tokens(DEV, "rt-dev-1"))
    cx.login(CARLOS, "rt-carlos-1")
    cx.revoked.add("rt-dev-1")

    res = pm.evaluate_codex_balance(reason="hook")
    assert res["action"] == "hold" and res["code"] == "within_budget"
    assert _events("codex.balance.decision"), "a hold was not logged"
    ev = _events("codex.balance.decision")[-1]
    assert ev["action"] == "hold" and ev["code"] == "within_budget" and ev["reason"] == res["reason"]
    assert "revoked" in ev["standbys"][DEV] and ev["source"] == "hook" and ev["trace_id"]

    cx.usage_pct["rt-carlos-1"] = 96
    res = pm.evaluate_codex_balance(reason="hook")
    assert res["code"] == "relogin_unavailable" and "Arc is not running" in res["reason"]
    assert _events("codex.balance.decision")[-1]["code"] == "relogin_unavailable"
    assert len(_events("codex.balance.decision")) == 2


def test_usage_says_why_a_standby_is_not_a_candidate(cx, capsys, monkeypatch):
    cx.save_copy(DEV_ID, DEV, cx.tokens(DEV, "rt-dev-1"))
    cx.login(CARLOS, "rt-carlos-1")
    cx.revoked.add("rt-dev-1")
    monkeypatch.setattr("sys.argv", ["provider_manager.py", "usage", "--provider", "codex"])
    pm_cli.main(pm)
    out = capsys.readouterr().out
    dev_line = next(l for l in out.splitlines() if DEV in l)
    carlos_line = next(l for l in out.splitlines() if CARLOS in l)
    assert "REVOKED (token_revoked)" in dev_line and "re-login is needed" in dev_line
    assert carlos_line.rstrip().endswith("active") and "OK" in carlos_line


def test_shared_workspace_out_of_credits_never_switches_seats(cx, monkeypatch):
    import pm_codex_login
    monkeypatch.setattr(pm_codex_login, "arc_usable", lambda timeout=3.0: pytest.fail("no re-login may be tried"))
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-1"))
    cx.login(DEV, "rt-dev-1")
    cx.limit_type["rt-dev-1"] = "workspace_credits_depleted"
    rows = _rows()
    assert "workspace credits are shared" in (rows[CARLOS]["standbyReason"] or "")
    res = pm.evaluate_codex_balance()
    assert res["action"] == "hold" and res["code"] == "no_candidate"
    assert cx.auth_tokens()["refresh_token"] == "rt-dev-1"


def test_relogin_forces_the_account_chooser_in_the_configured_arc_space(cx, monkeypatch):
    import pm_codex_login
    pm.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    pm.CONFIG_PATH.write_text(json.dumps({"codexAccounts": {CARLOS: {"arcSpace": "Carlos"}}}))
    calls = []

    def fake_login(email, space_name="Stimulus"):
        calls.append((email, space_name))
        cx.login(email, "rt-carlos-new")
        return True, "ok"

    monkeypatch.setattr(pm_codex_login, "arc_usable", lambda timeout=3.0: (True, "ok"))
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login", fake_login)
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-1"))
    cx.login(DEV, "rt-dev-1")
    cx.revoked.add("rt-carlos-1")
    cx.usage_pct["rt-dev-1"] = 97

    res = pm.evaluate_codex_balance(reason="hook")
    assert res["action"] == "switched" and res["method"] == "autonomous_browser_login"
    assert calls == [(CARLOS, "Carlos")]
    assert cx.kc[CARLOS_ID]["tokens"]["refresh_token"] == "rt-carlos-new"
    assert cx.kc[DEV_ID]["tokens"]["refresh_token"] == "rt-dev-1", "the outgoing seat was saved first"
    assert "rt-carlos-1" not in cx.refreshed, "a revoked grant is never spent"

    # a failed re-login is not retried on every kick (each opens an Arc tab)
    cx.login(DEV, "rt-dev-2")
    cx.usage_pct["rt-dev-2"] = 97
    cx.revoked.add("rt-carlos-new")
    pm.update_state(lambda s: s.update(lastCodexSwitch={"at": 0}, codexLoginAttempts={CARLOS: time.time()}))
    res = pm.evaluate_codex_balance(reason="hook")
    assert res["code"] == "relogin_recently_attempted" and len(calls) == 1


def test_the_authorize_url_gets_prompt_login_once():
    url = "https://auth.openai.com/oauth/authorize?response_type=code&client_id=x"
    assert pm_codex_login_mod().with_account_chooser(url) == url + "&prompt=login"
    assert pm_codex_login_mod().with_account_chooser(url + "&prompt=consent") == url + "&prompt=consent"


def pm_codex_login_mod():
    import pm_codex_login
    return pm_codex_login


def test_an_unanswering_arc_is_reported_in_seconds_and_no_login_starts(monkeypatch):
    import subprocess as sp
    mod = pm_codex_login_mod()

    def fake_run(cmd, **kw):
        if cmd[0] == "pgrep":
            return sp.CompletedProcess(cmd, 0, "123\n", "")
        if cmd[0] == "osascript":
            raise sp.TimeoutExpired(cmd, kw.get("timeout"))
        raise AssertionError("unexpected command %s" % cmd)

    monkeypatch.setattr(mod, "is_arc_available", lambda: True)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **k: pytest.fail("codex login must not start"))
    ok, why = mod.arc_usable()
    assert not ok and why.startswith("Arc not answering AppleScript")
    ok, msg = mod.run_codex_autonomous_login(CARLOS, space_name="Carlos")
    assert not ok and "Arc not answering AppleScript" in msg


def test_arc_not_running_is_reported_without_starting_it(monkeypatch):
    import subprocess as sp
    mod = pm_codex_login_mod()
    seen = []

    def fake_run(cmd, **kw):
        seen.append(cmd[0])
        return sp.CompletedProcess(cmd, 1, "", "")

    monkeypatch.setattr(mod, "is_arc_available", lambda: True)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.arc_usable() == (False, "Arc is not running")
    assert seen == ["pgrep"], "`tell application \"Arc\"` would launch it"


def test_a_throttled_active_seat_is_never_moved_on_its_old_numbers(cx, monkeypatch):
    """Stratum B (BRO-3192 review): a usage 429 keeps the last numbers for display; acting on them
    started an Arc re-login (which revokes the live seat) from a 5-hour-old 96%."""
    import pm_codex_login
    monkeypatch.setattr(pm_codex_login, "arc_usable", lambda timeout=3.0: (True, "ok"))
    logins = []
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login",
                        lambda *a, **k: logins.append(a) or (False, "refused by the test"))
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-1"))
    cx.login(DEV, "rt-dev-1")
    cx.revoked.add("rt-carlos-1")
    cx.usage_pct["rt-dev-1"] = 96
    assert _rows()[DEV]["primary"]["usedPercent"] == 96
    cache = json.loads(Path(pm.USAGE_CACHE_PATH).read_text())
    cache["codex:" + DEV]["cachedAt"] -= 5 * 3600
    Path(pm.USAGE_CACHE_PATH).write_text(json.dumps(cache))
    cx.throttled.add("rt-dev-1")
    rows = _rows()
    assert rows[DEV]["telemetry"] == "throttled" and rows[DEV]["primary"]["usedPercent"] == 96
    try:
        res = pm.evaluate_codex_balance(reason="hook")
    except pm_store.StoreError as e:
        res = {"action": "raised", "code": str(e)}
    assert logins == [], "a re-login started on unreadable numbers"
    assert res["action"] == "hold" and res["code"] == "telemetry_unavailable"


def test_a_transient_standby_refresh_failure_is_not_a_relogin_candidate(cx, monkeypatch):
    import pm_codex_login
    monkeypatch.setattr(pm_codex_login, "arc_usable", lambda timeout=3.0: pytest.fail("no re-login for a blip"))
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-1", ttl=10))
    cx.login(DEV, "rt-dev-1")
    cx.usage_pct["rt-dev-1"] = 97
    monkeypatch.setattr(pm, "refresh_codex_token", lambda rt, client_id=None, timeout=30: (None, None, "timed out"))
    rows = _rows()
    assert rows[CARLOS]["telemetry"] == "unavailable" and not rows[CARLOS]["needsLogin"]
    res = pm.evaluate_codex_balance(reason="hook")
    assert res["action"] == "hold" and res["code"] == "no_candidate"


def test_a_copy_rotated_by_another_writer_is_not_spent(cx):
    stale = cx.tokens(CARLOS, "rt-carlos-1", ttl=10)
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-2"))  # a switch rotated it meanwhile
    cx.login(DEV, "rt-dev-1")
    assert pm._refresh_codex_copy(CARLOS_ID, CARLOS, stale) == (None, "copy_changed")
    assert cx.refreshed == []


def _no_login(monkeypatch):
    import pm_codex_login
    logins = []
    monkeypatch.setattr(pm_codex_login, "arc_usable", lambda timeout=3.0: (True, "ok"))
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login",
                        lambda *a, **k: logins.append(a) or (False, "refused by the test"))
    return logins


def test_a_switch_whose_target_copy_cannot_be_read_never_relogs_in(cx, monkeypatch):
    """Stratum B round 2: a keychain read error is not an absent copy; treating it as one started a
    browser login, which revokes the live seat."""
    logins = _no_login(monkeypatch)
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-1"))
    cx.login(DEV, "rt-dev-1")
    real_read = cx._read
    monkeypatch.setattr(pm, "read_orca_codex", lambda k: pm_store.Read("error", None, "security rc 36")
                        if k in (CARLOS_ID, CARLOS) else real_read(k))
    with pytest.raises(pm_store.StoreError, match="could not be read"):
        pm.switch_codex_account(CARLOS)
    assert logins == [] and cx.auth_tokens()["refresh_token"] == "rt-dev-1"


def test_a_switch_whose_target_copy_changed_meanwhile_never_relogs_in(cx, monkeypatch):
    logins = _no_login(monkeypatch)
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-1"))
    cx.login(DEV, "rt-dev-1")
    real_read = cx._read
    reads = {"n": 0}

    def rotating_read(key):  # another writer rotates carlos@'s copy right after the switch reads it
        if key == CARLOS_ID:
            reads["n"] += 1
            if reads["n"] == 3:
                cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-2"))
        return real_read(key)

    monkeypatch.setattr(pm, "read_orca_codex", rotating_read)
    with pytest.raises(pm_store.StoreError, match="copy_changed"):
        pm.switch_codex_account(CARLOS)
    assert logins == [] and cx.refreshed == [] and cx.auth_tokens()["refresh_token"] == "rt-dev-1"


def test_an_odd_standby_401_is_not_a_relogin_candidate(cx, monkeypatch):
    logins = _no_login(monkeypatch)
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-1"))
    cx.login(DEV, "rt-dev-1")
    cx.usage_pct["rt-dev-1"] = 97
    real_usage = cx._usage
    monkeypatch.setattr(pm, "fetch_codex_usage_raw", lambda at, acc: (401, None, "HTTP 401: <html>gateway</html>")
                        if pm_store.decode_jwt_unverified(at).get("rt") == "rt-carlos-1" else real_usage(at, acc))
    rows = _rows()
    assert rows[CARLOS]["telemetry"] == "auth_expired" and "not re-logged in" in rows[CARLOS]["standbyReason"]
    res = pm.evaluate_codex_balance(reason="hook")
    assert res["code"] == "no_candidate" and logins == []


@pytest.mark.parametrize("errored", [(CARLOS_ID,), (CARLOS,), (CARLOS_ID, CARLOS)],
                         ids=["id-key", "email-key", "both-keys"])
def test_an_unreadable_copy_under_any_key_is_never_absent(cx, monkeypatch, errored):
    """Stratum B round 3: with the id key absent and the email key unreadable, the copy read as
    "no saved copy", a re-login reason. One reader now decides, for every caller."""
    logins = _no_login(monkeypatch)
    cx.login(DEV, "rt-dev-1")
    cx.usage_pct["rt-dev-1"] = 97
    real_read = cx._read
    monkeypatch.setattr(pm, "read_orca_codex", lambda k: pm_store.Read("error", None, "security rc 36")
                        if k in errored else real_read(k))
    assert pm.read_codex_copy(CARLOS_ID, CARLOS).status == "error"
    rows = _rows()
    assert rows[CARLOS]["telemetry"] == "unavailable" and not rows[CARLOS]["needsLogin"]
    assert pm.evaluate_codex_balance(reason="hook")["code"] == "no_candidate"
    with pytest.raises(pm_store.StoreError, match="could not be read"):
        pm.switch_codex_account(CARLOS)
    assert logins == [] and cx.auth_tokens()["refresh_token"] == "rt-dev-1"


def test_a_missing_copy_reads_absent_and_may_be_relogged_in(cx):
    assert pm.read_codex_copy(CARLOS_ID, CARLOS).status == "absent"
    cx.save_copy(CARLOS, CARLOS, cx.tokens(CARLOS, "rt-carlos-1"))
    assert pm.read_codex_copy(CARLOS_ID, CARLOS).status == "ok"


def test_a_refresh_401_without_a_dead_grant_code_marks_nothing(cx, monkeypatch):
    cx.save_copy(CARLOS_ID, CARLOS, cx.tokens(CARLOS, "rt-carlos-1", ttl=10))
    cx.login(DEV, "rt-dev-1")
    monkeypatch.setattr(pm, "refresh_codex_token", lambda rt, client_id=None, timeout=30: (401, None, "HTTP 401: <html>gateway</html>"))
    rows = _rows()
    assert rows[CARLOS]["telemetry"] == "unavailable"
    assert CARLOS_ID not in pm.load_state().get("codexHealth", {})
