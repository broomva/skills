"""Tests for reel_loop: count parsing, outlier and winner scoring, and the publish gate.

Each gate test pairs a passing card with a card that differs in exactly one
field, so deleting a check makes a test fail (a mutation-style control).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import reel_loop as rl

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "reel_loop.py"
EXAMPLE = SKILL / "references" / "example-niche.tsv"
NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


# --- parse_count --------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("12,3 mil", 12300), ("1,2 M", 1200000), ("12.3K", 12300), ("8.400", 8400),
    ("104 mil", 104000), ("2,214,507", 2214507), ("930", 930), ("1.1M", 1100000),
    ("2,1 mil", 2100), ("1 234", 1234), ("3 millones", 3000000), (" 15k ", 15000),
])
def test_parse_count(text, expected):
    assert rl.parse_count(text) == expected


@pytest.mark.parametrize("bad", ["", "lots", "12 zillion", None])
def test_parse_count_rejects(bad):
    with pytest.raises(ValueError):
        rl.parse_count(bad)


# --- outliers -----------------------------------------------------------------
def _outliers(**kw):
    args = dict(bar=4.0, min_views=20000, max_age_days=45, min_sample=5, now=NOW)
    args.update(kw)
    return rl.score_outliers(rl.read_rows(str(EXAMPLE)), **args)


def test_example_finds_the_small_account_breakout_not_the_big_account():
    res = _outliers()
    urls = [r["url"] for r in res["outliers"]]
    assert urls == ["https://www.instagram.com/p/A6/"]
    a6 = res["outliers"][0]
    assert a6["baseline"] == 10500           # median of A1..A5, A6 excluded
    assert a6["ratio"] == pytest.approx(1200000 / 10500, rel=1e-3)
    # @beta's 2.6M reel is the biggest number in the file and is NOT an outlier.
    b6 = next(r for r in res["skipped"] if r["url"].endswith("/B6/"))
    assert "ratio" in b6["reason"]


def test_leave_one_out_baseline_differs_from_inclusive_median():
    # Inclusive median of @alpha = median(12300, 9800, 11000, 10500, 8900, 1200000) = 10750.
    # Leave-one-out for A6 = median(12300, 9800, 11000, 10500, 8900) = 10500.
    res = _outliers()
    assert res["accounts"]["alpha"]["median"] == 10750
    assert res["outliers"][0]["baseline"] == 10500


def test_low_sample_account_never_passes():
    res = _outliers(min_views=0, bar=1.0)
    gamma = [r for r in res["skipped"] if r["account"] == "gamma"]
    assert len(gamma) == 2 and all("low sample" in r["reason"] for r in gamma)
    assert res["accounts"]["gamma"]["low_sample"] is True


def test_min_views_and_age_filters():
    assert _outliers(min_views=2_000_000)["outliers"] == []
    old_now = NOW + timedelta(days=60)
    res = _outliers(now=old_now)
    assert res["outliers"] == []
    assert any("age" in r["reason"] for r in res["skipped"] if r["url"].endswith("/A6/"))


def test_bad_rows_are_reported_not_dropped(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("account,url,views\n@a,u1,lots\n,u2,10\n", encoding="utf-8")
    res = rl.score_outliers(rl.read_rows(str(f)), bar=4, min_views=0, max_age_days=None, min_sample=1, now=NOW)
    assert len(res["errors"]) == 2


def test_duplicate_urls_count_once(tmp_path):
    rows = [{"account": "a", "url": "u", "views": "100"}] * 3
    res = rl.score_outliers(rows, bar=1, min_views=0, max_age_days=None, min_sample=0, now=NOW)
    assert res["accounts"]["a"]["reels"] == 1


def test_json_input(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps([{"Account": "@a", "URL": "u1", "Views": 5}]), encoding="utf-8")
    assert rl.read_rows(str(f))[0]["account"] == "@a"


# --- winners ------------------------------------------------------------------
def _posts(views_by_day_ago, trial_days=()):
    rows = []
    for days_ago, v in views_by_day_ago:
        rows.append({"id": f"p{days_ago}", "published_at": (NOW - timedelta(days=days_ago)).isoformat(),
                     "views": str(v), "is_trial": "true" if days_ago in trial_days else ""})
    return rows


def _winners(rows, **kw):
    args = dict(bar=2.0, window_days=30, min_age_hours=48, min_sample=5, graduation="SS_PERFORMANCE", now=NOW)
    args.update(kw)
    return rl.score_winners(rows, **args)


def test_winner_gets_three_trial_variants():
    rows = _posts([(20, 1000), (18, 1100), (15, 900), (12, 1000), (10, 1050), (5, 5000)])
    res = _winners(rows)
    assert [w["id"] for w in res["winners"]] == ["p5"]
    variants = res["winners"][0]["variants"]
    assert [v["axis"] for v in variants] == ["hook", "color", "framing"]
    assert all(v["trial_params"] == {"graduation_strategy": "SS_PERFORMANCE"} for v in variants)


def test_post_younger_than_48h_is_pending_not_judged():
    rows = _posts([(20, 1000), (18, 1100), (15, 900), (12, 1000), (10, 1050), (1, 50000)])
    res = _winners(rows)
    assert res["winners"] == []
    assert res["pending"][0]["id"] == "p1"


def test_trial_posts_are_not_in_the_baseline():
    # Six trial posts outnumber the five normal ones, so if they were counted the
    # median would be 90,000 and p5 (5,000) could not win.
    trials = (9, 8, 7, 6, 5.5, 5.2)
    rows = _posts([(20, 1000), (18, 1100), (15, 900), (12, 1000), (10, 1050)]
                  + [(d, 90000) for d in trials] + [(5, 5000)], trial_days=trials)
    res = _winners(rows)
    assert "p5" in [w["id"] for w in res["winners"]]


def test_bad_graduation_strategy_rejected():
    with pytest.raises(ValueError):
        _winners(_posts([(5, 1)]), graduation="AUTO")


# --- payload gate ---------------------------------------------------------------
def _ok_probe(_path):
    return {"codec": "h264", "fps": 30.0, "duration": 28.0, "format": "mov,mp4"}


@pytest.fixture
def video(tmp_path):
    v = tmp_path / "final.mp4"
    v.write_bytes(b"not really a video, the probe is stubbed")
    (tmp_path / "consent").mkdir()
    (tmp_path / "consent" / "voice.md").write_text("I consent. — the creator, 2026-11-16\n", encoding="utf-8")
    return v


def _card(video: Path, **over):
    card = {
        "account": "lab",
        "caption": "Mi agente trabaja mientras duermo #ia",
        "synthetic": {"voice_clone": True, "generated_visuals": True},
        "voice_consent": {"speaker": "the creator", "date": "2026-11-16", "ref": "consent/voice.md"},
        "trial": None,
        "approval": {"by": "owner", "at": "2026-11-16T09:00:00Z",
                     "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest()},
    }
    card.update(over)
    return card


def _gate(card, video, **kw):
    kw.setdefault("probe", _ok_probe)
    kw.setdefault("card_dir", video.parent)
    kw.setdefault("now", NOW)
    return rl.check_payload(card, video, **kw)


def test_dry_run_passes_and_names_no_file(video):
    payload, reasons, _ = _gate(_card(video, is_ai_generated=False), video)
    assert reasons == []
    c = payload["container"]
    assert c["is_ai_generated"] is True and c["media_type"] == "REELS" and c["upload_type"] == "resumable"
    assert payload["sha256"] == hashlib.sha256(video.read_bytes()).hexdigest()
    assert payload["file_size"] == video.stat().st_size
    assert set(payload) == {"container", "sha256", "file_size"}  # no path to upload by hand
    assert "trial_params" not in c


def test_gate_blocks_without_approval(video):
    payload, reasons, _ = _gate(_card(video, approval=None), video)
    assert payload is None and any("no approval" in r for r in reasons)


def test_gate_blocks_when_video_changed_after_approval(video):
    card = _card(video)
    video.write_bytes(b"re-rendered after approval")
    payload, reasons, _ = _gate(card, video)
    assert payload is None and any("does not match these bytes" in r for r in reasons)


# Review r1 BLOCKER 3: consent must be real evidence, not two strings.
@pytest.mark.parametrize("consent,needle", [
    (None, "without voice_consent"),
    ({"speaker": "the creator", "date": "NOT_A_DATE", "ref": "consent/voice.md"}, "ISO date"),
    ({"speaker": "the creator", "date": "2027-01-01", "ref": "consent/voice.md"}, "future"),
    ({"speaker": "the creator", "date": "2026-11-16", "ref": "missing.md"}, "does not exist"),
    ({"speaker": "the creator", "date": "2026-11-16"}, "ref must point"),
    ({"speaker": "", "date": "2026-11-16", "ref": "consent/voice.md"}, "speaker"),
])
def test_gate_blocks_weak_consent(video, consent, needle):
    payload, reasons, _ = _gate(_card(video, voice_consent=consent), video)
    assert payload is None and any(needle in r for r in reasons), reasons


def test_no_consent_needed_without_a_cloned_voice(video):
    card = _card(video, voice_consent=None, synthetic={"voice_clone": False, "generated_visuals": False})
    payload, reasons, _ = _gate(card, video)
    assert reasons == [] and payload["container"]["is_ai_generated"] is False


# Review r1 MAJOR 4: an explicit true disclosure is never dropped.
def test_explicit_ai_disclosure_is_kept(video):
    card = _card(video, voice_consent=None, synthetic={}, is_ai_generated=True)
    payload, reasons, _ = _gate(card, video)
    assert reasons == [] and payload["container"]["is_ai_generated"] is True


# Review r1 BLOCKER 1: malformed cards block, never crash and never pass.
@pytest.mark.parametrize("over,needle", [
    ({"approval": "yes"}, "approval must be an object"),
    ({"approval": {"by": "owner", "at": "now"}}, "approval.video_sha256"),
    ({"synthetic": []}, "synthetic must be an object"),
    ({"synthetic": {"voice_clone": "yes"}}, "synthetic must be an object"),
    ({"voice_consent": "yes"}, "voice_consent must be an object"),
    ({"trial": "SS_PERFORMANCE"}, "trial must be an object"),
    ({"caption": 12345}, "caption must be str"),
    ({"is_ai_generated": "true"}, "is_ai_generated must be bool"),
    ({"share_to_feed": "yes"}, "share_to_feed must be bool"),
    ({"thumb_offset": True}, "thumb_offset must be int"),
    ({"collaborators": ["a", "b", "c", "d"]}, "collaborators"),
])
def test_malformed_card_is_blocked(video, over, needle):
    payload, reasons, _ = _gate(_card(video, **over), video)
    assert payload is None and any(needle in r for r in reasons), reasons


def test_non_object_card_is_blocked(video):
    payload, reasons, _ = _gate(["not", "a", "card"], video)
    assert payload is None and "JSON object" in reasons[0]


@pytest.mark.parametrize("caption,needle", [
    ("x" * 2201, "chars"),
    (" ".join(f"#t{i}" for i in range(31)), "hashtags"),
    (" ".join(f"@u{i}" for i in range(21)), "@ tags"),
])
def test_gate_enforces_caption_limits(video, caption, needle):
    payload, reasons, _ = _gate(_card(video, caption=caption), video)
    assert payload is None and any(needle in r for r in reasons)


def test_caption_at_the_limits_passes(video):
    cap = " ".join(f"#t{i}" for i in range(30)) + " " + " ".join(f"@u{i}" for i in range(20))
    payload, reasons, _ = _gate(_card(video, caption=cap), video)
    assert reasons == []


def test_trial_params_passed_through_and_validated(video):
    payload, _, _ = _gate(_card(video, trial={"graduation_strategy": "SS_PERFORMANCE"}), video)
    assert payload["container"]["trial_params"] == {"graduation_strategy": "SS_PERFORMANCE"}
    payload, reasons, _ = _gate(_card(video, trial={"graduation_strategy": "AUTO"}), video)
    assert payload is None and any("graduation_strategy" in r for r in reasons)


@pytest.mark.parametrize("probe,needle", [
    ({"codec": "vp9", "fps": 30.0, "duration": 20.0, "format": "webm"}, "codec"),
    ({"codec": "h264", "fps": 15.0, "duration": 20.0, "format": "mp4"}, "frame rate"),
    ({"codec": "h264", "fps": 30.0, "duration": 2.0, "format": "mp4"}, "duration"),
    ({"codec": "h264", "fps": 30.0, "duration": 901.0, "format": "mp4"}, "duration"),
    ({"error": "moov atom not found"}, "ffprobe"),
])
def test_gate_enforces_reel_spec(video, probe, needle):
    payload, reasons, _ = _gate(_card(video), video, probe=lambda _p: probe)
    assert payload is None and any(needle in r for r in reasons)


# Review r1 MINOR 5: the 300 MB limit had no test.
def test_oversized_video_is_blocked(tmp_path):
    big = tmp_path / "big.mp4"
    with big.open("wb") as f:
        f.truncate(rl.REEL_MAX_BYTES + 1)  # sparse: no 300 MB written to disk
    card = {"approval": {"by": "o", "at": "t", "video_sha256": "x"}, "synthetic": {}}
    payload, reasons, _ = _gate(card, big)
    assert payload is None and "300 MB" in reasons[0]


def test_missing_ffprobe_is_unchecked_not_green(video):
    payload, reasons, notes = _gate(_card(video), video, probe=lambda _p: None)
    assert payload is not None
    assert any(n.startswith("UNCHECKED") for n in notes)


def test_container_holds_only_graph_api_fields(video):
    payload, _, notes = _gate(_card(video, cover_url="https://x/c.jpg"), video)
    allowed = {"media_type", "upload_type", "caption", "is_ai_generated", "share_to_feed",
               "trial_params", "cover_url", "thumb_offset", "audio_name", "collaborators"}
    assert set(payload["container"]) <= allowed
    assert any(n.startswith("gate passed: sha256 ") for n in notes)


# --- CLI ------------------------------------------------------------------------
def test_cli_outliers_runs_on_the_example():
    out = subprocess.run([sys.executable, str(SCRIPT), "outliers", str(EXAMPLE), "--now", "2026-11-16"],
                         capture_output=True, text=True, check=True).stdout
    assert "@alpha" in out and "/p/A6/" in out and "/p/B6/" not in out


@pytest.mark.parametrize("card_text", ['{"approval": "yes"}', "not json", "[]"])
def test_cli_payload_exit_2_on_bad_cards(tmp_path, video, card_text):
    card = tmp_path / "card.json"
    card.write_text(card_text, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), "payload", str(card), "--video", str(video)],
                          capture_output=True, text=True)
    assert proc.returncode == 2 and "BLOCKED" in proc.stderr and proc.stdout == ""
    assert "Traceback" not in proc.stderr


def test_cli_payload_passes_with_consent_resolved_next_to_the_card(tmp_path, video):
    card = tmp_path / "card.json"
    card.write_text(json.dumps(_card(video)), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), "payload", str(card), "--video", str(video)],
                          capture_output=True, text=True)
    # ffprobe may be absent (UNCHECKED note) or present and reject the fake bytes; both are honest.
    if proc.returncode == 0:
        assert json.loads(proc.stdout)["sha256"] == hashlib.sha256(video.read_bytes()).hexdigest()
    else:
        assert proc.returncode == 2 and "ffprobe could not read" in proc.stderr


# --- review r2: file edge cases ----------------------------------------------------
def test_empty_video_is_blocked(video):
    card = _card(video)
    video.write_bytes(b"")
    payload, reasons, _ = _gate(card, video)
    assert payload is None and reasons == ["video is empty"]


def test_directory_as_video_is_blocked(video, tmp_path):
    payload, reasons, _ = _gate(_card(video), tmp_path)
    assert payload is None and "not a regular file" in reasons[0]


def test_missing_video_is_blocked(video, tmp_path):
    payload, reasons, _ = _gate(_card(video), tmp_path / "nope.mp4")
    assert payload is None and "cannot be read" in reasons[0]


def test_null_share_to_feed_gets_the_default(video):
    payload, reasons, _ = _gate(_card(video, share_to_feed=None), video)
    assert reasons == [] and payload["container"]["share_to_feed"] is True


# --- review r2 BLOCKER: publish sends the gated bytes, whatever happens to the file --
class FakeGraph:
    """Records every call; answers like the Graph API and rupload."""

    def __init__(self, on_call=None, status=("IN_PROGRESS", "FINISHED")):
        self.calls, self.on_call, self.status = [], on_call, list(status)

    def __call__(self, method, url, *, params=None, headers=None, body=None, timeout=300):
        self.calls.append({"method": method, "url": url, "params": params, "headers": headers, "body": body})
        if self.on_call:
            self.on_call(len(self.calls), url)
        if url.endswith("/media"):
            return {"id": "170001"}
        if "rupload" in url:
            return {"success": True}
        if url.endswith("/media_publish"):
            return {"id": "180002"}
        return {"status_code": self.status.pop(0) if self.status else "FINISHED"}


def _publish(card, video, http, **kw):
    kw.setdefault("probe", _ok_probe)
    kw.setdefault("card_dir", video.parent)
    kw.setdefault("now", NOW)
    return rl.publish(card, video, ig_user_id="17841400000000000", token="TOKEN", http=http,
                      sleep=lambda _s: None, **kw)


def test_publish_runs_the_documented_sequence(video):
    http = FakeGraph()
    receipt, reasons, _ = _publish(_card(video, trial={"graduation_strategy": "SS_PERFORMANCE"}), video, http)
    assert reasons == [] and receipt["media_id"] == "180002" and receipt["container_id"] == "170001"
    create, upload = http.calls[0], http.calls[1]
    assert create["url"].endswith("/17841400000000000/media")
    assert create["params"]["upload_type"] == "resumable" and create["params"]["media_type"] == "REELS"
    assert create["params"]["is_ai_generated"] == "true"
    assert json.loads(create["params"]["trial_params"]) == {"graduation_strategy": "SS_PERFORMANCE"}
    assert "TOKEN" not in create["url"] and "TOKEN" not in json.dumps(create["params"])
    assert create["headers"] == {"Authorization": "Bearer TOKEN"}
    assert upload["url"].endswith("/ig-api-upload/v27.0/170001")
    assert upload["headers"] == {"Authorization": "OAuth TOKEN", "offset": "0", "file_size": str(len(upload["body"]))}
    assert http.calls[-1]["url"].endswith("/media_publish") and http.calls[-1]["params"] == {"creation_id": "170001"}
    assert http.calls[-1]["headers"] == {"Authorization": "Bearer TOKEN"}


def test_publish_sends_the_approved_bytes_even_if_the_file_is_swapped(video):
    approved = video.read_bytes()

    def swap(n, _url):  # after the gate, before the upload: replace the file, same length
        if n == 1:
            video.write_bytes(b"X" * len(approved))

    http = FakeGraph(on_call=swap)
    receipt, reasons, _ = _publish(_card(video), video, http)
    sent = next(c["body"] for c in http.calls if "rupload" in c["url"])
    assert sent == approved
    assert receipt["sha256"] == hashlib.sha256(approved).hexdigest()
    assert video.read_bytes() != approved  # the swap really happened


def test_publish_blocked_card_makes_no_api_call(video):
    http = FakeGraph()
    receipt, reasons, _ = _publish(_card(video, approval=None), video, http)
    assert receipt is None and http.calls == []


def test_publish_no_go_live_stops_before_media_publish(video):
    http = FakeGraph()
    receipt, _, _ = _publish(_card(video), video, http, go_live=False)
    assert "media_id" not in receipt and not any(c["url"].endswith("/media_publish") for c in http.calls)


class FakeClock:
    """Monotonic clock that advances on sleep and by `per_call` seconds per API call."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


