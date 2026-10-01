#!/usr/bin/env python3
"""Claude Code hook entry for ctx: SessionStart, Stop and StopFailure.

    /bin/sh /path/to/ctx-hook.sh session-start   < hook JSON on stdin
    /bin/sh /path/to/ctx-hook.sh stop
    /bin/sh /path/to/ctx-hook.sh stop-failure

ctx-hook.sh execs `python3 -I -S` on this file only if it exists; otherwise it
exits 0 (a Python asked to run a missing file exits 2, which would keep a Stop
hook's session turning).

The contract holds for every event, whatever ctx.py does:

  * Exit status 0, always. SIGALRM (the self-deadline) and SIGTERM (Claude
    Code's own timeout) both end the process with 0.
  * Nothing on stdout except one complete JSON object, written after the work
    is done, with the deadline timer off and SIGTERM ignored. Anything ctx.py
    prints, and every traceback, goes to /dev/null. Injection fails OPEN: a
    failed or late hook injects nothing, and the session carries on.
  * A hard self-deadline of BUDGET_S of wall time inside the interpreter.
    Interpreter start-up and teardown are the rest of the 200 ms: about 20 ms
    on the owner's machine. A hosted macOS CI runner is slower on both sides:
    start-up p99 near 120 ms with rare spikes past 500 ms, and its clamped QoS
    lets macOS fire the alarm up to 160 ms late (tests/conftest.py bounds a run
    that hits the deadline from these numbers). The alarm fires between
    bytecodes, so one long C call can delay it. The one such call that grows,
    the board.json parse, is capped (ctx.HOOK_BOARD_CAP), so the deadline stays
    hard.
  * A run that hits the deadline, or finishes but had to skip work (a busy
    lock, a board over its cap, a cache too far behind), appends one line to
    ~/.local/state/ctx/hook-misses.jsonl (time, event, stage, ms; no path),
    but only when ~/.config/ctx/scopes.yaml exists. The file is rotated to .1
    at 1 MiB. That is how `ctx doctor` tells "too slow under load" from "not
    registered". A deadline miss is the one write a hook can make before it
    knows the session's scope.

CTX_HOOK_BUDGET_MS overrides the budget for tests of behaviour on a loaded
machine; the registered hooks leave it unset.

`-I` keeps a module planted in the session's cwd, or in user site-packages,
from being imported in place of the stdlib; this script adds only its own
directory to sys.path, for ctx.py. `-S` skips the `site` import, a third of
interpreter start-up; everything here is stdlib. SIGKILL cannot be caught. A writer killed
mid-append leaves at most one torn line, which ctx.py skips and heals.
"""

import os
import signal
import sys
import time

_T0 = time.monotonic()
#: 80 ms inside the interpreter leaves 120 ms of the 200 ms wall for start-up
#: and teardown.
BUDGET_S = 0.080
STDIN_CAP = 1 << 20
MISS_LOG_CAP = 1 << 20
EVENTS = ("session-start", "stop", "stop-failure")
_EVENT = "other"
_STAGE = "start"


def _budget():
    try:
        return min(max(int(os.environ["CTX_HOOK_BUDGET_MS"]), 1), 10000) / 1000.0
    except (KeyError, ValueError):
        return BUDGET_S


def _record_miss(stage):
    home = os.environ.get("HOME") or ""
    if not home or not os.path.isfile(os.path.join(home, ".config", "ctx", "scopes.yaml")):
        return
    d = os.path.join(home, ".local", "state", "ctx")
    path = os.path.join(d, "hook-misses.jsonl")
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        try:
            if os.lstat(path).st_size >= MISS_LOG_CAP:
                os.replace(path, path + ".1")  # rotate; doctor reads both
        except FileNotFoundError:
            pass
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.write(fd, ('{"ts":%.3f,"event":"%s","stage":"%s","ms":%d}\n' % (
                time.time(), _EVENT, stage, (time.monotonic() - _T0) * 1000)).encode())
        finally:
            os.close(fd)
    except OSError:
        pass


def _bail(signum=None, frame=None):
    ctx = sys.modules.get("ctx")
    try:
        ctx.on_deadline()  # kill a hung git, remove a half-written temp file
    except BaseException:
        pass
    try:
        stage = getattr(ctx, "STAGE", None) or _STAGE
        _record_miss(("sigterm:" if signum == signal.SIGTERM else "") + str(stage))
    except BaseException:
        pass
    os._exit(0)


def _read_stdin():
    chunks, total = [], 0
    while total < STDIN_CAP:
        chunk = os.read(0, 65536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks).decode("utf-8", "replace")


def main(argv):
    global _EVENT, _STAGE
    try:
        signal.signal(signal.SIGALRM, _bail)
        signal.signal(signal.SIGTERM, _bail)
        budget = _budget()
        signal.setitimer(signal.ITIMER_REAL, max(0.001, budget - (time.monotonic() - _T0)))
        devnull = open(os.devnull, "w")
        sys.stdout = sys.stderr = devnull
        event = argv[1] if len(argv) > 1 else ""
        _EVENT = event if event in EVENTS else "other"
        _STAGE = "stdin"
        raw = _read_stdin()
        _STAGE = "import"
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        import ctx  # noqa: E402  (after the guards, so an import failure is caught too)

        _STAGE = "run"

        out = ctx.run_hook(event, raw, deadline=_T0 + budget)
        signal.setitimer(signal.ITIMER_REAL, 0)
        if getattr(ctx, "MISSED", None):
            _record_miss(str(ctx.MISSED))
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # the write below is not interrupted
        if out:
            data = out.encode("utf-8")
            while data:
                data = data[os.write(1, data):]
    except BaseException:
        pass
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv)
