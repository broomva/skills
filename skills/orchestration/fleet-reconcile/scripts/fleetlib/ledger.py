"""The write-ahead ledger: <state_dir>/ledger.jsonl (spec §5.7).

Append-only JSON Lines, written only through fleet_reconcile.py (tick.sh uses
`fleet ledger-append`, since the lock is fcntl.flock, which bash can't take).
Each append takes fcntl.flock on ledger.lock and fsyncs before returning, so an
intent is on disk before its action starts. Readers fold in write order; dry
records never count toward live state. A corrupt line is counted, not skipped
silently: phase 2's mail and spawn verbs refuse on it.

Every record (schema 1): v, id (unique per record: <tick>-<n>, or owner-<epoch
ms> for a record written outside a tick), ts, scope, tick (null outside a
tick), dry_run, by (act, recover, hook, tick, or owner:<tty>), kind:

    intent                      verb, key, target
    done / failed / unknown     of (the intent it closes), verb, key, result | reason, detail
    seen                        of (the ask intent raised), result: {channel: maestro, item, state}
                                (a phase-1 dialog's: {button, gave_up})
    ack                         of (the ask intent answered), asks: "all" | [ask ids];
                                or, by: tick, keys and resolved: true, when a tick
                                finds asks no longer true (pending the spec)
    adopt                       target: {session_id, paseo_agent_id}
    tick_fire / b_step / runner_exit   detail, exit
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

KINDS = ("intent", "done", "failed", "unknown", "seen", "ack", "adopt", "tick_fire", "b_step", "runner_exit",
         "notice")  # notice: a rate-limited reminder (a Stuck item, a persistent read error), not an action
OUTCOMES = ("done", "failed", "unknown")
VERBS = ("mail", "spawn", "label", "resume", "ask")
REASONS = ("not_live", "ambiguous_name", "harness_refused", "gate_refused", "unledgered_send", "name_taken",
           "ineligible", "spawn_error", "lost")
LOCK_WAIT_S = 10.0


class LedgerError(RuntimeError):
    pass


def ledger_path(state_dir: Path) -> Path:
    return Path(state_dir) / "ledger.jsonl"


def owner_by() -> str:
    """owner:<tty> for the owner's records (ack, adopt)."""
    try:
        tty = os.ttyname(0)
    except OSError:
        tty = "notty"
    return "owner:" + common.safe_text(tty, 40)