@pytest.mark.parametrize("status,needle", [(("ERROR",), "status ERROR"), (("IN_PROGRESS",) * 20, "not FINISHED within 300")])
def test_publish_container_failure_raises(video, status, needle):
    clock = FakeClock()
    with pytest.raises(rl.PublishError, match=needle):
        rl.publish(_card(video), video, ig_user_id="1", token="TOKEN", http=FakeGraph(status=status),
                   probe=_ok_probe, card_dir=video.parent, now=NOW, sleep=clock.sleep, clock=clock)


# Review r3 MINOR: requests count against Meta's 5-minute window, not just sleeps.
def test_publish_deadline_counts_slow_requests(video):
    clock = FakeClock()

    def slow(n, _url):  # every API call takes 70 s
        clock.t += 70

    graph = FakeGraph(on_call=slow, status=("IN_PROGRESS",) * 20)
    http_calls = graph.calls
    with pytest.raises(rl.PublishError, match="not FINISHED within 300"):
        rl.publish(_card(video), video, ig_user_id="1", token="TOKEN",
                   http=graph,
                   probe=_ok_probe, card_dir=video.parent, now=NOW, sleep=clock.sleep, clock=clock)
    # create + upload took 140 s; polling then stops within its 300 s window, overrunning by at most
    # one request (70 s). Before the fix it ran five full cycles regardless: 590 s in total.
    assert clock.t <= 140 + 300 + 70
    polls = [c for c in http_calls if c["method"] == "GET"]
    assert len(polls) == 3


