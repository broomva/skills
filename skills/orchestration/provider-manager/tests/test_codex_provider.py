"""Tests for OpenAI Codex provider support in provider-manager."""

import base64
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import pm_store
import provider_manager as pm
import pm_cli


def _make_dummy_jwt(payload: dict) -> str:
    header = {"alg": "RS256", "typ": "JWT"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=").decode("ascii")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"{h_b64}.{p_b64}.dummy_signature"


def test_decode_jwt_unverified():
    claims = {"email": "test@example.com", "sub": "user_123", "exp": 1800000000}
    jwt = _make_dummy_jwt(claims)
    decoded = pm_store.decode_jwt_unverified(jwt)
    assert decoded["email"] == "test@example.com"
    assert decoded["sub"] == "user_123"
    assert decoded["exp"] == 1800000000

    assert pm_store.decode_jwt_unverified("") == {}
    assert pm_store.decode_jwt_unverified(None) == {}
    assert pm_store.decode_jwt_unverified("invalid.token") == {}


def test_extract_codex_identity():
    id_claims = {"email": "devteam@getstimulus.ai", "name": "Stimulus Dev", "sub": "sub_456"}
    access_claims = {
        "https://api.openai.com/auth": {
            "chatgpt_account_id": "acc_789",
            "chatgpt_user_id": "user_999",
            "chatgpt_plan_type": "team",
        }
    }
    tokens = {
        "id_token": _make_dummy_jwt(id_claims),
        "access_token": _make_dummy_jwt(access_claims),
        "refresh_token": "rf_123",
        "account_id": "acc_789",
    }
    ident = pm_store.extract_codex_identity(tokens)
    assert ident["email"] == "devteam@getstimulus.ai"
    assert ident["accountId"] == "acc_789"
    assert ident["userId"] == "user_999"
    assert ident["planType"] == "team"
    assert ident["name"] == "Stimulus Dev"


def test_codex_token_expiring():
    now_sec = int(time.time())
    fresh_jwt = _make_dummy_jwt({"exp": now_sec + 3600})
    expiring_jwt = _make_dummy_jwt({"exp": now_sec + 60})
    expired_jwt = _make_dummy_jwt({"exp": now_sec - 100})

    assert not pm_store.codex_token_expiring({"access_token": fresh_jwt}, margin_ms=300_000)
    assert pm_store.codex_token_expiring({"access_token": expiring_jwt}, margin_ms=300_000)
    assert pm_store.codex_token_expiring({"access_token": expired_jwt}, margin_ms=300_000)
    assert pm_store.codex_token_expiring({}, margin_ms=300_000)


def test_read_and_write_codex_auth(tmp_path):
    auth_file = tmp_path / "auth.json"
    res = pm_store.read_codex_auth(auth_file)
    assert res.status == "absent"

    data = {"auth_mode": "chatgpt", "tokens": {"access_token": "tok1", "refresh_token": "rf1"}}
    ok = pm_store.write_codex_auth(data, auth_file)
    assert ok is True
    assert auth_file.is_file()

    read_back = pm_store.read_codex_auth(auth_file)
    assert read_back.status == "ok"
    assert read_back.data == data

    # Malformed JSON
    auth_file.write_text("not-json")
    read_err = pm_store.read_codex_auth(auth_file)
    assert read_err.status == "error"


def test_codex_roster(monkeypatch, tmp_path):
    monkeypatch.setattr(pm, "get_orca_data", lambda: {"settings": {"codexManagedAccounts": []}})
    monkeypatch.setattr(pm, "read_codex_auth", lambda: pm_store.Read("absent", None))

    roster = pm.codex_roster()
    emails = [a["email"].lower() for a in roster]
    assert "devteam@getstimulus.ai" in emails
    assert "carlos@getstimulus.ai" in emails


def test_get_codex_auth_status(monkeypatch):
    id_claims = {"email": "devteam@getstimulus.ai", "sub": "sub_1"}
    access_claims = {"exp": int(time.time()) + 3600, "https://api.openai.com/auth": {"chatgpt_plan_type": "team"}}
    fake_tokens = {
        "id_token": _make_dummy_jwt(id_claims),
        "access_token": _make_dummy_jwt(access_claims),
        "refresh_token": "rf_1",
        "account_id": "acc_1",
    }
    monkeypatch.setattr(pm, "read_codex_auth", lambda: pm_store.Read("ok", {"auth_mode": "chatgpt", "tokens": fake_tokens}))

    st = pm.get_codex_auth_status()
    assert st["loggedIn"] is True
    assert st["provider"] == "codex"
    assert st["email"] == "devteam@getstimulus.ai"
    assert st["planType"] == "team"
    assert st["tokenFresh"] is True


def test_list_codex_accounts(monkeypatch):
    id_claims = {"email": "devteam@getstimulus.ai"}
    access_claims = {"exp": int(time.time()) + 3600, "https://api.openai.com/auth": {"chatgpt_plan_type": "team"}}
    tokens = {
        "id_token": _make_dummy_jwt(id_claims),
        "access_token": _make_dummy_jwt(access_claims),
        "refresh_token": "rf_dev",
        "account_id": "acc_1",
    }
    ctx = {
        "accounts": [
            {"id": "id_1", "email": "devteam@getstimulus.ai", "organizationName": "Stimulus", "authMethod": "chatgpt"},
            {"id": "id_2", "email": "carlos@getstimulus.ai", "organizationName": "Stimulus", "authMethod": "chatgpt"},
        ],
        "copies": {
            "id_1": pm_store.Read("ok", {"tokens": tokens}),
            "id_2": pm_store.Read("absent", None),
        },
        "store": pm_store.Read("ok", {"auth_mode": "chatgpt", "tokens": tokens}),
        "storeTokens": tokens,
        "activeIdentity": {"email": "devteam@getstimulus.ai", "planType": "team"},
        "activeAccountId": "id_1",
        "storeReadable": True,
    }
    res = pm.list_codex_accounts(ctx)
    assert len(res) == 2
    dev = next(a for a in res if a["email"] == "devteam@getstimulus.ai")
    carlos = next(a for a in res if a["email"] == "carlos@getstimulus.ai")

    assert dev["isActive"] is True
    assert dev["hasStoredCredentials"] is True
    assert dev["isTokenFresh"] is True

    assert carlos["isActive"] is False
    assert carlos["hasStoredCredentials"] is False
    assert carlos["needsLogin"] is True


def test_switch_codex_account_success(monkeypatch, tmp_path):
    target_tokens = {
        "id_token": _make_dummy_jwt({"email": "carlos@getstimulus.ai"}),
        "access_token": _make_dummy_jwt({"exp": int(time.time()) + 3600}),
        "refresh_token": "rf_carlos_live",
        "account_id": "acc_stimulus",
    }
    outgoing_tokens = {
        "id_token": _make_dummy_jwt({"email": "devteam@getstimulus.ai"}),
        "access_token": _make_dummy_jwt({"exp": int(time.time()) + 3600}),
        "refresh_token": "rf_devteam",
        "account_id": "acc_stimulus",
    }
    keychain_db = {
        "carlos@getstimulus.ai": {"tokens": target_tokens},
        "dc906358-ff8c-5ad9-8e71-86e423b49425": {"tokens": target_tokens},
    }

    monkeypatch.setattr(pm, "read_orca_codex", lambda k: pm_store.Read("ok", keychain_db.get(k)) if k in keychain_db else pm_store.Read("absent", None))
    monkeypatch.setattr(pm, "write_orca_codex", lambda k, d, timeout=30: keychain_db.__setitem__(k, d) or True)

    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": outgoing_tokens}))
    monkeypatch.setattr(pm_store, "CODEX_AUTH_PATH", auth_path)
    monkeypatch.setattr(pm, "CODEX_AUTH_PATH", auth_path)

    # Mock refresh response
    refreshed_data = {
        "id_token": _make_dummy_jwt({"email": "carlos@getstimulus.ai"}),
        "access_token": _make_dummy_jwt({"exp": int(time.time()) + 7200}),
        "refresh_token": "rf_carlos_new",
    }
    monkeypatch.setattr(pm, "refresh_codex_token", lambda rf, client_id=None, timeout=30: (200, refreshed_data, ""))
    monkeypatch.setattr(pm, "_guarded_update", lambda path, fn: None)

    res = pm.switch_codex_account("carlos@getstimulus.ai")
    assert res["status"] == "switched"
    assert res["active"] == "carlos@getstimulus.ai"
    assert res["previous"] == "devteam@getstimulus.ai"

    # Verify auth.json was rewritten with new tokens
    current_auth = json.loads(auth_path.read_text())
    assert current_auth["tokens"]["refresh_token"] == "rf_carlos_new"

    # Verify outgoing tokens were backed up
    assert "devteam@getstimulus.ai" in keychain_db


def test_evaluate_codex_balance(monkeypatch):
    monkeypatch.setattr(pm, "load_state", lambda: {"lastCodexSwitch": {"at": 0}})

    # Case 1: Active is healthy (40% 5h) -> hold
    def fake_usage_healthy(force=False, ctx=None):
        return [
            {
                "id": "id_1", "email": "devteam@getstimulus.ai", "isActive": True,
                "telemetry": "ok", "isRateLimited": False,
                "primary": {"usedPercent": 40}, "secondary": {"usedPercent": 10},
            },
            {
                "id": "id_2", "email": "carlos@getstimulus.ai", "isActive": False,
                "telemetry": "ok", "isRateLimited": False,
                "primary": {"usedPercent": 10}, "secondary": {"usedPercent": 5},
            }
        ]

    monkeypatch.setattr(pm, "fetch_codex_usage", fake_usage_healthy)
    dec1 = pm.evaluate_codex_balance(threshold=90.0)
    assert dec1["action"] == "hold"

    # Case 2: Active is limited -> balance switches to standby
    def fake_usage_limited(force=False, ctx=None):
        return [
            {
                "id": "id_1", "email": "devteam@getstimulus.ai", "isActive": True,
                "telemetry": "ok", "isRateLimited": True, "rateLimitType": "workspace_member_credits_depleted",
                "primary": {"usedPercent": 100}, "secondary": {"usedPercent": 20},
            },
            {
                "id": "id_2", "email": "carlos@getstimulus.ai", "isActive": False,
                "telemetry": "ok", "isRateLimited": False,
                "primary": {"usedPercent": 15}, "secondary": {"usedPercent": 5},
            }
        ]

    monkeypatch.setattr(pm, "fetch_codex_usage", fake_usage_limited)
    dec2 = pm.evaluate_codex_balance(threshold=90.0, dry_run=True)
    assert dec2["action"] == "would_switch"
    assert dec2["target"] == "carlos@getstimulus.ai"


def test_evaluate_codex_balance_arc_fallback(monkeypatch):
    import pm_codex_login
    monkeypatch.setattr(pm, "load_state", lambda: {"lastCodexSwitch": {"at": 0}})
    monkeypatch.setattr(pm_codex_login, "arc_usable", lambda timeout=3.0: (True, "ok"))

    def fake_usage_standby_needs_login(force=False, ctx=None):
        return [
            {
                "id": "id_1", "email": "carlos@getstimulus.ai", "isActive": True,
                "telemetry": "ok", "isRateLimited": True,
                "primary": {"usedPercent": 100}, "secondary": {"usedPercent": 20},
            },
            {
                "id": "id_2", "email": "devteam@getstimulus.ai", "isActive": False,
                "telemetry": "needs_login", "needsLogin": True, "isRateLimited": False,
                "primary": None, "secondary": None,
            }
        ]

    monkeypatch.setattr(pm, "fetch_codex_usage", fake_usage_standby_needs_login)
    dec = pm.evaluate_codex_balance(threshold=90.0, dry_run=True)
    assert dec["action"] == "would_switch"
    assert dec["target"] == "devteam@getstimulus.ai"
    assert "re-auth via Arc" in dec["reason"]


def test_evaluate_codex_balance_cooldown(monkeypatch):
    now = time.time()
    monkeypatch.setattr(pm, "load_state", lambda: {"lastCodexSwitch": {"at": now - 300}})  # 5 min ago

    def fake_usage_high(force=False, ctx=None):
        return [
            {
                "id": "id_1", "email": "carlos@getstimulus.ai", "isActive": True,
                "telemetry": "ok", "isRateLimited": False,
                "primary": {"usedPercent": 95}, "secondary": {"usedPercent": 20},
            },
            {
                "id": "id_2", "email": "devteam@getstimulus.ai", "isActive": False,
                "telemetry": "ok", "isRateLimited": False,
                "primary": {"usedPercent": 10}, "secondary": {"usedPercent": 5},
            }
        ]

    monkeypatch.setattr(pm, "fetch_codex_usage", fake_usage_high)
    dec = pm.evaluate_codex_balance(threshold=90.0, dry_run=True)
    assert dec["action"] == "hold"
    assert "cooldown active" in dec["reason"]


def test_run_auto_all_providers(monkeypatch):
    monkeypatch.setattr(pm, "load_state", lambda: {"lastEvalAt": 0, "lastCodexSwitch": {"at": 0}})
    monkeypatch.setattr(pm, "balance_accounts", lambda **kw: {"action": "hold", "reason": "claude_ok"})
    monkeypatch.setattr(pm, "evaluate_codex_balance", lambda **kw: {"action": "hold", "reason": "codex_ok"})

    res = pm.run_auto(reason="test", provider="all")
    assert "claude" in res
    assert "codex" in res
    assert res["claude"]["reason"] == "claude_ok"
    assert res["codex"]["reason"] == "codex_ok"


def test_write_codex_auth_file_mode(tmp_path):
    auth_file = tmp_path / "auth.json"
    data = {"auth_mode": "chatgpt", "tokens": {"access_token": "tok1"}}
    ok = pm_store.write_codex_auth(data, auth_file)
    assert ok is True
    # Verify file permissions are 0600 (read/write only by owner)
    mode = auth_file.stat().st_mode & 0o777
    assert mode == 0o600


def test_fetch_codex_usage_skips_refresh_for_active(monkeypatch):
    id_claims = {"email": "devteam@getstimulus.ai"}
    access_claims = {"exp": int(time.time()) - 100}  # expired
    tokens = {
        "id_token": _make_dummy_jwt(id_claims),
        "access_token": _make_dummy_jwt(access_claims),
        "refresh_token": "rf_active",
        "account_id": "acc_stimulus",
    }
    ctx = {
        "accounts": [{"id": "id_1", "email": "devteam@getstimulus.ai"}],
        "copies": {"id_1": pm_store.Read("ok", {"tokens": tokens})},
        "store": pm_store.Read("ok", {"auth_mode": "chatgpt", "tokens": tokens}),
        "storeTokens": tokens,
        "activeIdentity": {"email": "devteam@getstimulus.ai"},
        "activeAccountId": "id_1",
        "storeReadable": True,
    }
    refresh_called = []
    monkeypatch.setattr(pm, "refresh_codex_token", lambda rf: refresh_called.append(rf) or (200, {}, ""))
    monkeypatch.setattr(pm, "fetch_codex_usage_raw", lambda tok, acc: (200, {"rate_limit": {}}, ""))

    res = pm.fetch_codex_usage(force_refresh=True, ctx=ctx)
    # Active account token must NOT be refreshed by usage check
    assert len(refresh_called) == 0
    assert len(res) == 1
    assert res[0]["isActive"] is True


def test_switch_codex_account_aborts_on_keychain_write_failure(monkeypatch, tmp_path):
    target_tokens = {
        "id_token": _make_dummy_jwt({"email": "carlos@getstimulus.ai"}),
        "access_token": _make_dummy_jwt({"exp": int(time.time()) + 3600}),
        "refresh_token": "rf_carlos_live",
        "account_id": "acc_stimulus",
    }
    keychain_db = {
        "carlos@getstimulus.ai": {"tokens": target_tokens},
        "dc906358-ff8c-5ad9-8e71-86e423b49425": {"tokens": target_tokens},
    }

    monkeypatch.setattr(pm, "read_orca_codex", lambda k: pm_store.Read("ok", keychain_db.get(k)))
    # write_orca_codex fails
    monkeypatch.setattr(pm, "write_orca_codex", lambda k, d, timeout=30: False)

    auth_path = tmp_path / "auth.json"
    initial_auth = json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "orig"}})
    auth_path.write_text(initial_auth)
    monkeypatch.setattr(pm_store, "CODEX_AUTH_PATH", auth_path)
    monkeypatch.setattr(pm, "CODEX_AUTH_PATH", auth_path)

    refreshed_data = {
        "id_token": _make_dummy_jwt({"email": "carlos@getstimulus.ai"}),
        "access_token": _make_dummy_jwt({"exp": int(time.time()) + 7200}),
        "refresh_token": "rf_carlos_new",
    }
    monkeypatch.setattr(pm, "refresh_codex_token", lambda rf, client_id=None, timeout=30: (200, refreshed_data, ""))

    with pytest.raises(pm_store.StoreError) as excinfo:
        pm.switch_codex_account("carlos@getstimulus.ai")

    assert "Failed to persist refreshed credentials" in str(excinfo.value)
    # auth.json MUST remain untouched
    assert auth_path.read_text() == initial_auth


