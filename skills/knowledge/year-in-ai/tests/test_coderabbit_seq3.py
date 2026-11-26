"""Regressions for CodeRabbit's review of 5330e2c."""

from __future__ import annotations

import json
import multiprocessing
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from test_reader_contract import iso, write_jsonl  # noqa: E402

from yia.ledger import attention as T  # noqa: E402
from yia.ledger import make_row  # noqa: E402
from yia.ledger import sources as S  # noqa: E402
from yia.ledger import store as L  # noqa: E402

T0 = 1793000000.0


def test_an_injected_prompt_keeps_its_reply_off_the_previous_turn(tmp_path):
    root = tmp_path / "bridge"
    root.mkdir()
    (root / "session-2026-10-26-abc.md").write_text(
        "---\ncreated: 2026-10-26\nsession_id: abc\n---\n\n"
        "> [!quote] **User** (10:15)\n> lets plan the recap\n\n"
        "> [!info] **Assistant**\n> Here is a plan.\n\n"
        "> [!quote] **User** (10:20)\n> <task-notification>job 7 finished</task-notification>\n\n"
        "> [!info] **Assistant**\n> Resumed after the notification.\n")
    _report, rows = S.read_bridged([root], None)
    replies = [r for r in rows if r["kind"] == "reply"]
    assert [r["words"] for r in replies] == [4]  # "Here is a plan." — not the notification's reply


def test_claude_bare_command_ends_the_turn(tmp_path):
    root = tmp_path / "claude"
    write_jsonl(root / "-p" / "s.jsonl", [
        {"type": "user", "uuid": "u1", "entrypoint": "cli", "timestamp": iso(T0), "message": {"content": "do the thing"}},
        {"type": "assistant", "uuid": "a1", "entrypoint": "cli", "timestamp": iso(T0 + 5),
         "message": {"content": [{"type": "text", "text": "Did the thing."}]}},
        {"type": "user", "uuid": "u2", "entrypoint": "cli", "timestamp": iso(T0 + 10),
         "message": {"content": "<command-name>/compact</command-name>"}},
        {"type": "assistant", "uuid": "a2", "entrypoint": "cli", "timestamp": iso(T0 + 15),
         "message": {"content": [{"type": "text", "text": "Compacted the whole conversation into a summary."}]}},
    ])
    _report, rows = S.read_claude_projects([root], None)
    assert [r["words"] for r in rows if r["kind"] == "reply"] == [3]


def test_conductor_injected_prompt_does_not_reassign_its_reply(tmp_path):
    import sqlite3
    db = tmp_path / "c.db"
    con = sqlite3.connect(db)
    con.execute("create table session_messages (id text, session_id text, role text, content text, created_at text, "
                "turn_id text)")

    def assistant(text):
        return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    for row in [("m1", "s", "user", "first ask", "2026-10-26 10:00:00", "t1"),
                ("m2", "s", "assistant", assistant("answer one"), "2026-10-26 10:00:05", "t1"),
                ("m3", "s", "user", "<system-reminder>context</system-reminder>", "2026-10-26 10:01:00", "t2"),
                ("m4", "s", "assistant", assistant("a much longer reply to the reminder"), "2026-10-26 10:01:05", "t2")]:
        con.execute("insert into session_messages values (?,?,?,?,?,?)", row)
    con.commit()
    con.close()
    _report, rows = S.read_conductor(db, None)
    assert [r["words"] for r in rows if r["kind"] == "reply"] == [2]


def test_a_change_of_attribution_alone_is_a_new_revision(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    human = make_row(src="claude_code", harness="claude-cli", kind="prompt", ts=T0, text="same words here",
                     session="s", author="human", occurrence="u1")
    agent = make_row(src="claude_code", harness="paseo", kind="prompt", ts=T0, text="same words here",
                     session="s", author="agent", occurrence="u1")
    ledger.write([human])
    assert T.fold(list(ledger.rows()))["written"]["prompts"] == 1
    ledger.write([agent])  # Paseo's session list now knows this session
    assert T.fold(list(ledger.rows()))["written"]["prompts"] == 0
    assert ledger.write([agent]) == {}  # and is unchanged after that


def _writer(path, start):
    ledger = L.Ledger(path)
    ledger.write([make_row(src="t3", harness="t3", kind="prompt", ts=T0 + start + i, text=f"p {start} {i}",
                           session="s", author="human", occurrence=f"o{start}-{i}") for i in range(200)])


def test_concurrent_writers_never_share_a_sequence(tmp_path):
    path = str(tmp_path / "ledger")
    procs = [multiprocessing.Process(target=_writer, args=(path, k * 1000)) for k in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    seqs = [r["seq"] for r in L.Ledger(path).rows()]
    assert len(seqs) == 800 and len(set(seqs)) == 800
