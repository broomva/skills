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
import json
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
READ_HELPERS = {"read_lines", "read_text", "list_files", "_content", "_ro_sqlite", "expand", "present",
                "_inaccessible", "paseo_session_ids", "find_zstd"}
FILE_CALLS = {"open", "read_text", "read_bytes", "Popen", "run", "glob", "rglob", "iterdir", "scandir",
              "listdir", "walk", "fdopen", "is_dir", "is_file", "exists"}


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
                                  "subprocess.run(['zstd'])", "walk(r)", "p.read_text()", "r.is_dir()",
                                  "p.is_file()", "os.path.exists(p)"])
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


# --- CodeRabbit at 861d22c


@pytest.mark.parametrize("store", ["claude_history", "codex_history"])
def test_an_absurd_history_timestamp_is_dropped_not_fatal(tmp_path, store):
    import json
    path = tmp_path / "history.jsonl"
    if store == "claude_history":
        bad, good = {"timestamp": 1e23, "display": "corrupt"}, {"timestamp": T0 * 1000, "display": "typed"}
        read = S.read_claude_history
    else:
        bad, good = {"ts": 1e20, "text": "corrupt"}, {"ts": T0, "text": "typed"}
        read = S.read_codex_history
    path.write_text(json.dumps(bad) + "\n" + json.dumps(good) + "\n")
    _report, rows = read(path, None)
    assert len(list(rows)) == 1


def test_the_ledger_never_appends_a_row_it_would_not_read(tmp_path):
    from yia.ledger import make_row
    from yia.ledger import store as L
    ledger = L.Ledger(str(tmp_path / "ledger"))
    good = make_row(src="t3", harness="t3", kind="prompt", ts=T0, text="ok", session="s", author="human",
                    occurrence="g")
    bad = dict(good, id="b" * 20, o="c" * 16, ts=4102444800.0)
    ledger.write([good, bad])
    ledger.write([bad])
    lines = [line for f in (tmp_path / "ledger").rglob("*.jsonl") for line in f.read_text().splitlines()]
    assert len(lines) == 1


# --- BRO-3766: last check of #290 at 861d22c


def _harvest(tmp_path, *args):
    env = dict(os.environ, HOME=str(tmp_path / "home"))
    return subprocess.run([sys.executable, str(SCRIPTS / "year_in_ai.py"), "harvest", "--backfill", "--no-defaults",
                           "--ledger", str(tmp_path / "ledger"), *args], capture_output=True, text=True, env=env)


def _store(tmp_path, store):
    """One transcript of ``store`` under ``tmp_path/gate/root``; returns the root and its --root key."""
    root = tmp_path / "gate" / "root"
    if store == "codex_sessions":
        _codex_rollout(root, [turn(1)], compress=False)
    elif store == "claude_projects":
        write_jsonl(root / "-proj" / "s1.jsonl", _claude_records([turn(1)], False))
    elif store == "gemini_tmp":
        chat = root / "p" / "chats" / "session-1.json"
        chat.parent.mkdir(parents=True)
        chat.write_text('{"sessionId": "s1", "messages": [{"type": "user", "content": "hello there", '
                        '"timestamp": "2026-10-26T12:00:00Z"}]}')
    else:
        root.mkdir(parents=True)
        (root / "session-2026-10-26-abc.md").write_text("---\ncreated: 2026-10-26\nsession_id: abc\n---\n")
    return root


@not_root
@pytest.mark.parametrize("store", ["codex_sessions", "claude_projects", "gemini_tmp", "bridged"])
def test_a_root_behind_a_locked_directory_is_reported_not_absent(tmp_path, store):
    root = _store(tmp_path, store)
    (tmp_path / "gate").chmod(0)
    try:
        run = _harvest(tmp_path, "--root", f"{store}={root}")
    finally:
        (tmp_path / "gate").chmod(0o755)
    assert run.returncode == 4, (run.stdout, run.stderr)
    assert "not accessible" in run.stderr


@not_root
def test_a_database_behind_a_locked_directory_is_reported(tmp_path):
    db = tmp_path / "gate" / "state.sqlite"
    db.parent.mkdir()
    db.write_bytes(b"")
    (tmp_path / "gate").chmod(0)
    try:
        report, rows = S.read_t3(db, None)
        assert list(rows) == [] and report.skipped == 1
    finally:
        (tmp_path / "gate").chmod(0o755)


def test_a_missing_optional_store_is_still_a_clean_run(tmp_path):
    run = _harvest(tmp_path, "--root", f"codex_sessions={tmp_path / 'nowhere'}")
    assert run.returncode == 0, run.stderr


