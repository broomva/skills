"""install.sh: pins a copy of the code, renders the plist to run that copy,
seeds the config once, loads the job with bootout-wait-bootstrap (so a rerun
is safe), retries a failed bootstrap, and uninstalls to the Trash. launchctl
here is a stub that records its arguments; nothing is loaded."""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import SKILL, _git

INSTALL = SKILL / "scripts" / "install.sh"
LABEL = "com.broomva.fleet-reconcile.broomva"


@pytest.fixture
def inst(world, tmp_path):
    calls = tmp_path / "launchctl.log"
    fails = tmp_path / "bootstrap-fails"
    launchctl = tmp_path / "launchctl"
    # `print` says "not loaded"; `bootstrap` fails while the fails file holds a count above 0.
    launchctl.write_text('#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\n'
                         '[ "$1" = print ] && exit 113\n'
                         'if [ "$1" = bootstrap ] && [ -f "%s" ]; then n=$(cat "%s"); '
                         'if [ "$n" -gt 0 ]; then echo $((n-1)) > "%s"; exit 5; fi; fi\nexit 0\n'
                         % (calls, fails, fails, fails))
    launchctl.chmod(0o755)
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    trash = tmp_path / "trash.sh"
    trash.write_text('#!/bin/sh\nmv "$1" "%s/"\n' % trash_dir)
    trash.chmod(0o755)
    agents = tmp_path / "LaunchAgents"
    releases = tmp_path / "releases"
    cfg = tmp_path / "cfg" / "fleet.json"

    def run(*args, script=INSTALL):
        env = dict(os.environ, FLEET_LAUNCHCTL=str(launchctl), FLEET_LAUNCH_AGENTS_DIR=str(agents),
                   FLEET_CONFIG=str(cfg), FLEET_TRASH=str(trash), FLEET_RELEASES_DIR=str(releases))
        return subprocess.run(["/bin/bash", str(script), *args], capture_output=True, text=True, env=env,
                              timeout=120)

    def calls_(verbs=("bootout", "bootstrap")):
        lines = calls.read_text().splitlines() if calls.exists() else []
        return [ln for ln in lines if ln.split()[0] in verbs]

    return type("Inst", (), {"run": staticmethod(run), "calls": staticmethod(calls_), "agents": agents, "cfg": cfg,
                             "trash": trash_dir, "releases": releases, "fails": fails})


def _plist(inst):
    with (inst.agents / (LABEL + ".plist")).open("rb") as fh:
        return plistlib.load(fh)


