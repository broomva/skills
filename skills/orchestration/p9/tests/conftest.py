"""Pytest configuration for skills/p9 tests.

Ensures `scripts/` is importable as `p9` regardless of how pytest is invoked,
and scrubs every session-identity marker from the ambient environment.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture(autouse=True)
def _hermetic_session_identity(monkeypatch):
    """Strip every session-identity marker before each test.

    ``current_session_id()`` derives from harness env vars (BRO-2373), so the
    suite is only hermetic if *all* of them are cleared — not just
    ``BROOMVA_P9_SESSION``. A test running under Claude Code or Orca otherwise
    inherits that harness's real session id and silently tests a different
    branch than it names.

    Autouse and centralized on purpose: this was missed once already. Adding a
    row to ``p9.SESSION_MARKERS`` without clearing it here makes the whole
    suite non-hermetic, so the list is read *from the module* rather than
    restated — a new marker is scrubbed the moment it is declared.
    """
    monkeypatch.delenv("BROOMVA_P9_SESSION", raising=False)
    import p9 as _p9
    for env_name, _prefix in _p9.SESSION_MARKERS:
        monkeypatch.delenv(env_name, raising=False)
