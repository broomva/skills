"""Every transcript a reader cannot read is reported, never counted as empty.

Round-2 verification of dad6328 found the same class at three more sites: a
corrupt or truncated archive streamed to a partial count, a permission-denied
transcript read as empty, and ``--since`` dropping an older longer copy before
comparison. The fix hoists every file read into ``sources.read_lines`` and
``sources.read_text``, which report through ``SourceReport.skip``; the
structural test below fails if a reader opens a file any other way.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from test_final_round import T0, _codex_rollout  # noqa: E402
from test_reader_contract import _claude_records, turn, write_jsonl  # noqa: E402

from yia.ledger import sources as S  # noqa: E402

needs_zstd = pytest.mark.skipif(not S.find_zstd(), reason="zstd not installed")
not_root = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any file")


def _compressed(root, n):
    path = _codex_rollout(root, [turn(i) for i in range(1, n + 1)], compress=True)
    return path.with_name(path.name + ".zst")


@needs_zstd
def test_a_corrupt_archive_is_reported(tmp_path):
    path = _compressed(tmp_path / "codex", 3)
    path.write_bytes(b"\x28\xb5\x2f\xfd" + b"garbage" * 50)
    report, rows = S.read_codex_sessions([tmp_path / "codex"], None)
    assert list(rows) == [] and report.skipped == 1 and "decompression failed" in report.reason


@needs_zstd
def test_a_truncated_archive_is_reported_not_counted_as_complete(tmp_path):
    path = _compressed(tmp_path / "codex", 400)
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    report, rows = S.read_codex_sessions([tmp_path / "codex"], None)
    assert len(list(rows)) < 400 and report.skipped == 1


@not_root
def test_an_unreadable_codex_transcript_is_reported(tmp_path):
    path = _codex_rollout(tmp_path / "codex", [turn(1)], compress=False)
    path.chmod(0)
    try:
        report, rows = S.read_codex_sessions([tmp_path / "codex"], None)
        assert list(rows) == [] and report.skipped == 1 and "unreadable" in report.reason
    finally:
        path.chmod(0o644)


@not_root
def test_an_unreadable_claude_transcript_is_reported(tmp_path):
    path = tmp_path / "projects" / "-proj" / "s1.jsonl"
    write_jsonl(path, _claude_records([turn(1)], False))
    path.chmod(0)
    try:
        report, rows = S.read_claude_projects([tmp_path / "projects"], None)
        assert list(rows) == [] and report.skipped == 1
    finally:
        path.chmod(0o644)


def test_since_compares_every_copy_of_a_recent_transcript(tmp_path):
    live, arch = tmp_path / "live", tmp_path / "arch"
    short = _codex_rollout(live, [turn(1)], compress=False)
    long = _codex_rollout(arch, [turn(i) for i in range(1, 31)], compress=False)
    os.utime(long, (T0 - 10 ** 6, T0 - 10 ** 6))  # restored metadata: older than its own content
    os.utime(short, (T0 + 10 ** 6, T0 + 10 ** 6))
    report, rows = S.read_codex_sessions([live, arch], T0 - 1000)
    assert len(list(rows)) == 30 and report.skipped == 0


def test_a_malformed_gemini_chat_is_reported(tmp_path):
    chat = tmp_path / "gemini" / "p" / "chats" / "session-1.json"
    chat.parent.mkdir(parents=True)
    chat.write_text('{"sessionId": "s1", "messages": [')
    report, rows = S.read_gemini([tmp_path / "gemini"], None)
    assert list(rows) == [] and report.skipped == 1


@needs_zstd
def test_harvest_exits_non_zero_on_a_corrupt_archive(tmp_path):
    path = _compressed(tmp_path / "codex", 3)
    path.write_bytes(b"\x28\xb5\x2f\xfd" + b"garbage" * 50)
    env = dict(os.environ, HOME=str(tmp_path / "home"))
    run = subprocess.run([sys.executable, str(SCRIPTS / "year_in_ai.py"), "harvest", "--backfill", "--no-defaults",
                          "--root", f"codex_sessions={tmp_path / 'codex'}", "--ledger", str(tmp_path / "ledger")],
                         capture_output=True, text=True, env=env)
    assert run.returncode == 4 and "incomplete" in run.stderr and "brew install" not in run.stderr


#: Functions allowed to touch the file system directly: the read and discovery
#: helpers, copy comparison, the SQLite opener, config path expansion and Paseo
#: id discovery (attribution, not a source).
READ_HELPERS = {"read_lines", "read_text", "list_files", "_content", "_ro_sqlite", "expand",
                "paseo_session_ids", "find_zstd"}
FILE_CALLS = {"open", "read_text", "read_bytes", "Popen", "run", "glob", "rglob", "iterdir", "scandir",
              "listdir", "walk", "fdopen"}


def file_access_outside_helpers(source: str):
    """Every call that reads or lists files outside the reporting helpers, as ``function:line .call()``."""
    offenders = []

    def visit(node, owner):
        for child in ast.iter_child_nodes(node):
            name = owner
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and owner is None:
                name = child.name
            if isinstance(child, ast.Call) and name not in READ_HELPERS:
                func = child.func
                called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
                calls_a_helper = isinstance(func, ast.Name) and called in READ_HELPERS
                if called in FILE_CALLS and not calls_a_helper:
                    offenders.append(f"{name}:{child.lineno} .{called}()")
            visit(child, name)

    visit(ast.parse(source), None)
    return offenders


def test_readers_read_files_only_through_the_reporting_helpers():
    assert file_access_outside_helpers((SCRIPTS / "yia" / "ledger" / "sources.py").read_text()) == []


@pytest.mark.parametrize("call", ["io.open(p)", "open(p)", "os.walk(r)", "r.glob('*')", "r.rglob('*')",
                                  "os.scandir(r)", "os.listdir(r)", "r.iterdir()", "p.read_bytes()",
                                  "subprocess.run(['zstd'])", "walk(r)", "p.read_text()"])
def test_the_guard_catches_every_file_api(call):
    assert file_access_outside_helpers(f"def read_new_store(p, r):\n    return {call}\n")


@not_root
@pytest.mark.parametrize("store", ["codex", "claude"])
def test_an_unlistable_directory_is_reported_not_read_as_empty(tmp_path, store):
    if store == "codex":
        path = _codex_rollout(tmp_path / "root", [turn(1)], compress=False)
        locked, read = path.parent, lambda: S.read_codex_sessions([tmp_path / "root"], None)
    else:
        path = tmp_path / "root" / "-proj" / "s1.jsonl"
        write_jsonl(path, _claude_records([turn(1)], False))
        locked, read = path.parent, lambda: S.read_claude_projects([tmp_path / "root"], None)
    locked.chmod(0)
    try:
        report, rows = read()
        assert list(rows) == [] and report.skipped == 1 and "listed" in report.reason
    finally:
        locked.chmod(0o755)


def test_an_unreadable_database_is_reported(tmp_path):
    db = tmp_path / "state.sqlite"
    db.write_bytes(b"not a database" * 100)
    report, rows = S.read_t3(db, None)
    assert list(rows) == [] and report.skipped == 1


def test_archive_temporary_files_are_not_transcripts(tmp_path):
    path = _codex_rollout(tmp_path / "codex", [turn(1)], compress=False)
    (path.parent / f".{path.name}.123.yia-tmp").write_text(path.read_text())
    report, rows = S.read_codex_sessions([tmp_path / "codex"], None)
    assert len(list(rows)) == 1 and report.files == 1


def test_skip_is_the_only_way_a_reader_counts_a_lost_file():
    source = (SCRIPTS / "yia" / "ledger" / "sources.py").read_text()
    assert "skipped +=" not in source and "skipped=" not in source.replace(" ", "")


@needs_zstd
def test_stopping_early_on_an_archive_is_not_a_failure(tmp_path):
    path = _compressed(tmp_path / "codex", 2000)
    report = S.SourceReport("codex", True)
    lines = S.read_lines(path, report)
    next(lines)
    lines.close()
    assert report.skipped == 0
