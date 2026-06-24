#!/usr/bin/env python3
"""swapit — stateful household toxics inventory + swap engine.

Identify household items that carry endocrine disruptors / persistent chemicals
(BPA, phthalates, PFAS/PTFE, parabens, flame retardants, VOCs, microplastics),
prioritize what's worth replacing first (biggest exposure reduction), track the swap
from flagged -> sourced -> swapped, and hand off sourcing to the `procurer` skill.

Local-first. Zero paid services. The skill's state at ``~/.config/swapit`` is the
source of truth — the agent is the app.

Usage:
    swapit init
    swapit add --name "Non-stick frying pan" --class nonstick-cookware --room kitchen \\
               --condition scratched --frequency daily --food-contact --heat
    swapit list [--room kitchen] [--band high] [--status flagged] [--sort risk]
    swapit assess <item_id>            # or: swapit assess --class nonstick-cookware
    swapit swap <item_id> --to cast-iron-skillet --status sourced --add-task "buy 10in skillet"
    swapit score [--top 10]
    swapit report [--out report.html]
    swapit procure <item_id>
    swapit knowledge search bpa
    swapit selfheal
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import anonymize  # noqa: E402
import knowledge  # noqa: E402
import ops  # noqa: E402
import report as report_mod  # noqa: E402
import risk  # noqa: E402
import selfheal as selfheal_mod  # noqa: E402
import state  # noqa: E402
import sync as sync_mod  # noqa: E402

FREQ_CHOICES = ["daily", "weekly", "monthly", "occasional", "rare", "unused"]
CONDITION_CHOICES = ["new", "good", "aging", "worn", "scratched", "damaged", "sealed"]
STATUS_CHOICES = ["keep", "flagged", "swap-planned", "sourcing", "swapped", "disposed"]
PROCUREMENT_CHOICES = ["researching", "sourced", "purchased", "installed"]


# ----------------------------------------------------------------- shared helpers
def _require_init() -> None:
    if not state.is_initialized():
        sys.exit("swapit is not initialized. Run:  swapit init")


def assess_item(kn: knowledge.Knowledge, item: dict) -> dict:
    """Resolve an item against the knowledge graph: category, hazards, risk, swaps."""
    cid = item.get("item_class")
    cls = kn.item_class(cid) if cid else None
    category = cls.get("category", "misc") if cls else "misc"
    hazards = kn.hazards_for_class(cid) if cls else []
    rr = risk.score_item(item, hazards, category)
    alts = kn.alternatives_for_class(cid) if cls else []
    reductions = [risk.reduction_for_alternative(rr, a) for a in alts]
    reductions.sort(key=lambda x: x["pct"], reverse=True)
    return {
        "category": category,
        "class": cls,
        "class_known": cls is not None,
        "risk": rr,
        "alternatives": alts,
        "reductions": reductions,
    }


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------------ commands
def cmd_init(args: argparse.Namespace) -> int:
    state.ensure_dirs()
    written = knowledge.seed_into_data_root(force=args.force)
    rooms = state.load_rooms()
    if not rooms:
        rooms = list(state.DEFAULT_ROOMS)
        state.save_rooms(rooms)
    kn = knowledge.Knowledge()
    state.log_event("init", {"seeded": written, "force": args.force})
    print(f"✓ swapit initialized at {state.data_root()}")
    s = kn.stats()
    print(
        f"  knowledge: {s['hazards']} hazards · {s['item_classes']} item-classes · "
        f"{s['alternatives']} alternatives · {s['products']} products"
    )
    print(f"  rooms: {', '.join(rooms)}")
    if written:
        print(f"  seeded: {', '.join(written)}")
    print("\nNext:  swapit add --name \"...\" --class <id> --room <room>")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    _require_init()
    if args.quantity < 1:
        sys.exit("--quantity must be >= 1")
    kn = knowledge.Knowledge()
    if args.cls and not kn.item_class(args.cls):
        sugg = kn.search(args.cls, kind="item-class")[:5]
        hint = "  ".join(s["id"] for s in sugg)
        print(f"⚠ unknown item-class '{args.cls}'. Closest: {hint or '(none)'}", file=sys.stderr)
        print("  Adding anyway (run `swapit knowledge list --type item-class` to browse).", file=sys.stderr)
    item = ops.add_item(
        name=args.name,
        item_class=args.cls,
        room=args.room,
        quantity=args.quantity,
        brand=args.brand,
        acquired=args.acquired,
        condition=args.condition,
        usage={
            "frequency": args.frequency,
            "food_contact": args.food_contact,
            "heat": args.heat,
            "child_contact": args.child_contact,
        },
        status=args.status,
        notes=args.notes or "",
    )
    print(f"✓ added {item['id']}: {args.name}")
    _render_assessment(kn, item)
    return 0


def _render_assessment(kn: knowledge.Knowledge, item: dict) -> None:
    a = assess_item(kn, item)
    rr = a["risk"]
    print(f"\n{risk.band_emoji(rr['band'])} risk: {rr['score']}/100 ({rr['band']})  ·  category: {a['category']}")
    if not a["class_known"]:
        print("  (item-class not in knowledge graph — risk is a floor estimate)")
    if rr["contributions"]:
        print("  hazards:")
        for c in rr["contributions"]:
            if c["risk"] <= 0:
                continue
            print(f"    • {c['name']} — contribution {c['risk']}  ({c['rationale']})")
    if a["reductions"]:
        print("  swap options (by exposure removed):")
        for red in a["reductions"][:4]:
            print(f"    → {red['name']}  (−{red['pct']}% exposure)")
        print(f"\n  Next:  swapit swap {item['id']} --to {a['reductions'][0]['alternative_id']}")


def cmd_assess(args: argparse.Namespace) -> int:
    _require_init()
    kn = knowledge.Knowledge()
    if args.item_id:
        items = state.load_items()
        item = items.get(args.item_id)
        if not item:
            sys.exit(f"no item {args.item_id}")
    else:
        if not args.cls:
            sys.exit("assess needs an <item_id> or --class <id>")
        item = {
            "id": "(ad-hoc)",
            "name": args.name or args.cls,
            "item_class": args.cls,
            "condition": args.condition,
            "usage": {
                "frequency": args.frequency,
                "food_contact": args.food_contact,
                "heat": args.heat,
                "child_contact": args.child_contact,
            },
        }
    if args.json:
        _print_json({"item": item, "assessment": assess_item(kn, item)})
        return 0
    print(f"# {item['name']}  [{item.get('item_class')}]")
    _render_assessment(kn, item)
    return 0


def _item_rows(kn: knowledge.Knowledge, items: dict) -> list[dict]:
    rows = []
    for item in items.values():
        a = assess_item(kn, item)
        best = a["reductions"][0] if a["reductions"] else None
        rows.append({"item": item, "assessment": a, "best_swap": best})
    return rows


def cmd_list(args: argparse.Namespace) -> int:
    _require_init()
    kn = knowledge.Knowledge()
    items = state.load_items()
    rows = _item_rows(kn, items)

    if args.room:
        rows = [r for r in rows if r["item"].get("room") == args.room]
    if args.status:
        rows = [r for r in rows if r["item"].get("status") == args.status]
    if args.cls:
        rows = [r for r in rows if r["item"].get("item_class") == args.cls]
    if args.band:
        rows = [r for r in rows if r["assessment"]["risk"]["band"] == args.band]
    if args.hazard:
        rows = [
            r
            for r in rows
            if any(c["hazard_id"] == args.hazard for c in r["assessment"]["risk"]["contributions"])
        ]

    if args.sort == "name":
        rows.sort(key=lambda r: r["item"].get("name", "").lower())
    elif args.sort == "room":
        rows.sort(key=lambda r: (r["item"].get("room") or "", -r["assessment"]["risk"]["score"]))
    else:  # risk
        rows.sort(key=lambda r: r["assessment"]["risk"]["score"], reverse=True)

    if args.json:
        _print_json(
            [
                {
                    "id": r["item"]["id"],
                    "name": r["item"]["name"],
                    "room": r["item"].get("room"),
                    "status": r["item"].get("status"),
                    "score": r["assessment"]["risk"]["score"],
                    "band": r["assessment"]["risk"]["band"],
                    "best_swap": r["best_swap"],
                }
                for r in rows
            ]
        )
        return 0

    if not rows:
        print("(no items match)")
        return 0
    print(f"{'':2} {'SCORE':>5}  {'ID':<12} {'ROOM':<12} {'STATUS':<12} NAME")
    for r in rows:
        rr = r["assessment"]["risk"]
        print(
            f"{risk.band_emoji(rr['band'])} {rr['score']:>5}  {r['item']['id']:<12} "
            f"{(r['item'].get('room') or '-'):<12} {(r['item'].get('status') or '-'):<12} {r['item']['name']}"
        )
    return 0


def cmd_swap(args: argparse.Namespace) -> int:
    _require_init()
    kn = knowledge.Knowledge()
    if args.item_id not in state.load_items():
        sys.exit(f"no item {args.item_id}")

    if args.to:
        if not kn.alternative(args.to):
            print(f"⚠ unknown alternative '{args.to}'", file=sys.stderr)
        ops.choose_alternative(args.item_id, args.to)
    if args.procurement or args.cost is not None or args.vendor:
        ops.update_procurement(args.item_id, status=args.procurement, cost=args.cost, vendor=args.vendor)
    if args.add_task:
        ops.add_task(args.item_id, args.add_task)
    if args.check:
        ops.set_task_done(args.item_id, args.check, True)
    if args.uncheck:
        ops.set_task_done(args.item_id, args.uncheck, False)
    if args.bookmark:
        ops.add_swap_bookmark(args.item_id, args.bookmark, args.title)
    if args.status:
        ops.set_item_status(args.item_id, args.status)
    if args.complete:
        ops.complete_swap(args.item_id)

    item = state.load_items()[args.item_id]
    swap = ops.find_swap(args.item_id) or {
        "chosen_alternative": None,
        "procurement": {"status": "researching", "cost": None, "vendor": None},
        "checklist": [],
        "bookmarks": [],
    }
    if args.json:
        _print_json(swap)
        return 0
    _render_swap(item, swap)
    return 0


def _render_swap(item: dict, swap: dict) -> None:
    print(f"# swap for {item['name']}  [{item['id']}]")
    print(f"  status: {item.get('status')}  ·  target: {swap.get('chosen_alternative') or '(none chosen)'}")
    proc = swap["procurement"]
    print(f"  procurement: {proc['status']}" + (f"  ·  ${proc['cost']} @ {proc['vendor']}" if proc.get("cost") else ""))
    if swap["checklist"]:
        print("  checklist:")
        for t in swap["checklist"]:
            print(f"    [{'x' if t['done'] else ' '}] {t['text']}")
    if swap["bookmarks"]:
        bms = state.load_bookmarks()
        print("  bookmarks:")
        for bid in swap["bookmarks"]:
            b = bms.get(bid)
            if b:
                print(f"    🔖 {b.get('title') or b['url']} — {b['url']}")
    if swap.get("completed"):
        print(f"  ✓ completed {swap['completed']}")


def cmd_bookmark(args: argparse.Namespace) -> int:
    _require_init()
    if args.list:
        bms = state.load_bookmarks()
        if not bms:
            print("(no bookmarks)")
            return 0
        for b in bms.values():
            attach = b.get("attached_to")
            tag = f" [{attach['type']}:{attach['id']}]" if attach else ""
            print(f"🔖 {b['id']}  {b.get('title') or b['url']} — {b['url']}{tag}")
        return 0
    if not args.url:
        sys.exit("bookmark needs --url or --list")
    attached = None
    if args.item:
        attached = {"type": "item", "id": args.item}
    elif args.swap:
        attached = {"type": "swap", "id": args.swap}
    bid = ops.add_bookmark(args.url, args.title, attached)
    print(f"✓ bookmarked {bid}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    _require_init()
    kn = knowledge.Knowledge()
    items = state.load_items()
    rows = _item_rows(kn, items)
    summary = report_mod.household_summary(rows)

    if args.json:
        _print_json(summary)
        return 0

    print("# Household exposure summary")
    print(f"  items: {summary['total']}  ·  🔴 {summary['bands']['high']}  🟠 {summary['bands']['medium']}  🟢 {summary['bands']['low']}")
    print(f"  addressed: {summary['addressed']}/{summary['total']}  ·  exposure reduction available: {summary['reduction_available']} pts")
    print("\n## Swap these first")
    swap_first = [r for r in rows if r["item"].get("status") not in ("swapped", "disposed", "keep")]
    swap_first.sort(key=lambda r: r["assessment"]["risk"]["score"], reverse=True)
    for r in swap_first[: args.top]:
        rr = r["assessment"]["risk"]
        best = r["best_swap"]
        line = f"  {risk.band_emoji(rr['band'])} {rr['score']:>3}  {r['item']['name']} ({r['item'].get('room') or '-'})"
        if best:
            line += f"  →  {best['name']} (−{best['pct']}%)"
        print(line)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    _require_init()
    kn = knowledge.Knowledge()
    items = state.load_items()
    rows = _item_rows(kn, items)
    html = report_mod.render_report(rows, kn)
    out = Path(args.out).expanduser() if args.out else (state.data_root() / "report.html")
    out.write_text(html, encoding="utf-8")
    print(f"✓ report → {out}")
    if args.open:
        webbrowser.open(out.as_uri())
    return 0


def cmd_procure(args: argparse.Namespace) -> int:
    """Build a procurer brief for an item's swap — the handoff to the `procurer` skill."""
    _require_init()
    kn = knowledge.Knowledge()
    items = state.load_items()
    item = items.get(args.target)
    if not item:
        swaps = state.load_swaps()
        swap = swaps.get(args.target)
        if swap:
            item = items.get(swap["item_id"])
    if not item:
        sys.exit(f"no item or swap {args.target}")
    a = assess_item(kn, item)
    chosen = None
    swaps = state.load_swaps()
    swap = next((s for s in swaps.values() if s["item_id"] == item["id"]), None)
    if swap and swap.get("chosen_alternative"):
        chosen = kn.alternative(swap["chosen_alternative"])
    targets = [chosen] if chosen else a["alternatives"][:3]
    locale = os.environ.get("SWAPIT_LOCALE", "your region")

    hazards = ", ".join(c["name"] for c in a["risk"]["contributions"] if c["risk"] > 0) or "—"
    brief = {
        "need": f"Replace {item['name']} ({item.get('item_class')}) — currently carries {hazards}.",
        "alternatives": [t["name"] for t in targets if t],
        "locale": locale,
        "quantity": item.get("quantity", 1),
    }
    if args.json:
        _print_json(brief)
        return 0
    print("# Procurer handoff brief")
    print(f"Need:        {brief['need']}")
    print(f"Replace with: {', '.join(brief['alternatives']) or '(assess for options)'}")
    print(f"Quantity:    {brief['quantity']}   ·   Locale: {locale}")
    print("\nHand this to the `procurer` skill, e.g.:")
    alt = brief["alternatives"][0] if brief["alternatives"] else "a safer alternative"
    print(f'  procurer: "Where can I buy {brief["quantity"]}× {alt} in {locale}, and what should it cost?"')
    return 0


