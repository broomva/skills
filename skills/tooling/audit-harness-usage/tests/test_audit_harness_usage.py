from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "audit_harness_usage.py"
PRICING = SKILL / "references" / "pricing.v1.json"
sys.path.insert(0, str(SCRIPT.parent))

import audit_harness_usage as usage  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def run_scan(provider: str, root: Path, **overrides):
    args = argparse.Namespace(
        provider=provider,
        days=30,
        path=[f"{provider}={root}"],
        pricing=str(PRICING),
        max_files=None,
        **overrides,
    )
    return usage.scan(args)


def now() -> str:
    return "2099-08-05T12:00:00Z"


def test_codex_last_usage_normalizes_cached_subset(tmp_path):
    path = tmp_path / "sessions" / "session.jsonl"
    write_jsonl(path, [
        {"type": "session_meta", "payload": {"id": "s1"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.4"}},
        {"timestamp": now(), "type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 200, "reasoning_output_tokens": 50, "total_tokens": 1200}
        }}},
    ])
    report = run_scan("codex", tmp_path)
    row = report["by_model"][0]
    assert row["input_uncached"] == 600
    assert row["cache_read"] == 400
    # CodexBar's cost scanner treats reasoning as part of provider output;
    # token_count does not expose a separately billable reasoning component.
    assert row["output"] == 200
    assert row["reasoning"] == 0
    assert row["total_tokens"] == 1200
    assert row["estimated_cost_usd"] == pytest.approx(0.0046)


def test_codex_cumulative_totals_use_positive_delta(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_jsonl(path, [
        {"type": "turn_context", "payload": {"model": "gpt-5"}},
        {"timestamp": now(), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10}}}},
        {"timestamp": now(), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 160, "cached_input_tokens": 40, "output_tokens": 25}}}},
    ])
    report = run_scan("codex", path)
    row = report["by_model"][0]
    assert row["total_tokens"] == 185
    assert "codex-lineage-aware" in row["quality"]


def token_row(timestamp: str, last_input: int, total_input: int, last_output: int, total_output: int) -> dict:
    return {"timestamp": timestamp, "type": "event_msg", "payload": {"type": "token_count", "info": {
        "last_token_usage": {"input_tokens": last_input, "cached_input_tokens": 0, "output_tokens": last_output},
        "total_token_usage": {"input_tokens": total_input, "cached_input_tokens": 0, "output_tokens": total_output},
    }}}


def test_codex_resolves_parent_snapshot_at_fork_time(tmp_path):
    parent = tmp_path / "sessions" / "parent.jsonl"
    child = tmp_path / "archived_sessions" / "child.jsonl"
    write_jsonl(parent, [
        {"type": "session_meta", "timestamp": "2099-08-05T11:00:00Z", "payload": {"id": "parent"}},
        {"type": "turn_context", "timestamp": "2099-08-05T11:00:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:01:00Z", 10, 10, 1, 1),
        token_row("2099-08-05T11:02:00Z", 5, 15, 1, 2),
    ])
    write_jsonl(child, [
        {"type": "session_meta", "timestamp": "2099-08-05T11:01:00Z", "payload": {
            "id": "child", "forked_from_id": "parent", "timestamp": "2099-08-05T11:01:00Z",
        }},
        {"type": "turn_context", "timestamp": "2099-08-05T11:01:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:01:30Z", 10, 10, 1, 1),
        token_row("2099-08-05T11:03:00Z", 5, 15, 1, 2),
    ])
    report = run_scan("codex", tmp_path)
    assert report["overall"]["total_tokens"] == 23
    assert report["diagnostics"]["fork_prefix_tokens_suppressed"]["codex"] == 11
    assert report["diagnostics"]["codex_unresolved_forks"] == 0
    assert report["diagnostics"]["backends"]["codex"] == "native-lineage"


