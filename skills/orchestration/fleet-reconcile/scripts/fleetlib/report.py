"""The tick report (markdown and JSON), the ask batch, and the owner's
labelling sheet.

Files, under the scope's state dir:
    ticks/<tick>/snapshot.json   what observe read
    ticks/<tick>/report.json     the classification and everything reported
    ticks/<tick>/report.md       the same, for the owner
    asks/<tick>.md               the ask batch, when there are asks
    labelling/<name>.md, .csv    the stratified sample the owner labels

Every sentence is a reading, not an instruction. Other sessions' words (names,
job details, PR titles) pass common.safe_text first.
"""
from __future__ import annotations

import csv
import io
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import classify, common, ledger



def tick_dir(state_dir: Path, tick: int) -> Path:
    return Path(state_dir) / "ticks" / ("%05d" % tick)


def short(sid: Optional[str]) -> str:
    return (sid or "-")[:8]


# --------------------------------------------------------------------------
# Building the report

def build(snap: Dict[str, Any], records: List[Dict[str, Any]], dry_run: bool,
          compare: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = snap["now"]
    results = classify.classify_all(snap)
    by_id = {s["session_id"]: s for s in snap["sessions"]}
    rows = []
    for r in results:
        s = by_id[r["session_id"]]
        a = classify.activity(s)
        rows.append({
            "session_id": s["session_id"], "short": short(s["session_id"]), "name": s["name"], "kind": s["kind"],
            "class": r["class"], "class_name": r["name"], "evidence": common.safe_text(r["evidence"], 160),
            "action": r["action"], "scope": s["scope"], "placement": s["placement"],
            "cwd": common.tilde(s["cwd"]), "branch": s.get("branch"),
            "state": s.get("state"), "status": s.get("status"), "pid": s.get("pid") is not None,
            "activity_age_s": None if a is None else round(now - a), "fleet_key": s.get("fleet_key"),
            "paseo_agent": (s.get("paseo") or {}).get("agent_id"),
        })
    rows.sort(key=lambda x: (classify.ORDER.index(x["class"]), x["session_id"]))
    counts: Dict[str, int] = {}
    for x in rows:
        counts[x["class"]] = counts.get(x["class"], 0) + 1
    rep = {
        "v": common.SCHEMA_VERSION, "scope": snap["scope"], "tick": snap["tick"], "ts": snap["ts"],
        "mode": "report", "phase": 1, "dry_run": dry_run,
        "cc_version": snap.get("cc_version"), "pinned_cc_version": snap.get("pinned_cc_version"),
        "surfaces": snap["surfaces"], "drift": snap.get("drift") or [],
        "sessions": rows, "class_counts": {k: counts[k] for k in classify.ORDER if k in counts},
        "count_check": classify.count_check(snap),
        "overlap": dict(classify.overlap_pass(snap["sessions"], snap["claims"]["by_session"], snap["scope"]),
                        claims_published=snap["claims"]["published"]),
        "spawn_pause": classify.spawn_pause(snap, results),
        "repos": [_repo_summary(r) for r in snap.get("repos") or []],
        "scheduled": snap.get("scheduled") or {},
        "core_compare": compare,
    }
    rep["asks"], rep["asks_open"], rep["acked_still_open"] = make_asks(rep, records, now)
    rep["ask_keys_current"] = sorted(k for k, _, _ in candidates(rep))
    rep["resolved"] = resolved_keys(records, rep["ask_keys_current"])
    open_of = {v["of"] for v in ledger.open_by_key(records).values()}
    pending = [b for b in ledger.ask_batches(records) if b["id"] in open_of]
    rep["batches"] = {"unanswered": len(pending), "unseen": sum(1 for b in pending if not b["seen"]),
                      "oldest": min((b["ts"] for b in pending), default=None)}
    return rep


def _repo_summary(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: r.get(k) for k in ("repo", "slug", "ok", "error", "default_branch", "rules")}
    prs = r.get("prs")
    if prs is None:
        out["prs"] = None
        return out
    held = [p for p in prs if any(lb.lower() == "hold" for lb in p["labels"])]
    out["prs"] = {"open": len(prs), "drafts": sum(1 for p in prs if p["draft"]),
                  "dependabot": sum(1 for p in prs if p["dependabot"]), "held": len(held),
                  "list": [{"number": p["number"], "title": p["title"], "head": common.safe_text(p["head"], 120),
                            "draft": p["draft"],
                            "dependabot": p["dependabot"], "labels": p["labels"]} for p in prs if not p["dependabot"]]}
    return out


# --------------------------------------------------------------------------
# Asks: everything that needs the owner (§3). An ask is per occurrence of a
# condition: asked once, open until the owner acks it or it stops being true
# (a resolution record), and an ack holds for as long as the condition does. A
# condition that ends and comes back is a new ask. Keys are stable for a
# condition: they carry no counts or error text, which change tick to tick.
# A tick writes a batch only when it has a new key.

def _tag(text: str) -> str:
    """A short, stable tag for a condition's content (a job's question, say),
    so a different question from the same session is a different ask."""
    import hashlib

    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:8]


