"""MFA provider port — adapters call this when a source demands a step-up code."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["MFAProvider"]


@runtime_checkable
class MFAProvider(Protocol):
    """Supply a one-time MFA code on demand.

    Implementations:
    - `PromptMFAProvider`     — interactive terminal prompt
    - `EnvMFAProvider`        — read once from `$BROOMVA_HEALTH_MFA_CODE` (CI / e2e)
    - `KeychainMFAProvider`   — read a TOTP secret from Keychain and generate locally
    """

    def prompt(self, source: str) -> str: ...
