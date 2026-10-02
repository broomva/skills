#!/usr/bin/env python3
"""fleet: the fleet-reconcile CLI (broomva/workspace
docs/specs/2026-09-29-fleet-reconcile-design.html, §5.7).

Phase 1 observes, classifies and reports; phase 2 adds the verbs under dry
run (mode act, dry_run 1); phase 3 runs them live. Stdlib
only. Run through scripts/fleet, which execs `python3 -I` so the tick's cwd and
the user site stay off sys.path; this file puts its own directory and
../ctx-core/scripts (the same checkout) there itself.

    fleet config-get <scope> <key>          one value; tick.sh reads errors as off and dry
    fleet config-check [<scope>]            exit 1 on any problem
    fleet observe --tick N                  write ticks/<N>/snapshot.json
    fleet report --tick N [--dry-run 0|1]   classify; write report.json, report.md and the ask batch
    fleet act ask --show [--tick N]         read answers back from Maestro; raise new batches there (Paseo)
    fleet act mail|spawn|label|resume       phase 2: re-check eligibility, intent, then dry or live (act.py)
    fleet recover [--tick N]                close intents a dead tick left open (recover.py)
    fleet send-gate pre|post                the coordinator's SendMessage hooks (sendgate.py)
    fleet coordinator --tick N              the coordinator's claude -p, in act mode (coordinator.py)
    fleet driver-profile --key K [--write]  a driver's 0600 settings file (profile.py)
    fleet janitor-check <path> --owner ID   the janitor's guard, failing closed (janitor.py)
    fleet janitor-run <path> --owner ID     check, stop, re-check, back up, remove (scratch only, for now)
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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    if args.init:
        # §5.7: the coordinator's stream-json init event against the pinned tool lists.
        from fleetlib import coordinator

        sec = config.scope(args.scope_id or os.environ.get("FLEET_SCOPE") or sorted(raw["scopes"])[0])
        try:
            ev = coordinator.init_event(Path(args.init).read_text(encoding="utf-8").splitlines())
        except OSError as exc:
            print("fleet config-check --init: %s" % exc, file=sys.stderr)
            return 1
        if ev is None:
            print("fleet config-check --init: no system/init event in %s" % args.init, file=sys.stderr)
            return 1
        probs = coordinator.posture_problems(ev.get("tools"), sec)
        for p in probs:
            print("fleet config-check --init: %s" % p, file=sys.stderr)
        if probs:
            return 1
        print("fleet config-check --init: %d tools, none disallowed or unclassified" % len(ev.get("tools") or []))
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


def _compare_state(scope_id: str) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """(why the daily comparison can't run, or None; the file's lines). The
    first line is read the way ctx doctor --compare reads it."""
    import ctx_compare

    first = ctx_compare.first_line(scope_id)
    if first is None:
        return "unreadable", []
    if ctx_compare.is_prototype(first):
        return "prototype", []
    lines = _compare_lines(scope_id)
    if not first.get("registered") or not lines:
        return "unregistered", lines
    return None, lines


def failed_in_a_row(lines: List[Dict[str, Any]]) -> int:
    """How many of compare.jsonl's last lines are errors, back to the latest run."""
    n = 0
    while n < len(lines) and "error" in lines[-1 - n]:
        n += 1
    return n


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
    refused, lines = _compare_state(sec["scope"])
    latest = None if refused else dict(lines[-1], failed_in_a_row=failed_in_a_row(lines))
    rep = report.build(snap, records, dry, {"refused": refused} if refused else latest)
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
# The ask channel, on Paseo (owner decision 2026-10-01; fleetlib/paseo_ask.py):
# each new batch becomes a Maestro work item at Needs you, and the owner's
# verdict there comes back as the answer. Never a desktop dialog.

def _open_now(records: list) -> Dict[str, Dict]:
    """Open asks: each tick records the ones it found no longer true, so what
    the ledger holds open is open (one whose surface wasn't read included)."""
    return ledger.open_by_key(records)


