#!/usr/bin/env python3
"""Decide the next Parallax command from state, and the remedy from an error code.

Two questions an agent driving Parallax gets wrong by reasoning about them, and
gets right by looking them up. Both are pure functions of a JSON document, which
is why they live here rather than in the prose half of the skill.

    parallax status --json | parallax_next.py --status -
    parallax run --json 2>err.json; parallax_next.py --error err.json

WHY A LOOKUP AND NOT A JUDGEMENT

1. THE STATE LIVES ON DISK, NOT IN THE CONVERSATION. A Parallax session is a new
   OS process every turn and an ActiveOntology cannot cross a process boundary.
   An agent that infers "we already accepted that" from message history is
   reading a cache that does not exist. `parallax status --json` is the
   authority; this maps its answer to the one next command.

2. AN ERROR IS A CODE, NOT A SENTENCE. Every surface returns
   {ok:false,error:{code,reason,detail?}}. The `reason` is for a human. The
   `code` is what a caller branches on, and several codes have remedies that a
   plain reading of the reason will not produce -- RECONCILIATION_UNACKNOWLEDGED
   requires telling the human something BEFORE retrying, and WORKSPACE_DENIED
   means a read was refused and came back as an empty directory rather than an
   error, so it looks like an empty workspace and not like a denial.

Exit codes: 0 a next step was determined; 3 the input parsed but names no known
state or code; 2 the input is not the document this was given.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# --------------------------------------------------------------------------
# error code -> remedy
#
# Sourced from runtime/src/tools/errors.ts. A code absent here is reported as
# unknown rather than guessed at: an invented remedy for a real refusal is worse
# than saying the code is unrecognised, because it sends the caller somewhere.
# --------------------------------------------------------------------------

REMEDIES: dict[str, str] = {
    # containment -- a path this surface refused to follow
    "PATH_ABSOLUTE": (
        "`within` must be RELATIVE. Do not derive an absolute path; the tool surface "
        "has no path argument on purpose."
    ),
    "PATH_ESCAPES_WORKSPACE": "`within` contained `..`. Stay inside the workspace root.",
    "PATH_NOT_FOUND": "The relative sub-path does not exist. Check it with a directory listing first.",
    "WORKSPACE_UNREADABLE": "The working directory cannot be read. This is the environment, not Parallax.",
    "ROOT_NOT_ALLOWED": (
        "`--root` is a CLI-only flag. Through the tool surface, change the session's "
        "working directory instead -- there is no root argument by design."
    ),
    "WORKSPACE_DENIED": (
        "A read was DENIED by the sandbox. Critically, a denied read surfaces as an EMPTY "
        "DIRECTORY rather than an error, so this looks identical to an empty workspace. "
        "Do not retry with a derived path; confirm which directory the session was given."
    ),
    "WORKSPACE_NOT_WRITABLE": (
        "Parallax writes thread state to `.parallax/` and the directory is read-only. "
        "The directory is broken, not Parallax. Say so rather than reporting a defect."
    ),
    "TABLES_REQUIRED": "kind is `business-data`, so `tables` is required.",
    "COLUMNS_REQUIRED": (
        "A table was supplied with an empty `columns` array. Name its columns. This used "
        "to be accepted -- the boundary said it needed columns and only counted tables -- "
        "so an older caller that 'worked' may now correctly refuse."
    ),
    "INVALID_ROW_COUNT": (
        "`rowCount` must be a whole number >= 0. Omit it entirely to propose a schema with "
        "no data; do not send -1 or a float to mean 'unknown'."
    ),
    "ORIGIN_REQUIRED": (
        "The table claims rows exist but some columns do not say where their values came "
        "from. Tag each column `observed` (read from an artifact you can produce) or "
        "`simulated` (concluded, matched, or estimated). Do NOT tag everything `simulated` "
        "to get past this: provenance is assigned at birth and nothing downstream can "
        "recover it, so a wrong tag is permanent. `detail.columns` lists the untagged ones."
    ),
    # pending-proposal addressing
    "NO_PENDING_PROPOSAL": "Nothing is pending. Run `parallax propose` first.",
    "UNKNOWN_REF": "No proposal starts with that ref. `parallax status` lists the pending ones.",
    "AMBIGUOUS_REF": "The ref prefix matches more than one proposal. Use more characters.",
    "QUESTION_OUT_OF_RANGE": (
        "`n` indexes the STORED proposal's blocking questions. Never renumber them yourself; "
        "re-read the numbering with `parallax render`."
    ),
    # re-minting an acceptance in a new process
    "WORKSPACE_MOVED": "The workspace moved since acceptance. Re-propose and re-accept; do not re-derive silently.",
    "PROPOSER_CHANGED": "The proposer changed since acceptance. Re-propose and re-accept.",
    "PROPOSAL_STALE": "The proposal changed since it was accepted. Re-propose and re-accept.",
    "UNKNOWN_DOMAIN": "No such registered domain. `parallax status --json` lists `domains`.",
    "DOMAIN_CHANGED": "The domain's code changed since acceptance. Re-accept against the current domain.",
    "DOMAIN_INVALID": "The registered domain is missing a transition or its invariants.",
    "RECONCILIATION_UNACKNOWLEDGED": (
        "TELL THE HUMAN FIRST, then retry. `detail.unmappedFromContext` lists fields the human was "
        "shown as read from their own context that the executable domain ignores. Relay that list "
        "verbatim, and only then call again with `acknowledgeUnmapped` / `--acknowledge-unmapped`. "
        "Setting it without telling them defeats the gate."
    ),
    # running
    "NO_ACCEPTED_ONTOLOGY": "Nothing has been accepted in this workspace. Accept a proposal first.",
    "UNKNOWN_ONTOLOGY": "No acceptance with that id. `parallax status` lists them.",
    "NOT_ACCEPTED": "An ontology nobody accepted cannot run. This is the product's central gate.",
    "BLOCKING_QUESTIONS_OPEN": (
        "Blocking questions are still open. Answer them with `parallax answer` -- units on numeric "
        "quantities are ALWAYS blocking and the gate will not yield on them."
    ),
    "UNANSWERED_BLOCKING": "At least one blocking question has no answer. `parallax answer` first.",
    "UNKNOWN_QUESTION": "That question number is not in the stored proposal.",
    "EMPTY_REPLY": "The reply text was empty. Pass the human's message verbatim.",
    # proposing
    "SOURCE_UNREADABLE": "The context could not be read.",
    "SOURCE_EMPTY": (
        "The context is empty. If the session is sandboxed, consider that a DENIED read also "
        "reads back as empty -- see WORKSPACE_DENIED before concluding the directory is bare."
    ),
    "UNSUPPORTED_SOURCE": "That `kind` is not supported.",
    "DEGENERATE_CONTEXT": "There was not enough in the context to build an ontology from.",
    "NO_TRANSITION": "The domain supplies no transition function.",
    "NO_INVARIANTS": "The domain declares no invariants, so nothing could be checked.",
    "NO_ACTIONS": "The proposed ontology has no actions, so there is nothing to roll forward.",
    # policies and rollout
    "POLICY_THREW": "The policy threw. A policy that throws is a defect in the policy.",
    "POLICY_EMPTY": "The policy chose no action.",
    "UNKNOWN_POLICY": "No policy registered under that name.",
    "EMPTY_TRAJECTORY": "The rollout produced no steps.",
    "OBJECTIVE_THREW": "The objective function threw.",
    # receipts
    "UNKNOWN_RUN": "No run starts with that id. `parallax status` lists the runs.",
    # argument handling
    "INVALID_INPUT": "Input failed schema validation. `detail.field` names the field.",
    "MISSING_FLAG": "A required flag was not given. `parallax help` prints each command's usage.",
    "UNKNOWN_FLAG": (
        "An unrecognised flag. It is refused rather than ignored on purpose: a silently dropped "
        "`--seed` produces a run at a seed nobody chose."
    ),
    "BAD_FLAG_VALUE": "A flag value was rejected. `detail.given` shows what was passed.",
    "NO_COMMAND": "No command was given. `parallax help`.",
    "UNKNOWN_COMMAND": "No such command. `parallax help` lists them.",
    "UNEXPECTED": (
        "Something threw instead of returning a typed error. This is a DEFECT in Parallax, not a "
        "refusal -- exit code 1 rather than 2. Report it with `detail.cause`."
    ),
}


def remedy(code: str) -> str | None:
    """The remedy for an error code, or None when the code is unrecognised."""
    return REMEDIES.get(code)


# --------------------------------------------------------------------------
# status -> next command
# --------------------------------------------------------------------------


def _ref(status: dict[str, Any]) -> str:
    head = status.get("head")
    return head.get("ref", "<ref>") if isinstance(head, dict) else "<ref>"


def _open_questions(status: dict[str, Any]) -> list[dict[str, Any]]:
    head = status.get("head")
    if not isinstance(head, dict):
        return []
    rows = head.get("blockingRemaining")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def next_step(status: dict[str, Any]) -> tuple[str | None, str] | None:
    """(command, why) for a StatusValue, or None if the state is not one we know.

    Mirrors the state machine in runtime/src/tools/handlers.ts: a pending head takes
    precedence over acceptances and runs, so a new proposal moves the thread back
    to PROPOSED even in a workspace that has already run.
    """
    if status.get("readable") is False:
        # No command, deliberately. Returning `parallax status` here -- the command
        # that produced this very result -- invites an agent to retry it in the same
        # workspace forever. Nothing Parallax offers fixes an unreadable directory;
        # the remedy is outside the tool.
        return (
            None,
            "The workspace is not readable, and no Parallax command changes that. Give the "
            "session a readable working directory, then start again. Note a DENIED read "
            "reports as an EMPTY directory rather than an error, so an unexpectedly empty "
            "workspace is the same symptom wearing a different face.",
        )

    state = status.get("state")

    if state == "IDLE":
        return (
            "parallax propose",
            "Nothing is pending, accepted or run in this workspace. Propose an ontology from "
            "what is actually in the directory.",
        )

    if state in ("PROPOSED", "PARTIAL"):
        qs = _open_questions(status)
        first = qs[0].get("n", 1) if qs else 1
        answered = "no answers recorded yet" if state == "PROPOSED" else "some answers already recorded"
        return (
            f"parallax answer --proposal {_ref(status)} --answer {first}=<value>",
            f"{len(qs)} blocking question(s) open, {answered}. Answers accumulate without "
            "accepting, so this does not imply consent. `n` indexes the STORED proposal -- "
            "never renumber the questions.",
        )

    if state == "READY":
        return (
            f"parallax accept --proposal {_ref(status)} --by <who>",
            "No blocking questions remain, so the proposal can be accepted. Expect a refusal "
            "of RECONCILIATION_UNACKNOWLEDGED if the domain ignores context fields the human "
            "was shown -- that is the gate working, not a bug.",
        )

    if state == "ACCEPTED":
        return (
            "parallax run",
            "An ontology is accepted and nothing has been run against it yet. Omitting "
            "--ontology means the most recent acceptance.",
        )

    if state == "RAN":
        return (
            "parallax receipt",
            "A run exists. Relay the receipt's link or path -- do NOT restate any number from "
            "the run in your own words; a restated number is an invented one the moment it is wrong.",
        )

    return None


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def _load(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    return json.loads(text)


def _unwrap(doc: Any) -> Any:
    """Accept either a bare value or the {ok,value}/{ok,error} envelope around it."""
    if isinstance(doc, dict) and "ok" in doc:
        if doc.get("ok") is True and isinstance(doc.get("value"), dict):
            return doc["value"]
        if doc.get("ok") is False and isinstance(doc.get("error"), dict):
            return doc["error"]
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", metavar="FILE", help="`parallax status --json` output, or - for stdin")
    g.add_argument("--error", metavar="FILE", help="an error envelope, or - for stdin")
    ap.add_argument("--json", action="store_true", help="emit a JSON object instead of prose")
    a = ap.parse_args(argv)

    src = a.status or a.error
    try:
        doc = _unwrap(_load(src))
    except (OSError, json.JSONDecodeError) as e:
        print(f"could not read {src}: {e}", file=sys.stderr)
        return 2
    if not isinstance(doc, dict):
        print(f"expected a JSON object, got {type(doc).__name__}", file=sys.stderr)
        return 2

    if a.error:
        code = doc.get("code")
        if not isinstance(code, str):
            print("no `code` field -- is this an error envelope?", file=sys.stderr)
            return 2
        fix = remedy(code)
        if fix is None:
            if a.json:
                print(json.dumps({"code": code, "known": False}))
            else:
                print(f"{code}: unrecognised code, no remedy on file")
            return 3
        if a.json:
            print(json.dumps({"code": code, "known": True, "remedy": fix}))
        else:
            print(f"{code}\n  {fix}")
        return 0

    step = next_step(doc)
    if step is None:
        if a.json:
            print(json.dumps({"state": doc.get("state"), "known": False}))
        else:
            print(f"unrecognised state: {doc.get('state')!r}", file=sys.stderr)
        return 3
    command, why = step
    if a.json:
        print(json.dumps({"state": doc.get("state"), "known": True, "next": command, "why": why}))
    elif command is None:
        # Determined, and the determination is "no Parallax command applies".
        print(f"next: (none -- this needs a change outside Parallax)\nwhy:  {why}")
    else:
        print(f"next: {command}\nwhy:  {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
