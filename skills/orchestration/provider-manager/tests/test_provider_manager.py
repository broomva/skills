import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure script dir is on path
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import provider_manager as pm


@pytest.fixture
def mock_orca_data():
    return {
        "settings": {
            "activeClaudeManagedAccountId": "acc-1",
            "claudeManagedAccounts": [
                {
                    "id": "acc-1",
                    "email": "primary@example.com",
                    "organizationName": "Primary Org",
                    "organizationUuid": "org-uuid-1",
                    "lastAuthenticatedAt": 1700000000000
                },
                {
                    "id": "acc-2",
                    "email": "secondary@example.com",
                    "organizationName": "Secondary Org",
                    "organizationUuid": "org-uuid-2",
                    "lastAuthenticatedAt": 1700000000000
                }
            ]
        }
    }


@pytest.fixture
def mock_claude_json():
    return {
        "oauthAccount": {
            "emailAddress": "primary@example.com",
            "organizationUuid": "org-uuid-1",
            "organizationName": "Primary Org",
            "organizationType": "claude_max"
        }
    }


def test_list_accounts(mock_orca_data, mock_claude_json):
    future_ms = int((time.time() + 3600) * 1000)
    fake_creds_1 = {
        "claudeAiOauth": {
            "accessToken": "tok-1",
            "expiresAt": future_ms
        }
    }
    fake_creds_2 = {
        "claudeAiOauth": {
            "accessToken": "tok-2",
            "expiresAt": future_ms
        }
    }

    def fake_read_keychain(service, account=None):
        if service == pm.KEYCHAIN_ORCA_SERVICE:
            if account == "acc-1":
                return fake_creds_1
            if account == "acc-2":
                return fake_creds_2
        return None

    with patch.object(pm, "get_orca_data", return_value=mock_orca_data), \
         patch.object(pm, "get_claude_json", return_value=mock_claude_json), \
         patch.object(pm, "read_keychain_generic_password", side_effect=fake_read_keychain):
        accounts = pm.list_accounts()
        assert len(accounts) == 2
        
        acc1 = accounts[0]
        assert acc1["id"] == "acc-1"
        assert acc1["email"] == "primary@example.com"
        assert acc1["isActive"] is True
        assert acc1["hasStoredCredentials"] is True
        assert acc1["isTokenFresh"] is True
        assert acc1["subscriptionType"] == "claude_max"

        acc2 = accounts[1]
        assert acc2["id"] == "acc-2"
        assert acc2["email"] == "secondary@example.com"
        assert acc2["isActive"] is False
        assert acc2["hasStoredCredentials"] is True
        assert acc2["isTokenFresh"] is True


def test_switch_account_success(mock_orca_data, mock_claude_json):
    future_ms = int((time.time() + 3600) * 1000)
    fake_creds_2 = {
        "claudeAiOauth": {
            "accessToken": "tok-2",
            "refreshToken": "ref-2",
            "expiresAt": future_ms
        }
    }

    saved_claude = {}
    saved_orca = {}
    keychain_writes = []

    def fake_read_keychain(service, account=None):
        if service == pm.KEYCHAIN_ORCA_SERVICE and account == "acc-2":
            return fake_creds_2
        return None

    def fake_write_keychain(service, account, data):
        keychain_writes.append((service, account, data))
        return True

    def fake_save_claude(cfg):
        saved_claude.update(cfg)
        return True

    def fake_save_orca(data):
        saved_orca.update(data)
        return True

    with patch.object(pm, "get_orca_data", return_value=mock_orca_data), \
         patch.object(pm, "get_claude_json", return_value=mock_claude_json), \
         patch.object(pm, "read_keychain_generic_password", side_effect=fake_read_keychain), \
         patch.object(pm, "write_keychain_generic_password", side_effect=fake_write_keychain), \
         patch.object(pm, "save_claude_json", side_effect=fake_save_claude), \
         patch.object(pm, "save_orca_data", side_effect=fake_save_orca), \
         patch.object(pm, "get_claude_auth_status", return_value={"loggedIn": True, "email": "secondary@example.com"}):

        result = pm.switch_account("secondary@example.com")
        assert result["success"] is True
        assert result["switchedTo"] == "secondary@example.com"
        assert result["accountId"] == "acc-2"

        # Verify Keychain writes for both scoped and unscoped services
        services_written = [kw[0] for kw in keychain_writes]
        assert pm.KEYCHAIN_CLAUDE_SCOPED in services_written
        assert pm.KEYCHAIN_CLAUDE_UNSCOPED in services_written

        # Verify ~/.claude.json was updated with secondary org
        assert saved_claude["oauthAccount"]["emailAddress"] == "secondary@example.com"
        assert saved_claude["oauthAccount"]["organizationUuid"] == "org-uuid-2"

        # Verify orca-data.json was updated with active account ID
        assert saved_orca["settings"]["activeClaudeManagedAccountId"] == "acc-2"


