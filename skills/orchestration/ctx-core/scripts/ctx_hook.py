#!/usr/bin/env python3
"""Claude Code hook entry for ctx: SessionStart, Stop and StopFailure.

    python3 -I /path/to/ctx_hook.py session-start   < hook JSON on stdin
    python3 -I /path/to/ctx_hook.py stop
    python3 -I /path/to/ctx_hook.py stop-failure

The contract holds for every event, whatever ctx.py does:

  * Exit status 0, always. SIGALRM (the self-deadline) and SIGTERM (Claude
    Code's own timeout) both end the process with 0.
  * Nothing on stdout except one complete JSON object, written in a single
    step after the work is done and the deadline timer is off. Anything ctx.py
    prints, and every traceback, goes to /dev/null. Injection fails OPEN: a
    failed or late hook injects nothing, and the session carries on.
  * A hard self-deadline of BUDGET_S of wall time inside the interpreter.
    Interpreter start-up and teardown are the rest of the 200 ms.
    CTX_HOOK_BUDGET_MS overrides it for tests of behaviour on a loaded machine;
    the registered hooks leave it unset.

`-I` keeps a module planted in the session's cwd, or in user site-packages,
from being imported in place of the stdlib; this script adds only its own
directory to sys.path, for ctx.py. SIGKILL cannot be caught. A writer killed
mid-append leaves at most one torn line, which ctx.py skips and heals.
"""

import os
import signal
import sys
import time

_T0 = time.monotonic()
#: 120 ms inside the interpreter leaves 80 ms of the 200 ms wall for start-up
#: and teardown, which a loaded machine or a slow Python can need.
BUDGET_S = 0.120
STDIN_CAP = 1 << 20


def _budget():
    try:
        return min(max(int(os.environ["CTX_HOOK_BUDGET_MS"]), 1), 10000) / 1000.0
    except (KeyError, ValueError):
        return BUDGET_S


def _bail(signum=None, frame=None):
    ctx = sys.modules.get("ctx")
    if ctx is not None:
        try:
            ctx.kill_child()
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
    try:
        signal.signal(signal.SIGALRM, _bail)
        signal.signal(signal.SIGTERM, _bail)
        budget = _budget()
        signal.setitimer(signal.ITIMER_REAL, max(0.001, budget - (time.monotonic() - _T0)))
        devnull = open(os.devnull, "w")
        sys.stdout = sys.stderr = devnull
        event = argv[1] if len(argv) > 1 else ""
        raw = _read_stdin()
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        import ctx  # noqa: E402  (after the guards, so an import failure is caught too)

        out = ctx.run_hook(event, raw, deadline=_T0 + budget)
        signal.setitimer(signal.ITIMER_REAL, 0)
        if out:
            data = out.encode("utf-8")
            while data:
                data = data[os.write(1, data):]
    except BaseException:
        pass
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv)
