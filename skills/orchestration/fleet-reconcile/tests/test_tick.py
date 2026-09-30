"""tick.sh end to end, and the CLI verbs around it, in an isolated HOME with
stub `claude`, `gh`, `osascript` and `p9` that serve the captured fixture and
record how they were called (the fleet token's length only, never its value)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from conftest import SCRIPTS, _git

TICK = SCRIPTS / "tick.sh"
TOKEN = "github_pat_" + "Z" * 40  # a fake, shaped like the real thing


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


@pytest.fixture
def rig(fresh_world, tmp_path):
    w = fresh_world
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls_dir = tmp_path / "calls"
    calls_dir.mkdir()
    fx = w.fixture
    _stub(bin_ / "claude", 'case "$1" in\n'
          '  --version) cat "%s/claude/version.txt" ;;\n'
          '  agents) [ -n "${STUB_HANG:-}" ] && sleep 30; cat "%s/claude/agents.json" ;;\n'
          '  *) exit 2 ;;\nesac\n' % (fx, fx))
    _stub(bin_ / "gh", 'echo "${#GH_TOKEN}" >> "%s/gh-token-lengths"\n'
          'slug=""; for a in "$@"; do case "$a" in repos/*) slug=${a#repos/}; slug=${slug%%%%/rules*} ;; esac; done\n'
          'if [ "$1" = pr ]; then slug=$4; fi\n'
          'd="%s/gh/$(echo "$slug" | sed "s#/#__#")"\n'
          'case "$*" in\n'
          '  *rules/branches*) cat "$d/rules.json" ;;\n'
          '  *default_branch*) cat "$d/default_branch.txt" ;;\n'
          '  "pr list"*) cat "$d/prs.json" ;;\n'
          '  *) exit 1 ;;\nesac\n' % (calls_dir, fx))
    _stub(bin_ / "osascript", 'printf "%%s\\n" "$*" >> "%s/osascript"\n' % calls_dir)
    _stub(bin_ / "p9", 'printf "%%s\\n" "$*" >> "%s/p9"\n' % calls_dir)
    (w.home / ".claude" / "projects").mkdir(parents=True)
    shutil.copytree(str(fx / "claude" / "jobs"), str(w.home / ".claude" / "jobs"))
    shutil.copytree(str(fx / "paseo"), str(w.home / ".paseo"))
    _git("remote", "add", "origin", "https://github.com/broomva/workspace.git", cwd=w.home / "broomva")
    _git("remote", "add", "origin", "https://github.com/broomva/skills.git", cwd=w.home / "broomva" / "skills")
    tok = w.home / ".config" / "broomva" / "fleet" / "gh-token"
    tok.parent.mkdir(parents=True)
    tok.write_text(TOKEN + "\n")
    tok.chmod(0o600)
    env = {"FLEET_CLAUDE_BIN": str(bin_ / "claude"), "FLEET_GH_BIN": str(bin_ / "gh"),
           "CTX_CLAUDE_BIN": str(bin_ / "claude"), "FLEET_OSASCRIPT_BIN": str(bin_ / "osascript"),
           "FLEET_P9_BIN": str(bin_ / "p9"), "FLEET_NOTIFY": "1", "FLEET_SCOPE": "broomva"}
    w.write_config(gh_token_file=str(tok))

    class Rig:
        world, token_file = w, tok

        def tick(self, **extra: str) -> subprocess.CompletedProcess:
            e = dict(os.environ, **env)
            e.update(extra)
            return subprocess.run(["/bin/bash", str(TICK)], capture_output=True, text=True, env=e, timeout=180)

        def fleet(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
            return w.fleet(*args, env=dict(env, **extra))

        def ledger(self, scope="broomva"):
            p = w.state[scope] / "ledger.jsonl"
            return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

        def log(self, scope="broomva"):
            p = w.state[scope] / "tick.log"
            return p.read_text() if p.exists() else ""

        def calls(self, name):
            p = calls_dir / name
            return p.read_text().splitlines() if p.exists() else []

    return Rig()


def test_a_tick_observes_reports_asks_and_records_itself(rig):
    r = rig.tick()
    assert r.returncode == 0, r.stderr
    sd = rig.world.state["broomva"]
    assert (sd / "tick-counter").read_text().strip() == "1"
    td = sd / "ticks" / "00001"
    for f in ("snapshot.json", "report.json", "report.md"):
        assert (td / f).is_file(), rig.log()
    kinds = [x["kind"] for x in rig.ledger()]
    assert kinds[0] == "tick_fire" and kinds[-1] == "runner_exit"
    assert rig.ledger()[-1]["exit_code"] == 0, rig.log()
    rep = json.loads((td / "report.json").read_text())
    assert rep["surfaces"]["listing"]["ok"] and rep["dry_run"] is True
    assert any(a["key"].startswith("rules:broomva/skills") for a in rep["asks"])
    assert "intent" in kinds and len(rig.calls("osascript")) == 1 and len(rig.calls("p9")) == 1
    assert "fleet broomva" in rig.calls("osascript")[0]
    assert (sd / "asks" / "00001.md").is_file()


def test_the_fleet_token_reaches_gh_through_the_environment_and_nowhere_else(rig):
    rig.tick()
    lengths = set(rig.calls("gh-token-lengths"))
    assert lengths == {str(len(TOKEN))}
    sd = rig.world.state["broomva"]
    for p in sd.rglob("*"):
        if p.is_file():
            assert TOKEN not in p.read_text(errors="replace"), p
    assert "gh: fleet token file" in rig.log()


def test_without_a_token_file_gh_falls_back_to_the_keyring(rig):
    rig.token_file.unlink()
    rig.tick()
    assert set(rig.calls("gh-token-lengths")) == {"0"}
    assert "token file" in rig.log() and "unreadable" in rig.log()


def test_the_kill_switch_stops_the_tick_before_anything_fires(rig):
    rig.world.write_config(dispatch_enabled=0)
    rig.tick()
    rig.tick()
    sd = rig.world.state["broomva"]
    assert not (sd / "tick-counter").exists() and rig.ledger() == []
    assert rig.calls("gh-token-lengths") == [] and rig.calls("osascript") == []
    assert rig.log().count("DISABLED") == 1  # noted once, not every hour


@pytest.mark.parametrize("bad", ["not json", json.dumps({"v": 1, "scopes": {"broomva": {"dispatch_enabled": 1,
                                                                                         "surprise": 1}}})])
def test_an_unreadable_or_invalid_config_stops_the_tick(rig, bad):
    rig.world.config.write_text(bad)
    rig.tick()
    assert rig.ledger() == [] and rig.calls("gh-token-lengths") == []


@pytest.mark.parametrize("cfg_dry,env_dry,expected", [(1, None, True), (0, None, False), (0, "1", True),
                                                      (1, "0", True), (0, "yes", True)])
def test_dry_run_falls_toward_dry(rig, cfg_dry, env_dry, expected):
    rig.world.write_config(dry_run=cfg_dry, gh_token_file=str(rig.token_file))
    rig.tick(**({"DRY_RUN": env_dry} if env_dry is not None else {}))
    fire = [x for x in rig.ledger() if x["kind"] == "tick_fire"][0]
    assert fire["dry_run"] is expected


def test_a_live_lock_skips_the_tick_and_a_stale_one_is_reclaimed(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    lock = sd / ".tick.lock"
    lock.mkdir()
    (lock / "pid").write_text(str(os.getpid()))  # this test process: alive
    rig.tick()
    assert "still running" in rig.log() and not (sd / "tick-counter").exists()
    dead = subprocess.Popen(["true"])
    dead.wait()
    (lock / "pid").write_text(str(dead.pid))
    old = time.time() - 600
    os.utime(lock, (old, old))
    rig.tick()
    assert "reclaimed a stale lock" in rig.log() and (sd / "tick-counter").read_text().strip() == "1"
    assert not lock.exists()


def test_the_recursion_guard_exits_before_anything(rig):
    rig.tick(FLEET_CHILD="1")
    assert rig.ledger() == [] and rig.log() == ""


def test_a_hung_step_is_stopped_by_the_watchdog(rig):
    t0 = time.monotonic()
    rig.tick(FLEET_TICK_TIMEOUT_S="3", STUB_HANG="1")
    assert time.monotonic() - t0 < 25
    assert "over the tick's budget: sent TERM" in rig.log()
    assert rig.ledger()[-1]["kind"] == "runner_exit" and rig.ledger()[-1]["exit_code"] == 1
    assert not (rig.world.state["broomva"] / ".tick.lock").exists()


def test_a_second_tick_does_not_renotify_an_unchanged_batch_within_six_hours(rig):
    rig.tick()
    first = len(rig.calls("osascript"))
    rig.tick()
    assert first == 1 and len(rig.calls("osascript")) == 1
    assert "not notified" in rig.log()


def test_the_owner_reads_and_acks_asks_and_other_verbs_refuse(rig):
    rig.tick()
    asks = rig.fleet("asks")
    assert asks.returncode == 0
    assert "tick 1" in asks.stdout and "[a1]" in asks.stdout
    assert rig.fleet("ack", "1", "--ask", "zz").returncode == 1
    assert rig.fleet("ack", "1").returncode == 0
    assert "no unacknowledged" in rig.fleet("asks").stdout
    assert any(x["kind"] == "ack" for x in rig.ledger())
    for verb in ("mail", "spawn", "label", "resume"):
        out = rig.fleet("act", verb)
        assert out.returncode == 3 and "refused" in out.stderr


def test_three_ticks_make_a_labelling_sheet(rig):
    for _ in range(3):
        rig.tick()
    out = rig.fleet("label-sheet", "--ticks", "1,2,3")
    assert out.returncode == 0, out.stderr
    md, csv_ = out.stdout.split()
    assert Path(md).is_file() and Path(csv_).read_text().startswith("row,tick,session")
