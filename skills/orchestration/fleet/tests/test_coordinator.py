"""The coordinator's posture (spec §5.3, §5.7) and the driver profile (§5.5).

The pinned Paseo classification must cover every tool Paseo registers: the
captured list (tests/fixtures/paseo-0.9.2-tools.json) fails this test the day
Paseo adds one the pins don't name; recapture it when Paseo updates."""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import FLEET, HERE

from fleetlib import config, coordinator, profile

PASEO = json.loads((HERE / "fixtures" / "paseo-0.9.2-tools.json").read_text())


def test_every_tool_paseo_registers_is_classified_read_or_write_and_not_both():
    pins = config.PASEO_TOOLS
    read, write = set(pins["read"]), set(pins["write"])
    assert not read & write
    assert set(PASEO["tools"]) - read - write == set(), "Paseo has tools the pinned lists don't classify"
    assert (len(read), len(write)) == (19, 42) and pins["paseo_version"] == PASEO["paseo_version"]


def test_the_argv_disallows_agent_edit_write_and_every_paseo_write_with_the_prompt_after_a_double_dash(world):
    world.write_config(mode="act", coordinator_model="claude-haiku-4-5-20251001")
    sec = config.scope("broomva")
    av = coordinator.argv(sec, Path("/s.json"), "the prompt")
    i = av.index("--disallowedTools")
    assert av[-2:] == ["--", "the prompt"]
    banned = av[i + 1:av.index("--")]
    assert banned[:4] == ["Agent", "Edit", "Write", "NotebookEdit"] and len(banned) == 4 + 42
    assert all(t.startswith("mcp__paseo__") for t in banned[4:])
    assert "--strict-mcp-config" in av and av[av.index("--max-budget-usd") + 1] == "2"
    assert av[av.index("--name") + 1] == "fleet-coordinator-broomva" and "--model" in av
    assert av[av.index("--output-format") + 1] == "stream-json" and "--verbose" in av


def test_the_settings_register_the_send_gate_on_sendmessage_pre_and_post():
    s = coordinator.settings("/x/fleet", "broomva")["hooks"]
    assert set(s) == {"PreToolUse", "PostToolUse", "PostToolUseFailure"}
    for event, which in (("PreToolUse", "pre"), ("PostToolUse", "post"), ("PostToolUseFailure", "post")):
        (entry,) = s[event]
        (h,) = entry["hooks"]
        assert entry["matcher"] == "SendMessage" and h["timeout"] == 10
        assert h["command"] == "/x/fleet send-gate %s --scope broomva" % which


def test_the_posture_check(world):
    sec = config.scope("broomva")
    base = ["Bash", "Read", "SendMessage", "mcp__paseo__list_agents"]
    assert coordinator.posture_problems(base, sec) == []
    assert coordinator.posture_problems(base + ["Agent"], sec) == ["Agent is in the tool list"]
    assert "write tool create_agent" in coordinator.posture_problems(base + ["mcp__paseo__create_agent"], sec)[0]
    assert "neither pinned list" in coordinator.posture_problems(base + ["mcp__paseo__teleport"], sec)[0]


def _init(path, tools):
    path.write_text("\n".join(json.dumps(x) for x in (
        {"type": "system", "subtype": "hook_started"},
        {"type": "system", "subtype": "init", "tools": tools, "session_id": "x"})) + "\n")


def test_config_check_init_reads_a_stream_json_init_event(world, tmp_path):
    env = dict(os.environ, FLEET_SCOPE="broomva")
    f = tmp_path / "s.jsonl"
    _init(f, ["Bash", "mcp__paseo__list_agents"])
    ok = subprocess.run(["/bin/sh", str(FLEET), "config-check", "broomva", "--init", str(f)], capture_output=True,
                        text=True, env=env, timeout=60)
    assert ok.returncode == 0 and "2 tools" in ok.stdout
    _init(f, ["Bash", "mcp__paseo__brand_new_tool"])
    bad = subprocess.run(["/bin/sh", str(FLEET), "config-check", "broomva", "--init", str(f)], capture_output=True,
                         text=True, env=env, timeout=60)
    assert bad.returncode == 1 and "brand_new_tool" in bad.stderr
    f.write_text('{"type": "result"}\n')
    assert subprocess.run(["/bin/sh", str(FLEET), "config-check", "broomva", "--init", str(f)],
                          capture_output=True, env=env, timeout=60).returncode == 1


