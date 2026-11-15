"""Regressions for sequence 3, round 2 (findings at ad83983)."""

from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from test_reader_contract import _codex_sid, iso, turn, write_jsonl  # noqa: E402

from yia.ledger import archive as A  # noqa: E402
from yia.ledger import attention as T  # noqa: E402
from yia.ledger import exclusive_lock, make_row  # noqa: E402
from yia.ledger import sources as S  # noqa: E402
from yia.ledger import store as L  # noqa: E402

T0 = 1793000000.0


def _codex_lines(turns, meta_ts=T0 - 60):
    out = [{"type": "session_meta", "timestamp": iso(meta_ts), "payload": {"originator": "Codex Desktop",
                                                                         "source": "vscode"}}]
    for t in turns:
        out.append({"type": "event_msg", "timestamp": iso(t["ts"]), "payload": {"type": "user_message",
                                                                                "message": t["prompt"]}})
        out.append({"type": "event_msg", "timestamp": iso(t["ts"] + 5), "payload": {"type": "agent_message",
                                                                                    "message": t["reply"]}})
    return out


@pytest.mark.skipif(not shutil.which("zstd"), reason="zstd not installed")
def test_a_compressed_archive_that_extends_the_live_copy_wins(tmp_path):
    live, archive = tmp_path / "live", tmp_path / "zz-archive"
    name = f"rollout-x-{_codex_sid('s1')}.jsonl"
    write_jsonl(live / "2026" / "10" / name, _codex_lines([turn(1)]))
    write_jsonl(archive / "2026" / "10" / name, _codex_lines([turn(i) for i in range(1, 21)]))
    subprocess.run(["zstd", "-q", "--rm", "-19", str(archive / "2026" / "10" / name)], check=True)
    os.utime(live / "2026" / "10" / name, None)  # the live copy is the newest write
    _report, rows = S.read_codex_sessions([live, archive], None)
    assert len([r for r in rows if r["kind"] == "prompt"]) == 20


def test_an_injected_message_ends_a_t3_runs_turn(tmp_path):
    db = tmp_path / "t3.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table orchestration_v2_projection_threads (thread_id text, default_provider text, "
                "payload_json text, created_at text)")
    con.execute("create table orchestration_v2_projection_messages (message_id text, thread_id text, run_id text, "
                "role text, streaming int, created_at text, payload_json text)")
    con.execute("insert into orchestration_v2_projection_threads values ('t','claudeAgent','{}',?)", (iso(T0 - 99),))
    for mid, role, ts, by, text in [("m1", "user", T0, "user", "do it"),
                                    ("m2", "assistant", T0 + 5, "agent", "done it"),
                                    ("m3", "user", T0 + 10, "user", "<task-notification>job finished</task-notification>"),
                                    ("m4", "assistant", T0 + 15, "agent", "noted the job result here")]:
        con.execute("insert into orchestration_v2_projection_messages values (?,?,?,?,?,?,?)",
                    (mid, "t", "r", role, 0, iso(ts), json.dumps({"createdBy": by, "text": text})))
    con.commit()
    con.close()
    _report, rows = S.read_t3(db, None)
    assert [(r["kind"], r["words"]) for r in rows] == [("prompt", 2), ("reply", 2)]


def test_codex_injected_prompt_is_a_boundary(tmp_path):
    root = tmp_path / "codex"
    write_jsonl(root / "2026" / "10" / f"rollout-x-{_codex_sid('s1')}.jsonl", _codex_lines([
        turn(1, prompt="real prompt", reply="real reply"),
        turn(2, prompt="<system-reminder>context</system-reminder>", reply="reply to the reminder only")]))
    _report, rows = S.read_codex_sessions([root], None)
    assert [(r["kind"], r["words"]) for r in rows] == [("prompt", 2), ("reply", 2)]


def test_gemini_injected_prompt_is_a_boundary(tmp_path):
    path = tmp_path / "gemini" / "p" / "chats" / "s.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"sessionId": "s", "messages": [
        {"id": "1", "timestamp": iso(T0), "type": "user", "content": "real prompt"},
        {"id": "2", "timestamp": iso(T0 + 5), "type": "gemini", "content": "real reply"},
        {"id": "3", "timestamp": iso(T0 + 10), "type": "user", "content": "<system-reminder>x</system-reminder>"},
        {"id": "4", "timestamp": iso(T0 + 15), "type": "gemini", "content": "reply to the reminder only"}]}))
    _report, rows = S.read_gemini([tmp_path / "gemini"], None)
    assert [(r["kind"], r["words"]) for r in rows] == [("prompt", 2), ("reply", 2)]


def test_a_row_missing_required_fields_is_skipped_and_counted(tmp_path):
    ledger = L.Ledger(str(tmp_path / "ledger"))
    good = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="valid row", session="s", author="human",
                    occurrence="m")
    ledger.write([good])
    broken = {k: v for k, v in good.items() if k != "chars"}
    broken.update(id="x" * 20, o="y" * 16)
    with ledger._month_file(T0).open("a") as handle:
        handle.write(json.dumps(broken) + "\n")
    rows = list(ledger.rows())
    assert [r["id"] for r in rows] == [good["id"]] and ledger.malformed_lines == 1
    T.fold(rows)  # does not raise


def _archive_in_child(root, source, started, done):
    started.set()  # measured from here, not from process start-up
    A.archive(Path(root), None, targets=[(source, "fixture")])
    done.set()


def test_an_archive_run_waits_for_the_root_lock(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    source = tmp_path / "source"
    (source / "p").mkdir(parents=True)
    (source / "p" / "a.jsonl").write_text("x\n")
    started, done = multiprocessing.Event(), multiprocessing.Event()
    with exclusive_lock(root, ".year-in-ai-archive.lock"):
        child = multiprocessing.Process(target=_archive_in_child,
                                        args=(str(root), str(source), started, done))
        child.start()
        assert started.wait(30)
        assert not done.wait(1.0)  # blocked while another run holds the lock
    child.join(30)
    assert done.is_set() and (root / "fixture" / "p" / "a.jsonl").read_text() == "x\n"


def test_an_empty_target_list_archives_nothing(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    assert A.archive(root, None, targets=[]) == {}


def test_temporary_copies_are_unique_per_process(tmp_path, monkeypatch):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "p").mkdir(parents=True)
    (src / "p" / "a.jsonl").write_text("x\n")
    seen = []
    real = A.shutil.copy2

    def spy(s, d, *args, **kw):
        seen.append(Path(d).name)
        return real(s, d, *args, **kw)

    monkeypatch.setattr(A.shutil, "copy2", spy)
    A.copy_additive(src, dst)
    assert seen and str(os.getpid()) in seen[0]


def test_make_row_rejects_unknown_kinds_and_authors():
    with pytest.raises(ValueError):
        make_row(src="t3", harness="t3", kind="tool", ts=T0, text="x", session="s", occurrence="o")
    with pytest.raises(ValueError):
        make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="x", session="s", author="robot", occurrence="o")
    with pytest.raises(ValueError):
        make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="x", session="s", occurrence="")
