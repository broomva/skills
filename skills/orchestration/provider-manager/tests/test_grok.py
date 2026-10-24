"""Hermetic Grok usage contracts (BRO-3466): no network, no grok binary, no real credentials.

Fixtures replay the shapes measured on 2026-10-24 from grok 1.0.70's endpoints."""
import io
import json
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from conftest import IMPL_DIR
import pm_antigravity
import pm_cli
import pm_grok as grok

pytestmark = pytest.mark.new_only
EMAIL = "person@example.test"
TOKEN = "fake-private-grok-access-token"
NOW = 1792800000.0  # 2026-10-24T05:20Z, inside the measured week
CREDITS = {"config": {
    "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY", "start": "2026-10-24T00:08:50.788+00:00",
                      "end": "2026-10-31T00:08:50.788+00:00"},
    "creditUsagePercent": 11.0, "productUsage": [{"product": "GrokBot", "usagePercent": 11.0}],
    "isUnifiedBillingUser": True, "prepaidBalance": {"val": 0},
    "billingPeriodStart": "2026-10-24T00:08:50.788+00:00", "billingPeriodEnd": "2026-10-31T00:08:50.788+00:00"}}
USER = {"email": EMAIL, "subscriptionTier": "GrokPro", "userBlockedReason": None, "teamBlockedReasons": []}


def write_auth(expires="2026-10-25T02:00:29.803441Z", email=EMAIL, extra=None):
    entry = {"key": TOKEN, "auth_mode": "oidc", "email": email, "refresh_token": "fake-private-refresh",
             "expires_at": expires}
    data = {"https://auth.x.ai::fake-client": entry}
    data.update(extra or {})
    path = Path.home() / ".grok" / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def stub(monkeypatch, credits=None, user=None):
    calls = []
    def request(path, token):
        calls.append(path)
        assert token == TOKEN
        value = (user if user is not None else USER) if path.startswith("/user") else \
            (credits if credits is not None else CREDITS)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(grok, "_request", request)
    return calls


def test_measured_week_reads_as_one_weekly_window_with_reset_and_tier(monkeypatch):
    write_auth()
    stub(monkeypatch)
    [row] = grok.usage(now=NOW)
    assert row["status"] == "OK" and row["telemetry"] == "ok" and row["tier"] == "GrokPro"
    assert row["email"] == EMAIL and row["numbersAt"] == NOW
    [w] = row["windows"]
    assert w["kind"] == "weekly" and w["usedPercent"] == 11.0 and w["windowDurationMins"] == 10080
    assert w["resetsAt"] == "2026-10-31T00:08:50.788000Z"
    assert w["products"] == [{"product": "GrokBot", "usedPercent": 11.0}]


def test_a_spent_window_is_limited(monkeypatch):
    write_auth()
    spent = json.loads(json.dumps(CREDITS))
    spent["config"]["creditUsagePercent"] = 100
    stub(monkeypatch, credits=spent)
    assert grok.usage(now=NOW)[0]["status"] == "LIMITED"


def test_a_blocked_account_is_limited_with_the_reason(monkeypatch):
    write_auth()
    stub(monkeypatch, user=dict(USER, userBlockedReason="spend_cap"))
    row = grok.usage(now=NOW)[0]
    assert row["status"] == "LIMITED" and row["reason"] == "account_blocked"


@pytest.mark.parametrize("bad", [{}, {"config": {}}, {"config": {"creditUsagePercent": "11"}},
                                 {"config": {"creditUsagePercent": True}},
                                 {"config": {"creditUsagePercent": float("nan")}}])
def test_a_response_without_a_measured_percent_is_unavailable_never_zero(monkeypatch, bad):
    write_auth()
    stub(monkeypatch, credits=bad)
    row = grok.usage(now=NOW)[0]
    assert row["status"] == "UNAVAILABLE" and row["telemetry"] == "unavailable"
    assert row["reason"] == "usage_not_reported" and row["windows"] == [] and row["numbersAt"] is None


def test_an_expired_access_token_makes_no_request_and_says_so(monkeypatch):
    write_auth(expires="2026-10-24T00:00:00Z")
    calls = stub(monkeypatch)
    row = grok.usage(now=NOW)[0]
    assert calls == [] and row["status"] == "UNAVAILABLE" and row["reason"] == "access_token_expired"
    assert "grok models" in grok.format_rows([row])


def test_missing_login_is_needs_login(monkeypatch):
    calls = stub(monkeypatch)
    row = grok.usage(now=NOW)[0]
    assert calls == [] and row["status"] == "NEEDS_LOGIN" and row["reason"] == "not_logged_in"