def cmd_knowledge(args: argparse.Namespace) -> int:
    _require_init()
    kn = knowledge.Knowledge()
    if args.ksub == "search":
        results = kn.search(args.query or "", kind=args.type)
        if args.json:
            _print_json(results)
            return 0
        for r in results[:30]:
            print(f"[{r['kind']}] {r['id']} — {r.get('name')}")
        if not results:
            print("(no matches)")
        return 0
    if args.ksub == "show":
        if args.type:
            lookup = {"hazard": kn.hazard, "item-class": kn.item_class, "alternative": kn.alternative}
            rec = lookup[args.type](args.query)
        else:
            rec = kn.hazard(args.query) or kn.item_class(args.query) or kn.alternative(args.query)
        if not rec:
            sys.exit(f"no knowledge node '{args.query}'")
        _print_json(rec)
        return 0
    # list
    pools = {
        "hazard": kn.hazards,
        "item-class": kn.item_classes,
        "alternative": kn.alternatives,
    }
    for kind, pool in pools.items():
        if args.type and kind != args.type:
            continue
        print(f"## {kind} ({len(pool)})")
        for rec in pool.values():
            print(f"  {rec['id']:<26} {rec.get('name')}")
    return 0


def cmd_rooms(args: argparse.Namespace) -> int:
    _require_init()
    rooms = state.load_rooms()
    if args.add:
        if args.add not in rooms:
            rooms.append(args.add)
            state.save_rooms(rooms)
            print(f"✓ added room {args.add}")
        return 0
    print("\n".join(rooms) if rooms else "(no rooms)")
    return 0


