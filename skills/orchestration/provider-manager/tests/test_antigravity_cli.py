"""Real CLI dispatch exercised with fake providers and isolated routing metadata only."""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from conftest import IMPL_DIR
import pm_antigravity as ag
import pm_cli
import pm_grok

pytestmark = pytest.mark.new_only


@pytest.fixture
def providers():
    # The CLI accepts its Claude/Codex backend explicitly. No keychain or process probes run.
    return SimpleNamespace(
        StoreError=RuntimeError,
        list_accounts=Mock(return_value=[]), list_codex_accounts=Mock(return_value=[]),
        get_claude_auth_status=Mock(return_value={"loggedIn": False}),
        get_codex_auth_status=Mock(return_value={"loggedIn": False}),
        fetch_all_usage=Mock(return_value=[]), fetch_codex_usage=Mock(return_value=[]),
        balance_accounts=Mock(return_value={"action": "hold", "reason": "fake"}),
        evaluate_codex_balance=Mock(return_value={"action": "hold", "reason": "fake"}),
        run_auto_until_settled=Mock(return_value={"claude": {"action": "hold"}, "codex": {"action": "hold"}}),
        gate_status=Mock(return_value=None),
    )


def run_cli(monkeypatch, providers, args):
    # Mutation runs must execute the scratch implementation, not an imported working-tree copy.
    assert Path(pm_cli.__file__).resolve().parent == IMPL_DIR
    assert Path(ag.__file__).resolve().parent == IMPL_DIR
    monkeypatch.setattr(sys, "argv", ["provider-manager", *args])
    pm_cli.main(providers)


@pytest.mark.parametrize("command", ["list", "status", "usage", "balance"])
@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
def test_all_includes_antigravity_in_text_and_json(monkeypatch, providers, capsys, command, as_json):
    accounts = Mock(return_value=[{"email": "test-account@example.test"}])
    balance = Mock(return_value={"action": "hold", "reason": "fake-antigravity"})
    monkeypatch.setattr(ag, "accounts", accounts)
    monkeypatch.setattr(ag, "balance", balance)
    monkeypatch.setattr(pm_grok, "accounts", Mock(return_value=[{"email": "grok-account@example.test"}]))
    monkeypatch.setattr(pm_grok, "usage", Mock(return_value=[]))
    options = [command, "--provider", "all"] + (["--json"] if as_json else [])
    if command == "usage":
        options += ["--force"]
    run_cli(monkeypatch, providers, options)
    output = capsys.readouterr().out
    if command == "balance":
        balance.assert_called_once_with(dry_run=False)
        providers.balance_accounts.assert_called_once()
        providers.evaluate_codex_balance.assert_called_once()
    else:
        expected = {} if command == "list" else {"refresh": True}
        if command == "usage":
            expected["force"] = True
        accounts.assert_called_once_with(**expected)
    if as_json:
        parsed = json.loads(output)
        assert set(parsed) == {"claude", "codex", "antigravity"} | ({"grok"} if command != "balance" else set())
        assert parsed["antigravity"] == (balance.return_value if command == "balance" else accounts.return_value)
    else:
        assert "[Antigravity]" in output
        assert ("fake-antigravity" if command == "balance" else "test-account@example.test") in output


@pytest.mark.parametrize("as_json", [False, True])
def test_all_auto_calls_antigravity_and_preserves_dry_run(monkeypatch, providers, capsys, as_json):
    balance = Mock(return_value={"action": "would_switch", "target": "fake"})
    monkeypatch.setattr(ag, "balance", balance)
    run_cli(monkeypatch, providers,
            ["balance", "--provider", "all", "--auto", "--dry-run"] + (["--json"] if as_json else []))
    balance.assert_called_once_with(dry_run=True, automatic=True)
    providers.run_auto_until_settled.assert_called_once_with(reason="hook", signal=None, provider="all")
    out = capsys.readouterr().out
    assert json.loads(out)["antigravity"]["action"] == "would_switch" if as_json else "[Antigravity]" in out


@pytest.fixture
def routing(monkeypatch, tmp_path):
    monkeypatch.setenv("PROVIDER_MANAGER_ANTIGRAVITY_ROOT", str(tmp_path / "routing"))
    monkeypatch.setattr(ag, "_refresh", lambda *a, **kw: None)
    config = Path.home() / ".config/broomva/provider-manager.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"autoBalance": False}))
    with ag.registry() as state:
        for email, used in (("first@example.test", 95), ("second@example.test", 10)):
            profile = str(tmp_path / email)
            stamp = "synthetic-%s" % email
            identity = ag.generation_id(email, profile, stamp)
            entry = {"email": email, "generation": identity, "profile": profile,
                "fingerprint": stamp, "binary": "/synthetic/agent", "usage": {
                "status": "ok", "numbersAt": time.time(), "windows": [
                    {"family": "gemini", "usedPercent": used},
                    {"family": "third_party", "usedPercent": used}]}}
            state["accounts"][email] = entry
            state["generations"][identity] = entry
        state["selected"] = dict.fromkeys(("all", "gemini", "third_party"), "first@example.test")
    return config


