"""Shared EDL library for the video-cut skill.

Single source of truth for: EDL load/validate, grade-preset resolution, output-timeline
segment math (clamped padded ranges + cumulative offsets), and SRT generation with the
caption output-timeline offset invariant. Imported by render.py, self_eval.py (math
reference), and the unit tests.
"""
from __future__ import annotations

import json
from pathlib import Path

GRADE_PRESETS = {
    "warm_cinematic": "eq=contrast=1.06:brightness=0.02:saturation=1.12,"
    "colorbalance=rm=0.06:gm=0.0:bm=-0.04",
    "neutral_punch": "eq=contrast=1.08:saturation=1.05",
    "none": None,
}

# Subtitle styles -> (ffmpeg force_style, uppercase?, default chunk_words)
SUBTITLE_STYLES = {
    "bold-overlay": (
        "FontName=Helvetica,Fontsize=18,Bold=1,PrimaryColour=&H00FFFFFF&,"
        "OutlineColour=&H00000000&,Outline=2,Alignment=2,MarginV=35",
        True,
        2,
    ),
    "natural-sentence": (
        "FontName=Helvetica,Fontsize=22,PrimaryColour=&H00FFFFFF&,"
        "OutlineColour=&H00000000&,Outline=2,Alignment=2,MarginV=70",
        False,
        6,
    ),
}

DEFAULT_FADE_MS = 30
DEFAULT_PAD_MS = 60


def load_edl(path: str | Path) -> dict:
    """Load + lightly validate an EDL, filling defaults."""
    edl = json.loads(Path(path).read_text())
    if edl.get("version") != 1:
        raise ValueError(f"unsupported EDL version: {edl.get('version')!r} (expected 1)")
    if not isinstance(edl.get("sources"), dict) or not edl["sources"]:
        raise ValueError("EDL.sources must be a non-empty {label: path} map")
    if not isinstance(edl.get("ranges"), list) or not edl["ranges"]:
        raise ValueError("EDL.ranges must be a non-empty list")
    for i, r in enumerate(edl["ranges"]):
        if r.get("source") not in edl["sources"]:
            raise ValueError(f"range[{i}] references unknown source {r.get('source')!r}")
        if not (float(r["end"]) > float(r["start"]) >= 0):
            raise ValueError(f"range[{i}] requires end > start >= 0")
    edl.setdefault("grade", "neutral_punch")
    edl.setdefault("fade_ms", DEFAULT_FADE_MS)
    edl.setdefault("pad_ms", DEFAULT_PAD_MS)
    edl.setdefault("overlays", [])
    edl.setdefault("subtitles", {"mode": "none"})
    edl.setdefault("output", "edit/final.mp4")
    return edl


def resolve_grade(grade) -> str | None:
    """Map a grade preset name or {'filter': ...} object to an ffmpeg -vf string (or None)."""
    if grade is None:
        return None
    if isinstance(grade, dict):
        return grade.get("filter") or None
    return GRADE_PRESETS.get(grade, None)


def output_segments(edl: dict, source_durations: dict) -> list[dict]:
    """Compute the output timeline: per range, the clamped padded source span, its output
    duration, and its cumulative output offset.

    source_durations: {label: duration_seconds}. Use a large sentinel if unknown.
    """
    pad = float(edl.get("pad_ms", DEFAULT_PAD_MS)) / 1000.0
    segs: list[dict] = []
    offset = 0.0
    for r in edl["ranges"]:
        label = r["source"]
        dur_src = float(source_durations.get(label, 10**9))
        s = max(0.0, float(r["start"]) - pad)
        e = min(dur_src, float(r["end"]) + pad)
        out_dur = max(0.0, e - s)
        segs.append(
            {
                "label": label,
                "src_start": s,
                "src_end": e,
                "out_dur": out_dur,
                "offset": offset,
                "grade": resolve_grade(r.get("grade", edl.get("grade"))),
            }
        )
        offset += out_dur
    return segs


def total_duration(edl: dict, source_durations: dict) -> float:
    return sum(s["out_dur"] for s in output_segments(edl, source_durations))


def srt_time(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(edl: dict, transcripts: dict, source_durations: dict) -> str:
    """Build an SRT on the OUTPUT timeline from per-source word transcripts.

    transcripts: {label: transcript_dict with 'words': [{word,start,end,speaker}]}.
    Applies the caption invariant: out_t = word_t - range.src_start + range.offset, then
    chunks words into groups of chunk_words.
    """
    sub = edl.get("subtitles", {"mode": "none"})
    if sub.get("mode") != "burn":
        return ""
    style_name = sub.get("style", "bold-overlay")
    _, uppercase, default_chunk = SUBTITLE_STYLES.get(
        style_name, SUBTITLE_STYLES["bold-overlay"]
    )
    chunk_words = int(sub.get("chunk_words", default_chunk))

    cues: list[tuple[float, float, str]] = []
    for seg in output_segments(edl, source_durations):
        words = (transcripts.get(seg["label"]) or {}).get("words", [])
        seg_end = seg["offset"] + seg["out_dur"]
        in_range = [
            w for w in words if seg["src_start"] <= float(w["start"]) < seg["src_end"]
        ]
        for i in range(0, len(in_range), chunk_words):
            group = in_range[i : i + chunk_words]
            if not group:
                continue
            out_start = float(group[0]["start"]) - seg["src_start"] + seg["offset"]
            out_end = float(group[-1]["end"]) - seg["src_start"] + seg["offset"]
            out_end = min(out_end, seg_end)
            if out_end <= out_start:
                out_end = out_start + 0.3
            text = " ".join(str(w["word"]).strip() for w in group).strip()
            if uppercase:
                text = text.upper()
            cues.append((out_start, out_end, text))

    cues.sort(key=lambda c: c[0])
    lines: list[str] = []
    for idx, (a, b, text) in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{srt_time(a)} --> {srt_time(b)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)
