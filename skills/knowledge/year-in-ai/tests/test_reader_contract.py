"""The reader identity contract, run against every reader in ``sources.REGISTRY``.

Each reader gets a fixture builder that writes its store in the real on-disk
format from one turn specification. The same cases then run against all of
them:

* stable: harvesting the same store twice gives the same row ids;
* distinct: two occurrences with identical text and timestamp get two ids;
* local: pruning the oldest turn, or inserting a turn, leaves every other
  row's id unchanged;
* native copies: where a store copies a message with its own id (a resumed
  Claude Code session), the copy has the original's id;
* hostile metadata: dicts and lists where a store should hold strings do not
  stop the reader.

Adding a reader to ``REGISTRY`` without a builder here fails the suite.
"""

from __future__ import annotations

import ast
import datetime as dt
import inspect
import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from yia import ledger as LEDGER  # noqa: E402
from yia.ledger import sources as S  # noqa: E402

T0 = 1793000000.0  # 2026-10-26, a Monday
COT = dt.timezone(dt.timedelta(hours=-5))
HOSTILE = {"nested": ["not", "a", "string"]}


def turn(n, sess="s1", ts=None, prompt=None, reply=None):
    """One turn: a prompt and its reply, with native ids for stores that have them."""
    return {"sess": sess, "ts": T0 + n * 600 if ts is None else ts, "prompt": prompt or f"prompt number {n}",
            "reply": reply or f"reply number {n}", "pid": f"p{n}", "rid": f"r{n}"}


def iso(ts, zone=dt.timezone.utc):
    return dt.datetime.fromtimestamp(ts, zone).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


# ---------------------------------------------------------------- builders


def build_t3(d, turns, hostile=False):
    db = d / "statev2.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table orchestration_v2_projection_threads (thread_id text, default_provider text, "
                "payload_json text, created_at text)")
    con.execute("create table orchestration_v2_projection_messages (message_id text, thread_id text, run_id text, "
                "role text, streaming int, created_at text, payload_json text)")
    for sess in sorted({t["sess"] for t in turns}):
        lineage = HOSTILE if hostile else None
        con.execute("insert into orchestration_v2_projection_threads values (?,?,?,?)",
                    (sess, json.dumps(HOSTILE) if hostile else "claudeAgent",
                     json.dumps({"lineage": {"relationshipToParent": lineage}}), iso(T0 - 86400)))
    for t in turns:
        created_by = HOSTILE if hostile else "user"
        con.execute("insert into orchestration_v2_projection_messages values (?,?,?,?,?,?,?)",
                    (t["pid"], t["sess"], f"run-{t['pid']}", "user", 0, iso(t["ts"]),
                     json.dumps({"createdBy": created_by, "creationSource": HOSTILE if hostile else "web",
                                 "text": t["prompt"]})))
        con.execute("insert into orchestration_v2_projection_messages values (?,?,?,?,?,?,?)",
                    (t["rid"], t["sess"], f"run-{t['pid']}", "assistant", 0, iso(t["ts"] + 5),
                     json.dumps({"createdBy": "agent", "text": t["reply"]})))
    con.commit()
    con.close()
    return lambda: S.read_t3(db, None)