def test_codex_unresolved_parent_skips_first_snapshot_then_counts_growth(tmp_path):
    child = tmp_path / "child.jsonl"
    write_jsonl(child, [
        {"type": "session_meta", "timestamp": "2099-08-05T11:00:00Z", "payload": {
            "id": "child", "forked_from_id": "missing", "timestamp": "2099-08-05T11:00:00Z",
        }},
        {"type": "turn_context", "timestamp": "2099-08-05T11:00:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:01:00Z", 10, 10, 0, 0),
        token_row("2099-08-05T11:02:00Z", 5, 15, 0, 0),
    ])
    report = run_scan("codex", tmp_path)
    assert report["overall"]["total_tokens"] == 5
    assert report["diagnostics"]["codex_unresolved_forks"] == 1
    assert any("parent baseline could not be resolved" in warning for warning in report["diagnostics"]["warnings"])


def test_codex_unresolved_total_only_rows_are_visible_and_not_guessed(tmp_path):
    child = tmp_path / "child.jsonl"
    write_jsonl(child, [
        {"type": "session_meta", "timestamp": "2099-08-05T11:00:00Z", "payload": {
            "id": "child", "forked_from_id": "missing", "timestamp": "2099-08-05T11:00:00Z",
        }},
        {"type": "turn_context", "timestamp": "2099-08-05T11:00:00Z", "payload": {"model": "gpt-5"}},
        {"timestamp": "2099-08-05T11:01:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 0},
        }}},
        {"timestamp": "2099-08-05T11:02:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 15, "cached_input_tokens": 0, "output_tokens": 0},
        }}},
    ])
    report = run_scan("codex", tmp_path)
    assert report["overall"]["total_tokens"] == 0
    assert report["diagnostics"]["codex_unresolved_total_only_rows"] == 2
    assert any("no safe last-usage cap" in insight["message"] for insight in report["insights"])


def test_codex_parent_baseline_uses_timestamp_order_not_file_order(tmp_path):
    parent = tmp_path / "parent.jsonl"
    child = tmp_path / "child.jsonl"
    write_jsonl(parent, [
        {"type": "session_meta", "payload": {"id": "parent"}},
        {"type": "turn_context", "timestamp": "2099-08-05T11:00:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:02:00Z", 10, 20, 0, 0),
        token_row("2099-08-05T11:01:00Z", 10, 10, 0, 0),
    ])
    write_jsonl(child, [
        {"type": "session_meta", "payload": {
            "id": "child", "forked_from_id": "parent", "timestamp": "2099-08-05T11:02:30Z",
        }},
        {"type": "turn_context", "timestamp": "2099-08-05T11:02:30Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:02:45Z", 20, 20, 0, 0),
        token_row("2099-08-05T11:03:00Z", 5, 25, 0, 0),
    ])
    report = run_scan("codex", tmp_path)
    # The parent file itself remains append-accounted (10 tokens), while its
    # fork snapshot must be reconstructed chronologically (20 inherited), so
    # only the child's 5-token post-fork growth is added.
    assert report["overall"]["total_tokens"] == 15
    assert report["diagnostics"]["fork_prefix_tokens_suppressed"]["codex"] == 20


def test_codex_invalid_parent_timestamp_makes_baseline_unresolved(tmp_path):
    parent = tmp_path / "parent.jsonl"
    child = tmp_path / "child.jsonl"
    write_jsonl(parent, [
        {"type": "session_meta", "payload": {"id": "parent"}},
        token_row("not-a-time", 10, 10, 0, 0),
    ])
    write_jsonl(child, [
        {"type": "session_meta", "payload": {
            "id": "child", "forked_from_id": "parent", "timestamp": "2099-08-05T11:00:00Z",
        }},
        {"type": "turn_context", "timestamp": "2099-08-05T11:00:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:01:00Z", 10, 10, 0, 0),
        token_row("2099-08-05T11:02:00Z", 5, 15, 0, 0),
    ])
    report = run_scan("codex", tmp_path)
    assert report["overall"]["total_tokens"] == 5
    assert report["diagnostics"]["codex_invalid_parent_timestamps"] == 1
    assert report["diagnostics"]["codex_unresolved_forks"] == 1
    assert any("unparseable token timestamp" in warning for warning in report["diagnostics"]["warnings"])


