"""The second STRUCTURAL directive: archive revisions are never ledger input.

Continuation review #2 (on fa24ca4) cut the input: `.rev-<n>` files the
archive keeps beside a diverged transcript are preserved for quoting and are
never read by the harvest. The executable check it named: a store holding
``x.jsonl`` and ``x.rev-1.jsonl`` harvests exactly like one holding only
``x.jsonl``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from test_reader_contract import _claude_records, _codex_sid, iso, turn, write_jsonl  # noqa: E402

from yia.ledger import archive as A  # noqa: E402
from yia.ledger import attention as T  # noqa: E402
from yia.ledger import make_row  # noqa: E402
from yia.ledger import sources as S  # noqa: E402
from yia.ledger import store as L  # noqa: E402

T0 = 1793000000.0


def _codex_records(turns):
    out = [{"type": "session_meta", "timestamp": iso(T0 - 60), "payload": {"originator": "Codex Desktop",
                                                                         "source": "vscode"}}]
    for t in turns:
        out.append({"type": "event_msg", "timestamp": iso(t["ts"]),
                    "payload": {"type": "user_message", "message": t["prompt"]}})
        out.append({"type": "event_msg", "timestamp": iso(t["ts"] + 5),
                    "payload": {"type": "agent_message", "message": t["reply"]}})
    return out


def _harvest(tmp_path, name, store, with_revision):
    d = tmp_path / name
    base_turns = [turn(1, sess="s1"), turn(2, sess="s1")]
    diverged = [turn(1, sess="s1", prompt="a diverged rewrite of the first prompt"), turn(3, sess="s1")]
    if store == "claude_code":
        write_jsonl(d / "-p" / "s1.jsonl", _claude_records(base_turns, False))
        if with_revision:
            write_jsonl(d / "-p" / "s1.rev-1.jsonl", _claude_records(diverged, False))
            write_jsonl(d / "-p" / "s1.rev-10.jsonl", _claude_records([turn(4, sess="s1")], False))
        report, rows = S.read_claude_projects([d], None)
    else:
        rollout = f"rollout-x-{_codex_sid('s1')}"
        write_jsonl(d / "2026" / "10" / f"{rollout}.jsonl", _codex_records(base_turns))
        if with_revision:
            write_jsonl(d / "2026" / "10" / f"{rollout}.rev-1.jsonl", _codex_records(diverged))
        report, rows = S.read_codex_sessions([d], None)
    ledger = L.Ledger(str(tmp_path / f"{name}-ledger"))
    for _ in range(3):  # weekly harvests over an unchanged store
        ledger.write(list(S.read_claude_projects([d], None)[1] if store == "claude_code"
                          else S.read_codex_sessions([d], None)[1]))
    stored = list(ledger.rows())
    return sorted(r["id"] for r in stored), T.fold(stored)


@pytest.mark.parametrize("store", ["claude_code", "codex"])
def test_an_archive_revision_harvests_exactly_like_its_absence(store, tmp_path):
    with_rev = _harvest(tmp_path, "with", store, True)
    without = _harvest(tmp_path, "without", store, False)
    assert with_rev[0] == without[0]
    assert with_rev[1]["written"] == without[1]["written"] and with_rev[1]["read"] == without[1]["read"]


def test_equal_size_prefers_the_live_root(tmp_path):
    live, archive = tmp_path / "live", tmp_path / "zz-archive"  # the archive path sorts later
    write_jsonl(live / "-p" / "s.jsonl", _claude_records([turn(1, prompt="live text")], False))
    write_jsonl(archive / "-p" / "s.jsonl", _claude_records([turn(1, prompt="arch text")], False))
    stamp = (live / "-p" / "s.jsonl").stat().st_mtime_ns
    for p in (live / "-p" / "s.jsonl", archive / "-p" / "s.jsonl"):
        os.utime(p, ns=(stamp, stamp))
    _report, rows = S.read_claude_projects([live, archive], None)
    prompt = next(r for r in rows if r["kind"] == "prompt")
    expected = make_row(src="claude_code", harness="claude-cli", kind="prompt", ts=T0, text="live text",
                        session="s", author="human", occurrence="x")
    assert prompt["h"] == expected["h"]


def test_versions_handle_glob_metacharacters(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    f = src / "p" / "foo[a].jsonl"
    f.write_text("a\n")
    A.copy_additive(src, dst)
    f.write_text("x\n")
    A.copy_additive(src, dst)
    for line in ("y\n", "z\n"):
        with f.open("a") as handle:
            handle.write(line)
        A.copy_additive(src, dst)
    assert sorted(p.name for p in (dst / "p").iterdir()) == ["foo[a].jsonl", "foo[a].rev-1.jsonl"]


def test_a_row_missing_its_identity_fields_is_skipped_not_fatal(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    ledger.dir.mkdir(parents=True)
    row = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="valid", session="s", author="human",
                   occurrence="m")
    ledger._month_file(T0).write_text(json.dumps({"v": row["v"], "id": "abc"}) + "\n")
    assert ledger.write([row]) == {ledger._month_file(T0).stem: 1}
    assert [r["id"] for r in ledger.rows()] == [row["id"]] and ledger.malformed_lines == 1


def test_returning_to_old_text_twice_mints_distinct_revisions(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    for text in ("alpha", "beta two", "alpha", "beta two", "alpha"):
        ledger.write([make_row(src="t3", harness="t3", kind="prompt", ts=T0, text=text, session="s",
                               author="human", occurrence="m")])
    rows = list(ledger.rows())
    assert len(rows) == 5 and len({r["id"] for r in rows}) == 5
    assert T.fold(rows)["written"]["words"] == 1


def test_rows_without_a_sequence_never_outrank_sequenced_ones_and_ties_ignore_month_order(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    ledger.dir.mkdir(parents=True)
    # Two unsequenced revisions of one message, the higher id in the EARLIER month,
    # so a tie broken by month-file order would pick the other one.
    early_ts, late_ts = T0 - 40 * 86400, T0
    for i in range(200):
        a = make_row(src="t3", harness="t3", kind="prompt", ts=early_ts, text=f"early text {i}", session="s",
                     author="human", occurrence="m")
        b = make_row(src="t3", harness="t3", kind="prompt", ts=late_ts, text=f"late text {i} more", session="s",
                     author="human", occurrence="m")
        if a["id"] > b["id"]:
            break
    winner = a
    ledger._month_file(a["ts"]).write_text(json.dumps(a) + "\n")
    ledger._month_file(b["ts"]).write_text(json.dumps(b) + "\n")
    _ids, latest, top = ledger._scan()
    assert latest[a["o"]][1] == L.fingerprint(winner) and top == 0  # the next harvest writes seq 1
    # A later harvest writes the other text; a sequenced row outranks both unsequenced ones.
    loser = a if winner is b else b
    ledger.write([dict(loser, seq=None)])
    assert T.fold(list(ledger.rows()))["written"]["words"] == loser["words"]


@pytest.mark.parametrize("length,counted", [(1400, 1), (1600, 0)])
def test_text_only_prompts_over_1500_characters_are_not_counted(length, counted):
    r = make_row(src="bridged", harness="bridged", kind="prompt", ts=T0, text="w" * length, session="b",
                 author="unknown", occurrence="b1")
    assert T.fold([r])["written"]["prompts"] == counted


def test_codex_prefers_the_longer_archived_copy_over_a_truncated_live_one(tmp_path):
    live, archive = tmp_path / "live", tmp_path / "zz-archive"
    rollout = f"rollout-x-{_codex_sid('s1')}.jsonl"
    write_jsonl(live / "2026" / "10" / rollout, _codex_records([turn(1, sess="s1")]))
    write_jsonl(archive / "2026" / "10" / rollout, _codex_records([turn(1, sess="s1"), turn(2, sess="s1")]))
    _report, rows = S.read_codex_sessions([live, archive], None)
    assert len([r for r in rows if r["kind"] == "prompt"]) == 2


def test_codex_equal_size_copies_prefer_the_live_root(tmp_path):
    live, archive = tmp_path / "live", tmp_path / "zz-archive"
    rollout = f"rollout-x-{_codex_sid('s1')}.jsonl"
    write_jsonl(live / "2026" / "10" / rollout, _codex_records([turn(1, sess="s1", prompt="live prompt")]))
    write_jsonl(archive / "2026" / "10" / rollout, _codex_records([turn(1, sess="s1", prompt="arch prompt")]))
    stamp = (live / "2026" / "10" / rollout).stat().st_mtime_ns
    for p in (live / "2026" / "10" / rollout, archive / "2026" / "10" / rollout):
        os.utime(p, ns=(stamp, stamp))
    _report, rows = S.read_codex_sessions([live, archive], None)
    prompt = next(r for r in rows if r["kind"] == "prompt")
    assert prompt["h"] == make_row(src="codex", harness="codex", kind="prompt", ts=T0, text="live prompt",
                                   session="s", author="human", occurrence="x")["h"]


@pytest.mark.parametrize("created_by,author", [("user", "human"), ("agent", "agent"), (None, "unknown"),
                                               ({"a": 1}, "unknown"), ("system", "unknown")])
def test_t3_maps_only_explicit_authors(created_by, author, tmp_path):
    import sqlite3
    db = tmp_path / "t3.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table orchestration_v2_projection_threads (thread_id text, default_provider text, "
                "payload_json text, created_at text)")
    con.execute("create table orchestration_v2_projection_messages (message_id text, thread_id text, run_id text, "
                "role text, streaming int, created_at text, payload_json text)")
    con.execute("insert into orchestration_v2_projection_threads values ('t','claudeAgent','{}',?)", (iso(T0 - 99),))
    con.execute("insert into orchestration_v2_projection_messages values ('m','t','r','user',0,?,?)",
                (iso(T0), json.dumps({"createdBy": created_by, "text": "hello"})))
    con.execute("insert into orchestration_v2_projection_messages values ('a','t','r','assistant',0,?,?)",
                (iso(T0 + 5), json.dumps({"createdBy": "agent", "text": "hi there"})))
    con.commit()
    con.close()
    _report, rows = S.read_t3(db, None)
    rows = list(rows)
    assert {r["author"] for r in rows if r["kind"] == "prompt"} == {author}
    summary = T.fold(rows)
    if author == "unknown":  # neither the person's writing nor the agents' own
        assert summary["written"]["prompts"] == 0 and summary["agents_own"]["replies"] == 0


def test_unsequenced_revisions_fold_the_same_in_any_order():
    a = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="one", session="s", author="human",
                 occurrence="m")
    b = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="two words", session="s", author="human",
                 occurrence="m")
    assert T.fold([a, b])["written"] == T.fold([b, a])["written"]