#: How long a raised batch's item is read back, from its latest raise: a note
#: sent after its asks stopped being true is still the owner's answer.
ASK_READ_DAYS = 14


def _ask_sync(sec: dict, sd: Path, records: list) -> Tuple[int, int]:
    """Read the owner's decisions back from every item raised (its latest
    raise) in the last ASK_READ_DAYS that isn't final, record each change of
    its state, and dispatch one left queued while an ask in its batch is still
    open: (answers recorded, failed reads and dispatches). Where an item
    stands is ledger.maestro_phase's one rule. A dispatch that leaves it
    queued (Maestro's run cap, or its loop starting it) is logged, not a
    failure; an item Maestro no longer has is recorded gone, which frees its
    batch to be raised again if an ask in it is still open."""
    from fleetlib import paseo_ask

    answered = failed = 0
    since = time.time() - ASK_READ_DAYS * 86400
    open_of = {v["of"] for v in ledger.open_by_key(records).values()}

    def seen(b: Dict[str, Any], state: str) -> None:
        ledger.append(sd, {"kind": "seen", "of": b["id"], "scope": sec["scope"], "tick": None, "dry_run": False,
                           "by": "tick", "result": {"channel": "maestro", "item": b["item"], "state": state}})

    def gone(b: Dict[str, Any]) -> None:
        print("fleet act ask: Maestro no longer has item %s of tick %s; its batch is raised again while an ask in "
              "it is open" % (b["item"], b["tick"]), file=sys.stderr)
        seen(b, "gone")

    for b in ledger.ask_batches(records):
        last = b.get("answer") or {}
        if not b.get("item") or ledger.maestro_phase(last.get("state")) == "final" \
                or (common.parse_iso(b.get("raised") or b["ts"]) or 0.0) < since:
            continue
        try:
            ans = paseo_ask.answer(sec, b["item"])
        except paseo_ask.MaestroError as exc:
            if exc.refusal == "gone":
                gone(b)
                continue
            print("fleet act ask: Maestro item %s of tick %s: %s" % (b["item"], b["tick"], exc), file=sys.stderr)
            failed += 1
            continue
        state = ans["state"]
        if ledger.maestro_phase(state) == "queued" and b["id"] in open_of:  # a cleared batch stays queued
            try:
                state = paseo_ask.start(sec, {"id": b["item"], "state": state}).get("state") or state
                if ledger.maestro_phase(state) == "queued":
                    print("fleet act ask: Maestro item %s of tick %s is still queued (its run cap, or its loop is "
                          "starting it)" % (b["item"], b["tick"]), file=sys.stderr)
            except paseo_ask.MaestroError as exc:
                if exc.refusal == "gone":
                    gone(b)
                    continue
                print("fleet act ask: Maestro item %s of tick %s not dispatched: %s" % (b["item"], b["tick"], exc),
                      file=sys.stderr)
                failed += 1
        if ledger.maestro_phase(state) and state != b.get("item_state"):  # however it moved: us, the owner, the loop
            seen(b, state)
        new = (ans["verdict"], ans["at"]) != (last.get("verdict"), last.get("at")) or \
            (ledger.maestro_phase(ans["state"]) == "final" and ledger.maestro_phase(last.get("state")) != "final")
        if ans["verdict"] and new:
            ledger.append(sd, {"kind": "ack", "of": b["id"], "asks": "all", "scope": sec["scope"], "tick": None,
                               "dry_run": False, "by": "owner:maestro",
                               "result": dict(ans, channel="maestro", item=b["item"])})
            answered += 1
        elif ans["state"] == "blocked":
            print("fleet act ask: Maestro item %s of tick %s is Stuck (its run failed); it shows there, and only "
                  "the owner can unblock or cancel it" % (b["item"], b["tick"]), file=sys.stderr)
    return answered, failed