# Review r3 MAJOR + r4: the token never reaches a URL, an exception, its chain or the CLI's output.
SENTINEL = "P20_FAKE_SECRET_SENTINEL"


def _fragments(s: str, n: int = 8):
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _assert_no_sentinel(exc_or_text):
    """No 8-character fragment of the sentinel anywhere: in the message, or in any
    exception chained to it (__cause__ / __context__)."""
    texts, e, seen = [], exc_or_text, set()
    if isinstance(e, BaseException):
        while e is not None and id(e) not in seen:
            seen.add(id(e))
            texts += [str(e), repr(e)]
            e = e.__cause__ or e.__context__
    else:
        texts.append(str(e))
    blob = " ".join(texts)
    assert not any(f in blob for f in _fragments(SENTINEL)), blob


def test_real_transport_puts_no_token_in_any_url(video, monkeypatch):
    import io
    import urllib.request
    seen = []
    replies = iter([b'{"id": "170003"}', b'{"success": true}', b'{"status_code": "FINISHED"}', b'{"id": "180004"}'])

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen.append((req.full_url, dict(req.header_items()), req.data))
        return Resp(next(replies))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    receipt, _, _ = rl.publish(_card(video), video, ig_user_id="1", token=SENTINEL, probe=_ok_probe,
                               card_dir=video.parent, now=NOW, sleep=lambda s: None)
    assert receipt["media_id"] == "180004" and len(seen) == 4
    assert all(SENTINEL not in url for url, _, _ in seen)
    # the token is never in a form body either (the upload body is the video itself)
    assert all(SENTINEL.encode() not in (body or b"") for _, _, body in (seen[0], seen[2], seen[3]))
    poll_url, poll_headers, _ = seen[2]
    assert "fields=status_code" in poll_url and poll_headers.get("Authorization") == f"Bearer {SENTINEL}"
    assert seen[1][1].get("Authorization") == f"OAuth {SENTINEL}"


