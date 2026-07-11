"""Integration tests — drive the real scheduler (tick.sh) against a fixture
queue and assert its DETERMINISTIC routing (mode decision, kill switch, in-flight
gate) with a spawnless governor (GAL_CLAUDE_BIN=echo, zero side effects).

The governor's *judgment* (reconcile/dispatch selection) is latent and lives in
the runner-prompt (covered by resolver + scenario evals, not here). What is
deterministic — and therefore tested here — is the scheduler that wraps it:
does an outer tick fire, does the kill switch fail closed, does an inner resume
tick fire iff work is in flight.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_TICK = _REPO / "scripts" / "tick.sh"

# A fixture config that is always in the active window (so the hour the test runs
# never trips quiet-hours) and has the inner resume loop armed.
_ACTIVE_ALWAYS = "ACTIVE_START=0\nACTIVE_END=24\nRESUME_ENABLED=1\n"


def _run_tick(state_dir: Path, env_extra: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "GAL_STATE_DIR": str(state_dir),
        "GAL_CLAUDE_BIN": "echo",           # spawnless governor
        "GAL_REPO": str(_REPO),
    })
    env.update(env_extra)
    return subprocess.run(["bash", str(_TICK)], env=env, capture_output=True, text=True)


def _seed_config(state_dir: Path, body: str):
    """Pre-seed a live config.env (+ .seeded stamp) so tick.sh loads it directly."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "config.env").write_text("DISPATCH_ENABLED=1\nDRY_RUN=1\n" + body)
    (state_dir / ".seeded").touch()


def _records(state_dir: Path) -> list[dict]:
    log = state_dir / "loop-log.jsonl"
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text().splitlines() if x.strip()]


def test_force_fires_outer_tick(tmp_path):
    sd = tmp_path / "state"
    _seed_config(sd, _ACTIVE_ALWAYS)
    proc = _run_tick(sd, {"DRY_RUN": "1", "FORCE": "1"})
    assert proc.returncode == 0, proc.stderr
    actions = [(r["action"], r.get("mode")) for r in _records(sd)]
    assert ("tick_fire", "outer") in actions
    assert any(a == "runner_exit" for a, _ in actions)


def test_force_run_does_not_persist_schedule(tmp_path):
    # A FORCE validation run must leave the durable schedule alone.
    sd = tmp_path / "state"
    _seed_config(sd, _ACTIVE_ALWAYS)
    _run_tick(sd, {"DRY_RUN": "1", "FORCE": "1"})
    assert not (sd / "next-fire-at").exists()


def test_kill_switch_fails_closed(tmp_path):
    sd = tmp_path / "state"
    sd.mkdir(parents=True)
    (sd / "config.env").write_text("DISPATCH_ENABLED=0\nDRY_RUN=1\n" + _ACTIVE_ALWAYS)
    (sd / ".seeded").touch()
    proc = _run_tick(sd, {"FORCE": "1"})  # FORCE must NOT bypass the kill switch
    assert proc.returncode == 0
    assert _records(sd) == []  # nothing fired


def test_corrupt_kill_switch_fails_closed(tmp_path):
    sd = tmp_path / "state"
    sd.mkdir(parents=True)
    (sd / "config.env").write_text("DISPATCH_ENABLED = 0\nDRY_RUN=1\n" + _ACTIVE_ALWAYS)
    (sd / ".seeded").touch()
    proc = _run_tick(sd, {"FORCE": "1"})
    assert proc.returncode == 0
    assert _records(sd) == []


def test_missing_config_after_seed_fails_closed(tmp_path):
    # .seeded present but config removed => operator removed it => DISABLED.
    sd = tmp_path / "state"
    sd.mkdir(parents=True)
    (sd / ".seeded").touch()
    proc = _run_tick(sd, {"FORCE": "1"})
    assert proc.returncode == 0
    assert _records(sd) == []


