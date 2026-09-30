"""The write-ahead ledger: <state_dir>/ledger.jsonl (spec §5.7).

Append-only JSON Lines, written by fleet_reconcile.py and tick.sh only. Each
append takes fcntl.flock on ledger.lock and fsyncs before returning, so an
intent is on disk before its action starts. Readers fold in write order; dry
records never count toward live state. A corrupt line is counted, not skipped
silently: phase 2's mail and spawn verbs refuse on it.

Record fields (schema 1): v, ts, scope, tick, dry_run, kind, and per kind:
    intent / done / failed / unknown   id, verb, key, target | result | reason, detail, recovered
    ack                                acks: {tick, asks}
    tick_fire / runner_exit            detail (and exit_code)
"""
from __future__ import annotations

import errno
import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import common

KINDS = ("intent", "done", "failed", "unknown", "ack", "tick_fire", "runner_exit")
VERBS = ("mail", "spawn", "label", "resume", "ask")
REASONS = ("not_live", "ambiguous_name", "harness_refused", "gate_refused", "unledgered_send", "name_taken",
           "ineligible", "spawn_error", "lost")
LOCK_WAIT_S = 10.0


class LedgerError(RuntimeError):
    pass


def ledger_path(state_dir: Path) -> Path:
    return Path(state_dir) / "ledger.jsonl"


def append(state_dir: Path, record: Dict[str, Any]) -> Dict[str, Any]:
    """Validate, stamp and append one record; returns it as written."""
    rec = dict(record)
    rec.setdefault("v", common.SCHEMA_VERSION)
    rec.setdefault("ts", common.ts(time.time()))
    if rec.get("kind") not in KINDS:
        raise LedgerError("unknown kind %r" % rec.get("kind"))
    for k in ("scope", "tick", "dry_run"):
        if k not in rec:
            raise LedgerError("record without %s" % k)
    if rec["kind"] in ("intent", "done", "failed", "unknown"):
        if rec.get("verb") not in VERBS or not isinstance(rec.get("id"), str):
            raise LedgerError("an intent or outcome needs verb and id")
    if rec["kind"] in ("failed", "unknown") and rec.get("reason") not in REASONS:
        raise LedgerError("reason must be one of %s" % ", ".join(REASONS))
    if isinstance(rec.get("detail"), str):
        rec["detail"] = common.safe_text(rec["detail"], 200)
    line = (json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    state_dir = common.ensure_dir(Path(state_dir))
    lock_fd = os.open(str(state_dir / "ledger.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES) or time.monotonic() > deadline:
                    raise LedgerError("ledger lock not acquired")
                time.sleep(0.02)
        fd = os.open(str(ledger_path(state_dir)), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            size = os.fstat(fd).st_size
            if size:
                with open(str(ledger_path(state_dir)), "rb") as fh:
                    fh.seek(size - 1)
                    if fh.read(1) != b"\n":
                        line = b"\n" + line
            view = memoryview(line)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(lock_fd)
    return rec


def read(state_dir: Path) -> Tuple[List[Dict[str, Any]], int]:
    """(records in write order, corrupt line count)."""
    try:
        data = ledger_path(state_dir).read_bytes()
    except FileNotFoundError:
        return [], 0
    records, corrupt = [], 0
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            corrupt += 1
            continue
        if not isinstance(rec, dict) or rec.get("kind") not in KINDS:
            corrupt += 1
            continue
        records.append(rec)
    return records, corrupt


def next_id(records: Iterable[Dict[str, Any]], tick: int) -> str:
    n = sum(1 for r in records if r.get("kind") == "intent" and r.get("tick") == tick)
    return "%d-%d" % (tick, n + 1)


# --------------------------------------------------------------------------
# Folds

def spawned(records: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Live (never dry) spawns: {fleet key: [session ids]} from done records."""
    intents = {r["id"]: r for r in records if r.get("kind") == "intent" and r.get("verb") == "spawn"
               and not r.get("dry_run")}
    out: Dict[str, List[str]] = {}
    for r in records:
        if r.get("kind") == "done" and r.get("verb") == "spawn" and not r.get("dry_run") and r.get("id") in intents:
            res = r.get("result") or {}
            ids = res.get("session_ids") or ([res["session_id"]] if res.get("session_id") else [])
            out.setdefault(intents[r["id"]].get("key") or "", []).extend(i for i in ids if isinstance(i, str))
    return out


def ask_batches(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every ask batch, oldest first: {tick, id, ts, batch, asks, notified: [ts],
    acked: set of ask ids or "all", dry_run}. Dry and live batches are both
    kept: the owner channel runs in every mode (see SKILL.md)."""
    batches: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for r in records:
        kind = r.get("kind")
        if kind == "intent" and r.get("verb") == "ask":
            t = r.get("target") or {}
            batches[r["id"]] = {"id": r["id"], "tick": r.get("tick"), "ts": r.get("ts"), "batch": t.get("batch"),
                                "asks": t.get("asks") or [], "notified": [], "acked": set(),
                                "dry_run": bool(r.get("dry_run"))}
            order.append(r["id"])
        elif kind == "done" and r.get("verb") == "ask" and r.get("id") in batches:
            res = r.get("result") or {}
            if res.get("notified"):
                batches[r["id"]]["notified"].append(r.get("ts"))
        elif kind == "ack":
            a = r.get("acks") or {}
            for bid in order:
                b = batches[bid]
                if b["tick"] == a.get("tick"):
                    if a.get("asks") == "all":
                        b["acked"] = "all"
                    elif b["acked"] != "all":
                        b["acked"] |= set(a.get("asks") or [])
    return [batches[i] for i in order]


def open_asks(batch: Dict[str, Any]) -> List[Dict[str, Any]]:
    if batch["acked"] == "all":
        return []
    return [a for a in batch["asks"] if a.get("id") not in batch["acked"]]


def unacked(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [b for b in ask_batches(records) if open_asks(b)]


def last_tick(records: Iterable[Dict[str, Any]]) -> Optional[int]:
    ticks = [r.get("tick") for r in records if r.get("kind") == "tick_fire" and type(r.get("tick")) is int]
    return max(ticks) if ticks else None