def test_codex_invalid_fork_cutoff_makes_baseline_unresolved(tmp_path):
    parent = tmp_path / "parent.jsonl"
    child = tmp_path / "child.jsonl"
    write_jsonl(parent, [
        {"type": "session_meta", "payload": {"id": "parent"}},
        token_row("2099-08-05T11:00:00Z", 10, 10, 0, 0),
    ])
    write_jsonl(child, [
        {"type": "session_meta", "payload": {
            "id": "child", "forked_from_id": "parent", "timestamp": "z",
        }},
        {"type": "turn_context", "timestamp": "2099-08-05T11:01:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:02:00Z", 10, 10, 0, 0),
        token_row("2099-08-05T11:03:00Z", 5, 15, 0, 0),
    ])
    report = run_scan("codex", tmp_path)
    assert report["diagnostics"]["codex_unresolved_forks"] == 1
    assert "codex" not in report["diagnostics"]["fork_prefix_tokens_suppressed"]


def test_codex_fractional_counter_is_rejected_visibly(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_jsonl(path, [
        {"type": "turn_context", "payload": {"model": "gpt-5"}},
        {"timestamp": now(), "type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 1.9, "output_tokens": 2},
        }}},
    ])
    report = run_scan("codex", path)
    assert report["overall"]["total_tokens"] == 2
    assert any("invalid codex input token counter" in warning for warning in report["diagnostics"]["warnings"])


def test_codex_interleaved_counters_use_monotonic_watermark(tmp_path):
    path = tmp_path / "interleaved.jsonl"
    write_jsonl(path, [
        {"type": "session_meta", "payload": {"id": "s"}},
        {"type": "turn_context", "timestamp": "2099-08-05T11:00:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:01:00Z", 100, 100, 0, 0),
        token_row("2099-08-05T11:02:00Z", 20, 20, 0, 0),
        token_row("2099-08-05T11:03:00Z", 90, 110, 0, 0),
    ])
    report = run_scan("codex", path)
    assert report["overall"]["total_tokens"] == 110
    assert report["diagnostics"]["codex_interleaved_files"] == 1


def test_codex_subagent_owned_suffix_uses_local_boundary(tmp_path):
    path = tmp_path / "subagent.jsonl"
    write_jsonl(path, [
        {"type": "session_meta", "payload": {"id": "leaf", "source": {"subagent": {"name": "worker"}}}},
        {"type": "turn_context", "timestamp": "2099-08-05T11:00:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:01:00Z", 100, 100, 0, 0),
        {"type": "session_meta", "payload": {"id": "ancestor"}},
        {"type": "turn_context", "timestamp": "2099-08-05T11:02:00Z", "payload": {"model": "gpt-5"}},
        {"type": "inter_agent_communication_metadata", "timestamp": "2099-08-05T11:02:01Z", "payload": {"trigger_turn": True}},
        token_row("2099-08-05T11:03:00Z", 10, 110, 0, 0),
    ])
    report = run_scan("codex", path)
    assert report["overall"]["total_tokens"] == 10
    assert report["diagnostics"]["codex_owned_suffixes"] == 1


def test_codex_ambiguous_copied_prefix_is_suppressed_visibly(tmp_path):
    path = tmp_path / "subagent.jsonl"
    write_jsonl(path, [
        {"type": "session_meta", "payload": {"id": "leaf", "source": {"subagent": {"name": "worker"}}}},
        {"type": "session_meta", "payload": {"id": "ancestor-a"}},
        {"type": "session_meta", "payload": {"id": "ancestor-b"}},
        {"type": "turn_context", "timestamp": "2099-08-05T11:00:00Z", "payload": {"model": "gpt-5"}},
        token_row("2099-08-05T11:01:00Z", 10, 10, 0, 0),
    ])
    report = run_scan("codex", path)
    assert report["overall"]["total_tokens"] == 0
    assert report["diagnostics"]["codex_ambiguous_copied_prefixes"] == 1
    assert any("no unique parent" in warning for warning in report["diagnostics"]["warnings"])


