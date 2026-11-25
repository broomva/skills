#!/usr/bin/env python3
"""checkable: can this problem be handed to agents and the result relied on?

A *statement* writes a problem as claims, the check behind each claim, the
actions the work may take and what stays unverified. This tool refuses a
statement that breaks one of eight invariants. It never judges whether the
claims are the right claims; that is a reader's job.

    checkable.py check   <statement> [--base REV] [--json]
    checkable.py replay  <statement> [--cwd DIR] [--timeout S] [--json]
    checkable.py route   <statement> [--index FILE] [--json]
    checkable.py index   [--index FILE] [--root DIR] [--json]

Exit codes: 0 holds, 1 a finding, 2 the input could not be read or a control
did not behave, 3 a comparison that was asked for could not be made.

Statements are JSON, or YAML when PyYAML is installed. Standard library only
otherwise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

RUNGS = ("proof", "replay", "measurement", "judgment", "track-record", "none")
COMMAND_RUNGS = ("proof", "replay")
PARTS = (
    "ontology",
    "claims",
    "verifiers",
    "evidence",
    "shield",
    "flow",
    "performers",
    "learning",
    "base",
)
REVERSIBILITY = ("reversible", "compensable", "irreversible")
ORIGIN_KINDS = ("code", "sensor", "model", "human")
STATUSES = ("open", "accepted", "refuted")

# What a verifier must carry so that it can fail, per rung. The measurement
# names follow bstack's `measurement` record contract.
FALSIFIER = {
    "proof": ("check", "rejects"),
    "replay": ("check", "rejects"),
    "measurement": ("sensor", "positive_control", "falsification_criterion"),
    "judgment": ("rubric", "pass_rule"),
    "track-record": ("prediction_recorded", "scored_by"),
}

INVARIANTS = {
    "C0": "the statement is well formed",
    "C1": "the claims match the base revision",
    "C2": "an accepted claim carries a receipt that can be replayed",
    "C3": "every check can fail",
    "C4": "a verifier's origin differs from the performer's",
    "C5": "step order is declared, not remembered",
    "C6": "every action has a reversibility class and irreversible ones a gate",
    "C7": "every output that becomes an input passes a check",
    "C8": "what stays unverified is written down",
}

EXIT_OK, EXIT_FINDING, EXIT_INVALID, EXIT_NO_COMPARISON = 0, 1, 2, 3


class InputError(Exception):
    """The statement or index could not be read."""


def parse(text: str, suffix: str, label: str) -> dict:
    if suffix.lower() == ".json":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputError(f"{label} is not valid JSON: {exc}") from exc
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise InputError(
                f"{label} is YAML and PyYAML is not installed; "
                "`pip install pyyaml` or write the statement as .json"
            ) from exc
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise InputError(f"{label} is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise InputError(f"{label} must hold a mapping at the top level")
    return doc


def load_doc(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    return parse(text, path.suffix, str(path))


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _items(doc: dict, key: str) -> list:
    value = doc.get(key)
    return value if isinstance(value, list) else []


def claim_definitions(doc: dict) -> str:
    """The part of the claims a performer must not change: what is asserted
    and how it is checked. Status and receipts move as the work proceeds."""
    kept = []
    for claim in _items(doc, "claims"):
        if isinstance(claim, dict):
            kept.append({k: claim.get(k) for k in ("id", "text", "rung", "verifier")})
    kept.sort(key=lambda c: str(c.get("id")))
    return json.dumps(kept, sort_keys=True, ensure_ascii=False)


def pin_state(path: Path, base: str | None, doc: dict) -> tuple[str, str]:
    """pinned | changed | absent | unknown, with a sentence saying why."""
    if not base:
        return "unknown", "no --base revision was given"
    folder = path.resolve().parent
    top = subprocess.run(
        ["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if top.returncode != 0:
        return "unknown", f"{folder} is not inside a git repository"
    root = Path(top.stdout.strip())
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    shown = subprocess.run(
        ["git", "-C", str(root), "show", f"{base}:{rel}"],
        capture_output=True,
        text=True,
    )
    if shown.returncode != 0:
        known = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],
            capture_output=True,
            text=True,
        )
        if known.returncode != 0:
            return "unknown", f"revision {base} does not exist in this repository"
        return "absent", f"{rel} does not exist at {base}"
    try:
        base_doc = parse(shown.stdout, path.suffix, f"{base}:{rel}")
    except InputError as exc:
        return "unknown", f"the copy at {base} could not be read: {exc}"
    if claim_definitions(base_doc) == claim_definitions(doc):
        return "pinned", f"claims match {base}"
    return "changed", f"claims differ from {base}"


def _origin(value) -> tuple[str, str] | None:
    if not _text(value):
        return None
    kind, _, name = value.partition(":")
    if kind not in ORIGIN_KINDS:
        return None
    if kind != "code" and not name.strip():
        return None
    return kind, name.strip()


def check(doc: dict, pin: tuple[str, str]) -> list[dict]:
    findings: list[dict] = []

    def add(invariant: str, level: str, where: str, message: str) -> None:
        findings.append({"invariant": invariant, "level": level, "where": where, "message": message})

    # C0: shape
    if doc.get("checkable") != 1:
        add("C0", "FAIL", "checkable", "must be 1, the statement format version")
    if not _text(doc.get("problem")):
        add("C0", "FAIL", "problem", "state the problem in one sentence")
    performers = [p for p in _items(doc, "performers") if _text(p)]
    if not performers:
        add("C0", "FAIL", "performers", "name who does the work, e.g. model:anthropic")
    for performer in performers:
        parsed = _origin(performer)
        if parsed is None or parsed[0] not in ("model", "human"):
            add("C0", "FAIL", f"performers.{performer}", "write a performer as model:<provider> or human:<role>")
    claims = [c for c in _items(doc, "claims") if isinstance(c, dict)]
    if not claims:
        add("C0", "FAIL", "claims", "a statement with no claims asserts nothing")
    by_id: dict[str, dict] = {}
    for position, claim in enumerate(claims):
        cid = claim.get("id")
        where = f"claims.{cid if _text(cid) else position}"
        if not _text(cid):
            add("C0", "FAIL", where, "every claim needs an id")
            continue
        if cid in by_id:
            add("C0", "FAIL", where, "claim ids must be unique")
        by_id[cid] = claim
        if not _text(claim.get("text")):
            add("C0", "FAIL", where, "say what the claim asserts")
        if claim.get("rung") not in RUNGS:
            add("C0", "FAIL", where, f"rung must be one of {', '.join(RUNGS)}")
        if claim.get("status", "open") not in STATUSES:
            add("C0", "FAIL", where, f"status must be one of {', '.join(STATUSES)}")

    accepted = [c for c in claims if c.get("status") == "accepted"]

    # C1: the base declares the claims
    state, why = pin
    if state == "changed":
        add("C1", "FAIL", "claims", f"{why}; a change to a claim lands on the base first")
    elif state != "pinned":
        if accepted:
            add("C1", "FAIL", "claims", f"{len(accepted)} claim(s) are accepted but the claims are not pinned: {why}")
        else:
            add("C1", "WARN", "claims", f"not pinned yet: {why}")

    for claim in claims:
        cid = claim.get("id")
        if not _text(cid):
            continue
        where = f"claims.{cid}"
        rung = claim.get("rung")
        status = claim.get("status", "open")
        verifier = claim.get("verifier") if isinstance(claim.get("verifier"), dict) else {}

        # C2: receipts
        receipt = claim.get("receipt") if isinstance(claim.get("receipt"), dict) else {}
        if status in ("accepted", "refuted"):
            for field in ("revision", "replay", "result"):
                if not _text(receipt.get(field)):
                    add("C2", "FAIL", where, f"{status} without receipt.{field}")
            wanted = "pass" if status == "accepted" else "fail"
            if _text(receipt.get("result")) and receipt.get("result") != wanted:
                add("C2", "FAIL", where, f"{status} needs receipt.result: {wanted}")
            if status == "accepted" and rung == "none":
                add("C2", "FAIL", where, "a claim with no check cannot be accepted; it stays in `unverified`")

        if rung not in RUNGS or rung == "none":
            continue

        # C3: the check can fail
        for field in FALSIFIER[rung]:
            if not _text(verifier.get(field)):
                add("C3", "FAIL", where, f"a {rung} check needs verifier.{field}")

        # C4: independence
        origin = _origin(verifier.get("origin"))
        if origin is None:
            add("C4", "FAIL", where, "verifier.origin must be code, sensor:<name>, model:<provider> or human:<role>")
            continue
        if verifier.get("origin") in performers:
            add("C4", "FAIL", where, f"{verifier.get('origin')} performs the work and cannot also judge it")
        if rung == "judgment" and origin[0] not in ("model", "human"):
            add("C4", "FAIL", where, "a judgment is made by a model or a human; name which")

    # C6: actions
    actions = [a for a in _items(doc, "actions") if isinstance(a, dict)]
    action_ids: set[str] = set()
    for position, action in enumerate(actions):
        aid = action.get("id")
        where = f"actions.{aid if _text(aid) else position}"
        if not _text(aid):
            add("C0", "FAIL", where, "every action needs an id")
            continue
        if aid in action_ids or aid in by_id:
            add("C0", "FAIL", where, "action ids must be unique and differ from claim ids")
        action_ids.add(aid)
        klass = action.get("reversibility")
        if klass not in REVERSIBILITY:
            add("C6", "FAIL", where, f"reversibility must be one of {', '.join(REVERSIBILITY)}")
            continue
        if not _text(action.get("reach")):
            add("C6", "FAIL", where, "say what the action can touch (reach)")
        requires = [r for r in _items(action, "requires") if _text(r)]
        for needed in requires:
            if needed not in by_id:
                add("C6", "FAIL", where, f"requires unknown claim {needed}")
            elif by_id[needed].get("rung") == "none" and klass != "reversible":
                add("C6", "FAIL", where, f"claim {needed} has no check, so it may only guard a reversible action")
        if klass in ("reversible", "compensable"):
            if not _text(action.get("undo")):
                add("C6", "FAIL", where, f"a {klass} action says how it is undone (undo)")
        else:
            gate = action.get("gate")
            kind, _, name = gate.partition(":") if _text(gate) else ("", "", "")
            if kind == "human" and name.strip():
                pass
            elif kind == "claim" and by_id.get(name.strip(), {}).get("rung") in COMMAND_RUNGS:
                if name.strip() not in requires:
                    add("C6", "FAIL", where, f"gate claim {name.strip()} must also be listed in requires")
            else:
                add("C6", "FAIL", where, "an irreversible action needs gate: human:<who>, or claim:<id> of a proof or replay claim")

    # C5: order
    flow = doc.get("flow") if isinstance(doc.get("flow"), dict) else None
    needs_flow = len(actions) >= 2 or any(a.get("reversibility") == "irreversible" for a in actions)
    if flow is None:
        if needs_flow:
            add("C5", "FAIL", "flow", "more than one action, or an irreversible one, needs a declared order")
    else:
        steps = flow.get("steps")
        if _text(flow.get("ref")):
            pass
        elif isinstance(steps, list) and steps:
            for step in steps:
                if step not in by_id and step not in action_ids:
                    add("C5", "FAIL", "flow.steps", f"unknown step {step}")
            for aid in sorted(action_ids - set(steps)):
                add("C5", "FAIL", "flow.steps", f"action {aid} is not in the order")
        else:
            add("C5", "FAIL", "flow", "give flow.ref (a flow definition) or flow.steps (ids in order)")

    # C7: contraction
    if not isinstance(doc.get("feeds"), list):
        add("C7", "FAIL", "feeds", "list each output that becomes an input, or write an empty list")
    for position, hop in enumerate(_items(doc, "feeds")):
        where = f"feeds.{position}"
        if not isinstance(hop, dict) or not _text(hop.get("from")) or not _text(hop.get("to")):
            add("C7", "FAIL", where, "a hop names from and to")
            continue
        if hop.get("check") not in by_id:
            add("C7", "FAIL", where, "a hop names the claim that checks it (check)")
        elif by_id[hop["check"]].get("rung") == "none":
            add("C7", "FAIL", where, f"claim {hop['check']} has no check, so it cannot guard a hop")
    learning = doc.get("learning") if isinstance(doc.get("learning"), dict) else {}
    if not _text(learning.get("on_correction")):
        add("C7", "FAIL", "learning.on_correction", "say where a correction goes so it is not repeated")

    # C8: the declared remainder
    unverified = doc.get("unverified")
    if not isinstance(unverified, list):
        add("C8", "FAIL", "unverified", "list what this statement does not verify")
    elif not [u for u in unverified if _text(u)]:
        if not _text(doc.get("nothing_unverified_because")):
            add("C8", "FAIL", "unverified", "an empty list needs nothing_unverified_because")
    for claim in claims:
        if claim.get("rung") == "none" and _text(claim.get("id")):
            listed = " ".join(u for u in (unverified if isinstance(unverified, list) else []) if _text(u))
            if claim["id"] not in listed:
                add("C8", "FAIL", f"claims.{claim['id']}", "a claim with no check is named in `unverified`")
    return findings


def coverage(doc: dict) -> dict:
    claims = [c for c in _items(doc, "claims") if isinstance(c, dict)]
    actions = [a for a in _items(doc, "actions") if isinstance(a, dict)]
    falsifiable = 0
    by_rung = {rung: 0 for rung in RUNGS}
    for claim in claims:
        rung = claim.get("rung")
        if rung in by_rung:
            by_rung[rung] += 1
        verifier = claim.get("verifier") if isinstance(claim.get("verifier"), dict) else {}
        if rung in FALSIFIER and all(_text(verifier.get(f)) for f in FALSIFIER[rung]):
            falsifiable += 1
    irreversible = [a for a in actions if a.get("reversibility") == "irreversible"]
    return {
        "claims": len(claims),
        "claims_with_a_check_that_can_fail": falsifiable,
        "claims_accepted": sum(1 for c in claims if c.get("status") == "accepted"),
        "claims_by_rung": by_rung,
        "actions": len(actions),
        "actions_irreversible": len(irreversible),
        "actions_irreversible_gated": sum(1 for a in irreversible if _text(a.get("gate"))),
    }


def _run(command: str, cwd: Path, timeout: int) -> tuple[int | None, str]:
    try:
        done = subprocess.run(
            command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"
    tail = (done.stdout + done.stderr).strip().splitlines()[-3:]
    return done.returncode, " | ".join(tail)


def replay(doc: dict, cwd: Path, timeout: int) -> tuple[list[dict], int]:
    """Run every proof and replay claim: its known-bad case must be refused,
    its known-good case accepted, and then the check itself is run."""
    rows: list[dict] = []
    worst = EXIT_OK
    for claim in _items(doc, "claims"):
        if not isinstance(claim, dict) or claim.get("rung") not in COMMAND_RUNGS:
            continue
        verifier = claim.get("verifier") if isinstance(claim.get("verifier"), dict) else {}
        row = {"claim": claim.get("id"), "rung": claim.get("rung")}
        if not _text(verifier.get("check")) or not _text(verifier.get("rejects")):
            row["verdict"] = "INVALID"
            row["why"] = "no check or no known-bad case to run"
            worst = EXIT_INVALID
            rows.append(row)
            continue
        code, tail = _run(verifier["rejects"], cwd, timeout)
        row["rejects_exit"] = code
        if code == 0:
            row["verdict"] = "INVALID"
            row["why"] = "the known-bad case passed, so this check cannot fail"
            worst = EXIT_INVALID
            rows.append(row)
            continue
        if code is None:
            row["verdict"] = "INVALID"
            row["why"] = f"the known-bad case {tail}"
            worst = EXIT_INVALID
            rows.append(row)
            continue
        if _text(verifier.get("accepts")):
            code, tail = _run(verifier["accepts"], cwd, timeout)
            row["accepts_exit"] = code
            if code != 0:
                row["verdict"] = "INVALID"
                row["why"] = f"the known-good case was refused: {tail}"
                worst = EXIT_INVALID
                rows.append(row)
                continue
        code, tail = _run(verifier["check"], cwd, timeout)
        row["check_exit"] = code
        row["tail"] = tail
        if code == 0:
            row["verdict"] = "PASS"
        else:
            row["verdict"] = "FAIL"
            if worst == EXIT_OK:
                worst = EXIT_FINDING
        rows.append(row)
    if not rows:
        return rows, EXIT_INVALID
    return rows, worst


def default_index() -> Path:
    return Path(__file__).resolve().parent.parent / "references" / "index.json"


def load_index(path: Path) -> dict:
    index = load_doc(path)
    if not isinstance(index.get("entries"), list) or not isinstance(index.get("no_role"), list):
        raise InputError(f"{path} needs `entries` and `no_role` lists")
    return index


def route(doc: dict, index: dict) -> dict:
    """Which catalog entries to load for this statement, by part."""
    domains = {d for d in _items(doc, "domain") if _text(d)}
    rungs = {c.get("rung") for c in _items(doc, "claims") if isinstance(c, dict)}
    routed: dict[str, list[dict]] = {part: [] for part in PARTS}
    for entry in index["entries"]:
        entry_domains = set(entry.get("domains") or [])
        if "any" not in entry_domains and not (entry_domains & domains):
            continue
        for part in entry.get("parts") or []:
            if part not in routed:
                continue
            if part == "verifiers":
                shared = sorted(set(entry.get("rungs") or []) & rungs)
                if not shared:
                    continue
                routed[part].append({"name": entry["name"], "kind": entry["kind"], "rungs": shared})
            else:
                routed[part].append({"name": entry["name"], "kind": entry["kind"]})
    return {part: sorted(rows, key=lambda r: r["name"]) for part, rows in routed.items()}


def find_root(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / "skills").is_dir() and (folder / "scripts" / "lint_skill_catalog.py").is_file():
            return folder
    return None


def roster(root: Path) -> set[str]:
    """Installable skills: skills/<bucket>/<name>/SKILL.md."""
    return {p.parent.name for p in (root / "skills").glob("*/*/SKILL.md")}


def index_report(index: dict, root: Path | None) -> tuple[dict, int]:
    problems: list[str] = []
    names: dict[str, int] = {}
    for entry in index["entries"]:
        name = entry.get("name")
        if not _text(name) or entry.get("kind") not in ("skill", "service", "contract"):
            problems.append(f"entry {name!r}: needs a name and kind skill, service or contract")
            continue
        names[name] = names.get(name, 0) + 1
        for part in entry.get("parts") or []:
            if part not in PARTS:
                problems.append(f"{name}: unknown part {part}")
        for rung in entry.get("rungs") or []:
            if rung not in RUNGS:
                problems.append(f"{name}: unknown rung {rung}")
        if not entry.get("parts"):
            problems.append(f"{name}: an entry with no part belongs in no_role")
        if "verifiers" in (entry.get("parts") or []) and not entry.get("rungs"):
            problems.append(f"{name}: a verifier names the rungs it serves")
        if not entry.get("domains"):
            problems.append(f"{name}: needs at least one domain, or `any`")
        if entry.get("kind") != "skill" and not _text(entry.get("where")):
            problems.append(f"{name}: a {entry.get('kind')} says where it lives")
    indexed_skills = {e["name"] for e in index["entries"] if e.get("kind") == "skill" and _text(e.get("name"))}
    set_aside = {n for n in index["no_role"] if _text(n)}
    for name, count in names.items():
        if count > 1:
            problems.append(f"{name}: listed {count} times")
    for name in sorted(indexed_skills & set_aside):
        problems.append(f"{name}: both indexed and in no_role")
    cells = {part: sorted(e["name"] for e in index["entries"] if part in (e.get("parts") or [])) for part in PARTS}
    report = {
        "entries": len(index["entries"]),
        "no_role": len(set_aside),
        "problems": problems,
        "empty_parts": [part for part, rows in cells.items() if not rows],
        "roster_checked": root is not None,
    }
    if root is not None:
        on_disk = roster(root)
        report["untagged"] = sorted(on_disk - indexed_skills - set_aside)
        report["dangling"] = sorted((indexed_skills | set_aside) - on_disk)
    code = EXIT_OK
    if problems or report.get("untagged") or report.get("dangling") or report["empty_parts"]:
        code = EXIT_FINDING
    return report, code


def _print_check(doc: dict, findings: list[dict], pin: tuple[str, str]) -> None:
    fails = [f for f in findings if f["level"] == "FAIL"]
    print("CHECKABLE" if not fails else "NOT CHECKABLE")
    print(f"  pin: {pin[0]} ({pin[1]})")
    for code, meaning in INVARIANTS.items():
        mine = [f for f in findings if f["invariant"] == code]
        level = "FAIL" if any(f["level"] == "FAIL" for f in mine) else ("WARN" if mine else "ok")
        print(f"  {code} {level:<4} {meaning}")
        for finding in mine:
            print(f"       {finding['where']}: {finding['message']}")
    numbers = coverage(doc)
    print(
        f"  coverage: {numbers['claims_with_a_check_that_can_fail']}/{numbers['claims']} claims have a check that can fail; "
        f"{numbers['actions_irreversible_gated']}/{numbers['actions_irreversible']} irreversible actions are gated; "
        f"{numbers['claims_accepted']}/{numbers['claims']} claims accepted"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="checkable", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="refuse a statement that breaks an invariant")
    p_check.add_argument("statement", type=Path)
    p_check.add_argument("--base", help="git revision that declares the claims, e.g. origin/main")
    p_check.add_argument("--json", action="store_true")

    p_replay = sub.add_parser("replay", help="run each proof and replay claim with its controls")
    p_replay.add_argument("statement", type=Path)
    p_replay.add_argument("--cwd", type=Path, default=Path.cwd())
    p_replay.add_argument("--timeout", type=int, default=300)
    p_replay.add_argument("--json", action="store_true")

    p_route = sub.add_parser("route", help="list the catalog entries to load for a statement")
    p_route.add_argument("statement", type=Path)
    p_route.add_argument("--index", type=Path, default=default_index())
    p_route.add_argument("--json", action="store_true")

    p_index = sub.add_parser("index", help="check the catalog index against the skills on disk")
    p_index.add_argument("--index", type=Path, default=default_index())
    p_index.add_argument("--root", type=Path, help="monorepo root; found by walking up when omitted")
    p_index.add_argument("--require-roster", action="store_true", help="exit 3 when no roster can be found")
    p_index.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            doc = load_doc(args.statement)
            pin = pin_state(args.statement, args.base, doc)
            findings = check(doc, pin)
            failed = any(f["level"] == "FAIL" for f in findings)
            if args.json:
                print(json.dumps({"checkable": not failed, "pin": pin, "findings": findings, "coverage": coverage(doc)}, indent=2))
            else:
                _print_check(doc, findings, pin)
            return EXIT_FINDING if failed else EXIT_OK

        if args.command == "replay":
            doc = load_doc(args.statement)
            rows, code = replay(doc, args.cwd, args.timeout)
            if args.json:
                print(json.dumps({"rows": rows, "exit": code}, indent=2))
            else:
                if not rows:
                    print("INVALID: the statement has no proof or replay claim to run")
                for row in rows:
                    # A passing row prints no command output, so the same
                    # statement at the same commit prints the same text.
                    detail = "" if row["verdict"] == "PASS" else (row.get("why") or row.get("tail") or "")
                    print(f"{row['verdict']:<7} {row['claim']} ({row['rung']}) {detail}".rstrip())
            return code

        if args.command == "route":
            doc = load_doc(args.statement)
            routed = route(doc, load_index(args.index))
            if args.json:
                print(json.dumps(routed, indent=2))
            else:
                for part, rows in routed.items():
                    shown = ", ".join(
                        f"{r['name']}[{'/'.join(r['rungs'])}]" if r.get("rungs") else r["name"] for r in rows
                    )
                    print(f"{part:<11} {shown or '(nothing indexed for these domains)'}")
            return EXIT_OK

        index = load_index(args.index)
        root = args.root or find_root(args.index.resolve().parent)
        if root is None and args.require_roster:
            print("no skills roster found to compare the index against", file=sys.stderr)
            return EXIT_NO_COMPARISON
        report, code = index_report(index, root)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"{report['entries']} entries, {report['no_role']} set aside, roster checked: {report['roster_checked']}")
            for key in ("problems", "untagged", "dangling", "empty_parts"):
                for item in report.get(key) or []:
                    print(f"  {key}: {item}")
        return code
    except InputError as exc:
        print(f"checkable: {exc}", file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
