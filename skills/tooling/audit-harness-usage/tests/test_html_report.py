from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "audit_harness_usage.py"
sys.path.insert(0, str(SCRIPT.parent))

import html_report  # noqa: E402
import audit_harness_usage as usage  # noqa: E402


def sample_report() -> dict:
    return {
        "schema_version": 1,
        "generated_at": "2026-08-06T12:00:00Z",
        "since": "2026-07-08T05:00:00Z",
        "window_days": 30,
        "cost_semantics": "Public API estimate, not an invoice.",
        "pricing": {"source": "bundled-snapshot", "as_of": "2026-08-05"},
        "overall": {
            "events": 4,
            "total_tokens": 1000,
            "input_uncached": 600,
            "cache_read": 50,
            "cache_write_5m": 0,
            "cache_write_1h": 0,
            "output": 300,
            "reasoning": 40,
            "tool": 10,
            "priced_tokens": 700,
            "pricing_coverage": .7,
            "estimated_cost_usd": None,
            "estimated_cost_usd_priced_portion": .0123,
            "reported_list_cost_usd": None,
            "charged_cost_usd": None,
        },
        "by_model": [{
            "provider": "codex",
            "model": "<script>alert(1)</script>",
            "events": 4,
            "total_tokens": 800,
            "priced_tokens": 500,
            "estimated_cost_usd": None,
            "estimated_cost_usd_priced_portion": .01,
        }],
        "quota_windows": [{
            "provider": "antigravity",
            "family": "gemini",
            "title": "Gemini <svg onload=alert(1)>",
            "remaining_fraction": .1,
            "usage_known": True,
            "resets_at": "2026-08-06T20:00:00Z",
        }],
        "insights": [{"kind": "quality", "message": "Skipped <img src=x onerror=alert(1)>"}],
        "diagnostics": {
            "backends": {"codex": "native-lineage", "antigravity": "quota-only"},
            "quota_backends": {"antigravity": "local-app"},
            "files_scanned": {"codex": 2},
            "malformed_rows": {"codex": 1},
            "unattributed_tokens": {},
            "codex_unresolved_forks": 0,
            "codex_unresolved_total_only_rows": 0,
            "codex_ambiguous_copied_prefixes": 0,
            "warnings": ["Warning <script>bad()</script>"],
        },
    }


def test_html_report_is_self_contained_structured_and_escapes_dynamic_values():
    report = sample_report()
    report["generated_at"] = "2026-08-06--><script>breakout()</script>"
    rendered = html_report.render_html(report)
    assert rendered.startswith("<!doctype html>")
    assert "slug: harness-usage-audit" in rendered
    assert "Improvement opportunities" in rendered
    assert "Where the tokens went" in rendered
    assert "Usage by model" in rendered
    assert "Quota windows" in rendered
    assert "Data quality and backends" in rendered
    assert "Content-Security-Policy" in rendered
    assert "<script>" not in rendered
    assert "<svg onload" not in rendered
    assert "<img src=" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script src=" not in rendered
    assert "<link rel=" not in rendered
    assert "--><script>breakout()" not in rendered
    assert 'role="img"' not in rendered
    assert 'class="composition-bar" aria-hidden="true"' in rendered
    assert "Usage aggregated by provider and model" in rendered
    assert "Selected window" in rendered
    assert "30 days" in rendered


def test_html_shows_provider_reported_cost_separately_from_estimate():
    report = sample_report()
    report["overall"]["reported_list_cost_usd"] = 2.0
    report["overall"]["charged_cost_usd"] = .5
    rendered = html_report.render_html(report)
    assert "Vendor-reported list cost" in rendered
    assert "Plan-deducted cost" in rendered
    assert "do not add to the API estimate" in rendered


def test_opportunity_signals_are_bounded_and_tied_to_report_evidence():
    opportunities = html_report.improvement_opportunities(sample_report())
    assert {item["kind"] for item in opportunities} == {"pricing", "cache", "routing", "quota"}
    combined = json.dumps(opportunities)
    assert "70.0% of tokens have a resolved rate" in combined
    assert "7.7% of normalized input" in combined
    assert "80.0% of tokens" in combined
    assert "malformed" not in combined
    assert "10.0% remaining" in combined
    assert "until quota resets" in combined
    assert len(opportunities) <= 6


