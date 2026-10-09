"""The owner channel as a ledger: the fleet's asks and alerts are decision asks
in the scope's own machine-local ledger, answered in Maestro's Decisions
(BRO-2908).

Before this, each batch of asks became a Maestro work item: a Paseo agent run
for one turn so the batch would reach review and show at Needs you. That made
the owner's answer a gate verdict on a session that did nothing, a second
answer surface beside Decisions, and an agent per batch left behind. The
control interface spec (broomva/workspace#861, §5.6) already gives a writer
with no branch to ride a registered machine-local ledger, and Maestro reads
the fleet's (`<state_dir>/.control/asks`, server/fleet.ts ASK_ROOT): its
asks list in Decisions, a blocking one counts in Needs you, and the answer is
written into the entry by Maestro under the spec's lock (§5.5).

The ledger is `<state_dir>/.control/asks/fleet-<scope>.yaml`, written only by
this module and by Maestro's answer. Every value is one line of JSON, which is
YAML too: Maestro's answer edit writes `key: <JSON>` lines into the entry, so
the file stays in that subset and is read back here without a YAML library
(the tick runs `python3 -I`, where none is installed). A line outside the
subset fails the read loudly, and nothing is written over a file this module
cannot read.

An ask is one occurrence of a condition (SKILL.md, the owner channel), so its
`uid` is `fleet-<scope>-<sha256(key, batch)[:12]>`: the same occurrence is the
same entry from tick to tick, and a condition that ends and comes back is a new
entry beside the old one's answer. An occurrence a tick finds no longer true
is withdrawn (`status: withdrawn`); an owner's answer is read back once into
the fleet's own ledger as an `ack` of that batch's ask, as the item's verdict was.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from . import common

ASK_ROOT = Path(".control") / "asks"

#: Spec §5.5's lock root, shared with Maestro (server/paths.ts controlAskPaths).
LOCK_ROOT_ENV = "MAESTRO_PASEO_ASK_LOCKS"
LOCK_STALE_S = 120
RECLAIM_STALE_S = 60
LOCK_WAIT_S = 5.0

#: A session waits on the owner in these classes (3: at a prompt; 7: blocked on you): Needs you counts them.
BLOCKING_CLASSES = frozenset({"3", "7"})

#: The one answer the fleet acts on: acknowledged, with the owner's note if any (`fleet ack`'s own meaning).
ACK = "ack"
OPTIONS = [
    {"id": ACK, "label": "Acknowledge", "consequence": "The fleet records your answer and its note, and asks again "
     "only if this stops being true and comes back.", "reversible": True, "recommended": True},
]
#: An alert's one answer: seen. It comes back while the failure lasts, and Maestro's health notice stays until a tick passes.
ALERT_OPTIONS = [
    {"id": ACK, "label": "Acknowledge", "consequence": "Records that you saw it. While the failure lasts it is raised "
     "again after 6 h, and Maestro's fleet health notice stays until a tick passes.", "reversible": True,
     "recommended": True},
]
WHY_YOU = "fleet-reconcile only observes and asks: it never approves a prompt or changes a repo's rules for you."
DEFAULT = "It stays open until you answer, or until a tick finds it no longer true."


class LedgerError(RuntimeError):
    """The ledger could not be read or written; nothing was changed."""


def path(sec: Dict[str, Any]) -> Path:
    return Path(sec["state_dir"]) / ASK_ROOT / ("fleet-%s.yaml" % sec["scope"])


def uid(scope: str, key: str, batch: Any) -> str:
    """One occurrence's identity: its key and the batch that first asked it."""
    return "fleet-%s-%s" % (scope, hashlib.sha256(("%s\n%s" % (key, batch)).encode("utf-8")).hexdigest()[:12])


# -- the spec §5.5 lock -------------------------------------------------------

def lock_root() -> Path:
    return Path(os.environ.get(LOCK_ROOT_ENV) or (common.home() / ".local/state/control-asks/locks"))


