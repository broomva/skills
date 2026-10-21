"""Native profile generations preserve old sessions across same-account reauthorization."""
import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from conftest import IMPL_DIR
import pm_antigravity as ag

pytestmark = pytest.mark.new_only
EMAIL = "account@example.test"


def usage(email=EMAIL):
    return {"email": email, "status": "ok", "numbersAt": time.time(), "checkedAt": time.time(),
            "windows": [{"family": "gemini", "usedPercent": 10},
                        {"family": "third_party", "usedPercent": 20}]}


@pytest.fixture
def machine(tmp_path, monkeypatch):
    assert Path(ag.__file__).resolve().parent == IMPL_DIR
    monkeypatch.setenv("PROVIDER_MANAGER_ANTIGRAVITY_ROOT", str(tmp_path / "registry"))
    monkeypatch.setattr(ag, "runtime_fingerprint", Mock(return_value=ag.VERIFIED_RUNTIME))
    monkeypatch.setattr(ag, "validate_profile", Mock())
    monkeypatch.setattr(ag, "automatic_enabled", lambda: True)
    monkeypatch.setattr(ag.pm_antigravity_quota, "probe", Mock(side_effect=lambda profile, email: usage(email)))
    binary = tmp_path / "fake-official-acp"
    binary.write_text("#!/bin/sh\nexit 99\n")
    binary.chmod(0o700)

    def profile(name):
        p = tmp_path / name
        auth = p / "antigravity-acp/acp_token.json"
        auth.parent.mkdir(parents=True)
        auth.write_text(json.dumps({"client_id": "fake-client", "client_secret": "fake-client-secret",
                                    "refresh_token": "independent-fake-grant-" + name,
                                    "project_id": "fake-project"}))
        auth.chmod(0o600)
        return p
    return binary, profile


def register(binary, profile, email=EMAIL):
    return ag.register(email, str(profile), str(binary))


def token(profile):
    return profile / "antigravity-acp/acp_token.json"


def pin_or_error(key, **kwargs):
    # Mutations must fail the assertion about ownership, not merely crash in a lookup.
    try:
        return ag.pin_session(key, **kwargs)
    except ag.AntigravityError as exc:
        return {"error": str(exc)}


def test_reauthorization_publishes_new_generation_while_old_thread_retains_its_profile(machine):
    binary, profile = machine
    first, second = profile("first-native-home"), profile("second-native-home")
    originals = {token(p): token(p).read_bytes() for p in (first, second)}
    old = register(binary, first)
    initial = pin_or_error("existing-host-thread", model="gemini")
    new = register(binary, second)
    resumed = pin_or_error("existing-host-thread", model="gemini", require_existing=True)
    created = pin_or_error("new-host-thread", model="gemini")
    assert old.get("generation") and new.get("generation") != old["generation"]
    assert initial.get("profile") == resumed.get("profile") == str(first)
    assert resumed.get("generation") == old["generation"]
    assert created.get("profile") == str(second) and created.get("generation") == new["generation"]
    assert created.get("email") == resumed.get("email") == EMAIL
    with ag.registry() as state:
        assert state["accounts"][EMAIL]["generation"] == new["generation"]
        assert state["pins"]["existing-host-thread"] == old["generation"]
        assert state["pins"]["new-host-thread"] == new["generation"]
        assert set(state["generations"]) == {old["generation"], new["generation"]}
    assert {p: p.read_bytes() for p in originals} == originals
    assert not list(ag.root().rglob("acp_token.json")), "registration must not duplicate a native grant"


def test_registering_unchanged_profile_is_idempotent(machine):
    binary, profile = machine
    home = profile("same-native-home")
    first = register(binary, home)
    second = register(binary, home)
    assert first.get("generation") and second.get("generation") == first["generation"]
    with ag.registry() as state:
        assert list(state["generations"]) == [first["generation"]]


def test_reauthorization_cannot_replace_a_grant_inside_an_existing_profile(machine):
    binary, profile = machine
    home = profile("pinned-home")
    register(binary, home)
    ag.pin_session("existing")
    before = (ag.root() / "registry.json").read_bytes()
    data = json.loads(token(home).read_text())
    data["refresh_token"] = "changed-in-place-native-grant"
    token(home).write_text(json.dumps(data))
    with pytest.raises(ag.AntigravityError):
        register(binary, home)
    assert (ag.root() / "registry.json").read_bytes() == before
    assert pin_or_error("existing", require_existing=True).get("error"), "changed pinned profile must not resume"


def test_historical_profile_cannot_be_reassigned_to_another_email(machine):
    binary, profile = machine
    historical, latest = profile("historical"), profile("latest")
    register(binary, historical)
    ag.pin_session("old-owner")
    register(binary, latest)
    before = (ag.root() / "registry.json").read_bytes()
    with pytest.raises(ag.AntigravityError):
        register(binary, historical, "different@example.test")
    assert (ag.root() / "registry.json").read_bytes() == before
    assert pin_or_error("old-owner").get("profile") == str(historical)


def legacy_state(binary, profile):
    return {"version": 1, "accounts": {EMAIL: {
        "profile": str(profile), "binary": str(binary), "fingerprint": ag.fingerprint(profile),
        "runtimeFingerprint": list(ag.VERIFIED_RUNTIME), "usage": usage()}},
        "selected": dict.fromkeys(("all", "gemini", "third_party"), EMAIL),
        "pins": {"legacy-host-thread": EMAIL}, "lastSwitch": {"gemini": 123}}


