"""The coordinator (spec §5.3, §5.7): one headless `claude -p` per tick in act mode.

Its settings file registers the send gate on SendMessage (PreToolUse, and
PostToolUse plus PostToolUseFailure, 10 s each). Its argv disallows Agent,
Edit, Write and every pinned Paseo write tool, with `--` before the prompt,
since --disallowedTools takes every following word (evidence §1: without it the
prompt was read as a tool name and the run never replied). The stream-json
init event carries the session's tool list; a coordinator whose list holds
one of those tools, or a Paseo tool in neither pinned list, is terminated
before its first turn ends and the tick reports it.

The tool list is a posture, not a boundary: the coordinator runs unsandboxed,
and its Bash reaches git, gh and the Paseo CLI (§5.3).
"""
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, IO, Iterable, List, Optional

from . import common
from .sources import child_env

DISALLOWED = ("Agent", "Edit", "Write")
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
           "--output-format", "stream-json", "--verbose", "--permission-mode", "bypassPermissions"]
    if sec.get("coordinator_model"):
        out += ["--model", sec["coordinator_model"]]
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


def posture_problems(tools: Iterable[str], sec: Dict[str, Any]) -> List[str]:
    """What's wrong with the coordinator's tool list: a disallowed tool present,
    a pinned Paseo write tool present, or a Paseo tool in neither pinned list
    (Paseo registered one after the classification was pinned)."""
    pins = sec["paseo_tools"]
    read, write = set(pins.get("read") or []), set(pins.get("write") or [])
    tools = list(tools)
    out = ["%s is in the tool list" % t for t in DISALLOWED if t in tools]
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
                       dry="dry run: every verb but ask logs only" if dry else "LIVE").strip()


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
    if os.environ.get("GH_TOKEN"):
        extra["GH_TOKEN"] = os.environ["GH_TOKEN"]  # tick.sh exports the fleet token for this step
    res: Dict[str, Any] = {"exit": None, "posture": [], "init": False}
    with out_path.open("w", encoding="utf-8") as out, out_path.with_suffix(".err").open("w") as err:
        proc = subprocess.Popen(av, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True,
                                env=child_env(extra), start_new_session=True)
        res["exit"] = _pump(proc, out, sec, res)
    return res


def _pump(proc: "subprocess.Popen[str]", out: IO[str], sec: Dict[str, Any], res: Dict[str, Any]) -> int:
    assert proc.stdout is not None
    for line in proc.stdout:
        out.write(line)
        if not res["init"]:
            ev = init_event([line])
            if ev is not None:
                res["init"] = True
                res["posture"] = posture_problems(ev.get("tools") or [], sec)
                if res["posture"]:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except OSError:
                        pass
    proc.wait()
    return EXIT_POSTURE if res["posture"] else proc.returncode