def test_a_rejected_token_is_needs_login(monkeypatch):
    write_auth()
    stub(monkeypatch, user=grok.ProbeError("auth_rejected"))
    assert grok.usage(now=NOW)[0]["status"] == "NEEDS_LOGIN"


def test_identity_mismatch_stops_before_the_usage_call(monkeypatch):
    write_auth()
    calls = stub(monkeypatch, user=dict(USER, email="someone-else@example.test"))
    row = grok.usage(now=NOW)[0]
    assert row.get("reason") == "identity_mismatch" and row["status"] == "UNAVAILABLE"
    assert calls == ["/user?include=subscription"]


def test_the_probe_never_writes_the_grok_auth_file(monkeypatch):
    path = write_auth()
    before = path.read_bytes()
    stub(monkeypatch)
    grok.usage(force=True, now=NOW)
    assert path.read_bytes() == before


def test_cache_serves_inside_its_window_and_force_rereads(monkeypatch):
    write_auth()
    calls = stub(monkeypatch)
    grok.usage(now=NOW)
    again = grok.usage(now=NOW + 30)[0]
    assert len(calls) == 2 and again["numbersAgeSeconds"] == 30
    grok.usage(now=NOW + 30, force=True)
    assert len(calls) == 4


def test_a_failed_read_keeps_old_numbers_only_as_last_known(monkeypatch):
    write_auth()
    stub(monkeypatch)
    grok.usage(now=NOW)
    stub(monkeypatch, credits=grok.ProbeError("endpoint_throttled"))
    row = grok.usage(now=NOW + 600)[0]
    assert row["status"] == "UNAVAILABLE" and row["windows"] == [] and row["numbersAt"] is None
    assert row["lastKnown"]["numbersAgeSeconds"] == 600 and row["lastKnown"]["windows"][0]["usedPercent"] == 11.0
    text = grok.format_rows([row])
    assert "telemetry unavailable: endpoint_throttled" in text and "last known 10m ago" in text


def test_transport_errors_disclose_no_body_and_refuse_redirects(monkeypatch):
    handlers = []
    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Authorization") == "Bearer " + TOKEN
            raise urllib.error.HTTPError(request.full_url, 500, "x", {}, io.BytesIO(b"secret body " + TOKEN.encode()))
    monkeypatch.setattr(grok.urllib.request, "build_opener", lambda handler: handlers.append(handler) or Opener())
    with pytest.raises(grok.ProbeError) as exc:
        grok._request("/billing?format=credits", TOKEN)
    assert str(exc.value) == "http_500" and exc.value.__cause__ is None
    assert len(handlers) == 1 and isinstance(handlers[0], grok._NoRedirect)
    assert handlers[0].redirect_request(None, None, 302, "", {}, "https://elsewhere.example") is None


def test_no_result_field_carries_the_token(monkeypatch):
    write_auth()
    stub(monkeypatch, user=dict(USER, subscriptionTier=TOKEN))
    row = grok.usage(now=NOW)[0]
    assert TOKEN not in json.dumps(row) and row.get("reason") == "credential_in_result"
    assert row["status"] == "UNAVAILABLE" and row["windows"] == []


@pytest.mark.parametrize("bad", [
    {"config": {"creditUsagePercent": 5, "currentPeriod": {"type": [1]}}},
    {"config": {"creditUsagePercent": 5, "productUsage": 5}},
    {"config": {"creditUsagePercent": 5, "productUsage": [5, None, {"product": 1}]}},
    {"config": {"creditUsagePercent": 5, "currentPeriod": "weekly"}}])
def test_odd_shapes_never_crash_and_never_invent_a_window_kind(monkeypatch, bad):
    write_auth()
    stub(monkeypatch, credits=bad)
    row = grok.usage(now=NOW)[0]
    assert row["status"] == "OK" and row["windows"][0]["usedPercent"] == 5 and row["windows"][0]["kind"] == "other"
    assert "products" not in row["windows"][0]
    grok.format_rows([row])


def test_a_parser_crash_is_unavailable_not_an_exception(monkeypatch):
    write_auth()
    stub(monkeypatch)
    monkeypatch.setattr(grok, "parse_credits", Mock(side_effect=TypeError("boom")))
    try:
        row = grok.usage(now=NOW)[0]
    except TypeError:
        raise AssertionError("a parser crash escaped the probe") from None
    assert row["status"] == "UNAVAILABLE" and row.get("reason") == "invalid_response" and row["windows"] == []