def _ask_raise(args: argparse.Namespace, sec: dict, sd: Path, records: list,
               open_now: Dict[str, Dict]) -> Tuple[int, int, int]:
    """Raise each batch with no item (never raised, or its item gone) once an
    ask in it has been open for ask_raise_after_min (by default past the next
    hourly tick, so an ask a later tick found no longer true isn't raised):
    (raised, failed, waiting). An open item Maestro made for the batch (a
    `new` with no clear answer) is found by its title's marker and adopted. An
    item made but not started is recorded all the same, queued, and a later
    tick dispatches it; the failed start fails this step."""
    from fleetlib import paseo_ask

    raised = failed = waiting = 0
    tick = args.tick if args.tick else None
    now = time.time()
    for b in ledger.ask_batches(records):
        asks = [v["ask"] for v in open_now.values() if v["of"] == b["id"]]
        if b.get("item") or not asks:
            continue
        asked = common.parse_iso(b["ts"])
        if asked is not None and now - asked < sec.get("ask_raise_after_min", 50) * 60:
            waiting += 1
            continue
        n = len(asks)
        what = "%d fleet ask%s for scope %s (tick %s)" % (n, "" if n == 1 else "s", sec["scope"], b["tick"])
        tag = paseo_ask.marker(sec["scope"], "batch %s" % b["id"])
        title = "%d ask%s (tick %s) %s" % (n, "" if n == 1 else "s", b["tick"], tag)
        text = paseo_ask.brief(
            "fleet-reconcile has %s for the owner; `fleet asks --scope %s` lists them too." % (what, sec["scope"]),
            ["[%s] (%s) %s" % (a.get("id"), a.get("class"), a.get("question")) for a in asks],
            "%s are in this item's brief: approve to acknowledge them, send back a note to answer, cancel to "
            "dismiss" % what)
        try:
            item = paseo_ask.find(sec, tag, since=asked) or paseo_ask.raise_item(sec, title, text)
        except (paseo_ask.MaestroError, OSError, subprocess.SubprocessError) as exc:
            print("fleet act ask: batch of tick %s not raised: %s" % (b["tick"], common.safe_text(str(exc), 200)),
                  file=sys.stderr)
            failed += 1
            continue
        try:
            item = paseo_ask.start(sec, item)
            if ledger.maestro_phase(item.get("state")) == "queued":
                print("fleet act ask: batch of tick %s is queued in Maestro (its run cap, or its loop is starting "
                      "it); a later tick dispatches it" % b["tick"], file=sys.stderr)
        except paseo_ask.MaestroError as exc:
            print("fleet act ask: batch of tick %s raised as item %s but not started: %s; a later tick dispatches it"
                  % (b["tick"], item["id"], common.safe_text(str(exc), 200)), file=sys.stderr)
            failed += 1
        ledger.append(sd, {"kind": "seen", "of": b["id"], "scope": sec["scope"], "tick": tick,
                           "dry_run": _dry(args, sec), "by": "tick",
                           "result": {"channel": "maestro", "item": item["id"], "state": item.get("state")}})
        raised += 1
    return raised, failed, waiting


def cmd_alert(args: argparse.Namespace) -> int:
    """tick.sh's alert, through Python so an open item of its kind is adopted
    rather than a second raised. Exit 0: the item reached the owner (phase
    owner); 4: still queued (Maestro's run cap, or its loop is starting it;
    not delivered); 5: Maestro failed (not delivered; an item made but not
    started is adopted by the next alert of its kind). Any other exit (a
    config Python can't read) sends tick.sh to its bash fallback."""
    from fleetlib import paseo_ask

    sec = _sec(args)
    try:
        item = paseo_ask.start(sec, paseo_ask.alert(sec, args.kind, args.message))
    except (paseo_ask.MaestroError, OSError, subprocess.SubprocessError) as exc:
        print("fleet alert: not delivered: %s" % common.safe_text(str(exc), 200), file=sys.stderr)
        return 5
    print(json.dumps({"item": item.get("id"), "state": item.get("state"), "adopted": bool(item.get("adopted"))}))
    if ledger.maestro_phase(item.get("state")) == "queued":
        print("fleet alert: still queued in Maestro (its run cap, or its loop is starting it)", file=sys.stderr)
        return 4
    return 0