def _stub_claude(tmp_path, tools):
    stub = tmp_path / "claude"
    stub.write_text("#!/bin/sh\n"
                    'printf "%%s\\n" "$@" > "%s/argv"\n'
                    'env > "%s/env"\n'
                    "echo '%s'\n"
                    "sleep 5 &\nwait\n"
                    "echo '{\"type\": \"result\", \"result\": \"nothing to do\"}'\n"
                    % (tmp_path, tmp_path, json.dumps({"type": "system", "subtype": "init", "tools": tools})))
    stub.chmod(0o755)
    return str(stub)


def test_run_terminates_a_coordinator_whose_tool_list_fails_the_posture(world, tmp_path):
    world.write_config(mode="act")
    sec = config.scope("broomva")
    out = tmp_path / "t" / "coordinator.jsonl"
    out.parent.mkdir()
    import time
    t0 = time.monotonic()
    res = coordinator.run(sec, 3, "/x/fleet", out, True, claude=_stub_claude(tmp_path, ["Bash", "Agent"]))
    assert res["exit"] == coordinator.EXIT_POSTURE and res["posture"] == ["Agent is in the tool list"]
    assert time.monotonic() - t0 < 4  # terminated, not waited out
    assert '"result"' not in out.read_text()


def test_run_passes_a_clean_coordinator_its_tick_and_no_session_variables(world, tmp_path, monkeypatch):
    world.write_config(mode="act")
    sec = config.scope("broomva")
    out = tmp_path / "t" / "coordinator.jsonl"
    out.parent.mkdir()
    monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
    monkeypatch.setenv("PASEO_AGENT_ID", "x")
    monkeypatch.setenv("GH_TOKEN", "github_pat_" + "Q" * 30)
    res = coordinator.run(sec, 3, "/x/fleet", out, True, claude=_stub_claude(tmp_path, ["Bash"]))
    assert res["exit"] == 0 and res["init"] and res["posture"] == []
    env = dict(ln.split("=", 1) for ln in (tmp_path / "env").read_text().splitlines() if "=" in ln)
    assert env["FLEET_TICK"] == "3" and env["FLEET_CHILD"] == "1" and env["DRY_RUN"] == "1"
    assert "CLAUDE_CODE_CHILD_SESSION" not in env and "PASEO_AGENT_ID" not in env
    assert "GH_TOKEN" not in env  # the owner's gh login: no token reaches the coordinator (0.4.0)
    argv = (tmp_path / "argv").read_text()  # one argument per line; the prompt spans several
    assert argv.index("\n--\n") < argv.index("the fleet coordinator for scope broomva, tick 3")
    st = os.stat(str(world.state["broomva"] / "coordinator-settings.json"))
    assert stat.S_IMODE(st.st_mode) == 0o600


# --------------------------------------------------------------------------
# The driver profile

def test_the_driver_profile_is_probe_6s_shape_with_the_scopes_allowlist(world):
    world.write_config(driver={"allowed_domains": ["api.github.com", "registry.npmjs.org"], "allow_write": ["~/.bun"]})
    p = profile.driver_profile(config.scope("broomva"), "broomva-x-pr1")
    assert p["crossSessionInbound"] == "accept"
    sb = p["sandbox"]
    assert sb["enabled"] is True and sb["allowUnsandboxedCommands"] is False
    assert sb["network"] == {"strictAllowlist": True, "allowedDomains": ["api.github.com", "registry.npmjs.org"]}
    # gh's config and the keychain are readable: a driver uses the owner's login (owner decision 2026-10-01).
    # The login keychain is NOT denied (a file deny is whole-keychain, a W1 decision) and ~/.config/gh stays
    # readable (the gh route needs it); the credential files the gh route doesn't need ARE denied (BRO-2755).
    assert sb["filesystem"]["denyRead"] == ["~/.paseo"] + profile.CRED_DENY_READ
    assert "~/.aws" in sb["filesystem"]["denyRead"] and "~/.ssh" in sb["filesystem"]["denyRead"]
    assert not any("Keychains" in d or "/.config/gh" in d for d in sb["filesystem"]["denyRead"])
    assert sb["filesystem"]["allowWrite"] == ["~/.bun"]
    assert p["permissions"]["deny"] == (
        ["Read(~/.paseo/**)", "Edit(~/.claude/**)", "Edit(**/.claude/settings*.json)"]
        + ["Read(%s)" % c for c in profile.CRED_DENY_READ] + ["Read(%s/**)" % c for c in profile.CRED_DENY_READ])
    assert not any(".claude/**" == d.split("(")[1].rstrip(")") for d in p["permissions"]["deny"])  # own worktree
    assert "env" not in p  # no token, no GH_CONFIG_DIR


