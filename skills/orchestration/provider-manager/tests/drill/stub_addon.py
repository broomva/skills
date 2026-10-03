"""mitmproxy addon: answers every request locally from fake_anthropic's state. Nothing is forwarded.

/v1/messages streams SSE. The main loop (requests that carry the Bash tool) gets a Bash tool_use for
calls 1..N-1 and a final "DRILL-DONE" text for call N. Before answering main call g (DRILL_GATES,
e.g. "2,4"), the addon writes gate-<g>.reached and waits for gate-<g>.release, so the driver can
switch accounts while the session is between requests. The command answered at a gate sleeps past
Claude Code's 30-second keychain read cache, so the next request sees the switched store. Every main call's bearer is resolved to an
account and logged to served.jsonl.
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.environ["DRILL_FAKEWORLD"])

import fake_anthropic  # noqa: E402
from mitmproxy import http  # noqa: E402

DRILL_DIR = os.environ["DRILL_DIR"]
MAIN_CALLS = int(os.environ.get("DRILL_MAIN_CALLS", "5"))
GATES = {int(g) for g in os.environ.get("DRILL_GATES", "").split(",") if g.strip()}
# Claude Code caches its keychain read for 30 s (WNn=30000 in 2.1.280): the command answered at a gate
# sleeps past that, so the next request reads the store as the switch left it.
SLEEP_AFTER_GATE = int(os.environ.get("DRILL_SLEEP_AFTER_GATE", "32"))


def _log(name, rec):
    rec["ts"] = time.time()
    with open(os.path.join(DRILL_DIR, name), "a") as f:
        f.write(json.dumps(rec) + "\n")


def _sse(events):
    out = []
    for ev in events:
        out.append("event: %s\ndata: %s\n\n" % (ev["type"], json.dumps(ev)))
    return "".join(out).encode()


def _message(content_blocks, stop_reason):
    events = [{"type": "message_start", "message": {
        "id": "msg_drill_%d" % int(time.time() * 1000), "type": "message", "role": "assistant",
        "model": "claude-haiku-4-5", "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 1}}}]
    for i, block in enumerate(content_blocks):
        if block["type"] == "text":
            events.append({"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})
            events.append({"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": block["text"]}})
        else:
            events.append({"type": "content_block_start", "index": i, "content_block": {
                "type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}})
            events.append({"type": "content_block_delta", "index": i, "delta": {
                "type": "input_json_delta", "partial_json": json.dumps(block["input"])}})
        events.append({"type": "content_block_stop", "index": i})
    events.append({"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                   "usage": {"output_tokens": 5}})
    events.append({"type": "message_stop"})
    return _sse(events)


class Stub:
    def __init__(self):
        self.main = 0

    async def request(self, flow: http.HTTPFlow):
        host = flow.request.pretty_host
        path = flow.request.path.split("?", 1)[0]
        auth = flow.request.headers.get("authorization", "")
        bearer = auth[7:] if auth.lower().startswith("bearer ") else None

        def reply(status, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            flow.response = http.Response.make(status, data, {"content-type": ctype})

        if host == "platform.claude.com" and path == "/v1/oauth/token":
            try:
                body = json.loads(flow.request.get_text() or "{}")
            except ValueError:
                body = {}
            status, payload = fake_anthropic.token_refresh(body.get("refresh_token"))
            _log("token.jsonl", {"status": status})
            return reply(status, payload)
        if host == "api.anthropic.com" and path == "/api/oauth/profile":
            return reply(*fake_anthropic.profile(bearer))
        if host == "api.anthropic.com" and path == "/api/oauth/usage":
            return reply(*fake_anthropic.usage(bearer))
        if host == "api.anthropic.com" and path == "/v1/messages":
            try:
                req = json.loads(flow.request.get_text() or "{}")
            except ValueError:
                req = {}
            is_main = any((t or {}).get("name") == "Bash" for t in req.get("tools") or [])
            status, payload = fake_anthropic.messages(bearer)
            email = fake_anthropic.email_for_access(bearer) if bearer else None
            if not is_main:
                _log("side.jsonl", {"status": status, "email": email})
                if status != 200:
                    return reply(status, payload)
                return reply(200, _message([{"type": "text", "text": "OK"}], "end_turn"), "text/event-stream")
            if status != 200:
                _log("served.jsonl", {"call": self.main + 1, "status": status, "email": email})
                return reply(status, payload)
            self.main += 1
            n = self.main
            _log("served.jsonl", {"call": n, "status": status, "email": email})
            if n in GATES:
                open(os.path.join(DRILL_DIR, "gate-%d.reached" % n), "w").close()
                deadline = time.time() + 120
                while not os.path.exists(os.path.join(DRILL_DIR, "gate-%d.release" % n)) and time.time() < deadline:
                    await asyncio.sleep(0.1)
            if n >= MAIN_CALLS:
                return reply(200, _message([{"type": "text", "text": "DRILL-DONE"}], "end_turn"), "text/event-stream")
            command = ("sleep %d; echo tick-%d" % (SLEEP_AFTER_GATE, n)) if n in GATES else "echo tick-%d" % n
            tool = {"type": "tool_use", "id": "toolu_drill_%d" % n, "name": "Bash",
                    "input": {"command": command, "description": "drill tick", "timeout": 120000}}
            return reply(200, _message([tool], "tool_use"), "text/event-stream")
        _log("other.jsonl", {"host": host, "path": path})
        return reply(200, {})


addons = [Stub()]
