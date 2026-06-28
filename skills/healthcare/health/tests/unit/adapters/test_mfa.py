"""Tests for MFA adapters (EnvMFAProvider, StaticMFAProvider).

PromptMFAProvider is skipped — it requires a TTY for `input()`.
"""

from __future__ import annotations

import pytest

from broomva_health.adapters.mfa.prompt import (
    EnvMFAProvider,
    StaticMFAProvider,
)
from broomva_health.domain.errors import MFANeeded


def test_static_mfa_returns_code() -> None:
    provider = StaticMFAProvider("123456")
    assert provider.prompt("garmin") == "123456"


def test_static_mfa_ignores_source() -> None:
    provider = StaticMFAProvider("000000")
    assert provider.prompt("garmin") == "000000"
    assert provider.prompt("whoop") == "000000"


def test_env_mfa_reads_default_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROOMVA_HEALTH_MFA_CODE", "999000")
    provider = EnvMFAProvider()
    assert provider.prompt("garmin") == "999000"


def test_env_mfa_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROOMVA_HEALTH_MFA_CODE", "  123456  \n")
    provider = EnvMFAProvider()
    assert provider.prompt("garmin") == "123456"


def test_env_mfa_raises_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BROOMVA_HEALTH_MFA_CODE", raising=False)
    provider = EnvMFAProvider()
    with pytest.raises(MFANeeded) as exc_info:
        provider.prompt("garmin")
    assert "BROOMVA_HEALTH_MFA_CODE" in str(exc_info.value)


def test_env_mfa_raises_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROOMVA_HEALTH_MFA_CODE", "   ")
    provider = EnvMFAProvider()
    with pytest.raises(MFANeeded):
        provider.prompt("garmin")


def test_env_mfa_custom_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_MFA", "abc")
    provider = EnvMFAProvider(env_var="MY_MFA")
    assert provider.prompt("garmin") == "abc"
