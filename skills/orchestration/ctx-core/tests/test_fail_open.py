"""Injection fails open: whatever goes wrong inside a hook, it exits 0 and
prints nothing, so the session carries on as if the hook were not there.

The wrapper is exercised against deliberately broken ctx modules, copied next
to it in a scratch dir: one that fails to import, one that raises, one that
prints and raises, one that hangs, one that is sent SIGTERM (Claude Code's own
timeout). Then the real module against hostile input.
"""
from __future__ import annotations

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
