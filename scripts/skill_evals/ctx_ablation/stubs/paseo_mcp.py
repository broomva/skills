#!/usr/bin/env python3
"""A stdio MCP server named ``paseo`` with the real ``list_agents`` defaults.

The trap it reproduces is measured, not invented (memory
``paseo-sidebar-lists-workspaces-not-agents``, source
``apps/paseo/packages/server/src/server/agent/tools/paseo-tools.ts``):
``list_agents`` filters to the CALLER's cwd subtree unless ``cwd`` is passed, and
caps at ``limit`` 50. Worktree sessions live under ``~/.paseo/worktrees``, outside
the caller's checkout, so the default call undercounts, and ``cwd:"/"`` alone still
truncates a fleet of more than 50. Only ``cwd:"/", limit:200`` returns every agent.

The fleet comes from ``stubs.json`` (``paseo.agents``, and ``paseo.fleet`` groups;
see :func:`fleet`). Paths starting ``~`` resolve against the case HOME. The caller's cwd
is this process's cwd, which the CLI sets to the session's project directory.

Every ``tools/call`` is logged with its arguments. Pure stdlib, newline-delimited
JSON-RPC 2.0 over stdio.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common  # noqa: E402

NAME = "paseo"
DEFAULT_LIMIT = 50

TOOLS = [
    {
        "name": "list_agents",
        "description": "List Paseo agents. Filters to agents whose cwd is the given cwd or "
                       "below it (defaults to the caller's cwd). Returns at most `limit` "
                       "agents (default 50), newest first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Only agents at or below this directory. Defaults to the caller's cwd."},
                "limit": {"type": "number", "description": "Maximum agents to return (default 50)."},
                "includeArchived": {"type": "boolean", "description": "Include archived agents."},
            },
        },
    },
    {
        "name": "get_agent_status",
        "description": "Get the status of one Paseo agent by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"agentId": {"type": "string"}},
            "required": ["agentId"],
        },
    },
]


def _home() -> str:
    return os.environ.get("HOME") or os.path.expanduser("~")


def _expand(path: str) -> str:
    if path.startswith("~"):
        path = _home() + path[1:]
    return os.path.realpath(path)


def _under(child: str, parent: str) -> bool:
    parent = parent.rstrip("/") or "/"
    return parent == "/" or child == parent or child.startswith(parent + "/")


def fleet() -> list[dict]:
    """``paseo.agents`` verbatim, plus ``paseo.fleet`` groups expanded:
    ``{"count": 44, "cwd": "~/.paseo/worktrees/w{i}/main", "status": "idle"}``."""
    cfg = _common.config(NAME)
    out = list(cfg.get("agents") or [])
    for g_i, group in enumerate(cfg.get("fleet") or []):
        for i in range(int(group.get("count", 0))):
            out.append({
                "id": f"agent-{g_i}{i:03d}",
                "cwd": str(group.get("cwd", "~")).replace("{i}", f"{i:03d}"),
                "status": group.get("status", "idle"),
                "title": str(group.get("title", "session {i}")).replace("{i}", str(i)),
            })
    return out


def list_agents(args: dict) -> dict:
    fleet_rows = fleet()
    cwd = args.get("cwd")
    root = _expand(cwd) if isinstance(cwd, str) and cwd.strip() else os.path.realpath(os.getcwd())
    try:
        limit = int(args.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    include_archived = bool(args.get("includeArchived"))
    rows = []
    for a in fleet_rows:
        if a.get("status") == "archived" and not include_archived:
            continue
        a_cwd = _expand(str(a.get("cwd", "")))
        if _under(a_cwd, root):
            rows.append({**a, "cwd": a_cwd})
    rows = rows[: max(0, limit)]
    return {"agents": rows, "count": len(rows)}


def get_agent_status(args: dict) -> dict:
    for a in fleet():
        if a.get("id") == args.get("agentId"):
            return {"agent": a}
    return {"error": f"agent {args.get('agentId')!r} not found"}


def _reply(msg_id, result=None, error=None) -> None:
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> None:
    method, msg_id = msg.get("method"), msg.get("id")
    if method == "initialize":
        params = msg.get("params") or {}
        _reply(msg_id, {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "paseo", "version": "0.0.0-eval"},
        })
    elif method == "tools/list":
        _reply(msg_id, {"tools": TOOLS})
    elif method == "tools/call":
        params = msg.get("params") or {}
        name, args = params.get("name"), params.get("arguments") or {}
        fn = {"list_agents": list_agents, "get_agent_status": get_agent_status}.get(name)
        if fn is None:
            _reply(msg_id, error={"code": -32602, "message": f"unknown tool {name!r}"})
            return
        result = fn(args)
        # Coverage accumulates across calls, so two scoped calls that together return
        # the whole fleet count the same as one wide call.
        state = _common.load_state(NAME)
        seen = set(state.get("seen_live") or [])
        seen |= {a["id"] for a in result.get("agents") or [] if a.get("status") != "archived"}
        state["seen_live"] = sorted(seen)
        _common.save_state(NAME, state)
        live_total = sum(1 for a in fleet() if a.get("status") != "archived")
        _common.log(NAME, {"tool": name, "arguments": args, "returned": result.get("count"),
                           "covered_live": len(seen), "live_total": live_total})
        _reply(msg_id, {"content": [{"type": "text", "text": json.dumps(result)}]})
    elif method == "ping":
        _reply(msg_id, {})
    elif msg_id is not None:
        _reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if isinstance(msg, dict):
            handle(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