def test_the_profile_file_is_0600(world):
    sec = config.scope("broomva")
    f = profile.write(world.state["broomva"] / "profiles" / "k.json", profile.driver_profile(sec, "k"))
    assert stat.S_IMODE(os.stat(str(f)).st_mode) == 0o600


def test_the_cli_writes_a_profile_with_no_token_even_with_a_token_file_configured(world, tmp_path):
    secret = "github_pat_" + "S" * 40
    tok = tmp_path / "gh-token"
    tok.write_text(secret)
    tok.chmod(0o600)
    world.write_config(gh_token_file=str(tok))  # accepted since 0.4.0, not read
    env = dict(os.environ, FLEET_SCOPE="broomva", GH_TOKEN=secret)
    out = subprocess.run(["/bin/sh", str(FLEET), "driver-profile", "--key", "broomva-x-pr1", "--write"],
                         capture_output=True, text=True, env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    written = world.state["broomva"] / "profiles" / "broomva-x-pr1.json"
    assert secret not in out.stdout + out.stderr + written.read_text()
    assert "env" not in json.loads(written.read_text()) and stat.S_IMODE(os.stat(str(written)).st_mode) == 0o600


def test_a_bad_driver_section_fails_config_check(world):
    for bad in ({"allowed_domains": "github.com"}, {"surprise": 1}, {"model": 3}):
        world.write_config(driver=bad)
        with pytest.raises(config.ConfigError):
            config.scope("broomva")


# --------------------------------------------------------------------------
# P20 round 1: an unchecked coordinator is stopped, and the watchdog reaches it

def _stub(tmp_path, body):
    stub = tmp_path / "claude"
    stub.write_text("#!/bin/sh\n" + body)
    stub.chmod(0o755)
    return str(stub)


def test_a_coordinator_that_acts_before_its_init_event_is_stopped(world, tmp_path):
    world.write_config(mode="act")
    out = tmp_path / "c.jsonl"
    res = coordinator.run(config.scope("broomva"), 3, "/x/fleet", out, True, claude=_stub(
        tmp_path, "echo '{\"type\": \"assistant\", \"message\": {}}'\nexec sleep 20\n"))
    assert res["exit"] == coordinator.EXIT_POSTURE and "acted before its init event" in res["posture"][0]


def test_a_coordinator_with_no_init_event_is_stopped_at_the_deadline(world, tmp_path, monkeypatch):
    import time
    world.write_config(mode="act")
    monkeypatch.setattr(coordinator, "INIT_S", 1.0)
    t0 = time.monotonic()
    res = coordinator.run(config.scope("broomva"), 3, "/x/fleet", tmp_path / "c.jsonl", True,
                          claude=_stub(tmp_path, "exec sleep 20\n"))
    assert res["exit"] == coordinator.EXIT_POSTURE and "no init event" in res["posture"][0]
    assert time.monotonic() - t0 < 15


@pytest.mark.parametrize("body, said", [
    ("exit 0\n", "(it exited 0)"),                       # a clean exit, its tool list never checked
    ("exit 3\n", "(it exited 3)"),                       # a crash keeps its own code beside it
    ("exec 1>&-\nexec sleep 30\n", "(it exited -15)"),  # its stream closed while it still runs: stopped
])
def test_a_coordinator_whose_stream_ends_before_its_init_event_fails_its_posture(world, tmp_path, body, said):
    import time
    world.write_config(mode="act")
    t0 = time.monotonic()
    res = coordinator.run(config.scope("broomva"), 3, "/x/fleet", tmp_path / "c.jsonl", True,
                          claude=_stub(tmp_path, body))
    assert res["exit"] == coordinator.EXIT_POSTURE and "ended before its init event" in res["posture"][0]
    assert said in res["posture"][0] and time.monotonic() - t0 < 20  # stopped, not waited out


def test_the_tick_watchdogs_term_to_the_step_group_reaches_the_coordinators_claude(world, tmp_path):
    import signal
    import time
    world.write_config(mode="act")
    stub = _stub(tmp_path, "echo '%s'\nexec sleep 47.25\n" % json.dumps(
        {"type": "system", "subtype": "init", "tools": ["Bash"]}))
    env = dict(os.environ, FLEET_SCOPE="broomva", FLEET_CLAUDE_BIN=stub)
    (world.state["broomva"] / "ticks" / "00003").mkdir(parents=True)
    p = subprocess.Popen(["/bin/sh", str(FLEET), "coordinator", "--tick", "3"], env=env, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    kids = subprocess.run(["pgrep", "-P", str(p.pid)], capture_output=True, text=True).stdout.split()
    assert kids, "the coordinator's claude didn't start"
    os.killpg(p.pid, signal.SIGTERM)  # what tick.sh's watchdog sends to the step's group
    p.wait(timeout=20)
    time.sleep(0.5)
    alive = []
    for k in kids:
        try:
            os.kill(int(k), 0)
            alive.append(k)
        except OSError:
            pass
    assert alive == [], "the coordinator's claude outlived the group TERM"


def test_the_tool_list_is_an_allowlist(world):
    sec = config.scope("broomva")
    av = coordinator.argv(sec, Path("/s.json"), "p")
    assert av[av.index("--tools") + 1:av.index("--disallowedTools")] == ["Bash", "Read", "SendMessage"]
    assert coordinator.posture_problems(["Bash", "Read", "SendMessage"], sec) == []
    assert coordinator.posture_problems(["Bash", "Workflow"], sec) == ["Workflow is outside the allowlist"]
    for bad in (None, "Bash", [1]):
        assert "no tool list" in coordinator.posture_problems(bad, sec)[0]


def test_a_late_init_event_doesnt_undo_the_deadline(world, tmp_path, monkeypatch):
    world.write_config(mode="act")
    monkeypatch.setattr(coordinator, "INIT_S", 0.5)
    res = coordinator.run(config.scope("broomva"), 3, "/x/fleet", tmp_path / "c.jsonl", True, claude=_stub(
        # TERM ignored, so the init line still comes after the deadline's stop began
        tmp_path, "trap '' TERM\nsleep 1.5\necho '%s'\nsleep 3\n" % json.dumps({"type": "system", "subtype": "init",
                                                                                 "tools": ["Bash"]})))
    assert res["exit"] == coordinator.EXIT_POSTURE and "no init event" in res["posture"][0]


def test_a_fleet_child_keeps_auth_and_provider_settings(monkeypatch):
    from fleetlib import sources
    for k, v in (("CLAUDE_CODE_OAUTH_TOKEN", "x"), ("CLAUDE_CODE_USE_BEDROCK", "1"), ("CLAUDE_CODE_SESSION_ID", "s"),
                 ("CLAUDE_CODE_MESSAGING_TOKEN", "m"), ("CLAUDE_CODE_SESSION_ATTENDED", "1"), ("CLAUDECODE", "1"),
                 ("PASEO_AGENT_ID", "a")):
        monkeypatch.setenv(k, v)
    env = sources.child_env()
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "x" and env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert not {"CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDECODE",
                "PASEO_AGENT_ID"} & set(env)  # a parent session's messaging token never reaches a child


def test_a_partial_paseo_classification_fails_config_check(world):
    world.write_config(paseo_tools={"paseo_version": "0.9.3", "read": ["list_agents"]})
    with pytest.raises(config.ConfigError):
        config.scope("broomva")
