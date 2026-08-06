from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "audit_harness_usage.py"
PARITY_SCRIPT = SKILL / "scripts" / "verify_codexbar_parity.py"


def dump(path: Path, value, jsonl: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value)
    path.write_text(text + ("\n" if jsonl else ""), encoding="utf-8")


def test_combined_cli_report_spans_all_adapters(tmp_path):
    timestamp = "2099-08-05T12:00:00Z"
    codex = tmp_path / "codex.jsonl"
    dump(codex, {"type": "turn_context", "payload": {"model": "gpt-5"}}, jsonl=True)
    with codex.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": timestamp, "type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 10, "output_tokens": 2}}}}) + "\n")

    claude = tmp_path / "claude.jsonl"
    dump(claude, {"timestamp": timestamp, "type": "assistant", "requestId": "r", "message": {"id": "m", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 10, "output_tokens": 2}}}, jsonl=True)

    gemini = tmp_path / "session-1.json"
    dump(gemini, {"sessionId": "g", "messages": [{"timestamp": timestamp, "type": "gemini", "model": "gemini-2.5-flash", "tokens": {"input": 10, "output": 2, "total": 12}}]})

    cursor = tmp_path / "cursor.json"
    dump(cursor, {"usageEvents": [{"id": "c", "timestamp": 4079140800000, "model": "m", "chargedCents": 1, "tokenUsage": {"inputTokens": 10, "outputTokens": 2, "cacheReadTokens": 0, "cacheWriteTokens": 0, "totalCents": 2}}]})

    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--days", "36500", "--format", "json",
        "--path", f"codex={codex}", "--path", f"claude={claude}",
        "--path", f"gemini={gemini}", "--path", f"cursor={cursor}",
    ], check=True, capture_output=True, text=True)
    report = json.loads(proc.stdout)
    assert {row["provider"] for row in report["by_model"]} == {"codex", "claude", "gemini", "cursor"}
    assert report["overall"]["total_tokens"] == 48
    assert report["overall"]["charged_cost_usd"] == .01


def test_cli_uses_native_lineage_without_codexbar_dependency(tmp_path):
    codex = tmp_path / "codex.jsonl"
    dump(codex, {"type": "session_meta", "payload": {"id": "s"}}, jsonl=True)
    with codex.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "turn_context", "timestamp": "2099-08-05T12:00:00Z", "payload": {"model": "gpt-5"}}) + "\n")
        handle.write(json.dumps({"type": "event_msg", "timestamp": "2099-08-05T12:00:01Z", "payload": {
            "type": "token_count", "info": {"last_token_usage": {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 10}},
        }}) + "\n")
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--provider", "codex", "--days", "36500", "--format", "json",
        "--path", f"codex={codex}",
    ], check=True, capture_output=True, text=True, env={"PATH": ""})
    report = json.loads(proc.stdout)
    assert report["overall"]["total_tokens"] == 110
    assert report["overall"]["events"] == 1
    assert report["diagnostics"]["backends"]["codex"] == "native-lineage"
    assert report["pricing"]["codex_backend"] == "native-lineage"


def test_optional_codexbar_parity_oracle_emits_machine_receipt(tmp_path):
    codex = tmp_path / "session.jsonl"
    dump(codex, {"type": "session_meta", "payload": {"id": "s"}}, jsonl=True)
    with codex.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "turn_context", "timestamp": "2099-08-05T12:00:00Z", "payload": {"model": "gpt-5"}}) + "\n")
        handle.write(json.dumps({"type": "event_msg", "timestamp": "2099-08-05T12:00:01Z", "payload": {
            "type": "token_count", "info": {"last_token_usage": {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 10}},
        }}) + "\n")
    native = subprocess.run([
        sys.executable, str(SCRIPT), "--provider", "codex", "--days", "36500", "--format", "json",
        "--path", f"codex={tmp_path}",
    ], check=True, capture_output=True, text=True)
    expected_cost = json.loads(native.stdout)["overall"]["estimated_cost_usd"]

    fake_codexbar = tmp_path / "fake-codexbar"
    fake_codexbar.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os\n"
        "print(json.dumps([{'daily': [{'totalTokens': 110, 'totalCost': float(os.environ['EXPECTED_COST'])}]}]))\n",
        encoding="utf-8",
    )
    fake_codexbar.chmod(0o755)
    env = os.environ.copy()
    env["EXPECTED_COST"] = str(expected_cost)
    proc = subprocess.run([
        sys.executable, str(PARITY_SCRIPT), "--codex-home", str(tmp_path),
        "--days", "36500", "--codexbar-bin", str(fake_codexbar),
    ], check=True, capture_output=True, text=True, env=env)
    receipt = json.loads(proc.stdout)
    assert receipt["match"] is True
    assert receipt["tokens"]["delta"] == 0
    assert receipt["estimated_cost_usd"]["delta"] == 0


def test_cli_merges_lineage_codex_with_native_provider_once(tmp_path):
    timestamp = "2099-08-05T12:00:00Z"
    claude = tmp_path / "claude.jsonl"
    dump(claude, {
        "timestamp": timestamp, "type": "assistant", "requestId": "r",
        "message": {"id": "m", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 10, "output_tokens": 2}},
    }, jsonl=True)
    gemini_root = tmp_path / "empty-gemini"
    gemini_root.mkdir()
    cursor = tmp_path / "empty-cursor.json"
    dump(cursor, {"usageEvents": []})
    codex = tmp_path / "codex.jsonl"
    dump(codex, {"type": "session_meta", "payload": {"id": "s"}}, jsonl=True)
    with codex.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "turn_context", "timestamp": timestamp, "payload": {"model": "gpt-5"}}) + "\n")
        handle.write(json.dumps({"type": "event_msg", "timestamp": timestamp, "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 10},
        }}}) + "\n")
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--days", "36500", "--format", "json",
        "--path", f"codex={codex}", "--path", f"claude={claude}",
        "--path", f"gemini={gemini_root}", "--path", f"cursor={cursor}",
    ], check=True, capture_output=True, text=True)
    report = json.loads(proc.stdout)
    assert report["overall"]["total_tokens"] == 122
    assert report["overall"]["events"] == 2
    assert [row["provider"] for row in report["by_model"]].count("codex") == 1
    assert [row["provider"] for row in report["by_model"]].count("claude") == 1
    assert report["diagnostics"]["backends"] == {
        "antigravity": "quota-only", "claude": "native", "codex": "native-lineage",
        "cursor": "native", "gemini": "native",
    }
