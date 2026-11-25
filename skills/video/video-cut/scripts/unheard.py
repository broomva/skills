#!/usr/bin/env python3
"""unheard.py — Word-aligned UNHEARD retake & dropped-speech detector for video-cut.

Pure Python stdlib + ffmpeg (zero extra pip dependencies).

Decodes input audio/video to 16 kHz mono 16-bit PCM (or reads uncompressed 16-bit
PCM WAV directly), computes a 20 ms RMS loudness envelope in dBFS, detects
contiguous active-speech intervals using an adaptive noise floor, subtracts
word spans from a transcript JSON (padded by --margin-s), and flags any
uncovered active-speech stretches >= --min-gap-s as UNHEARD regions.

CLI:
    python3 unheard.py detect <media_path> --transcript <json>
        [--min-gap-s 0.6] [--margin-s 0.12] [--speech-db FLOAT]
        [--merge-pause-s 0.15] [--clip NAME] [--json] [--annotate-out TXT]

    python3 unheard.py annotate [<media_path>] --transcript <json>
        [--unheard DETECT_JSON] [-o OUT.txt]
        [--min-gap-s 0.6] [--margin-s 0.12] [--speech-db FLOAT]
        [--merge-pause-s 0.15] [--clip NAME]
"""

from __future__ import annotations

import argparse
import array
import json
import math
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FRAME_MS = 20.0
DEFAULT_MIN_GAP_S = 0.6
DEFAULT_MARGIN_S = 0.12
DEFAULT_MERGE_PAUSE_S = 0.15
DEFAULT_PHRASE_GAP_S = 0.5
ADAPTIVE_MARGIN_DB = 12.0
ADAPTIVE_FLOOR_DB = -42.0
SILENCE_FLOOR_DB = -120.0
SUGGESTED_ACTION = "inspect_possible_retake_or_dropped_speech"


# ---------------------------------------------------------------------------
# Audio decoding + 20ms RMS loudness envelope
# ---------------------------------------------------------------------------
def _read_pcm_wav_direct(path: Path) -> tuple[array.array, int] | None:
    """Read an uncompressed 16-bit PCM WAV directly without spawning ffmpeg.

    Returns (mono_s16_samples, sample_rate) or None if the file is not a plain
    16-bit PCM WAV (caller falls back to ffmpeg).
    """
    if path.suffix.lower() != ".wav":
        return None
    try:
        with wave.open(str(path), "rb") as wf:
            if wf.getcomptype() != "NONE" or wf.getsampwidth() != 2:
                return None
            nchannels = wf.getnchannels()
            framerate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
    except (wave.Error, EOFError, OSError):
        return None

    if len(raw) % 2 != 0:
        raw = raw[: len(raw) - 1]
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder == "big":
        samples.byteswap()

    if nchannels == 1:
        return samples, framerate
    if nchannels > 1:
        total_frames = len(samples) // nchannels
        mono = array.array("h")
        for i in range(0, total_frames * nchannels, nchannels):
            acc = 0
            for c in range(nchannels):
                acc += samples[i + c]
            mono.append(acc // nchannels)
        return mono, framerate
    return None


def decode_pcm_mono(
    media_path: str | Path, sample_rate: int = DEFAULT_SAMPLE_RATE
) -> tuple[array.array, int]:
    """Decode audio/video to mono 16-bit signed PCM.

    Reads uncompressed 16-bit PCM WAV directly; uses ffmpeg for all other formats.
    """
    path = Path(media_path)
    if not path.exists():
        raise FileNotFoundError(f"media file not found: {path}")

    direct = _read_pcm_wav_direct(path)
    if direct is not None:
        return direct

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg not found on PATH; install ffmpeg to decode non-WAV media"
        ) from exc

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg audio decode failed (exit {proc.returncode}): {err}")

    raw = proc.stdout
    if len(raw) % 2 != 0:
        raw = raw[: len(raw) - 1]
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples, sample_rate