def candidates(rep: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(key, class, question) for everything this tick would ask."""
    cands: List[Tuple[str, str, str]] = []
    for s in rep["sessions"]:
        if s["scope"] != rep["scope"]:
            continue
        label = "%s (%s)" % (s["name"] or "-", s["short"])
        if s["class"] == "3":
            cands.append(("prompt:%s:%s" % (s["session_id"], _tag(s["evidence"])), "3",
                          "Session %s is waiting at a prompt: %s. The fleet never approves prompts."
                          % (label, s["evidence"])))
        elif s["class"] == "7":
            cands.append(("blocked:%s:%s" % (s["session_id"], _tag(s["evidence"])), "7",
                          "Session %s is blocked on you: %s." % (label, s["evidence"])))
    surf = rep["surfaces"]
    if not surf.get("listing", {}).get("ok"):
        cands.append(("listing", "observe", "The session listing was not read: %s. Nothing was classified."
                      % surf.get("listing", {}).get("error", "?")))
    for name, st in sorted(surf.items()):
        if name == "listing":
            continue
        if name == "board":
            for sid, b in sorted(st.items()):
                if not b.get("ok"):
                    cands.append(("surface:board:" + sid, "observe", "The %s board was not read (%s); sessions "
                                  "that would have been 9, 9a or 10 read as unknown." % (sid, b.get("error"))))
            continue
        if not st.get("ok"):
            cands.append(("surface:" + name, "observe", "Surface %s was not read: %s." % (name, st.get("error"))))
    if surf.get("jobs", {}).get("unparsed"):
        cands.append(("surface:jobs-unparsed", "observe",
                      "%d job file(s) did not parse; their sessions read as unknown." % surf["jobs"]["unparsed"]))
    if surf.get("ledger", {}).get("corrupt"):
        cands.append(("surface:ledger-corrupt", "observe",
                      "The ledger has %d corrupt line(s)." % surf["ledger"]["corrupt"]))
    for d in rep["drift"]:
        cands.append(("drift:" + d, "observe", "Parser drift: %s. Recapture the fixtures (tests/"
                      "capture_fixtures.py) and review the parsers." % d))
    cc = rep["count_check"]
    if cc.get("ran") and cc.get("records_without_process"):
        recs = cc["records_without_process"]
        cands.append(("records-without-process", "count",
                      "%d Paseo record(s) in this scope are not archived and have no live process in claude "
                      "agents (listed in the report)." % len(recs)))
    shaped = [u for u in cc.get("unmanaged") or [] if u.get("fleet_shaped")]
    if shaped:
        cands.append(("fleet-shaped-unledgered", "count",
                      "%d session(s) carry a fleet-shaped name the ledger doesn't hold; they are treated as "
                      "unmanaged." % len(shaped)))
    for r in rep["repos"]:
        name = r.get("slug") or common.tilde(r["repo"])
        if not r["ok"]:
            cands.append(("repo:" + name, "github",
                          "Repo %s was not observed: %s." % (name, r.get("error"))))
        elif r.get("rules") and r["rules"]["flags"]:
            ru = r["rules"]
            cands.append(("rules:%s:%s" % (name, ";".join(ru["flags"])), "github", "Repo %s: %s.%s" % (
                name, "; ".join(ru["flags"]),
                " Its PRs get no driver until it has a pull_request rule and checks pinned to GitHub Actions."
                if not ru["driver_eligible"] else "")))
    for it in (rep["scheduled"].get("items") or []):
        # A launchd job's staleness is read from a log's mtime, which a
        # self-gated job leaves untouched for hours, so only a failing exit is
        # asked about; staleness stays a reading in the table. A Paseo schedule
        # has its own nextRunAt, so an overdue one is asked about.
        failing = it["source"] == "launchd" and isinstance(it.get("last_result"), str) and \
            it["last_result"].startswith("exit ") and it["last_result"][5:].lstrip("-").isdigit() and \
            int(it["last_result"][5:]) != 0
        overdue = it["source"] == "paseo" and it.get("stale")
        if failing or overdue:
            cands.append(("sched:%s:%s:%s" % (it["source"], it["id"], it.get("last_result")), "scheduled",
                          "Scheduled %s %s %s: last run %s, cadence %s." % (
                              it["source"], it["name"], "last exited %s" % it["last_result"][5:] if failing
                              else "is overdue", common.ts(it["last_run"])[:16] if it.get("last_run") else "never",
                              it.get("cadence") or "-")))
    return cands


def make_asks(rep: Dict[str, Any], records: List[Dict[str, Any]],
              now: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(new asks for this tick's batch, asks still open from earlier batches,
    asks the owner acked that are still true)."""
    states = ledger.key_states(records)
    new, still, acked_open = [], [], []
    for key, cls, q in candidates(rep):
        q = common.safe_text(q, 400)
        v = states.get(key)
        if v and v["state"] == "open":
            still.append({"key": key, "class": cls, "question": q, "first_tick": v["tick"],
                          "id": v["ask"].get("id")})
        elif v and v["state"] == "acked":
            acked_open.append({"key": key, "class": cls, "question": q})
        else:
            new.append({"id": "a%d" % (len(new) + 1), "key": key, "class": cls, "question": q})
    return new, still, acked_open


def resolved_keys(records: List[Dict[str, Any]], current: Iterable[str]) -> List[str]:
    """Open or acked keys that are no longer true: the tick records their
    resolution, so the same condition coming back is a new ask."""
    now_true = set(current)
    return sorted(k for k, v in ledger.key_states(records).items()
                  if v["state"] in ("open", "acked") and k not in now_true)


# --------------------------------------------------------------------------
# Markdown

def _cell(v: Any) -> str:
    return str(v if v not in (None, "") else "-").replace("|", "/")


def render_md(rep: Dict[str, Any]) -> str:
    now = common.parse_iso(rep["ts"]) or time.time()
    L: List[str] = []
    L.append("# fleet-reconcile · %s · tick %d · %s" % (rep["scope"], rep["tick"], rep["ts"]))
    L.append("")
    L.append("Report only (phase 1). Nothing was sent, spawned, labelled or resumed. The \"would do\" column is "
             "what phase 3 would do.")
    L.append("")
    bt = rep["batches"]
    L.append("Ask batches unanswered: %d, of them not seen: %d%s." % (
        bt["unanswered"], bt["unseen"], ", oldest %s ago" % common.age(now - (common.parse_iso(bt["oldest"]) or now))
        if bt["oldest"] else ""))
    L.append("")
    still = rep["asks_open"]
    n_open = len(still) + len(rep["asks"])
    if n_open:
        first = min([a["first_tick"] for a in still] or [rep["tick"]])
        L.append("**Open asks: %d** (%d new this tick; the oldest first asked in tick %d). Read them with "
                 "`fleet asks`; `fleet ack <tick>` acknowledges that tick's batch and every earlier one."
                 % (n_open, len(rep["asks"]), first))
    else:
        L.append("Open asks: 0.")
    if rep.get("surfaces", {}).get("gh_auth", {}).get("mode", "").startswith("keyring"):
        L.append("")
        L.append("GitHub was read with the keyring token (%s), not the fleet token." % rep["surfaces"]["gh_auth"]["mode"])
    L.append("")
    L.append("## Observation")
    L.append("")
    L.append("| surface | read | detail |")
    L.append("|---|---|---|")
    for name, s in sorted(rep["surfaces"].items()):
        if name == "board":
            for sid, b in sorted(s.items()):
                L.append("| board %s | %s | %s |" % (sid, "yes" if b.get("ok") else "NO", _cell(
                    b.get("error") or "%s rows, %s events" % (b.get("rows"), b.get("events")))))
            continue
        detail = s.get("error") or ", ".join("%s %s" % (k, v) for k, v in sorted(s.items()) if k != "ok")
        L.append("| %s | %s | %s |" % (name, "yes" if s.get("ok") else "**NO**", _cell(detail)))
    L.append("")
    L.append("Claude Code %s; parsers pinned on %s." % (rep.get("cc_version") or "?", rep["pinned_cc_version"]))
    if rep["drift"]:
        L.append("")
        L.append("Drift: " + "; ".join(rep["drift"]))
    L.append("")
    L.append("## Classes")
    L.append("")
    L.append("| # | class | sessions |")
    L.append("|---|---|---|")
    for k, n in rep["class_counts"].items():
        L.append("| %s | %s | %d |" % (k, classify.NAMES[k], n))
    if rep.get("spawn_pause"):
        sp = rep["spawn_pause"]
        L.append("")
        L.append("Spawn pause (class 2; the usage limit is shared): %s %s (%s), from %d session(s)." % (
            "until" if sp["active"] else "ended at",
            common.ts(sp["until"])[:16] + "Z" if sp.get("until") else "an unreadable reset time",
            sp.get("how"), len(sp["sessions"])))
    L.append("")
    L.append("## Sessions in scope %s" % rep["scope"])
    L.append("")
    L.append("| # | session | name | kind | status | activity | where | evidence | would do |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    inscope = [s for s in rep["sessions"] if s["class"] != "1"]
    for s in inscope:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            s["class"], s["short"], _cell(s["name"]), s["kind"], _cell(s["status"] or s["state"]),
            common.age(s["activity_age_s"]) if s["activity_age_s"] is not None else "no transcript",
            _cell(s["cwd"]), _cell(s["evidence"]), s["action"]))
    out = [s for s in rep["sessions"] if s["class"] == "1"]
    L.append("")
    unplaced = [s for s in out if s["placement"] == "unplaced"]
    L.append("Out of scope (class 1): %d session(s); %d of them unplaced (cwd gone, no board row), which could "
             "belong to any scope:" % (len(out), len(unplaced)))
    for s in unplaced[:60]:
        L.append("- %s %s (%s, %s), cwd %s" % (s["short"], _cell(s["name"]), s["kind"], s["state"] or s["status"]
                                             or "-", _cell(s["cwd"])))
    L.append("")
    L.append("## Count check")
    L.append("")
    cc = rep["count_check"]
    if not cc.get("ran"):
        L.append("Not run: %s." % cc.get("reason"))
    else:
        recs = cc.get("records_without_process")
        if recs is None:
            L.append("- Paseo records: %s." % cc.get("records_reason"))
        else:
            L.append("- Paseo records not archived and with no live process in claude agents: %d (plus %d whose "
                     "cwd can't be placed in any scope)." % (len(recs), cc.get("records_unplaced", 0)))
            for r in recs[:40]:
                L.append("  - agent %s, session %s, status %s, %s: %s" % (
                    short(r["agent_id"]), short(r["session_id"]), r["last_status"] or "-", _cell(r["title"]),
                    r["why"]))
        um = cc.get("unmanaged") or []
        L.append("- In-scope sessions with neither a Paseo record nor a fleet name: %d (%d live)." % (
            len(um), sum(1 for u in um if u["live"])))
        for u in um[:40]:
            L.append("  - %s %s (%s)%s%s" % (short(u["session_id"]), _cell(u["name"]), u["kind"],
                                            ", live" if u["live"] else "",
                                            ", fleet-shaped name not in the ledger" if u["fleet_shaped"] else ""))
    L.append("")
    L.append("## Overlap pass")
    L.append("")
    ov = rep["overlap"]
    if not ov["claims_published"]:
        L.append("No claims yet: the core publishes them in its phase 2. The pass runs on fixtures only.")
    for o in ov["overlaps"]:
        L.append("- %s and %s share %s in %s; would mail: %s" % (
            short(o["sessions"][0]), short(o["sessions"][1]), ", ".join(o["paths"]), common.tilde(o["repo"]),
            ", ".join(short(x) for x in o["would_mail"]) or "none (not fleet sessions)"))
    L.append("")
    L.append("## Repos, rules and PRs")
    L.append("")
    L.append("| repo | observed | rules | driver-eligible repo | open PRs | drafts | dependabot | held |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in rep["repos"]:
        name = r.get("slug") or common.tilde(r["repo"])
        if not r["ok"]:
            L.append("| %s | **NO**: %s | - | - | - | - | - | - |" % (name, _cell(r.get("error"))))
            continue
        ru = r["rules"]
        p = r["prs"]
        L.append("| %s | yes | %s | %s | %d | %d | %d | %d |" % (
            name, _cell(", ".join(ru["types"])), "yes" if ru["driver_eligible"] else "no: " + "; ".join(ru["flags"]),
            p["open"], p["drafts"], p["dependabot"], p["held"]))
    L.append("")
    L.append("## Scheduled work (inventory, report-only)")
    L.append("")
    sch = rep["scheduled"]
    for name, s in sorted((sch.get("surfaces") or {}).items()):
        L.append("- %s: %s" % (name, "read" if s.get("ok") else "NOT read: %s" % s.get("error")) + (
            " (%d in other scopes, not listed)" % s["other_scopes"] if s.get("other_scopes") else ""))
    L.append("")
    L.append("| source | id | name | cadence | status | last run | last result | next run | stale |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for it in sch.get("items") or []:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            it["source"], _cell(it["id"]), _cell(it["name"]), _cell(it.get("cadence")), _cell(it.get("status")),
            (common.ts(it["last_run"])[:16] + "Z (%s ago)" % common.age(now - it["last_run"])) if it.get("last_run")
            else "-", _cell(it.get("last_result")),
            common.ts(it["next_run"])[:16] + "Z" if it.get("next_run") else "-",
            {True: "**yes**", False: "no", None: "-"}[it.get("stale")]))
    L.append("")
    if rep.get("core_compare"):
        c = rep["core_compare"]
        L.append("## Core comparison (ctx doctor --compare, latest)")
        L.append("")
        L.append("%s: board side %s, session side %s (raw %s / %s), %s." % (
            c.get("ts", "?"), _pct(c.get("board_pct")), _pct(c.get("session_pct")), _pct(c.get("board_raw_pct")),
            _pct(c.get("session_raw_pct")), "pass" if c.get("pass") else "FAIL"))
        L.append("")
    L.append("## Asks")
    L.append("")
    L.append("New this tick: %d." % len(rep["asks"]))
    for a in rep["asks"]:
        L.append("- [%s] %s" % (a["id"], a["question"]))
    if still:
        L.append("")
        L.append("Still open from earlier ticks: %d." % len(still))
        for a in still:
            L.append("- [tick %s, %s] %s" % (a["first_tick"], a["id"], a["question"]))
    if rep["acked_still_open"]:
        L.append("")
        L.append("Acknowledged and still true: %d (not asked again while they stay true)."
                 % len(rep["acked_still_open"]))
    if rep.get("resolved"):
        L.append("")
        L.append("No longer true since the last tick, so closed: %d." % len(rep["resolved"]))
    return "\n".join(L) + "\n"