def lock_key(ledger: Path) -> str:
    """`<k>`: the first 16 hex of SHA-256(realpath(dirname(L)) + "/" + basename(L)), as Maestro's lockKey."""
    return hashlib.sha256(("%s/%s" % (os.path.realpath(ledger.parent), ledger.name)).encode("utf-8")).hexdigest()[:16]


def _start_of(pid: int) -> Optional[int]:
    """A process's start, in epoch seconds, from `ps -o etime=` (elapsed time, which no time zone shifts)."""
    try:
        out = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    parts = out.strip().replace("-", ":").split(":")
    if not out.strip() or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    seconds = 0
    for unit, n in zip([86400, 3600, 60, 1][-len(nums):], nums):
        seconds += unit * n
    return int(time.time()) - seconds


def _alive(pid_line: str) -> bool:
    words = pid_line.split()
    if not words or not words[0].isdigit() or int(words[0]) <= 0:
        return False
    pid = int(words[0])
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    if len(words) < 2 or not words[1].lstrip("-").isdigit():
        return True
    start = _start_of(pid)
    return start is None or abs(start - int(words[1])) <= 2


def _age(p: Path) -> Optional[float]:
    try:
        return time.time() - p.stat().st_mtime
    except FileNotFoundError:
        return None


def _stale(d: Path) -> bool:
    age = _age(d)
    if age is None or age < LOCK_STALE_S:
        return False
    try:
        return not _alive((d / "pid").read_text())
    except OSError:
        return True


def _reclaim(d: Path) -> None:
    mutex = Path(str(d)[:-2] + ".reclaim.d")
    try:
        mutex.mkdir()
    except FileExistsError:
        age = _age(mutex)
        if age is not None and age >= RECLAIM_STALE_S:
            _rmtree(mutex)
        return
    try:
        if _stale(d):
            aside = Path("%s.stale-%s" % (d, secrets.token_hex(4)))
            try:
                d.rename(aside)
            except OSError:
                return
            _rmtree(aside)
    finally:
        _rmtree(mutex)


def _rmtree(d: Path) -> None:
    for child in d.glob("*"):
        try:
            child.unlink()
        except OSError:
            pass
    try:
        d.rmdir()
    except OSError:
        pass


@contextmanager
def locked(ledger: Path, wait: float = LOCK_WAIT_S) -> Iterator[Callable[[], None]]:
    """Hold the ledger's spec §5.5 lock: a directory with our pid and start, and a token. Yields a check to
    call right before writing: it raises if the lock is no longer ours (reclaimed as stale meanwhile)."""
    root = lock_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    d = root / ("%s.d" % lock_key(ledger))
    deadline = time.time() + wait
    while True:
        try:
            d.mkdir()
            break
        except FileExistsError:
            if _stale(d):
                _reclaim(d)
            if time.time() >= deadline:
                raise LedgerError("another writer holds the lock on %s; nothing was written" % common.tilde(ledger))
            time.sleep(0.05)
    token = secrets.token_hex(16)
    try:
        (d / "pid").write_text("%d %d\n" % (os.getpid(), _start_of(os.getpid()) or int(time.time())))
        (d / "token").write_text(token + "\n")
    except OSError as exc:
        _rmtree(d)  # made but not finished: taken back, so no half-written lock is left
        raise LedgerError("could not take the lock on %s: %s" % (common.tilde(ledger), exc))

    def still_ours() -> None:
        try:
            if (d / "token").read_text().strip() == token:
                return
        except OSError:
            pass
        raise LedgerError("the lock on %s was taken over; nothing was written" % common.tilde(ledger))

    try:
        yield still_ours
    finally:
        try:
            if (d / "token").read_text().strip() == token:
                _rmtree(d)
        except OSError:
            pass


# -- the ledger's one-line-JSON subset of YAML ----------------------------------

