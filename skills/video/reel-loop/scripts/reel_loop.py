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
  payload   Dry run of the publish gate (below). Prints the container
            parameters, sha256 and size; names no file to upload.
  publish   The publish gate, then the publish. Reads the video ONCE and
            gates those bytes: the card must be well-formed and carry an
            approval bound to their sha256; a declared cloned voice needs a
            consent record (speaker, past ISO date, existing file); the caption
            must be within Meta's limits; the trial strategy must be valid.
            Declared synthetic media or an explicit is_ai_generated=true yields
            is_ai_generated=true. Then: create a resumable REELS container,
            send THE SAME BYTES to rupload, poll until FINISHED (5-minute
            deadline), media_publish. Swapping the file after the gate cannot
            change what is published. The token goes only in Authorization
            headers and is redacted from every error.
            Exit 2 with reasons when blocked, 3 when a Graph API step fails.
            Tested against a fake Graph API only; never run against a live account.
            It cannot prove who wrote the approval or detect synthetic media
            the card does not declare.

Pure stdlib. `ffprobe` is used by the gate when present; when absent the spec
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
import os
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


# --- the publish gate -----------------------------------------------------------
GRAPH = "https://graph.facebook.com"
RUPLOAD = "https://rupload.facebook.com/ig-api-upload"
API_VERSION = "v27.0"


class PublishError(RuntimeError):
    """A Graph API step failed after the gate passed. Never carries the token."""


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


# Optional fields: null means absent. Fields not listed here (account, source,
# script) are provenance for the run note; they are never published and not checked.
_OPTIONAL_TYPES = {"cover_url": str, "audio_name": str, "thumb_offset": int, "share_to_feed": bool,
                   "is_ai_generated": bool, "caption": str}


def _type_errors(card) -> list[str]:
    """Every shape problem in the published or gating fields of a card. A card
    with any of these is blocked before a single field is trusted, so a malformed
    card can neither crash the gate nor slip past a check that assumed a type."""
    if not isinstance(card, dict):
        return [f"the card must be a JSON object, got {type(card).__name__}"]
    errs = []
    approval = card.get("approval")
    if approval is not None:
        if not isinstance(approval, dict):
            errs.append("approval must be an object {by, at, video_sha256} or null")
        else:
            for k in ("by", "at", "video_sha256"):
                if not isinstance(approval.get(k), str) or not approval.get(k).strip():
                    errs.append(f"approval.{k} must be a non-empty string")
    synthetic = card.get("synthetic", {})
    if not isinstance(synthetic, dict) or not all(isinstance(v, bool) for v in synthetic.values()):
        errs.append("synthetic must be an object whose values are true or false")
    consent = card.get("voice_consent")
    if consent is not None and not isinstance(consent, dict):
        errs.append("voice_consent must be an object {speaker, date, ref} or null")
    trial = card.get("trial")
    if trial is not None and not isinstance(trial, dict):
        errs.append("trial must be an object {graduation_strategy} or null")
    for k, typ in _OPTIONAL_TYPES.items():
        v = card.get(k)
        if v is not None and (not isinstance(v, typ) or (typ is int and isinstance(v, bool))):
            errs.append(f"{k} must be {typ.__name__}")
    collab = card.get("collaborators")
    if collab is not None and (not isinstance(collab, list) or not all(isinstance(c, str) for c in collab)
                               or len(collab) > 3):
        errs.append("collaborators must be a list of at most 3 usernames")
    return errs


def _consent_errors(consent: dict | None, card_dir: Path, now: datetime) -> list[str]:
    if not consent:
        return ["cloned voice declared without voice_consent {speaker, date, ref}"]
    errs = []
    if not isinstance(consent.get("speaker"), str) or not consent["speaker"].strip():
        errs.append("voice_consent.speaker must name the person whose voice is cloned")
    try:
        when = parse_time(consent.get("date")) if isinstance(consent.get("date"), str) else None
    except ValueError:
        when = None
    if when is None:
        errs.append("voice_consent.date must be an ISO date")
    elif when > now:
        errs.append("voice_consent.date is in the future")
    ref = consent.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        errs.append("voice_consent.ref must point to the consent record file")
    elif not (card_dir / ref).is_file():
        errs.append(f"voice_consent.ref {ref!r} does not exist relative to the card ({card_dir})")
    return errs


def read_video(video: Path) -> tuple[bytes | None, list[str]]:
    """Read the video ONCE. Every later step — hash, probe, upload — uses these
    bytes, so nothing that happens to the file afterwards can reach Instagram."""
    if not video.exists():
        return None, [f"video cannot be read: {video} does not exist"]
    if not video.is_file():
        return None, [f"video is not a regular file: {video}"]
    try:
        with video.open("rb") as f:
            data = f.read(REEL_MAX_BYTES + 1)  # one bounded read: no stat/read race on the size
    except OSError as exc:
        return None, [f"video cannot be read: {exc}"]
    if not data:
        return None, ["video is empty"]
    if len(data) > REEL_MAX_BYTES:
        return None, ["video is over 300 MB"]
    return data, []