def cmd_selfheal(args: argparse.Namespace) -> int:
    findings = selfheal_mod.run()
    if args.json:
        _print_json(findings)
    else:
        selfheal_mod.print_findings(findings)
    errors = [f for f in findings if f["severity"] == "error"]
    return 1 if errors else 0


def cmd_serve(args: argparse.Namespace) -> int:
    _require_init()
    import server  # lazy import — avoids the server<->swapit cycle at module load

    server.serve(port=args.port, open_browser=not args.no_open)
    return 0


def _require(cond: bool, msg: str) -> None:
    if not cond:
        sys.exit(f"contribute: {msg}")


def cmd_contribute(args: argparse.Namespace) -> int:
    """Build a generic, anonymized knowledge fact, apply it locally, and queue it for sync."""
    _require_init()
    kn = knowledge.Knowledge()
    if args.ksub == "product":
        _require(bool(args.name and args.cls), "product needs --name and --class")
        _require(kn.item_class(args.cls) is not None, f"unknown item-class '{args.cls}'")
        for h in args.hazard or []:
            _require(kn.hazard(h) is not None, f"unknown hazard '{h}'")
    elif args.ksub == "hazard":
        _require(bool(args.cls and args.hazard_id) and args.likelihood is not None,
                 "hazard needs --class, --hazard-id and --likelihood")
        _require(kn.item_class(args.cls) is not None, f"unknown item-class '{args.cls}'")
        _require(kn.hazard(args.hazard_id) is not None, f"unknown hazard '{args.hazard_id}'")
        _require(0.0 <= args.likelihood <= 1.0, "--likelihood must be 0..1")
    else:
        _require(bool(args.name and args.replaces and args.avoids),
                 "alternative needs --name, --replaces and --avoids")
        for c in args.replaces:
            _require(kn.item_class(c) is not None, f"unknown item-class '{c}'")
        for h in args.avoids:
            _require(kn.hazard(h) is not None, f"unknown hazard '{h}'")
    if args.ksub == "product":
        fact = anonymize.product_fact(
            product_name=args.name, item_class=args.cls, brand=args.brand, gtin=args.gtin,
            observed_hazards=args.hazard or [], recycling_code=args.recycling_code,
            label_terms=args.label_term or [], confidence=args.confidence,
        )
    elif args.ksub == "hazard":
        fact = anonymize.hazard_presence_fact(
            item_class=args.cls, hazard_id=args.hazard_id, presence_likelihood=args.likelihood,
            rationale=args.rationale or "", source_url=args.source_url, source_title=args.source_title,
            confidence=args.confidence,
        )
    else:  # alternative
        fact = anonymize.alternative_fact(
            name=args.name, replaces=args.replaces, avoids_hazards=args.avoids or [],
            material=args.material or "", rationale=args.rationale or "", source_url=args.source_url,
            confidence=args.confidence,
        )
    sync_mod.enqueue(fact)          # privacy-gated queue for the commons
    sync_mod.merge_incoming([fact])  # apply locally so you benefit immediately
    if args.json:
        _print_json(fact)
        return 0
    print(f"✓ queued {fact['kind']} fact {fact['id']} (and applied locally)")
    leaks = anonymize.scan_for_forbidden(fact)
    if leaks:
        print(f"  ⚠ leaks: {leaks}")
    else:
        print("  privacy: ✓ no inventory-structural fields. Note: free-text (name/brand/rationale) is")
        print("           sent verbatim — keep it generic and public. Preview:  swapit sync --dry-run")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    _require_init()
    if args.configure:
        endpoint = sync_mod.BROOMVA_COMMONS if args.broomva else args.endpoint
        cfg = sync_mod.configure(endpoint=endpoint, token=args.token, opt_in=True if args.opt_in else None)
        print(f"✓ sync configured · endpoint={cfg.get('endpoint')} · opt_in={cfg.get('opt_in')}")
        return 0
    if args.status:
        cfg = sync_mod.load_config()
        q = sync_mod.queued()
        _print_json({"endpoint": cfg.get("endpoint"), "opt_in": cfg.get("opt_in"),
                     "last_sync": cfg.get("last_sync"), "queued": len(q)})
        return 0
    if args.dry_run:
        preview = sync_mod.dry_run()
        if args.json:
            _print_json(preview)
            return 0
        if not preview:
            print("(contribution queue is empty)")
            return 0
        print(f"# {len(preview)} fact(s) would be sent to the commons. Your private inventory is never sent —")
        print("# only these generic facts. Free-text fields below are sent verbatim; review them:\n")
        for p in preview:
            flag = "✓ no structural leaks" if p["clean"] else f"⚠ LEAKS {p['leaks']}"
            print(f"[{flag}] {p['kind']} {p['id']}")
            print(f"  {json.dumps(p['payload'], ensure_ascii=False)}")
        return 0
    # real sync
    try:
        result = sync_mod.push_pull()
    except RuntimeError as exc:
        sys.exit(str(exc))
    print(f"✓ sync · pushed {result['pushed']} · pulled {result['pulled']} · merged {result['merged']}")
    return 0