@pytest.mark.parametrize("failure", ["http_error", "url_error", "dump"])
def test_errors_are_redacted(video, monkeypatch, failure):
    import io
    import urllib.error
    import urllib.request

    def fake_urlopen(req, timeout=0):
        if failure == "http_error":
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(f'{{"error": "{SENTINEL} invalid"}}'.encode()))
        if failure == "url_error":
            raise urllib.error.URLError(f"proxy said {SENTINEL}")

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return Resp(f'{{"echo": "{SENTINEL}"}}'.encode())  # no id: before r3 the reply was dumped into the error

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(rl.PublishError) as info:
        rl.publish(_card(video), video, ig_user_id="1", token=SENTINEL, probe=_ok_probe,
                   card_dir=video.parent, now=NOW, sleep=lambda s: None)
    _assert_no_sentinel(info.value)


# Review r3 MINOR: malformed replies fail as PublishError (exit 3), never crash or pass.
@pytest.mark.parametrize("raw", [b"not json", b"[]", b"null"])
def test_non_object_replies_raise_publish_error(raw, monkeypatch):
    import io
    import urllib.request

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: Resp(raw))
    with pytest.raises(rl.PublishError):
        rl.graph_http("POST", "https://graph.facebook.com/v27.0/1/media", params={"a": "b"})


