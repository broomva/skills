"""The inventory of scheduled work, report-only: the seam for the Dream (P13)
and scheduled/heartbeat section the spec will add later.

Phase 1 lists what already runs on a schedule and whether it is keeping time.
It starts, stops and edits nothing:

- Paseo schedules (~/.paseo/schedules), placed in a scope by their cwd; a
  schedule in another scope is counted, not listed;
- LaunchAgents whose label has the scope's launchd_prefix, each with its
  cadence, whether it is loaded, its run count, last exit status, last run
  (its log's modification time) and staleness;
- the last bookkeeping (P6) run, from its run log's last line;
- the last Dream (P13) run, from dream_run_log when one is configured.

Each item is a dict with the same keys (see ITEM_KEYS), so the later spec
section can add a source without changing the report.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import ctx

from . import common, parsers
from .sources import SourceError, Sources

ITEM_KEYS = ("source", "id", "name", "cadence", "status", "last_run", "last_result", "next_run", "stale", "detail")
DAY = 86400.0


def _item(**kw: Any) -> Dict[str, Any]:
    return {k: kw.get(k) for k in ITEM_KEYS}


def _period_of_calendar(cal: Any) -> Optional[float]:
    """A StartCalendarInterval's period: weekly with Weekday, monthly with Day,
    daily with Hour, hourly with only Minute. A list takes its shortest."""
    if isinstance(cal, list):
        periods = [p for p in (_period_of_calendar(c) for c in cal) if p]
        return min(periods) if periods else None
    if not isinstance(cal, dict):
        return None
    if "Weekday" in cal:
        return 7 * DAY
    if "Day" in cal:
        return 31 * DAY
    if "Hour" in cal:
        return DAY
    return 3600.0


def _cadence_text(plist: Dict[str, Any]) -> str:
    if isinstance(plist.get("StartInterval"), int):
        return "every %ss" % plist["StartInterval"]
    cal = plist.get("StartCalendarInterval")
    if cal is not None:
        return "calendar %s" % json.dumps(cal, sort_keys=True)
    if plist.get("KeepAlive") or plist.get("RunAtLoad"):
        return "at load" + (" (kept alive)" if plist.get("KeepAlive") else "")
    return "on demand"


def launchd_items(prefix: str, src: Sources, now: float,
                  logs: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """A job's last run is read from its log's modification time: the plist's
    StandardOutPath, or `logs[label]` for a job whose real work logs elsewhere
    (a self-gated job's stdout can stay silent across many launchd runs). It is
    a reading, and `detail` names its source."""
    items = []
    for label, text in src.launch_agents(prefix):
        try:
            plist = json.loads(text)
        except ValueError:
            items.append(_item(source="launchd", id=label, name=label, status="unreadable plist"))
            continue
        period = float(plist["StartInterval"]) if isinstance(plist.get("StartInterval"), int) else \
            _period_of_calendar(plist.get("StartCalendarInterval"))
        printed = src.launchctl_print(label)
        info = parsers.parse_launchctl_print(printed) if printed is not None else {"loaded": False}
        log = (logs or {}).get(label) or plist.get("StandardOutPath") or plist.get("StandardErrorPath")
        last = src.mtime(log) if isinstance(log, str) else None
        stale = None
        if info.get("loaded") and period:
            stale = last is None or now - last > period * 1.5 + 3600
        status = "not loaded" if not info.get("loaded") else ("running" if info.get("running") else "loaded")
        last_exit = info.get("last_exit")
        items.append(_item(
            source="launchd", id=label, name=label, cadence=_cadence_text(plist), status=status,
            last_run=last, last_result=None if last_exit is None else "exit %s" % last_exit,
            stale=stale, detail="runs %s; last run read from %s" % (info.get("runs", "-"),
                                                                     common.tilde(log) if log else "no log path")))
    return items


def paseo_items(src: Sources, by_repo: Dict[str, Optional[str]], scope_id: str,
                now: float) -> Dict[str, Any]:
    items, other, bad = [], 0, 0
    for name, text in src.paseo_schedules():
        try:
            s = parsers.parse_schedule(text, name)
        except parsers.ParseError:
            bad += 1
            continue
        w = ctx.locate(s["cwd"], timeout=2.0) if s["cwd"] else None
        sched_scope = by_repo.get(w.common_dir) if w else None
        if sched_scope != scope_id:
            other += 1
            continue
        one_shot = s["max_runs"] == 1
        cad = s["cadence"]
        stale = None
        if s["status"] == "active" and s["next_run"] is not None:
            stale = s["next_run"] < now - 3600  # due over an hour ago and not run
        items.append(_item(
            source="paseo", id=s["id"], name=s["name"],
            cadence="%s %s (%s)%s" % (cad.get("type", "?"), cad.get("expression", "?"), cad.get("timezone", "?"),
                                      ", one-shot" if one_shot else ""),
            status=s["status"], last_run=s["last_run"],
            last_result=s["last_run_status"], next_run=s["next_run"], stale=stale,
            detail="%d runs, %d failed%s" % (s["runs"], s["failed_runs"],
                                            "; expires %s" % common.ts(s["expires_at"])[:10] if s["expires_at"]
                                            else "")))
    return {"items": items, "other_scopes": other, "unparsed": bad}


def bookkeeping_item(path: str, src: Sources, now: float) -> Dict[str, Any]:
    """The run log's last line: its time and counts. source_files is never read
    (it can name crm/ paths)."""
    try:
        tail = src.tail(path, 64 * 1024)
    except SourceError as exc:
        return _item(source="bookkeeping", id="P6", name="bookkeeping", status="unreadable",
                     detail=common.safe_text(str(exc), 120))
    last = None
    for raw in reversed(tail.splitlines()):
        try:
            rec = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(rec, dict):
            last = rec
            break
    if last is None:
        return _item(source="bookkeeping", id="P6", name="bookkeeping", status="no run recorded")
    t = common.parse_iso(last.get("timestamp"))
    counts = {k: last.get(k) for k in ("items_ingested", "items_promoted", "entities_created", "lint_errors")
              if type(last.get(k)) is int}
    return _item(source="bookkeeping", id="P6", name="bookkeeping", status="ok", last_run=t,
                 last_result="lint_errors %s" % counts.get("lint_errors", "-"),
                 stale=None if t is None else now - t > 2 * DAY,
                 detail=", ".join("%s %d" % kv for kv in sorted(counts.items())))


def dream_item(path: Optional[str], src: Sources, now: float) -> Dict[str, Any]:
    if not path:
        return _item(source="dream", id="P13", name="dream", status="no record",
                     detail="no Dream (P13) run log is configured (dream_run_log); none was found on this machine")
    try:
        tail = src.tail(path, 64 * 1024)
    except SourceError as exc:
        return _item(source="dream", id="P13", name="dream", status="unreadable",
                     detail=common.safe_text(str(exc), 120))
    for raw in reversed(tail.splitlines()):
        try:
            rec = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(rec, dict):
            t = common.parse_iso(rec.get("ts") or rec.get("timestamp"))
            return _item(source="dream", id="P13", name="dream", status="ok", last_run=t,
                         last_result=common.safe_text(rec.get("result") or rec.get("status"), 40) or None,
                         stale=None if t is None else now - t > 7 * DAY)
    return _item(source="dream", id="P13", name="dream", status="no run recorded")


def inventory(sec: Dict[str, Any], src: Sources, by_repo: Dict[str, Optional[str]], now: float) -> Dict[str, Any]:
    out: Dict[str, Any] = {"items": [], "surfaces": {}}
    try:
        p = paseo_items(src, by_repo, sec["scope"], now)
        out["items"].extend(p["items"])
        out["surfaces"]["paseo_schedules"] = {"ok": True, "listed": len(p["items"]), "other_scopes": p["other_scopes"],
                                              "unparsed": p["unparsed"]}
    except (SourceError, OSError) as exc:
        out["surfaces"]["paseo_schedules"] = {"ok": False, "error": common.safe_text(str(exc), 160)}
    if sec.get("launchd_prefix"):
        try:
            items = launchd_items(sec["launchd_prefix"], src, now, sec.get("launchd_logs"))
            out["items"].extend(items)
            out["surfaces"]["launchd"] = {"ok": True, "listed": len(items)}
        except (SourceError, OSError) as exc:
            out["surfaces"]["launchd"] = {"ok": False, "error": common.safe_text(str(exc), 160)}
    if sec.get("bookkeeping_run_log"):
        out["items"].append(bookkeeping_item(sec["bookkeeping_run_log"], src, now))
    out["items"].append(dream_item(sec.get("dream_run_log"), src, now))
    return out