def build_conductor(d, turns, hostile=False):
    db = d / "conductor.db"
    con = sqlite3.connect(db)
    con.execute("create table session_messages (id text, session_id text, role text, content text, "
                "created_at text, turn_id text)")
    for t in turns:
        stamp = dt.datetime.fromtimestamp(t["ts"], dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        later = dt.datetime.fromtimestamp(t["ts"] + 5, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        message = {"type": "assistant", "message": {"content": [{"type": "text", "text": t["reply"]}]}}
        if hostile:
            message["message"]["content"].append({"type": "text", "text": HOSTILE})
        con.execute("insert into session_messages values (?,?,?,?,?,?)",
                    (t["pid"], t["sess"], "user", t["prompt"], stamp, t["pid"]))
        con.execute("insert into session_messages values (?,?,?,?,?,?)",
                    (t["rid"], t["sess"], "assistant", json.dumps(message), later, t["pid"]))
    con.commit()
    con.close()
    return lambda: S.read_conductor(db, None)


def _claude_records(turns, hostile):
    entry = HOSTILE if hostile else "cli"
    out = []
    for t in turns:
        out.append({"type": "user", "uuid": t["pid"], "entrypoint": entry, "timestamp": iso(t["ts"]),
                    "message": {"content": t["prompt"]}})
        out.append({"type": "assistant", "uuid": t["rid"], "entrypoint": entry, "timestamp": iso(t["ts"] + 5),
                    "message": {"content": [{"type": "text", "text": t["reply"]}]}})
    return out


def build_claude_code(d, turns, hostile=False):
    root = d / "projects"
    for sess in sorted({t["sess"] for t in turns}):
        write_jsonl(root / "-proj" / f"{sess}.jsonl", _claude_records([t for t in turns if t["sess"] == sess], hostile))
    root.mkdir(parents=True, exist_ok=True)
    return lambda: S.read_claude_projects([root], None)


def build_claude_history(d, turns, hostile=False):
    path = d / "history.jsonl"
    write_jsonl(path, [{"display": t["prompt"], "timestamp": int(t["ts"] * 1000),
                        "project": HOSTILE if hostile else "/p",
                        "sessionId": HOSTILE if hostile else t["sess"], "pastedContents": HOSTILE if hostile else {}}
                       for t in turns])
    return lambda: S.read_claude_history(path, None)


def _codex_sid(sess):
    return (sess + "-" * 36)[:36]


def build_codex(d, turns, hostile=False):
    root = d / "codex"
    for sess in sorted({t["sess"] for t in turns}):
        mine = [t for t in turns if t["sess"] == sess]
        records = [{"type": "session_meta", "timestamp": iso(T0 - 60),
                    "payload": {"originator": HOSTILE if hostile else "Codex Desktop", "source": "vscode"}}]
        for t in mine:
            records.append({"type": "event_msg", "timestamp": iso(t["ts"]),
                            "payload": {"type": "user_message", "message": t["prompt"]}})
            records.append({"type": "event_msg", "timestamp": iso(t["ts"] + 5),
                            "payload": {"type": "agent_message", "message": t["reply"]}})
        write_jsonl(root / "2026" / "10" / f"rollout-x-{_codex_sid(sess)}.jsonl", records)
    root.mkdir(parents=True, exist_ok=True)
    return lambda: S.read_codex_sessions([root], None)


def build_codex_history(d, turns, hostile=False):
    path = d / "codex-history.jsonl"
    write_jsonl(path, [{"session_id": HOSTILE if hostile else t["sess"], "ts": int(t["ts"]), "text": t["prompt"]}
                       for t in turns])
    return lambda: S.read_codex_history(path, None)


def build_gemini(d, turns, hostile=False):
    root = d / "gemini"
    for sess in sorted({t["sess"] for t in turns}):
        messages = []
        for t in (t for t in turns if t["sess"] == sess):
            messages.append({"id": t["pid"], "timestamp": iso(t["ts"]), "type": "user", "content": t["prompt"]})
            messages.append({"id": t["rid"], "timestamp": iso(t["ts"] + 5), "type": "gemini", "content": t["reply"]})
        path = root / "proj" / "chats" / f"{sess}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"sessionId": HOSTILE if hostile else sess, "messages": messages}))
    root.mkdir(parents=True, exist_ok=True)
    return lambda: S.read_gemini([root], None)


def build_bridged(d, turns, hostile=False):
    root = d / "bridge"
    root.mkdir(parents=True, exist_ok=True)
    for sess in sorted({t["sess"] for t in turns}):
        mine = [t for t in turns if t["sess"] == sess]
        day = dt.datetime.fromtimestamp(mine[0]["ts"], COT).strftime("%Y-%m-%d")
        lines = ["---", f"created: {day}", f"session_id: {sess}", "---", ""]
        for t in mine:
            hm = dt.datetime.fromtimestamp(t["ts"], COT).strftime("%H:%M")
            lines += [f"> [!quote] **User** ({hm})", f"> {t['prompt']}", "", "> [!info] **Assistant**",
                      f"> {t['reply']}", ""]
        (root / f"session-{day}-{sess}.md").write_text("\n".join(lines))
    return lambda: S.read_bridged([root], None)


def build_export(d, turns, hostile=False):
    path = d / "conversations.jsonl"
    records = []
    for sess in sorted({t["sess"] for t in turns}):
        mine = [t for t in turns if t["sess"] == sess]
        body = []
        for t in mine:
            body += [{"role": "user", "content": t["prompt"]}, {"role": "assistant", "content": t["reply"]}]
        records.append({"session_id": HOSTILE if hostile else sess,
                        "date": dt.datetime.fromtimestamp(mine[0]["ts"], dt.timezone.utc).strftime("%Y-%m-%d"),
                        "turns": json.dumps(body)})
    write_jsonl(path, records)
    return lambda: S.read_exports([path], None)


BUILDERS = {
    "t3": build_t3, "conductor": build_conductor, "claude_code": build_claude_code,
    "claude_history": build_claude_history, "codex": build_codex, "codex_history": build_codex_history,
    "gemini": build_gemini, "bridged": build_bridged, "export": build_export,
}
#: Stores whose own message ids survive a copy into another session.
NATIVE_COPIES = {"claude_code"}


def harvest(builder, tmp_path, turns, name="run", hostile=False):
    d = tmp_path / name
    d.mkdir()
    _report, rows = builder(d, turns, hostile)()
    return list(rows)


def prompt_ids(rows):
    return {r["ts"]: r["id"] for r in rows if r["kind"] == "prompt"}


# ----------------------------------------------------------------- the cases


def test_every_registered_reader_has_a_fixture():
    assert set(BUILDERS) == set(S.REGISTRY)


@pytest.mark.parametrize("store", sorted(BUILDERS))
def test_ids_are_stable_across_harvests(store, tmp_path):
    turns = [turn(1), turn(2), turn(3)]
    first = harvest(BUILDERS[store], tmp_path, turns, "a")
    second = harvest(BUILDERS[store], tmp_path, turns, "b")
    assert first and sorted(r["id"] for r in first) == sorted(r["id"] for r in second)


@pytest.mark.parametrize("store", sorted(BUILDERS))
def test_identical_occurrences_get_distinct_ids(store, tmp_path):
    same = dict(ts=T0 + 120, prompt="yes", reply="ok")
    turns = [turn(1, **same), turn(2, **same)]
    rows = harvest(BUILDERS[store], tmp_path, turns)
    prompts = [r for r in rows if r["kind"] == "prompt"]
    assert len(prompts) == 2
    assert len({r["id"] for r in prompts}) == 2


@pytest.mark.parametrize("store", sorted(BUILDERS))
def test_pruning_the_oldest_turn_leaves_other_ids_alone(store, tmp_path):
    full = harvest(BUILDERS[store], tmp_path, [turn(1), turn(2), turn(3)], "full")
    pruned = harvest(BUILDERS[store], tmp_path, [turn(2), turn(3)], "pruned")
    assert {r["id"] for r in pruned if r["kind"] == "prompt"} <= {r["id"] for r in full if r["kind"] == "prompt"}
    assert len([r for r in pruned if r["kind"] == "prompt"]) == 2


@pytest.mark.parametrize("store", sorted(BUILDERS))
def test_inserting_a_turn_leaves_other_ids_alone(store, tmp_path):
    before = harvest(BUILDERS[store], tmp_path, [turn(1), turn(3)], "before")
    after = harvest(BUILDERS[store], tmp_path, [turn(1), turn(2), turn(3)], "after")
    assert {r["id"] for r in before if r["kind"] == "prompt"} <= {r["id"] for r in after if r["kind"] == "prompt"}


@pytest.mark.parametrize("store", sorted(BUILDERS))
def test_hostile_metadata_does_not_stop_the_reader(store, tmp_path):
    rows = harvest(BUILDERS[store], tmp_path, [turn(1), turn(2)], hostile=True)
    assert len([r for r in rows if r["kind"] == "prompt"]) == 2  # still read, not silently skipped
    for r in rows:
        assert "nested" not in json.dumps(r)


@pytest.mark.parametrize("store", sorted(NATIVE_COPIES))
def test_a_native_copy_keeps_the_original_id(store, tmp_path):
    original = turn(1, sess="original")
    copy = dict(original, sess="resumed")  # same native ids, carried into a resumed session
    rows = harvest(BUILDERS[store], tmp_path, [original, copy, turn(2, sess="resumed")])
    ids = [r["id"] for r in rows if r["kind"] == "prompt"]
    assert len(set(ids)) == 2  # the copy collapses into its original; the new turn stays distinct


# ------------------------------------------------------- the static half


def test_one_function_makes_row_ids():
    """Only ``row_identity`` hashes a row id; no reader or fold computes one itself."""
    ledger_dir = SCRIPTS / "yia" / "ledger"
    for path in ledger_dir.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "sha1":
                owner = next((f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                              and f.lineno <= node.lineno <= f.end_lineno), None)
                assert path.name == "__init__.py" and owner in {"row_identity", "text_hash", "prefix_hash", "opaque"}, \
                    f"{path.name}:{node.lineno} hashes outside the identity functions"


def test_every_row_a_reader_makes_names_its_occurrence():
    assert inspect.signature(LEDGER.make_row).parameters["occurrence"].default is inspect.Parameter.empty
    tree = ast.parse((SCRIPTS / "yia" / "ledger" / "sources.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "make_row"]
    assert calls
    for call in calls:
        assert "occurrence" in {k.arg for k in call.keywords}, f"make_row at line {call.lineno} has no occurrence"