# ------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="swapit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="initialize state + load seed knowledge")
    sp.add_argument("--force", action="store_true", help="overwrite existing knowledge cache with seed")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("add", help="add a household item")
    sp.add_argument("--name", required=True)
    sp.add_argument("--class", dest="cls", required=True, help="item-class id (see `knowledge list`)")
    sp.add_argument("--room")
    sp.add_argument("--quantity", type=int, default=1)
    sp.add_argument("--brand")
    sp.add_argument("--acquired", help="ISO date acquired")
    sp.add_argument("--condition", choices=CONDITION_CHOICES, default="good")
    sp.add_argument("--frequency", choices=FREQ_CHOICES, default="occasional")
    sp.add_argument("--food-contact", dest="food_contact", action="store_true")
    sp.add_argument("--heat", action="store_true", help="used with heat (cooking, hot liquids)")
    sp.add_argument("--child-contact", dest="child_contact", action="store_true")
    sp.add_argument("--status", choices=STATUS_CHOICES, default="flagged")
    sp.add_argument("--notes")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("assess", help="assess an item or an ad-hoc item-class")
    sp.add_argument("item_id", nargs="?")
    sp.add_argument("--class", dest="cls")
    sp.add_argument("--name")
    sp.add_argument("--condition", choices=CONDITION_CHOICES, default="good")
    sp.add_argument("--frequency", choices=FREQ_CHOICES, default="occasional")
    sp.add_argument("--food-contact", dest="food_contact", action="store_true")
    sp.add_argument("--heat", action="store_true")
    sp.add_argument("--child-contact", dest="child_contact", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_assess)

    sp = sub.add_parser("list", help="list inventory items")
    sp.add_argument("--room")
    sp.add_argument("--status", choices=STATUS_CHOICES)
    sp.add_argument("--class", dest="cls")
    sp.add_argument("--band", choices=["high", "medium", "low"])
    sp.add_argument("--hazard", help="filter to items carrying this hazard id")
    sp.add_argument("--sort", choices=["risk", "name", "room"], default="risk")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("swap", help="create / update a swap plan for an item")
    sp.add_argument("item_id")
    sp.add_argument("--to", help="chosen alternative id")
    sp.add_argument("--status", choices=STATUS_CHOICES)
    sp.add_argument("--procurement", choices=PROCUREMENT_CHOICES)
    sp.add_argument("--cost", type=float)
    sp.add_argument("--vendor")
    sp.add_argument("--add-task", dest="add_task")
    sp.add_argument("--check", help="task id or text to mark done")
    sp.add_argument("--uncheck", help="task id or text to mark undone")
    sp.add_argument("--bookmark", help="URL to save")
    sp.add_argument("--title", help="bookmark title")
    sp.add_argument("--complete", action="store_true", help="mark swap complete (item -> swapped)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_swap)

    sp = sub.add_parser("bookmark", help="save a source/vendor link")
    sp.add_argument("--url")
    sp.add_argument("--title")
    sp.add_argument("--item", help="attach to item id")
    sp.add_argument("--swap", help="attach to swap id")
    sp.add_argument("--list", action="store_true")
    sp.set_defaults(func=cmd_bookmark)

    sp = sub.add_parser("score", help="household exposure summary + swap-first ranking")
    sp.add_argument("--top", type=int, default=10)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_score)

    sp = sub.add_parser("report", help="generate the static HTML report")
    sp.add_argument("--out", help="output path (default: <data root>/report.html)")
    sp.add_argument("--open", action="store_true", help="open in browser")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("procure", help="emit a procurer handoff brief for an item/swap")
    sp.add_argument("target", help="item id or swap id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_procure)

    sp = sub.add_parser("knowledge", help="browse the knowledge graph")
    sp.add_argument("ksub", nargs="?", choices=["list", "search", "show"], default="list")
    sp.add_argument("query", nargs="?")
    sp.add_argument("--type", choices=["hazard", "item-class", "alternative"])
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_knowledge)

    sp = sub.add_parser("rooms", help="list or add rooms")
    sp.add_argument("--add")
    sp.set_defaults(func=cmd_rooms)

    sp = sub.add_parser("selfheal", help="validate knowledge + inventory integrity")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_selfheal)

    sp = sub.add_parser("serve", help="launch the live local dashboard (the agent is the app)")
    sp.add_argument("--port", type=int, default=8731, help="localhost port (default 8731)")
    sp.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("contribute", help="queue an anonymized knowledge fact for the commons")
    sp.add_argument("ksub", choices=["product", "hazard", "alternative"], help="fact kind")
    sp.add_argument("--name", help="product or alternative name (public)")
    sp.add_argument("--class", dest="cls", help="item-class id (product/hazard)")
    sp.add_argument("--brand", help="public product brand (product)")
    sp.add_argument("--gtin", help="barcode (product)")
    sp.add_argument("--hazard", action="append", help="observed hazard id (product; repeatable)")
    sp.add_argument("--recycling-code", dest="recycling_code")
    sp.add_argument("--label-term", dest="label_term", action="append")
    sp.add_argument("--hazard-id", dest="hazard_id", help="hazard id (hazard fact)")
    sp.add_argument("--likelihood", type=float, help="presence likelihood 0-1 (hazard fact)")
    sp.add_argument("--rationale")
    sp.add_argument("--replaces", action="append", help="item-class id replaced (alternative; repeatable)")
    sp.add_argument("--avoids", action="append", help="hazard id avoided (alternative; repeatable)")
    sp.add_argument("--material")
    sp.add_argument("--source-url", dest="source_url")
    sp.add_argument("--source-title", dest="source_title")
    sp.add_argument("--confidence", type=float, default=0.7)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_contribute)

    sp = sub.add_parser("sync", help="push/pull the anonymized knowledge commons (opt-in)")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true", help="preview exactly what would be sent")
    sp.add_argument("--configure", action="store_true", help="set endpoint/token and opt in")
    sp.add_argument("--endpoint", help="commons base URL")
    sp.add_argument("--broomva", action="store_true", help="use the hosted broomva.tech commons")
    sp.add_argument("--token", help="anonymous contributor token")
    sp.add_argument("--opt-in", dest="opt_in", action="store_true", help="enable syncing")
    sp.add_argument("--status", action="store_true", help="show sync config + queue size")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_sync)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, json.JSONDecodeError) as exc:
        print(
            f"swapit: data error — {exc}\n  → run `swapit selfheal` to locate and fix it.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
