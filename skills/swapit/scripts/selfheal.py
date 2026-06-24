"""Swapit self-heal — validate knowledge graph + inventory integrity.

Mirrors the finance-substrate self-heal philosophy: detect data-quality issues, classify
by severity, and emit actionable suggestions an agent (or human) can fix. Exit non-zero on
any ``error`` so it can gate CI / pre-commit.

Checks
------
Knowledge (Realm 1):
  * every item_class.hazards[].hazard_id resolves to a hazard            (error)
  * every alternative.replaces[] resolves to an item_class               (error)
  * every alternative.avoids_hazards[] resolves to a hazard              (warn)
  * no duplicate ids within a file                                       (error)
  * every record carries >= 1 source (grounding discipline)              (warn)
  * severity in 0..3, confidence/presence_likelihood in 0..1             (warn)
  * item-classes with no swap path / hazards never referenced            (info)

Inventory (Realm 2):
  * item.item_class resolves to a known item-class                       (warn)
  * swap.item_id resolves to an existing item                            (error)
  * swap.chosen_alternative resolves to an alternative                   (warn)
  * bookmark.attached_to references resolve                              (info)
"""
from __future__ import annotations

import json

import state


def _finding(severity: str, code: str, message: str, suggestion: str = "") -> dict:
    return {"severity": severity, "code": code, "message": message, "suggestion": suggestion}


def _check_dupes(records: list[dict], label: str, findings: list[dict]) -> None:
    seen: set = set()
    for rec in records:
        rid = rec.get("id")
        if rid in seen:
            findings.append(_finding("error", "duplicate_id", f"{label}: duplicate id '{rid}'", "remove or rename one"))
        seen.add(rid)


def _in_range(val, lo, hi) -> bool:
    try:
        return lo <= float(val) <= hi
    except (TypeError, ValueError):
        return False


def run() -> list[dict]:
    findings: list[dict] = []

    if not state.is_initialized():
        return [_finding("error", "not_initialized", "swapit is not initialized", "run: swapit init")]

    kdir = state.knowledge_dir()
    try:
        hz = state.read_jsonl(kdir / "hazards.jsonl")
        ic = state.read_jsonl(kdir / "item-classes.jsonl")
        alt = state.read_jsonl(kdir / "alternatives.jsonl")
    except ValueError as exc:
        return [_finding("error", "json_parse", str(exc), "fix the malformed JSONL line")]

    for label, recs in (("hazards", hz), ("item-classes", ic), ("alternatives", alt)):
        for i, rec in enumerate(recs):
            if not rec.get("id"):
                findings.append(_finding("error", "missing_id", f"{label}[{i}] has no id", "add an id"))
    hazard_ids = {h["id"] for h in hz if h.get("id")}
    class_ids = {c["id"] for c in ic if c.get("id")}
    alt_ids = {a["id"] for a in alt if a.get("id")}

    _check_dupes(hz, "hazards", findings)
    _check_dupes(ic, "item-classes", findings)
    _check_dupes(alt, "alternatives", findings)

    # --- grounding + range checks
    for h in hz:
        if not h.get("sources"):
            findings.append(_finding("warn", "no_source", f"hazard '{h['id']}' has no source", "add an authoritative citation"))
        if not _in_range(h.get("severity"), 0, 3):
            findings.append(_finding("warn", "bad_severity", f"hazard '{h['id']}' severity out of 0..3", "set severity 0-3"))

    referenced_hazards: set[str] = set()
    classes_with_swap: set[str] = set()

    # --- edge integrity: item_class -> hazard
    for c in ic:
        if not c.get("sources"):
            findings.append(_finding("warn", "no_source", f"item-class '{c['id']}' has no source", "add a citation"))
        for edge in c.get("hazards", []):
            hid = edge.get("hazard_id")
            referenced_hazards.add(hid)
            if hid not in hazard_ids:
                findings.append(_finding("error", "broken_edge", f"item-class '{c['id']}' references unknown hazard '{hid}'", "add the hazard or fix the id"))
            if not _in_range(edge.get("presence_likelihood"), 0, 1):
                findings.append(_finding("warn", "bad_likelihood", f"item-class '{c['id']}' hazard '{hid}' presence_likelihood out of 0..1", "set 0-1"))

    # --- edge integrity: alternative -> item_class / hazard
    for a in alt:
        if not a.get("sources"):
            findings.append(_finding("warn", "no_source", f"alternative '{a['id']}' has no source", "add a citation"))
        for cid in a.get("replaces", []):
            classes_with_swap.add(cid)
            if cid not in class_ids:
                findings.append(_finding("error", "broken_edge", f"alternative '{a['id']}' replaces unknown item-class '{cid}'", "fix the item-class id"))
        for hid in a.get("avoids_hazards", []):
            if hid not in hazard_ids:
                findings.append(_finding("warn", "broken_edge", f"alternative '{a['id']}' avoids unknown hazard '{hid}'", "fix the hazard id"))

    # --- coverage (info)
    for hid in hazard_ids - referenced_hazards:
        findings.append(_finding("info", "unused_hazard", f"hazard '{hid}' is not referenced by any item-class", "ok — reference data, or add an item-class"))
    for cid in class_ids - classes_with_swap:
        findings.append(_finding("info", "no_swap_path", f"item-class '{cid}' has no alternative", "add an alternative that replaces it"))

    # --- inventory (Realm 2)
    try:
        items = state.load_items()
        swaps = state.load_swaps()
        bookmarks = state.load_bookmarks()
    except (ValueError, json.JSONDecodeError) as exc:
        findings.append(_finding("error", "corrupt_inventory", f"inventory file is corrupt: {exc}", "fix or restore the JSON document"))
        return findings
    for iid, item in items.items():
        cid = item.get("item_class")
        if cid and cid not in class_ids:
            findings.append(_finding("warn", "unknown_item_class", f"item '{iid}' uses unknown item-class '{cid}'", "add it to the knowledge graph or fix the id"))
    for sid, swap in swaps.items():
        if swap.get("item_id") not in items:
            findings.append(_finding("error", "orphan_swap", f"swap '{sid}' references missing item '{swap.get('item_id')}'", "remove the swap or restore the item"))
        ca = swap.get("chosen_alternative")
        if ca and ca not in alt_ids:
            findings.append(_finding("warn", "unknown_alternative", f"swap '{sid}' chose unknown alternative '{ca}'", "fix the alternative id"))
    for bid, bm in bookmarks.items():
        att = bm.get("attached_to")
        if att and att.get("type") == "item" and att.get("id") not in items:
            findings.append(_finding("info", "orphan_bookmark", f"bookmark '{bid}' attached to missing item '{att.get('id')}'", "reattach or detach"))

    return findings


def print_findings(findings: list[dict]) -> None:
    icon = {"error": "✗", "warn": "⚠", "info": "ℹ"}
    counts = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    if not findings:
        print("✓ self-heal: no issues")
        return
    for f in findings:
        line = f"{icon.get(f['severity'], '?')} [{f['severity']}] {f['message']}"
        if f.get("suggestion"):
            line += f"  → {f['suggestion']}"
        print(line)
    print(f"\n{counts['error']} error · {counts['warn']} warn · {counts['info']} info")
