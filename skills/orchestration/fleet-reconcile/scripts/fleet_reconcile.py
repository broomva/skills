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
    fleet act ask --notify --tick N         notify the owner of the batch (osascript, p9 notify)
    fleet act mail|spawn|label|resume       phase 2: refuses in this build
    fleet asks [--all]                      the owner's unacknowledged ask batches
    fleet ack <tick> [--ask ID ...]         acknowledge a batch, whole or per ask
    fleet ledger-record fire|exit --tick N  tick.sh's tick_fire and runner_exit records
    fleet core-compare [--force]            the core's phase-1 comparison, once a day
    fleet label-sheet --ticks A,B,C         the owner's stratified labelling sheet

Every command takes --scope, or reads FLEET_SCOPE.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CTX_SCRIPTS = HERE.parent.parent / "ctx-core" / "scripts"
for _p in (str(CTX_SCRIPTS), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fleetlib import common, config, ledger, observe, report  # noqa: E402
from fleetlib.sources import FixtureSources, Sources  # noqa: E402

EXIT_REFUSED = 3


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
    """Dry unless the config says exactly 0 and nothing forces dry."""
    if os.environ.get("DRY_RUN") == "1" or getattr(args, "dry_run", None) == "1":
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


def _latest_compare(scope_id: str) -> dict:
    import ctx

    p = ctx.state_root() / scope_id / "compare.jsonl"
    try:
        tail = common.read_tail(p, 16 * 1024).splitlines()
        return json.loads(tail[-1]) if tail else None
    except (OSError, ValueError, IndexError):
        return None


def cmd_report(args: argparse.Namespace) -> int:
    sec = _sec(args)
    sd = config.state_dir(sec)
    td = report.tick_dir(sd, args.tick)
    snap = json.loads((td / "snapshot.json").read_text(encoding="utf-8"))
    records, _ = ledger.read(sd)
    dry = _dry(args, sec)
    rep = report.build(snap, records, dry, _latest_compare(sec["scope"]))
    common.write_json(td / "report.json", rep)
    common.write_atomic(td / "report.md", report.render_md(rep).encode("utf-8"))
    if rep["asks"]:
        batch = sd / "asks" / ("%05d.md" % args.tick)
        common.write_atomic(batch, report.render_batch(rep).encode("utf-8"))
        ledger.append(sd, {"kind": "intent", "verb": "ask", "id": ledger.next_id(records, args.tick),
                           "key": "asks:%d" % args.tick, "scope": sec["scope"], "tick": args.tick, "dry_run": dry,
                           "target": {"batch": str(batch), "asks": rep["asks"]}})
    print(str(td / "report.md"))
    return 0


def _aq(s: str) -> str:
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, body: str) -> dict:
    """One osascript notification, and p9 notify when p9 is on PATH. Delivery
    can be observed and sight cannot, so an ask counts as seen only once acked."""
    out = {}
    if os.environ.get("FLEET_NOTIFY") == "0":
        return {"osascript": "disabled", "p9": "disabled"}
    osa = os.environ.get("FLEET_OSASCRIPT_BIN") or "osascript"
    try:
        out["osascript"] = subprocess.run([osa, "-e", "display notification %s with title %s" % (_aq(body), _aq(title))],
                                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, timeout=15).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        out["osascript"] = common.safe_text(str(exc), 80)
    p9 = os.environ.get("FLEET_P9_BIN") or shutil.which("p9")
    if p9:
        try:
            out["p9"] = subprocess.run([p9, "notify", title, "--body", body, "--kind", "fleet-ask"],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=30).returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            out["p9"] = common.safe_text(str(exc), 80)
    else:
        out["p9"] = "not on PATH"
    return out


def cmd_act(args: argparse.Namespace) -> int:
    sec = _sec(args)
    if args.verb != "ask":
        print("fleet act %s: refused: phase 1 is report-only; the verb lands in phase 2 (DRY_RUN) and acts only "
              "in phase 3" % args.verb, file=sys.stderr)
        return EXIT_REFUSED
    sd = config.state_dir(sec)
    records, _ = ledger.read(sd)
    batches = [b for b in ledger.ask_batches(records) if b["tick"] == args.tick]
    pending = ledger.unacked(records)
    if not args.notify:
        print("fleet act ask: %d open batch(es); pass --notify to notify" % len(pending))
        return 0
    now = time.time()
    go, why = report.should_notify(records, args.tick, sec["ask_renotify_h"], now)
    target = batches[-1] if batches else (pending[-1] if pending else None)
    if target is None:
        print("fleet act ask: nothing to notify (%s)" % why)
        return 0
    if not go:
        print("fleet act ask: not notified (%s)" % why)
        return 0
    n_open = sum(len(ledger.open_asks(b)) for b in pending)
    oldest = min((common.parse_iso(b["ts"]) or now) for b in pending) if pending else now
    first = (ledger.open_asks(target) or [{"question": ""}])[0]["question"]
    title = "fleet %s: %d open ask%s" % (sec["scope"], n_open, "" if n_open == 1 else "s")
    body = "%s | oldest %s | run: fleet asks" % (common.safe_text(first, 110), common.age(now - oldest))
    res = notify(title, body)
    res["notified"] = res.get("osascript") == 0 or res.get("p9") == 0
    res["why"] = why
    ledger.append(sd, {"kind": "done", "verb": "ask", "id": target["id"], "key": "asks:%s" % target["tick"],
                       "scope": sec["scope"], "tick": args.tick, "dry_run": _dry(args, sec), "result": res})
    print("fleet act ask: %s (%s)" % ("notified" if res["notified"] else "notification failed", why))
    return 0


