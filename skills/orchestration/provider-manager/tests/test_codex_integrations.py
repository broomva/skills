import copy
import json

import pytest

import pm_codex_integrations as integrations
import pm_store

pytestmark = pytest.mark.new_only


@pytest.fixture
def launcher(tmp_path):
    path = tmp_path / "codex-account"
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o700)
    return str(path)


def test_paseo_preserves_config_and_input(launcher):
    original = {"daemon": {"listen": "127.0.0.1:6767"}, "agents": {"providers": {
        "claude": {"enabled": True}, "codex": {"env": {"OTHER": "value"}, "enabled": True}}}}
    before = copy.deepcopy(original)
    candidate = integrations.paseo_config(original, launcher)
    assert original == before
    expected = copy.deepcopy(before)
    expected["agents"]["providers"]["codex"]["command"] = [launcher]
    assert candidate == expected
    assert integrations.paseo_config(candidate, launcher) == candidate


@pytest.mark.parametrize("config", [[], {"agents": []}, {"agents": {"providers": []}},
    {"agents": {"providers": {"codex": []}}},
    {"agents": {"providers": {"codex": {"command": ["custom", "--required"]}}}},
    {"agents": {"providers": {"codex": {"env": {"CODEX_HOME": "/pinned"}}}}},
    {"agents": {"providers": {"codex": {"env": []}}}},
    {"agents": {"providers": {"codex": {"extends": "acp"}}}}])
def test_paseo_fails_closed(config, launcher):
    before = copy.deepcopy(config)
    with pytest.raises(pm_store.StoreError):
        integrations.paseo_config(config, launcher)
    assert config == before


def test_reject_missing_or_relative_launcher(tmp_path):
    for path in ("codex", str(tmp_path / "missing")):
        with pytest.raises(pm_store.StoreError):
            integrations.paseo_config({}, path)


def test_t3_generation_ids_do_not_follow_selection_or_retarget(monkeypatch, tmp_path, launcher):
    first = tmp_path / "generation-a"
    second = tmp_path / "generation-b"
    first.mkdir()
    second.mkdir()
    registry = {"accounts": {"account@example.test": {
        "id": "same-workspace", "email": "account@example.test", "home": str(first)}},
        "selected": "account@example.test"}
    monkeypatch.setattr(integrations.pm_codex_homes, "registry", lambda: registry)
    request = integrations.t3_requests(launcher)[0]
    mutation = request["payload"]["providerInstanceMutation"]
    assert mutation["operation"] == "create"
    assert mutation["instanceId"] != "codex"
    assert mutation["instance"]["config"]["homePath"] == str(first)
    registry["selected"] = None
    assert integrations.t3_requests(launcher)[0] == request
    registry["accounts"]["account@example.test"]["home"] = str(second)
    assert integrations.t3_requests(launcher)[0]["payload"]["providerInstanceMutation"]["instanceId"] != mutation["instanceId"]
    assert request["payload"]["patch"] == {}
    assert "auth.json" not in json.dumps(request)


def test_t3_rejects_missing_home(monkeypatch, tmp_path, launcher):
    monkeypatch.setattr(integrations.pm_codex_homes, "registry", lambda: {
        "accounts": {"a@example.test": {"home": str(tmp_path / "missing")}}})
    with pytest.raises(pm_store.StoreError):
        integrations.t3_requests(launcher)
