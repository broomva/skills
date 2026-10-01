#!/usr/bin/env python3
"""fleet: the fleet-reconcile CLI (broomva/workspace
docs/specs/2026-09-29-fleet-reconcile-design.html, §5.7).

Phase 1 observes and classifies and reports; it acts on no session. Stdlib
only. Run through scripts/fleet, which execs `python3 -I` so the tick's cwd and
the user site stay off sys.path; this file puts its own directory and
../ctx-core/scripts (the same checkout) there itself.

    fleet config-get <scope> <key>          one value; tick.sh reads errors as off and dry
    fleet config-check [<scope>]            exit 1 on any problem
    fleet observe --tick N                  write ticks/<N>/snapshot.json
    fleet report --tick N [--dry-run 0|1]   classify; write report.json, report.md and the ask batch
    fleet act ask --show [--tick N]         show the owner a dialog of the open asks (Seen / Later)
    fleet act mail|spawn|label|resume       phase 2: refuses in this build
    fleet asks [--all]                      the owner's open asks
    fleet ack <tick> [--ask ID ...] | --all answer a batch, whole or per ask; or every open batch
    fleet ledger-append fire|exit --tick N  tick.sh's tick_fire and runner_exit records
    fleet next-tick                         the next tick number
    fleet core-compare [--force]            the core's phase-1 comparison, once a day
    fleet label-sheet --ticks A,B,C         the owner's stratified labelling sheet

Every command takes --scope, or reads FLEET_SCOPE. Like every local mechanism
here, these are a floor on the named route, not a boundary (spec §5.7).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
CTX_SCRIPTS = HERE.parent.parent / "ctx-core" / "scripts"
for _p in (str(CTX_SCRIPTS), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fleetlib import common, config, ledger, observe, report  # noqa: E402
from fleetlib.sources import FixtureSources, Sources  # noqa: E402

EXIT_REFUSED = 3
DIALOG_GIVE_UP_S = 600  # §5.7: the dialog gives up after 10 minutes


def _scope(args: argparse.Namespace) -> str:
    sid = getattr(args, "scope", None) or os.environ.get("FLEET_SCOPE") or ""
    if not sid:
        raise SystemExit("fleet: no scope (pass --scope or set FLEET_SCOPE)")
    return sid


def _sec(args: argparse.Namespace) -> dict:
    try:
        return config.scope(_scope(args))
    except config.ConfigError as exc:
        raise SystemExit("fleet: config: %s" % exc)


def _dry(args: argparse.Namespace, sec: dict) -> bool:
    """Dry unless the config says exactly 0 and nothing forces dry: any DRY_RUN
    value but "" or "0" forces it, as in tick.sh."""
    if os.environ.get("DRY_RUN", "") not in ("", "0") or getattr(args, "dry_run", None) == "1":
        return True
    return sec.get("dry_run") != 0


# --------------------------------------------------------------------------

def cmd_config_get(args: argparse.Namespace) -> int:
    try:
        print(config.get(args.scope_id, args.key))
        return 0
    except config.ConfigError as exc:
        print("fleet: %s" % exc, file=sys.stderr)
        return 2


def cmd_config_check(args: argparse.Namespace) -> int:
    try:
        raw = config.load()
        for sid in ([args.scope_id] if args.scope_id else sorted(raw["scopes"])):
            config.scope(sid)
    except config.ConfigError as exc:
        print("fleet config-check: %s" % exc, file=sys.stderr)
        return 1
    print("fleet config-check: ok (%s)" % config.path())
    return 0


def cmd_observe(args: argparse.Namespace) -> int:
    sec = _sec(args)
    src = FixtureSources(Path(args.fixtures)) if args.fixtures else Sources()
    snap = observe.observe(sec, src, args.tick)
    out = report.tick_dir(config.state_dir(sec), args.tick) / "snapshot.json"
    common.write_json(out, snap)
    print(str(out))
    return 0


def _compare_lines(scope_id: str) -> List[Dict[str, Any]]:
    import ctx

    try:
        text = (ctx.state_root() / scope_id / "compare.jsonl").read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def cmd_report(args: argparse.Namespace) -> int:
    sec = _sec(args)
    sd = config.state_dir(sec)
    td = report.tick_dir(sd, args.tick)
    snap = json.loads((td / "snapshot.json").read_text(encoding="utf-8"))
    records, _ = ledger.read(sd)
    dry = _dry(args, sec)
    lines = _compare_lines(sec["scope"])
    rep = report.build(snap, records, dry, lines[-1] if lines else None)
    common.write_json(td / "report.json", rep)
    common.write_atomic(td / "report.md", report.render_md(rep).encode("utf-8"))
    report.prune(sd, time.time())
    base = {"scope": sec["scope"], "tick": args.tick, "dry_run": dry, "by": "tick"}
    if rep["resolved"]:
        ledger.append(sd, dict(base, kind="ack", keys=rep["resolved"], resolved=True))
    if rep["asks"]:
        batch = sd / "asks" / ("%05d.md" % args.tick)
        common.write_atomic(batch, report.render_batch(rep).encode("utf-8"))
        ledger.append(sd, dict(base, kind="intent", verb="ask", key="scope:%s" % sec["scope"],
                               target={"batch": str(batch), "asks": rep["asks"]}))
    print(str(td / "report.md"))
    return 0


# --------------------------------------------------------------------------
# The ask channel (§5.7): a dialog, since banners are stored but not shown on
# this Mac. A dialog that gave up was not seen; a Seen click is a statement,
# not a proof (anything at the Mac can click it).

def _aq(s: str) -> str:
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def show_dialog(title: str, text: str) -> Dict[str, Any]:
    """{button, gave_up} from a `display dialog` with Seen and Later, or
    {error} when it couldn't be shown."""
    osa = os.environ.get("FLEET_OSASCRIPT_BIN") or "osascript"
    script = 'display dialog %s with title %s buttons {"Later", "Seen"} default button "Seen" giving up after %d' % (
        _aq(text), _aq(title), DIALOG_GIVE_UP_S)
    try:
        proc = subprocess.run([osa, "-e", script], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=DIALOG_GIVE_UP_S + 60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": common.safe_text(str(exc), 120)}
    m = re.search(r"button returned:([^,]*), gave up:(true|false)", proc.stdout or "")
    if proc.returncode != 0 or not m:
        return {"error": common.safe_text("osascript exited %d %s" % (proc.returncode, proc.stderr), 120)}
    return {"button": m.group(1).strip() or None, "gave_up": m.group(2) == "true"}


def p9_notify(title: str, body: str) -> Any:
    """p9 may send off the machine (a phone channel), so it gets a count only."""
    p9 = os.environ.get("FLEET_P9_BIN") or shutil.which("p9")
    if not p9:
        return "not on PATH"
    try:
        return subprocess.run([p9, "notify", title, "--body", body, "--kind", "fleet-ask"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        return common.safe_text(str(exc), 80)


def _current_keys(sd: Path) -> Optional[List[str]]:
    """The ask keys still true at the latest tick (its report.json)."""
    rep = report.latest_report(sd)
    return None if rep is None else list(rep.get("ask_keys_current") or [])


def _open_now(records: list, sd: Path) -> Dict[str, Dict]:
    opened = ledger.open_by_key(records)
    current = _current_keys(sd)
    return {k: v for k, v in opened.items() if current is None or k in current}


def due_batches(records: list, open_keys: Dict[str, Dict], now: float,
                reshow_s: float = 6 * 3600) -> List[Dict[str, Any]]:
    """Batches to show: holding an open ask, not clicked Seen, and never shown,
    or shown once (the next tick shows it again), or last shown reshow_s ago
    (ask_renotify_h, 6 h by default)."""
    out = []
    for b in ledger.ask_batches(records):
        if b["seen"] or not any(v["of"] == b["id"] for v in open_keys.values()):
            continue
        shows = b["shown"]
        last = max((common.parse_iso(x["ts"]) or 0.0) for x in shows) if shows else 0.0
        if len(shows) <= 1 or now - last >= reshow_s:
            out.append(b)
    return out


def cmd_act(args: argparse.Namespace) -> int:
    sec = _sec(args)
    if args.verb != "ask":
        print("fleet act %s: refused: phase 1 is report-only; the verb lands in phase 2 (DRY_RUN) and acts only "
              "in phase 3" % args.verb, file=sys.stderr)
        return EXIT_REFUSED
    sd = config.state_dir(sec)
    records, _ = ledger.read(sd)
    open_now = _open_now(records, sd)
    if not args.show:
        print("fleet act ask: %d open ask(s); pass --show to show them" % len(open_now))
        return 0
    # ask runs in every mode and under dry_run: it reaches only the owner (§5.7).
    now = time.time()
    due = due_batches(records, open_now, now, sec["ask_renotify_h"] * 3600)
    if not due:
        print("fleet act ask: nothing to show (%d open ask(s), each shown or seen)" % len(open_now))
        return 0
    if os.environ.get("FLEET_NOTIFY") == "0":
        print("fleet act ask: %d batch(es) due; not shown (FLEET_NOTIFY=0)" % len(due))
        return 0
    n = len(open_now)
    oldest = min((common.parse_iso(v["ts"]) or now) for v in open_now.values())
    first = sorted(open_now.values(), key=lambda v: (v["ts"] or "", v["ask"].get("id") or ""))[-1]["ask"]
    title = "fleet %s: %d open ask%s" % (sec["scope"], n, "" if n == 1 else "s")
    text = "%s\n\nOldest %s. Read them: fleet asks --scope %s\nAnswer: fleet ack <tick> --scope %s" % (
        common.safe_text(first.get("question"), 240), common.age(now - oldest), sec["scope"], sec["scope"])
    res = show_dialog(title, text)
    res["p9"] = p9_notify(title, "%d open; read them on the Mac with fleet asks --scope %s" % (n, sec["scope"]))
    tick = args.tick if args.tick else None
    for b in due:
        ledger.append(sd, {"kind": "seen", "of": b["id"], "scope": sec["scope"], "tick": tick,
                           "dry_run": _dry(args, sec), "by": "tick", "result": res})
    print("fleet act ask: %s" % (("clicked %s" % res.get("button")) if res.get("button") and not res.get("gave_up")
                                 else "gave up (not seen)" if res.get("gave_up") else "not shown: %s" % res.get("error")))
    return 0


def cmd_asks(args: argparse.Namespace) -> int:
    sec = _sec(args)
    sd = config.state_dir(sec)
    records, corrupt = ledger.read(sd)
    now = time.time()
    if args.all:
        for b in ledger.ask_batches(records):
            print("tick %s · %s · %s" % (b["tick"], b["ts"], "answered" if not ledger.open_asks(b)
                                         else "%d open, %s" % (len(ledger.open_asks(b)),
                                                               "seen" if b["seen"] else "not seen")))
            for a in b["asks"]:
                print("  [%s] (%s) %s" % (a.get("id"), a.get("class"), a.get("question")))
    else:
        open_now = _open_now(records, sd)
        if not open_now:
            print("fleet asks: no open asks in scope %s" % sec["scope"])
        for key, v in sorted(open_now.items(), key=lambda kv: (kv[1]["tick"] or 0, kv[1]["ask"].get("id") or "")):
            t = common.parse_iso(v["ts"]) or now
            print("[tick %s, %s] %s ago · (%s) %s" % (v["tick"], v["ask"].get("id"), common.age(now - t),
                                                    v["ask"].get("class"), v["ask"].get("question")))
        if open_now:
            print("\nfleet ack <tick> answers that tick's batch; --ask <id> one ask; --all every open batch.")
    if corrupt:
        print("fleet asks: %d corrupt ledger line(s)" % corrupt, file=sys.stderr)
    return 0


def cmd_ack(args: argparse.Namespace) -> int:
    # A floor, not a boundary: an injected coordinator passes it by unsetting them.
    if os.environ.get("FLEET_CHILD") or os.environ.get("CLAUDECODE"):
        print("fleet ack: refused inside a fleet tick or a Claude Code session; the owner answers from a terminal",
              file=sys.stderr)
        return EXIT_REFUSED
    sec = _sec(args)
    sd = config.state_dir(sec)
    records, _ = ledger.read(sd)
    batches = ledger.ask_batches(records)
    if args.all:
        targets = [(b, "all") for b in batches if ledger.open_asks(b)]
    else:
        if args.tick is None:
            print("fleet ack: name a tick, or pass --all", file=sys.stderr)
            return 2
        mine = [b for b in batches if b["tick"] == args.tick]
        if not mine:
            print("fleet ack: tick %d wrote no ask batch" % args.tick, file=sys.stderr)
            return 1
        ids = {a.get("id") for b in mine for a in b["asks"]}
        unknown = [a for a in args.ask or [] if a not in ids]
        if unknown:
            print("fleet ack: tick %d has no ask %s" % (args.tick, ", ".join(unknown)), file=sys.stderr)
            return 1
        targets = [(b, args.ask or "all") for b in mine]
    for b, asks in targets:
        ledger.append(sd, {"kind": "ack", "of": b["id"], "asks": asks, "scope": sec["scope"], "tick": None,
                           "dry_run": False, "by": ledger.owner_by()})
    print("fleet ack: %d batch(es) answered" % len(targets))
    return 0


def cmd_next_tick(args: argparse.Namespace) -> int:
    """The next tick number: one past both the counter file and the ledger's
    last tick_fire, so a lost counter can't reuse a number. Writes the counter.
    tick.sh calls it while holding the scope's lock."""
    sec = _sec(args)
    sd = config.state_dir(sec)
    counter = sd / "tick-counter"
    try:
        n = int(counter.read_text().strip() or 0)
    except (OSError, ValueError):
        n = 0
    records, _ = ledger.read(sd)
    n = max(n, ledger.last_tick(records) or 0) + 1
    common.write_atomic(counter, ("%d\n" % n).encode())
    print(n)
    return 0


def cmd_ledger_append(args: argparse.Namespace) -> int:
    sec = _sec(args)
    rec = {"kind": {"fire": "tick_fire", "exit": "runner_exit", "b-step": "b_step"}[args.what],
           "scope": sec["scope"], "tick": args.tick, "dry_run": args.dry_run != "0", "by": "tick",
           "detail": args.detail or ""}
    if args.what != "fire":
        rec["exit"] = args.exit
    ledger.append(config.state_dir(sec), rec)
    return 0


def cmd_core_compare(args: argparse.Namespace) -> int:
    """The core's comparison (ctx doctor --compare), once a day at or after
    compare_hour local time, as a read-only step of the tick. Its registration
    time is the owner's to give once (`ctx doctor --compare --registered ...`);
    until compare.jsonl holds it, this step says so and does nothing."""
    sec = _sec(args)
    lines = _compare_lines(sec["scope"])
    if not lines or not lines[0].get("registered"):
        print("fleet core-compare: no registration time yet; the owner runs `ctx doctor --compare --registered "
              "<UTC time>` once in the scope")
        return 0
    now = time.time()
    if not args.force:
        last = common.parse_iso(lines[-1].get("ts")) or 0.0
        if time.localtime(last)[:3] == time.localtime(now)[:3] or time.localtime(now).tm_hour < sec["compare_hour"]:
            print("fleet core-compare: not due (last %s ago; runs once a day from %02d:00)"
                  % (common.age(now - last), sec["compare_hour"]))
            return 0
    import ctx_compare

    return ctx_compare.run_for_scope(sec["scope"], hours=6.0, as_json=False, now=now)


def cmd_label_sheet(args: argparse.Namespace) -> int:
    sec = _sec(args)
    sd = config.state_dir(sec)
    ticks = [int(t) for t in args.ticks.split(",") if t.strip()]
    reps = [report.load_report(sd, t) for t in ticks]
    rows, available = report.labelling_sheet(reps, args.per_class, args.seed)
    name = args.name or "sheet-ticks-%s" % "-".join(str(t) for t in ticks)
    base = sd / "labelling" / name
    common.write_atomic(base.with_suffix(".md"), report.sheet_md(rows, available, ticks, sec["scope"]).encode())
    common.write_atomic(base.with_suffix(".csv"), report.sheet_csv(rows).encode())
    print(str(base.with_suffix(".md")))
    print(str(base.with_suffix(".csv")))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fleet", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def scoped(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--scope", default=None, help="scope id (default: $FLEET_SCOPE)")
        return p

    p = sub.add_parser("config-get")
    p.add_argument("scope_id")
    p.add_argument("key")
    p.set_defaults(func=cmd_config_get)
    p = sub.add_parser("config-check")
    p.add_argument("scope_id", nargs="?")
    p.set_defaults(func=cmd_config_check)
    p = scoped(sub.add_parser("observe"))
    p.add_argument("--tick", type=int, required=True)
    p.add_argument("--fixtures", default=None, help="read captured copies from DIR (tests)")
    p.set_defaults(func=cmd_observe)
    p = scoped(sub.add_parser("report"))
    p.add_argument("--tick", type=int, required=True)
    p.add_argument("--dry-run", default=None, choices=("0", "1"))
    p.set_defaults(func=cmd_report)
    p = scoped(sub.add_parser("act"))
    p.add_argument("verb", choices=("mail", "spawn", "label", "resume", "ask"))
    p.add_argument("--tick", type=int, default=0)
    p.add_argument("--show", action="store_true", help="ask: show the owner a dialog of the open asks")
    p.add_argument("--dry-run", default=None, choices=("0", "1"))
    p.set_defaults(func=cmd_act)
    p = scoped(sub.add_parser("asks"))
    p.add_argument("--all", action="store_true", help="every batch, answered ones included")
    p.set_defaults(func=cmd_asks)
    p = scoped(sub.add_parser("ack"))
    p.add_argument("tick", type=int, nargs="?")
    p.add_argument("--ask", action="append", help="one ask id of that tick's batch (repeatable)")
    p.add_argument("--all", action="store_true", help="answer every batch with an open ask")
    p.set_defaults(func=cmd_ack)
    p = scoped(sub.add_parser("next-tick"))
    p.set_defaults(func=cmd_next_tick)
    p = scoped(sub.add_parser("ledger-append"))
    p.add_argument("what", choices=("fire", "exit", "b-step"))
    p.add_argument("--tick", type=int, required=True)
    p.add_argument("--dry-run", default="1", choices=("0", "1"))
    p.add_argument("--exit", type=int, default=0)
    p.add_argument("--detail", default="")
    p.set_defaults(func=cmd_ledger_append)
    p = scoped(sub.add_parser("core-compare"))
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_core_compare)
    p = scoped(sub.add_parser("label-sheet"))
    p.add_argument("--ticks", required=True, help="comma-separated tick numbers")
    p.add_argument("--per-class", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--name", default=None)
    p.set_defaults(func=cmd_label_sheet)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