def _lock(state_dir: Path, wait: float = LOCK_WAIT_S) -> int:
    fd = os.open(str(state_dir / "ledger.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except OSError as exc:
            if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES) or time.monotonic() > deadline:
                os.close(fd)
                raise LedgerError("ledger lock not acquired")
            time.sleep(0.02)


def append(state_dir: Path, record: Dict[str, Any], wait: float = LOCK_WAIT_S) -> Dict[str, Any]:
    """Validate, stamp (v, ts, id) and append one record; returns it as written.
    The id is taken under the lock: <tick>-<n> in a tick, owner-<epoch ms>
    outside one."""
    rec = dict(record)
    rec.setdefault("v", common.SCHEMA_VERSION)
    rec.setdefault("ts", common.ts(time.time()))
    kind = rec.get("kind")
    if kind not in KINDS:
        raise LedgerError("unknown kind %r" % kind)
    for k in ("scope", "tick", "dry_run", "by"):
        if k not in rec:
            raise LedgerError("record without %s" % k)
    if rec["tick"] is not None and type(rec["tick"]) is not int:
        raise LedgerError("tick must be an integer or null")
    if kind == "intent" and (rec.get("verb") not in VERBS or not rec.get("key")):
        raise LedgerError("an intent needs a verb and a key")
    if kind in OUTCOMES and rec.get("verb") not in VERBS:
        raise LedgerError("an outcome needs its verb")
    if kind in ("failed", "unknown") and rec.get("reason") not in REASONS:
        raise LedgerError("reason must be one of %s" % ", ".join(REASONS))
    if kind in ("seen", "ack") and not rec.get("of") and not rec.get("resolved"):
        raise LedgerError("%s needs of: the ask intent it answers" % kind)
    if isinstance(rec.get("detail"), str):
        rec["detail"] = common.safe_text(rec["detail"], 200)
    state_dir = common.ensure_dir(Path(state_dir))
    lock_fd = _lock(state_dir, wait)
    try:
        if "id" not in rec:
            records, _ = read(state_dir)
            taken = {r.get("id") for r in records}
            if rec["tick"] is None:
                base, n = "owner-%d" % int(time.time() * 1000), 1
                rec["id"] = base
                while rec["id"] in taken:  # two owner records in one millisecond
                    n += 1
                    rec["id"] = "%s-%d" % (base, n)
            else:
                n = sum(1 for r in records if r.get("tick") == rec["tick"]) + 1
                while "%d-%d" % (rec["tick"], n) in taken:
                    n += 1
                rec["id"] = "%d-%d" % (rec["tick"], n)
        line = (json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        fd = os.open(str(ledger_path(state_dir)), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            size = os.fstat(fd).st_size
            if size and os.pread(fd, 1, size - 1) != b"\n":
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


# --------------------------------------------------------------------------
# Folds

def spawned(records: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Live (never dry) spawns: {fleet key: [session ids, and the background
    job id (a session id's first 8 hex) when the listing lagged the spawn]}."""
    records = list(records)
    intents = {r["id"]: r for r in records if r.get("kind") == "intent" and r.get("verb") == "spawn"
               and not r.get("dry_run")}
    out: Dict[str, List[str]] = {}
    for r in records:
        if r.get("kind") == "done" and r.get("verb") == "spawn" and not r.get("dry_run") and r.get("of") in intents:
            res = r.get("result") or {}
            ids = res.get("session_ids") or ([res["session_id"]] if res.get("session_id") else [])
            ids = list(ids) + ([res["job_id"]] if isinstance(res.get("job_id"), str) and not ids else [])
            out.setdefault(intents[r["of"]].get("key") or "", []).extend(i for i in ids if isinstance(i, str))
    return out


#: Where a Maestro item stands, by its state (maestro-paseo shared/states.ts):
#: queued waits for a dispatch (isDispatchable) and hasn't reached the owner;
#: owner is past the queue, so it shows in the Paseo app (running, Needs you,
#: Stuck); final is closed (isTerminal); gone is the fleet's own record of an
#: item Maestro no longer has. The one rule every ask path reads.
MAESTRO_PHASES = {"proposed": "queued", "reviewing": "queued", "triggered": "queued",
                  "running": "owner", "review": "owner", "blocked": "owner",
                  "done": "final", "canceled": "final", "gone": "gone"}


def maestro_phase(state: Any) -> Optional[str]:
    """queued, owner, final or gone; None for a state Maestro doesn't define."""
    return MAESTRO_PHASES.get(state) if isinstance(state, str) else None


def ask_batches(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every ask batch, oldest first: {id, tick, ts, batch, asks, shown: [{ts,
    button, gave_up}], seen (its Maestro item reached the owner, phase owner or
    final, or a phase-1 dialog's Seen click; cleared when the item is gone),
    item (its Maestro work id; None once Maestro no longer has it, so the
    batch is raised again), raised (when the fleet first recorded that item:
    the latest raise), item_state (as last recorded), answer (the last answer
    read back from Maestro, or None), acked (set of ask ids, or "all")}."""
    batches: Dict[str, Dict[str, Any]] = {}
    for r in records:
        kind = r.get("kind")
        if kind == "intent" and r.get("verb") == "ask":
            t = r.get("target") or {}
            batches[r["id"]] = {"id": r["id"], "tick": r.get("tick"), "ts": r.get("ts"), "batch": t.get("batch"),
                                "asks": t.get("asks") or [], "shown": [], "seen": False, "acked": set(),
                                "item": None, "raised": None, "item_state": None, "answer": None}
        elif r.get("of") in batches:
            b = batches[r["of"]]
            if kind == "seen":
                res = r.get("result") or {}
                b["shown"].append({"ts": r.get("ts"), "button": res.get("button"), "gave_up": res.get("gave_up")})
                # Raised in Paseo (a Maestro item past the queue), or a phase-1 dialog's Seen click.
                maestro = res.get("channel") == "maestro"
                phase = maestro_phase(res.get("state")) if maestro else None
                # Gone: the item that reached the owner is no more, and the batch is raised again.
                b["seen"] = phase != "gone" and (
                    b["seen"] or res.get("button") == "Seen" or phase in ("owner", "final"))
                if maestro and isinstance(res.get("item"), str):
                    item = None if phase == "gone" else res["item"]
                    if item is not None and item != b["item"]:
                        b["raised"] = r.get("ts")
                    b["item"], b["item_state"] = item, res.get("state")
            elif kind == "ack" and not r.get("resolved"):
                if r.get("by") == "owner:maestro" and isinstance(r.get("result"), dict):
                    b["answer"] = r["result"]
                if b["acked"] != "all":
                    b["acked"] = "all" if r.get("asks") == "all" else b["acked"] | set(r.get("asks") or [])
    return list(batches.values())


def notices(records: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], float]:
    """{(maestro item id, what): the latest time a `notice` of that kind was
    logged, as epoch seconds}. Used to rate-limit the reminders a still-open
    ask produces each tick (a Stuck item, a persistent read error)."""
    out: Dict[Tuple[str, str], float] = {}
    for r in records:
        if r.get("kind") != "notice":
            continue
        res = r.get("result") or {}
        item, what = res.get("item"), res.get("what")
        if not isinstance(item, str) or not isinstance(what, str):
            continue
        at = common.parse_iso(res.get("ts") or r.get("ts"))
        if at is not None:
            out[(item, what)] = max(at, out.get((item, what), 0.0))
    return out


def open_asks(batch: Dict[str, Any]) -> List[Dict[str, Any]]:
    if batch["acked"] == "all":
        return []
    return [a for a in batch["asks"] if a.get("id") not in batch["acked"]]


def key_states(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Each ask key's state, folded in write order: {key: {"state", "tick",
    "ask", "ts", "of"}}, where state is

        open      asked, and neither answered nor resolved since;
        acked     the owner answered it, and it has not stopped being true since;
        resolved  a tick found it no longer true.

    An ask is per occurrence: a key asked again after a resolution is a new
    ask, and an owner's answer holds for as long as the condition does."""
    st: Dict[str, Dict[str, Any]] = {}
    for r in records:
        kind = r.get("kind")
        if kind == "intent" and r.get("verb") == "ask":
            for a in (r.get("target") or {}).get("asks") or []:
                st[a.get("key")] = {"state": "open", "tick": r.get("tick"), "ask": a, "ts": r.get("ts"),
                                    "of": r.get("id")}
        elif kind == "ack" and r.get("resolved"):
            for k in r.get("keys") or []:
                if k in st and st[k]["state"] in ("open", "acked"):
                    st[k]["state"] = "resolved"
        elif kind == "ack":
            for v in st.values():
                if v["state"] == "open" and v["of"] == r.get("of") and \
                        (r.get("asks") == "all" or v["ask"].get("id") in (r.get("asks") or [])):
                    v["state"] = "acked"
    return st


def open_by_key(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{ask key: {"ask", "tick", "ts", "of"}} for every open key."""
    return {k: v for k, v in key_states(records).items() if v["state"] == "open"}


def closing(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{intent id: the outcome (done, failed or unknown) that closed it}. The
    first outcome closes an intent; a later one for the same id is a second
    writer's and doesn't reopen or change it."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in records:
        if r.get("kind") in OUTCOMES and r.get("of") and r["of"] not in out:
            out[r["of"]] = r
    return out


def open_intents(records: Iterable[Dict[str, Any]], verb: Optional[str] = None) -> List[Dict[str, Any]]:
    """Intents with no outcome yet, in write order (ask intents excluded:
    their answer is an ack, not an outcome)."""
    records = list(records)
    shut = closing(records)
    return [r for r in records if r.get("kind") == "intent" and r.get("verb") != "ask" and r.get("id") not in shut
            and (verb is None or r.get("verb") == verb)]


def mail_recent(records: Iterable[Dict[str, Any]], recipient: str, now: float, hours: float, dry: bool,
                exclude: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The 6 h rule (§5.7): a mail intent to this recipient (its Paseo agent id,
    else its session id) from the last `hours` that is unclosed, or closed done
    or unknown; a failed one doesn't count. Live and dry are counted apart."""
    records = list(records)
    shut = closing(records)
    since = now - hours * 3600
    for r in records:
        if r.get("kind") != "intent" or r.get("verb") != "mail" or r.get("id") == exclude:
            continue
        if bool(r.get("dry_run")) != dry or (r.get("target") or {}).get("recipient") != recipient:
            continue
        if (common.parse_iso(r.get("ts")) or 0.0) < since:
            continue
        out = shut.get(r["id"])
        if out is None or out["kind"] in ("done", "unknown"):
            return r
    return None


def last_tick(records: Iterable[Dict[str, Any]]) -> Optional[int]:
    ticks = [r.get("tick") for r in records if r.get("kind") == "tick_fire" and type(r.get("tick")) is int]
    return max(ticks) if ticks else None
