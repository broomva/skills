#!/usr/bin/env python3
"""Claude Code hook entry for the ctx System 1 gate, one stage per registration.

    /bin/sh /path/to/ctx-s1-hook.sh <stage>     < hook JSON on stdin

Stages: session-start, compact, prompt, pre-edit, post-read, post-bash,
subagent, post-compact (see ctx_s1.STAGES). ctx-s1-hook.sh checks the flags
(CTX_S1=1 and the stage in CTX_S1_STAGES) before it starts Python, so a stage
that is off costs one /bin/sh.

The contract, whatever ctx_s1 does, the same as ctx_hook.py's:
  * exit status 0, always; SIGALRM (the self-deadline) and SIGTERM end the
    process with 0;
  * nothing on stdout except one complete JSON object, written after the work
    is done, with the timer off and SIGTERM ignored; tracebacks go to
    /dev/null. Injection fails OPEN: a failed or late hook injects nothing;
  * a self-deadline per stage inside the interpreter (ctx_s1.STAGES
    `deadline_ms`: 70 ms for the tool stages, whose whole budget is 100 ms);
  * a run that hits the deadline appends one line to hook-misses.jsonl (event
    `s1-<stage>`), the file ctx doctor already reads.

CTX_S1_BUDGET_MS overrides the self-deadline for tests.
"""

import os
import signal
import sys
import time

_T0 = time.monotonic()
STDIN_CAP = 1 << 20
MISS_LOG_CAP = 1 << 20
_STAGE = "start"
_EVENT = "s1-other"


def _budget(stage_ms):
    try:
        return min(max(int(os.environ["CTX_S1_BUDGET_MS"]), 1), 10000) / 1000.0
    except (KeyError, ValueError):
        return stage_ms / 1000.0


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
                os.replace(path, path + ".1")
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
        ctx.on_deadline()
    except BaseException:
        pass
    try:
        s1 = sys.modules.get("ctx_s1")
        stage = getattr(s1, "STAGE", None) or _STAGE
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


#: Per-stage self-deadlines, kept here so the timer is armed before any import.
_DEADLINES_MS = {"pre-edit": 70, "post-read": 70, "post-bash": 70, "subagent": 150,
                 "post-compact": 150, "prompt": 300, "session-start": 300, "compact": 300}


def _emit(out):
    """Write the hook's output whole, before the log line: the timer and
    SIGTERM are held off for the write, so neither cuts the JSON in half (a
    SIGKILL still can), then the timer is re-armed for whatever time is left."""
    left = signal.setitimer(signal.ITIMER_REAL, 0)[0]
    old = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    data = out.encode("utf-8")
    while data:
        data = data[os.write(1, data):]
    if left <= 0:
        os._exit(0)
    signal.signal(signal.SIGTERM, old)
    signal.setitimer(signal.ITIMER_REAL, left)


def main(argv):
    global _STAGE, _EVENT
    try:
        signal.signal(signal.SIGALRM, _bail)
        signal.signal(signal.SIGTERM, _bail)
        stage = argv[1] if len(argv) > 1 else ""
        _EVENT = "s1-" + stage if stage in _DEADLINES_MS else "s1-other"
        budget = _budget(_DEADLINES_MS.get(stage, 70))
        signal.setitimer(signal.ITIMER_REAL, max(0.001, budget - (time.monotonic() - _T0)))
        devnull = open(os.devnull, "w")
        sys.stdout = sys.stderr = devnull
        _STAGE = "stdin"
        raw = _read_stdin()
        _STAGE = "import"
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        import ctx_s1  # noqa: E402

        _STAGE = "run"
        ctx_s1.run_stage(stage, raw, deadline=_T0 + budget, emit=_emit)
    except BaseException as exc:
        # fail open, but leave the same breadcrumb a deadline miss leaves, so
        # `ctx doctor` can tell "raised" from "never ran"
        try:
            s1 = sys.modules.get("ctx_s1")
            _record_miss("error:%s:%s" % (type(exc).__name__[:40], getattr(s1, "STAGE", None) or _STAGE))
        except BaseException:
            pass
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv)