def test_switch_account_not_found(mock_orca_data, mock_claude_json):
    with patch.object(pm, "get_orca_data", return_value=mock_orca_data), \
         patch.object(pm, "get_claude_json", return_value=mock_claude_json):
        with pytest.raises(ValueError, match="not found in managed accounts roster"):
            pm.switch_account("nonexistent@example.com")


def test_switch_account_missing_creds(mock_orca_data, mock_claude_json):
    with patch.object(pm, "get_orca_data", return_value=mock_orca_data), \
         patch.object(pm, "get_claude_json", return_value=mock_claude_json), \
         patch.object(pm, "read_keychain_generic_password", return_value=None):
        with pytest.raises(RuntimeError, match="No credentials stored in Keychain"):
            pm.switch_account("secondary@example.com")


def test_rotate_account_dry_run(mock_orca_data, mock_claude_json):
    future_ms = int((time.time() + 3600) * 1000)
    fake_creds = {"claudeAiOauth": {"accessToken": "t", "expiresAt": future_ms}}

    with patch.object(pm, "get_orca_data", return_value=mock_orca_data), \
         patch.object(pm, "get_claude_json", return_value=mock_claude_json), \
         patch.object(pm, "read_keychain_generic_password", return_value=fake_creds):
        result = pm.rotate_account(reason="rate_limit_429", dry_run=True)
        assert result["success"] is True
        assert result["dryRun"] is True
        assert result["currentAccount"] == "primary@example.com"
        assert result["nextAccount"] == "secondary@example.com"
        assert result["reason"] == "rate_limit_429"


def test_rotate_account_no_alternative(mock_orca_data, mock_claude_json):
    # Only 1 account in roster
    single_account_orca = {
        "settings": {
            "activeClaudeManagedAccountId": "acc-1",
            "claudeManagedAccounts": [mock_orca_data["settings"]["claudeManagedAccounts"][0]]
        }
    }
    with patch.object(pm, "get_orca_data", return_value=single_account_orca), \
         patch.object(pm, "get_claude_json", return_value=mock_claude_json), \
         patch.object(pm, "read_keychain_generic_password", return_value={"claudeAiOauth": {}}):
        result = pm.rotate_account()
        assert result["success"] is False
        assert "only 1 account configured" in result["error"]


def test_write_keychain_generic_password_token_not_in_argv():
    secret_token = "super_secret_oauth_access_token_12345"
    data = {
        "claudeAiOauth": {
            "accessToken": secret_token
        }
    }
    with patch.object(pm, "run_cmd", return_value=MagicMock(returncode=0)) as mock_run:
        ok = pm.write_keychain_generic_password("TestService", "testuser", data)
        assert ok is True
        mock_run.assert_called_once()
        cmd_args, kwargs = mock_run.call_args
        command_list = cmd_args[0]
        # Command should only be ["security", "-i"]
        assert command_list == ["security", "-i"]
        # Secret token must NOT appear anywhere in the argv list
        for arg in command_list:
            assert secret_token not in arg
        # Secret token payload is passed via input_str on stdin (hex-encoded)
        input_str = kwargs.get("input_str", "")
        assert secret_token not in input_str
        assert secret_token.encode("utf-8").hex() in input_str


