"""System 1 fails open: whatever breaks, the hook exits 0 with nothing on
stdout, and it never waits long. And its latency, measured from outside."""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

import s1_support as S


@pytest.fixture
def gate(world, tmp_path):
    S.write_corpus(world)
    assert S.build(world).returncode == 0
    world.params = S.write_params(tmp_path, S.LOW_FLOORS)
    return world


def _copy_scripts(tmp_path: Path) -> Path:
    dst = tmp_path / "skill" / "scripts"
    shutil.copytree(str(S.SCRIPTS), str(dst), ignore=shutil.ignore_patterns("__pycache__"))
    return dst


@pytest.mark.parametrize("breakage", [
    "raise RuntimeError('import-time failure')\n",
    "import sys\nprint('stray output')\nsys.stdout.write('more')\nraise SystemExit(3)\n",
])
def test_a_module_that_fails_to_import_injects_nothing(gate, tmp_path, breakage):
    scripts = _copy_scripts(tmp_path)
    (scripts / "ctx_s1.py").write_text(breakage)
    r = S.run_s1("pre-edit", S.edit("f1", gate.broomva, gate.broomva / "scripts/gate.py"), gate.params,
                 script=scripts / "ctx_s1_hook.py")
    assert (r.rc, r.stdout) == (0, "")


def test_a_decision_that_raises_injects_nothing(gate, tmp_path):
    scripts = _copy_scripts(tmp_path)
    src = (scripts / "ctx_s1.py").read_text()
    anchor = '    cfg = stage_cfg(stage, params)\n    key_kinds'
    assert anchor in src
    (scripts / "ctx_s1.py").write_text(src.replace(anchor, '    print("junk")\n    1 / 0\n' + anchor, 1))
    r = S.run_s1("pre-edit", S.edit("f2", gate.broomva, gate.broomva / "scripts/gate.py"), gate.params,
                 script=scripts / "ctx_s1_hook.py")
    assert (r.rc, r.stdout) == (0, "")
    misses = gate.home / ".local" / "state" / "ctx" / "hook-misses.jsonl"
    assert "error:ZeroDivisionError" in misses.read_text()  # raised, not silent


@pytest.mark.parametrize("raw", ["", "not json", "[1,2,3]", '{"session_id": 5}', "\xff\xfe" * 1000,
                                 json.dumps({"session_id": "x", "cwd": "relative/path"}),
                                 json.dumps({"session_id": "../../etc", "cwd": "/tmp"}),
                                 "{" + " " * (2 << 20)],
                         ids=["empty", "not-json", "a-list", "bad-session", "bad-utf8", "relative-cwd",
                              "path-session-id", "2mb"])
def test_hostile_stdin(gate, raw):
    r = S.run_s1("pre-edit", {}, gate.params, raw=raw)
    assert (r.rc, r.stdout) == (0, "")


def test_a_corrupt_cache_injects_nothing(gate):
    cur = gate.store("broomva") / "rank-current"
    for p in (cur / "postings").iterdir():
        p.write_text("{not json")
    r = S.run_s1("pre-edit", S.edit("f3", gate.broomva, gate.broomva / "scripts/gate.py"), gate.params)
    assert (r.rc, r.stdout) == (0, "")


def test_a_missing_cache_abstains_and_says_so(world, tmp_path):
    S.write_corpus(world)
    p = S.write_params(tmp_path, S.LOW_FLOORS)
    r = S.run_s1("pre-edit", S.edit("f4", world.broomva, world.broomva / "scripts/gate.py"), p)
    assert (r.rc, r.stdout) == (0, "")
    assert S.decisions(world)[-1]["reason"] == "no-cache"


