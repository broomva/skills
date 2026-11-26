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
import os
import re
import signal
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
    "C1": "the statement matches the base revision, apart from status and receipts",
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


def _no_duplicate_keys(pairs: list) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise InputError(f"the key {key!r} appears twice in one mapping")
        seen[key] = value
    return seen


def parse(text: str, suffix: str, label: str) -> dict:
    """Read a statement or index. A key written twice in one mapping is
    refused, because a reader would see one value and a parser the other."""
    if suffix.lower() == ".json":
        try:
            doc = json.loads(text, object_pairs_hook=_no_duplicate_keys)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise InputError(f"{label} is not valid JSON: {exc.__class__.__name__}: {exc}") from exc
        except InputError as exc:
            raise InputError(f"{label}: {exc}") from exc
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise InputError(
                f"{label} is YAML and PyYAML is not installed; "
                "`pip install pyyaml` or write the statement as .json"
            ) from exc

        class Loader(yaml.SafeLoader):
            pass

        def mapping(loader, node, deep=False):
            pairs = [(loader.construct_object(k, deep=True), loader.construct_object(v, deep=True)) for k, v in node.value]
            return _no_duplicate_keys(pairs)

        Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        try:
            doc = yaml.load(text, Loader=Loader)  # noqa: S506 (a SafeLoader subclass)
        except yaml.YAMLError as exc:
            raise InputError(f"{label} is not valid YAML: {exc}") from exc
        except (InputError, TypeError, ValueError, RecursionError) as exc:
            raise InputError(f"{label}: {exc.__class__.__name__}: {exc}") from exc
    if not isinstance(doc, dict):
        raise InputError(f"{label} must hold a mapping at the top level")
    return doc


