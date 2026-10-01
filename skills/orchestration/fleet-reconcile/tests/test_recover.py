"""fleet recover (spec §5.7): every open intent is closed from what happened."""
from __future__ import annotations

import json
import time

from fleetlib import common, config, ledger, recover
from fleetlib.sources import FixtureSources

BASE = {"scope": "broomva", "tick": 4, "dry_run": False, "by": "act"}


def _intent(w, verb, target, key="k"):
    return ledger.append(w.state["broomva"], dict(BASE, kind="intent", verb=verb, key=key, target=target))


def _run(w):
    w.write_config(mode="act", dry_run=0)
    return recover.recover(config.scope("broomva"), FixtureSources(w.fixture), 5)


def _transcript(w, sid, lines):
    d = w.fixture / "claude" / "transcript-files"
    d.mkdir(parents=True, exist_ok=True)
    (d / (sid + ".jsonl")).write_text("\n".join(json.dumps(x) for x in lines) + "\n")


SID = "%08d-0000-4000-8000-%012d" % (77, 77)


def test_mail_is_done_when_its_text_reached_the_transcript_after_the_intent_in_either_shape(world):
    a = _intent(world, "mail", {"session_id": SID, "text": "fleet: hello \"there\"\nline two"})
    b = _intent(world, "mail", {"session_id": SID, "text": "queued one"})
    c = _intent(world, "mail", {"session_id": SID, "text": "never arrived"})
    later = common.ts(time.time() + 5)
    _transcript(world, SID, [
        {"type": "user", "timestamp": later, "message": {"content": "fleet: hello \"there\"\nline two"}},
        {"type": "queue-operation", "operation": "enqueue", "timestamp": later, "content": "queued one"},
        {"type": "user", "timestamp": common.ts(time.time() - 3600), "message": {"content": "never arrived"}},
    ])
    out = {r["of"]: r for r in _run(world)}
    assert out[a["id"]]["kind"] == "done" and out[b["id"]]["kind"] == "done"
    assert out[c["id"]]["kind"] == "failed" and out[c["id"]]["reason"] == "lost"  # only before the intent
    assert all(r["by"] == "recover" for r in out.values())
    assert _run(world) == []  # nothing left open


def test_mail_to_a_transcript_that_is_missing_is_unknown(world):
    it = _intent(world, "mail", {"session_id": SID, "text": "x"})
    (rec,) = _run(world)
    assert rec["of"] == it["id"] and rec["kind"] == "unknown"


def _rows(w, extra):
    rows = json.loads((w.fixture / "claude" / "agents.json").read_text())
    (w.fixture / "claude" / "agents.json").write_text(json.dumps(rows + extra))


def _row(n, name, started, pid=None, kind="background"):
    r = {"sessionId": "%08d-0000-4000-8000-%012d" % (n, n), "kind": kind, "cwd": "/tmp", "name": name,
         "startedAt": int(started * 1000), "id": "%08d" % n, "state": "running"}
    if pid:
        r.update(pid=pid, status="busy")
    return r


def test_spawn_is_done_with_the_one_row_named_after_it_failed_with_none_and_flagged_with_two(world):
    one = _intent(world, "spawn", {"name": "broomva-x-pr1"})
    none = _intent(world, "spawn", {"name": "broomva-x-pr2"})
    two = _intent(world, "spawn", {"name": "broomva-x-pr3"})
    t = time.time() + 5
    _rows(world, [_row(901, "broomva-x-pr1", t), _row(902, "broomva-x-pr3", t), _row(903, "broomva-x-pr3", t),
                  _row(904, "broomva-x-pr2", t - 7200)])  # one named so, but started before the intent
    out = {r["of"]: r for r in _run(world)}
    assert out[one["id"]]["kind"] == "done" and out[one["id"]]["result"]["session_id"].startswith("00000901")
    assert out[none["id"]]["kind"] == "failed"
    assert out[two["id"]]["result"]["duplicate"] is True and len(out[two["id"]]["result"]["session_ids"]) == 2


def test_resume_is_done_only_when_the_process_started_after_the_intent(world):
    new = _intent(world, "resume", {"session_id": "%08d-0000-4000-8000-%012d" % (905, 905)})
    old = _intent(world, "resume", {"session_id": "%08d-0000-4000-8000-%012d" % (906, 906)})
    _rows(world, [_row(905, "a", 0, pid=5050), _row(906, "b", 0, pid=6060)])
    (world.fixture / "claude" / "pids.json").write_text(json.dumps({"5050": time.time() + 5, "6060": 1.0}))
    out = {r["of"]: r for r in _run(world)}
    assert out[new["id"]]["kind"] == "done" and out[new["id"]]["result"] == {"pid": 5050}
    assert out[old["id"]]["kind"] == "failed"


def test_label_reads_the_prs_labels(world):
    add = _intent(world, "label", {"repo": "broomva/workspace", "pr": 849, "label": "ci-heal-escalation", "op": "add"})
    rm = _intent(world, "label", {"repo": "broomva/workspace", "pr": 849, "label": "hold", "op": "remove"})
    (world.fixture / "gh" / "broomva__workspace" / "pr-849-labels.json").write_text('["ci-heal-escalation", "hold"]')
    out = {r["of"]: r for r in _run(world)}
    assert out[add["id"]]["kind"] == "done" and out[rm["id"]]["kind"] == "failed"


def test_closed_intents_and_asks_are_left_alone(world):
    it = _intent(world, "label", {"repo": "broomva/workspace", "pr": 1, "label": "x", "op": "add"})
    ledger.append(world.state["broomva"], dict(BASE, kind="done", of=it["id"], verb="label", key="k", result={}))
    ledger.append(world.state["broomva"], dict(BASE, kind="intent", verb="ask", key="scope:broomva",
                                               target={"batch": "x", "asks": []}))
    assert _run(world) == []
