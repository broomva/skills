"""Shared fixtures. Every test runs hermetically: no test can reach the login keychain, the real
`claude`, or the network.

- PATH starts with a guard dir whose `security`, `claude` and `node` refuse (exit 99), unless the
  test builds a `world`, whose fakes replace them.
- HOME and every module path constant point into tmp.
- urllib is blocked unless a `world` routes it to the Anthropic stub.

PM_IMPL_DIR=<dir> runs the suite against another copy of the scripts, for example origin/main's.
The kill-path tests are meant to FAIL there; tests marked `new_only` are skipped (unless
PM_IMPL_IS_NEW=1, which tests/mutation_check.py sets for its mutated copies).
"""

import os
import sys
import urllib.request
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
IMPL_DIR = Path(os.environ.get("PM_IMPL_DIR") or SCRIPTS_DIR).resolve()
# PM_IMPL_IS_NEW=1: the other copy is this branch's code (mutation runs), so run new-only tests too.
OLD_IMPL = IMPL_DIR != SCRIPTS_DIR.resolve() and not os.environ.get("PM_IMPL_IS_NEW")

sys.path.insert(0, str(TESTS_DIR / "fakeworld"))
sys.path.insert(0, str(IMPL_DIR))

import fake_net  # noqa: E402
import provider_manager as pm  # noqa: E402
from world import World, default_paths  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "new_only: behaviour that only the fixed implementation has")


def pytest_collection_modifyitems(config, items):
    if not OLD_IMPL:
        return
    skip = pytest.mark.skip(reason="PM_IMPL_DIR set: new-only test")
    for item in items:
        if "new_only" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    guard_bin = tmp_path / "guard-bin"
    guard_bin.mkdir()
    for name in ("security", "claude", "node"):
        p = guard_bin / name
        p.write_text("#!/bin/sh\necho 'test guard: %s refused' >&2\nexit 99\n" % name)
        p.chmod(0o755)
    home = tmp_path / "guard-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USER", "guard")
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % guard_bin)
    monkeypatch.setenv("PROVIDER_MANAGER_TEST_GUARD", "1")
    monkeypatch.setenv("PYTHONPATH", str(TESTS_DIR / "fakeworld"))
    for k in ("FAKE_SECURITY_DB", "FAKE_ANTHROPIC_STATE", "CLAUDE_CONFIG_DIR",
              "CLAUDE_SECURESTORAGE_CONFIG_DIR", "PROVIDER_MANAGER_INLINE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", fake_net.blocked_urlopen)
    for name, value in default_paths(home).items():
        if hasattr(pm, name):
            monkeypatch.setattr(pm, name, value)
    yield


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path / "w", monkeypatch, pm)


@pytest.fixture
def pmh():
    import provider_manager_hook

    return provider_manager_hook