def test_upload_success_must_be_boolean_true(video):
    class Stringy(FakeGraph):
        def __call__(self, method, url, **kw):
            out = super().__call__(method, url, **kw)
            return {"success": "false"} if "rupload" in url else out

    http = Stringy()
    with pytest.raises(rl.PublishError, match="did not report success: true"):
        _publish(_card(video), video, http)
    assert not any(c["url"].endswith("/media_publish") for c in http.calls)


def test_cli_publish_failure_exits_3_without_the_token(tmp_path, video):
    card = tmp_path / "card.json"
    card.write_text(json.dumps(_card(video)), encoding="utf-8")
    env = {**__import__("os").environ, "IG_ACCESS_TOKEN": SENTINEL, "https_proxy": "http://127.0.0.1:9",
           "HTTPS_PROXY": "http://127.0.0.1:9"}
    proc = subprocess.run([sys.executable, str(SCRIPT), "publish", str(card), "--video", str(video),
                           "--ig-user-id", "1"], capture_output=True, text=True, env=env, timeout=60)
    if proc.returncode == 2:  # ffprobe present and rejected the fake bytes: the gate blocked first
        assert "ffprobe could not read" in proc.stderr
    else:
        assert proc.returncode == 3 and "PUBLISH FAILED" in proc.stderr
    assert SENTINEL not in proc.stderr + proc.stdout


