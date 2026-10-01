"""fleet recover (spec §5.7): close every intent a dead tick left open.

tick.sh runs it before the coordinator. For each intent with no outcome it
observes whether the action happened and writes one record (by: recover):

- mail: the intent's exact text in the recipient's transcript after the
  intent's time is done; it lands as a user entry (an idle recipient) or as a
  queue-operation enqueue (mid-turn), and an enqueue never taken still counts
  as delivered. A readable transcript with neither is failed (lost); an
  unreadable one is unknown. Delivered is not acted on.
- spawn: one listing row carrying the intent's name and started after it is
  done with that session id; none is failed (lost); two or more is done with
  every id and marked duplicate, which the report asks about.
- label: the PR's labels on GitHub decide.
- resume: a row for the session whose process started after the intent is
  done; otherwise failed (lost).

Ask intents aren't recovered: the batch file is written before its intent, so
a tick that dies between them leaves a file whose keys the next tick asks
again. The recovering tick retries nothing; the coordinator decides again
from what it then observes.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from . import common, config, ledger, parsers
from .sources import SourceError, Sources

GRACE_S = 2.0  # clock steps between the intent's fsync and the action


def recover(sec: Dict[str, Any], src: Sources, tick: Optional[int]) -> List[Dict[str, Any]]:
    sd = config.state_dir(sec)
    records, _ = ledger.read(sd)
    out = []
    rows: Optional[List[Dict[str, Any]]] = None
    for it in ledger.open_intents(records):
        t = it.get("target") or {}
        since = (common.parse_iso(it.get("ts")) or 0.0) - GRACE_S
        try:
            if it["verb"] == "mail":
                kind, extra = _mail(src, t, since)
            elif it["verb"] in ("spawn", "resume"):
                if rows is None:
                    rows, _ = parsers.parse_listing(src.agents_listing())
                kind, extra = (_spawn if it["verb"] == "spawn" else _resume)(src, rows, t, since)
            elif it["verb"] == "label":
                kind, extra = _label(src, t)
            else:
                continue
        except (SourceError, parsers.ParseError, OSError, ValueError) as exc:
            kind, extra = "unknown", {"reason": "lost", "detail": "not observed: %s" % common.safe_text(exc, 120)}
        out.append(ledger.append(sd, dict(kind=kind, of=it["id"], verb=it["verb"], key=it["key"], scope=sec["scope"],
                                          tick=tick, dry_run=bool(it.get("dry_run")), by="recover", **extra)))
    return out


def _mail(src: Sources, t: Dict[str, Any], since: float) -> Tuple[str, Dict[str, Any]]:
    path = src.transcript_path(t.get("session_id") or "")
    if not path:
        return "unknown", {"reason": "lost", "detail": "the recipient's transcript was not found"}
    text = t.get("text") or ""
    needles = {json.dumps(text, ensure_ascii=False)[1:-1], json.dumps(text)[1:-1]}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not any(n in line for n in needles):
                    continue
                try:
                    e = json.loads(line)
                    ts = common.parse_iso(e.get("timestamp"))
                except (ValueError, AttributeError):
                    continue
                if ts is not None and ts >= since and text in _delivered(e):
                    return "done", {"result": {"delivered": True, "at": common.ts(ts)}}
    except OSError as exc:
        return "unknown", {"reason": "lost", "detail": "the transcript couldn't be read: %s" % (exc.strerror or exc)}
    return "failed", {"reason": "lost", "detail": "the text isn't in the recipient's transcript after the intent"}


def _delivered(e: Dict[str, Any]) -> List[str]:
    """The texts a transcript entry delivered, in §5.7's two shapes: a user
    entry's message (a string, or its text parts), or a queue-operation's
    enqueued content. Anything else (an assistant entry quoting it) is none."""
    if e.get("type") == "queue-operation":
        return [e["content"]] if isinstance(e.get("content"), str) else []
    if e.get("type") != "user":
        return []
    content = (e.get("message") or {}).get("content") if isinstance(e.get("message"), dict) else None
    if isinstance(content, str):
        return [content]
    return [c.get("text") for c in content or [] if isinstance(c, dict) and isinstance(c.get("text"), str)]


def _spawn(src: Sources, rows: List[Dict[str, Any]], t: Dict[str, Any], since: float) -> Tuple[str, Dict[str, Any]]:
    hits = [r for r in rows if r["name"] == t.get("name") and r["started_at"] >= since]
    if not hits:
        return "failed", {"reason": "lost", "detail": "no session named %s started after the intent" % t.get("name")}
    ids = sorted(r["session_id"] for r in hits)
    res: Dict[str, Any] = {"session_ids": ids, "session_id": ids[0]} if len(ids) == 1 else {
        "session_ids": ids, "duplicate": True}
    return "done", {"result": res}


def _resume(src: Sources, rows: List[Dict[str, Any]], t: Dict[str, Any], since: float) -> Tuple[str, Dict[str, Any]]:
    row = next((r for r in rows if r["session_id"] == t.get("session_id") and r["pid"] is not None), None)
    started = src.pid_started(row["pid"]) if row else None
    if started is not None and started >= since:
        return "done", {"result": {"pid": row["pid"]}}
    return "failed", {"reason": "lost", "detail": "no process for the session started after the intent"}


def _label(src: Sources, t: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    labels = json.loads(src.pr_labels(t["repo"], int(t["pr"])))
    present = t.get("label") in labels
    if present == (t.get("op") == "add"):
        return "done", {"result": {"label": t.get("label"), "op": t.get("op"), "observed": True}}
    return "failed", {"reason": "lost", "detail": "the PR's labels don't show the %s" % t.get("op")}
