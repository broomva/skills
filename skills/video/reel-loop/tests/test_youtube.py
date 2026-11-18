"""YouTube Shorts platform mode: gates, upload boundary, token safety and stats."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

import reel_loop as rl

NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)
CHANNEL = "UC0123456789ABCDEFGHIJKL"
VIDEO_ID = "AbCdEf_1234"


def _youtube_probe(_path):
    return {"codec": "h264", "fps": 30.0, "duration": 28.0, "format": "mov,mp4",
            "width": 1080, "height": 1920}


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "short.mp4"
    path.write_bytes(b"the approved video bytes")
    return path


def youtube_card(video: Path, **over):
    card = {
        "platform": "youtube",
        "synthetic": {},
        "youtube": {"title": "A useful short", "made_for_kids": False},
        "approval": {"by": "owner", "at": "2026-11-18T09:00:00Z",
                     "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                     "platform": "youtube", "channel_id": CHANNEL,
                     "privacy_status": "private", "made_for_kids": False},
    }
    card.update(over)
    return card


def instagram_card(video: Path, **over):
    card = {
        "synthetic": {},
        "caption": "A normal Reel",
        "approval": {"by": "owner", "at": "2026-11-18T09:00:00Z",
                     "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest()},
    }
    card.update(over)
    return card


def payload(card, video, **kw):
    return rl.check_payload(card, video, card_dir=video.parent, probe=kw.pop("probe", _youtube_probe),
                            now=NOW, **kw)


class FakeGoogle:
    """A fake Google transport with a safe resumable session URI."""

    session = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=session"

    def __init__(self, *, channel=CHANNEL, location=None, resource=None, on_call=None):
        self.calls = []
        self.channel = channel
        self.location = self.session if location is None else location
        self.resource = resource or {"id": VIDEO_ID, "status": {"privacyStatus": "private",
                                                                    "uploadStatus": "uploaded"}}
        self.on_call = on_call

    def __call__(self, method, url, *, params=None, headers=None, body=None, timeout=120):
        call = {"method": method, "url": url, "params": params, "headers": headers, "body": body}
        self.calls.append(call)
        if self.on_call:
            self.on_call(len(self.calls), call)
        if url.endswith("/channels"):
            return {"status": 200, "headers": {}, "json": {"items": [{"id": self.channel}]}}
        if method == "POST" and url.endswith("/upload/youtube/v3/videos"):
            return {"status": 200, "headers": {"Location": self.location}, "json": None}
        if method == "PUT":
            return {"status": 200, "headers": {}, "json": self.resource}
        if url.endswith("/videos"):
            return {"status": 200, "headers": {}, "json": {"items": [{
                "id": VIDEO_ID,
                "status": {"privacyStatus": "unlisted", "uploadStatus": "processed"},
                "statistics": {"viewCount": "7", "likeCount": "3", "commentCount": "2"},
            }]}}
        raise AssertionError(f"unexpected fake Google request: {method} {url}")


def publish(card, video, http, **kw):
    return rl.publish_youtube(card, video, channel_id=CHANNEL, token="YT_TOKEN", http=http,
                              card_dir=video.parent, probe=kw.pop("probe", _youtube_probe), now=NOW, **kw)


def test_default_platform_is_instagram_and_unknown_platform_is_blocked(video):
    result, reasons, _ = rl.check_payload(instagram_card(video), video, card_dir=video.parent,
                                          probe=lambda _p: {"codec": "h264", "fps": 30.0,
                                                            "duration": 10.0, "format": "mp4"}, now=NOW)
    assert reasons == [] and set(result) == {"container", "sha256", "file_size"}
    blocked, reasons, _ = payload(youtube_card(video, platform="tiktok"), video)
    assert blocked is None and any("platform" in reason for reason in reasons)


@pytest.mark.parametrize("approval,needle", [
    ({"by": "owner", "at": "now", "video_sha256": "x", "channel_id": CHANNEL}, "approval.platform"),
    ({"by": "owner", "at": "now", "video_sha256": "x", "platform": "instagram", "channel_id": CHANNEL},
     "approval.platform"),
    ({"by": "owner", "at": "now", "video_sha256": "x", "platform": "youtube", "channel_id": "other"},
     "channel_id"),
])
def test_youtube_approval_binds_platform_channel_and_bytes(video, approval, needle):
    approval["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    card = youtube_card(video, approval=approval)
    result, reasons, _ = publish(card, video, FakeGoogle())
    assert result is None and any(needle in reason for reason in reasons)


def test_youtube_approval_with_wrong_sha_is_blocked(video):
    card = youtube_card(video)
    card["approval"]["video_sha256"] = "0" * 64
    result, reasons, _ = payload(card, video)
    assert result is None and any("does not match these bytes" in reason for reason in reasons)


@pytest.mark.parametrize("approval,needle", [
    ({"platform": "youtube"}, "approval.platform"),
    ({"ig_user_id": "different"}, "approval.ig_user_id"),
])
def test_instagram_optional_approval_destination_bindings_are_enforced(video, approval, needle):
    card = instagram_card(video)
    card["approval"].update(approval)
    http = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call Graph"))
    result, reasons, _ = rl.publish(card, video, ig_user_id="17841400000000000", token="IG_TOKEN", http=http,
                                    probe=lambda _p: {"codec": "h264", "fps": 30.0, "duration": 10.0,
                                                      "format": "mp4"}, card_dir=video.parent, now=NOW)
    assert result is None and any(needle in reason for reason in reasons)


@pytest.mark.parametrize("value,needle", [(None, "made_for_kids"), ("false", "made_for_kids")])
def test_made_for_kids_is_required_and_boolean(video, value, needle):
    card = youtube_card(video)
    if value is None:
        del card["youtube"]["made_for_kids"]
    else:
        card["youtube"]["made_for_kids"] = value
    result, reasons, _ = payload(card, video)
    assert result is None and any(needle in reason for reason in reasons)


def test_youtube_privacy_defaults_to_private_and_invalid_value_is_blocked(video):
    result, reasons, _ = payload(youtube_card(video), video)
    assert reasons == [] and result["platform"] == "youtube"
    assert result["insert_body"]["status"]["privacyStatus"] == "private"
    bad = youtube_card(video)
    bad["youtube"]["privacy_status"] = "friends"
    result, reasons, _ = payload(bad, video)
    assert result is None and any("privacy_status" in reason for reason in reasons)


@pytest.mark.parametrize("title", ["", "x" * 101, "bad <title>"])
def test_youtube_title_boundaries(video, title):
    card = youtube_card(video)
    card["youtube"]["title"] = title
    result, reasons, _ = payload(card, video)
    assert result is None and any("title" in reason for reason in reasons)


def test_youtube_description_and_tags_size_limits(video):
    description = youtube_card(video)
    description["youtube"]["description"] = "é" * 2501
    result, reasons, _ = payload(description, video)
    assert result is None and any("description" in reason for reason in reasons)
    tags = youtube_card(video)
    tags["youtube"]["tags"] = ["x" * 501]
    result, reasons, _ = payload(tags, video)
    assert result is None and any("tags" in reason for reason in reasons)


@pytest.mark.parametrize("probe,passes", [
    ({"duration": 20.0, "width": 1920, "height": 1080}, False),
    ({"duration": 181.0, "width": 1080, "height": 1920}, False),
    ({"duration": 20.0, "width": 1080, "height": 1080}, True),
    ({"duration": 20.0, "width": 1080, "height": 1920}, True),
])
def test_shorts_dimensions_and_duration_are_gated(video, probe, passes):
    info = {"codec": "h264", "fps": 30.0, "format": "mp4", **probe}
    result, reasons, _ = payload(youtube_card(video), video, probe=lambda _p: info)
    assert (result is not None) is passes
    assert (reasons == []) is passes


def test_youtube_declared_synthetic_forces_disclosure(video):
    card = youtube_card(video, synthetic={"generated_visuals": True})
    card["youtube"]["contains_synthetic_media"] = False
    result, reasons, notes = payload(card, video)
    assert reasons == []
    assert result["insert_body"]["status"]["containsSyntheticMedia"] is True
    assert any("forced to true" in note for note in notes)


def test_youtube_upload_sends_the_hashed_bytes_after_the_file_changes(video):
    approved = video.read_bytes()

    def swap(number, call):
        if number == 2:  # after the gate and channel check, while accepting metadata
            video.write_bytes(b"changed after the gate")

    http = FakeGoogle(on_call=swap)
    receipt, reasons, _ = publish(youtube_card(video), video, http)
    put = next(call for call in http.calls if call["method"] == "PUT")
    assert reasons == [] and put["body"] == approved
    assert receipt["sha256"] == hashlib.sha256(approved).hexdigest()
    assert video.read_bytes() != approved


def test_youtube_refuses_foreign_session_location_without_a_put(video):
    http = FakeGoogle(location="https://attacker.example/upload/youtube/v3/videos")
    with pytest.raises(rl.PublishError, match="Location"):
        publish(youtube_card(video), video, http)
    assert [call["method"] for call in http.calls] == ["GET", "POST"]


def test_youtube_channel_mismatch_uploads_nothing(video):
    http = FakeGoogle(channel="UC_NOT_THE_APPROVED_CHANNEL")
    receipt, reasons, _ = publish(youtube_card(video), video, http)
    assert receipt is None and any("channel" in reason for reason in reasons)
    assert [call["method"] for call in http.calls] == ["GET"]


def test_youtube_malformed_video_id_fails(video):
    http = FakeGoogle(resource={"id": "too-short", "status": {"privacyStatus": "private", "uploadStatus": "uploaded"}})
    with pytest.raises(rl.PublishError, match="video id"):
        publish(youtube_card(video), video, http)


def test_youtube_no_go_live_accepts_session_without_sending_bytes(video):
    http = FakeGoogle()
    receipt, reasons, _ = publish(youtube_card(video), video, http, go_live=False)
    assert reasons == [] and receipt["upload_status"] == "session_accepted"
    assert not any(call["method"] == "PUT" for call in http.calls)


def test_credentials_file_must_be_private_and_pin_its_token_endpoint(tmp_path):
    creds = tmp_path / "yt.json"
    creds.write_text(json.dumps({"client_id": "CLIENT", "client_secret": "SECRET", "refresh_token": "REFRESH"}))
    creds.chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        rl.youtube_access_token(credentials=creds, environ={})
    creds.chmod(0o600)
    creds.write_text(json.dumps({"client_id": "CLIENT", "client_secret": "SECRET", "refresh_token": "REFRESH",
                                 "token_uri": "https://attacker.example/token"}))
    with pytest.raises(ValueError, match="token_uri"):
        rl.youtube_access_token(credentials=creds, environ={})


def test_google_transport_keeps_only_google_reason_codes(monkeypatch):
    import io
    import urllib.error
    import urllib.request

    def denied(req, timeout=0):
        body = b'{"error": {"message": "server text must not escape", "errors": [{"reason": "quotaExceeded"}]}}'
        raise urllib.error.HTTPError(req.full_url, 403, "server text", {}, io.BytesIO(body))

    monkeypatch.setattr(rl, "_open", denied)
    with pytest.raises(rl.PublishError) as error:
        rl.google_http("GET", "https://www.googleapis.com/youtube/v3/channels")
    assert str(error.value) == "HTTP 403 (quotaExceeded)"


def test_youtube_secrets_are_redacted_at_the_cli_boundary(video, tmp_path, monkeypatch, capsys):
    token, refresh, secret = "YT_TOKEN_SECRET", "YT_REFRESH_SECRET", "YT_CLIENT_SECRET"
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(youtube_card(video)), encoding="utf-8")
    def access_token(**kw):
        kw["redactions"].extend([token, refresh, secret])
        return token
    monkeypatch.setattr(rl, "youtube_access_token", access_token)

    def fail(*_args, **_kw):
        raise rl.PublishError(f"failure {token} {refresh} {secret}")

    monkeypatch.setattr(rl, "publish_youtube", fail)
    assert rl.main(["publish", str(card_path), "--video", str(video), "--channel-id", CHANNEL]) == 3
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert token not in output and refresh not in output and secret not in output


def test_youtube_stats_output_shape_uses_the_read_only_endpoint(capsys, monkeypatch):
    http = FakeGoogle()
    result = rl.youtube_stats(VIDEO_ID, token="YT_TOKEN", http=http)
    assert set(result) == {"video_id", "privacy_status", "upload_status", "views", "likes", "comments"}
    assert http.calls[0]["method"] == "GET" and http.calls[0]["url"].endswith("/videos")
    monkeypatch.setattr(rl, "youtube_access_token", lambda **_kw: "YT_TOKEN")
    monkeypatch.setattr(rl, "youtube_stats", lambda *args, **kw: result)
    assert rl.main(["stats", "--platform", "youtube", "--video-id", VIDEO_ID]) == 0
    assert set(json.loads(capsys.readouterr().out)) == set(result)


def test_cli_rejects_a_wrong_destination_flag_before_token_lookup(video, tmp_path, monkeypatch, capsys):
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(youtube_card(video)), encoding="utf-8")
    monkeypatch.setattr(rl, "youtube_access_token", lambda **_kw: (_ for _ in ()).throw(AssertionError("no token lookup")))
    assert rl.main(["publish", str(card_path), "--video", str(video), "--ig-user-id", "1"]) == 2
    assert "channel-id" in capsys.readouterr().err


def test_youtube_cli_without_a_token_is_blocked(video, tmp_path, monkeypatch, capsys):
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(youtube_card(video)), encoding="utf-8")
    monkeypatch.delenv("YT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("YT_CREDENTIALS_FILE", raising=False)
    assert rl.main(["publish", str(card_path), "--video", str(video), "--channel-id", CHANNEL]) == 2
    assert "YouTube token unavailable" in capsys.readouterr().err


@pytest.mark.parametrize("tags,passes", [
    (["x" * 250, "y" * 249], True),          # 250 + 1 comma + 249 = 500
    (["x" * 250, "y" * 250], False),         # 501: the comma counts
    (["a b" + "c" * 495], True),             # 498 + 2 quotes = 500
    (["a b" + "c" * 496], False),            # 499 + 2 quotes = 501
])
def test_youtube_tags_are_counted_the_way_youtube_counts_them(video, tags, passes):
    card = youtube_card(video)
    card["youtube"]["tags"] = tags
    result, reasons, _ = payload(card, video)
    assert (result is not None) is passes, reasons


def test_redirects_are_refused_so_authorization_never_follows_one(monkeypatch):
    import urllib.request
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/channels",
                                 headers={"Authorization": "Bearer TOKEN"})
    assert rl._NoRedirect().redirect_request(req, None, 302, "Found", {}, "https://evil.example/") is None
    seen = []

    class Opener:
        def open(self, req, timeout):
            return "opened"

    def build_opener(*handlers):
        seen.extend(handlers)
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    assert rl._open(req, 5) == "opened"
    assert any(isinstance(h, rl._NoRedirect) for h in seen)


def test_cli_says_why_the_credentials_file_was_refused_without_leaking_it(video, tmp_path, monkeypatch, capsys):
    creds = tmp_path / "yt.json"
    creds.write_text(json.dumps({"client_id": "CLIENT", "client_secret": "SECRET", "refresh_token": "REFRESH"}))
    creds.chmod(0o644)
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(youtube_card(video)), encoding="utf-8")
    monkeypatch.delenv("YT_ACCESS_TOKEN", raising=False)
    assert rl.main(["publish", str(card_path), "--video", str(video), "--channel-id", CHANNEL,
                    "--credentials", str(creds)]) == 2
    err = capsys.readouterr().err
    assert "permissions must be 0600" in err
    assert "SECRET" not in err and "REFRESH" not in err


def test_google_transport_keeps_params_in_the_query_when_a_body_is_sent(monkeypatch):
    seen = {}

    class Resp:
        headers = {"Location": FakeGoogle.session}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b""

        def getcode(self):
            return 200

    def fake_open(req, timeout=0):
        seen["url"], seen["data"] = req.full_url, req.data
        return Resp()

    monkeypatch.setattr(rl, "_open", fake_open)
    rl.google_http("POST", rl.GOOGLE_UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"},
                   headers={}, body=b'{"snippet":{}}')
    assert seen["url"] == rl.GOOGLE_UPLOAD + "?uploadType=resumable&part=snippet%2Cstatus"
    assert seen["data"] == b'{"snippet":{}}'


# --- review round 1 (P20 stratum B) ------------------------------------------------
def test_the_put_goes_to_the_session_uri_google_returned(video):
    http = FakeGoogle()
    publish(youtube_card(video), video, http)
    puts = [call for call in http.calls if call["method"] == "PUT"]
    assert len(puts) == 1 and puts[0]["url"] == FakeGoogle.session
    post = next(call for call in http.calls if call["method"] == "POST")
    assert post["url"] == rl.GOOGLE_UPLOAD
    assert post["params"] == {"uploadType": "resumable", "part": "snippet,status"}
    assert http.calls[0]["url"] == "https://www.googleapis.com/youtube/v3/channels"


@pytest.mark.parametrize("location", [
    "http://www.googleapis.com/upload/youtube/v3/videos?upload_id=x",
    "https://www.googleapis.com/upload/youtube/v3/other?upload_id=x",
    "https://user@www.googleapis.com/upload/youtube/v3/videos?upload_id=x",
    "https://www.googleapis.com:8443/upload/youtube/v3/videos?upload_id=x",
    "https://www.googleapis.com.attacker.example/upload/youtube/v3/videos",
])
def test_every_part_of_the_session_uri_is_checked(video, location):
    http = FakeGoogle(location=location)
    with pytest.raises(rl.PublishError, match="Location"):
        publish(youtube_card(video), video, http)
    assert not any(call["method"] == "PUT" for call in http.calls)


def test_a_failed_put_is_reported_and_never_retried(video):
    def fail_put(number, call):
        if call["method"] == "PUT":
            raise rl.PublishError("HTTP 503")
    http = FakeGoogle(on_call=fail_put)
    with pytest.raises(rl.PublishError, match="upload: HTTP 503"):
        publish(youtube_card(video), video, http)
    assert sum(call["method"] == "PUT" for call in http.calls) == 1


def _creds(tmp_path, **extra):
    path = tmp_path / "yt.json"
    path.write_text(json.dumps({"client_id": "CLIENT", "client_secret": "ClientSecretValue",
                                "refresh_token": "RefreshSecretValue", **extra}))
    path.chmod(0o600)
    return path


def test_refresh_posts_only_to_the_pinned_endpoint_with_a_refresh_grant(tmp_path):
    import urllib.parse
    calls = []

    def http(method, url, *, params=None, headers=None, body=None, timeout=120):
        calls.append((method, url, headers, body))
        return {"status": 200, "headers": {}, "json": {"access_token": "AccessTokenValue"}}

    redactions = []
    token = rl.youtube_access_token(credentials=_creds(tmp_path), environ={}, http=http, redactions=redactions)
    assert token == "AccessTokenValue"
    method, url, headers, body = calls[0]
    assert (method, url) == ("POST", "https://oauth2.googleapis.com/token")
    form = urllib.parse.parse_qs(body.decode())
    assert form == {"grant_type": ["refresh_token"], "client_id": ["CLIENT"],
                    "client_secret": ["ClientSecretValue"], "refresh_token": ["RefreshSecretValue"]}
    assert {"ClientSecretValue", "RefreshSecretValue", "AccessTokenValue"} <= set(redactions)


def test_explicit_credentials_win_over_an_inherited_access_token(tmp_path):
    calls = []

    def http(method, url, **kw):
        calls.append(url)
        return {"status": 200, "headers": {}, "json": {"access_token": "FromTheFile"}}

    token = rl.youtube_access_token(credentials=_creds(tmp_path), environ={"YT_ACCESS_TOKEN": "Inherited"}, http=http)
    assert token == "FromTheFile" and calls == [rl.GOOGLE_TOKEN_URI]
    assert rl.youtube_access_token(environ={"YT_ACCESS_TOKEN": "Inherited"}, http=http) == "Inherited"


def test_a_symlinked_credentials_file_is_refused(tmp_path):
    real = _creds(tmp_path)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        rl.youtube_access_token(credentials=link, environ={})


def test_a_credentials_file_owned_by_someone_else_is_refused(tmp_path, monkeypatch):
    path = _creds(tmp_path)
    monkeypatch.setattr(rl.os, "getuid", lambda: os.stat(path).st_uid + 1)
    with pytest.raises(ValueError, match="owned by the current user"):
        rl.youtube_access_token(credentials=path, environ={})


def test_a_directory_is_not_a_credentials_file(tmp_path):
    d = tmp_path / "dir.json"
    d.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="regular file"):
        rl.youtube_access_token(credentials=d, environ={})


def test_secrets_echoed_by_the_token_endpoint_never_reach_the_cli(video, tmp_path, monkeypatch, capsys):
    import io
    import urllib.error

    def echo(req, timeout=0):
        body = json.dumps({"error": {"errors": [{"reason": "RefreshSecretValue"}, {"reason": "ClientSecretValue"}]}})
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(body.encode()))

    monkeypatch.setattr(rl, "_open", echo)
    monkeypatch.delenv("YT_ACCESS_TOKEN", raising=False)
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(youtube_card(video)), encoding="utf-8")
    creds = _creds(tmp_path)
    assert rl.main(["publish", str(card_path), "--video", str(video), "--channel-id", CHANNEL,
                    "--credentials", str(creds)]) == 2
    assert rl.main(["stats", "--platform", "youtube", "--video-id", VIDEO_ID, "--credentials", str(creds)]) == 3
    out = capsys.readouterr()
    text = out.out + out.err
    assert "RefreshSecretValue" not in text and "ClientSecretValue" not in text
    assert "<redacted>" in text


@pytest.mark.parametrize("command", ["publish", "stats"])
def test_unexpected_exceptions_print_only_their_type(video, tmp_path, monkeypatch, capsys, command):
    secret = "AccessTokenValue"
    monkeypatch.setattr(rl, "youtube_access_token", lambda **_kw: secret)

    def boom(*_a, **_kw):
        raise RuntimeError(f"leak {secret}")

    monkeypatch.setattr(rl, "publish_youtube", boom)
    monkeypatch.setattr(rl, "youtube_stats", boom)
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(youtube_card(video)), encoding="utf-8")
    argv = (["publish", str(card_path), "--video", str(video), "--channel-id", CHANNEL] if command == "publish"
            else ["stats", "--platform", "youtube", "--video-id", VIDEO_ID])
    assert rl.main(argv) == 3
    err = capsys.readouterr().err
    assert secret not in err and "unexpected RuntimeError" in err


def test_transport_failures_carry_no_upstream_text(monkeypatch):
    import urllib.error

    def refused(req, timeout=0):
        raise urllib.error.URLError("AccessTokenValue in a proxy message")

    monkeypatch.setattr(rl, "_open", refused)
    with pytest.raises(rl.PublishError) as exc:
        rl.google_http("GET", "https://www.googleapis.com/youtube/v3/channels")
    assert "AccessTokenValue" not in str(exc.value)

    def raising_http(*_a, **_kw):
        raise RuntimeError("AccessTokenValue")

    with pytest.raises(rl.PublishError) as exc:
        rl._google_call("channel check", "GET", "https://www.googleapis.com/youtube/v3/channels", http=raising_http)
    assert "AccessTokenValue" not in str(exc.value) and "RuntimeError" in str(exc.value)


@pytest.mark.parametrize("stream,expect", [
    ({"width": 1080, "height": 1920, "side_data_list": [{"rotation": -90}]}, (1920, 1080)),
    ({"width": 1080, "height": 1920, "tags": {"rotate": "90"}}, (1920, 1080)),
    ({"width": 1080, "height": 1920, "side_data_list": [{"rotation": 180}]}, (1080, 1920)),
    ({"width": 1080, "height": 1920}, (1080, 1920)),
])
def test_probe_reports_displayed_dimensions(monkeypatch, tmp_path, stream, expect):
    import subprocess
    stream = {"codec_name": "h264", "avg_frame_rate": "30/1", **stream}
    out = json.dumps({"streams": [stream], "format": {"duration": "20.0", "format_name": "mp4"}})
    monkeypatch.setattr(rl.shutil, "which", lambda _n: "/usr/bin/ffprobe")
    monkeypatch.setattr(rl.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out, stderr=""))
    info = rl.probe_video(tmp_path / "x.mp4")
    assert (info["width"], info["height"]) == expect


def test_an_instagram_approval_cannot_name_a_youtube_channel(video):
    card = instagram_card(video)
    card["approval"]["channel_id"] = CHANNEL
    result, reasons, _ = rl.check_payload(card, video, card_dir=video.parent, probe=_youtube_probe, now=NOW)
    assert result is None and any("channel_id" in r for r in reasons)


@pytest.mark.parametrize("field,card_value,approved", [
    ("privacy_status", "public", "private"),
    ("privacy_status", "unlisted", None),
    ("made_for_kids", True, False),
])
def test_the_approval_names_visibility_and_audience(video, field, card_value, approved):
    card = youtube_card(video)
    card["youtube"][field] = card_value
    if approved is None:
        del card["approval"][field]
    else:
        card["approval"][field] = approved
    result, reasons, _ = payload(card, video)
    assert result is None and any(f"approval.{field}" in r for r in reasons)
    card["approval"][field] = card_value
    result, reasons, _ = payload(card, video)
    assert result is not None, reasons


@pytest.mark.parametrize("change,needle", [
    ({"title": "   "}, "title"),
    ({"category_id": "22a"}, "category_id"),
    ({"description": "see <this>"}, "description"),
])
def test_more_metadata_rules(video, change, needle):
    card = youtube_card(video)
    card["youtube"].update(change)
    result, reasons, _ = payload(card, video)
    assert result is None and any(needle in r for r in reasons)


def test_each_publisher_refuses_the_other_platforms_card(video):
    receipt, reasons, _ = rl.publish(youtube_card(video), video, ig_user_id="17841400000000000", token="T",
                                     card_dir=video.parent, probe=_youtube_probe, now=NOW,
                                     http=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert receipt is None and any("YouTube card" in r for r in reasons)
    http = FakeGoogle()
    receipt, reasons, _ = publish(instagram_card(video), video, http)
    assert receipt is None and any("Instagram card" in r for r in reasons) and http.calls == []


def test_made_for_kids_absent_everywhere_is_still_blocked(video):
    card = youtube_card(video)
    del card["youtube"]["made_for_kids"]
    del card["approval"]["made_for_kids"]
    result, reasons, _ = payload(card, video)
    assert result is None and any("youtube.made_for_kids is required" in r for r in reasons)