@not_root
@pytest.mark.parametrize("case", ["unreadable", "invalid", "not an object", "missing"])
def test_a_config_that_cannot_be_used_is_an_error_not_an_empty_config(tmp_path, case):
    cfg = tmp_path / "config.json"
    root = _store(tmp_path, "codex_sessions")
    if case != "missing":
        cfg.write_text({"unreadable": json.dumps({"roots": {"codex_sessions": [str(root)]}}),
                        "invalid": "{not json", "not an object": "[1, 2]"}[case])
    if case == "unreadable":
        cfg.chmod(0)
    try:
        run = _harvest(tmp_path, "--config", str(cfg))
    finally:
        if cfg.exists():
            cfg.chmod(0o644)
    assert run.returncode == 2 and "config" in run.stderr


def test_an_absent_default_config_is_empty(tmp_path, monkeypatch):
    from yia.ledger import store as L
    monkeypatch.setattr(L, "DEFAULT_CONFIG", str(tmp_path / "no-config.json"))
    assert L.load_config(None) == {}


def test_symlinked_directories_are_followed_once(tmp_path):
    real = tmp_path / "elsewhere"
    path = _codex_rollout(real, [turn(1)], compress=False)
    root = tmp_path / "codex"
    root.mkdir()
    (root / "linked").symlink_to(real, target_is_directory=True)
    (real / "loop").symlink_to(real, target_is_directory=True)  # a cycle must end
    report, rows = S.read_codex_sessions([root], None)
    assert len(list(rows)) == 1 and report.skipped == 0 and path.exists()


# --- BRO-3767: a stalled zstd must end in a skip, never a hang


@pytest.fixture
def stalling_zstd(tmp_path, monkeypatch):
    fake = tmp_path / "bin" / "zstd"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\nexec sleep 60\n")
    fake.chmod(0o755)
    monkeypatch.setattr(S, "find_zstd", lambda: str(fake))
    monkeypatch.setattr(S, "ZSTD_STALL_SECONDS", 2.0)
    monkeypatch.setattr(S, "_zstd_stalled", False)
    return fake


def test_a_stalled_zstd_is_a_skip_not_a_hang(tmp_path, stalling_zstd):
    import time
    root = tmp_path / "codex"
    for day in ("01", "02", "03"):
        path = root / "2026" / "10" / day / f"rollout-{day}.jsonl.zst"  # three transcripts, one copy each
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\x28\xb5\x2f\xfd")
    started = time.monotonic()
    report, rows = S.read_codex_sessions([root], None)
    assert list(rows) == []
    # One stall, then the rest are skipped at once: under 3 x the 2 s limit.
    assert time.monotonic() - started < 5
    assert report.skipped == 3 and "stalled" in report.reason


def test_a_slow_consumer_is_not_a_stall(tmp_path, monkeypatch):
    import time
    if not S.find_zstd():
        pytest.skip("zstd not installed")
    monkeypatch.setattr(S, "ZSTD_STALL_SECONDS", 0.5)
    monkeypatch.setattr(S, "_zstd_stalled", False)
    path = _compressed(tmp_path / "codex", 3)
    report = S.SourceReport("codex", True)
    lines = []
    for line in S.read_lines(path, report):
        lines.append(line)
        time.sleep(0.8)  # longer than the limit, spent by the caller, not zstd
    assert len(lines) >= 4 and report.skipped == 0


def test_a_stalled_zstd_in_copy_comparison_is_bounded(tmp_path, stalling_zstd):
    path = tmp_path / "x.jsonl.zst"
    path.write_bytes(b"\x28\xb5\x2f\xfd")
    assert S._content(path) is None and S._zstd_stalled


def test_stopping_early_never_waits_forever_on_zstd(tmp_path, monkeypatch):
    import time
    fake = tmp_path / "bin" / "zstd"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\ntrap '' PIPE\necho line\nexec sleep 60\n")
    fake.chmod(0o755)
    monkeypatch.setattr(S, "find_zstd", lambda: str(fake))
    monkeypatch.setattr(S, "ZSTD_STALL_SECONDS", 1.0)
    monkeypatch.setattr(S, "_zstd_stalled", False)
    path = tmp_path / "x.jsonl.zst"
    path.write_bytes(b"\x28\xb5\x2f\xfd")
    report = S.SourceReport("codex", True)
    lines = S.read_lines(path, report)
    assert next(lines).strip() == "line"
    started = time.monotonic()
    lines.close()
    assert time.monotonic() - started < 5 and report.skipped == 1