def compute_rms_envelope(
    samples: array.array | list[int],
    sample_rate: int,
    frame_ms: float = DEFAULT_FRAME_MS,
) -> list[dict[str, float]]:
    """Compute a fixed-window (default 20 ms) RMS loudness envelope in dBFS."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if frame_ms <= 0:
        raise ValueError("frame_ms must be positive")

    n = len(samples)
    if n == 0:
        return []

    frame_samples = max(1, int(round(sample_rate * (frame_ms / 1000.0))))
    envelope: list[dict[str, float]] = []
    for i in range(0, n, frame_samples):
        chunk = samples[i : i + frame_samples]
        count = len(chunk)
        if count == 0:
            break
        sum_sq = 0
        for s in chunk:
            sum_sq += s * s
        rms_norm = math.sqrt(sum_sq / count) / 32768.0
        if rms_norm <= 1e-6:
            db = SILENCE_FLOOR_DB
        else:
            db = max(SILENCE_FLOOR_DB, 20.0 * math.log10(rms_norm))
        envelope.append(
            {
                "start": i / sample_rate,
                "end": (i + count) / sample_rate,
                "rms": rms_norm,
                "db": db,
            }
        )
    return envelope


# ---------------------------------------------------------------------------
# Adaptive noise floor & active-speech intervals
# ---------------------------------------------------------------------------
def estimate_noise_floor_db(
    envelope: list[dict[str, float]], percentile: float = 0.10
) -> float:
    """Estimate background noise floor dBFS as a low percentile of frame levels."""
    if not envelope:
        return SILENCE_FLOOR_DB
    dbs = sorted(frame["db"] for frame in envelope)
    idx = max(0, min(len(dbs) - 1, int(round(percentile * (len(dbs) - 1)))))
    return dbs[idx]


def compute_speech_threshold_db(
    envelope: list[dict[str, float]], speech_db: float | None = None
) -> tuple[float, float]:
    """Return (noise_floor_db, active_speech_threshold_db)."""
    noise_floor = estimate_noise_floor_db(envelope)
    if speech_db is not None:
        return noise_floor, float(speech_db)
    threshold = max(noise_floor + ADAPTIVE_MARGIN_DB, ADAPTIVE_FLOOR_DB)
    return noise_floor, threshold


def merge_intervals(
    intervals: list[tuple[float, float]], max_gap: float = 0.0
) -> list[tuple[float, float]]:
    """Sort and merge intervals separated by <= max_gap seconds."""
    cleaned = sorted(
        (float(s), float(e)) for s, e in intervals if float(e) > float(s)
    )
    if not cleaned:
        return []
    merged: list[tuple[float, float]] = [cleaned[0]]
    for start, end in cleaned[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + max_gap + 1e-9:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def detect_active_speech(
    envelope: list[dict[str, float]],
    threshold_db: float,
    merge_pause_s: float = DEFAULT_MERGE_PAUSE_S,
) -> list[tuple[float, float]]:
    """Detect contiguous active-speech intervals and merge tiny intra-word pauses."""
    raw: list[tuple[float, float]] = []
    cur_start: float | None = None
    cur_end: float | None = None

    for frame in envelope:
        if frame["db"] >= threshold_db:
            if cur_start is None:
                cur_start = frame["start"]
            cur_end = frame["end"]
        else:
            if cur_start is not None and cur_end is not None:
                raw.append((cur_start, cur_end))
                cur_start = None
                cur_end = None
    if cur_start is not None and cur_end is not None:
        raw.append((cur_start, cur_end))

    return merge_intervals(raw, max_gap=max(0.0, float(merge_pause_s)))


def subtract_intervals(
    active: list[tuple[float, float]], covered: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Subtract covered spans from active intervals, returning uncovered stretches."""
    if not active:
        return []
    merged_cov = merge_intervals(covered, max_gap=0.0)
    if not merged_cov:
        return list(active)

    uncovered: list[tuple[float, float]] = []
    cov_idx = 0
    n_cov = len(merged_cov)

    for a_start, a_end in merge_intervals(active, max_gap=0.0):
        while cov_idx < n_cov and merged_cov[cov_idx][1] <= a_start:
            cov_idx += 1

        cursor = a_start
        j = cov_idx
        while j < n_cov and merged_cov[j][0] < a_end:
            c_start, c_end = merged_cov[j]
            if c_start > cursor:
                uncovered.append((cursor, min(c_start, a_end)))
            if c_end > cursor:
                cursor = c_end
            if cursor >= a_end:
                break
            j += 1

        if cursor < a_end:
            uncovered.append((cursor, a_end))

    return uncovered


