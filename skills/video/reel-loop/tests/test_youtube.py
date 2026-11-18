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
                     "platform": "youtube", "channel_id": CHANNEL},
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