def test_cli_publish_without_token_is_blocked(tmp_path, video):
    card = tmp_path / "card.json"
    card.write_text(json.dumps(_card(video)), encoding="utf-8")
    env = {k: v for k, v in __import__("os").environ.items() if k != "IG_ACCESS_TOKEN"}
    proc = subprocess.run([sys.executable, str(SCRIPT), "publish", str(card), "--video", str(video),
                           "--ig-user-id", "1"], capture_output=True, text=True, env=env)
    assert proc.returncode == 2 and "IG_ACCESS_TOKEN" in proc.stderr


# --- review r4 ---------------------------------------------------------------------
class _Resp(__import__("io").BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("raw_body", [
    lambda: ("x" * (500 - len(SENTINEL) + 1) + SENTINEL).encode(),           # straddles the old 500 cut
    lambda: ('{"error": {"message": "' + SENTINEL + '", "code": 190, "error_subcode": 463}}').encode(),
])
def test_http_error_text_never_reaches_the_message(monkeypatch, raw_body):
    import io
    import urllib.error
    import urllib.request

    def fake(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 400, SENTINEL, {}, io.BytesIO(raw_body()))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(rl.PublishError) as info:
        rl.graph_http("GET", "https://graph.facebook.com/v27.0/1", params={"fields": "status_code"})
    _assert_no_sentinel(info.value)
    assert "HTTP 400" in str(info.value)


def test_meta_numeric_codes_are_kept(monkeypatch):
    import io
    import urllib.error
    import urllib.request
    body = b'{"error": {"message": "Invalid OAuth access token", "code": 190, "error_subcode": 463}}'
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: (_ for _ in ()).throw(
        urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(body))))
    with pytest.raises(rl.PublishError, match="code 190, subcode 463"):
        rl.graph_http("GET", "https://graph.facebook.com/v27.0/1")