def write_legacy(data):
    ag.root().mkdir(parents=True)
    path = ag.root() / "registry.json"
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path


def test_v1_migration_persists_exact_pin_owner_before_fresh_generation(machine, monkeypatch):
    binary, profile = machine
    old_home, new_home = profile("legacy-native"), profile("new-native")
    old_bytes = token(old_home).read_bytes()
    legacy = legacy_state(binary, old_home)
    path = write_legacy(legacy)
    replace = ag.os.replace
    publications = []
    def observe_replace(source, target):
        if Path(target) == path:
            publications.append(json.loads(Path(source).read_text()))
        return replace(source, target)
    monkeypatch.setattr(ag.os, "replace", observe_replace)
    with ag.registry() as migrated:
        version = migrated.get("version")
        generation = migrated.get("pins", {}).get("legacy-host-thread")
        owner = migrated.get("generations", {}).get(generation, {})
        assert version == 2 and owner.get("profile") == str(old_home) and owner.get("email") == EMAIL
        assert owner.get("generation") == generation
        assert migrated["selected"] == legacy["selected"] and migrated["lastSwitch"] == legacy["lastSwitch"]
    persisted = json.loads(path.read_text())
    assert persisted == publications[-1] and persisted["version"] == 2
    assert persisted["pins"]["legacy-host-thread"] == generation
    assert path.stat().st_mode & 0o777 == 0o600
    register(binary, new_home)
    assert pin_or_error("legacy-host-thread", require_existing=True).get("profile") == str(old_home)
    assert pin_or_error("fresh-host-thread").get("profile") == str(new_home)
    assert token(old_home).read_bytes() == old_bytes


def test_v1_generation_ids_are_deterministic_across_identical_migrations(machine):
    binary, profile = machine
    home = profile("legacy")
    legacy = legacy_state(binary, home)
    path = write_legacy(legacy)
    with ag.registry() as state:
        first = state.get("pins", {}).get("legacy-host-thread")
        assert first in state.get("generations", {})
    path.write_text(json.dumps(legacy))
    with ag.registry() as state:
        assert state["pins"]["legacy-host-thread"] == first


def test_v1_unknown_pin_owner_is_refused_without_rewriting_registry(machine):
    binary, profile = machine
    legacy = legacy_state(binary, profile("legacy"))
    legacy["pins"]["orphaned-thread"] = "missing@example.test"
    path = write_legacy(legacy)
    before = path.read_bytes()
    with pytest.raises(ag.AntigravityError):
        with ag.registry():
            pass
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["identity", "runtime", "profile_validation"])
def test_bad_new_generation_cannot_publish_or_move_old_pin(machine, monkeypatch, failure):
    binary, profile = machine
    original, candidate = profile("original"), profile("candidate")
    register(binary, original)
    ag.pin_session("preserved-thread")
    before = (ag.root() / "registry.json").read_bytes()
    if failure == "identity":
        monkeypatch.setattr(ag.pm_antigravity_quota, "probe", lambda *args: usage("wrong@example.test"))
    elif failure == "runtime":
        monkeypatch.setattr(ag, "runtime_fingerprint", lambda *args: ("unverified", "unverified"))
    else:
        monkeypatch.setattr(ag, "validate_profile", Mock(side_effect=ag.AntigravityError("invalid profile")))
    with pytest.raises(ag.AntigravityError):
        register(binary, candidate)
    assert (ag.root() / "registry.json").read_bytes() == before


def test_registering_retained_generation_does_not_roll_latest_back(machine):
    binary, profile = machine
    historical, latest = profile("retained"), profile("latest-native")
    old = register(binary, historical)
    ag.pin_session("old-session")
    new = register(binary, latest)
    again = register(binary, historical)
    assert again.get("generation") == old.get("generation")
    assert pin_or_error("future-session").get("generation") == new.get("generation")
    assert pin_or_error("old-session").get("generation") == old.get("generation")


def test_native_grant_cannot_be_registered_in_two_profiles(machine):
    binary, profile = machine
    first, duplicate = profile("original-grant"), profile("duplicate-grant")
    register(binary, first)
    token(duplicate).write_bytes(token(first).read_bytes())
    before = (ag.root() / "registry.json").read_bytes()
    with pytest.raises(ag.AntigravityError):
        register(binary, duplicate)
    assert (ag.root() / "registry.json").read_bytes() == before


def test_v1_migration_maps_each_legacy_thread_to_its_own_generation(machine):
    binary, profile = machine
    first, second = profile("legacy-first"), profile("legacy-second")
    legacy = legacy_state(binary, first)
    other_email = "other@example.test"
    legacy["accounts"][other_email] = {
        "profile": str(second), "binary": str(binary), "fingerprint": ag.fingerprint(second),
        "runtimeFingerprint": list(ag.VERIFIED_RUNTIME), "usage": usage(other_email)}
    legacy["pins"]["second-legacy-thread"] = other_email
    path = write_legacy(legacy)
    with ag.registry() as state:
        pins = state.get("pins", {})
        generations = state.get("generations", {})
        first_owner = generations.get(pins.get("legacy-host-thread"), {})
        second_owner = generations.get(pins.get("second-legacy-thread"), {})
        assert first_owner.get("profile") == str(first)
        assert second_owner.get("profile") == str(second) and second_owner.get("email") == other_email
        assert pins["legacy-host-thread"] != pins["second-legacy-thread"]
    persisted = json.loads(path.read_text())
    assert persisted["generations"][persisted["pins"]["second-legacy-thread"]]["profile"] == str(second)