def test_claude_components_are_disjoint_and_final_stream_chunk_wins(tmp_path):
    path = tmp_path / "project" / "trace.jsonl"
    base = {"timestamp": now(), "type": "assistant", "requestId": "r1"}
    write_jsonl(path, [
        {**base, "message": {"id": "m1", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 100, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 250, "output_tokens": 20}}},
        {**base, "message": {"id": "m1", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 100, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 300, "cache_creation": {"ephemeral_1h_input_tokens": 50}, "output_tokens": 40}}},
    ])
    report = run_scan("claude", tmp_path)
    row = report["by_model"][0]
    assert row["events"] == 1
    assert row["input_uncached"] == 100
    assert row["cache_read"] == 200
    assert row["cache_write_5m"] == 250
    assert row["cache_write_1h"] == 50
    assert row["total_tokens"] == 640
    expected = (100 * 3 + 200 * .3 + 250 * 3.75 + 50 * 6 + 40 * 15) / 1_000_000
    assert row["estimated_cost_usd"] == pytest.approx(expected)


def test_claude_rows_missing_half_of_provider_identity_remain_distinct(tmp_path):
    path = tmp_path / "session.jsonl"
    write_jsonl(path, [
        {
            "timestamp": now(), "type": "assistant",
            "message": {"id": "same-message", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 10, "output_tokens": 1}},
        },
        {
            "timestamp": now(), "type": "assistant",
            "message": {"id": "same-message", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 20, "output_tokens": 2}},
        },
    ])
    report = run_scan("claude", tmp_path)
    assert report["window_days"] == 30
    assert report["overall"]["events"] == 2
    assert report["overall"]["total_tokens"] == 33


def test_claude_one_hour_cache_component_is_clamped_to_total_creation(tmp_path):
    path = tmp_path / "session.jsonl"
    write_jsonl(path, [{
        "timestamp": now(), "type": "assistant", "requestId": "request",
        "message": {
            "id": "message", "model": "claude-sonnet-4-6",
            "usage": {
                "cache_creation_input_tokens": 20,
                "cache_creation": {"ephemeral_1h_input_tokens": 50},
            },
        },
    }])
    report = run_scan("claude", tmp_path)
    row = report["by_model"][0]
    assert row["cache_write_5m"] == 0
    assert row["cache_write_1h"] == 20
    assert row["total_tokens"] == 20


def test_gemini_cached_is_subset_and_thoughts_are_output_side(tmp_path):
    path = tmp_path / "project" / "chats" / "session-1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"sessionId": "g1", "messages": [{
        "type": "gemini", "timestamp": now(), "model": "gemini-3-flash-preview",
        "tokens": {"input": 1000, "cached": 700, "output": 100, "thoughts": 50, "tool": 25, "total": 1175}
    }]}), encoding="utf-8")
    report = run_scan("gemini", tmp_path)
    row = report["by_model"][0]
    assert row["input_uncached"] == 300
    assert row["cache_read"] == 700
    assert row["total_tokens"] == 1175
    expected = (300 * .5 + 700 * .05 + 175 * 3) / 1_000_000
    assert row["estimated_cost_usd"] == pytest.approx(expected)


def test_gemini_jsonl_patch_keeps_final_cumulative_message_once(tmp_path):
    path = tmp_path / "project" / "chats" / "session.jsonl"
    base = {"id": "gm1", "timestamp": now(), "model": "gemini-2.5-flash"}
    write_jsonl(path, [
        {"messages": [{**base, "tokens": {"input": 10, "output": 1}}]},
        {"$set": {"messages": [{**base, "tokens": {"input": 20, "output": 2}}]}},
    ])
    report = run_scan("gemini", path)
    assert report["overall"]["events"] == 1
    assert report["overall"]["total_tokens"] == 22


