"""Auth — constant-time secret comparison + IP allowlist."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tradingview_bridge.auth import require_valid_secret, verify_secret

from .conftest import TEST_SECRET


def test_verify_secret_correct(paper_env: None) -> None:
    assert verify_secret(TEST_SECRET, TEST_SECRET) is True


def test_verify_secret_wrong(paper_env: None) -> None:
    assert verify_secret("wrong", TEST_SECRET) is False


def test_verify_secret_empty(paper_env: None) -> None:
    assert verify_secret("", TEST_SECRET) is False


def test_verify_secret_case_sensitive(paper_env: None) -> None:
    assert verify_secret(TEST_SECRET.upper(), TEST_SECRET) is False


def test_require_valid_secret_accepts(paper_env: None) -> None:
    """Should not raise."""
    require_valid_secret(TEST_SECRET)


def test_require_valid_secret_rejects(paper_env: None) -> None:
    with pytest.raises(HTTPException) as ei:
        require_valid_secret("bad-secret")
    assert ei.value.status_code == 401
    assert "secret" in ei.value.detail.lower()


def test_verify_secret_with_secretstr(paper_env: None) -> None:
    """Accepts SecretStr on either side without unwrapping at the call site."""
    from pydantic import SecretStr

    assert verify_secret(SecretStr(TEST_SECRET), SecretStr(TEST_SECRET)) is True
    assert verify_secret(SecretStr("nope"), SecretStr(TEST_SECRET)) is False
    assert verify_secret(SecretStr(TEST_SECRET), TEST_SECRET) is True