def test_a_spent_product_is_limited_even_under_the_overall_percent(monkeypatch):
    write_auth()
    spent = json.loads(json.dumps(CREDITS))
    spent["config"]["productUsage"] = [{"product": "GrokBot", "usagePercent": 100}]
    stub(monkeypatch, credits=spent)
    assert grok.usage(now=NOW)[0]["status"] == "LIMITED"


def test_nanosecond_and_unreadable_expiry(monkeypatch):
    write_auth(expires="2026-10-25T02:00:29.803441123Z")
    stub(monkeypatch)
    assert grok.usage(now=NOW, force=True)[0]["status"] == "OK"
    write_auth(expires="soon")
    row = grok.usage(now=NOW, force=True)[0]
    assert row.get("reason") == "token_expiry_unreadable" and row["status"] == "UNAVAILABLE"


def test_another_logins_cache_is_never_served(monkeypatch):
    write_auth()
    calls = stub(monkeypatch)
    grok.usage(now=NOW)
    write_auth(email="other@example.test")
    stub(monkeypatch, user=dict(USER, email="other@example.test"), credits=grok.ProbeError("endpoint_throttled"))
    row = grok.usage(now=NOW + 5)[0]
    assert row["email"] == "other@example.test" and row["status"] == "UNAVAILABLE"
    assert "lastKnown" not in row and row.get("numbersAgeSeconds") is None
    assert len(calls) == 2


def test_a_malformed_cache_is_ignored_and_the_cache_is_private(monkeypatch):
    write_auth()
    stub(monkeypatch)
    grok.usage(now=NOW)
    cache = grok._paths()[1]
    assert cache.stat().st_mode & 0o077 == 0
    cache.write_text(json.dumps({"email": EMAIL, "numbersAt": NOW, "windows": [{"usedPercent": None}]}))
    stub(monkeypatch, credits=grok.ProbeError("endpoint_throttled"))
    row = grok.usage(now=NOW + 5)[0]
    assert row["status"] == "UNAVAILABLE" and "lastKnown" not in row
    grok.format_rows([row])


def providers():
    return SimpleNamespace(StoreError=RuntimeError, fetch_all_usage=Mock(return_value=[]),
                           fetch_codex_usage=Mock(return_value=[]), gate_status=Mock(return_value=None),
                           list_accounts=Mock(return_value=[]), list_codex_accounts=Mock(return_value=[]),
                           get_claude_auth_status=Mock(return_value={}), get_codex_auth_status=Mock(return_value={}),
                           stale_numbers_note=Mock(return_value=None), load_config=Mock(return_value={}))


def run_cli(monkeypatch, args):
    assert Path(pm_cli.__file__).resolve().parent == IMPL_DIR
    monkeypatch.setattr(sys, "argv", ["provider-manager", *args])
    pm_cli.main(providers())


@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
def test_cli_usage_grok_prints_the_real_row(monkeypatch, capsys, as_json):
    write_auth()
    stub(monkeypatch)
    monkeypatch.setattr(grok.time, "time", lambda: NOW)
    run_cli(monkeypatch, ["usage", "--provider", "grok"] + (["--json"] if as_json else []))
    out = capsys.readouterr().out
    if as_json:
        assert json.loads(out)[0]["windows"][0]["usedPercent"] == 11.0
    else:
        assert "GrokPro" in out and "weekly" in out and "11%" in out and "2026-10-31 00:08" in out and " OK" in out


@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
def test_cli_usage_all_includes_grok(monkeypatch, capsys, as_json):
    write_auth()
    stub(monkeypatch)
    monkeypatch.setattr(grok.time, "time", lambda: NOW)
    monkeypatch.setattr(pm_antigravity, "accounts", Mock(return_value=[]))
    run_cli(monkeypatch, ["usage", "--provider", "all"] + (["--json"] if as_json else []))
    out = capsys.readouterr().out
    if as_json:
        assert (json.loads(out).get("grok") or [{}])[0].get("tier") == "GrokPro"
    else:
        assert "[Grok Usage]" in out and "GrokPro" in out


@pytest.mark.parametrize("command", [["balance"], ["switch", EMAIL], ["rotate"], ["login-headless"]])
def test_cli_refuses_anything_but_read_only_commands_for_grok(monkeypatch, capsys, command):
    calls = stub(monkeypatch)
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, [*command, "--provider", "grok"])
    assert calls == [] and "read-only" in capsys.readouterr().err