def test_inner_tick_fires_only_with_work_in_flight(tmp_path):
    sd = tmp_path / "state"
    _seed_config(sd, _ACTIVE_ALWAYS)
    # Outer fire is in the future; inner is due. A fixture in-flight dispatch.
    (sd / "next-fire-at").write_text("9999999999")
    (sd / "loop-log.jsonl").write_text(
        json.dumps({"action": "dispatch", "ticket": "BRO-1", "dry_run": False}) + "\n")
    proc = _run_tick(sd, {})  # no FORCE => the mode decision runs
    assert proc.returncode == 0
    modes = [r.get("mode") for r in _records(sd) if r["action"] == "tick_fire"]
    assert "inner" in modes


def test_inner_tick_skipped_when_nothing_in_flight(tmp_path):
    sd = tmp_path / "state"
    _seed_config(sd, _ACTIVE_ALWAYS)
    (sd / "next-fire-at").write_text("9999999999")
    # in-flight dispatch then reconciled => 0 in flight => no governor spawn.
    (sd / "loop-log.jsonl").write_text(
        json.dumps({"action": "dispatch", "ticket": "BRO-1"}) + "\n" +
        json.dumps({"action": "reconcile_done", "ticket": "BRO-1"}) + "\n")
    proc = _run_tick(sd, {})
    assert proc.returncode == 0
    # only the pre-existing 2 fixture records; no new tick_fire appended.
    assert not any(r["action"] == "tick_fire" for r in _records(sd))


def test_recursion_guard_exits_immediately(tmp_path):
    sd = tmp_path / "state"
    _seed_config(sd, _ACTIVE_ALWAYS)
    proc = _run_tick(sd, {"GAL_CHILD": "1", "FORCE": "1"})
    assert proc.returncode == 0
    assert _records(sd) == []  # a child never re-enters the tick


def test_dry_run_fails_closed_when_denylist_missing(tmp_path):
    # P20 #1: DRY_RUN=1 with an unassemblable denylist must FAIL CLOSED (no fire),
    # never spawn a dry governor with the mechanical write-block silently dropped.
    sd = tmp_path / "state"
    _seed_config(sd, _ACTIVE_ALWAYS)
    proc = _run_tick(sd, {
        "DRY_RUN": "1", "FORCE": "1",
        "GAL_DENYLIST_FILE": str(tmp_path / "does-not-exist.json"),
    })
    assert proc.returncode == 0
    assert _records(sd) == []  # nothing fired — failed closed


def test_dry_run_fails_closed_when_denylist_empty(tmp_path):
    sd = tmp_path / "state"
    _seed_config(sd, _ACTIVE_ALWAYS)
    empty = tmp_path / "empty-denylist.json"
    empty.write_text(json.dumps({"governor_dry_denylist": []}))
    proc = _run_tick(sd, {"DRY_RUN": "1", "FORCE": "1", "GAL_DENYLIST_FILE": str(empty)})
    assert proc.returncode == 0
    assert _records(sd) == []  # empty write-surface => fail closed


def test_dry_run_fires_with_valid_denylist(tmp_path):
    # The positive control: a valid denylist DOES fire and injects the flags.
    sd = tmp_path / "state"
    _seed_config(sd, _ACTIVE_ALWAYS)
    dl = tmp_path / "denylist.json"
    dl.write_text(json.dumps({"governor_dry_denylist": ["mcp__t__save_x", "mcp__t__save_y"]}))
    proc = _run_tick(sd, {"DRY_RUN": "1", "FORCE": "1", "GAL_DENYLIST_FILE": str(dl)})
    assert proc.returncode == 0
    assert any(r["action"] == "tick_fire" for r in _records(sd))
    assert "disallowedTools" in (sd / "tick.log").read_text()


def test_partition_seed_guard_refuses_wrong_template(tmp_path):
    # A -life state dir must refuse a non-life template (double-dispatch footgun).
    sd = tmp_path / "loop-life"          # basename ends with -life
    tpl = _REPO / "templates" / "config.env.template"  # generic, no 'life'
    proc = _run_tick(sd, {
        "GAL_PARTITION_TAG": "life",
        "GAL_CONFIG_TEMPLATE": str(tpl),
        "FORCE": "1",
    })
    assert proc.returncode == 0
    assert not (sd / "config.env").exists()  # refused to seed
    assert _records(sd) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