def cmd_asks(args: argparse.Namespace) -> int:
    sec = _sec(args)
    records, corrupt = ledger.read(config.state_dir(sec))
    batches = ledger.ask_batches(records) if args.all else ledger.unacked(records)
    now = time.time()
    if not batches:
        print("fleet asks: no unacknowledged ask batches in scope %s" % sec["scope"])
    for b in batches:
        t = common.parse_iso(b["ts"]) or now
        asks = b["asks"] if args.all else ledger.open_asks(b)
        print("tick %s · %s ago · %d open · %s" % (b["tick"], common.age(now - t), len(ledger.open_asks(b)),
                                                   common.tilde(b["batch"])))
        for a in asks:
            print("  [%s] (%s) %s" % (a.get("id"), a.get("class"), a.get("question")))
    if corrupt:
        print("fleet asks: %d corrupt ledger line(s)" % corrupt, file=sys.stderr)
    return 0


def cmd_ack(args: argparse.Namespace) -> int:
    sec = _sec(args)
    sd = config.state_dir(sec)
    records, _ = ledger.read(sd)
    batches = [b for b in ledger.ask_batches(records) if b["tick"] == args.tick]
    if not batches:
        print("fleet ack: no ask batch for tick %d" % args.tick, file=sys.stderr)
        return 1
    ids = {a.get("id") for b in batches for a in b["asks"]}
    unknown = [a for a in args.ask or [] if a not in ids]
    if unknown:
        print("fleet ack: tick %d has no ask %s" % (args.tick, ", ".join(unknown)), file=sys.stderr)
        return 1
    ledger.append(sd, {"kind": "ack", "scope": sec["scope"], "tick": args.tick, "dry_run": False,
                       "acks": {"tick": args.tick, "asks": args.ask or "all"}})
    print("fleet ack: tick %d, %s" % (args.tick, ", ".join(args.ask) if args.ask else "all asks"))
    return 0


def cmd_ledger_record(args: argparse.Namespace) -> int:
    sec = _sec(args)
    rec = {"kind": "tick_fire" if args.what == "fire" else "runner_exit", "scope": sec["scope"], "tick": args.tick,
           "dry_run": args.dry_run != "0", "detail": args.detail or ""}
    if args.what == "exit":
        rec["exit_code"] = args.exit_code
    ledger.append(config.state_dir(sec), rec)
    return 0


def cmd_core_compare(args: argparse.Namespace) -> int:
    """Run the core's comparison (ctx doctor --compare) when the last one is
    more than 23 h old, or with --force. Its result goes to the core's
    compare.jsonl; the tick report quotes the latest line."""
    sec = _sec(args)
    last = _latest_compare(sec["scope"])
    if last and not args.force:
        t = common.parse_iso(last.get("ts"))
        if t and time.time() - t < 23 * 3600:
            print("fleet core-compare: last run %s ago; not due" % common.age(time.time() - t))
            return 0
    import ctx_compare

    return ctx_compare.run_for_scope(sec["scope"], hours=6.0, as_json=False)


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
    p.add_argument("--notify", action="store_true")
    p.add_argument("--dry-run", default=None, choices=("0", "1"))
    p.set_defaults(func=cmd_act)
    p = scoped(sub.add_parser("asks"))
    p.add_argument("--all", action="store_true", help="include acknowledged batches")
    p.set_defaults(func=cmd_asks)
    p = scoped(sub.add_parser("ack"))
    p.add_argument("tick", type=int)
    p.add_argument("--ask", action="append", help="one ask id (repeatable); default all")
    p.set_defaults(func=cmd_ack)
    p = scoped(sub.add_parser("ledger-record"))
    p.add_argument("what", choices=("fire", "exit"))
    p.add_argument("--tick", type=int, required=True)
    p.add_argument("--dry-run", default="1", choices=("0", "1"))
    p.add_argument("--exit-code", type=int, default=0)
    p.add_argument("--detail", default="")
    p.set_defaults(func=cmd_ledger_record)
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
