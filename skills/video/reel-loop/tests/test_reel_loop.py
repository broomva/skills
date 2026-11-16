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


def test_gate_passes_and_forces_ai_disclosure(video):
    payload, reasons, _ = rl.check_payload(_card(video, is_ai_generated=False), video, "https://x/v.mp4", probe=_ok_probe)
    assert reasons == []
    assert payload["is_ai_generated"] is True
    assert payload["media_type"] == "REELS"
    assert "trial_params" not in payload


def test_gate_blocks_without_approval(video):
    payload, reasons, _ = rl.check_payload(_card(video, approval=None), video, None, probe=_ok_probe)
    assert payload is None and any("no approval" in r for r in reasons)


def test_gate_blocks_when_video_changed_after_approval(video):
    card = _card(video)
    video.write_bytes(b"re-rendered after approval")
    payload, reasons, _ = rl.check_payload(card, video, None, probe=_ok_probe)
    assert payload is None and any("does not match these bytes" in r for r in reasons)


def test_gate_blocks_cloned_voice_without_consent(video):
    payload, reasons, _ = rl.check_payload(_card(video, voice_consent=None), video, None, probe=_ok_probe)
    assert payload is None and any("consent" in r for r in reasons)


def test_no_consent_needed_without_a_cloned_voice(video):
    card = _card(video, voice_consent=None, synthetic={"voice_clone": False, "generated_visuals": False})
    payload, reasons, _ = rl.check_payload(card, video, None, probe=_ok_probe)
    assert reasons == [] and payload["is_ai_generated"] is False


@pytest.mark.parametrize("caption,needle", [
    ("x" * 2201, "chars"),
    (" ".join(f"#t{i}" for i in range(31)), "hashtags"),
    (" ".join(f"@u{i}" for i in range(21)), "@ tags"),
])
def test_gate_enforces_caption_limits(video, caption, needle):
    payload, reasons, _ = rl.check_payload(_card(video, caption=caption), video, None, probe=_ok_probe)
    assert payload is None and any(needle in r for r in reasons)


def test_caption_at_the_limits_passes(video):
    cap = " ".join(f"#t{i}" for i in range(30)) + " " + " ".join(f"@u{i}" for i in range(20))
    payload, reasons, _ = rl.check_payload(_card(video, caption=cap), video, None, probe=_ok_probe)
    assert reasons == []


def test_trial_params_passed_through_and_validated(video):
    payload, _, _ = rl.check_payload(_card(video, trial={"graduation_strategy": "SS_PERFORMANCE"}), video, None, probe=_ok_probe)
    assert payload["trial_params"] == {"graduation_strategy": "SS_PERFORMANCE"}
    payload, reasons, _ = rl.check_payload(_card(video, trial={"graduation_strategy": "AUTO"}), video, None, probe=_ok_probe)
    assert payload is None and any("graduation_strategy" in r for r in reasons)


@pytest.mark.parametrize("probe,needle", [
    ({"codec": "vp9", "fps": 30.0, "duration": 20.0, "format": "webm"}, "codec"),
    ({"codec": "h264", "fps": 15.0, "duration": 20.0, "format": "mp4"}, "frame rate"),
    ({"codec": "h264", "fps": 30.0, "duration": 2.0, "format": "mp4"}, "duration"),
    ({"codec": "h264", "fps": 30.0, "duration": 901.0, "format": "mp4"}, "duration"),
    ({"error": "moov atom not found"}, "ffprobe"),
])
def test_gate_enforces_reel_spec(video, probe, needle):
    payload, reasons, _ = rl.check_payload(_card(video), video, None, probe=lambda _p: probe)
    assert payload is None and any(needle in r for r in reasons)


def test_missing_ffprobe_is_unchecked_not_green(video):
    payload, reasons, notes = rl.check_payload(_card(video), video, None, probe=lambda _p: None)
    assert payload is not None
    assert any(n.startswith("UNCHECKED") for n in notes)


# --- CLI ------------------------------------------------------------------------
def test_cli_outliers_runs_on_the_example():
    out = subprocess.run([sys.executable, str(SCRIPT), "outliers", str(EXAMPLE), "--now", "2026-11-16"],
                         capture_output=True, text=True, check=True).stdout
    assert "@alpha" in out and "/p/A6/" in out and "/p/B6/" not in out


def test_cli_payload_exit_2_when_blocked(tmp_path, video):
    card = tmp_path / "card.json"
    card.write_text(json.dumps(_card(video, approval=None)), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), "payload", str(card), "--video", str(video)],
                          capture_output=True, text=True)
    assert proc.returncode == 2 and "BLOCKED" in proc.stderr and proc.stdout == ""


def test_payload_holds_only_graph_api_fields(video):
    payload, _, notes = rl.check_payload(_card(video), video, "https://x/v.mp4", probe=_ok_probe)
    allowed = {"media_type", "video_url", "caption", "is_ai_generated", "share_to_feed", "trial_params",
               "cover_url", "thumb_offset", "audio_name", "collaborators"}
    assert set(payload) <= allowed
    assert any(n.startswith("gate passed: sha256 ") for n in notes)
