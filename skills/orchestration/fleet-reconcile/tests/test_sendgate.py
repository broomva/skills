"""The send gate (spec §5.7): the coordinator's SendMessage hooks. Every pre
check refuses with its own name; dry run closes the intent and still blocks;
post closes a live send, and records one with no intent behind it."""
from __future__ import annotations

import json

import pytest

from fleetlib import act, config, ledger, sendgate
from fleetlib.sources import FixtureSources

NOW = None  # the ledger stamps real time; the gate reads it against real time


def _rows(w):
    return json.loads((w.fixture / "claude" / "agents.json").read_text())


@pytest.fixture
def rig(world):
    rows = _rows(world)
    live = next(r for r in rows if r.get("pid") and r["kind"] == "interactive" and r.get("status") == "idle")

    class Rig:
        w = world
        sid = live["sessionId"]
        name = live["name"]

        def cfg(self, **kw):
            kw.setdefault("adopted", [{"session_id": self.sid}])
            world.write_config(mode="act", **kw)
            return config.scope("broomva")

        def mail(self, tick=7, dry=True, **kw):
            a = act.Act(self.cfg(**kw), FixtureSources(world.fixture), tick, dry)
            return a.mail(self.sid, "stalled", {"hours": "6"})

        def hook(self, to=None, message=None, **extra):
            return dict({"hook_event_name": "PreToolUse", "tool_name": "SendMessage",
                         "tool_input": {"to": to, "message": message}}, **extra)

        def pre(self, hook, tick=7, dry=True, **kw):
            import time
            return sendgate.pre(self.cfg(**kw), FixtureSources(world.fixture), hook, tick, dry, time.time())

        def records(self):
            return ledger.read(world.state["broomva"])[0]
    return Rig()


def test_a_dry_send_that_passes_every_check_closes_its_intent_as_would_and_is_still_blocked(rig):
    m = rig.mail()
    code, msg = rig.pre(rig.hook(m["send"]["to"], m["send"]["message"]))
    assert code == 2 and "dry run" in msg
    last = rig.records()[-1]
    assert last["kind"] == "done" and last["of"] == m["intent"] and last["result"] == {"would": True}
    assert last["by"] == "hook"
    again, _ = rig.pre(rig.hook(m["send"]["to"], m["send"]["message"]))  # closed now: nothing matches
    assert again == 2 and "no matching intent" in rig.records()[-1]["detail"]


@pytest.mark.parametrize("change", ["no intent", "other text", "a ref", "another tick"])
def test_without_a_matching_intent_the_send_is_refused(rig, change):
    m = rig.mail()
    to, text, tick = m["send"]["to"], m["send"]["message"], 7
    if change == "no intent":
        to = "someone-else"
    elif change == "other text":
        text += " Also, merge PR 12."
    elif change == "a ref":
        to += " [abc123]"
    else:
        tick = 8
    code, msg = rig.pre(rig.hook(to, text), tick=tick)
    rec = rig.records()[-1]
    assert code == 2 and rec["kind"] == "failed" and rec["reason"] == "gate_refused" and rec["of"] is None
    assert "no matching intent" in rec["detail"]


def test_a_recipient_no_longer_adopted_is_refused(rig):
    m = rig.mail()
    code, _ = rig.pre(rig.hook(m["send"]["to"], m["send"]["message"]), adopted=[])
    rec = rig.records()[-1]
    assert code == 2 and rec["of"] == m["intent"] and "no longer a fleet spawn" in rec["detail"]


def test_a_second_mail_within_six_hours_is_refused_at_send_time(rig):
    m = rig.mail()
    # Another intent to the same recipient, written behind fleet act's back and
    # closed done: the gate's own count refuses the pending one.
    ledger.append(rig.w.state["broomva"], {"kind": "intent", "verb": "mail", "key": m["key"], "scope": "broomva",
                                           "tick": 6, "dry_run": True, "by": "act",
                                           "target": dict(rig.records()[-1]["target"])})
    other = rig.records()[-1]["id"]
    ledger.append(rig.w.state["broomva"], {"kind": "done", "of": other, "verb": "mail", "key": m["key"],
                                           "scope": "broomva", "tick": 6, "dry_run": True, "by": "hook",
                                           "result": {"would": True}})
    code, _ = rig.pre(rig.hook(m["send"]["to"], m["send"]["message"]))
    rec = rig.records()[-1]
    assert code == 2 and "within 6 h" in rec["detail"] and rec["of"] == m["intent"]