def parse(text: str) -> Dict[str, Any]:
    """{top-level key: value, "asks": [entry, ...]} from the subset this module and Maestro write."""
    doc: Dict[str, Any] = {}
    asks: Optional[List[Dict[str, Any]]] = None
    entry: Optional[Dict[str, Any]] = None
    # "\n" only: an answer's JSON may hold a raw U+2028 or U+0085, which str.splitlines() would break on.
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip("\r").rstrip(" \t")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if indent == 0:
            if body == "asks:":
                asks = doc.setdefault("asks", [])
                entry = None
                continue
            key, value = _pair(body, n)
            doc[key] = value
            asks = entry = None
            continue
        if asks is None:
            raise LedgerError("line %d: an indented line outside asks:" % n)
        if body.startswith("- "):
            entry = {}
            asks.append(entry)
            body = body[2:].strip()
        if entry is None:
            raise LedgerError("line %d: a key before the first ask" % n)
        key, value = _pair(body, n)
        entry[key] = value
    doc.setdefault("asks", [])
    return doc


def _pair(body: str, n: int) -> Tuple[str, Any]:
    key, sep, rest = body.partition(":")
    if not sep or not key or " " in key:
        raise LedgerError("line %d: not a `key: value` line" % n)
    rest = rest.strip()
    if rest == "":
        return key, None
    try:
        return key, json.loads(rest)
    except ValueError:
        raise LedgerError("line %d: %s is not one line of JSON" % (n, key))


def render(doc: Dict[str, Any], scope: str) -> str:
    lines = ["# The fleet's asks for scope %s, written by fleet-reconcile (BRO-2908). Answer them in Maestro's "
             "Decisions." % scope]
    for key, value in doc.items():
        if key != "asks":
            lines.append("%s: %s" % (key, _json(value)))
    lines.append("asks:")
    for entry in doc.get("asks") or []:
        first = True
        for key, value in entry.items():
            lines.append("%s%s: %s" % ("  - " if first else "    ", key, _json(value)))
            first = False
    return "\n".join(lines) + "\n"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def read(ledger: Path) -> Dict[str, Any]:
    try:
        return parse(ledger.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"asks": []}
    except OSError as exc:
        raise LedgerError("%s: %s" % (common.tilde(ledger), exc))


def _write(ledger: Path, doc: Dict[str, Any], scope: str, still_ours: Callable[[], None]) -> None:
    still_ours()  # spec §5.5: the token is checked again right before the rename
    common.write_atomic(ledger, render(doc, scope).encode("utf-8"), mode=0o600)


# -- entries ----------------------------------------------------------------------

def answered(entry: Dict[str, Any]) -> bool:
    return any(entry.get(k) not in (None, "") for k in ("answer", "answer_option", "answered_at")) or \
        str(entry.get("status") or "").startswith(("resolved", "answered"))


def is_open(entry: Dict[str, Any]) -> bool:
    return not answered(entry) and not str(entry.get("status") or "").startswith(("withdrawn", "archived", "closed"))


def ask_entry(scope: str, ask: Dict[str, Any], batch: Optional[str], tick: Any, asked: Optional[str]) -> Dict[str, Any]:
    cls = str(ask.get("class") or "")
    u = uid(scope, str(ask["key"]), batch)
    return {
        "id": u,
        "uid": u,
        "headline": common.safe_text(ask.get("question"), 400),
        "class": "fleet",
        "blocking": cls in BLOCKING_CLASSES,
        "why_you": WHY_YOU,
        "default": DEFAULT,
        "options": OPTIONS,
        "asked_at": asked or common.ts(time.time()),
        "fleet": {"scope": scope, "key": ask["key"], "class": cls, "batch": batch, "ask": ask.get("id"), "tick": tick},
    }


