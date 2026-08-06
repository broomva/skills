from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "audit_harness_usage.py"
sys.path.insert(0, str(SCRIPT.parent))

import antigravity_quota as quota  # noqa: E402


def quota_summary() -> dict:
    return {
        "response": {
            "groups": [
                {
                    "displayName": "Gemini Models",
                    "buckets": [
                        {
                            "bucketId": "gemini-weekly",
                            "displayName": "Weekly Limit",
                            "remaining": {"remainingFraction": 0.82},
                            "resetTime": "2026-06-19T08:45:39Z",
                        },
                        {
                            "bucketId": "gemini-5h",
                            "displayName": "Five Hour Limit",
                            "remaining": {"case": "remainingFraction", "value": 0.91},
                            "resetTime": "2026-06-15T11:39:34Z",
                        },
                    ],
                },
                {
                    "displayName": "Claude and GPT models",
                    "buckets": [
                        {
                            "bucketId": "3p-weekly",
                            "displayName": "Weekly Limit",
                            "remaining": {"remainingFraction": 0.64},
                        },
                        {
                            "bucketId": "3p-5h",
                            "displayName": "Five Hour Limit",
                            "remaining": {"remainingFraction": 0.73},
                        },
                    ],
                },
            ]
        }
    }


def test_quota_summary_normalizes_group_windows_and_oneof_shape():
    windows, warnings = quota.parse_quota_summary(quota_summary())
    assert warnings == []
    assert [window["title"] for window in windows] == [
        "Gemini 5-hour", "Gemini weekly", "Claude/GPT 5-hour", "Claude/GPT weekly",
    ]
    assert [window["window_minutes"] for window in windows] == [300, 10080, 300, 10080]
    assert [window["remaining_fraction"] for window in windows] == pytest.approx([.91, .82, .73, .64])
    assert windows[0]["used_fraction"] == pytest.approx(.09)
    assert windows[0]["resets_at"] == "2026-06-15T11:39:34Z"


def test_invalid_and_disabled_buckets_never_become_known_usage():
    payload = {
        "groups": [{"displayName": "Gemini", "buckets": [
            {"bucketId": "bad", "remainingFraction": 1.1},
            {"bucketId": "off", "remainingFraction": .5, "disabled": True},
        ]}],
    }
    windows, warnings = quota.parse_quota_summary(payload)
    assert [window["usage_known"] for window in windows] == [False, False]
    assert all(window["remaining_fraction"] is None for window in windows)
    assert any("invalid Antigravity remaining fraction" in warning for warning in warnings)


def test_consumed_quota_fields_cannot_emit_email_identity_or_free_form_prose():
    email = "private@example.com"
    payload = {"groups": [{
        "displayName": email,
        "buckets": [{
            "bucketId": "weekly",
            "displayName": email,
            "description": f"Owner {email}",
            "remainingFraction": .5,
        }],
    }]}
    windows, warnings = quota.parse_quota_summary(payload)
    serialized = json.dumps(windows)
    assert warnings == []
    assert windows[0]["title"] == "Quota weekly"
    assert windows[0]["reset_description"] is None
    assert email not in serialized


def test_user_status_fallback_ignores_account_identity():
    payload = {
        "code": 0,
        "userStatus": {
            "email": "private@example.com",
            "planStatus": {"planInfo": {"planName": "Pro"}},
            "cascadeModelConfigData": {"clientModelConfigs": [{
                "label": "Claude Sonnet",
                "modelOrAlias": {"model": "claude-sonnet"},
                "quotaInfo": {"remainingFraction": .5, "resetTime": "2025-12-24T10:00:00Z"},
            }]},
        },
    }
    windows, warnings = quota.parse_model_quotas(payload)
    serialized = json.dumps(windows)
    assert warnings == []
    assert len(windows) == 1
    assert windows[0]["family"] == "claude-gpt"
    assert "private@example.com" not in serialized
    assert "planName" not in serialized


def test_export_directory_keeps_newest_snapshot_and_sanitizes_csv_labels(tmp_path):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old_payload = quota_summary()
    new_payload = quota_summary()
    old_payload["response"]["groups"][0]["buckets"][0]["remaining"]["remainingFraction"] = .1
    new_payload["response"]["groups"][0]["buckets"][0]["remaining"]["remainingFraction"] = .9
    new_payload["response"]["groups"][0]["displayName"] = "=HYPERLINK(evil)"
    old.write_text(json.dumps(old_payload), encoding="utf-8")
    new.write_text(json.dumps(new_payload), encoding="utf-8")
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))
    result = quota.load_exports([tmp_path])
    weekly = next(window for window in result.windows if window["quota_id"].endswith("gemini-weekly"))
    assert weekly["remaining_fraction"] == .9
    assert all(not window["title"].startswith(("=", "+", "-", "@")) for window in result.windows)
    assert result.files_discovered == 2


def test_linux_proc_port_parser_matches_owned_listening_socket(tmp_path):
    process = tmp_path / "123"
    (process / "fd").mkdir(parents=True)
    (process / "net").mkdir()
    (process / "fd" / "4").symlink_to("socket:[98765]")
    (process / "net" / "tcp").write_text(
        "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
        "0: 0100007F:1F90 00000000:0000 0A 0:0 0:0 0 1000 0 98765\n",
        encoding="utf-8",
    )
    assert quota._proc_listening_ports(123, tmp_path) == [8080]


