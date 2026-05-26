"""Tests for domain/errors.py."""

from __future__ import annotations

from broomva_health.domain.errors import (
    AuthRequired,
    HealthError,
    MFANeeded,
    RateLimited,
)


def test_health_error_default_code() -> None:
    err = HealthError("kaboom", source="garmin")
    assert err.code == "health_error"
    assert err.exit_code == 1
    assert err.context["source"] == "garmin"


def test_auth_required_exit_code_matches_eddmann_convention() -> None:
    err = AuthRequired("re-login needed")
    assert err.exit_code == 2
    assert err.code == "auth_required"


def test_mfa_needed_is_subclass_of_health_error() -> None:
    assert issubclass(MFANeeded, HealthError)
    assert MFANeeded("").exit_code == 2


def test_rate_limited_carries_retry_after() -> None:
    err = RateLimited("backoff", retry_after_s=900)
    assert err.retry_after_s == 900
    assert err.context["retry_after_s"] == 900


def test_health_error_repr_has_context() -> None:
    err = HealthError("boom", source="garmin", profile="default")
    rep = repr(err)
    assert "source='garmin'" in rep
    assert "profile='default'" in rep