def test_cursor_preserves_disjoint_counts_and_two_cost_semantics(tmp_path):
    path = tmp_path / "cursor-export.json"
    path.write_text(json.dumps({"usageEvents": [{
        "id": "c1", "timestamp": 4079140800000, "model": "claude-sonnet-4-6", "chargedCents": 17,
        "tokenUsage": {"inputTokens": 100, "outputTokens": 20, "cacheReadTokens": 300, "cacheWriteTokens": 40, "totalCents": 25}
    }]}), encoding="utf-8")
    report = run_scan("cursor", path)
    row = report["by_model"][0]
    assert row["total_tokens"] == 460
    assert row["reported_list_cost_usd"] == pytest.approx(.25)
    assert row["charged_cost_usd"] == pytest.approx(.17)
    assert row["estimated_cost_usd"] is None


def test_cursor_never_publishes_partial_charged_sum(tmp_path):
    path = tmp_path / "cursor-export.json"
    path.write_text(json.dumps({"usageEvents": [
        {"id": "c1", "timestamp": 4079140800000, "model": "m", "chargedCents": 17, "tokenUsage": {"inputTokens": 10, "outputTokens": 1, "totalCents": 20}},
        {"id": "c2", "timestamp": 4079140800001, "model": "m", "tokenUsage": {"inputTokens": 10, "outputTokens": 1, "totalCents": 20}},
    ]}), encoding="utf-8")
    report = run_scan("cursor", path)
    assert report["overall"]["reported_list_cost_usd"] == pytest.approx(.4)
    assert report["overall"]["charged_cost_usd"] is None
    assert report["by_model"][0]["charged_cost_usd"] is None


def test_cursor_invalid_cost_is_missing_not_fatal(tmp_path):
    path = tmp_path / "cursor-export.json"
    path.write_text(json.dumps({"usageEvents": [{
        "id": "c1", "timestamp": 4079140800000, "model": "m", "chargedCents": -1,
        "tokenUsage": {"inputTokens": 10, "outputTokens": 1, "totalCents": "NaN"},
    }]}), encoding="utf-8")
    report = run_scan("cursor", path)
    assert report["overall"]["reported_list_cost_usd"] is None
    assert report["overall"]["charged_cost_usd"] is None
    assert any("invalid Cursor" in warning for warning in report["diagnostics"]["warnings"])


def test_nonfinite_or_out_of_range_timestamp_uses_epoch_fallback():
    epoch = usage.parse_timestamp(0)
    assert usage.parse_timestamp(float("inf")) == epoch
    assert usage.parse_timestamp(10**100) == epoch


def test_unknown_model_is_null_not_zero(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_jsonl(path, [
        {"type": "turn_context", "payload": {"model": "future-model"}},
        {"timestamp": now(), "type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 100, "output_tokens": 10}}}},
    ])
    report = run_scan("codex", path)
    assert report["overall"]["estimated_cost_usd"] is None
    assert report["overall"]["pricing_coverage"] == 0
    assert "future-model" in report["insights"][-1]["message"]


def test_malformed_rows_are_counted_not_fatal(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    report = run_scan("codex", path)
    assert report["diagnostics"]["malformed_rows"]["codex"] == 1


def test_invalid_token_counter_is_visible_and_nonfatal(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_jsonl(path, [
        {"type": "turn_context", "payload": {"model": "gpt-5"}},
        {"timestamp": now(), "type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": float("inf"), "output_tokens": 10},
        }}},
    ])
    report = run_scan("codex", path)
    assert report["overall"]["total_tokens"] == 10
    assert any("invalid codex input" in warning for warning in report["diagnostics"]["warnings"])


def test_long_context_prices_entire_request_at_long_rate():
    card = usage.RateCard(PRICING)
    event = usage.UsageEvent("codex", "gpt-5.4", usage.parse_timestamp(now()), "e", input_uncached=272001, output=1)
    cost, name = card.price(event)
    assert name.endswith(":long-context")
    assert cost == pytest.approx((272001 * 5 + 1 * 22.5) / 1_000_000)


def test_incomplete_custom_rate_is_unpriced(tmp_path):
    pricing = tmp_path / "pricing.json"
    pricing.write_text(json.dumps({
        "as_of": "2099-01-01",
        "models": {"partial": {"provider": "codex", "input": 1.0}},
    }), encoding="utf-8")
    card = usage.RateCard(pricing)
    event = usage.UsageEvent("codex", "partial", usage.parse_timestamp(now()), "e", input_uncached=10, output=1)
    assert card.price(event) is None


@pytest.mark.parametrize("payload", [[], {}, {"as_of": "2099-01-01"}, {"models": {}}])
def test_malformed_pricing_shape_raises_value_error(tmp_path, payload):
    pricing = tmp_path / "pricing.json"
    pricing.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="pricing file must be an object"):
        usage.RateCard(pricing)