def test_usage_cache_read_write(tmp_path):
    test_cache_file = tmp_path / "test-usage.json"
    data = {
        "updatedAt": 1234567.0,
        "accounts": {
            "acc-1": {
                "id": "acc-1",
                "cachedAt": 1234567.0,
                "five_hour": {"utilization": 25.0},
                "status": "ok"
            }
        }
    }
    with patch.object(pm, "USAGE_CACHE_PATH", test_cache_file):
        ok = pm.save_usage_cache(data)
        assert ok is True
        loaded = pm.read_usage_cache()
        assert loaded["updatedAt"] == 1234567.0
        assert "acc-1" in loaded["accounts"]
        assert loaded["accounts"]["acc-1"]["five_hour"]["utilization"] == 25.0


def test_fetch_account_usage_cached(tmp_path):
    test_cache_file = tmp_path / "test-usage.json"
    now = time.time()
    cached_entry = {
        "id": "acc-1",
        "cachedAt": now - 10,  # 10s old, well within 60s TTL
        "five_hour": {"utilization": 15.0},
        "seven_day": {"utilization": 50.0},
        "isRateLimited": False,
        "status": "ok"
    }
    with patch.object(pm, "USAGE_CACHE_PATH", test_cache_file), \
         patch.object(pm, "read_usage_cache", return_value={"accounts": {"acc-1": cached_entry}}):
        usage = pm.fetch_account_usage("acc-1", force_refresh=False)
        assert usage == cached_entry