def test_a_held_session_lock_abstains_quickly(gate):
    # the state file exists once a first event ran; hold its lock as a stuck peer would
    S.run_s1("post-read", S.read("f5", gate.broomva, gate.broomva / "scripts/other.py"), gate.params)
    path = gate.store("broomva") / "s1-sessions" / "f5.lock"
    fd = os.open(str(path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        r = S.run_s1("pre-edit", S.edit("f5", gate.broomva, gate.broomva / "scripts/gate.py"), gate.params)
    finally:
        os.close(fd)
    assert (r.rc, r.stdout) == (0, "")
    assert S.decisions(gate)[-1]["reason"] == "state-busy"
    assert r.elapsed < 2.0


def test_the_self_deadline_exits_0_and_records_a_miss(gate):
    r = S.run_s1("pre-edit", S.edit("f6", gate.broomva, gate.broomva / "scripts/gate.py"), gate.params,
                 budget_ms="1")
    assert (r.rc, r.stdout) == (0, "")
    misses = gate.home / ".local" / "state" / "ctx" / "hook-misses.jsonl"
    assert misses.exists() and '"event":"s1-pre-edit"' in misses.read_text()


def test_sigterm_exits_0_with_nothing(gate):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CTX_S1")}
    env.update(CTX_S1="1", CTX_S1_STAGES="pre-edit", CTX_PYTHON=sys.executable, CTX_S1_BUDGET_MS="10000")
    p = subprocess.Popen(["/bin/sh", str(S.S1_WRAPPER), "pre-edit"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, env=env)
    time.sleep(0.5)  # the hook is blocked reading a stdin that never closes
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=10)
    p.stdin.close() if p.stdin and not p.stdin.closed else None
    assert (p.returncode, out) == (0, b"")


def test_the_wrapper_exits_0_when_the_hook_or_interpreter_is_gone(gate, tmp_path):
    scripts = _copy_scripts(tmp_path)
    (scripts / "ctx_s1_hook.py").unlink()
    env = {"PATH": os.environ["PATH"], "HOME": str(gate.home), "CTX_S1": "1", "CTX_S1_STAGES": "all",
           "CTX_PYTHON": sys.executable}
    data = json.dumps(S.edit("f7", gate.broomva, gate.broomva / "scripts/gate.py")).encode()
    r = subprocess.run(["/bin/sh", str(scripts / "ctx-s1-hook.sh"), "pre-edit"], input=data, env=env,
                       capture_output=True)
    assert (r.returncode, r.stdout) == (0, b"")
    env["CTX_PYTHON"] = "/nonexistent/python3"
    r = subprocess.run(["/bin/sh", str(S.S1_WRAPPER), "pre-edit"], input=data, env=env, capture_output=True)
    assert (r.returncode, r.stdout) == (0, b"")
    not_exec = tmp_path / "python3-not-executable"
    not_exec.write_text("#!/bin/sh\n")  # there, but not executable: exec would exit 126
    env["CTX_PYTHON"] = str(not_exec)
    r = subprocess.run(["/bin/sh", str(S.S1_WRAPPER), "pre-edit"], input=data, env=env, capture_output=True)
    assert (r.returncode, r.stdout) == (0, b"")
    # positive control: without the wrapper's check, Python on a missing file exits 2
    r = subprocess.run([sys.executable, "-I", "-S", str(scripts / "ctx_s1_hook.py"), "pre-edit"], input=data,
                       capture_output=True)
    assert r.returncode == 2
    # and if the script vanishes after the shell's check, the loader exits 0
    # rather than Python's 2 (exit 2 from PreToolUse would block the edit):
    # the loader is given a path that does not exist, as a race would leave it
    loader = S.S1_WRAPPER.read_text().split("-c '", 1)[1].split("' \"$hook\"", 1)[0]
    r = subprocess.run([sys.executable, "-I", "-S", "-c", loader, str(tmp_path / "gone.py"), "pre-edit"],
                       input=data, capture_output=True)
    assert (r.returncode, r.stdout) == (0, b"")
    half = tmp_path / "half.py"
    half.write_text("def main(:\n")  # a half-written file: does not compile
    r = subprocess.run([sys.executable, "-I", "-S", "-c", loader, str(half), "pre-edit"], input=data,
                       capture_output=True)
    assert (r.returncode, r.stdout) == (0, b"")


# --------------------------------------------------------------------------
# Latency, from outside the process. The owner's machine numbers are in the
# PR; CI runners start Python slower (ctx_hook.py: ~110 ms on a macOS runner),
# so these bounds are the ctx-core hooks' 200 ms wall, not the 100 ms budget.

WALL_S = 0.200


def test_an_off_stage_costs_one_shell(gate, tmp_path):
    marker = tmp_path / "python-ran"
    fake = tmp_path / "fake-python"
    fake.write_text("#!/bin/sh\ntouch %s\nexit 0\n" % marker)
    fake.chmod(0o755)
    ts = []
    for i, env in enumerate([{}, {"CTX_S1": "1", "CTX_S1_STAGES": "prompt,post-read"}, {"CTX_S1": "0"},
                             {"CTX_S1": "0", "CTX_S1_STAGES": "pre-edit"}, {"CTX_S1_STAGES": "all"}]):
        env = dict(env, CTX_PYTHON=str(fake))
        r = S.run_s1("pre-edit", S.edit("l%d" % i, gate.broomva, gate.broomva / "scripts/gate.py"), gate.params,
                     on=False, env=env)
        ts.append(r.elapsed)
        assert (r.rc, r.stdout) == (0, "")
    assert not marker.exists()  # the wrapper decided without starting any interpreter
    assert statistics.median(ts) < 0.1
    # positive control: when the stage is on, the wrapper does start it
    S.run_s1("pre-edit", S.edit("l9", gate.broomva, gate.broomva / "scripts/gate.py"), gate.params,
             env={"CTX_PYTHON": str(fake)})
    assert marker.exists()


@pytest.mark.parametrize("stage,payload", [
    ("pre-edit", lambda w, i: S.edit("l%d" % i, w.broomva, w.broomva / "scripts/gate.py")),
    ("post-read", lambda w, i: S.read("l%d" % i, w.broomva, w.broomva / "scripts/gate.py")),
    ("post-bash", lambda w, i: S.bash("l%d" % i, w.broomva, "sed -n 1,5p scripts/gate.py")),
    ("prompt", lambda w, i: S.prompt("l%d" % i, w.broomva, "why does the zebrafish gate refuse writes %d" % i)),
])
def test_an_on_stage_meets_the_wall_bound(gate, stage, payload):
    ts, ms = [], []
    for i in range(15):
        r = S.run_s1(stage, payload(gate, i), gate.params, budget_ms=None)
        assert r.rc == 0
        ts.append(r.elapsed)
    ms = [d["ms"] for d in S.decisions(gate) if d["stage"] == stage]
    assert statistics.median(ts) < WALL_S, ts
    # the decision itself, inside the interpreter: well inside the tool stages' 70 ms self-deadline
    assert statistics.median(ms) < 35, ms
