"""Auth — TradingView source-IP allowlist + constant-time shared-secret comparison.

TradingView does NOT natively HMAC-sign webhook payloads. The standard auth
pattern is: include the secret as a field in the Pine Script alert message
body and verify on the server. We pair this with an IP allowlist as
defense-in-depth.

This module provides FastAPI dependency callables — they raise HTTPException
on failure so the framework converts them to clean HTTP responses.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status
from pydantic import SecretStr

from .settings import Settings, get_settings


def source_ip(request: Request, settings: Settings | None = None) -> str:
    """Return the source IP, honoring X-Forwarded-For if trust_forwarded_for=True.

    When trust_forwarded_for is False (default), we use the direct peer address.
    When True (e.g., behind Cloudflare Tunnel), we take the first IP in
    X-Forwarded-For. The 'first' rule is correct because TradingView is the
    original client; subsequent IPs are intermediaries.
    """
    s = settings or get_settings()
    if s.trust_forwarded_for:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = request.client
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unable to determine source IP",
        )
    return client.host


def verify_source_ip(request: Request) -> None:
    """FastAPI dependency — 403 if source IP not in allowlist."""
    s = get_settings()
    ip = source_ip(request, s)
    if ip not in s.tv_allowed_ips:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Source IP {ip!r} not in TradingView allowlist",
        )


def verify_secret(provided: SecretStr | str, expected: SecretStr | str) -> bool:
    """Constant-time secret comparison.

    Uses hmac.compare_digest to prevent timing side-channel attacks. Even though
    the shared secret isn't HMAC-signed, the comparison primitive is still the
    right one for any sensitive string equality check.

    Accepts SecretStr or plain str on both sides for ergonomics in tests.
    """
    a = provided.get_secret_value() if isinstance(provided, SecretStr) else provided
    b = expected.get_secret_value() if isinstance(expected, SecretStr) else expected
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_valid_secret(provided: SecretStr | str) -> None:
    """Raise 401 if the provided secret doesn't match settings.tv_webhook_secret.

    Not a FastAPI dependency — called from the webhook handler after the body
    is parsed (because the secret arrives inside the body, not in a header).
    """
    s = get_settings()
    if not verify_secret(provided, s.tv_webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid shared secret",
        )