def test_non_json_body_at_the_old_200_cut_does_not_leak(monkeypatch):
    import urllib.request
    raw = ("y" * (200 - len(SENTINEL) + 1) + SENTINEL).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _Resp(raw))
    with pytest.raises(rl.PublishError) as info:
        rl.graph_http("POST", "https://graph.facebook.com/v27.0/1/media", params={"a": "b"})
    _assert_no_sentinel(info.value)


def test_url_error_leaves_no_raw_exception_in_the_chain(monkeypatch):
    import urllib.error
    import urllib.request

    def fake(req, timeout=0):
        raise urllib.error.URLError(SENTINEL)
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(rl.PublishError) as info:
        rl.graph_http("GET", "https://graph.facebook.com/v27.0/1")
    assert info.value.__context__ is None and info.value.__cause__ is None
    _assert_no_sentinel(info.value)


def test_unexpected_exception_in_publish_prints_only_its_type(tmp_path, video, monkeypatch, capsys):
    card = tmp_path / "card.json"
    card.write_text(json.dumps(_card(video)), encoding="utf-8")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "TOKEN")

    def boom(*a, **k):
        raise OSError(SENTINEL)
    monkeypatch.setattr(rl, "gate", boom)
    code = rl.main(["publish", str(card), "--video", str(video), "--ig-user-id", "1"])
    out = capsys.readouterr()
    assert code == 3 and "unexpected OSError" in out.err
    _assert_no_sentinel(out.err + out.out)


