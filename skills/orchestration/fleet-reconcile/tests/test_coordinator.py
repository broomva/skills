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
    assert banned[:3] == ["Agent", "Edit", "Write"] and len(banned) == 3 + 42
    assert all(t.startswith("mcp__paseo__") for t in banned[3:])
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
    assert env["GH_TOKEN"].startswith("github_pat_")  # §5.2: the coordinator gets the fleet token
    argv = (tmp_path / "argv").read_text()  # one argument per line; the prompt spans several
    assert argv.index("\n--\n") < argv.index("the fleet coordinator for scope broomva, tick 3")
    st = os.stat(str(world.state["broomva"] / "coordinator-settings.json"))
    assert stat.S_IMODE(st.st_mode) == 0o600


# --------------------------------------------------------------------------
# The driver profile

def test_the_driver_profile_is_probe_6s_shape_with_the_scopes_allowlist(world):
    world.write_config(driver={"allowed_domains": ["api.github.com", "registry.npmjs.org"], "allow_write": ["~/.bun"]})
    p = profile.driver_profile(config.scope("broomva"), "broomva-x-pr1", "TOKEN", "/g")
    assert p["crossSessionInbound"] == "accept"
    sb = p["sandbox"]
    assert sb["enabled"] is True and sb["allowUnsandboxedCommands"] is False
    assert sb["network"] == {"strictAllowlist": True, "allowedDomains": ["api.github.com", "registry.npmjs.org"]}
    assert sb["filesystem"]["denyRead"] == ["~/.config/gh", "~/.paseo", "~/Library/Keychains/login.keychain-db"]
    assert sb["filesystem"]["allowWrite"] == ["~/.bun"]
    assert p["permissions"]["deny"] == ["Read(~/.paseo/**)", "Read(~/.config/gh/**)", "Edit(~/.claude/**)",
                                        "Edit(**/.claude/settings*.json)"]
    assert not any(".claude/**" == d.split("(")[1].rstrip(")") for d in p["permissions"]["deny"])  # own worktree
    assert p["env"] == {"GH_TOKEN": "TOKEN", "GH_CONFIG_DIR": "/g"}


def test_the_profile_file_is_0600_and_the_token_file_must_be_too(world, tmp_path):
    tok = tmp_path / "gh-token"
    tok.write_text("github_pat_" + "Z" * 40 + "\n")
    tok.chmod(0o600)
    world.write_config(gh_token_file=str(tok))
    sec = config.scope("broomva")
    assert profile.read_token(sec) == "github_pat_" + "Z" * 40
    f = profile.write(world.state["broomva"] / "profiles" / "k.json", profile.driver_profile(sec, "k", "T", "/g"))
    assert stat.S_IMODE(os.stat(str(f)).st_mode) == 0o600
    tok.chmod(0o644)
    assert profile.read_token(sec) is None
    tok.chmod(0o600)
    tok.write_text("\n")
    assert profile.read_token(sec) is None


def test_the_cli_never_prints_the_token(world, tmp_path):
    secret = "github_pat_" + "S" * 40
    tok = tmp_path / "gh-token"
    tok.write_text(secret)
    tok.chmod(0o600)
    world.write_config(gh_token_file=str(tok))
    env = dict(os.environ, FLEET_SCOPE="broomva")
    for extra in ([], ["--write"]):
        out = subprocess.run(["/bin/sh", str(FLEET), "driver-profile", "--key", "broomva-x-pr1"] + extra,
                             capture_output=True, text=True, env=env, timeout=60)
        assert out.returncode == 0, out.stderr
        assert secret not in out.stdout + out.stderr and "[withheld" in out.stdout
    written = world.state["broomva"] / "profiles" / "broomva-x-pr1.json"
    assert json.loads(written.read_text())["env"]["GH_TOKEN"] == secret
    assert stat.S_IMODE(os.stat(str(written)).st_mode) == 0o600
    tok.unlink()
    out = subprocess.run(["/bin/sh", str(FLEET), "driver-profile", "--key", "k", "--write"], capture_output=True,
                         text=True, env=env, timeout=60)
    assert out.returncode == 1 and "not written" in out.stderr


def test_a_bad_driver_section_fails_config_check(world):
    for bad in ({"allowed_domains": "github.com"}, {"surprise": 1}, {"model": 3}):
        world.write_config(driver=bad)
        with pytest.raises(config.ConfigError):
            config.scope("broomva")
