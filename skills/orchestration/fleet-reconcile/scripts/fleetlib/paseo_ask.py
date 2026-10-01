"""The owner channel on Paseo: asks and alerts as Maestro work at "Needs you".

Owner decision, 2026-10-01: owner notifications go through the Paseo app,
never a macOS dialog, banner, ntfy or log file ("If it goes to the computer
and I'm not there it won't work"). It replaces the dialog that
broomva/workspace#842 (§5.7) chose for `fleet act ask`.

Measured on 2026-10-01 with Maestro for Paseo and Claude Code 2.1.280:
`maestro new <title> --brief <text> --repo <git repo> --dispatch` starts a
Paseo agent in a fresh worktree of the repo. Told to change nothing and end
with `## Decided` and `## Ask`, it ran one turn in under a minute. The item
then reached `review`, which Maestro shows as Needs you, with the ask as its
look at the gate. The run agent's Paseo record read `requiresAttention: true`
(reason `finished`), which the app shows as needing attention on each client.
That was measured at the daemon, which the app renders from, not on a phone.

A session can't pass a human gate. The owner answers in Maestro:
- Approve is acknowledged;
- Send back with a note is the answer, recorded with the asks;
- Block, or Cancel, is dismissed.

Each tick reads the human gate event or the cancel back into the ledger as the
answer. The runs go to the fleet's own scratch repo, never a scope repo.
Every ask costs one turn of the provider Maestro is configured with.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import common
from .sources import child_env

MAESTRO_CLI = "~/broomva/apps/maestro-paseo/bin/maestro.ts"
BUN = "~/.bun/bin/bun"
ASK_REPO = "~/.local/state/fleet-reconcile/maestro-asks"
#: maestro's exit codes: 1 refused, 2 not listening or bad usage, 3 no clear
#: answer (the request may have applied: check before retrying).
EXITS = {1: "Maestro refused", 2: "Maestro is not listening", 3: "Maestro gave no clear answer"}


class MaestroError(RuntimeError):
    def __init__(self, code: Optional[int], detail: str) -> None:
        super().__init__(detail)
        self.code = code


def command(sec: Dict[str, Any]) -> List[str]:
    """How to run the maestro CLI: FLEET_MAESTRO_BIN (tests), else bun and the CLI."""
    if os.environ.get("FLEET_MAESTRO_BIN"):
        return [os.environ["FLEET_MAESTRO_BIN"]]
    return [str(common.expand(sec.get("maestro_bun") or BUN)), str(common.expand(sec.get("maestro_cli") or MAESTRO_CLI))]


def run(sec: Dict[str, Any], args: List[str], timeout: float = 90) -> Dict[str, Any]:
    try:
        proc = subprocess.run(command(sec) + args + ["--json"], stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout, env=child_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MaestroError(None, "maestro didn't run: %s" % common.safe_text(exc, 120))
    if proc.returncode != 0:
        raise MaestroError(proc.returncode, "%s (exit %d): %s" % (
            EXITS.get(proc.returncode, "maestro failed"), proc.returncode,
            common.safe_text(proc.stderr or proc.stdout, 160)))
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        raise MaestroError(None, "maestro printed no JSON: %s" % common.safe_text(proc.stdout, 120))
    if not isinstance(out, dict):
        raise MaestroError(None, "maestro printed JSON that isn't an object")
    return out


def ensure_repo(sec: Dict[str, Any]) -> str:
    """The fleet's own scratch repo for ask runs (a git repo with one commit)."""
    repo = common.expand(sec.get("ask_repo") or ASK_REPO)
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        for args in (["init", "-q", "-b", "main"],
                     ["-c", "user.name=fleet", "-c", "user.email=fleet@localhost", "commit", "-q", "--allow-empty",
                      "-m", "fleet-reconcile ask runs"]):
            subprocess.run(["git", "-C", str(repo)] + args, check=True, capture_output=True, timeout=30)
    return str(repo)


def brief(scope: str, lead: str, asks: List[str], closing: str) -> str:
    lines = [lead, "", "Change nothing and run no tools. End your turn at once with exactly two sections: "
             "'## Decided' with one bullet, 'nothing', and '## Ask' with these bullets, word for word:"]
    lines += ["- %s" % common.safe_text(a, 400) for a in asks]
    lines += ["- %s" % closing, "", "If the owner sends a note back, end again at once with '## Decided' quoting "
              "the note and '## Ask' with one bullet: approve to close."]
    return "\n".join(lines)


def raise_item(sec: Dict[str, Any], title: str, text: str) -> Dict[str, Any]:
    """Create the work and dispatch its run; returns the item."""
    out = run(sec, ["new", common.safe_text(title, 120), "--brief", text, "--repo", ensure_repo(sec),
                    "--initiative", "fleet-reconcile-%s" % sec["scope"], "--dispatch"])
    item = out.get("item") if isinstance(out.get("item"), dict) else {}
    if not isinstance(item.get("id"), str):
        raise MaestroError(None, "maestro made no item id")
    return item


def answer(sec: Dict[str, Any], item_id: str) -> Dict[str, Any]:
    """{state, verdict, note, at}: verdict is the owner's (approve, revise or
    block, from the latest human gate event), or cancel, or None while the
    item waits."""
    out = run(sec, ["show", item_id])
    item = out.get("item") if isinstance(out.get("item"), dict) else {}
    events = out.get("events") if isinstance(out.get("events"), list) else []
    gate = [e for e in events if isinstance(e, dict) and e.get("type") == "gate" and e.get("actor") == "human"]
    res: Dict[str, Any] = {"state": item.get("state"), "verdict": None, "note": None, "at": None}
    if gate:
        g = gate[-1]
        res.update(verdict=g.get("verdict"), note=common.safe_text(g.get("note"), 200) or None, at=g.get("ts"))
    elif item.get("state") == "canceled":
        res.update(verdict="cancel", at=item.get("updatedAt"))
    return res