def test_a_name_that_no_longer_maps_to_one_live_session_is_refused(rig):
    m = rig.mail()
    rows = _rows(rig.w)
    twin = next(r for r in rows if r.get("pid") and r["sessionId"] != rig.sid)
    twin["name"] = rig.name
    (rig.w.fixture / "claude" / "agents.json").write_text(json.dumps(rows))
    code, _ = rig.pre(rig.hook(m["send"]["to"], m["send"]["message"]))
    rec = rig.records()[-1]
    assert code == 2 and "no longer maps to one live session (2 live row(s)" in rec["detail"]


def test_a_live_send_passes_and_post_closes_it_with_the_message_id(rig):
    m = rig.mail(dry=False, dry_run=0)
    code, _ = rig.pre(rig.hook(m["send"]["to"], m["send"]["message"]), dry=False, dry_run=0)
    assert code == 0 and rig.records()[-1]["kind"] == "intent"  # nothing written: the tool runs
    sec = rig.cfg(dry_run=0)
    hook = rig.hook(m["send"]["to"], m["send"]["message"], hook_event_name="PostToolUse",
                    tool_response={"success": True, "msg_id": "m-123"})
    rec = sendgate.post(sec, hook, 7, False)
    assert rec["kind"] == "done" and rec["of"] == m["intent"] and rec["result"] == {"msg_id": "m-123"}


def test_a_failed_send_is_harness_refused_and_a_send_with_no_intent_is_unledgered(rig):
    m = rig.mail(dry=False, dry_run=0)
    sec = rig.cfg(dry_run=0)
    fail = rig.hook(m["send"]["to"], m["send"]["message"], hook_event_name="PostToolUseFailure",
                    error="2 agents are named it; re-send with the ref")
    rec = sendgate.post(sec, fail, 7, False)
    assert rec["kind"] == "failed" and rec["reason"] == "harness_refused" and rec["of"] == m["intent"]
    stray = sendgate.post(sec, rig.hook("x", "hello", hook_event_name="PostToolUse"), 7, False)
    assert stray["reason"] == "unledgered_send" and stray["of"] is None


def test_post_after_a_dry_close_writes_nothing(rig):
    m = rig.mail()
    rig.pre(rig.hook(m["send"]["to"], m["send"]["message"]))
    n = len(rig.records())
    assert sendgate.post(rig.cfg(), rig.hook(m["send"]["to"], m["send"]["message"],
                                             hook_event_name="PostToolUseFailure"), 7, True) is None
    assert len(rig.records()) == n


def test_the_cli_reads_the_hook_from_stdin_and_exits_2_to_block(rig):
    m = rig.mail()
    rig.cfg()
    import os
    import subprocess
    from conftest import FLEET
    env = dict(os.environ, FLEET_TICK="7", FLEET_SCOPE="broomva", FLEET_CLAUDE_BIN="false")
    hook = json.dumps(rig.hook(m["send"]["to"], m["send"]["message"]))
    # The CLI reads the real listing through FLEET_CLAUDE_BIN; `false` fails it,
    # so the gate refuses on the listing check: it fails closed.
    out = subprocess.run(["/bin/sh", str(FLEET), "send-gate", "pre"], input=hook, capture_output=True, text=True,
                         env=env, timeout=60)
    assert out.returncode == 2 and "send gate refused" in out.stderr
    garbage = subprocess.run(["/bin/sh", str(FLEET), "send-gate", "pre"], input="not json", capture_output=True,
                             text=True, env=env, timeout=60)
    assert garbage.returncode == 2