def _tick(args: argparse.Namespace) -> Optional[int]:
    if getattr(args, "tick", None):
        return args.tick
    t = os.environ.get("FLEET_TICK", "")
    return int(t) if t.isdigit() else None


def cmd_act_verb(args: argparse.Namespace, sec: dict) -> int:
    """mail, spawn, label, resume (fleetlib/act.py): one JSON line; exit 3 on a refusal."""
    from fleetlib import act

    if sec["mode"] != "act":  # before anything else, arguments included
        print("fleet act %s: refused: scope %s is in report mode (observe, classify and ask); every other verb "
              "waits for mode: act (§5.7)" % (args.verb, sec["scope"]), file=sys.stderr)
        return EXIT_REFUSED
    run = act.Act(sec, Sources(), _tick(args), _dry(args, sec))
    try:
        if args.verb == "mail":
            if not args.session:
                raise SystemExit("fleet act mail: --session is required")
            values = dict(v.split("=", 1) for v in args.var or [] if "=" in v)
            res = run.mail(args.session, args.template or "", values)
        elif args.verb == "spawn":
            if not (args.repo and args.pr):
                raise SystemExit("fleet act spawn: --repo and --pr are required")
            res = run.spawn(args.repo, args.pr, args.role)
        elif args.verb == "label":
            if not (args.repo and args.pr and args.label):
                raise SystemExit("fleet act label: --repo, --pr and --label are required")
            res = run.label(args.repo, args.pr, args.label, "remove" if args.remove else "add")
        else:
            if not args.session:
                raise SystemExit("fleet act resume: --session is required")
            res = run.resume(args.session)
    except act.ModeRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps(res, sort_keys=True))
    return 0 if res["ok"] else EXIT_REFUSED


def cmd_act(args: argparse.Namespace) -> int:
    sec = _sec(args)
    if args.verb != "ask":
        return cmd_act_verb(args, sec)
    sd = config.state_dir(sec)
    records, _ = ledger.read(sd)
    open_now = _open_now(records)
    if not args.show:
        print("fleet act ask: %d open ask(s); pass --show to raise them in Paseo" % len(open_now))
        return 0
    # ask runs in every mode and under dry_run: it reaches only the owner (§5.7).
    answered, read_failed = _ask_sync(sec, sd, records)
    records, _ = ledger.read(sd)
    open_now = _open_now(records)
    if os.environ.get("FLEET_NOTIFY") == "0":
        print("fleet act ask: %d answered; nothing raised (FLEET_NOTIFY=0)" % answered)
        return 1 if read_failed else 0
    raised, raise_failed, waiting = _ask_raise(args, sec, sd, records, open_now)
    print("fleet act ask: %d answer(s) read back from Maestro, %d batch(es) raised, %d waiting to see if they last, "
          "%d open ask(s)" % (answered, raised, waiting, len(_open_now(ledger.read(sd)[0]))))
    return 1 if read_failed or raise_failed else 0


