"""MFA provider adapters.

Three implementations:

- `PromptMFAProvider`  — interactive `input()` prompt; the human-in-loop default.
- `EnvMFAProvider`     — read once from `$BROOMVA_HEALTH_MFA_CODE`; used in CI
                          where the user typed it in advance.
- `StaticMFAProvider`  — fixed-value provider for tests.
"""

from __future__ import annotations

import os

from broomva_health.domain.errors import MFANeeded

__all__ = ["EnvMFAProvider", "PromptMFAProvider", "StaticMFAProvider"]


class PromptMFAProvider:
    """Read an MFA code from the terminal via `input()`.

    Never log the code. The user typed it; we hand it to the source library
    and forget it.
    """

    def prompt(self, source: str) -> str:
        return input(f"[{source}] MFA code: ").strip()


class EnvMFAProvider:
    """Read the MFA code from an environment variable.

    Raises `MFANeeded` if the variable is absent or empty so the CLI can map
    that to a deterministic exit code.
    """

    def __init__(self, env_var: str = "BROOMVA_HEALTH_MFA_CODE") -> None:
        self._env_var = env_var

    def prompt(self, source: str) -> str:
        value = os.environ.get(self._env_var, "").strip()
        if not value:
            raise MFANeeded(
                f"MFA required for {source!r} but {self._env_var} is not set",
                source=source,
                env_var=self._env_var,
            )
        return value


class StaticMFAProvider:
    """Fixed-value MFA provider. **Tests only.**"""

    def __init__(self, code: str) -> None:
        self._code = code

    def prompt(self, source: str) -> str:  # noqa: ARG002 — interface conformity
        return self._code