def _pct(v: Any) -> str:
    return "%.0f%%" % (v * 100) if isinstance(v, (int, float)) else "-"


def render_batch(rep: Dict[str, Any]) -> str:
    L = ["# fleet asks · %s · tick %d · %s" % (rep["scope"], rep["tick"], rep["ts"]), "",
         "New asks. `fleet ack %d` acknowledges them and every earlier batch; `fleet ack %d --ask <id>` one ask."
         % (rep["tick"], rep["tick"]), ""]
    for a in rep["asks"]:
        L.append("- [%s] (%s) %s" % (a["id"], a["class"], a["question"]))
    if rep["asks_open"]:
        L += ["", "Also still open from earlier ticks: %d (`fleet asks`)." % len(rep["asks_open"])]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# The labelling sheet (§9 phase 1 exit)

SHEET_COLUMNS = ("row", "tick", "session", "name", "kind", "class", "class_name", "evidence", "would_do",
                 "owner_agree_or_disagree", "owner_note")


def labelling_sheet(reports: Iterable[Dict[str, Any]], per_class: int = 3,
                    seed: int = 0) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """A stratified sample: per_class sessions for every class that occurs
    (fewer only if fewer exist), distinct sessions first, drawn with a fixed
    seed so the sheet is reproducible."""
    pool: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    for rep in reports:
        for s in rep["sessions"]:
            pool.setdefault(s["class"], []).append((rep["tick"], s))
    rng = random.Random(seed)
    rows, available = [], {}
    for cls in classify.ORDER:
        entries = pool.get(cls) or []
        if not entries:
            continue
        seen, distinct, repeats = set(), [], []
        shuffled = entries[:]
        rng.shuffle(shuffled)
        for tick, s in shuffled:
            (repeats if s["session_id"] in seen else distinct).append((tick, s))
            seen.add(s["session_id"])
        available[cls] = len(seen)
        for tick, s in distinct[:per_class]:  # §9: fewer only if fewer exist; never one session twice
            rows.append({"tick": tick, "session": s["short"], "name": s["name"], "kind": s["kind"],
                         "class": cls, "class_name": classify.NAMES[cls], "evidence": s["evidence"],
                         "would_do": s["action"], "owner_agree_or_disagree": "", "owner_note": ""})
    for i, r in enumerate(rows, 1):
        r["row"] = i
    return rows, available


