"""Tests for `health doctor` self-diagnostic checks.

Focus: `_check_install` — the freshness/RC1 guard (BRO-1552/1553) that flags an
editable install pinned to an ephemeral temp dir before the reboot that clears
it breaks every `health` call.
"""

from __future__ import annotations

import broomva_health
from broomva_health.cli.doctor import _check_install


def test_check_install_ok_for_stable_path(monkeypatch):
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(
        broomva_health,
        "__file__",
        "/Users/x/.local/share/broomva-health/pkg/src/broomva_health/__init__.py",
    )
    checks = _check_install()
    assert len(checks) == 1
    assert checks[0].name == "install.source"
    assert checks[0].status == "OK"


def test_check_install_fails_for_tmp_path(monkeypatch):
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(
        broomva_health,
        "__file__",
        "/tmp/broomva-skills-src.abc123/skills/health/src/broomva_health/__init__.py",
    )
    checks = _check_install()
    assert checks[0].status == "FAIL"
    assert "ephemeral" in checks[0].detail.lower()


def test_check_install_fails_for_custom_tmpdir(monkeypatch):
    # A $TMPDIR *outside* the hardcoded prefixes must still be caught — this
    # exercises the TMPDIR branch specifically (not the static prefix list).
    monkeypatch.setenv("TMPDIR", "/scratch/ci-tmp")
    monkeypatch.setattr(
        broomva_health,
        "__file__",
        "/scratch/ci-tmp/clone/src/broomva_health/__init__.py",
    )
    checks = _check_install()
    assert checks[0].status == "FAIL"
