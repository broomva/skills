"""Hermetic Antigravity quota contracts: no native login, network, or real credentials."""
import io
import json
import urllib.error
from pathlib import Path

import pytest
import pm_antigravity_quota as quota

pytestmark = pytest.mark.new_only
EMAIL = "person@example.test"
RT = "fake-private-refresh-grant"
AT = "fake-private-access-grant"
SECRET = "fake-private-client-secret"


@pytest.fixture
def profile(tmp_path, monkeypatch):
    # Fail any accidental outbound transport, including this module's custom opener.
    monkeypatch.setattr(quota.urllib.request.OpenerDirector, "open",
                        lambda *a, **k: pytest.fail("unmocked network transport"))
    p = tmp_path / "native-profile"
    f = p / "antigravity-acp" / "acp_token.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"client_id": "fake-client-id", "client_secret": SECRET,
                             "refresh_token": RT, "project_id": "fake-project"}))
    f.chmod(0o600)
    return p


def summary(fraction=1, identifier="gemini-weekly", **extra):
    return {"groups": [{"displayName": "Gemini Models", "buckets": [dict(
        bucketId=identifier, window="weekly", remainingFraction=fraction,
        resetTime="2026-10-25T12:00:00Z", **extra)]}]}


def stub(monkeypatch, responses=None, token=None, identity=None):
    calls = []
    def request(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/token"):
            return token if token is not None else {"access_token": AT, "expires_in": 3600}
        if url.endswith("/userinfo"):
            return identity if identity is not None else {"email": EMAIL, "verified_email": True}
        value = responses(url) if callable(responses) else responses
        if isinstance(value, Exception):
            raise value
        return value if value is not None else summary()
    monkeypatch.setattr(quota, "_request", request)
    return calls


def test_probe_merges_every_endpoint_and_never_writes_native_credentials(profile, monkeypatch):
    token_file = profile / "antigravity-acp/acp_token.json"
    before = token_file.read_bytes()
    def responses(url):
        return summary(0.3 if "daily-" in url else 0.8)
    calls = stub(monkeypatch, responses)
    result = quota.probe(profile, EMAIL)
    assert result["email"] == EMAIL and result["status"] == "ok" and result["numbersAt"]
    assert len(result["windows"]) == 1 and result["windows"][0]["usedPercent"] == pytest.approx(70)
    assert result["windows"][0]["family"] == "gemini"
    assert result["windows"][0]["kind"] == "weekly"
    assert result["windows"][0]["windowDurationMins"] == 10080
    assert calls[0][1]["form"]["grant_type"] == "refresh_token"
    assert len(calls) == 4
    assert all(kw["body"] == {"project": "fake-project"} for _, kw in calls[2:])
    assert token_file.read_bytes() == before
    serialized = json.dumps(result)
    assert all(secret not in serialized for secret in (RT, AT, SECRET))


def test_endpoint_groups_are_unioned_instead_of_stopping_at_first_success(profile, monkeypatch):
    stub(monkeypatch, lambda url: summary(1, "3p-weekly") if "daily-" in url else summary(0))
    windows = quota.probe(profile, EMAIL)["windows"]
    assert {w["family"] for w in windows} == {"third_party", "gemini"}
    assert {w["id"]: w["usedPercent"] for w in windows} == {"3p-weekly": 0, "gemini-weekly": 100}


@pytest.mark.parametrize("fraction", [None, True, False, float("nan"), float("inf"), -0.1, 1.1, "1"])
def test_unknown_or_invalid_numbers_are_not_zero(fraction):
    window = quota.parse_summary(summary(fraction))[0]
    assert window["usedPercent"] is None


@pytest.mark.parametrize("extra", [{"remainingAmount": "100"}, {"disabled": True}, {"disabled": "false"}])
def test_amount_only_and_disabled_buckets_cannot_supply_headroom(extra):
    assert quota.parse_summary(summary(**extra))[0]["usedPercent"] is None


def test_missing_window_does_not_invent_a_five_hour_cadence():
    data = {"buckets": [{"bucketId": "gemini-pool", "remainingFraction": .5,
                         "resetTime": "not-a-date"}]}
    window = quota.parse_summary(data)[0]
    assert window["kind"] == "other"
    assert "windowDurationMins" not in window and "window" not in window and "resetsAt" not in window


def test_grouped_summary_supersedes_deprecated_flat_buckets():
    data = summary(.2)
    data["buckets"] = [{"bucketId": "old", "remainingFraction": 1}]
    assert [w["id"] for w in quota.parse_summary(data)] == ["gemini-weekly"]


def test_conflicting_or_unknown_endpoint_observations_fail_closed():
    known = quota.parse_summary(summary(.7))
    unknown = quota.parse_summary(summary(None))
    disabled = quota.parse_summary(summary(.8, disabled=True))
    assert quota.merge_windows(known, unknown)[0]["usedPercent"] is None
    assert quota.merge_windows(unknown, known)[0]["usedPercent"] is None
    assert quota.merge_windows(known, disabled)[0]["disabled"] is True
    other = quota.parse_summary({"buckets": [{"bucketId": "gemini-weekly", "window": "5h", "remainingFraction": 1}]})
    assert quota.merge_windows(known, other)[0]["usedPercent"] is None


def test_endpoint_reset_disagreement_uses_later_actual_timestamp():
    first = quota.parse_summary(summary(.2))
    later = quota.parse_summary(summary(.5))
    later[0]["resetsAt"] = "2026-10-28T00:00:00Z"
    merged = quota.merge_windows(first, later)[0]
    assert merged["usedPercent"] == 80
    assert merged["resetsAt"] == "2026-10-28T00:00:00Z"


def test_models_fallback_keeps_worst_family_reading_without_inventing_duration(profile, monkeypatch):
    models = {"models": {
        "gemini-a": {"quotaInfo": {"remainingFraction": .9}},
        "gemini-b": {"quotaInfo": {"remainingFraction": .1}},
        "claude-a": {"weeklyQuotaInfo": {"remainingFraction": .6}},
    }}
    calls = stub(monkeypatch, lambda url: {} if url.endswith("retrieveUserQuotaSummary") else models)
    result = quota.probe(profile, EMAIL)
    windows = {w["id"]: w for w in result["windows"]}
    assert len(calls) == 6 and result["status"] == "ok"
    assert windows["gemini-quota"]["usedPercent"] == 90
    assert windows["gemini-quota"]["kind"] == "other" and "windowDurationMins" not in windows["gemini-quota"]
    assert windows["claude-weekly"]["windowDurationMins"] == 10080


def test_unknown_quota_produces_no_measurement_timestamp(profile, monkeypatch):
    stub(monkeypatch, {})
    result = quota.probe(profile, EMAIL)
    assert result["status"] == "unavailable" and result["numbersAt"] is None
    assert result["reason"] == "quota_unavailable"


def test_identity_mismatch_prevents_all_quota_calls(profile, monkeypatch):
    calls = stub(monkeypatch, identity={"email": "other@example.test"})
    result = quota.probe(profile, EMAIL)
    assert result["reason"] == "identity_mismatch" and len(calls) == 2
    assert "other@example.test" not in json.dumps(result)


def test_refresh_rotation_is_marked_durably_and_never_retried(profile, monkeypatch):
    token_file = profile / "antigravity-acp/acp_token.json"
    before = token_file.read_bytes()
    calls = stub(monkeypatch, token={"access_token": AT, "expires_in": 3600,
                                    "refresh_token": "replacement-secret-must-not-escape"})
    first = quota.probe(profile, EMAIL)
    second = quota.probe(profile, EMAIL)
    assert first["reason"] == second["reason"] == "auth_rotation_unsupported"
    assert len(calls) == 1 and token_file.read_bytes() == before
    marker = next((Path.home() / ".cache/broomva-provider-antigravity").iterdir())
    assert marker.stat().st_mode & 0o777 == 0o600
    assert "replacement-secret" not in json.dumps(first) + marker.read_text()
    # A newly authorized grant has a different fingerprint; the old marker remains useful.
    changed = json.loads(before)
    changed["refresh_token"] = "fresh-native-grant"
    token_file.write_text(json.dumps(changed))
    stub(monkeypatch)
    assert quota.probe(profile, EMAIL)["status"] == "ok"


def test_same_refresh_token_in_response_is_not_rotation(profile, monkeypatch):
    stub(monkeypatch, token={"access_token": AT, "expires_in": 3600, "refresh_token": RT})
    assert quota.probe(profile, EMAIL)["status"] == "ok"


def test_malformed_native_profile_makes_no_http_calls(profile, monkeypatch):
    (profile / "antigravity-acp/acp_token.json").write_text("{}")
    monkeypatch.setattr(quota, "_request", lambda *a, **k: pytest.fail("must not send invalid credentials"))
    assert quota.probe(profile, EMAIL)["reason"] == "invalid_credentials"


@pytest.mark.parametrize("status,reason", [(302, "redirect_refused"), (401, "auth_unavailable"),
                                          (403, "forbidden"), (429, "throttled"), (503, "http_unavailable")])
def test_transport_errors_disclose_no_error_body_or_credentials(monkeypatch, status, reason):
    def fail(req, timeout):
        raise urllib.error.HTTPError(req.full_url, status, RT, {}, io.BytesIO(SECRET.encode()))
    class Opener:
        open = staticmethod(fail)
    handlers = []
    monkeypatch.setattr(quota.urllib.request, "build_opener", lambda handler: handlers.append(handler) or Opener())
    with pytest.raises(quota.ProbeError) as exc:
        quota._request("https://oauth2.googleapis.com/token", form={"refresh_token": RT})
    assert str(exc.value) == reason
    assert isinstance(handlers[0], quota._NoRedirect)
    assert handlers[0].redirect_request(None, None, 302, "", {}, "https://attacker.invalid") is None


def test_transport_bounds_response_and_sets_native_headers(monkeypatch):
    seen = {}
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            seen["limit"] = limit
            return b'{}'
    class Opener:
        def open(self, request, timeout):
            seen.update(request=request, timeout=timeout)
            return Response()
    monkeypatch.setattr(quota.urllib.request, "build_opener", lambda handler: Opener())
    assert quota._request(quota.ENDPOINTS[0] + "/v1internal:retrieveUserQuotaSummary",
                          body={"project": "fake"}, access_token=AT) == {}
    assert seen["request"].get_method() == "POST"
    assert seen["request"].get_header("Authorization") == "Bearer " + AT
    assert seen["request"].get_header("Content-type") == "application/json"
    assert seen["request"].get_header("User-agent").startswith("antigravity/hub/")
    assert seen["timeout"] <= 10 and seen["limit"] == quota.MAX_RESPONSE + 1


def test_server_strings_cannot_echo_grants_into_sanitized_output(profile, monkeypatch):
    data = summary()
    data["groups"][0]["displayName"] = "Echo " + RT + " " + AT + " " + SECRET
    stub(monkeypatch, data)
    result = json.dumps(quota.probe(profile, EMAIL))
    assert all(secret not in result for secret in (RT, AT, SECRET))
