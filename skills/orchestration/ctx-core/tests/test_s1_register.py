"""The owner's registration script: off unless a stage is named, backs up,
idempotent, touches only its own entries, and --remove takes them all out."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import s1_support as S

SCRIPT = S.SCRIPTS / "register_s1_hooks.py"
OTHER = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "guard.sh"}]}],
                   "SessionStart": [{"hooks": [{"type": "command", "command": "ctx-hook.sh session-start"}]}]},
         "model": "opus"}


def run(settings: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--settings", str(settings), "--python", sys.executable,
                           *args], capture_output=True, text=True)


@pytest.fixture
def settings(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(OTHER, indent=2))
    return p


def backups(p: Path):
    return sorted(p.parent.glob(p.name + ".bak-ctx-s1-*"))


def test_no_stage_named_changes_nothing(settings):
    before = settings.read_text()
    r = run(settings)
    assert r.returncode == 0 and "nothing is registered" in r.stdout
    assert settings.read_text() == before and not backups(settings)


def test_named_stages_are_added_beside_everything_else(settings):
    r = run(settings, "--stages", "pre-edit,post-bash,subagent", "--shadow")
    assert r.returncode == 0, r.stderr
    data = json.loads(settings.read_text())
    assert data["model"] == "opus"
    pre = data["hooks"]["PreToolUse"]
    assert pre[0]["hooks"][0]["command"] == "guard.sh"  # the existing entry stays first and unchanged
    s1 = [g for g in pre if "ctx-s1-hook.sh" in g["hooks"][0]["command"]]
    assert len(s1) == 1 and s1[0]["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
    cmd = s1[0]["hooks"][0]["command"]
    assert "CTX_S1=1 CTX_S1_STAGES=pre-edit CTX_S1_SHADOW=1" in cmd and cmd.endswith(" pre-edit")
    assert any(g.get("matcher") == "Bash" and "post-bash" in g["hooks"][0]["command"]
               for g in data["hooks"]["PostToolUse"])
    assert "SubagentStart" in data["hooks"]
    assert len(backups(settings)) == 1


def test_it_is_idempotent_and_converges_on_the_requested_set(settings):
    run(settings, "--stages", "pre-edit,prompt")
    once = settings.read_text()
    r = run(settings, "--stages", "pre-edit,prompt")
    assert "nothing to do" in r.stdout and settings.read_text() == once and len(backups(settings)) == 1
    run(settings, "--stages", "prompt")
    data = json.loads(settings.read_text())
    cmds = [h["command"] for ev in data["hooks"].values() for g in ev for h in g["hooks"]]
    assert sum("ctx-s1-hook.sh" in c for c in cmds) == 1 and any(c.endswith(" prompt") for c in cmds)


def test_remove_takes_out_only_its_own_entries(settings):
    run(settings, "--stages", "pre-edit,prompt,session-start")
    r = run(settings, "--remove")
    assert r.returncode == 0
    assert json.loads(settings.read_text()) == OTHER


def test_an_unknown_stage_is_refused(settings):
    before = settings.read_text()
    r = run(settings, "--stages", "pre-compact")
    assert r.returncode == 2 and settings.read_text() == before


def test_a_shared_group_keeps_its_other_hooks(settings):
    """Remove only the gate's own entries: a group someone else also uses stays."""
    run(settings, "--stages", "pre-edit")
    data = json.loads(settings.read_text())
    group = [g for g in data["hooks"]["PreToolUse"] if "ctx-s1-hook.sh" in g["hooks"][0]["command"]][0]
    group["hooks"].append({"type": "command", "command": "their-own-check.sh"})
    settings.write_text(json.dumps(data))
    run(settings, "--remove")
    cmds = [h["command"] for g in json.loads(settings.read_text())["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert "their-own-check.sh" in cmds and not any("ctx-s1-hook.sh" in c for c in cmds)


def test_paths_are_quoted_and_the_file_mode_kept(tmp_path):
    odd = tmp_path / "with space"
    odd.mkdir()
    p = odd / "settings.json"
    p.write_text(json.dumps(OTHER))
    p.chmod(0o600)
    r = run(p, "--stages", "prompt", "--params", str(odd / "floors.json"))
    assert r.returncode == 0, r.stderr
    cmd = [h["command"] for g in json.loads(p.read_text())["hooks"]["UserPromptSubmit"] for h in g["hooks"]][0]
    assert "CTX_S1_PARAMS='%s'" % (odd / "floors.json") in cmd
    assert oct(p.stat().st_mode & 0o777) == oct(0o600)


def test_a_missing_interpreter_is_refused(settings):
    before = settings.read_text()
    r = subprocess.run([sys.executable, str(SCRIPT), "--settings", str(settings), "--python", "/nonexistent/py",
                        "--stages", "prompt"], capture_output=True, text=True)
    assert r.returncode == 1 and settings.read_text() == before