# ---------------------------------------------------------------------------
# Transcript loading (all common layouts)
# ---------------------------------------------------------------------------
def _parse_timed_text(item: Any) -> dict[str, Any] | None:
    """Parse a word or segment dict into {word, start, end}."""
    if not isinstance(item, dict):
        return None
    raw_start = item.get("start", item.get("start_s"))
    raw_end = item.get("end", item.get("end_s"))
    if raw_start is None or raw_end is None:
        return None
    try:
        start = float(raw_start)
        end = float(raw_end)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(start) and math.isfinite(end)) or end <= start or start < 0:
        return None
    text = item.get("word")
    if text is None:
        text = item.get("text", "")
    return {"word": str(text).strip(), "start": start, "end": end}


def _group_words_to_phrases(
    words: list[dict[str, Any]], gap: float = DEFAULT_PHRASE_GAP_S
) -> list[dict[str, Any]]:
    """Group sorted words into phrase lines separated by >= gap seconds."""
    if not words:
        return []
    phrases: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = [words[0]]
    for w in words[1:]:
        if w["start"] - cur[-1]["end"] >= gap:
            phrases.append(
                {
                    "start": cur[0]["start"],
                    "end": cur[-1]["end"],
                    "text": " ".join(x["word"] for x in cur if x["word"]).strip(),
                }
            )
            cur = [w]
        else:
            cur.append(w)
    if cur:
        phrases.append(
            {
                "start": cur[0]["start"],
                "end": cur[-1]["end"],
                "text": " ".join(x["word"] for x in cur if x["word"]).strip(),
            }
        )
    return [p for p in phrases if p["text"]]