def test_unknown_pricing_empty_report_and_unknown_quota_stay_unknown():
    report = sample_report()
    report["overall"]["pricing_coverage"] = None
    report["overall"]["estimated_cost_usd_priced_portion"] = 0
    rendered = html_report.render_html(report)
    assert "Establish pricing coverage" in rendered
    assert "Pricing coverage is unknown" in rendered
    assert "0.0% of tokens have a resolved rate" not in rendered

    report["quota_windows"][0]["remaining_fraction"] = None
    report["quota_windows"][0]["usage_known"] = False
    rendered = html_report.render_html(report)
    assert "usage unavailable" in rendered
    assert 'aria-valuenow="0.0"' not in rendered
    assert 'class="quota-track unavailable"' in rendered
    assert 'usage unavailable"><span' not in rendered

    empty = sample_report()
    empty["overall"].update({
        "events": 0,
        "total_tokens": 0,
        "input_uncached": 0,
        "cache_read": 0,
        "output": 0,
        "reasoning": 0,
        "tool": 0,
        "pricing_coverage": None,
        "estimated_cost_usd": None,
        "estimated_cost_usd_priced_portion": 0,
    })
    empty["by_model"] = []
    empty["quota_windows"] = []
    rendered = html_report.render_html(empty)
    assert "No trace usage" in rendered
    assert "No token events found" in rendered
    assert "Not applicable" in rendered
    assert "No trace usage found" in rendered
    assert "No normalized token events or quota windows were discovered" in rendered


def test_unresolved_codex_lineage_is_the_accounting_gap_signal():
    report = sample_report()
    report["diagnostics"]["codex_unresolved_forks"] = 2
    opportunities = html_report.improvement_opportunities(report)
    quality = [item for item in opportunities if item["kind"] == "quality"]
    assert len(quality) == 1
    assert "2 unresolved Codex lineage gap" in quality[0]["evidence"]


def test_cli_writes_html_and_refuses_overwrite_without_force(tmp_path):
    export = tmp_path / "quota.json"
    output = tmp_path / "usage-report.html"
    export.write_text(json.dumps({
        "groups": [{
            "displayName": "Gemini Models",
            "buckets": [{
                "bucketId": "gemini-weekly",
                "displayName": "Weekly Limit",
                "remainingFraction": .75,
            }],
        }],
    }), encoding="utf-8")
    command = [
        sys.executable, str(SCRIPT), "--provider", "antigravity", "--format", "html",
        "--path", f"antigravity={export}", "--output", str(output),
    ]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    assert first.stdout == ""
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    second = subprocess.run(command, check=False, capture_output=True, text=True)
    assert second.returncode == 2
    assert "pass --force to replace it" in second.stderr
    output.chmod(0o644)
    forced = subprocess.run([*command, "--force"], check=True, capture_output=True, text=True)
    assert forced.stdout == ""
    assert stat.S_IMODE(output.stat().st_mode) == 0o600

    protected = tmp_path / "protected.txt"
    symlink = tmp_path / "report-link.html"
    protected.write_text("keep", encoding="utf-8")
    symlink.symlink_to(protected)
    symlink_command = [*command[:-1], str(symlink), "--force"]
    refused = subprocess.run(symlink_command, check=False, capture_output=True, text=True)
    assert refused.returncode == 2
    assert protected.read_text(encoding="utf-8") == "keep"


def test_forced_output_replacement_is_atomic_on_failure(tmp_path, monkeypatch):
    output = tmp_path / "usage-report.html"
    output.write_text("old report", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated interruption")

    monkeypatch.setattr(usage.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        usage.write_output(output, "new report", force=True)

    assert output.read_text(encoding="utf-8") == "old report"
    assert list(tmp_path.glob(".usage-report.html.*.tmp")) == []


def test_quota_only_html_never_turns_allowance_into_token_cost(tmp_path):
    export = tmp_path / "quota.json"
    export.write_text(json.dumps({
        "groups": [{
            "displayName": "Claude and GPT models",
            "buckets": [{"bucketId": "3p-5h", "displayName": "Five Hour Limit", "remainingFraction": .5}],
        }],
    }), encoding="utf-8")
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--provider", "antigravity", "--format", "html",
        "--path", f"antigravity={export}",
    ], check=True, capture_output=True, text=True)
    assert "Not exposed" in proc.stdout
    assert "Quota status does not include tokens or cost" in proc.stdout
    assert "50.0%" in proc.stdout
    assert str(tmp_path) not in proc.stdout