def test_install_pins_a_copy_renders_the_plist_seeds_the_config_and_loads_the_job(inst):
    out = inst.run("--scope", "broomva", "--force")
    assert out.returncode == 0, out.stdout + out.stderr
    (rel,) = list(inst.releases.iterdir())
    commit = subprocess.run(["git", "-C", str(SKILL), "rev-parse", "--short=12", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    assert rel.name.startswith(commit)
    for f in ("orchestration/fleet-reconcile/scripts/tick.sh", "orchestration/fleet-reconcile/scripts/fleet",
              "orchestration/fleet-reconcile/templates/fleet.json.example",
              "orchestration/ctx-core/scripts/ctx.py", "RELEASE"):
        assert (rel / f).is_file(), f
    assert not list(rel.rglob("__pycache__")) and not (rel / "orchestration/fleet-reconcile/tests").exists()
    p = _plist(inst)
    assert p["Label"] == LABEL
    assert p["ProgramArguments"] == ["/bin/bash", str(rel / "orchestration/fleet-reconcile/scripts/tick.sh")]
    assert p["StartInterval"] == 3600 and p["RunAtLoad"] is False and "ProcessType" not in p
    assert p["EnvironmentVariables"]["FLEET_SCOPE"] == "broomva"
    assert p["EnvironmentVariables"]["FLEET_CONFIG"] == str(inst.cfg)
    assert oct(inst.cfg.stat().st_mode & 0o777) == "0o600"
    assert json.loads(inst.cfg.read_text()) == json.loads((SKILL / "templates" / "fleet.json.example").read_text())
    uid = os.getuid()
    assert inst.calls() == ["bootout gui/%d/%s" % (uid, LABEL),
                            "bootstrap gui/%d %s" % (uid, inst.agents / (LABEL + ".plist"))]


def test_the_pinned_copy_runs_without_the_checkout(inst, tmp_path):
    assert inst.run("--scope", "broomva", "--force").returncode == 0
    (rel,) = list(inst.releases.iterdir())
    out = subprocess.run(["/bin/sh", str(rel / "orchestration/fleet-reconcile/scripts/fleet"), "config-check",
                          "broomva"], capture_output=True, text=True, env=dict(os.environ, FLEET_CONFIG=str(inst.cfg)))
    assert out.returncode == 0, out.stderr


def test_a_second_install_reloads_and_never_overwrites_the_config(inst):
    assert inst.run("--scope", "broomva", "--force").returncode == 0
    cfg = json.loads(inst.cfg.read_text())
    cfg["scopes"]["broomva"]["mail_interval_h"] = 7
    inst.cfg.write_text(json.dumps(cfg))
    assert inst.run("--scope", "broomva", "--force").returncode == 0
    assert json.loads(inst.cfg.read_text())["scopes"]["broomva"]["mail_interval_h"] == 7
    assert [c.split()[0] for c in inst.calls()] == ["bootout", "bootstrap", "bootout", "bootstrap"]
    assert any(ln.startswith("print ") for ln in inst.calls(("print",)))  # it waited for the bootout


def test_a_failed_bootstrap_is_retried(inst):
    inst.fails.write_text("2")
    out = inst.run("--scope", "broomva", "--force")
    assert out.returncode == 0, out.stderr
    assert [c.split()[0] for c in inst.calls()] == ["bootout", "bootstrap", "bootstrap", "bootstrap"]
    inst.fails.write_text("5")
    out = inst.run("--scope", "broomva", "--force")
    assert out.returncode == 1 and "failed three times" in out.stderr


def test_uninstall_unloads_and_moves_the_plist_to_the_trash(inst):
    assert inst.run("--scope", "broomva", "--force").returncode == 0
    out = inst.run("--scope", "broomva", "--uninstall")
    assert out.returncode == 0, out.stderr
    assert not (inst.agents / (LABEL + ".plist")).exists()
    assert (inst.trash / (LABEL + ".plist")).exists()
    assert inst.calls()[-1].startswith("bootout ")
    assert inst.cfg.exists() and list(inst.releases.iterdir())  # config and releases stay
    again = inst.run("--scope", "broomva", "--uninstall")
    assert again.returncode == 0 and "no plist" in again.stdout


def test_a_dry_run_checks_the_config_and_changes_nothing(inst):
    out = inst.run("--scope", "broomva", "--dry-run", "--force")
    assert out.returncode == 0 and "nothing was changed" in out.stdout, out.stderr
    assert "config-check: ok" in out.stdout
    assert not inst.cfg.exists() and not inst.agents.exists() and not inst.releases.exists()
    assert inst.calls() == []


def test_a_broken_config_stops_the_install(inst):
    inst.cfg.parent.mkdir(parents=True)
    inst.cfg.write_text('{"v": 1, "scopes": {"broomva": {"surprise": 1}}}')
    out = inst.run("--scope", "broomva", "--force")
    assert out.returncode == 1 and "config-check failed" in out.stderr
    assert inst.calls() == [] and not inst.releases.exists()


def test_a_scope_is_required(inst):
    assert inst.run().returncode == 2


def test_uncommitted_changes_are_refused_without_force(inst, tmp_path):
    repo = tmp_path / "repo"
    for name in ("fleet-reconcile", "ctx-core"):
        shutil.copytree(str(SKILL.parent / name), str(repo / "orchestration" / name),
                        ignore=shutil.ignore_patterns("__pycache__", "tests"))
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "x", cwd=repo)
    script = repo / "orchestration" / "fleet-reconcile" / "scripts" / "install.sh"
    clean = inst.run("--scope", "broomva", script=script)
    assert clean.returncode == 0, clean.stderr
    (repo / "orchestration" / "fleet-reconcile" / "scripts" / "tick.sh").write_text("# edited\n")
    dirty = inst.run("--scope", "broomva", script=script)
    assert dirty.returncode == 2 and "uncommitted changes" in dirty.stderr
    forced = inst.run("--scope", "broomva", "--force", script=script)
    assert forced.returncode == 0 and any("-dirty-" in p.name for p in inst.releases.iterdir())