def sync(sec: Dict[str, Any], ready: Dict[str, Dict[str, Any]], open_all: List[Tuple[str, Any]],
         acked: List[Tuple[str, Any]] = ()) -> Tuple[int, int]:
    """Bring the ledger to the fleet's asks. Each ready occurrence (open past ask_raise_after_min) has an
    entry, added when new, its question refreshed while open. Any open entry that is no longer an open
    occurrence (`open_all`, every `(key, batch)` the fleet holds open) is closed: as answered from a
    terminal when the owner acked it there (`acked`), else withdrawn, no longer true; so a tick that
    skipped its ask step leaves nothing open behind. Answers are never touched. (added, withdrawn)."""
    scope = sec["scope"]
    ledger = path(sec)
    added = withdrawn = 0
    with locked(ledger) as still_ours:
        doc = read(ledger)
        doc.setdefault("arc", "fleet-%s" % scope)
        doc.setdefault("writer", "fleet-reconcile")
        entries = doc["asks"]
        by_uid = {e.get("uid"): e for e in entries}
        for key, v in ready.items():
            ask = dict(v["ask"], key=key)
            e = by_uid.get(uid(scope, key, v.get("of")))
            if e is None:
                fresh = ask_entry(scope, ask, v.get("of"), v.get("tick"), v.get("ts"))
                entries.append(fresh)
                by_uid[fresh["uid"]] = fresh
                added += 1
            elif is_open(e):
                headline = common.safe_text(ask.get("question"), 400)
                if e.get("headline") != headline:  # only when it changed: an answer checks the entry it read
                    e["headline"] = headline
        still = {uid(scope, k, b) for k, b in open_all}
        elsewhere = {uid(scope, k, b) for k, b in acked}
        for e in entries:
            f = e.get("fleet") if isinstance(e.get("fleet"), dict) else {}
            if not f.get("key") or not is_open(e) or e.get("uid") in still:
                continue
            if e.get("uid") in elsewhere:
                e["status"] = "resolved"
                e["resolution"] = "Answered from a terminal (fleet ack)."
            else:
                e["status"] = "withdrawn"
                e["resolution"] = "A tick found it no longer true."
                withdrawn += 1
        _write(ledger, doc, scope, still_ours)
    return added, withdrawn


def alert(sec: Dict[str, Any], kind: str, message: str) -> str:
    """An alert of `kind`, as an entry: refreshed while one is open, a new one once the last was answered."""
    scope = sec["scope"]
    ledger = path(sec)
    with locked(ledger) as still_ours:
        doc = read(ledger)
        doc.setdefault("arc", "fleet-%s" % scope)
        doc.setdefault("writer", "fleet-reconcile")
        entries = doc["asks"]
        base = "fleet-%s-alert-%s" % (scope, "".join(c if c.isalnum() else "-" for c in kind)[:40])
        current = next((e for e in reversed(entries) if str(e.get("uid") or "").startswith(base) and is_open(e)), None)
        text = common.safe_text(message, 400)
        if current is None:
            u = "%s-%d" % (base, int(time.time()))
            # Not blocking: a failing or missed tick is Maestro's own fleet health notice, which counts in Needs
            # you; this entry is its words, listed in Decisions, so the one failure is never counted twice.
            current = {"id": u, "uid": u, "class": "alert", "blocking": False, "why_you": WHY_YOU,
                       "default": "It stays open until you acknowledge it.",
                       "options": ALERT_OPTIONS, "fleet": {"scope": scope, "alert": kind}}
            entries.append(current)
        current["headline"] = "The %s fleet tick: %s" % (scope, text)
        current["asked_at"] = common.ts(time.time())
        _write(ledger, doc, scope, still_ours)
    return str(current["uid"])


def answers(sec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every answered ask entry: {uid, key, batch, ask, option, answer, at}. Alerts are not asks and are left out."""
    out = []
    for e in read(path(sec))["asks"]:
        f = e.get("fleet") if isinstance(e.get("fleet"), dict) else {}
        # The owner's answer is its words or its option; a status alone (closed from a terminal) is not one.
        if not (e.get("answer_option") or e.get("answer")) or not f.get("key"):
            continue
        out.append({"uid": e.get("uid"), "key": f["key"], "batch": f.get("batch"), "ask": f.get("ask"),
                    "option": e.get("answer_option"), "answer": e.get("answer"), "at": e.get("answered_at")})
    return out