def cmd_asks(args: argparse.Namespace) -> int:
    sec = _sec(args)
    sd = config.state_dir(sec)
    records, corrupt = ledger.read(sd)
    now = time.time()
    if args.all:
        states = ledger.key_states(records)
        for b in ledger.ask_batches(records):
            n = sum(1 for v in states.values() if v["of"] == b["id"] and v["state"] == "open")
            print("tick %s · %s · %s" % (b["tick"], b["ts"], "%d open, %s" % (n, "seen" if b["seen"] else "not seen")
                                         if n else "nothing open (answered or no longer true)"))
            for a in b["asks"]:
                print("  [%s] (%s) %s" % (a.get("id"), a.get("class"), a.get("question")))
    else:
        open_now = _open_now(records)
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
    opened = ledger.open_by_key(records).values()
    n = sum(1 for b, asks in targets for v in opened
            if v["of"] == b["id"] and (asks == "all" or v["ask"].get("id") in asks))
    for b, asks in targets:
        ledger.append(sd, {"kind": "ack", "of": b["id"], "asks": asks, "scope": sec["scope"], "tick": None,
                           "dry_run": False, "by": ledger.owner_by()})
    print("fleet ack: %d open ask(s) answered in %d batch(es)%s" % (
        n, len(targets), "" if n else "; nothing there was open (answered, no longer true, or asked again in a "
                                      "later batch: see fleet asks)"))
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    from fleetlib import recover

    sec = _sec(args)
    out = recover.recover(sec, Sources(), _tick(args))
    for r in out:
        print("fleet recover: %s %s %s -> %s%s" % (r["of"], r["verb"], r["key"], r["kind"],
                                                  " (%s)" % r["reason"] if r.get("reason") else ""))
    print("fleet recover: %d open intent(s) closed" % len(out))
    return 0


def cmd_send_gate(args: argparse.Namespace) -> int:
    """The coordinator's SendMessage hooks: the hook JSON on stdin; pre exits 2
    to block. A gate that can't read its input blocks too (pre) and records
    nothing it can't attribute (post)."""
    from fleetlib import sendgate

    # pre fails closed: any error, a config that can't be read included, is
    # exit 2, which blocks the send; any other exit lets the tool run.
    try:
        sec = _sec(args)
        try:
            hook = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            hook = {}
        hook = hook if isinstance(hook, dict) else {}
        if args.which == "pre":
            code, msg = sendgate.pre(sec, Sources(), hook, _tick(args), _dry(args, sec), time.time())
            if msg:
                print(msg, file=sys.stderr)
            return code
        sendgate.post(sec, hook, _tick(args), _dry(args, sec))
        return 0
    except BaseException as exc:  # noqa: B036 - SystemExit from the config read too
        if args.which != "pre":
            print("fleet send-gate post: %s" % common.safe_text(exc, 160), file=sys.stderr)
            return 0
        print("fleet send gate refused this SendMessage: the gate failed (%s: %s), so it fails closed" % (
            type(exc).__name__, common.safe_text(exc, 120)), file=sys.stderr)
        return 2


def cmd_coordinator(args: argparse.Namespace) -> int:
    from fleetlib import coordinator

    sec = _sec(args)
    if sec["mode"] != "act":
        print("fleet coordinator: scope %s is in report mode; no coordinator runs" % sec["scope"])
        return 0
    td = report.tick_dir(config.state_dir(sec), args.tick)
    fleet_bin = str(HERE / "fleet")
    res = coordinator.run(sec, args.tick, fleet_bin, td / "coordinator.jsonl", _dry(args, sec),
                          claude=os.environ.get("FLEET_CLAUDE_BIN") or "claude")
    if res["posture"]:
        print("fleet coordinator: terminated: %s" % "; ".join(res["posture"]), file=sys.stderr)
    elif not res["init"]:
        print("fleet coordinator: no init event (exit %s)" % res["exit"], file=sys.stderr)
    print("fleet coordinator: exit %s, init %s" % (res["exit"], "checked" if res["init"] else "missing"))
    return res["exit"] if res["exit"] else (0 if res["init"] else 1)


def cmd_driver_profile(args: argparse.Namespace) -> int:
    """Render a driver's profile; --write writes it 0600. It holds no token:
    a driver uses the owner's gh login (owner decision 2026-10-01)."""
    from fleetlib import profile

    sec = _sec(args)
    sd = config.state_dir(sec)
    prof = profile.driver_profile(sec, args.key)
    if args.write:
        print(str(profile.write(profile.path_for(sd, args.key), prof)))
    print(json.dumps(prof, indent=1, sort_keys=True))
    return 0


def cmd_janitor_check(args: argparse.Namespace) -> int:
    from fleetlib import janitor

    sec = _sec(args)
    res = janitor.Guard(sec, Sources(), args.path, args.owner).run()
    print(json.dumps(res, indent=1))
    return res["exit"]