def sheet_md(rows: List[Dict[str, Any]], available: Dict[str, int], ticks: List[int], scope: str) -> str:
    L = ["# Owner labelling sheet · fleet-reconcile phase 1 · scope %s" % scope, "",
         "Ticks %s. For each row, mark **agree** or **disagree** with the class, and add a note when you "
         "disagree. The exit criterion (spec §9): ≥90%% agreement overall and no class below 2 of 3." %
         ", ".join(str(t) for t in ticks), "",
         "Distinct sessions available per class: %s." % ", ".join("%s: %d" % kv for kv in available.items()), "",
         "| row | tick | session | name | kind | class | evidence | would do | agree / disagree | note |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %d | %d | %s | %s | %s | %s %s | %s | %s |  |  |" % (
            r["row"], r["tick"], r["session"], _cell(r["name"]), r["kind"], r["class"], r["class_name"],
            _cell(r["evidence"]), r["would_do"]))
    return "\n".join(L) + "\n"


def sheet_csv(rows: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(SHEET_COLUMNS))
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in SHEET_COLUMNS})
    return buf.getvalue()


#: Snapshots are the bulk of a tick (about 120 KB); reports stay.
SNAPSHOT_KEEP_S = 7 * 86400


def prune(state_dir: Path, now: float) -> int:
    """Remove this tool's own snapshot.json files older than a week; the
    report.json and report.md of every tick stay. Returns how many went."""
    n = 0
    for p in (Path(state_dir) / "ticks").glob("*/snapshot.json"):
        try:
            if now - p.stat().st_mtime > SNAPSHOT_KEEP_S:
                p.unlink()
                n += 1
        except OSError:
            continue
    return n


def latest_report(state_dir: Path) -> Optional[Dict[str, Any]]:
    ticks = sorted(p for p in (Path(state_dir) / "ticks").glob("*/report.json"))
    if not ticks:
        return None
    try:
        return json.loads(ticks[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_report(state_dir: Path, tick: int) -> Dict[str, Any]:
    return json.loads((tick_dir(state_dir, tick) / "report.json").read_text(encoding="utf-8"))