def test_login_codex_headless(monkeypatch):
    import pm_codex_login
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login",
                        lambda email, space_name="Stimulus": (True, f"Logged in {email}"))
    res = pm.login_codex_headless("carlos@getstimulus.ai")
    assert res["success"] is True
    assert res["email"] == "carlos@getstimulus.ai"
    assert res["provider"] == "codex"


def test_switch_codex_account_autonomous_fallback(monkeypatch, tmp_path):
    import pm_codex_login
    # Simulate missing/invalidated stored token
    monkeypatch.setattr(pm, "read_orca_codex", lambda k: pm_store.Read("absent", None))

    auth_path = tmp_path / "auth.json"
    outgoing_tokens = {"access_token": "dev_tok", "email": "devteam@getstimulus.ai"}
    auth_path.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": outgoing_tokens}))
    monkeypatch.setattr(pm_store, "CODEX_AUTH_PATH", auth_path)
    monkeypatch.setattr(pm, "CODEX_AUTH_PATH", auth_path)

    # Mock autonomous login to write new auth
    def mock_auto_login(email, space_name="Stimulus"):
        carlos_tokens = {
            "id_token": _make_dummy_jwt({"email": "carlos@getstimulus.ai"}),
            "access_token": _make_dummy_jwt({"exp": int(time.time()) + 3600}),
            "refresh_token": "rf_carlos_auto",
            "account_id": "acc_stimulus",
        }
        auth_path.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": carlos_tokens}))
        return True, "autologin ok"

    monkeypatch.setattr(pm_codex_login, "arc_usable", lambda timeout=3.0: (True, "ok"))
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login", mock_auto_login)
    monkeypatch.setattr(pm, "_guarded_update", lambda path, fn: None)

    res = pm.switch_codex_account("carlos@getstimulus.ai")
    assert res["status"] == "switched"
    assert res["active"] == "carlos@getstimulus.ai"
    assert res["method"] == "autonomous_browser_login"



