"""Per-account homes pin a process to its grant while selection affects new sessions only.

All credentials are CodexWorld fakes. The subprocess test runs two tiny fake CLIs, never Codex.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import pm_codex_homes as homes
import pm_store
import provider_manager as pm
from test_codex_balancer import CodexWorld, DEV, DEV_ID, CARLOS, CARLOS_ID

pytestmark = pytest.mark.new_only


@pytest.fixture
def cx(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVIDER_MANAGER_CODEX_ROOT", str(tmp_path / "managed-codex"))
    return CodexWorld(monkeypatch)


def _register(cx, email, account_id, token, *, select=False, ttl=3600):
    auth = {"auth_mode": "chatgpt", "tokens": cx.tokens(email, token, ttl=ttl)}
    home = homes.new_home(email, auth, cx.auth.parent)
    homes.register(email, account_id, home, select=select)
    return home


def _token(home):
    return json.loads((home / "auth.json").read_text())["tokens"]["refresh_token"]


def test_selecting_an_account_changes_only_metadata_and_preserves_both_grants(cx):
    dev = _register(cx, DEV, DEV_ID, "rt-dev-1", select=True)
    carlos = _register(cx, CARLOS, CARLOS_ID, "rt-carlos-1")
    before = {p: (p / "auth.json").read_bytes() for p in (dev, carlos)}
    res = pm.switch_codex_account(CARLOS)
    assert res["active"] == CARLOS and homes.selected()["home"] == str(carlos)
    pm.switch_codex_account(DEV)
    assert homes.selected()["home"] == str(dev)
    assert {p: (p / "auth.json").read_bytes() for p in before} == before
    assert cx.refreshed == [] and cx.revoked == set()
    assert not cx.auth.exists(), "selection must not create or rewrite legacy auth.json"


def test_legacy_home_is_adopted_in_place_without_a_duplicate_grant(cx):
    cx.login(DEV, "rt-dev-live")
    original = cx.auth.read_bytes()
    pm._adopt_legacy_codex_home()
    pm._adopt_legacy_codex_home()
    assert homes.entry(DEV)["home"] == str(cx.auth.parent.resolve())
    assert homes.selected()["email"] == DEV
    assert cx.auth.read_bytes() == original
    assert not (homes.root() / "homes").exists(), "adoption must not clone a running refresh grant"
    assert cx.refreshed == []


def test_active_reauthorization_publishes_new_generation_and_keeps_old_auth(cx, monkeypatch):
    import pm_codex_login
    old = _register(cx, DEV, DEV_ID, "rt-dev-old", select=True)
    old_auth = (old / "auth.json").read_bytes()
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login", cx.fake_login("rt-dev-new"))
    result = pm.login_codex_headless(DEV)
    new = Path(homes.selected()["home"])
    assert result["activated"] is True and result["active"] == DEV
    assert new != old and _token(new) == "rt-dev-new"
    assert (old / "auth.json").read_bytes() == old_auth
    assert not cx.revoked, "reauthorization must start in an empty home"


def test_off_roster_login_remains_selectable_after_selection_changes(cx, monkeypatch):
    import pm_codex_login
    unknown = "personal@example.test"
    _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login", cx.fake_login("rt-personal-new"))
    result = pm.login_codex_headless(unknown)
    personal = homes.entry(unknown)
    assert result["activated"] is False and homes.selected()["email"] == DEV
    assert any(a["email"] == unknown for a in pm.codex_roster())
    assert pm.switch_codex_account(personal["id"])["active"] == unknown
    pm.switch_codex_account(DEV)
    assert pm.switch_codex_account(unknown)["active"] == unknown
    assert _token(Path(personal["home"])) == "rt-personal-new"


def test_manager_never_spends_a_managed_standbys_refresh_grant(cx):
    _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    standby = _register(cx, CARLOS, CARLOS_ID, "rt-carlos-expired", ttl=-1)
    original = (standby / "auth.json").read_bytes()
    tokens = json.loads(original)["tokens"]
    assert pm._refresh_codex_copy(CARLOS_ID, CARLOS, tokens) == (None, "managed_home_owns_refresh")
    pm.fetch_codex_usage(force=True)
    pm.switch_codex_account(CARLOS)
    assert cx.refreshed == []
    assert (standby / "auth.json").read_bytes() == original


def test_launcher_exec_pins_concrete_home_and_file_store(cx, monkeypatch, tmp_path):
    chosen = _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    binary = tmp_path / "fake-codex"
    binary.write_text("#!/bin/sh\nexit 0\n")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "unrelated-home"))
    seen = {}
    monkeypatch.setattr(homes.os, "execve", lambda binary, argv, env: seen.update(binary=binary, argv=argv, env=env))
    homes.launch(str(binary), ["exec", "hello"])
    assert seen["binary"] == str(binary.resolve())
    assert seen["env"]["CODEX_HOME"] == str(chosen.resolve())
    assert seen["argv"][1:3] == ["-c", 'cli_auth_credentials_store="file"']


def test_launcher_refuses_login_into_a_pinned_generation(cx, monkeypatch, tmp_path):
    _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    monkeypatch.setattr(homes.os, "execve", lambda *a: pytest.fail("must not exec login"))
    with pytest.raises(pm_store.StoreError, match="login-headless"):
        homes.launch(str(tmp_path / "unused"), ["login"])


def test_two_running_fake_sessions_keep_their_home_when_selection_switches(cx, tmp_path):
    dev = _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    carlos = _register(cx, CARLOS, CARLOS_ID, "rt-carlos-live")
    binary = tmp_path / "fake-codex"
    binary.write_text("#!" + sys.executable + "\n" + '''import json, os, sys
from pathlib import Path
home = Path(os.environ["CODEX_HOME"])
print(str(home), flush=True)
suffix = sys.stdin.readline().strip()
auth = home / "auth.json"
data = json.loads(auth.read_text())
data["tokens"]["refresh_token"] += suffix
auth.write_text(json.dumps(data))
''')
    binary.chmod(0o755)
    launcher = Path(homes.__file__).resolve()
    processes = []
    try:
        first = subprocess.Popen([sys.executable, str(launcher), "--binary", str(binary)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, env=dict(os.environ))
        processes.append(first)
        assert first.stdout.readline().strip() == str(dev)
        pm.switch_codex_account(CARLOS)
        second = subprocess.Popen([sys.executable, str(launcher), "--binary", str(binary)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=dict(os.environ))
        processes.append(second)
        assert second.stdout.readline().strip() == str(carlos)
        # A late refresh in the old session finishes after the selection changed.
        for process in processes:
            _, err = process.communicate("-rotated\n", timeout=10)
            assert process.returncode == 0, err
        assert _token(dev) == "rt-dev-live-rotated"
        assert _token(carlos) == "rt-carlos-live-rotated"
        assert homes.selected()["home"] == str(carlos)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)


def test_paseo_agent_id_retains_generation_across_selection_and_reauthorization(cx, monkeypatch, tmp_path):
    old = _register(cx, DEV, DEV_ID, "rt-dev-old", select=True)
    carlos = _register(cx, CARLOS, CARLOS_ID, "rt-carlos-live")
    binary = tmp_path / "fake-codex"
    binary.write_text("#!/bin/sh\nexit 0\n")
    launched = []
    monkeypatch.setattr(homes.os, "execve", lambda binary, argv, env: launched.append(env["CODEX_HOME"]))
    monkeypatch.setenv("PASEO_AGENT_ID", "existing-paseo-agent")
    homes.launch(str(binary), ["exec", "hello"])
    homes.select(CARLOS)
    homes.launch(str(binary), ["exec", "resume"])
    # Reauthorization replaces the registry entry, while the existing agent owns the old generation.
    new = _register(cx, DEV, DEV_ID, "rt-dev-new", select=True)
    homes.launch(str(binary), ["exec", "resume"])
    monkeypatch.setenv("PASEO_AGENT_ID", "new-paseo-agent")
    homes.launch(str(binary), ["exec", "hello"])
    monkeypatch.delenv("PASEO_AGENT_ID")
    homes.select(CARLOS)
    homes.launch(str(binary), ["exec", "hello"])
    assert launched == [str(old), str(old), str(old), str(new), str(carlos)]


@pytest.mark.parametrize("args", [["logout"], ["-c", "model=example", "login"],
                                  ["exec", "hello", "-c", 'cli_auth_credentials_store="keyring"']])
def test_launcher_rejects_auth_mutation_or_keyring_override(cx, monkeypatch, tmp_path, args):
    _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    binary = tmp_path / "fake-codex"
    binary.write_text("#!/bin/sh\nexit 0\n")
    monkeypatch.setattr(homes.os, "execve", lambda *a: pytest.fail("unsafe command must not exec"))
    with pytest.raises(pm_store.StoreError):
        homes.launch(str(binary), args)


@pytest.mark.parametrize("prefix", [["--enable", "goals"], ["-p", "work"], ["--model=x"], ["-pwork"]])
@pytest.mark.parametrize("command", ["login", "logout"])
def test_global_option_values_cannot_bypass_auth_guard(cx, monkeypatch, prefix, command):
    _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    monkeypatch.setattr(homes.os, "execve", lambda *a: pytest.fail("unsafe command was executed"))
    with pytest.raises(pm_store.StoreError, match="login-headless"):
        homes.launch(sys.executable, prefix + [command])


def test_read_only_login_status_and_literal_config_prompt_are_allowed(cx, monkeypatch):
    _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    calls = []
    monkeypatch.setattr(homes.os, "execve", lambda *args: calls.append(args))
    homes.launch(sys.executable, ["--enable", "goals", "login", "status"])
    homes.launch(sys.executable, ["exec", "Explain cli_auth_credentials_store"])
    assert len(calls) == 2


def test_app_server_after_global_option_values_still_uses_proxy(cx, monkeypatch):
    import pm_codex_proxy
    chosen = _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    seen = []
    monkeypatch.setattr(pm_codex_proxy, "run", lambda *args: seen.append(args) or 0)
    monkeypatch.setattr(homes.os, "execve", lambda *args: pytest.fail("proxy bypassed"))
    with pytest.raises(SystemExit) as result:
        homes.launch(sys.executable, ["--enable", "goals", "app-server"])
    assert result.value.code == 0 and seen[0][2] == chosen


def test_missing_registry_with_retained_homes_cannot_spend_backup_grants(cx):
    _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    old = _register(cx, CARLOS, CARLOS_ID, "rt-carlos-live")
    (homes.root() / "accounts.json").unlink()
    with pytest.raises(pm_store.StoreError, match="registry is missing"):
        pm._refresh_codex_copy(CARLOS_ID, CARLOS, json.loads((old / "auth.json").read_text())["tokens"])
    assert cx.refreshed == []


def test_confirmed_revoked_generation_can_be_repaired_without_copying_its_new_grant(cx, monkeypatch):
    import pm_codex_login
    home = _register(cx, DEV, DEV_ID, "rt-dev-revoked", select=True)
    (home / "sessions").mkdir()
    (home / "sessions/fixture").write_text("retained conversation")
    cx.revoked.add("rt-dev-revoked")
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login", cx.fake_login("rt-dev-repaired"))
    before = set((homes.root() / "homes").iterdir())
    result = pm.login_codex_headless(DEV, repair_home=str(home))
    assert result["repairedHome"] == str(home)
    assert _token(home) == "rt-dev-repaired"
    assert homes.selected()["home"] == str(home)
    assert set((homes.root() / "homes").iterdir()) == before, "the fresh grant must have exactly one home"
    assert (home / "sessions/fixture").read_text() == "retained conversation"
    assert cx.refreshed == [], "repair never spends the old refresh grant"


def test_repair_refuses_a_live_or_merely_expired_generation(cx, monkeypatch):
    import pm_codex_login
    home = _register(cx, DEV, DEV_ID, "rt-dev-live", select=True)
    before = (home / "auth.json").read_bytes()
    calls = []
    monkeypatch.setattr(pm_codex_login, "run_codex_autonomous_login", cx.fake_login("rt-dev-new", calls=calls))
    with pytest.raises(pm_store.StoreError, match="not confirmed"):
        pm.login_codex_headless(DEV, repair_home=str(home))
    assert (home / "auth.json").read_bytes() == before
    assert calls == [], "must prove revocation before login"