def load_doc(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    return parse(text, path.suffix, str(path))


# --- shape -----------------------------------------------------------------
#
# A statement is read strictly. A value of the wrong type, or a key this
# format does not define, is refused instead of skipped: an entry the checker
# silently ignored would be an entry no invariant applies to.

ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ORIGIN = re.compile(r"^(?:code|(?:sensor|model|human):[a-z0-9][a-z0-9._-]*)$")
PERFORMER = re.compile(r"^(?:model|human):[a-z0-9][a-z0-9._-]*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _id(value) -> bool:
    return isinstance(value, str) and bool(ID.match(value))


def _origin(value) -> bool:
    return isinstance(value, str) and bool(ORIGIN.match(value))


def _performer(value) -> bool:
    return isinstance(value, str) and bool(PERFORMER.match(value))


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _one_of(options):
    return lambda value: isinstance(value, str) and value in options


def _each(test):
    return lambda value: isinstance(value, list) and all(test(item) for item in value)


def _mapping(value) -> bool:
    return isinstance(value, dict)


def _mappings(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


A_TEXT = (_text, "a non-empty string")
AN_ID = (_id, "an id: lower-case letters, digits and hyphens")
AN_ORIGIN = (_origin, "code, sensor:<name>, model:<provider> or human:<role>, in lower case with no spaces")

VERIFIER_SHAPE = {
    "origin": AN_ORIGIN,
    "check": A_TEXT,
    "rejects": A_TEXT,
    "rejects_exit": (_whole, "a whole number: the exit status the known-bad case must end with"),
    "accepts": A_TEXT,
    "sensor": A_TEXT,
    "positive_control": A_TEXT,
    "falsification_criterion": A_TEXT,
    "rubric": A_TEXT,
    "pass_rule": A_TEXT,
    "prediction_recorded": (lambda value: isinstance(value, str) and bool(DATE.match(value)), "the date the prediction was written, as a quoted YYYY-MM-DD string"),
    "scored_by": A_TEXT,
}
RECEIPT_SHAPE = {"revision": A_TEXT, "replay": A_TEXT, "result": (_one_of(("pass", "fail")), "pass or fail")}
CLAIM_SHAPE = {
    "id": AN_ID,
    "text": A_TEXT,
    "rung": (_one_of(RUNGS), f"one of {', '.join(RUNGS)}"),
    "verifier": (_mapping, "a mapping"),
    "status": (_one_of(STATUSES), f"one of {', '.join(STATUSES)}"),
    "receipt": (_mapping, "a mapping"),
}
ACTION_SHAPE = {
    "id": AN_ID,
    "text": A_TEXT,
    "reversibility": (_one_of(REVERSIBILITY), f"one of {', '.join(REVERSIBILITY)}"),
    "reach": A_TEXT,
    "undo": A_TEXT,
    "gate": A_TEXT,
    "requires": (_each(_id), "a list of claim ids"),
}
FLOW_SHAPE = {"steps": (_each(_id), "a list of claim and action ids"), "ref": A_TEXT}
HOP_SHAPE = {"from": A_TEXT, "to": A_TEXT, "check": AN_ID}
LEARNING_SHAPE = {"on_correction": A_TEXT}
TOP_SHAPE = {
    "checkable": (lambda value: _whole(value) and value == 1, "1, the statement format version"),
    "problem": A_TEXT,
    "domain": (_each(_text), "a list of domain names"),
    "performers": (lambda value: _each(_performer)(value) and bool(value), "a non-empty list of model:<provider> or human:<role>, in lower case with no spaces"),
    "claims": (lambda value: _mappings(value) and bool(value), "a non-empty list of mappings"),
    "actions": (_mappings, "a list of mappings"),
    "flow": (_mapping, "a mapping"),
    "feeds": (_mappings, "a list of mappings"),
    "learning": (_mapping, "a mapping"),
    "unverified": (_each(_text), "a list of non-empty strings"),
    "nothing_unverified_because": A_TEXT,
}


def shape(doc: dict) -> list[dict]:
    """Type and key errors, as C0 findings. Missing fields that an invariant
    asks for are left to that invariant."""
    findings: list[dict] = []

    def add(where: str, message: str) -> None:
        findings.append({"invariant": "C0", "level": "FAIL", "where": where, "message": message})

    def walk(obj: dict, where: str, spec: dict, required: tuple = ()) -> None:
        for key in obj:
            if key not in spec:
                add(f"{where}{key}", "this key is not part of the statement format")
        for key, (test, expected) in spec.items():
            if key in obj:
                if not test(obj[key]):
                    add(f"{where}{key}", f"must be {expected}")
            elif key in required:
                add(f"{where}{key}", f"is required: {expected}")

    walk(doc, "", TOP_SHAPE, ("checkable", "problem", "performers", "claims"))
    if findings:
        return findings
    seen: set[str] = set()
    for position, claim in enumerate(doc["claims"]):
        where = f"claims.{claim['id'] if _id(claim.get('id')) else position}."
        walk(claim, where, CLAIM_SHAPE, ("id", "text", "rung"))
        if _mapping(claim.get("verifier")):
            walk(claim["verifier"], f"{where}verifier.", VERIFIER_SHAPE)
        if _mapping(claim.get("receipt")):
            walk(claim["receipt"], f"{where}receipt.", RECEIPT_SHAPE)
        if _id(claim.get("id")):
            if claim["id"] in seen:
                add(f"{where}id", "claim and action ids must be unique")
            seen.add(claim["id"])
    for position, action in enumerate(doc.get("actions", [])):
        where = f"actions.{action['id'] if _id(action.get('id')) else position}."
        walk(action, where, ACTION_SHAPE, ("id", "text"))
        if _id(action.get("id")):
            if action["id"] in seen:
                add(f"{where}id", "claim and action ids must be unique")
            seen.add(action["id"])
    if "flow" in doc:
        walk(doc["flow"], "flow.", FLOW_SHAPE)
    for position, hop in enumerate(doc.get("feeds", [])):
        walk(hop, f"feeds.{position}.", HOP_SHAPE, ("from", "to"))
    if "learning" in doc:
        walk(doc["learning"], "learning.", LEARNING_SHAPE)
    return findings


MOVES_WITH_THE_WORK = ("status", "receipt")


def pinned_text(doc: dict) -> str:
    """Everything a performer must not change once the work starts: the whole
    statement except each claim's status and receipt, which record progress."""
    kept = dict(doc)
    claims = doc.get("claims")
    if isinstance(claims, list):
        kept["claims"] = [
            {k: v for k, v in claim.items() if k not in MOVES_WITH_THE_WORK} if isinstance(claim, dict) else claim
            for claim in claims
        ]
    return json.dumps(_plain(kept), sort_keys=True, ensure_ascii=False)


def _plain(value):
    """A copy that always serializes: keys become strings and a value JSON has
    no form for (a YAML date, say) becomes its text."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def pin_state(path: Path, base: str | None, doc: dict) -> tuple[str, str]:
    """pinned | changed | absent | unknown, with a sentence saying why."""
    if not base:
        return "unknown", "no --base revision was given"
    if base.startswith("-"):
        return "unknown", f"{base!r} is not a revision"
    folder = path.resolve().parent

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], capture_output=True, text=True, errors="replace")

    try:
        top = git("-C", str(folder), "rev-parse", "--show-toplevel")
    except OSError as exc:
        return "unknown", f"git could not be run: {exc}"
    if top.returncode != 0:
        return "unknown", f"{folder} is not inside a git repository"
    root = Path(top.stdout.strip()).resolve()
    try:
        rel = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return "unknown", f"{path} resolves to a file outside the repository at {root}"
    known = git("-C", str(root), "rev-parse", "--verify", "--quiet", "--end-of-options", f"{base}^{{commit}}")
    if known.returncode != 0:
        return "unknown", f"revision {base} does not exist in this repository"
    shown = git("-C", str(root), "show", f"{base}:{rel}")
    if shown.returncode != 0:
        return "absent", f"{rel} does not exist at {base}"
    try:
        base_doc = parse(shown.stdout, path.suffix, f"{base}:{rel}")
    except InputError as exc:
        return "unknown", f"the copy at {base} could not be read: {exc}"
    if pinned_text(base_doc) == pinned_text(doc):
        return "pinned", f"the statement matches {base}"
    return "changed", f"the statement differs from {base}"


def gate_problem(action: dict, by_id: dict, performers: set) -> str | None:
    """Why an irreversible action's gate does not hold, or None when it does.
    A gate is a named person who is not doing the work, or a proof or replay
    claim that the action also requires."""
    gate = action.get("gate", "")
    kind, _, name = gate.partition(":")
    if kind == "human" and PERFORMER.match(gate):
        if gate in performers:
            return f"{gate} performs the work and cannot also be its gate"
        return None
    if kind == "claim" and name in by_id and by_id[name]["rung"] in COMMAND_RUNGS:
        if name not in action.get("requires", []):
            return f"gate claim {name} must also be listed in requires"
        return None
    return "an irreversible action needs gate: human:<who>, or claim:<id> of a proof or replay claim"


def check(doc: dict, pin: tuple[str, str], folder: Path | None = None) -> list[dict]:
    """Every finding for a statement. Shape errors are reported alone: the
    invariants are only decided for a statement that is well formed."""
    findings = shape(doc)
    if findings:
        return findings

    def add(invariant: str, level: str, where: str, message: str) -> None:
        findings.append({"invariant": invariant, "level": level, "where": where, "message": message})

    performers = set(doc["performers"])
    claims = doc["claims"]
    actions = doc.get("actions", [])
    by_id = {claim["id"]: claim for claim in claims}
    action_ids = {action["id"] for action in actions}
    accepted = [claim for claim in claims if claim.get("status") == "accepted"]
    unverified = doc.get("unverified")

    # C1: the base declares the claims
    state, why = pin
    if state == "changed":
        add("C1", "FAIL", "statement", f"{why}; a change to the statement lands on the base first")
    elif state != "pinned":
        if accepted:
            add("C1", "FAIL", "statement", f"{len(accepted)} claim(s) are accepted but the statement is not pinned: {why}")
        else:
            add("C1", "WARN", "statement", f"not pinned yet: {why}")

    for claim in claims:
        where = f"claims.{claim['id']}"
        rung = claim["rung"]
        status = claim.get("status", "open")
        verifier = claim.get("verifier", {})
        receipt = claim.get("receipt", {})

        # C2: receipts
        if status in ("accepted", "refuted"):
            for field in ("revision", "replay", "result"):
                if field not in receipt:
                    add("C2", "FAIL", where, f"{status} without receipt.{field}")
            wanted = "pass" if status == "accepted" else "fail"
            if receipt.get("result", wanted) != wanted:
                add("C2", "FAIL", where, f"{status} needs receipt.result: {wanted}")
            if rung in COMMAND_RUNGS and "replay" in receipt and receipt["replay"] != verifier.get("check"):
                add("C2", "FAIL", where, "the receipt of a proof or replay claim names the claim's own check as its replay")
            if status == "accepted" and rung == "none":
                add("C2", "FAIL", where, "a claim with no check cannot be accepted; it stays in `unverified`")

        if rung == "none":
            # C8: a claim nobody checks is named in the remainder, by its id
            named = [item for item in (unverified or []) if item == claim["id"] or item.startswith(claim["id"] + ":")]
            if not named:
                add("C8", "FAIL", where, f"a claim with no check starts an `unverified` entry, as `{claim['id']}: ...`")
            if verifier:
                add("C3", "FAIL", where, "a claim on rung none has no verifier; give it a rung or remove the verifier")
            continue

        # C3: the check can fail
        for field in FALSIFIER[rung]:
            if field not in verifier:
                add("C3", "FAIL", where, f"a {rung} check needs verifier.{field}")

        # C4: independence
        origin = verifier.get("origin")
        if origin is None:
            add("C4", "FAIL", where, "verifier.origin is required: code, sensor:<name>, model:<provider> or human:<role>")
        elif origin in performers:
            add("C4", "FAIL", where, f"{origin} performs the work and cannot also judge it")
        elif rung == "judgment" and origin.partition(":")[0] not in ("model", "human"):
            add("C4", "FAIL", where, "a judgment is made by a model or a human; name which")

    # C5: order. It is needed before C6 can ask whether a gate comes first.
    steps = doc.get("flow", {}).get("steps") or []
    position_of = {step: index for index, step in enumerate(steps)}
    needs_flow = len(actions) >= 2 or any(a.get("reversibility") == "irreversible" for a in actions)
    if not steps:
        if needs_flow:
            add("C5", "FAIL", "flow.steps", "more than one action, or an irreversible one, needs its order written as flow.steps")
    else:
        if len(position_of) != len(steps):
            add("C5", "FAIL", "flow.steps", "a step is listed twice")
        for step in steps:
            if step not in by_id and step not in action_ids:
                add("C5", "FAIL", "flow.steps", f"unknown step {step}")
        for aid in sorted(action_ids - set(steps)):
            add("C5", "FAIL", "flow.steps", f"action {aid} is not in the order")
    ref = doc.get("flow", {}).get("ref")
    if ref is not None and folder is not None and not (folder / ref).is_file():
        add("C5", "FAIL", "flow.ref", f"{ref} is not a file next to the statement")

    # C6: actions
    for action in actions:
        aid = action["id"]
        where = f"actions.{aid}"
        klass = action.get("reversibility")
        if klass is None:
            add("C6", "FAIL", where, f"reversibility is required: one of {', '.join(REVERSIBILITY)}")
            continue
        if "reach" not in action:
            add("C6", "FAIL", where, "say what the action can touch (reach)")
        requires = action.get("requires", [])
        for needed in requires:
            if needed not in by_id:
                add("C6", "FAIL", where, f"requires unknown claim {needed}")
                continue
            if by_id[needed]["rung"] == "none":
                # Nothing runs for a claim with no check, so it is not a step.
                if klass != "reversible":
                    add("C6", "FAIL", where, f"claim {needed} has no check, so it may only guard a reversible action")
                continue
            if aid in position_of and position_of.get(needed, len(steps)) > position_of[aid]:
                add("C5", "FAIL", where, f"claim {needed} is required but does not come before {aid} in flow.steps")
        if klass in ("reversible", "compensable"):
            if "undo" not in action:
                add("C6", "FAIL", where, f"a {klass} action says how it is undone (undo)")
            continue
        problem = gate_problem(action, by_id, performers)
        if problem:
            add("C6", "FAIL", where, problem)

    # C7: contraction
    if "feeds" not in doc:
        add("C7", "FAIL", "feeds", "list each output that becomes an input, or write an empty list")
    for position, hop in enumerate(doc.get("feeds", [])):
        where = f"feeds.{position}"
        if hop.get("check") not in by_id:
            add("C7", "FAIL", where, "a hop names the claim that checks it (check)")
        elif by_id[hop["check"]]["rung"] == "none":
            add("C7", "FAIL", where, f"claim {hop['check']} has no check, so it cannot guard a hop")
    if "on_correction" not in doc.get("learning", {}):
        add("C7", "FAIL", "learning.on_correction", "say where a correction goes so it is not repeated")

    # C8: the declared remainder
    if unverified is None:
        add("C8", "FAIL", "unverified", "list what this statement does not verify")
    elif not unverified and "nothing_unverified_because" not in doc:
        add("C8", "FAIL", "unverified", "an empty list needs nothing_unverified_because")
    return findings


def coverage(doc: dict) -> dict:
    """Counts for a well-formed statement."""
    claims = doc["claims"]
    actions = doc.get("actions", [])
    by_rung = {rung: 0 for rung in RUNGS}
    falsifiable = 0
    for claim in claims:
        rung = claim["rung"]
        by_rung[rung] += 1
        verifier = claim.get("verifier", {})
        if rung in FALSIFIER and all(field in verifier for field in FALSIFIER[rung]):
            falsifiable += 1
    irreversible = [a for a in actions if a.get("reversibility") == "irreversible"]
    return {
        "claims": len(claims),
        "claims_with_a_check_that_can_fail": falsifiable,
        "claims_accepted": sum(1 for c in claims if c.get("status") == "accepted"),
        "claims_by_rung": by_rung,
        "actions": len(actions),
        "actions_irreversible": len(irreversible),
        "actions_irreversible_gated": sum(
            1 for a in irreversible if gate_problem(a, {c["id"]: c for c in claims}, set(doc["performers"])) is None
        ),
    }


def _run(command: str, cwd: Path, timeout: int) -> tuple[int | None, str]:
    # The command gets its own process group, so a timeout stops what it
    # started as well. Killing only the shell would leave a child holding the
    # output pipe, and the wait would outlast the timeout.
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            # The group is already gone, or holds only a process that has
            # exited (macOS answers EPERM for that).
            pass
        try:
            # A process that left the group can still hold the pipe open, so
            # this wait is bounded too.
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            if proc.stdout is not None:
                proc.stdout.close()
        return None, f"timed out after {timeout}s"
    tail = output.strip().splitlines()[-3:]
    return proc.returncode, " | ".join(tail)


# Exit statuses a shell uses when it could not run the command at all.
COULD_NOT_RUN = (126, 127)


def replay(doc: dict, cwd: Path, timeout: int) -> tuple[list[dict], int]:
    """Run every proof and replay claim: its known-bad case must be refused,
    its known-good case accepted, and then the check itself is run.

    A known-bad case that could not run proves nothing, so it is INVALID, not
    a refusal: a missing command, a signal or a timeout. When the statement
    gives `rejects_exit`, the case must end with exactly that status."""
    rows: list[dict] = []
    worst = EXIT_OK

    def invalid(row: dict, why: str) -> None:
        nonlocal worst
        row["verdict"] = "INVALID"
        row["why"] = why
        worst = EXIT_INVALID
        rows.append(row)

    for claim in doc["claims"]:
        if claim["rung"] not in COMMAND_RUNGS:
            continue
        verifier = claim.get("verifier", {})
        row = {"claim": claim["id"], "rung": claim["rung"]}
        if "check" not in verifier or "rejects" not in verifier:
            invalid(row, "no check or no known-bad case to run")
            continue
        code, tail = _run(verifier["rejects"], cwd, timeout)
        row["rejects_exit"] = code
        wanted = verifier.get("rejects_exit")
        if code is None:
            invalid(row, f"the known-bad case {tail}")
            continue
        if code == 0:
            invalid(row, "the known-bad case passed, so this check cannot fail")
            continue
        if code in COULD_NOT_RUN or code < 0:
            invalid(row, f"the known-bad case could not run (exit {code}): {tail}")
            continue
        if wanted is not None and code != wanted:
            invalid(row, f"the known-bad case ended with exit {code}, not the stated {wanted}")
            continue
        if "accepts" in verifier:
            code, tail = _run(verifier["accepts"], cwd, timeout)
            row["accepts_exit"] = code
            if code != 0:
                invalid(row, f"the known-good case was refused: {tail}")
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
    entries, set_aside = index.get("entries"), index.get("no_role")
    if not isinstance(entries, list) or not isinstance(set_aside, list):
        raise InputError(f"{path} needs `entries` and `no_role` lists")
    for entry in entries:
        if not isinstance(entry, dict) or not _text(entry.get("name")):
            raise InputError(f"{path}: every entry is a mapping with a name; found {entry!r}")
        for key in ("parts", "rungs", "domains"):
            if key in entry and not _each(_text)(entry[key]):
                raise InputError(f"{path}: {entry['name']}.{key} must be a list of strings")
    if not _each(_text)(set_aside):
        raise InputError(f"{path}: no_role must be a list of skill names")
    return index


def route(doc: dict, index: dict) -> dict:
    """Which catalog entries to load for this statement, by part."""
    domains = set(doc.get("domain", []))
    rungs = {claim["rung"] for claim in doc["claims"]}
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


def _print_check(findings: list[dict], pin: tuple[str, str], numbers: dict | None) -> None:
    fails = [f for f in findings if f["level"] == "FAIL"]
    print("CHECKABLE" if not fails else "NOT CHECKABLE")
    print(f"  pin: {pin[0]} ({pin[1]})")
    for code, meaning in INVARIANTS.items():
        mine = [f for f in findings if f["invariant"] == code]
        level = "FAIL" if any(f["level"] == "FAIL" for f in mine) else ("WARN" if mine else "ok")
        print(f"  {code} {level:<4} {meaning}")
        for finding in mine:
            print(f"       {finding['where']}: {finding['message']}")
    if numbers is None:
        print("  the statement is malformed, so C1 to C8 were not decided")
        return
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
            findings = check(doc, pin, args.statement.resolve().parent)
            failed = any(f["level"] == "FAIL" for f in findings)
            well_formed = not any(f["invariant"] == "C0" for f in findings)
            numbers = coverage(doc) if well_formed else None
            if args.json:
                print(json.dumps({"checkable": not failed, "pin": pin, "findings": findings, "coverage": numbers}, indent=2))
            else:
                _print_check(findings, pin, numbers)
            if failed:
                return EXIT_FINDING
            if args.base and pin[0] != "pinned":
                print(f"checkable: --base {args.base} was given but the statement could not be compared: {pin[1]}", file=sys.stderr)
                return EXIT_NO_COMPARISON
            return EXIT_OK

        if args.command in ("replay", "route"):
            malformed = shape(load_doc(args.statement))
            if malformed:
                first = malformed[0]
                raise InputError(
                    f"{args.statement} is malformed ({first['where']}: {first['message']}); run `check` for the full list"
                )

        if args.command == "replay":
            doc = load_doc(args.statement)
            if not args.cwd.is_dir():
                raise InputError(f"--cwd {args.cwd} is not a directory")
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
        if args.root is not None and not (args.root / "skills").is_dir():
            raise InputError(f"{args.root} has no skills/ directory")
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
            if report.get("untagged"):
                print(f"  fix: give each untagged skill an entry in {args.index}, or add its name to `no_role` there")
            if report.get("dangling"):
                print(f"  fix: remove each dangling name from {args.index}")
        return code
    except InputError as exc:
        print(f"checkable: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except (OSError, TypeError, ValueError, KeyError, AttributeError, RecursionError) as exc:
        # The contract is an exit status. Input this tool did not expect is
        # unreadable input, not a finding.
        print(f"checkable: the input could not be processed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
