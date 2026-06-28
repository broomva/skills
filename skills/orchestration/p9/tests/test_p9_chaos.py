"""Chaos tests for p9 — fault injection battery.

Each test injects a specific failure mode and asserts the system stays
consistent (no silent drops, fails closed where required, recoverable
otherwise). Mirrors the M7-FINAL chaos pattern used elsewhere in the stack.
"""

from __future__ import annotations

import importlib
import json
import multiprocessing
import os
import signal
import sys
import time
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
_FIXTURES = _HERE / "fixtures"
sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


# ─────────────────────────────────────────────────────────────────────────────
# Chaos #1 — state.jsonl partial write (truncated mid-flush)
# ─────────────────────────────────────────────────────────────────────────────
def test_chaos_state_jsonl_partial_last_line_recovered(p9):
    """Simulates a process crash mid-write: last line is truncated.

    JSONL append-only design must lose at most one event.
    """
    # First, write 3 valid events
    for pr, state in [(1, "WATCHING"), (2, "WATCHING"), (3, "WATCHING")]:
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-04T20:00:00+00:00",
            pr=pr, repo="broomva/x",
            from_state=p9.PRState.PUSHED.value,
            to_state=state,
            watcher_id=f"w{pr}",
        ))
    # Now manually corrupt the last line
    raw = p9.state_jsonl().read_text(encoding="utf-8")
    truncated = raw[:-30] + '{"ts":"par'  # broken trailing JSON
    p9.state_jsonl().write_text(truncated, encoding="utf-8")

    rows, dropped = p9.jsonl_read_all(p9.state_jsonl())
    # We lost the third event entirely (its line was overwritten by the
    # corrupt one), so only 2 valid rows remain + 1 dropped from corruption
    assert dropped == 1
    assert len(rows) >= 2  # at least the first two events survived


# ─────────────────────────────────────────────────────────────────────────────
# Chaos #2 — state.jsonl mid-file corruption (invariant violation)
# ─────────────────────────────────────────────────────────────────────────────
def test_chaos_state_jsonl_mid_file_corruption_raises(p9):
    """Corruption that's NOT on the last line is an invariant violation.

    JSONL append-only contract: only the last line can be partial. Anything
    else means data was tampered with.
    """
    p9.state_jsonl().parent.mkdir(parents=True, exist_ok=True)
    p9.state_jsonl().write_text(
        '{"ts":"a","pr":1}\n'
        '{"corrupted":\n'
        '{"ts":"c","pr":3}\n',
        encoding="utf-8",
    )
    with pytest.raises(p9.IllegalTransitionError):
        p9.jsonl_read_all(p9.state_jsonl())


# ─────────────────────────────────────────────────────────────────────────────
# Chaos #3 — concurrent state writers (flock correctness)
# ─────────────────────────────────────────────────────────────────────────────
def _writer(home: str, policy: str, pr_start: int, count: int):
    """Worker function — appends `count` events with PRs starting at pr_start."""
    os.environ["BROOMVA_P9_HOME"] = home
    os.environ["BROOMVA_P9_POLICY"] = policy
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")
    for i in range(count):
        mod.append_state_event(mod.PRStateEvent(
            ts="2026-05-04T20:00:00+00:00",
            pr=pr_start + i, repo="broomva/x",
            from_state=mod.PRState.PUSHED.value,
            to_state=mod.PRState.WATCHING.value,
            watcher_id=f"w{pr_start + i}",
        ))


def test_chaos_concurrent_writers_no_corruption(p9, tmp_path):
    """5 concurrent processes each appending 10 events. flock must serialize."""
    workers = []
    for i in range(5):
        proc = multiprocessing.Process(
            target=_writer,
            args=(str(tmp_path), str(_FIXTURES / "policy-good.yaml"), 1000 + i * 100, 10),
        )
        workers.append(proc)
        proc.start()
    for w in workers:
        w.join(timeout=30)
        assert w.exitcode == 0, "writer process failed"

    rows, dropped = p9.jsonl_read_all(p9.state_jsonl())
    assert dropped == 0  # no corruption from interleaving
    assert len(rows) == 50  # 5 × 10 events all preserved
    # All distinct PRs
    prs = sorted(r["pr"] for r in rows)
    assert prs == sorted(set(prs))


