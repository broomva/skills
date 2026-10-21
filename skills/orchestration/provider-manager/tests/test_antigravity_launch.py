import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import pm_antigravity_launch as launcher

pytestmark = pytest.mark.new_only


def bound(count=1, **changes):
    thread = {"threadId": "thread-one", "model": "gemini-4-argon-medium",
              "providerInstanceId": "antigravity-balanced", "runCount": count,
              "itemCount": 1,
              "relationshipToParent": None}
    thread.update(changes)
    return thread


def context_stub(monkeypatch, thread=None, capability=None):
    thread = thread or bound()
    capability = capability or {"parentThreadId": "thread-one", "inheritedModel": "gemini-4-argon-medium",
                               "inheritedProviderInstanceId": "antigravity-balanced"}
    monkeypatch.setattr(launcher, "t3_call", lambda tool, args, env:
                        capability if tool == "orchestrator_capabilities" else {"thread": thread})


def profile(tmp_path):
    home = tmp_path / "profile"
    folder = home / "antigravity-acp"
    folder.mkdir(parents=True)
    (folder / "acp_token.json").write_text("synthetic-private-token")
    (folder / "settings.json").write_text(json.dumps({"auth": {"type": "oauth-personal"}}))
    binary = tmp_path / "agy_acp_server.par"
    harness = tmp_path / "localharness_external"
    for path in (binary, harness):
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o700)
    return {"profile": str(home), "binary": str(binary), "email": "personal@example.test"}


def test_exec_keeps_stdio_unmodified_and_forces_private_account(monkeypatch, tmp_path, capsys):
    context_stub(monkeypatch)
    account = profile(tmp_path)
    pins = []
    def pin(key, model, require_existing=False):
        pins.append((key, model, require_existing))
        return account
    monkeypatch.setattr(launcher.pm_antigravity, "pin_session", pin)
    executed = []
    monkeypatch.setattr(launcher.os, "execve", lambda *args: executed.append(args))
    launcher.launch(environment={"PATH": "/usr/bin", "GEMINI_HOME": "/wrong",
                                "GEMINI_API_KEY": "never-used", "AGY_ACP_FORCE_FILE_STORAGE": "0"})
    assert pins == [("t3:antigravity-balanced:thread-one", "gemini-4-argon-medium", False)]
    binary, args, env = executed[0]
    assert binary == account["binary"] and args == [binary]
    assert env["GEMINI_HOME"] == account["profile"]
    assert env["AGY_ACP_FORCE_FILE_STORAGE"] == "1"
    assert env["BROWSER"] == "/usr/bin/false"
    assert "GEMINI_API_KEY" not in env
    assert capsys.readouterr().out == ""


def test_existing_thread_requires_existing_pin(monkeypatch, tmp_path):
    context_stub(monkeypatch, bound(2))
    calls = []
    def pin(*args, **kwargs):
        calls.append(kwargs)
        raise launcher.pm_antigravity.AntigravityError("unbound")
    monkeypatch.setattr(launcher.pm_antigravity, "pin_session", pin)
    with pytest.raises(launcher.pm_antigravity.AntigravityError):
        launcher.launch(environment={})
    assert calls == [{"require_existing": True}]


def test_imported_history_with_first_local_run_requires_pin(monkeypatch):
    context_stub(monkeypatch, bound(itemCount=12))
    assert launcher.context({})[2] is True


@pytest.mark.parametrize("changes", [{"relationshipToParent": "fork"}, {"runCount": None},
    {"runCount": 0}, {"runCount": True}, {"threadId": "other"}, {"model": "changed"},
    {"providerInstanceId": "other"}])
def test_ambiguous_or_fork_context_never_selects(monkeypatch, changes):
    context_stub(monkeypatch, bound(**changes))
    monkeypatch.setattr(launcher.pm_antigravity, "pin_session", lambda *a, **k: pytest.fail("must not pin"))
    with pytest.raises(launcher.LaunchError):
        launcher.launch(environment={})


def test_unbound_discovery_context_fails_closed(monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: pytest.fail("must not call external command"))
    with pytest.raises(launcher.LaunchError):
        launcher.launch(environment={})


def test_supported_t3_cli_transport_uses_env_not_argument_credentials(monkeypatch):
    env = {"T3_ACP_MCP_NODE": "/app/node", "T3_ACP_MCP_ENTRYPOINT": "/app/entry.mjs",
           "T3_ACP_MCP_ENDPOINT": "http://localhost/mcp", "T3_ACP_MCP_AUTHORIZATION": "private"}
    seen = []
    def call(command, **kwargs):
        seen.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"structuredContent": {"parentThreadId": "one"}}).encode())
    monkeypatch.setattr(launcher.subprocess, "run", call)
    assert launcher.t3_call("orchestrator_capabilities", {}, env)["parentThreadId"] == "one"
    command, kwargs = seen[0]
    assert command == ["/app/node", "/app/entry.mjs", "acp-mcp-call", "orchestrator_capabilities", "{}"]
    assert "private" not in command
    assert kwargs["env"]["ELECTRON_RUN_AS_NODE"] == "1"
    assert kwargs["timeout"] == 15


@pytest.mark.parametrize("content", [None, "private-invalid-context", {}, 7, False])
def test_malformed_mcp_content_raises_sanitized_launch_error(content):
    with pytest.raises(launcher.LaunchError, match="malformed launcher context content") as exc:
        launcher._structured({"content": content})
    assert "private-invalid-context" not in str(exc.value)


def test_structured_mcp_context_takes_precedence_over_unused_content():
    assert launcher._structured({"structuredContent": {"threadId": "one"}, "content": None}) == {"threadId": "one"}


def test_malformed_context_cli_error_has_no_traceback(monkeypatch, capsys):
    def malformed(*args, **kwargs):
        launcher._structured({"content": None})
    monkeypatch.setattr(launcher, "launch", malformed)
    assert launcher.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "launch refused" in captured.err


@pytest.mark.parametrize("mutation", ["symlink", "wrong-auth", "missing-harness"])
def test_invalid_profile_or_pair_refuses_exec(tmp_path, mutation):
    entry = profile(tmp_path)
    if mutation == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(entry["profile"])
        entry["profile"] = str(alias)
    elif mutation == "wrong-auth":
        (Path(entry["profile"]) / "antigravity-acp/settings.json").write_text('{"auth":{"type":"gemini-api-key"}}')
    else:
        (tmp_path / "localharness_external").unlink()
    with pytest.raises(launcher.LaunchError):
        launcher.child_environment(entry, {})
