"""install.sh: renders the plist, seeds the config once, loads the job with
bootout-then-bootstrap (so a rerun is safe), and uninstalls to the Trash. The
launchctl here is a stub that records its arguments; nothing is loaded."""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import SKILL

INSTALL = SKILL / "scripts" / "install.sh"


@pytest.fixture
def inst(world, tmp_path):
    calls = tmp_path / "launchctl.log"
    launchctl = tmp_path / "launchctl"
    launchctl.write_text('#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\n' % calls)
    launchctl.chmod(0o755)
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    trash = tmp_path / "trash.sh"
    trash.write_text('#!/bin/sh\nmv "$1" "%s/"\n' % trash_dir)
    trash.chmod(0o755)
    agents = tmp_path / "LaunchAgents"
    cfg = tmp_path / "cfg" / "fleet.json"

    def run(*args, script=INSTALL):
        env = dict(os.environ, FLEET_LAUNCHCTL=str(launchctl), FLEET_LAUNCH_AGENTS_DIR=str(agents),
                   FLEET_CONFIG=str(cfg), FLEET_TRASH=str(trash))
        return subprocess.run(["/bin/bash", str(script), *args], capture_output=True, text=True, env=env,
                              timeout=120)

    def calls_():
        return calls.read_text().splitlines() if calls.exists() else []

    return type("Inst", (), {"run": staticmethod(run), "calls": staticmethod(calls_), "agents": agents, "cfg": cfg,
                             "trash": trash_dir})


def _plist(inst, scope="broomva"):
    with (inst.agents / ("com.broomva.fleet-reconcile.%s.plist" % scope)).open("rb") as fh:
        return plistlib.load(fh)


def test_install_renders_the_plist_seeds_the_config_and_loads_the_job(inst):
    out = inst.run("--scope", "broomva", "--force")
    assert out.returncode == 0, out.stdout + out.stderr
    p = _plist(inst)
    assert p["Label"] == "com.broomva.fleet-reconcile.broomva"
    assert p["ProgramArguments"] == ["/bin/bash", str(SKILL / "scripts" / "tick.sh")]
    assert p["StartInterval"] == 3600 and p["RunAtLoad"] is False and "ProcessType" not in p
    assert p["EnvironmentVariables"]["FLEET_SCOPE"] == "broomva"
    assert p["EnvironmentVariables"]["FLEET_CONFIG"] == str(inst.cfg)
    assert oct(inst.cfg.stat().st_mode & 0o777) == "0o600"
    assert json.loads(inst.cfg.read_text()) == json.loads((SKILL / "templates" / "fleet.json.example").read_text())
    uid = os.getuid()
    assert inst.calls() == ["bootout gui/%d/com.broomva.fleet-reconcile.broomva" % uid,
                            "bootstrap gui/%d %s" % (uid, inst.agents / "com.broomva.fleet-reconcile.broomva.plist")]


def test_a_second_install_reloads_and_never_overwrites_the_config(inst):
    assert inst.run("--scope", "broomva", "--force").returncode == 0
    cfg = json.loads(inst.cfg.read_text())
    cfg["scopes"]["broomva"]["dry_run"] = 1
    cfg["scopes"]["broomva"]["mail_interval_h"] = 7
    inst.cfg.write_text(json.dumps(cfg))
    assert inst.run("--scope", "broomva", "--force").returncode == 0
    assert json.loads(inst.cfg.read_text())["scopes"]["broomva"]["mail_interval_h"] == 7
    assert [c.split()[0] for c in inst.calls()] == ["bootout", "bootstrap", "bootout", "bootstrap"]


def test_uninstall_unloads_and_moves_the_plist_to_the_trash(inst):
    assert inst.run("--scope", "broomva", "--force").returncode == 0
    out = inst.run("--scope", "broomva", "--uninstall")
    assert out.returncode == 0, out.stderr
    assert not (inst.agents / "com.broomva.fleet-reconcile.broomva.plist").exists()
    assert (inst.trash / "com.broomva.fleet-reconcile.broomva.plist").exists()
    assert inst.calls()[-1].startswith("bootout ")
    assert inst.cfg.exists()  # the config stays
    again = inst.run("--scope", "broomva", "--uninstall")
    assert again.returncode == 0 and "no plist" in again.stdout


def test_a_dry_run_changes_nothing(inst):
    out = inst.run("--scope", "broomva", "--dry-run", "--force")
    assert out.returncode == 0 and "nothing was changed" in out.stdout
    assert not inst.cfg.exists() and not inst.agents.exists() and inst.calls() == []


def test_a_broken_config_stops_the_install(inst):
    inst.cfg.parent.mkdir(parents=True)
    inst.cfg.write_text('{"v": 1, "scopes": {"broomva": {"surprise": 1}}}')
    out = inst.run("--scope", "broomva", "--force")
    assert out.returncode == 1 and "config-check failed" in out.stderr
    assert inst.calls() == []


def test_a_scope_is_required(inst):
    assert inst.run().returncode == 2


def test_a_temporary_checkout_is_refused(inst, tmp_path):
    copy = tmp_path / "repo" / ".claude" / "worktrees" / "wt" / "fleet-reconcile"
    shutil.copytree(str(SKILL / "scripts"), str(copy / "scripts"))
    shutil.copytree(str(SKILL / "templates"), str(copy / "templates"))
    out = inst.run("--scope", "broomva", script=copy / "scripts" / "install.sh")
    assert out.returncode == 2 and "temporary checkout" in out.stderr
    assert inst.calls() == []