# ─────────────────────────────────────────────────────────────────────────────
# Chaos #4 — policy.yaml missing required block (fail closed)
# ─────────────────────────────────────────────────────────────────────────────
def test_chaos_policy_missing_block_fails_closed(tmp_path, monkeypatch, capsys):
    """Missing ci_watch: block → exit 2 with no side effects."""
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv(
        "BROOMVA_P9_POLICY",
        str(_FIXTURES / "policy-missing-ci-watch.yaml"),
    )
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")

    rc = mod.main(["watch", "999", "--repo", "broomva/test", "--dry-run"])
    assert rc == mod.EXIT_POLICY_ERROR

    # No state written
    if mod.state_jsonl().exists():
        assert mod.state_jsonl().read_text(encoding="utf-8") == ""


# ─────────────────────────────────────────────────────────────────────────────
# Chaos #5 — heal.lock contention timeout
# ─────────────────────────────────────────────────────────────────────────────
def _lock_holder(home: str, policy: str, ready, hold_seconds: float):
    """Acquire the heal lock and hold it for `hold_seconds`."""
    os.environ["BROOMVA_P9_HOME"] = home
    os.environ["BROOMVA_P9_POLICY"] = policy
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")
    with mod.file_lock(mod.heal_lock_path(), timeout_s=10.0):
        ready.set()
        time.sleep(hold_seconds)


def _lock_challenger(home: str, policy: str, ready, out_q, timeout_s: float):
    """Wait for the holder, then try to grab the lock with a tight timeout."""
    os.environ["BROOMVA_P9_HOME"] = home
    os.environ["BROOMVA_P9_POLICY"] = policy
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")
    ready.wait(timeout=10)
    try:
        with mod.file_lock(mod.heal_lock_path(), timeout_s=timeout_s):
            out_q.put("acquired")
    except mod.P9Error as e:
        out_q.put(f"timeout: {e}")


def test_chaos_heal_lock_timeout(p9, tmp_path):
    """Two competing flock holders. Second should time out cleanly."""
    lock_path = p9.heal_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    ready = multiprocessing.Event()
    out_q = multiprocessing.Queue()
    home = str(tmp_path)
    policy = str(_FIXTURES / "policy-good.yaml")

    h = multiprocessing.Process(
        target=_lock_holder, args=(home, policy, ready, 2.0),
    )
    c = multiprocessing.Process(
        target=_lock_challenger, args=(home, policy, ready, out_q, 0.5),
    )
    h.start()
    c.start()
    c.join(timeout=10)
    h.join(timeout=10)

    result = out_q.get(timeout=2)
    assert result.startswith("timeout"), f"expected timeout, got: {result}"


# ─────────────────────────────────────────────────────────────────────────────
# Chaos #6 — wait-queue write durability under concurrent push
# ─────────────────────────────────────────────────────────────────────────────
def _queue_pusher(home: str, policy: str, source: str, count: int):
    os.environ["BROOMVA_P9_HOME"] = home
    os.environ["BROOMVA_P9_POLICY"] = policy
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")
    for i in range(count):
        mod.queue_push(f"item-{i}", source)


def test_chaos_concurrent_queue_pushes_no_loss(p9, tmp_path):
    """5 concurrent pushers × 10 items = 50 items, no loss."""
    sources = ["session", "memory", "graph", "docs", "linear"]
    workers = []
    for src in sources:
        proc = multiprocessing.Process(
            target=_queue_pusher,
            args=(str(tmp_path), str(_FIXTURES / "policy-good.yaml"), src, 10),
        )
        workers.append(proc)
        proc.start()
    for w in workers:
        w.join(timeout=30)
        assert w.exitcode == 0

    items = p9.queue_list()
    assert len(items) == 50
    # All sources represented
    assert set(it.source for it in items) == set(sources)