@pytest.mark.parametrize("parser", [usage.parse_claude, usage.parse_gemini, usage.parse_cursor])
def test_disappeared_trace_file_is_nonfatal(tmp_path, parser):
    diagnostics = usage.Diagnostics()
    assert list(parser(tmp_path / "already-rotated.jsonl", diagnostics)) == []


def test_unsafe_model_label_is_replaced_before_all_rendering(tmp_path):
    secret = "=DO_NOT_COPY_PRIVATE_PROMPT\n/Users/private/project"
    path = tmp_path / "cursor-export.json"
    path.write_text(json.dumps({"usageEvents": [{
        "id": "c1", "timestamp": 4079140800000, "model": secret,
        "tokenUsage": {"inputTokens": 10, "outputTokens": 1},
    }]}), encoding="utf-8")
    report = run_scan("cursor", path)
    assert report["by_model"][0]["model"] == "unknown"
    assert secret not in json.dumps(report)
    assert secret not in usage.render_text(report)
    assert secret not in usage.render_csv(report)


@pytest.mark.parametrize("unsafe", ["C:/Users/private/project", "../private/project", "work/private/project"])
def test_path_shaped_model_labels_are_replaced(unsafe):
    diagnostics = usage.Diagnostics()
    assert usage.safe_model(unsafe, diagnostics, "test") == "unknown"
    assert unsafe not in json.dumps(diagnostics.serializable())


def test_explicit_export_uses_event_time_not_old_file_mtime(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_jsonl(path, [
        {"type": "turn_context", "payload": {"model": "gpt-5"}},
        {"timestamp": now(), "type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 10, "output_tokens": 1},
        }}},
    ])
    os.utime(path, (1, 1))
    report = run_scan("codex", path)
    assert report["overall"]["total_tokens"] == 11


def test_cli_json_contains_no_prompt_or_response_content(tmp_path):
    secret = "DO_NOT_COPY_PRIVATE_PROMPT"
    path = tmp_path / "trace.jsonl"
    write_jsonl(path, [
        {"type": "turn_context", "payload": {"model": "gpt-5", "user_prompt": secret}},
        {"timestamp": now(), "type": "event_msg", "payload": {"type": "token_count", "content": secret, "info": {"last_token_usage": {"input_tokens": 100, "output_tokens": 10}}}},
    ])
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--provider", "codex", "--days", "36500",
        "--path", f"codex={path}", "--format", "json",
    ], check=True, capture_output=True, text=True)
    assert secret not in proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["overall"]["total_tokens"] == 110
    assert str(tmp_path) not in proc.stdout
    assert payload["pricing"]["source"] == "bundled-snapshot"


def test_invalid_override_is_actionable():
    with pytest.raises(ValueError, match="PROVIDER=PATH"):
        usage.parse_overrides(["wrong"])