def cmd_janitor_run(args: argparse.Namespace) -> int:
    from fleetlib import janitor

    sec = _sec(args)
    res = janitor.run(sec, Sources(), args.path, args.owner, args.remove,
                      lambda m: print("fleet janitor: %s" % m, file=sys.stderr))
    print(json.dumps(res, indent=1, default=str))
    if res.get("left"):  # removed, but its profile or gh dir is still there
        return 1
    return 0 if res.get("removed") or (not args.remove and not res.get("aborted")) else 1


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
    import ctx_compare

    refused, lines = _compare_state(sec["scope"])
    if refused:  # the report asks the owner
        print("fleet core-compare: not run (%s): %s" % (refused, report.COMPARE_REFUSALS[refused]))
        return 0
    now = time.time()
    if not args.force:
        ran = [ln for ln in lines if "error" not in ln]  # a failed run doesn't use up the day
        last = common.parse_iso(ran[-1].get("ts")) if ran else 0.0
        last = last or 0.0
        if time.localtime(last)[:3] == time.localtime(now)[:3] or time.localtime(now).tm_hour < sec["compare_hour"]:
            print("fleet core-compare: not due (last %s ago; runs once a day from %02d:00)"
                  % (common.age(now - last), sec["compare_hour"]))
            return 0

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
    p.add_argument("--init", default=None, help="check a coordinator's stream-json init event (a file)")
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
    p.add_argument("--show", action="store_true", help="ask: read answers back from Maestro and raise new batches")
    p.add_argument("--dry-run", default=None, choices=("0", "1"))
    p.add_argument("--session", default=None, help="mail, resume: the target's session id")
    p.add_argument("--template", default=None, help="mail: stalled, hung or overlap")
    p.add_argument("--var", action="append", help="mail: a template value, k=v (repeatable)")
    p.add_argument("--repo", default=None, help="spawn, label: owner/name")
    p.add_argument("--pr", type=int, default=None)
    p.add_argument("--role", default="driver", choices=("driver", "janitor", "research"))
    p.add_argument("--label", default=None)
    p.add_argument("--remove", action="store_true", help="label: remove instead of add")
    p.set_defaults(func=cmd_act)
    p = scoped(sub.add_parser("alert", help="tick.sh's alert to the owner in Maestro (exit 0 delivered)"))
    p.add_argument("--kind", required=True)
    p.add_argument("--message", required=True)
    p.set_defaults(func=cmd_alert)
    p = scoped(sub.add_parser("recover"))
    p.add_argument("--tick", type=int, default=0)
    p.set_defaults(func=cmd_recover)
    p = scoped(sub.add_parser("send-gate"))
    p.add_argument("which", choices=("pre", "post"))
    p.add_argument("--tick", type=int, default=0)
    p.add_argument("--dry-run", default=None, choices=("0", "1"))
    p.set_defaults(func=cmd_send_gate)
    p = scoped(sub.add_parser("coordinator"))
    p.add_argument("--tick", type=int, required=True)
    p.add_argument("--dry-run", default=None, choices=("0", "1"))
    p.set_defaults(func=cmd_coordinator)
    p = scoped(sub.add_parser("driver-profile"))
    p.add_argument("--key", required=True)
    p.add_argument("--write", action="store_true", help="write the 0600 file")
    p.set_defaults(func=cmd_driver_profile)
    p = scoped(sub.add_parser("janitor-check"))
    p.add_argument("path")
    p.add_argument("--owner", required=True, help="the owning background session's id")
    p.set_defaults(func=cmd_janitor_check)
    p = scoped(sub.add_parser("janitor-run"))
    p.add_argument("path")
    p.add_argument("--owner", required=True)
    p.add_argument("--remove", action="store_true", help="remove (scratch worktrees only until the drill passes)")
    p.set_defaults(func=cmd_janitor_run)
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