@pytest.mark.parametrize("final", [{"id": " "}, {"id": "180002", "error": {"message": "failure"}},
                                   {"id": SENTINEL}, {"id": "../../me"}])
def test_media_publish_reply_must_be_a_clean_numeric_id(video, final):
    class Final(FakeGraph):
        def __call__(self, method, url, **kw):
            out = super().__call__(method, url, **kw)
            return final if url.endswith("/media_publish") else out
    with pytest.raises(rl.PublishError) as info:
        _publish(_card(video), video, Final())
    _assert_no_sentinel(info.value)


def test_echoed_credential_as_container_id_is_never_used_in_a_url(video):
    class Echo(FakeGraph):
        def __call__(self, method, url, **kw):
            out = super().__call__(method, url, **kw)
            return {"id": SENTINEL} if url.endswith("/media") else out
    http = Echo()
    with pytest.raises(rl.PublishError, match="no numeric id"):
        _publish(_card(video), video, http)
    assert len(http.calls) == 1


def test_non_numeric_ig_user_id_is_blocked_before_any_call(video):
    http = FakeGraph()
    receipt, reasons, _ = rl.publish(_card(video), video, ig_user_id="me/../x", token="TOKEN", http=http,
                                     probe=_ok_probe, card_dir=video.parent, now=NOW)
    assert receipt is None and "numeric" in reasons[0] and http.calls == []


def test_no_poll_starts_at_or_after_the_deadline(video):
    clock = FakeClock()
    graph = FakeGraph(status=("IN_PROGRESS",) * 20)
    with pytest.raises(rl.PublishError, match="not FINISHED within 300"):
        rl.publish(_card(video), video, ig_user_id="1", token="TOKEN", http=graph, probe=_ok_probe,
                   card_dir=video.parent, now=NOW, sleep=clock.sleep, clock=clock, poll_every=60.0)
    poll_times = [c for c in graph.calls if c["method"] == "GET"]
    assert len(poll_times) == 5  # at 0, 60, 120, 180, 240; none at 300
    assert clock.t <= 300