def test_process_detection_keeps_antigravity_distinct_and_requires_ide_csrf():
    output = "\n".join([
        " 101 /Applications/Antigravity.app/Contents/Resources/language_server --app_data_dir antigravity --csrf_token secret --extension_server_port 64000",
        " 102 /Applications/Antigravity IDE.app/Contents/extensions/antigravity/bin/language_server --app_data_dir antigravity-ide",
        " 103 /usr/local/bin/agy serve",
        " 104 /usr/local/bin/gemini",
        " 105 /tmp/language_server --csrf_token unrelated",
    ])
    processes = quota.parse_process_list(output)
    assert [(process.pid, process.kind) for process in processes] == [(101, "app"), (103, "cli")]
    assert processes[0].csrf_token == "secret"
    assert processes[1].csrf_token == ""


def test_probe_prefers_summary_then_falls_back_without_spawning_processes():
    process = quota.ProcessInfo(pid=101, kind="app", csrf_token="secret")
    calls: list[str] = []

    def requester(endpoint, path, body, timeout):
        calls.append(path)
        if path == quota.QUOTA_SUMMARY_PATH:
            return {"groups": []}
        if path == quota.USER_STATUS_PATH:
            return {"userStatus": {"cascadeModelConfigData": {"clientModelConfigs": [{
                "label": "Gemini Pro",
                "modelOrAlias": {"model": "gemini-pro"},
                "quotaInfo": {"remainingFraction": .25},
            }]}}}
        raise AssertionError("unexpected third endpoint")

    result = quota.probe_local(
        process_reader=lambda timeout: [process],
        port_reader=lambda pid, timeout: [64440],
        requester=requester,
    )
    assert calls == [quota.QUOTA_SUMMARY_PATH, quota.USER_STATUS_PATH]
    assert result.backend == "local-app"
    assert result.windows[0]["remaining_fraction"] == .25


def test_probe_timeout_is_one_deadline_not_multiplied_per_attempt():
    process = quota.ProcessInfo(pid=101, kind="app", csrf_token="secret")
    port_calls: list[float] = []
    ticks = iter([10.0, 12.1])
    result = quota.probe_local(
        timeout=2,
        process_reader=lambda timeout: [process],
        port_reader=lambda pid, timeout: port_calls.append(timeout) or [64440],
        requester=lambda endpoint, path, body, timeout: quota_summary(),
        clock=lambda: next(ticks),
    )
    assert port_calls == []
    assert result.backend == "unavailable"
    assert result.warnings == ["Antigravity local quota probe timed out."]


def test_local_request_refuses_redirect_without_forwarding_csrf():
    received_headers: list[dict[str, str]] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_GET(self):
            received_headers.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)

    class Redirector(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{receiver.server_port}/capture")
            self.end_headers()

        def log_message(self, format, *args):
            pass

    redirector = ThreadingHTTPServer(("127.0.0.1", 0), Redirector)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (receiver, redirector)]
    for thread in threads:
        thread.start()
    try:
        endpoint = quota.Endpoint("http", redirector.server_port, "top-secret", "local-ide")
        with pytest.raises(urllib.error.HTTPError) as error:
            quota.request_json(endpoint, quota.QUOTA_SUMMARY_PATH, {"forceRefresh": True}, 1)
        assert error.value.code == 302
        assert received_headers == []
    finally:
        redirector.shutdown()
        receiver.shutdown()
        redirector.server_close()
        receiver.server_close()


def test_antigravity_cli_export_reports_quotas_without_fabricating_tokens_or_cost(tmp_path):
    export = tmp_path / "antigravity.json"
    payload = quota_summary()
    payload["userStatus"] = {"email": "private@example.com"}
    export.write_text(json.dumps(payload), encoding="utf-8")
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--provider", "antigravity", "--format", "json",
        "--path", f"antigravity={export}",
    ], check=True, capture_output=True, text=True)
    report = json.loads(proc.stdout)
    assert report["overall"]["events"] == 0
    assert report["overall"]["total_tokens"] == 0
    assert report["overall"]["estimated_cost_usd"] is None
    assert report["by_model"] == []
    assert len(report["quota_windows"]) == 4
    assert report["diagnostics"]["backends"]["antigravity"] == "quota-only"
    assert report["diagnostics"]["quota_backends"]["antigravity"] == "export"
    assert "private@example.com" not in proc.stdout
    assert str(tmp_path) not in proc.stdout
    assert any(item["kind"] == "quota-semantics" for item in report["insights"])


def test_antigravity_csv_marks_quota_records(tmp_path):
    export = tmp_path / "antigravity.json"
    export.write_text(json.dumps(quota_summary()), encoding="utf-8")
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--provider", "antigravity", "--format", "csv",
        "--path", f"antigravity={export}",
    ], check=True, capture_output=True, text=True)
    assert "record_type" in proc.stdout.splitlines()[0]
    assert proc.stdout.count("quota-window") == 4
