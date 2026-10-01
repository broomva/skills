"""Injection fails open: whatever goes wrong inside a hook, it exits 0 and
prints nothing, so the session carries on as if the hook were not there.

The wrapper is exercised against deliberately broken ctx modules, copied next
to it in a scratch dir: one that fails to import, one that raises, one that
prints and raises, one that hangs, one that is sent SIGTERM (Claude Code's own
timeout). Then the real module against hostile input.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import HOOK, HOOK_WALL_S, World

BROKEN = {
    "import-error": "raise RuntimeError('broken at import')\n",
    "syntax-error": "def run_hook(:\n",
    "raises": "def run_hook(event, raw, deadline):\n    raise ValueError('boom')\n",
    "prints-then-raises": (
        "import sys\n"
        "def run_hook(event, raw, deadline):\n"
        "    print('{\"hookSpecificOutput\": {\"additionalContext\": \"half')\n"
        "    sys.stderr.write('Traceback: noise\\n')\n"
        "    raise KeyError('x')\n"),
    "prints-returns-empty": "def run_hook(event, raw, deadline):\n    print('stray')\n    return ''\n",
    "hangs": "import time\ndef run_hook(event, raw, deadline):\n    time.sleep(30)\n    return 'late'\n",
    "sigterm": ("import os, signal, time\n"
                "def run_hook(event, raw, deadline):\n"
                "    os.kill(os.getpid(), signal.SIGTERM)\n"
                "    time.sleep(5)\n"
                "    return 'after term'\n"),
    "exits-nonzero": "import sys\ndef run_hook(event, raw, deadline):\n    sys.exit(3)\n",
    "returns-non-string": "def run_hook(event, raw, deadline):\n    return {'not': 'a string'}\n",
}


@pytest.mark.parametrize("kind", sorted(BROKEN))
@pytest.mark.parametrize("event", ["session-start", "stop", "stop-failure"])
def test_a_broken_ctx_module_never_escapes_the_hook(timed: World, tmp_path: Path, kind: str, event: str) -> None:
    d = tmp_path / ("plugin-" + kind)
    d.mkdir()
    shutil.copy2(HOOK, d / "ctx_hook.py")
    (d / "ctx.py").write_text(BROKEN[kind])
    run = timed.hook(event, {"session_id": "s-1", "cwd": str(timed.broomva)}, script=d / "ctx_hook.py")
    assert (run.rc, run.stdout, run.stderr) == (0, "", ""), kind
    assert run.elapsed < HOOK_WALL_S, "%s took %.0f ms" % (kind, run.elapsed * 1000)


@pytest.mark.parametrize("raw", [
    "", "not json", "[1, 2]", "null", '{"session_id": 5}', '{"session_id": "s-1"}',
    '{"session_id": "s-1", "cwd": "relative/path"}', '{"session_id": "../../etc", "cwd": "/"}',
    '{"session_id": "s-1", "cwd": "/nonexistent/dir"}', "\udcff".encode("utf-8", "surrogatepass").decode("latin-1"),
])
def test_hostile_input_is_a_silent_noop(timed: World, raw: str) -> None:
    for event in ("session-start", "stop", "stop-failure", "no-such-event", ""):
        run = timed.hook(event, {}, raw=raw)
        assert (run.rc, run.stdout, run.stderr) == (0, "", ""), (event, raw)
    assert timed.events("broomva") == []


def test_a_malformed_config_is_a_silent_noop(timed: World) -> None:
    (timed.home / ".config" / "ctx" / "scopes.yaml").write_text("scopes:\n\tbroken\n")
    run = timed.start("s-1", timed.broomva)
    assert (run.rc, run.stdout, run.stderr) == (0, "", "")
    (timed.home / ".config" / "ctx" / "scopes.yaml").write_bytes(b"\xff\xfe")
    assert timed.start("s-1", timed.broomva).stdout == ""


def test_an_unwritable_store_is_a_silent_noop(timed: World) -> None:
    state = timed.home / ".local" / "state"
    state.mkdir(parents=True)
    (state / "ctx").write_text("a file where the state dir should be")
    for run in (timed.start("s-1", timed.broomva), timed.stop("s-1", timed.broomva)):
        assert (run.rc, run.stdout, run.stderr) == (0, "", "")


def test_the_stop_hook_never_prints(timed: World) -> None:
    """Stop output is decision control: stray JSON there could block the stop."""
    timed.start("s-1", timed.broomva)
    run = timed.stop("s-2", timed.broomva, "ARC-STATUS: BLOCKED {\"decision\": \"block\"}")
    assert (run.rc, run.stdout) == (0, "")


def test_a_hook_that_runs_out_of_time_leaves_a_breadcrumb(timed: World, tmp_path: Path) -> None:
    """So `ctx doctor` can tell "too slow" from "not registered"."""
    d = tmp_path / "plugin-hangs"
    d.mkdir()
    shutil.copy2(HOOK, d / "ctx_hook.py")
    (d / "ctx.py").write_text(BROKEN["hangs"])
    run = timed.hook("stop", {"session_id": "s-1", "cwd": str(timed.broomva)}, script=d / "ctx_hook.py")
    assert (run.rc, run.stdout) == (0, "")
    misses = (timed.home / ".local" / "state" / "ctx" / "hook-misses.jsonl").read_text().splitlines()
    rec = json.loads(misses[-1])
    assert (rec["event"], rec["stage"]) == ("stop", "run") and set(rec) == {"ts", "event", "stage", "ms"}
    # And doctor reads it when sessions ran but nothing was recorded.
    proj = timed.home / ".claude" / "projects" / "p"
    proj.mkdir(parents=True)
    (proj / "t.jsonl").write_text(json.dumps({"cwd": str(timed.broomva)}) + "\n")
    report = timed.cli("doctor", cwd=timed.broomva)
    assert report.returncode == 1 and "1 hook runs in 24h ran out of time or skipped work, machine-wide" in report.stdout
    assert "by stage: run 1" in report.stdout
    assert "the hooks are running out of time or skipping work (see misses)" in report.stdout


def test_no_breadcrumb_without_a_ctx_config(timed: World, tmp_path: Path) -> None:
    (timed.home / ".config" / "ctx" / "scopes.yaml").unlink()
    d = tmp_path / "plugin-hangs"
    d.mkdir()
    shutil.copy2(HOOK, d / "ctx_hook.py")
    (d / "ctx.py").write_text(BROKEN["hangs"])
    timed.hook("stop", {"session_id": "s-1", "cwd": str(timed.broomva)}, script=d / "ctx_hook.py")
    assert not (timed.home / ".local").exists()


def test_the_misses_log_rotates_instead_of_going_silent(timed: World, tmp_path: Path) -> None:
    state = timed.home / ".local" / "state" / "ctx"
    state.mkdir(parents=True)
    (state / "hook-misses.jsonl").write_text(("x" * 99 + "\n") * 10486)  # just over 1 MiB
    d = tmp_path / "plugin-hangs"
    d.mkdir()
    shutil.copy2(HOOK, d / "ctx_hook.py")
    (d / "ctx.py").write_text(BROKEN["hangs"])
    timed.hook("stop", {"session_id": "s-1", "cwd": str(timed.broomva)}, script=d / "ctx_hook.py")
    assert (state / "hook-misses.jsonl.1").stat().st_size > 1 << 20
    assert json.loads((state / "hook-misses.jsonl").read_text())["stage"] == "run"
