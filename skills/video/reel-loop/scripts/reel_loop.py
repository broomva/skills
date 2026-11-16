#!/usr/bin/env python3
"""reel_loop — the deterministic parts of the reel loop.

The loop (see ../SKILL.md) is mostly judgment: deconstructing a reel, writing a
script, directing a render. Three steps are arithmetic or policy, and those live
here so an agent cannot talk itself past them:

  outliers  Reels in a niche scored against their own account's normal.
            ratio = views / median(views of the account's OTHER reels).
            Leave-one-out, so a 40x reel does not raise its own baseline.
  winners   Our own posts scored the same way against our trailing window,
            only once they are old enough for insights to have settled
            (Meta: insights can lag up to 48 h). Emits a trial-reel variant
            plan for each winner.
  payload   The publish gate. Prints the Instagram Graph API container
            parameters for a post card ONLY when the card carries an approval
            bound to the exact bytes of the rendered video, a consent record
            for any cloned voice, a caption within Meta's limits, and a valid
            trial graduation strategy. Anything synthetic forces
            is_ai_generated=true. Exit 2 and a list of reasons otherwise.

Pure stdlib. `ffprobe` is used by `payload` when present; when absent the spec
check is reported as UNCHECKED, never as passed.

Sources for the platform numbers (read 2026-11-16):
  developers.facebook.com/documentation/instagram-platform/instagram-graph-api/
    reference/ig-user/media.md  — caption "Maximum 2200 characters, 30
    hashtags, and 20 @ tags"; trial_params.graduation_strategy MANUAL |
    SS_PERFORMANCE; is_ai_generated; Reels spec (MOV/MP4, H264/HEVC, 23-60 FPS,
    3 s - 15 min, 300 MB).
  developers.facebook.com/docs/instagram-platform/reference/instagram-media/
    insights — "views", "reels_skip_rate", "ig_reels_avg_watch_time"; data can
    be delayed up to 48 hours.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

# --- platform limits (see module docstring for the source) -------------------
CAPTION_MAX_CHARS = 2200
CAPTION_MAX_HASHTAGS = 30
CAPTION_MAX_MENTIONS = 20
GRADUATION_STRATEGIES = ("MANUAL", "SS_PERFORMANCE")
REEL_MIN_SECONDS = 3.0
REEL_MAX_SECONDS = 15 * 60.0
REEL_MAX_BYTES = 300 * 1024 * 1024
REEL_FPS = (23.0, 60.0)
REEL_CODECS = ("h264", "hevc")
INSIGHTS_SETTLE_HOURS = 48

VARIANT_AXES = (
    ("hook", "Same body and footage; a different first line and first frame."),
    ("color", "Same cut; a different grade or caption palette."),
    ("framing", "Same cut; a different crop, zoom or on-screen layout."),
)

# --- parsing ------------------------------------------------------------------
_SUFFIX = {
    "k": 1e3, "mil": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "millón": 1e6, "millon": 1e6, "millones": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9,
}
_NUM = re.compile(r"^\s*([0-9][0-9.,\s  ]*?)\s*([a-zA-Zñóé]+)?\s*$")


def parse_count(text: str) -> int:
    """Parse a view count as Instagram renders it, in English or Spanish.

    "12,3 mil" -> 12300, "1,2 M" -> 1200000, "12.3K" -> 12300,
    "8.400" -> 8400, "104 mil" -> 104000, "2,214,507" -> 2214507.

    Without a suffix the number is an integer count, so every separator is a
    thousands separator. With a suffix the LAST separator is the decimal mark.
    """
    if text is None:
        raise ValueError("empty count")
    raw = str(text).strip().lower()
    if not raw:
        raise ValueError("empty count")
    m = _NUM.match(raw)
    if not m:
        raise ValueError(f"unparseable count: {text!r}")
    digits, suffix = m.group(1), (m.group(2) or "")
    digits = re.sub(r"[\s  ]", "", digits)
    if suffix:
        if suffix not in _SUFFIX:
            raise ValueError(f"unknown suffix {suffix!r} in {text!r}")
        seps = [i for i, c in enumerate(digits) if c in ".,"]
        if seps:
            last = seps[-1]
            whole = re.sub(r"[.,]", "", digits[:last])
            value = float(f"{whole or '0'}.{digits[last + 1:]}")
        else:
            value = float(digits)
        return int(round(value * _SUFFIX[suffix]))
    return int(re.sub(r"[.,]", "", digits))


def parse_time(text: str | None) -> datetime | None:
    if text is None or not str(text).strip():
        return None
    s = str(text).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"bad date {text!r}: use ISO 8601 (YYYY-MM-DD or a timestamp)") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def read_rows(path: str) -> list[dict]:
    """Read CSV, TSV or a JSON list of objects. Header names are lower-cased."""
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        rows = json.loads(text)
        return [{str(k).strip().lower(): v for k, v in r.items()} for r in rows]
    first = text.splitlines()[0] if text else ""
    dialect = "excel-tab" if "\t" in first else "excel"
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [{(k or "").strip().lower(): (v.strip() if isinstance(v, str) else v)
             for k, v in r.items()} for r in reader]


def _field(row: dict, *names: str):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return None


# --- outliers -----------------------------------------------------------------
def score_outliers(rows: list[dict], *, bar: float, min_views: int, max_age_days: int | None,
                   min_sample: int, now: datetime) -> dict:
    reels, errors, seen = [], [], set()
    for i, r in enumerate(rows, start=2):
        account = _field(r, "account", "cuenta", "creator", "username")
        url = _field(r, "url", "link", "enlace", "permalink")
        views_raw = _field(r, "views", "view_count", "plays", "reproducciones", "visitas")
        if not account or views_raw is None:
            errors.append(f"row {i}: needs account and views")
            continue
        try:
            views = parse_count(views_raw)
            published = parse_time(_field(r, "date", "published_at", "timestamp", "fecha"))
        except ValueError as exc:
            errors.append(f"row {i}: {exc}")
            continue
        key = url or f"{account}#{i}"
        if key in seen:
            continue
        seen.add(key)
        reels.append({"account": str(account).lstrip("@").lower(), "url": url, "views": views,
                      "published": published, "hook": _field(r, "hook", "gancho")})

    by_account: dict[str, list[dict]] = {}
    for r in reels:
        by_account.setdefault(r["account"], []).append(r)

    passed, skipped = [], []
    accounts = {}
    for acct, items in sorted(by_account.items()):
        accounts[acct] = {"reels": len(items),
                          "median": int(round(median(x["views"] for x in items))),
                          "low_sample": len(items) - 1 < min_sample}
        for r in items:
            others = [x["views"] for x in items if x is not r]
            base = median(others) if others else None
            r["baseline"] = int(round(base)) if base is not None else None
            r["ratio"] = (r["views"] / base) if base else None
            r["age_days"] = (now - r["published"]).days if r["published"] else None
            reason = None
            if len(others) < min_sample:
                reason = f"low sample: {len(others)} other reels < {min_sample}"
            elif not base:
                reason = "baseline is zero"
            elif r["ratio"] < bar:
                reason = f"ratio {r['ratio']:.2f} < bar {bar}"
            elif r["views"] < min_views:
                reason = f"views {r['views']} < minimum {min_views}"
            elif max_age_days is not None and r["age_days"] is not None and r["age_days"] > max_age_days:
                reason = f"age {r['age_days']} d > {max_age_days} d"
            (skipped if reason else passed).append({**_public(r), **({"reason": reason} if reason else {})})

    passed.sort(key=lambda x: x["ratio"], reverse=True)
    return {"params": {"bar": bar, "min_views": min_views, "max_age_days": max_age_days,
                       "min_sample": min_sample, "baseline": "leave-one-out median of the account's other reels"},
            "accounts": accounts, "outliers": passed, "skipped": skipped, "errors": errors}


def _public(r: dict) -> dict:
    return {"account": r["account"], "url": r["url"], "views": r["views"],
            "baseline": r.get("baseline"),
            "ratio": round(r["ratio"], 2) if r.get("ratio") is not None else None,
            "published": r["published"].isoformat() if r.get("published") else None,
            "age_days": r.get("age_days"), "hook": r.get("hook")}


# --- winners ------------------------------------------------------------------
def score_winners(rows: list[dict], *, bar: float, window_days: int, min_age_hours: float,
                  min_sample: int, graduation: str, now: datetime) -> dict:
    if graduation not in GRADUATION_STRATEGIES:
        raise ValueError(f"graduation must be one of {GRADUATION_STRATEGIES}")
    posts, errors = [], []
    for i, r in enumerate(rows, start=2):
        pid = _field(r, "id", "media_id", "url", "permalink")
        views_raw = _field(r, "views", "view_count")
        try:
            published = parse_time(_field(r, "published_at", "timestamp", "date"))
            views = parse_count(views_raw) if views_raw is not None else None
        except ValueError as exc:
            errors.append(f"row {i}: {exc}")
            continue
        if not pid or published is None or views is None:
            errors.append(f"row {i}: needs id, published_at and views")
            continue
        is_trial = str(_field(r, "is_trial", "trial") or "").lower() in ("1", "true", "yes")
        posts.append({"id": pid, "published": published, "views": views, "is_trial": is_trial,
                      "skip_rate": _maybe_float(_field(r, "reels_skip_rate", "skip_rate")),
                      "avg_watch_ms": _maybe_float(_field(r, "ig_reels_avg_watch_time", "avg_watch_time"))})

    winners, pending, rest = [], [], []
    for p in posts:
        age_h = (now - p["published"]).total_seconds() / 3600
        window = [q["views"] for q in posts
                  if q is not p and not q["is_trial"]
                  and p["published"] - timedelta(days=window_days) <= q["published"] < p["published"]]
        base = median(window) if window else None
        row = {"id": p["id"], "published": p["published"].isoformat(), "views": p["views"],
               "age_hours": round(age_h, 1), "baseline": int(round(base)) if base else None,
               "ratio": round(p["views"] / base, 2) if base else None, "window_posts": len(window),
               "skip_rate": p["skip_rate"], "avg_watch_ms": p["avg_watch_ms"], "is_trial": p["is_trial"]}
        if age_h < min_age_hours:
            pending.append({**row, "reason": f"{age_h:.0f} h old < {min_age_hours:.0f} h: insights not settled"})
        elif len(window) < min_sample:
            rest.append({**row, "reason": f"{len(window)} posts in the trailing {window_days} d < {min_sample}"})
        elif base and p["views"] / base >= bar:
            winners.append({**row, "variants": [
                {"axis": axis, "brief": brief, "media_type": "REELS",
                 "trial_params": {"graduation_strategy": graduation}} for axis, brief in VARIANT_AXES]})
        else:
            rest.append({**row, "reason": f"ratio {row['ratio']} < bar {bar}" if base else "no baseline"})
    winners.sort(key=lambda x: x["ratio"], reverse=True)
    return {"params": {"bar": bar, "window_days": window_days, "min_age_hours": min_age_hours,
                       "min_sample": min_sample, "graduation_strategy": graduation,
                       "baseline": "median views of our non-trial posts in the trailing window before each post"},
            "winners": winners, "pending": pending, "rest": rest, "errors": errors}


def _maybe_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# --- payload (the publish gate) ------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video(path: Path) -> dict | None:
    """Return codec, fps and duration through ffprobe, or None when unavailable."""
    if not shutil.which("ffprobe"):
        return None
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,avg_frame_rate:format=duration,format_name", "-of", "json", str(path)],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or f"ffprobe exited {proc.returncode}"}
    data = json.loads(proc.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    num, _, den = (stream.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {"codec": stream.get("codec_name"), "fps": round(fps, 3),
            "duration": float((data.get("format") or {}).get("duration") or 0.0),
            "format": (data.get("format") or {}).get("format_name", "")}


def check_payload(card: dict, video: Path, video_url: str | None, *, probe=probe_video) -> tuple[dict | None, list[str], list[str]]:
    """Return (payload, blocking_reasons, notes). payload is None when blocked."""
    reasons, notes = [], []

    if not video.is_file():
        return None, [f"video not found: {video}"], notes
    digest = sha256_file(video)

    approval = card.get("approval") or {}
    if not approval.get("by") or not approval.get("at"):
        reasons.append("no approval: the card needs approval.by and approval.at, set by a person")
    elif approval.get("video_sha256") != digest:
        reasons.append("approval does not match these bytes: approval.video_sha256 != sha256(video); "
                       "a re-render needs a new approval")

    synthetic = card.get("synthetic") or {}
    if not isinstance(synthetic, dict):
        reasons.append("synthetic must be an object of booleans")
        synthetic = {}
    if synthetic.get("voice_clone"):
        consent = card.get("voice_consent") or {}
        if not consent.get("speaker") or not consent.get("date"):
            reasons.append("cloned voice without a consent record (voice_consent.speaker and .date)")
    is_ai = any(bool(v) for v in synthetic.values())
    if card.get("is_ai_generated") is False and is_ai:
        notes.append("card said is_ai_generated=false but synthetic media is declared; forced to true")

    caption = card.get("caption") or ""
    if len(caption) > CAPTION_MAX_CHARS:
        reasons.append(f"caption is {len(caption)} chars > {CAPTION_MAX_CHARS}")
    tags = len(re.findall(r"(?<![\w#])#\w+", caption))
    if tags > CAPTION_MAX_HASHTAGS:
        reasons.append(f"caption has {tags} hashtags > {CAPTION_MAX_HASHTAGS}")
    mentions = len(re.findall(r"(?<![\w@])@[\w.]+", caption))
    if mentions > CAPTION_MAX_MENTIONS:
        reasons.append(f"caption has {mentions} @ tags > {CAPTION_MAX_MENTIONS}")

    trial = card.get("trial")
    if trial is not None:
        strategy = (trial or {}).get("graduation_strategy")
        if strategy not in GRADUATION_STRATEGIES:
            reasons.append(f"trial.graduation_strategy must be one of {GRADUATION_STRATEGIES}, got {strategy!r}")
        elif strategy == "MANUAL":
            notes.append("MANUAL graduation happens only in the Instagram app; nothing in the API graduates it")

    size = video.stat().st_size
    if size > REEL_MAX_BYTES:
        reasons.append(f"video is {size} bytes > 300 MB")
    info = probe(video)
    if info is None:
        notes.append("UNCHECKED: ffprobe not on PATH, so codec, fps and duration were not verified")
    elif "error" in info:
        reasons.append(f"ffprobe could not read the video: {info['error']}")
    else:
        if info["codec"] not in REEL_CODECS:
            reasons.append(f"codec {info['codec']!r} is not H264 or HEVC")
        if not (REEL_FPS[0] <= info["fps"] <= REEL_FPS[1]):
            reasons.append(f"frame rate {info['fps']} outside 23-60 fps")
        if not (REEL_MIN_SECONDS <= info["duration"] <= REEL_MAX_SECONDS):
            reasons.append(f"duration {info['duration']:.1f} s outside 3 s - 15 min")

    if not video_url:
        notes.append("video_url left as a placeholder: Meta fetches the file from a public URL")

    if reasons:
        return None, reasons, notes
    payload = {"media_type": "REELS", "video_url": video_url or "<PUBLIC_VIDEO_URL>",
               "caption": caption, "is_ai_generated": is_ai,
               "share_to_feed": bool(card.get("share_to_feed", True))}
    if trial is not None:
        payload["trial_params"] = {"graduation_strategy": trial["graduation_strategy"]}
    for opt in ("cover_url", "thumb_offset", "audio_name", "collaborators"):
        if card.get(opt) not in (None, ""):
            payload[opt] = card[opt]
    notes.append(f"gate passed: sha256 {digest} approved by {approval.get('by')} at {approval.get('at')}")
    return payload, reasons, notes


# --- CLI ----------------------------------------------------------------------
def _now(arg: str | None) -> datetime:
    return parse_time(arg) if arg else datetime.now(timezone.utc)


def _print_outliers(res: dict) -> None:
    p = res["params"]
    print(f"bar {p['bar']}x the account's normal · min {p['min_views']:,} views"
          + (f" · max {p['max_age_days']} d old" if p["max_age_days"] is not None else "")
          + f" · baseline: {p['baseline']}")
    print("\naccount normals (median of all their reels):")
    for a, d in res["accounts"].items():
        flag = "  LOW SAMPLE" if d["low_sample"] else ""
        print(f"  @{a:<24} {d['median']:>12,}  ({d['reels']} reels){flag}")
    print()
    if not res["outliers"]:
        print("no reel clears the bar.")
    for i, r in enumerate(res["outliers"], 1):
        print(f"{i:>2}. {r['ratio']:>6.1f}x  {r['views']:>12,} vs {r['baseline']:>10,}  @{r['account']}  {r['url'] or ''}")
    for e in res["errors"]:
        print(f"error: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="reel_loop", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("outliers", help="score niche reels against their own account's normal")
    o.add_argument("input", help="CSV, TSV or JSON list with account, url, views[, date, hook]; '-' for stdin")
    o.add_argument("--bar", type=float, default=4.0)
    o.add_argument("--min-views", type=int, default=20000)
    o.add_argument("--max-age-days", type=int, default=45, help="0 = no limit")
    o.add_argument("--min-sample", type=int, default=5, help="other reels needed for a baseline")
    o.add_argument("--now")
    o.add_argument("--json", action="store_true")

    w = sub.add_parser("winners", help="find our posts that beat our own trailing normal")
    w.add_argument("input", help="CSV, TSV or JSON list with id, published_at, views[, reels_skip_rate, ig_reels_avg_watch_time, is_trial]")
    w.add_argument("--bar", type=float, default=2.0)
    w.add_argument("--window-days", type=int, default=30)
    w.add_argument("--min-age-hours", type=float, default=INSIGHTS_SETTLE_HOURS)
    w.add_argument("--min-sample", type=int, default=5)
    w.add_argument("--graduation", default="SS_PERFORMANCE", choices=GRADUATION_STRATEGIES)
    w.add_argument("--now")

    p = sub.add_parser("payload", help="the publish gate: card + video -> Graph API container params")
    p.add_argument("card", help="post card JSON (references/post-card.md)")
    p.add_argument("--video", required=True)
    p.add_argument("--video-url", help="the public URL Meta will fetch the same bytes from")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "outliers":
            res = score_outliers(read_rows(a.input), bar=a.bar, min_views=a.min_views,
                                 max_age_days=a.max_age_days or None, min_sample=a.min_sample, now=_now(a.now))
            if a.json:
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                _print_outliers(res)
            return 0
        if a.cmd == "winners":
            res = score_winners(read_rows(a.input), bar=a.bar, window_days=a.window_days,
                                min_age_hours=a.min_age_hours, min_sample=a.min_sample,
                                graduation=a.graduation, now=_now(a.now))
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0
        card = json.loads(Path(a.card).read_text(encoding="utf-8"))
        payload, reasons, notes = check_payload(card, Path(a.video), a.video_url)
        for n in notes:
            print(f"note: {n}", file=sys.stderr)
        if payload is None:
            print("BLOCKED — not publishable:", file=sys.stderr)
            for r in reasons:
                print(f"  - {r}", file=sys.stderr)
            return 2
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
