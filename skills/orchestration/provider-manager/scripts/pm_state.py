"""pm_state.py — machine-wide coordination for provider-manager.

- `balancer_lock`: one flock for the whole machine. Hooks in N sessions can each ask for an
  evaluation, but only the holder evaluates or switches. Reentrant within a process.
- State (JSON, short lock): last evaluation, last switch (the cooldown), a manual hold, pending
  rate-limit reports, per-account telemetry backoff and health, probe results.
- Event log (JSONL): every decision and switch, with trace_id/run_id and the caller.
- Stalled sessions (JSONL): turns that a StopFailure hook reported, for resume.
"""

import contextvars
import fcntl
import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

RUN_ID = uuid.uuid4().hex[:12]
_TRACE: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("pm_trace", default=None)
_LOCK_DEPTH = 0


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.tmp.%d" % (path.name, os.getpid()))
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# -- the one balancer -----------------------------------------------------------------------------

@contextmanager
def balancer_lock(path: Path, blocking: bool = False, timeout: float = 30.0, holder: str = "") -> Iterator[bool]:
    """Yield True while holding the machine-wide balancer lock, False if another process has it."""
    global _LOCK_DEPTH
    if _LOCK_DEPTH:
        _LOCK_DEPTH += 1
        try:
            yield True
        finally:
            _LOCK_DEPTH -= 1
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    deadline = time.monotonic() + (timeout if blocking else 0.0)
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                f.close()
                yield False
                return
            time.sleep(0.1)
    try:
        f.seek(0)
        f.truncate()
        f.write(json.dumps({"pid": os.getpid(), "since": time.time(), "holder": holder, "run_id": RUN_ID}))
        f.flush()
        _LOCK_DEPTH = 1
        yield True
    finally:
        _LOCK_DEPTH = 0
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def lock_holder(path: Path) -> Optional[Dict[str, Any]]:
    """Who holds the balancer lock right now, or None."""
    path = Path(path)
    if not path.exists():
        return None
    with open(path, "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            try:
                return json.loads(f.read() or "{}")
            except ValueError:
                return {"pid": None}
        fcntl.flock(f, fcntl.LOCK_UN)
    return None


# -- state ----------------------------------------------------------------------------------------

def _empty_state() -> Dict[str, Any]:
    return {
        "lastEvalAt": 0.0,
        "lastKickAt": 0.0,
        "lastSwitch": None,
        "holdUntil": 0.0,
        "pendingSignals": [],
        "telemetry": {},
        "health": {},
        "probes": {},
        "storeIdentity": None,
    }


def load_state(path: Path) -> Dict[str, Any]:
    state = _empty_state()
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            state.update(loaded)
    except (OSError, ValueError):
        pass
    return state


def update_state(path: Path, fn: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
    """Read-modify-write the state under a short lock of its own (never the balancer lock, which an
    evaluation can hold for a minute while it probes)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = load_state(path)
            fn(state)
            _atomic_write(path, json.dumps(state, indent=2))
            return state
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


# -- events ---------------------------------------------------------------------------------------

@contextmanager
def trace() -> Iterator[str]:
    tid = _TRACE.get()
    if tid:
        yield tid
        return
    tid = uuid.uuid4().hex[:16]
    token = _TRACE.set(tid)
    try:
        yield tid
    finally:
        _TRACE.reset(token)


def log_event(path: Path, event: str, details: Optional[Dict[str, Any]] = None) -> None:
    record = {
        "timestamp": int(time.time()),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "trace_id": _TRACE.get(),
        "run_id": RUN_ID,
        "pid": os.getpid(),
        "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"),
    }
    record.update(details or {})
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass


def read_events(path: Path, limit: int = 20, kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if kinds is None or e.get("event") in kinds:
                    out.append(e)
    except OSError:
        return []
    return out[-limit:]


# -- stalled sessions -----------------------------------------------------------------------------

def record_stalled(path: Path, payload: Dict[str, Any], env: Dict[str, str]) -> Dict[str, Any]:
    entry = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sessionId": payload.get("session_id"),
        "cwd": payload.get("cwd"),
        "transcriptPath": payload.get("transcript_path"),
        "error": payload.get("error"),
        "errorDetails": str(payload.get("error_details") or "")[:300],
        "paseoAgentId": env.get("PASEO_AGENT_ID"),
    }
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return entry


def list_stalled(path: Path, since_ts: float) -> List[Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("ts", 0) >= since_ts:
                    latest[e.get("sessionId") or "?%s" % e.get("ts")] = e
    except OSError:
        return []
    return sorted(latest.values(), key=lambda e: e.get("ts", 0))


# -- detached work --------------------------------------------------------------------------------

def spawn_detached(argv: List[str], env: Optional[Dict[str, str]] = None) -> Optional[int]:
    """Start argv in its own session, detached from the hook (which must return at once)."""
    try:
        p = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        return p.pid
    except OSError:
        return None
