"""Shared set-up for the System 1 / System 2 tests: a small corpus in the
scratch world's broomva repo, a built cache, parameters, and a hook runner.

The corpus has one of everything the gate must keep and everything it must
drop: a spec and an entity that cite scripts/gate.py, a memory rule, a person
entity, a crm entity, a claim holding a credential-shaped token, a citation
into crm/, and a user-type memory file.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
S1_WRAPPER = SCRIPTS / "ctx-s1-hook.sh"
S1_HOOK = SCRIPTS / "ctx_s1_hook.py"
CTX = SCRIPTS / "ctx.py"
S1CLI = SCRIPTS / "ctx_s1_cli.py"

SPEC = """<!doctype html><html><head><title>Gate design</title>
<meta name="description" content="The write gate runs before every edit and records each refusal in the gate log.">
</head><body><h1>Gate design</h1>
<p>It lives in scripts/gate.py; the branch feat/x carries the rewrite. Ticket BRO-4242.</p>
</body></html>
"""
ENTITY = """---
id: "pattern/gate-that-cannot-fail"
title: "A gate that cannot fail"
type: pattern
created: "2026-09-01"
core_claim: "A gate whose only branch is pass measures nothing; zebrafish tests found it."
tags:
  - gate
---
# A gate that cannot fail

Seen in scripts/gate.py, where the refusal branch was unreachable. Related: [[crm-link]].
This page is research/entities/pattern/gate-that-cannot-fail.md.
"""
PERSON = """---
id: "person/alice"
type: person
created: "2026-09-01"
core_claim: "Alice Example owns scripts/gate.py and reviews every change to it."
---
Alice works on scripts/gate.py.
"""
PERSON_UNTYPED = """---
id: "person/bob"
created: "2026-09-01"
core_claim: "Bob Example keeps the zebrafish gate's on-call rota."
---
scripts/gate.py
"""
PERSON_ELSEWHERE = """---
id: "concept/carol"
type: person
created: "2026-09-01"
core_claim: "Carol Example signed off the zebrafish gate design."
---
scripts/gate.py
"""
CRM = """---
id: "crm/acme"
type: org
created: "2026-09-01"
core_claim: "Acme renews in March; the deal owner is in scripts/gate.py notes."
---
scripts/gate.py
"""
LEAKY = """---
id: "tool/leaky"
type: tool
created: "2026-09-01"
core_claim: "The gate token ghp_abcdefghijklmnopqrstuvwxyz0123456789 unlocks scripts/gate.py."
---
scripts/gate.py
"""
CRM_LINK = """---
id: "tool/crm-link"
type: tool
created: "2026-09-01"
core_claim: "The zebrafish importer reads lead files from the crm tree."
---
It reads crm/leads/acme.md and scripts/importer.py.
"""
MEMORY_RULE = """---
name: gate-rule
description: "Writes under ops/ pass through the zebrafish gate before they land."
metadata:
  type: feedback
---
The rule: scripts/gate.py is the one door.
"""
MEMORY_USER = """---
name: owner-profile
description: "The owner prefers morning reviews and lives in Bogota."
metadata:
  type: user