def _extract_from_single_transcript(
    obj: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract (words, phrases) from one transcript dict."""
    words: list[dict[str, Any]] = []
    phrases: list[dict[str, Any]] = []

    raw_words = obj.get("words")
    if isinstance(raw_words, list):
        for w in raw_words:
            parsed = _parse_timed_text(w)
            if parsed is not None:
                words.append(parsed)

    raw_segments = obj.get("segments")
    if isinstance(raw_segments, list):
        for seg in raw_segments:
            if not isinstance(seg, dict):
                continue
            seg_parsed = _parse_timed_text(seg)
            if seg_parsed is not None and seg_parsed["word"]:
                phrases.append(
                    {
                        "start": seg_parsed["start"],
                        "end": seg_parsed["end"],
                        "text": seg_parsed["word"],
                    }
                )
            if not words:
                seg_words = seg.get("words")
                if isinstance(seg_words, list) and seg_words:
                    for sw in seg_words:
                        p = _parse_timed_text(sw)
                        if p is not None:
                            words.append(p)
                elif seg_parsed is not None:
                    words.append(seg_parsed)

    words.sort(key=lambda w: (w["start"], w["end"]))
    phrases.sort(key=lambda p: (p["start"], p["end"]))

    if not phrases and words:
        phrases = _group_words_to_phrases(words)
    return words, phrases


def _select_clip_entry(
    clips: Any, clip_name: str | None, media_path: str | Path | None
) -> list[dict[str, Any]]:
    """Select the target clip dict(s) from a `clips` dict or list."""
    stem = Path(media_path).stem if media_path is not None else None

    if isinstance(clips, dict):
        if clip_name is not None:
            if clip_name not in clips:
                raise KeyError(
                    f"clip {clip_name!r} not found in transcript clips "
                    f"(available: {sorted(clips.keys())})"
                )
            entry = clips[clip_name]
            return [entry] if isinstance(entry, dict) else []
        if stem is not None:
            if stem in clips and isinstance(clips[stem], dict):
                return [clips[stem]]
            for entry in clips.values():
                if isinstance(entry, dict) and entry.get("source"):
                    if Path(str(entry["source"])).stem == stem:
                        return [entry]
        if len(clips) == 1:
            only = next(iter(clips.values()))
            return [only] if isinstance(only, dict) else []
        return [v for v in clips.values() if isinstance(v, dict)]

    if isinstance(clips, list):
        dict_entries = [c for c in clips if isinstance(c, dict)]
        if clip_name is not None:
            for c in dict_entries:
                if c.get("id") == clip_name or c.get("name") == clip_name or c.get("clip") == clip_name:
                    return [c]
            raise KeyError(f"clip {clip_name!r} not found in transcript clips list")
        if stem is not None:
            for c in dict_entries:
                if c.get("id") == stem or c.get("name") == stem or c.get("clip") == stem:
                    return [c]
                if c.get("source") and Path(str(c["source"])).stem == stem:
                    return [c]
        if len(dict_entries) == 1:
            return dict_entries
        return dict_entries

    return []


def load_transcript_spans(
    transcript_data: dict[str, Any] | list[Any],
    clip_name: str | None = None,
    media_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load word spans and phrase lines from any supported transcript JSON layout.

    Supported shapes:
      - {"words": [{start, end, word}], "segments": [...]} (transcribe_local.py)
      - {"segments": [{start, end, text, words?: [...]}]}
      - {"clips": {"name": {"words": ..., "segments": ...}}} (or list of clips)
      - [{start, end, word|text}, ...]
    """
    if isinstance(transcript_data, list):
        return _extract_from_single_transcript({"words": transcript_data})

    if not isinstance(transcript_data, dict):
        raise ValueError("transcript JSON must be a JSON object or list")

    if "clips" in transcript_data:
        entries = _select_clip_entry(transcript_data["clips"], clip_name, media_path)
        all_words: list[dict[str, Any]] = []
        all_phrases: list[dict[str, Any]] = []
        for entry in entries:
            w, p = _extract_from_single_transcript(entry)
            all_words.extend(w)
            all_phrases.extend(p)
        all_words.sort(key=lambda x: (x["start"], x["end"]))
        all_phrases.sort(key=lambda x: (x["start"], x["end"]))
        if not all_phrases and all_words:
            all_phrases = _group_words_to_phrases(all_words)
        return all_words, all_phrases

    return _extract_from_single_transcript(transcript_data)


# ---------------------------------------------------------------------------
# UNHEARD region assembly & transcript annotation
# ---------------------------------------------------------------------------
def _region_loudness(
    envelope: list[dict[str, float]], start: float, end: float
) -> tuple[float, float]:
    """Compute (peak_db, mean_db) across envelope frames overlapping [start, end]."""
    overlapping = [
        f for f in envelope if f["end"] > start + 1e-9 and f["start"] < end - 1e-9
    ]
    if not overlapping:
        return SILENCE_FLOOR_DB, SILENCE_FLOOR_DB
    peak_db = max(f["db"] for f in overlapping)
    mean_power = sum(f["rms"] * f["rms"] for f in overlapping) / len(overlapping)
    mean_rms = math.sqrt(mean_power)
    if mean_rms <= 1e-6:
        mean_db = SILENCE_FLOOR_DB
    else:
        mean_db = max(SILENCE_FLOOR_DB, 20.0 * math.log10(mean_rms))
    return round(peak_db, 2), round(mean_db, 2)


def _surrounding_context(
    words: list[dict[str, Any]],
    start: float,
    end: float,
    margin_s: float,
    max_words: int = 6,
) -> tuple[str, str]:
    """Return (context_before, context_after) snippets around [start, end]."""
    before = [w["word"] for w in words if w["end"] <= start + margin_s + 1e-6 and w["word"]]
    after = [w["word"] for w in words if w["start"] >= end - margin_s - 1e-6 and w["word"]]
    return " ".join(before[-max_words:]), " ".join(after[:max_words])


def detect_unheard(
    media_path: str | Path,
    transcript: str | Path | dict[str, Any] | list[Any],
    *,
    min_gap_s: float = DEFAULT_MIN_GAP_S,
    margin_s: float = DEFAULT_MARGIN_S,
    speech_db: float | None = None,
    merge_pause_s: float = DEFAULT_MERGE_PAUSE_S,
    frame_ms: float = DEFAULT_FRAME_MS,
    clip_name: str | None = None,
) -> dict[str, Any]:
    """Detect uncovered active-speech intervals (UNHEARD regions) in media_path."""
    if min_gap_s <= 0:
        raise ValueError("min_gap_s must be positive")
    if margin_s < 0:
        raise ValueError("margin_s must be non-negative")

    transcript_label: str | None = None
    if isinstance(transcript, (str, Path)):
        t_path = Path(transcript)
        if not t_path.exists():
            raise FileNotFoundError(f"transcript file not found: {t_path}")
        transcript_data = json.loads(t_path.read_text(encoding="utf-8"))
        transcript_label = str(t_path)
    else:
        transcript_data = transcript

    samples, sample_rate = decode_pcm_mono(media_path)
    duration_s = len(samples) / sample_rate if sample_rate else 0.0
    envelope = compute_rms_envelope(samples, sample_rate, frame_ms=frame_ms)
    noise_floor_db, threshold_db = compute_speech_threshold_db(
        envelope, speech_db=speech_db
    )
    active = detect_active_speech(
        envelope, threshold_db=threshold_db, merge_pause_s=merge_pause_s
    )

    words, phrases = load_transcript_spans(
        transcript_data, clip_name=clip_name, media_path=media_path
    )
    covered = [
        (max(0.0, w["start"] - margin_s), w["end"] + margin_s)
        for w in words
    ]
    uncovered = subtract_intervals(active, covered)

    unheard_regions: list[dict[str, Any]] = []
    for u_start, u_end in uncovered:
        dur = u_end - u_start
        if dur + 1e-9 < min_gap_s:
            continue
        peak_db, mean_db = _region_loudness(envelope, u_start, u_end)
        ctx_before, ctx_after = _surrounding_context(
            words, u_start, u_end, margin_s=margin_s
        )
        unheard_regions.append(
            {
                "start": round(u_start, 3),
                "end": round(u_end, 3),
                "duration": round(dur, 3),
                "peak_db": peak_db,
                "mean_db": mean_db,
                "context_before": ctx_before,
                "context_after": ctx_after,
                "suggested_action": SUGGESTED_ACTION,
            }
        )

    return {
        "media": str(Path(media_path)),
        "transcript": transcript_label,
        "duration_s": round(duration_s, 3),
        "sample_rate": sample_rate,
        "frame_ms": frame_ms,
        "noise_floor_db": round(noise_floor_db, 2),
        "threshold_db": round(threshold_db, 2),
        "min_gap_s": min_gap_s,
        "margin_s": margin_s,
        "active_speech_count": len(active),
        "active_speech_intervals": [
            {"start": round(s, 3), "end": round(e, 3)} for s, e in active
        ],
        "unheard_count": len(unheard_regions),
        "unheard": unheard_regions,
        "phrases": phrases,
    }


def format_unheard_marker(region: dict[str, Any]) -> str:
    """Format one UNHEARD marker line for inline transcript annotation."""
    return (
        f"[UNHEARD {float(region['start']):.2f}s-{float(region['end']):.2f}s "
        f"({float(region['duration']):.2f}s, {float(region['mean_db']):.1f} dBFS)]"
    )


def annotate_transcript(
    phrases: list[dict[str, Any]], unheard_regions: list[dict[str, Any]]
) -> str:
    """Merge spoken transcript lines and [UNHEARD ...] markers chronologically."""
    timeline: list[tuple[float, int, str]] = []
    for p in phrases:
        text = str(p.get("text", "")).strip()
        if not text:
            continue
        start = float(p["start"])
        end = float(p["end"])
        timeline.append((start, 0, f"[{start:06.2f}s-{end:06.2f}s] {text}"))

    for u in unheard_regions:
        timeline.append((float(u["start"]), 1, format_unheard_marker(u)))

    timeline.sort(key=lambda item: (item[0], item[1]))
    if not timeline:
        return ""
    return "\n".join(line for _, _, line in timeline) + "\n"


def _human_detect_report(result: dict[str, Any]) -> str:
    lines = [
        f"media: {result['media']} ({result['duration_s']:.2f}s)",
        f"noise_floor: {result['noise_floor_db']:.1f} dBFS | "
        f"speech_threshold: {result['threshold_db']:.1f} dBFS | "
        f"min_gap: {result['min_gap_s']:.2f}s | margin: {result['margin_s']:.2f}s",
        f"unheard regions: {result['unheard_count']}",
    ]
    for u in result["unheard"]:
        lines.append(f"  {format_unheard_marker(u)}")
        if u["context_before"] or u["context_after"]:
            lines.append(
                f"    context: {u['context_before']!r} ... {u['context_after']!r}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _add_detection_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--transcript",
        required=True,
        help="Path to transcript JSON (words, segments, or clips layout).",
    )
    p.add_argument(
        "--min-gap-s",
        type=float,
        default=DEFAULT_MIN_GAP_S,
        help=f"Minimum uncovered speech stretch in seconds (default: {DEFAULT_MIN_GAP_S}).",
    )
    p.add_argument(
        "--margin-s",
        type=float,
        default=DEFAULT_MARGIN_S,
        help=f"Padding subtracted around each word span in seconds (default: {DEFAULT_MARGIN_S}).",
    )
    p.add_argument(
        "--speech-db",
        type=float,
        default=None,
        help="Explicit active-speech threshold in dBFS (overrides adaptive floor).",
    )
    p.add_argument(
        "--merge-pause-s",
        type=float,
        default=DEFAULT_MERGE_PAUSE_S,
        help=f"Merge intra-word pauses <= seconds (default: {DEFAULT_MERGE_PAUSE_S}).",
    )
    p.add_argument(
        "--clip",
        default=None,
        help="Optional clip key when transcript JSON uses a multi-clip 'clips' layout.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Word-aligned UNHEARD retake & dropped-speech detector.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser(
        "detect",
        help="Detect active speech stretches missing from a transcript JSON.",
    )
    p_detect.add_argument("media_path", help="Path to source audio or video file.")
    _add_detection_flags(p_detect)
    p_detect.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout.",
    )
    p_detect.add_argument(
        "--annotate-out",
        default=None,
        help="Write merged transcript + [UNHEARD ...] markers to this text file.",
    )

    p_ann = sub.add_parser(
        "annotate",
        help="Merge [UNHEARD ...] markers inline between spoken transcript lines.",
    )
    p_ann.add_argument(
        "media_path",
        nargs="?",
        default=None,
        help="Source audio/video path (optional when --unheard JSON is provided).",
    )
    _add_detection_flags(p_ann)
    p_ann.add_argument(
        "--unheard",
        default=None,
        help="Precomputed detect --json file (skips re-decoding media).",
    )
    p_ann.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output text file path (prints to stdout if omitted).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "detect":
            result = detect_unheard(
                args.media_path,
                args.transcript,
                min_gap_s=args.min_gap_s,
                margin_s=args.margin_s,
                speech_db=args.speech_db,
                merge_pause_s=args.merge_pause_s,
                clip_name=args.clip,
            )
            if args.annotate_out:
                out_txt = Path(args.annotate_out)
                out_txt.parent.mkdir(parents=True, exist_ok=True)
                annotated = annotate_transcript(result["phrases"], result["unheard"])
                out_txt.write_text(annotated, encoding="utf-8")

            if args.json:
                # Keep JSON output clean and focused on detection fields.
                payload = {k: v for k, v in result.items() if k != "phrases"}
                print(json.dumps(payload, indent=2))
            else:
                print(_human_detect_report(result))
            return 0

        if args.command == "annotate":
            if args.unheard:
                unheard_payload = json.loads(
                    Path(args.unheard).read_text(encoding="utf-8")
                )
                unheard_regions = (
                    unheard_payload.get("unheard", [])
                    if isinstance(unheard_payload, dict)
                    else unheard_payload
                )
                transcript_data = json.loads(
                    Path(args.transcript).read_text(encoding="utf-8")
                )
                _, phrases = load_transcript_spans(
                    transcript_data,
                    clip_name=args.clip,
                    media_path=args.media_path,
                )
            else:
                if not args.media_path:
                    print(
                        "error: annotate requires either <media_path> or --unheard <json>",
                        file=sys.stderr,
                    )
                    return 1
                result = detect_unheard(
                    args.media_path,
                    args.transcript,
                    min_gap_s=args.min_gap_s,
                    margin_s=args.margin_s,
                    speech_db=args.speech_db,
                    merge_pause_s=args.merge_pause_s,
                    clip_name=args.clip,
                )
                phrases = result["phrases"]
                unheard_regions = result["unheard"]

            annotated = annotate_transcript(phrases, unheard_regions)
            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(annotated, encoding="utf-8")
                print(str(out_path.resolve()))
            else:
                sys.stdout.write(annotated)
            return 0
    except (FileNotFoundError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