def test_fetch_account_usage_api_call(tmp_path):
    test_cache_file = tmp_path / "test-usage.json"
    fake_creds = {
        "claudeAiOauth": {
            "accessToken": "test-access-token",
            "expiresAt": int((time.time() + 3600) * 1000)
        }
    }
    api_payload = {
        "five_hour": {"utilization": 30.0, "resets_at": "2026-10-01T00:00:00Z"},
        "seven_day": {"utilization": 45.0, "resets_at": "2026-10-05T00:00:00Z"}
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(api_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch.object(pm, "USAGE_CACHE_PATH", test_cache_file), \
         patch.object(pm, "read_usage_cache", return_value={"accounts": {}}), \
         patch.object(pm, "read_keychain_generic_password", return_value=fake_creds), \
         patch.object(pm.urllib.request, "urlopen", return_value=mock_resp):
        usage = pm.fetch_account_usage("acc-1", force_refresh=True)
        assert usage is not None
        assert usage["five_hour"]["utilization"] == 30.0
        assert usage["seven_day"]["utilization"] == 45.0
        assert usage["status"] == "ok"
        assert usage["isRateLimited"] is False


def test_refresh_account_token_persists_rotated_token(mock_orca_data):
    fake_creds = {
        "claudeAiOauth": {
            "accessToken": "old-access-token",
            "refreshToken": "old-refresh-token",
            "expiresAt": int((time.time() - 100) * 1000)
        }
    }
    refresh_response = {
        "access_token": "new-access-token-999",
        "refresh_token": "new-rotated-refresh-token-888",
        "expires_in": 7200
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(refresh_response).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    saved_keychain = {}

    def fake_write_keychain(service, account, data):
        saved_keychain[(service, account)] = data
        return True

    with patch.object(pm, "read_keychain_generic_password", return_value=fake_creds), \
         patch.object(pm, "write_keychain_generic_password", side_effect=fake_write_keychain), \
         patch.object(pm, "get_orca_data", return_value=mock_orca_data), \
         patch.object(pm, "save_orca_data", return_value=True), \
         patch.object(pm.urllib.request, "urlopen", return_value=mock_resp):

        res = pm.refresh_account_token("acc-1")
        assert res is not None
        assert res["claudeAiOauth"]["accessToken"] == "new-access-token-999"
        assert res["claudeAiOauth"]["refreshToken"] == "new-rotated-refresh-token-888"

        # Verify Keychain was written with the rotated refresh token
        orca_write = saved_keychain.get((pm.KEYCHAIN_ORCA_SERVICE, "acc-1"))
        assert orca_write is not None
        assert orca_write["claudeAiOauth"]["refreshToken"] == "new-rotated-refresh-token-888"


def test_balance_accounts_within_budget(mock_orca_data):
    usage_list = [
        {
            "id": "acc-1",
            "email": "primary@example.com",
            "isActive": True,
            "hasStoredCredentials": True,
            "isRateLimited": False,
            "fiveHourUtil": 25.0,
            "sevenDayUtil": 40.0
        },
        {
            "id": "acc-2",
            "email": "secondary@example.com",
            "isActive": False,
            "hasStoredCredentials": True,
            "isRateLimited": False,
            "fiveHourUtil": 10.0,
            "sevenDayUtil": 30.0
        }
    ]
    with patch.object(pm, "fetch_all_usage", return_value=usage_list):
        res = pm.balance_accounts(threshold=85.0, dry_run=True)
        assert res["action"] == "none"
        assert res["reason"] == "within_budget"


def test_balance_accounts_over_threshold_triggers_switch(mock_orca_data):
    usage_list = [
        {
            "id": "acc-1",
            "email": "primary@example.com",
            "isActive": True,
            "hasStoredCredentials": True,
            "isRateLimited": False,
            "fiveHourUtil": 92.0,
            "sevenDayUtil": 70.0
        },
        {
            "id": "acc-2",
            "email": "secondary@example.com",
            "isActive": False,
            "hasStoredCredentials": True,
            "isRateLimited": False,
            "fiveHourUtil": 15.0,
            "sevenDayUtil": 20.0
        }
    ]
    with patch.object(pm, "fetch_all_usage", return_value=usage_list), \
         patch.object(pm, "switch_account", return_value={"success": True}) as mock_switch:

        # Dry run
        dry_res = pm.balance_accounts(threshold=85.0, dry_run=True)
        assert dry_res["action"] == "would_switch"
        assert dry_res["fromAccount"] == "primary@example.com"
        assert dry_res["toAccount"] == "secondary@example.com"
        mock_switch.assert_not_called()

        # Real run
        real_res = pm.balance_accounts(threshold=85.0, dry_run=False)
        assert real_res["action"] == "switched"
        assert real_res["fromAccount"] == "primary@example.com"
        assert real_res["toAccount"] == "secondary@example.com"
        mock_switch.assert_called_once_with("acc-2")


def test_rotate_account_picks_lowest_utilization_standby(tmp_path, mock_orca_data, mock_claude_json):
    test_cache_file = str(tmp_path / "test-usage-cache.json")
    future_ms = int((time.time() + 3600) * 1000)
    fake_creds = {"claudeAiOauth": {"accessToken": "t", "expiresAt": future_ms}}

    # 3 accounts: acc-1 active, acc-2 at 80%, acc-3 at 10%
    three_accounts = [
        {"id": "acc-1", "email": "a1@example.com", "isActive": True, "hasStoredCredentials": True},
        {"id": "acc-2", "email": "a2@example.com", "isActive": False, "hasStoredCredentials": True},
        {"id": "acc-3", "email": "a3@example.com", "isActive": False, "hasStoredCredentials": True},
    ]
    usage_list = [
        {"id": "acc-1", "email": "a1@example.com", "isActive": True, "hasStoredCredentials": True, "isRateLimited": False, "fiveHourUtil": 99.0},
        {"id": "acc-2", "email": "a2@example.com", "isActive": False, "hasStoredCredentials": True, "isRateLimited": False, "fiveHourUtil": 80.0},
        {"id": "acc-3", "email": "a3@example.com", "isActive": False, "hasStoredCredentials": True, "isRateLimited": False, "fiveHourUtil": 10.0},
    ]

    with patch.object(pm, "USAGE_CACHE_PATH", test_cache_file), \
         patch.object(pm, "list_accounts", return_value=three_accounts), \
         patch.object(pm, "fetch_all_usage", return_value=usage_list), \
         patch.object(pm, "read_keychain_generic_password", return_value=fake_creds), \
         patch.object(pm, "switch_account", return_value={"success": True}) as mock_switch:

        res = pm.rotate_account(reason="rate_limit_429", dry_run=False)
        assert res["success"] is True
        assert res["rotatedTo"] == "a3@example.com"
        mock_switch.assert_called_once_with("acc-3")


def test_hook_post_tool_use_detects_rate_limit():
    import provider_manager_hook as pmh

    with patch.object(pm, "rotate_account", return_value={"success": True, "rotatedFrom": "a1", "rotatedTo": "a2"}) as mock_rotate:
        # Rate limit in error field
        payload = {"error": "Error: 429 Too Many Requests - rate_limit_error"}
        pmh.handle_post_tool_use(payload)
        mock_rotate.assert_called_once_with(reason="tool_rate_limit", dry_run=False)