def test_cli_auto_honors_disabled_config(monkeypatch, providers, capsys, routing):
    run_cli(monkeypatch, providers, ["balance", "--provider", "antigravity", "--auto", "--json"])
    assert json.loads(capsys.readouterr().out)["action"] == "would_switch"
    with ag.registry() as state:
        assert state["selected"]["all"] == "first@example.test" and not state["lastSwitch"]


def test_cli_manual_dry_run_preserves_selection(monkeypatch, providers, capsys, routing):
    routing.write_text(json.dumps({"autoBalance": True}))
    run_cli(monkeypatch, providers, ["balance", "--provider", "antigravity", "--dry-run", "--json"])
    assert json.loads(capsys.readouterr().out)["action"] == "would_switch"
    with ag.registry() as state:
        assert state["selected"]["all"] == "first@example.test" and not state["lastSwitch"]


@pytest.mark.parametrize("as_json", [False, True])
def test_antigravity_module_error_exits_one_without_traceback(monkeypatch, providers, capsys, as_json):
    monkeypatch.setattr(ag, "accounts", Mock(side_effect=ag.AntigravityError("Profile unavailable")))
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, providers,
                ["list", "--provider", "antigravity"] + (["--json"] if as_json else []))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    if as_json:
        assert json.loads(captured.out) == {"success": False, "error": "Profile unavailable"}
        assert captured.err == ""
    else:
        assert captured.err == "Error: Profile unavailable\n" and captured.out == ""
    assert "Traceback" not in captured.out + captured.err


def test_register_and_launcher_commands_dispatch_without_provider_flag(monkeypatch, providers, capsys):
    register = Mock(return_value={"status": "registered"})
    launcher = Mock(return_value={"launcher": "/fake/launcher"})
    monkeypatch.setattr(ag, "register", register)
    monkeypatch.setattr(ag, "install_launcher", launcher)
    run_cli(monkeypatch, providers, ["antigravity-register", "--email", "test@example.test",
                                  "--profile", "/fake/profile", "--binary", "/fake/agent"])
    register.assert_called_once_with("test@example.test", "/fake/profile", "/fake/agent")
    assert json.loads(capsys.readouterr().out)["status"] == "registered"
    run_cli(monkeypatch, providers, ["antigravity-launcher"])
    launcher.assert_called_once_with()
    assert json.loads(capsys.readouterr().out)["launcher"] == "/fake/launcher"


@pytest.mark.parametrize("model", ["gemini-4-argon-medium", "claude-opus-5-5"])
@pytest.mark.parametrize("command", ["balance", "switch"])
def test_antigravity_model_family_reaches_backend(monkeypatch, providers, capsys, model, command):
    operation = Mock(return_value={"action": "hold"})
    monkeypatch.setattr(ag, command, operation)
    options = [command, "--provider", "antigravity", "--model", model, "--json"]
    if command == "switch":
        options.append("test@example.test")
    run_cli(monkeypatch, providers, options)
    if command == "switch":
        operation.assert_called_once_with("test@example.test", model=model)
    else:
        operation.assert_called_once_with(dry_run=False, automatic=False, model=model)
    assert json.loads(capsys.readouterr().out)["action"] == "hold"


@pytest.mark.parametrize("automatic", [False, True])
def test_aggregate_model_routes_only_to_antigravity(monkeypatch, providers, capsys, automatic):
    balance = Mock(return_value={"action": "would_switch"})
    monkeypatch.setattr(ag, "balance", balance)
    options = ["balance", "--provider", "all", "--model", "gemini-4-argon-medium", "--dry-run", "--json"]
    if automatic:
        options.append("--auto")
    run_cli(monkeypatch, providers, options)
    expected = {"dry_run": True, "model": "gemini-4-argon-medium"}
    if automatic:
        expected["automatic"] = True
    balance.assert_called_once_with(**expected)
    for operation in (providers.run_auto_until_settled, providers.balance_accounts, providers.evaluate_codex_balance):
        for call in operation.call_args_list:
            assert "model" not in call.kwargs
    assert json.loads(capsys.readouterr().out)["antigravity"]["action"] == "would_switch"


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_antigravity_model_option_rejects_other_providers(monkeypatch, providers, capsys, provider):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, providers, ["balance", "--provider", provider, "--model", "gemini-4-argon-medium"])
    assert exc.value.code == 2
    providers.balance_accounts.assert_not_called()
    providers.evaluate_codex_balance.assert_not_called()
    assert "--model applies only to Antigravity" in capsys.readouterr().err


def test_no_model_switch_retains_all_family_backend_default(monkeypatch, providers, capsys):
    switch = Mock(return_value={"active": "test@example.test"})
    monkeypatch.setattr(ag, "switch", switch)
    run_cli(monkeypatch, providers, ["switch", "--provider", "antigravity", "test@example.test", "--json"])
    switch.assert_called_once_with("test@example.test")
    assert json.loads(capsys.readouterr().out)["active"] == "test@example.test"