def _probe_bytes(data: bytes, probe) -> dict | None:
    """Probe the exact bytes in hand, through a private temporary copy."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "probe.mp4"
        f.write_bytes(data)
        return probe(f)


def gate(card: dict, data: bytes, *, card_dir: Path, probe, now: datetime
         ) -> tuple[dict | None, list[str], list[str], str]:
    """Judge a well-formed card against the exact bytes `data`.
    Returns (container_params | None, reasons, notes, sha256(data))."""
    notes: list[str] = []
    reasons: list[str] = []
    digest = hashlib.sha256(data).hexdigest()

    approval = card.get("approval")
    if not approval:
        reasons.append("no approval: the card needs approval {by, at, video_sha256}, written after a person says yes")
    elif approval["video_sha256"] != digest:
        reasons.append("approval does not match these bytes: approval.video_sha256 != sha256(video); "
                       "a re-render needs a new approval")

    synthetic = card.get("synthetic") or {}
    if synthetic.get("voice_clone"):
        reasons += _consent_errors(card.get("voice_consent"), card_dir, now)
    is_ai = card.get("is_ai_generated") is True or any(synthetic.values())
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
        strategy = trial.get("graduation_strategy")
        if strategy not in GRADUATION_STRATEGIES:
            reasons.append(f"trial.graduation_strategy must be one of {GRADUATION_STRATEGIES}, got {strategy!r}")
        elif strategy == "MANUAL":
            notes.append("MANUAL: Meta documents graduating it in the Instagram app; no API graduation endpoint is documented")

    info = _probe_bytes(data, probe)
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

    if reasons:
        return None, reasons, notes, digest
    share = card.get("share_to_feed")
    container = {"media_type": "REELS", "upload_type": "resumable", "caption": caption,
                 "is_ai_generated": is_ai, "share_to_feed": True if share is None else share}
    if trial is not None:
        container["trial_params"] = {"graduation_strategy": trial["graduation_strategy"]}
    for opt in ("cover_url", "thumb_offset", "audio_name", "collaborators"):
        if card.get(opt) not in (None, "", []):
            container[opt] = card[opt]
    notes.append(f"gate passed: sha256 {digest} approved by {approval['by']} at {approval['at']}")
    return container, reasons, notes, digest


def check_payload(card, video: Path, *, card_dir: Path | None = None, probe=probe_video,
                  now: datetime | None = None) -> tuple[dict | None, list[str], list[str]]:
    """Dry run of the gate. Returns ({"container", "sha256", "file_size"} | None, reasons, notes).
    It names no file to upload: the only way bytes reach Instagram is `publish`."""
    errs = _type_errors(card)
    if errs:
        return None, errs, []
    data, errs = read_video(video)
    if errs:
        return None, errs, []
    container, reasons, notes, digest = gate(card, data, card_dir=card_dir or Path("."), probe=probe,
                                             now=now or datetime.now(timezone.utc))
    if container is None:
        return None, reasons, notes
    return {"container": container, "sha256": digest, "file_size": len(data)}, [], notes


def graph_http(method: str, url: str, *, params: dict | None = None, headers: dict | None = None,
               body: bytes | None = None, timeout: float = 120) -> dict:
    """One Graph API call. The caller passes the token only in `headers`. Any failure,
    including a non-JSON or non-object reply, raises PublishError; the caller
    redacts the token from every message."""
    import urllib.error
    import urllib.parse
    import urllib.request
    data = body
    if params is not None:
        enc = urllib.parse.urlencode(params)
        if method == "GET":
            url = f"{url}?{enc}"
        else:
            data = enc.encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    where = f"{method} {url.split('?')[0]}"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise PublishError(f"{where} -> HTTP {exc.code}: {exc.read()[:500].decode('utf-8', 'replace')}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise PublishError(f"{where} failed: {getattr(exc, 'reason', exc)}") from None
    try:
        out = json.loads(raw or b"{}")
    except ValueError:
        raise PublishError(f"{where} returned non-JSON: {raw[:200]!r}") from None
    if not isinstance(out, dict):
        raise PublishError(f"{where} returned {type(out).__name__}, not a JSON object")
    return out


def _form(container: dict) -> dict:
    out = {}
    for k, v in container.items():
        out[k] = json.dumps(v) if isinstance(v, (dict, list)) else ("true" if v is True else "false" if v is False else v)
    return out


def _redact(text: str, token: str) -> str:
    return text.replace(token, "<redacted>") if token else text


PUBLISH_DEADLINE_SECONDS = 300.0  # Meta: poll "once per minute, for no more than 5 minutes"


def publish(card, video: Path, *, ig_user_id: str, token: str, card_dir: Path | None = None,
            api_version: str = API_VERSION, http=graph_http, probe=probe_video, now: datetime | None = None,
            sleep=None, clock=None, poll_every: float = 60.0, deadline_s: float = PUBLISH_DEADLINE_SECONDS,
            go_live: bool = True) -> tuple[dict | None, list[str], list[str]]:
    """Gate, then publish the gated bytes. Returns (receipt | None, reasons, notes).

    The video is read once; the bytes hashed against the approval are the bytes
    sent to rupload, so swapping the file after the gate changes nothing that is
    published. The token travels only in Authorization headers (Bearer for Graph
    calls, OAuth for rupload), never in a URL or body, and every error message is
    redacted. Raises PublishError when a Graph
    API step fails after the gate, or when the container is not FINISHED within
    `deadline_s` (requests and sleeps both count).
    """
    import time
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    errs = _type_errors(card)
    if errs:
        return None, errs, []
    data, errs = read_video(video)
    if errs:
        return None, errs, []
    container, reasons, notes, digest = gate(card, data, card_dir=card_dir or Path("."), probe=probe,
                                             now=now or datetime.now(timezone.utc))
    if container is None:
        return None, reasons, notes

    bearer = {"Authorization": f"Bearer {token}"}   # Graph calls, as in Meta's content-publishing guide
    oauth = {"Authorization": f"OAuth {token}"}     # rupload, as in the media reference

    def call(step: str, method: str, url: str, **kw) -> dict:
        try:
            out = http(method, url, **kw)
        except Exception as exc:  # noqa: BLE001 - every transport failure is a redacted PublishError
            raise PublishError(_redact(f"{step}: {exc}", token)) from None
        if not isinstance(out, dict):
            raise PublishError(f"{step}: reply is {type(out).__name__}, not a JSON object")
        return out

    def fail(msg: str) -> PublishError:
        return PublishError(_redact(msg, token))

    made = call("create container", "POST", f"{GRAPH}/{api_version}/{ig_user_id}/media",
                params=_form(container), headers=bearer)
    cid = made.get("id")
    if not isinstance(cid, str) or not cid:
        raise fail(f"create container: no id in reply {made}")
    sent = call("upload", "POST", f"{RUPLOAD}/{api_version}/{cid}",
                headers={**oauth, "offset": "0", "file_size": str(len(data))}, body=data)
    if sent.get("success") is not True:
        raise fail(f"upload: rupload did not report success: {sent}")
    deadline = clock() + deadline_s
    while True:
        status = call("poll", "GET", f"{GRAPH}/{api_version}/{cid}", params={"fields": "status_code"},
                      headers=bearer, timeout=max(1.0, deadline - clock())).get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise fail(f"poll: container {cid} status {status}")
        if clock() + poll_every > deadline:
            raise fail(f"poll: container {cid} not FINISHED within {deadline_s:.0f} s (last status {status!r})")
        sleep(poll_every)
    receipt = {"container_id": cid, "sha256": digest, "file_size": len(data), "status": "FINISHED",
               "trial": container.get("trial_params"), "is_ai_generated": container["is_ai_generated"]}
    if go_live:
        done = call("media_publish", "POST", f"{GRAPH}/{api_version}/{ig_user_id}/media_publish",
                    params={"creation_id": cid}, headers=bearer)
        if not isinstance(done.get("id"), str) or not done.get("id"):
            raise fail(f"media_publish: no id in reply {done}")
        receipt["media_id"] = done["id"]
    return receipt, [], notes


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

    p = sub.add_parser("payload", help="dry run of the publish gate: card + video -> container params")
    p.add_argument("card", help="post card JSON (references/post-card.md)")
    p.add_argument("--video", required=True)

    u = sub.add_parser("publish", help="gate, then publish the gated bytes (token from $IG_ACCESS_TOKEN)")
    u.add_argument("card", help="post card JSON (references/post-card.md)")
    u.add_argument("--video", required=True)
    u.add_argument("--ig-user-id", required=True)
    u.add_argument("--api-version", default=API_VERSION)
    u.add_argument("--no-go-live", action="store_true",
                   help="create, upload and wait for the container, but do not call media_publish")

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
        try:
            card = json.loads(Path(a.card).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"BLOCKED — not publishable:\n  - the card could not be read as JSON: {exc}", file=sys.stderr)
            return 2
        card_dir = Path(a.card).resolve().parent
        if a.cmd == "payload":
            result, reasons, notes = check_payload(card, Path(a.video), card_dir=card_dir)
        else:
            token = os.environ.get("IG_ACCESS_TOKEN", "")
            if not token:
                print("BLOCKED — not publishable:\n  - IG_ACCESS_TOKEN is not set", file=sys.stderr)
                return 2
            try:
                result, reasons, notes = publish(card, Path(a.video), ig_user_id=a.ig_user_id, token=token,
                                                 card_dir=card_dir, api_version=a.api_version,
                                                 go_live=not a.no_go_live)
            except PublishError as exc:
                print(f"PUBLISH FAILED after the gate passed: {exc}", file=sys.stderr)
                return 3
        for n in notes:
            print(f"note: {n}", file=sys.stderr)
        if result is None:
            print("BLOCKED — not publishable:", file=sys.stderr)
            for r in reasons:
                print(f"  - {r}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
