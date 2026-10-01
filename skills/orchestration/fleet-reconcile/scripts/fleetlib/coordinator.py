"""The coordinator (spec §5.3, §5.7): one headless `claude -p` per tick in act mode.

Its settings file registers the send gate on SendMessage (PreToolUse, and
PostToolUse plus PostToolUseFailure, 10 s each). Its argv disallows Agent,
Edit, Write, NotebookEdit and every pinned Paseo write tool, with `--` before
the prompt, since --disallowedTools takes every following word (evidence §1:
without it the prompt was read as a tool name and the run never replied); it
loads no MCP server (--strict-mcp-config, pending the spec, which names only
the Paseo writes: fleet act is its route, and the user-scope servers would be
238 tools of reach) and spends at most `coordinator_budget_usd`. The
stream-json init event carries the session's tool list; a coordinator whose
list holds a disallowed tool or a Paseo tool in neither pinned list, that acts
before its init event, or whose init event doesn't come within INIT_S, is
terminated and the tick reports it. claude stays in this process's group, so
tick.sh's watchdog (TERM, then KILL, to the step's group) reaches it.

The tool list is a posture, not a boundary: the coordinator runs unsandboxed,
and its Bash reaches git, gh and the Paseo CLI (§5.3).
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, IO, Iterable, List, Optional

from . import common
from .sources import child_env

#: Its whole tool list (--tools; measured on 2.1.280: the init event lists
#: exactly these): fleet act through Bash, the report through Read, and the
#: mail fleet act prepared through SendMessage. Anything else in its init
#: event stops it.
ALLOWED = ("Bash", "Read", "SendMessage")
DISALLOWED = ("Agent", "Edit", "Write", "NotebookEdit")
INIT_S = 60.0
PASEO_PREFIX = "mcp__paseo__"
SKILL = Path(__file__).resolve().parents[2]
EXIT_POSTURE = 4


def settings(fleet_bin: str, scope_id: str) -> Dict[str, Any]:
    def entry(which: str) -> List[Dict[str, Any]]:
        cmd = "%s send-gate %s --scope %s" % (shlex.quote(fleet_bin), which, shlex.quote(scope_id))
        return [{"matcher": "SendMessage", "hooks": [{"type": "command", "command": cmd, "timeout": 10}]}]
    return {"hooks": {"PreToolUse": entry("pre"), "PostToolUse": entry("post"), "PostToolUseFailure": entry("post")}}


def argv(sec: Dict[str, Any], settings_path: Path, prompt: str, claude: str = "claude") -> List[str]:
    out = [claude, "-p", "--name", "fleet-coordinator-%s" % sec["scope"], "--settings", str(settings_path),
           "--output-format", "stream-json", "--verbose", "--permission-mode", "bypassPermissions",
           "--strict-mcp-config", "--max-budget-usd", str(sec["coordinator_budget_usd"])]
    if sec.get("coordinator_model"):
        out += ["--model", sec["coordinator_model"]]
    out += ["--tools"] + list(ALLOWED)
    out += ["--disallowedTools"] + list(DISALLOWED) + [PASEO_PREFIX + t for t in sec["paseo_tools"]["write"]]
    return out + ["--", prompt]


def init_event(lines: Iterable[str]) -> Optional[Dict[str, Any]]:
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "system" and ev.get("subtype") == "init":
            return ev
    return None


def posture_problems(tools: Any, sec: Dict[str, Any]) -> List[str]:
    """What's wrong with the coordinator's tool list: no list at all, a tool
    outside ALLOWED (a disallowed one named as such), a pinned Paseo write
    tool, or a Paseo tool in neither pinned list (Paseo registered one after
    the classification was pinned)."""
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        return ["the init event carries no tool list, so it can't be checked"]
    pins = sec["paseo_tools"]
    read, write = set(pins.get("read") or []), set(pins.get("write") or [])
    out = ["%s is in the tool list" % t for t in DISALLOWED if t in tools]
    out += ["%s is outside the allowlist" % t for t in tools
            if t not in ALLOWED and t not in DISALLOWED and not t.startswith(PASEO_PREFIX)]
    for t in tools:
        if not t.startswith(PASEO_PREFIX):
            continue
        name = t[len(PASEO_PREFIX):]
        if name in write:
            out.append("Paseo write tool %s is in the tool list" % name)
        elif name not in read:
            out.append("Paseo tool %s is in neither pinned list (pinned on Paseo %s)" % (
                name, pins.get("paseo_version") or "?"))
    return out


def prompt(sec: Dict[str, Any], tick: int, report_json: Path, dry: bool, fleet_bin: str) -> str:
    text = (SKILL / "templates" / "runner-prompt.md").read_text(encoding="utf-8")
    return text.format(scope=sec["scope"], tick=tick, report=str(report_json), fleet=fleet_bin,
                       hours=sec["mail_interval_h"],
                       dry="DRY RUN: spawn, label and resume only log what they would do, and a mail's "
                           "SendMessage is checked, recorded and blocked" if dry else "LIVE").strip()


def run(sec: Dict[str, Any], tick: int, fleet_bin: str, out_path: Path, dry: bool,
        claude: str = "claude") -> Dict[str, Any]:
    """Start the coordinator, copy its stream to out_path, and terminate it if
    its init event fails the posture check. Returns {exit, posture, init}."""
    sd = Path(sec["state_dir"])
    sp = sd / "coordinator-settings.json"
    common.write_atomic(sp, (json.dumps(settings(fleet_bin, sec["scope"]), indent=1) + "\n").encode())
    os.chmod(str(sp), 0o600)
    report_json = out_path.parent / "report.json"
    av = argv(sec, sp, prompt(sec, tick, report_json, dry, fleet_bin), claude)
    extra = {"FLEET_TICK": str(tick), "FLEET_SCOPE": sec["scope"], "DRY_RUN": "1" if dry else "0"}
    res: Dict[str, Any] = {"exit": None, "posture": [], "init": False}
    with out_path.open("w", encoding="utf-8") as out, out_path.with_suffix(".err").open("w") as err:
        proc = subprocess.Popen(av, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True,
                                env=child_env(extra))
        res["exit"] = _pump(proc, out, sec, res)
    return res


def _stop(proc: "subprocess.Popen[str]") -> None:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    except OSError:
        pass


def _pump(proc: "subprocess.Popen[str]", out: IO[str], sec: Dict[str, Any], res: Dict[str, Any],
          init_s: Optional[float] = None) -> int:
    """Copy the stream; stop the coordinator on a failed posture, on an event
    before the init event (it acted unchecked), or when no init event came."""
    assert proc.stdout is not None
    init_s = INIT_S if init_s is None else init_s

    lock = threading.Lock()

    def late() -> None:
        with lock:
            if res["init"] or res["posture"]:
                return
            res["posture"] = ["no init event within %ds: the tool list was never checked" % init_s]
        _stop(proc)
    timer = threading.Timer(init_s, late)
    timer.daemon = True
    timer.start()
    try:
        for line in proc.stdout:
            out.write(line)
            with lock:
                if res["init"] or res["posture"]:
                    continue  # decided (a late init can't undo the deadline's stop)
                ev = init_event([line])
                if ev is not None:
                    res["init"] = True
                    res["posture"] = posture_problems(ev.get("tools"), sec)
                elif _acts(line):
                    res["posture"] = ["it acted before its init event: the tool list was never checked"]
            if res["posture"]:
                _stop(proc)
                break  # its stream is no longer read: a child still holding it can't delay the stop
    finally:
        timer.cancel()
    proc.wait()
    return EXIT_POSTURE if res["posture"] else proc.returncode


def _acts(line: str) -> bool:
    try:
        ev = json.loads(line)
    except ValueError:
        return False
    return isinstance(ev, dict) and ev.get("type") in ("assistant", "user", "result")
