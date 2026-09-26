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