---
scripts/gate.py
"""

LOW_FLOORS = {"version": "test-low", "stages": {
    s: {"floor": 0.01} for s in ("session-start", "compact", "prompt", "pre-edit", "post-read", "post-bash",
                                 "subagent")}}


def memory_dir(home: Path, repo: Path) -> Path:
    return home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo)) / "memory"


def write_corpus(world) -> None:
    b = world.broomva
    (b / "docs" / "specs").mkdir(parents=True)
    (b / "docs" / "specs" / "2026-09-01-gate-design.html").write_text(SPEC)
    ents = b / "research" / "entities"
    for rel, text in (("pattern/gate-that-cannot-fail.md", ENTITY), ("person/alice.md", PERSON),
                      ("person/bob.md", PERSON_UNTYPED), ("concept/carol.md", PERSON_ELSEWHERE),
                      ("crm/acme.md", CRM), ("tool/leaky.md", LEAKY), ("tool/crm-link.md", CRM_LINK)):
        (ents / rel).parent.mkdir(parents=True, exist_ok=True)
        (ents / rel).write_text(text)
    (b / "scripts").mkdir()
    (b / "scripts" / "gate.py").write_text("def gate():\n    return True\n")
    (b / "scripts" / "other.py").write_text("x = 1\n")
    md = memory_dir(world.home, b)
    md.mkdir(parents=True)
    (md / "gate-rule.md").write_text(MEMORY_RULE)
    (md / "owner-profile.md").write_text(MEMORY_USER)
    (md / "MEMORY.md").write_text("- [Gate rule](gate-rule.md)\n")


def build(world, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(S1CLI), "build", "--no-network", "--json"],
                          cwd=str(cwd or world.broomva), capture_output=True, text=True, timeout=120)


def write_params(tmp: Path, body: Dict) -> Path:
    p = tmp / ("params-%d.json" % int(time.monotonic_ns()))
    p.write_text(json.dumps(body))
    return p


@dataclass
class S1Run:
    rc: int
    stdout: str
    elapsed: float

    @property
    def context(self) -> Optional[str]:
        if not self.stdout:
            return None
        return json.loads(self.stdout)["hookSpecificOutput"]["additionalContext"]

    @property
    def event(self) -> Optional[str]:
        return json.loads(self.stdout)["hookSpecificOutput"]["hookEventName"] if self.stdout else None


def run_s1(stage: str, payload: Dict, params: Optional[Path] = None, stages: Optional[str] = None,
           env: Optional[Dict[str, str]] = None, on: bool = True, budget_ms: Optional[str] = "5000",
           raw: Optional[str] = None, script: Optional[Path] = None) -> S1Run:
    full = {k: v for k, v in os.environ.items() if not k.startswith("CTX_S1")}
    full["CTX_PYTHON"] = sys.executable
    if on:
        full["CTX_S1"] = "1"
        full["CTX_S1_STAGES"] = stages or stage
    if params is not None:
        full["CTX_S1_PARAMS"] = str(params)
    if budget_ms:
        full["CTX_S1_BUDGET_MS"] = budget_ms
    full.update(env or {})
    data = raw if raw is not None else json.dumps(payload)
    cmd = (["/bin/sh", str(S1_WRAPPER), stage] if script is None
           else [sys.executable, "-I", "-S", str(script), stage])
    t0 = time.monotonic()
    p = subprocess.run(cmd, input=data.encode(), capture_output=True, env=full, timeout=60)
    return S1Run(p.returncode, p.stdout.decode(), time.monotonic() - t0)


def decisions(world, scope: str = "broomva") -> List[Dict]:
    log = world.store(scope) / "s1-decisions.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def edit(sid: str, cwd: Path, path: Path, **extra) -> Dict:
    d = {"session_id": sid, "cwd": str(cwd), "hook_event_name": "PreToolUse", "tool_name": "Edit",
         "tool_input": {"file_path": str(path), "old_string": "a", "new_string": "b"}, "tool_use_id": "toolu_1"}
    d.update(extra)
    return d


def read(sid: str, cwd: Path, path: Path) -> Dict:
    return {"session_id": sid, "cwd": str(cwd), "hook_event_name": "PostToolUse", "tool_name": "Read",
            "tool_input": {"file_path": str(path)}, "tool_response": {"type": "text"}}


def bash(sid: str, cwd: Path, command: str, stdout: str = "") -> Dict:
    return {"session_id": sid, "cwd": str(cwd), "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}, "tool_response": {"stdout": stdout, "stderr": ""}}


def prompt(sid: str, cwd: Path, text: str) -> Dict:
    return {"session_id": sid, "cwd": str(cwd), "hook_event_name": "UserPromptSubmit", "prompt": text,
            "prompt_id": "p1"}


def start(sid: str, cwd: Path, source: str = "startup") -> Dict:
    return {"session_id": sid, "cwd": str(cwd), "hook_event_name": "SessionStart", "source": source}


def subagent(sid: str, cwd: Path, agent_id: str, agent_type: str = "general-purpose") -> Dict:
    return {"session_id": sid, "cwd": str(cwd), "hook_event_name": "SubagentStart", "agent_id": agent_id,
            "agent_type": agent_type}


def _ts(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


class Transcript:
    """A transcript writer with Claude Code's record shapes, under the world's
    ~/.claude/projects. `tools` writes calls issued together (one assistant
    message id); `path` may be given for a subagent transcript."""

    def __init__(self, world, sid: str, cwd: Path, t0: float, path: Optional[Path] = None):
        self.sid, self.cwd, self.t, self.n, self.lines = sid, str(cwd), t0, 0, []
        if path is None:
            d = world.home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
            d.mkdir(parents=True, exist_ok=True)
            path = d / (sid + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def _rec(self, **kw):
        self.t += 5
        base = {"sessionId": self.sid, "cwd": self.cwd, "gitBranch": "main", "timestamp": _ts(self.t)}
        base.update(kw)
        self.lines.append(json.dumps(base))

    def prompt(self, text):
        self._rec(type="user", message={"role": "user", "content": text})

    def tool(self, name, _out="ok", **inp):
        return self.tools([(name, inp)], [_out])[0]

    def tools(self, calls, outs=None):
        """Calls issued in one assistant message, then their results."""
        self.n += 1
        mid = "msg_%s_%d" % (self.sid, self.n)
        ids = []
        for k, (name, inp) in enumerate(calls):
            tid = "toolu_%s_%d_%d" % (self.sid, self.n, k)
            ids.append(tid)
            self._rec(type="assistant", message={"id": mid, "role": "assistant", "content": [
                {"type": "tool_use", "id": tid, "name": name, "input": inp}]})
        for tid, out in zip(ids, outs or ["ok"] * len(calls)):
            self._rec(type="user", message={"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": out}]})
        return ids

    def skill_body(self, text):
        self._rec(type="user", isMeta=True, message={"role": "user", "content": text})

    def injected(self, text):
        self._rec(type="attachment", attachment={"type": "hook_additional_context", "hookEvent": "UserPromptSubmit",
                                                 "content": [text]})

    def save(self):
        self.path.write_text("\n".join(self.lines) + "\n")
