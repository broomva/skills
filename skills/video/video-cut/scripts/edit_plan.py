#!/usr/bin/env python3
"""edit_plan.py — Typed editPlan.json v1 validator & deterministic FFmpeg compiler.

Separates editorial judgment (editPlan.json) from deterministic FFmpeg execution.
Pure Python stdlib + ffmpeg (zero extra pip dependencies).

CLI:
    python3 edit_plan.py validate <plan.json> [--check-files]
    python3 edit_plan.py compile  <plan.json> -o <out.mp4> [--check-files]
    python3 edit_plan.py render   <plan.json> -o <out.mp4> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# Fractional margins (from each frame edge) reserved for platform chrome.
SAFE_AREA_PRESETS: dict[str, dict[str, float]] = {
    "9:16-reels": {"top": 0.14, "bottom": 0.22, "left": 0.06, "right": 0.14},
    "16:9-youtube": {"top": 0.06, "bottom": 0.12, "left": 0.05, "right": 0.05},
    "1:1-square": {"top": 0.08, "bottom": 0.12, "left": 0.06, "right": 0.06},
}

MIN_PUNCH_SCALE = 1.0
MAX_PUNCH_SCALE = 2.0
MIN_DUCK_PAD_TAIL_S = 0.5
DEFAULT_CAPTION_Y_FRAC = 0.72
DEFAULT_CAPTION_X_FRAC = 0.50


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------
def _is_number(val: Any) -> bool:
    return (
        isinstance(val, (int, float))
        and not isinstance(val, bool)
        and math.isfinite(val)
    )


def _is_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _fmt_num(val: float) -> str:
    s = f"{float(val):.6f}".rstrip("0").rstrip(".")
    return s if s and s != "-0" else "0"


def _resolve_path(raw: str, base_dir: Path | None) -> Path:
    p = Path(raw)
    if p.is_absolute() or base_dir is None:
        return p
    return (base_dir / p).resolve()


# ---------------------------------------------------------------------------
# Safe-area resolution + schema validator
# ---------------------------------------------------------------------------
def resolve_safe_area(
    safe_area: Any,
) -> tuple[dict[str, float] | None, str | None]:
    """Resolve a safe_area preset name or custom {top,bottom,left,right} dict."""
    if safe_area is None:
        return None, None
    if isinstance(safe_area, str):
        if safe_area not in SAFE_AREA_PRESETS:
            valid = ", ".join(sorted(SAFE_AREA_PRESETS))
            return None, f"canvas.safe_area unknown preset {safe_area!r} (expected one of: {valid})"
        return dict(SAFE_AREA_PRESETS[safe_area]), None
    if isinstance(safe_area, dict):
        box: dict[str, float] = {}
        for side in ("top", "bottom", "left", "right"):
            v = safe_area.get(side)
            if not _is_number(v) or not (0.0 <= float(v) < 0.5):
                return (
                    None,
                    f"canvas.safe_area.{side} must be a finite number in [0.0, 0.5)",
                )
            box[side] = float(v)
        if box["top"] + box["bottom"] >= 1.0:
            return None, "canvas.safe_area top + bottom must be < 1.0"
        if box["left"] + box["right"] >= 1.0:
            return None, "canvas.safe_area left + right must be < 1.0"
        return box, None
    return (
        None,
        "canvas.safe_area must be a preset name or {top, bottom, left, right} object",
    )


def validate_plan(
    plan: Any,
    check_files: bool = False,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate an editPlan.json v1 payload and return {valid, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []
    base = Path(base_dir) if base_dir is not None else None

    if not isinstance(plan, dict):
        return {
            "valid": False,
            "errors": ["plan root must be a JSON object"],
            "warnings": [],
        }

    # --- version ---
    version = plan.get("version")
    if not _is_int(version) or version != SCHEMA_VERSION:
        errors.append(
            f"unsupported editPlan version {version!r} (expected {SCHEMA_VERSION})"
        )

    # --- canvas ---
    safe_area_box: dict[str, float] | None = None
    canvas = plan.get("canvas")
    if not isinstance(canvas, dict):
        errors.append("canvas must be an object with width, height, and fps")
    else:
        for dim in ("width", "height"):
            v = canvas.get(dim)
            if not _is_int(v) or v < 2:
                errors.append(f"canvas.{dim} must be an integer >= 2")
            elif v % 2 != 0:
                errors.append(
                    f"canvas.{dim} ({v}) must be even for yuv420p compatibility"
                )
        fps = canvas.get("fps")
        if not _is_number(fps) or float(fps) <= 0 or float(fps) > 240:
            errors.append("canvas.fps must be a finite number in (0, 240]")

        safe_area_box, sa_err = resolve_safe_area(canvas.get("safe_area"))
        if sa_err:
            errors.append(sa_err)

    # --- clips ---
    clips = plan.get("clips")
    total_dur = 0.0
    if not isinstance(clips, list) or not clips:
        errors.append("clips must be a non-empty list")
    else:
        seen_ids: set[str] = set()
        for idx, clip in enumerate(clips):
            prefix = f"clips[{idx}]"
            if not isinstance(clip, dict):
                errors.append(f"{prefix} must be an object")
                continue

            cid = clip.get("id")
            if not isinstance(cid, str) or not cid.strip():
                errors.append(f"{prefix}.id must be a non-empty string")
            elif cid in seen_ids:
                errors.append(f"{prefix}.id duplicate clip id {cid!r}")
            else:
                seen_ids.add(cid)

            src = clip.get("source")
            if not isinstance(src, str) or not src.strip():
                errors.append(f"{prefix}.source must be a non-empty string")
            elif check_files:
                resolved = _resolve_path(src, base)
                if not resolved.exists():
                    errors.append(f"{prefix}.source file not found: {resolved}")
                else:
                    info = _probe_media_streams(resolved)
                    if info is not None:
                        if not info["has_video"]:
                            errors.append(f"{prefix}.source has no video stream: {resolved}")
                        elif info.get("packet_probe_error") and info["video_dur_s"] is None:
                            errors.append(
                                f"{prefix}.source video duration could not be verified ({info['packet_probe_error']}): {resolved}"
                            )
                        elif (
                            info["video_dur_s"] is not None
                            and info["video_end_s"] is not None
                            and info["video_dur_s"] > 0.1
                            and _is_number(clip.get("in_s"))
                            and _is_number(clip.get("out_s"))
                        ):
                            in_v = float(clip["in_s"])
                            out_v = float(clip["out_s"])
                            v_start = float(info["video_start_s"])
                            v_end = float(info["video_end_s"])
                            if in_v < v_start - 0.05:
                                errors.append(
                                    f"{prefix}.in_s ({in_v:.3f}s) starts before source video stream ({v_start:.3f}s)"
                                )
                            if in_v >= v_end - 1e-6:
                                errors.append(
                                    f"{prefix}.in_s ({in_v:.3f}s) is at/past source video end ({v_end:.3f}s)"
                                )
                            elif out_v > v_end + 0.05:
                                errors.append(
                                    f"{prefix}.out_s ({out_v:.3f}s) exceeds source video end ({v_end:.3f}s)"
                                )

            in_s = clip.get("in_s")
            out_s = clip.get("out_s")
            if not _is_number(in_s) or not _is_number(out_s):
                errors.append(f"{prefix} requires numeric in_s and out_s")
            else:
                in_f, out_f = float(in_s), float(out_s)
                if in_f < 0.0:
                    errors.append(f"{prefix}.in_s ({in_f}) must be >= 0")
                if out_f <= 0.0:
                    errors.append(f"{prefix}.out_s ({out_f}) must be > 0")
                if in_f >= out_f:
                    errors.append(
                        f"{prefix} requires in_s < out_s (got in_s={in_f}, out_s={out_f})"
                    )
                else:
                    dur = out_f - in_f
                    total_dur += dur
                    if dur < 0.05:
                        warnings.append(
                            f"{prefix} duration ({dur:.3f}s) is shorter than 50ms"
                        )

            punch = clip.get("punch_in")
            if punch is not None:
                if not isinstance(punch, dict):
                    errors.append(f"{prefix}.punch_in must be an object")
                else:
                    scale = punch.get("scale")
                    if not _is_number(scale) or not (
                        MIN_PUNCH_SCALE <= float(scale) <= MAX_PUNCH_SCALE
                    ):
                        errors.append(
                            f"{prefix}.punch_in.scale ({scale!r}) must be in "
                            f"[{MIN_PUNCH_SCALE}, {MAX_PUNCH_SCALE}]"
                        )
                    for axis in ("anchor_x", "anchor_y"):
                        if axis in punch:
                            av = punch[axis]
                            if not _is_number(av) or not (0.0 <= float(av) <= 1.0):
                                errors.append(
                                    f"{prefix}.punch_in.{axis} ({av!r}) must be in [0.0, 1.0]"
                                )

            grade = clip.get("grade")
            if grade is not None:
                if not isinstance(grade, dict):
                    errors.append(f"{prefix}.grade must be an object")
                else:
                    bounds = {
                        "brightness": (-1.0, 1.0),
                        "contrast": (0.0, 3.0),
                        "saturation": (0.0, 3.0),
                    }
                    for field, (lo, hi) in bounds.items():
                        if field in grade:
                            gv = grade[field]
                            if not _is_number(gv) or not (lo <= float(gv) <= hi):
                                errors.append(
                                    f"{prefix}.grade.{field} ({gv!r}) must be in [{lo}, {hi}]"
                                )

            if "gain_db" in clip:
                gain_db = clip["gain_db"]
                if not _is_number(gain_db):
                    errors.append(f"{prefix}.gain_db must be a finite number")
                elif float(gain_db) > 18.0:
                    warnings.append(
                        f"{prefix}.gain_db ({gain_db} dB) exceeds +18 dB and may clip"
                    )

    # --- audio ---
    audio = plan.get("audio")
    if audio is not None:
        if not isinstance(audio, dict):
            errors.append("audio must be an object")
        else:
            if "target_lufs" in audio:
                target_lufs = audio["target_lufs"]
                if not _is_number(target_lufs) or not (-70.0 <= float(target_lufs) <= -5.0):
                    errors.append(
                        f"audio.target_lufs ({target_lufs!r}) must be in [-70.0, -5.0]"
                    )

            music = audio.get("music")
            if music is not None:
                if not isinstance(music, dict):
                    errors.append("audio.music must be an object")
                else:
                    msrc = music.get("source")
                    if not isinstance(msrc, str) or not msrc.strip():
                        errors.append("audio.music.source must be a non-empty string")
                    elif check_files:
                        resolved = _resolve_path(msrc, base)
                        if not resolved.exists():
                            errors.append(
                                f"audio.music.source file not found: {resolved}"
                            )

                    if "gain_db" in music:
                        if not _is_number(music["gain_db"]):
                            errors.append("audio.music.gain_db must be a finite number")

                    ducking_active = False
                    if "duck_db" in music:
                        duck_db = music["duck_db"]
                        if not _is_number(duck_db):
                            errors.append("audio.music.duck_db must be a finite number")
                        elif float(duck_db) != 0.0:
                            ducking_active = True

                    if "pad_tail_s" in music:
                        pad_tail = music["pad_tail_s"]
                        if not _is_number(pad_tail):
                            errors.append(
                                "audio.music.pad_tail_s must be a finite number"
                            )
                        elif float(pad_tail) < MIN_DUCK_PAD_TAIL_S:
                            errors.append(
                                f"audio.music.pad_tail_s ({pad_tail}) must be >= "
                                f"{MIN_DUCK_PAD_TAIL_S}s to prevent FFmpeg "
                                "sidechaincompress early music truncation"
                            )
                    elif ducking_active:
                        errors.append(
                            f"audio.music.pad_tail_s (>= {MIN_DUCK_PAD_TAIL_S}s) is "
                            "required when sidechain ducking (duck_db) is enabled"
                        )

    # --- captions ---
    captions = plan.get("captions")
    if captions is not None:
        if not isinstance(captions, dict):
            errors.append("captions must be an object")
        else:
            enabled = captions.get("enabled")
            if not isinstance(enabled, bool):
                errors.append("captions.enabled must be a boolean")
                enabled = False

            safe_zone_check = captions.get("safe_zone_check", True)
            if not isinstance(safe_zone_check, bool):
                errors.append("captions.safe_zone_check must be a boolean")
                safe_zone_check = True

            if enabled and captions.get("safe_zone_check") is True and safe_area_box is None:
                warnings.append(
                    "captions.safe_zone_check is true but canvas.safe_area is not set"
                )

            entries = captions.get("entries")
            if entries is not None and not isinstance(entries, list):
                errors.append("captions.entries must be a list")
            elif enabled and not entries:
                warnings.append("captions.enabled is true but captions.entries is empty")

            if isinstance(entries, list):
                for c_idx, entry in enumerate(entries):
                    cprefix = f"captions.entries[{c_idx}]"
                    if not isinstance(entry, dict):
                        errors.append(f"{cprefix} must be an object")
                        continue
                    cs = entry.get("start_s")
                    ce = entry.get("end_s")
                    if not _is_number(cs) or not _is_number(ce):
                        errors.append(f"{cprefix} requires numeric start_s and end_s")
                    else:
                        cs_f, ce_f = float(cs), float(ce)
                        if cs_f < 0.0 or ce_f <= cs_f:
                            errors.append(
                                f"{cprefix} requires 0 <= start_s < end_s "
                                f"(got {cs_f}..{ce_f})"
                            )
                        elif total_dur > 0.0 and ce_f > total_dur + 1e-6:
                            warnings.append(
                                f"{cprefix} end_s ({ce_f:.2f}s) exceeds total clip "
                                f"duration ({total_dur:.2f}s)"
                            )

                    txt = entry.get("text")
                    if not isinstance(txt, str) or not txt.strip():
                        errors.append(f"{cprefix}.text must be a non-empty string")

                    y_frac = entry.get("y_frac", DEFAULT_CAPTION_Y_FRAC)
                    x_frac = entry.get("x_frac", DEFAULT_CAPTION_X_FRAC)
                    if not _is_number(y_frac) or not (0.0 <= float(y_frac) <= 1.0):
                        errors.append(
                            f"{cprefix}.y_frac ({y_frac!r}) must be in [0.0, 1.0]"
                        )
                        y_ok = False
                    else:
                        y_ok = True

                    if not _is_number(x_frac) or not (0.0 <= float(x_frac) <= 1.0):
                        errors.append(
                            f"{cprefix}.x_frac ({x_frac!r}) must be in [0.0, 1.0]"
                        )
                        x_ok = False
                    else:
                        x_ok = True

                    if enabled and safe_zone_check and safe_area_box is not None:
                        cw = int(canvas["width"]) if isinstance(canvas, dict) and _is_int(canvas.get("width")) and int(canvas["width"]) > 0 else 1080
                        ch = int(canvas["height"]) if isinstance(canvas, dict) and _is_int(canvas.get("height")) and int(canvas["height"]) > 0 else 1920
                        fs = max(20, int(round(ch * 0.042)))
                        clean_t = txt.strip() if isinstance(txt, str) else ""
                        est_px = sum(
                            1.08 if ch_i in "WMwm@%#" else (0.78 if ch_i.isupper() else 0.66)
                            for ch_i in (clean_t or "X")
                        ) * fs + 8.0
                        half_h = (fs * 1.35) / (2.0 * ch)
                        half_w = est_px / (2.0 * cw)
                        if y_ok:
                            yf = float(y_frac)
                            min_y = safe_area_box["top"]
                            max_y = 1.0 - safe_area_box["bottom"]
                            if (yf - half_h) < min_y - 1e-9 or (yf + half_h) > max_y + 1e-9:
                                errors.append(
                                    f"{cprefix}.y_frac ({yf:.3f}) caption box [{yf - half_h:.3f}, {yf + half_h:.3f}] "
                                    f"violates safe_area vertical bounds [{min_y:.3f}, {max_y:.3f}]"
                                )
                        if x_ok:
                            xf = float(x_frac)
                            min_x = safe_area_box["left"]
                            max_x = 1.0 - safe_area_box["right"]
                            if (xf - half_w) < min_x - 1e-9 or (xf + half_w) > max_x + 1e-9:
                                errors.append(
                                    f"{cprefix}.x_frac ({xf:.3f}) caption box [{xf - half_w:.3f}, {xf + half_w:.3f}] "
                                    f"violates safe_area horizontal bounds [{min_x:.3f}, {max_x:.3f}]"
                                )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Deterministic FFmpeg filter_complex compiler
# ---------------------------------------------------------------------------
def _escape_drawtext(text: str) -> str:
    """Escape text for FFmpeg filtergraph + drawtext option parser (with expansion=none)."""
    cleaned = text.replace("\r", "").replace("\n", " ")
    return (
        cleaned.replace("\\", "\\\\\\\\")
        .replace("'", "\\\\\\'")
        .replace(":", "\\\\\\:")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _escape_filter_path(path: Path) -> str:
    """Escape a filesystem path for FFmpeg drawtext textfile= option."""
    s = str(path)
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace(";", "\\;")


def _parse_fps_ratio(val: Any) -> float | None:
    if not isinstance(val, str) or not val or val == "0/0":
        return None
    try:
        if "/" in val:
            num, den = val.split("/", 1)
            f = float(num) / float(den)
        else:
            f = float(val)
        return f if math.isfinite(f) and f > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _probe_media_streams(src: Path, *, count_video_packets: bool = False) -> dict[str, Any] | None:
    """Probe video/audio stream presence, start_time, packet count, and real video duration via ffprobe."""
    if not src.exists():
        return None
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,duration,start_time,nb_frames,avg_frame_rate,r_frame_rate,codec_name:format=duration",
                "-of",
                "json",
                str(src),
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    streams = data.get("streams") or []
    v_streams = [s for s in streams if s.get("codec_type") == "video"]
    a_streams = [s for s in streams if s.get("codec_type") == "audio"]
    fmt_dur = None
    raw_fmt = (data.get("format") or {}).get("duration")
    if raw_fmt is not None:
        try:
            v = float(raw_fmt)
            if math.isfinite(v) and v > 0:
                fmt_dur = v
        except (TypeError, ValueError):
            pass
    v_dur = None
    v_start = 0.0
    v_packets = None
    packet_probe_error = None
    if v_streams:
        vs0 = v_streams[0]
        raw_vd = vs0.get("duration")
        if raw_vd is not None:
            try:
                v = float(raw_vd)
                if math.isfinite(v) and v > 0:
                    v_dur = v
            except (TypeError, ValueError):
                pass
        raw_vs = vs0.get("start_time")
        if raw_vs is not None:
            try:
                vs = float(raw_vs)
                if math.isfinite(vs) and vs >= 0:
                    v_start = vs
            except (TypeError, ValueError):
                pass
        raw_nf = vs0.get("nb_frames")
        if raw_nf is not None and str(raw_nf).isdigit():
            v_packets = int(raw_nf)
        # Containers like Matroska/WebM omit stream.duration; count actual video packets so
        # a longer audio track cannot mask a shorter video stream.
        if v_dur is None or count_video_packets:
            pkt_proc = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "packet=pts_time,dts_time,duration_time",
                    "-of",
                    "csv=p=0",
                    str(src),
                ],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            pkt_err = pkt_proc.stderr.strip()
            if pkt_proc.returncode == 0 and not pkt_err:
                lines = [ln.strip() for ln in pkt_proc.stdout.splitlines() if ln.strip()]
                v_packets = len(lines)
                if v_dur is None and lines:
                    min_pts = None
                    max_end = None
                    for ln in lines:
                        parts = [p.strip() for p in ln.split(",")]
                        t_raw = parts[0] if len(parts) > 0 else ""
                        if not t_raw or t_raw == "N/A":
                            t_raw = parts[1] if len(parts) > 1 else ""
                        d_raw = parts[2] if len(parts) > 2 else ""
                        try:
                            t_val = float(t_raw)
                        except (TypeError, ValueError):
                            continue
                        if not math.isfinite(t_val):
                            continue
                        try:
                            d_val = float(d_raw) if d_raw and d_raw != "N/A" else 0.0
                            if not math.isfinite(d_val) or d_val < 0:
                                d_val = 0.0
                        except (TypeError, ValueError):
                            d_val = 0.0
                        if min_pts is None or t_val < min_pts:
                            min_pts = t_val
                        end_t = t_val + d_val
                        if max_end is None or end_t > max_end:
                            max_end = end_t
                    if min_pts is not None and max_end is not None and max_end > min_pts:
                        v_start = max(0.0, min_pts)
                        v_dur = max_end - v_start
            else:
                # Fail closed: never trust header nb_frames or container duration (which may reflect a longer audio tail)
                # when live packet inspection reported errors or exited nonzero.
                v_packets = None
                packet_probe_error = pkt_err or f"ffprobe packet probe exited {pkt_proc.returncode}"
    eff_v_dur = v_dur if v_dur is not None else (None if packet_probe_error else fmt_dur)
    v_end = (v_start + eff_v_dur) if eff_v_dur is not None else None
    return {
        "has_video": bool(v_streams),
        "has_audio": bool(a_streams),
        "video_start_s": v_start,
        "video_dur_s": eff_v_dur,
        "video_end_s": v_end,
        "video_packets": v_packets,
        "packet_probe_error": packet_probe_error,
        "format_dur_s": fmt_dur,
    }


def _probe_has_audio(src: Path) -> bool:
    """Return True if media file has at least one audio stream (defaults True if file absent)."""
    info = _probe_media_streams(src)
    if info is None:
        return True
    return bool(info["has_audio"])


def _punch_in_crop_filter(punch_in: dict[str, Any]) -> str:
    """Build deterministic FFmpeg crop centered on (anchor_x, anchor_y) within bounds."""
    scale = float(punch_in["scale"])
    ax = float(punch_in.get("anchor_x", 0.5))
    ay = float(punch_in.get("anchor_y", 0.5))
    return (
        f"crop="
        f"w='max(min(2,iw),trunc(iw/{_fmt_num(scale)}/2)*2)':"
        f"h='max(min(2,ih),trunc(ih/{_fmt_num(scale)}/2)*2)':"
        f"x='max(0,min(iw-ow,{_fmt_num(ax)}*iw-ow/2))':"
        f"y='max(0,min(ih-oh,{_fmt_num(ay)}*ih-oh/2))'"
    )


def _eq_grade_filter(grade: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("brightness", "contrast", "saturation"):
        if key in grade and grade[key] is not None:
            parts.append(f"{key}={_fmt_num(float(grade[key]))}")
    if not parts:
        return None
    return "eq=" + ":".join(parts)


def compile_plan(
    plan: dict[str, Any],
    output_path: str | Path,
    *,
    base_dir: str | Path | None = None,
    caption_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate and compile an editPlan.json v1 into a deterministic ffmpeg command spec."""
    validation = validate_plan(plan, check_files=False, base_dir=base_dir)
    if not validation["valid"]:
        raise ValueError("invalid editPlan: " + "; ".join(validation["errors"]))

    base = Path(base_dir) if base_dir is not None else None
    cap_dir = Path(caption_dir) if caption_dir is not None else None
    canvas = plan["canvas"]
    width = int(canvas["width"])
    height = int(canvas["height"])
    fps = float(canvas["fps"])
    safe_area_box, _ = resolve_safe_area(canvas.get("safe_area"))
    clips = plan["clips"]
    audio = plan.get("audio") or {}
    music = audio.get("music")
    captions = plan.get("captions") or {}

    inputs: list[str] = []
    fc_parts: list[str] = []
    total_dur = 0.0

    for i, clip in enumerate(clips):
        src_path = _resolve_path(clip["source"], base)
        src = str(src_path)
        if src_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            inputs.extend(["-loop", "1", "-framerate", _fmt_num(fps), "-i", src])
        else:
            inputs.extend(["-i", src])
        in_s = float(clip["in_s"])
        out_s = float(clip["out_s"])
        clip_dur = out_s - in_s
        total_dur += clip_dur

        v_ops = [
            f"trim=start={_fmt_num(in_s)}:end={_fmt_num(out_s)}",
            "setpts=PTS-STARTPTS",
        ]
        if clip.get("punch_in") is not None:
            v_ops.append(_punch_in_crop_filter(clip["punch_in"]))
        v_ops.extend(
            [
                f"scale={width}:{height}:force_original_aspect_ratio=decrease",
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "setsar=1",
                f"fps={_fmt_num(fps)}",
            ]
        )
        if clip.get("grade") is not None:
            eq_f = _eq_grade_filter(clip["grade"])
            if eq_f:
                v_ops.append(eq_f)
        v_ops.append("format=yuv420p")
        fc_parts.append(f"[{i}:v]" + ",".join(v_ops) + f"[v{i}]")

        # Handle silent B-roll clips cleanly (anullsrc) and pad short clip audio to full clip_dur
        has_audio = clip.get("has_audio")
        if has_audio is None:
            has_audio = _probe_has_audio(src_path)
        if has_audio:
            a_ops = [
                "aresample=48000:async=1:first_pts=0",
                "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
                f"apad=whole_dur={_fmt_num(out_s + 0.1)}",
                f"atrim=start={_fmt_num(in_s)}:end={_fmt_num(out_s)}",
                "asetpts=PTS-STARTPTS",
            ]
            gain_db = clip.get("gain_db")
            if gain_db is not None and float(gain_db) != 0.0:
                a_ops.append(f"volume={_fmt_num(float(gain_db))}dB")
            fc_parts.append(f"[{i}:a]" + ",".join(a_ops) + f"[a{i}]")
        else:
            fc_parts.append(
                f"anullsrc=r=48000:cl=stereo,"
                f"atrim=start=0:end={_fmt_num(clip_dur)},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )

    # Concatenate all clips in order
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(len(clips)))
    fc_parts.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=1[vcat][acat]")

    # Video final stage: captions applied LAST with expansion=none + safe-area clamping
    v_cur = "[vcat]"
    if captions.get("enabled") and captions.get("entries"):
        font_size = max(20, int(round(height * 0.042)))
        min_x_px = int(round(safe_area_box["left"] * width)) if safe_area_box else 0
        max_x_pad = int(round(safe_area_box["right"] * width)) if safe_area_box else 0
        min_y_px = int(round(safe_area_box["top"] * height)) if safe_area_box else 0
        max_y_pad = int(round(safe_area_box["bottom"] * height)) if safe_area_box else 0
        for c_idx, entry in enumerate(captions["entries"]):
            nxt = f"[vcap{c_idx}]"
            raw_txt = str(entry["text"]).strip()
            if cap_dir is not None:
                cap_file = cap_dir / f"caption_{c_idx}.txt"
                cap_file.write_text(raw_txt, encoding="utf-8")
                text_opt = f"textfile={_escape_filter_path(cap_file)}"
            else:
                text_opt = f"text={_escape_drawtext(raw_txt)}"
            cs = float(entry["start_s"])
            ce = float(entry["end_s"])
            xf = float(entry.get("x_frac", DEFAULT_CAPTION_X_FRAC))
            yf = float(entry.get("y_frac", DEFAULT_CAPTION_Y_FRAC))
            x_expr = f"max({min_x_px},min(w-{max_x_pad}-tw,{_fmt_num(xf)}*w-tw/2))"
            y_expr = f"max({min_y_px},min(h-{max_y_pad}-th,{_fmt_num(yf)}*h-th/2))"
            dt = (
                f"drawtext={text_opt}:expansion=none:"
                f"fontsize={font_size}:fontcolor=white:"
                f"borderw=2:bordercolor=black:"
                f"x='{x_expr}':"
                f"y='{y_expr}':"
                f"enable='between(t,{_fmt_num(cs)},{_fmt_num(ce)})'"
            )
            fc_parts.append(f"{v_cur}{dt}{nxt}")
            v_cur = nxt

    # Audio final stage: optional music bed with tail padding + optional sidechaincompress
    a_cur = "[acat]"
    if music is not None:
        m_idx = len(clips)
        msrc = str(_resolve_path(music["source"], base))
        inputs.extend(["-stream_loop", "-1", "-i", msrc])

        music_gain = float(music.get("gain_db", -12.0))
        duck_db = music.get("duck_db")
        ducking_active = duck_db is not None and float(duck_db) != 0.0
        pad_tail = float(music.get("pad_tail_s", MIN_DUCK_PAD_TAIL_S))
        padded_dur = total_dur + pad_tail

        fc_parts.append(
            f"[{m_idx}:a]aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"volume={_fmt_num(music_gain)}dB,"
            f"apad=pad_dur={_fmt_num(pad_tail)},"
            f"atrim=start=0:end={_fmt_num(padded_dur)},"
            "asetpts=PTS-STARTPTS[mus_pre]"
        )

        if ducking_active:
            fc_parts.append("[acat]asplit=2[voice_mix][voice_sc]")
            fc_parts.append(
                f"[voice_sc]apad=pad_dur={_fmt_num(pad_tail)},"
                f"atrim=start=0:end={_fmt_num(padded_dur)},"
                "asetpts=PTS-STARTPTS[sc_pad]"
            )
            ratio = min(20.0, max(2.0, abs(float(duck_db)) / 2.0))
            fc_parts.append(
                f"[mus_pre][sc_pad]sidechaincompress="
                f"threshold=0.02:ratio={ratio:.2f}:attack=20:release=250[mus_ducked]"
            )
            fc_parts.append(
                f"[mus_ducked]atrim=start=0:end={_fmt_num(total_dur)},"
                "asetpts=PTS-STARTPTS[mus_final]"
            )
            voice_in = "[voice_mix]"
        else:
            fc_parts.append(
                f"[mus_pre]atrim=start=0:end={_fmt_num(total_dur)},"
                "asetpts=PTS-STARTPTS[mus_final]"
            )
            voice_in = "[acat]"

        fc_parts.append(
            f"{voice_in}[mus_final]amix=inputs=2:duration=longest:"
            f"dropout_transition=0:normalize=0,"
            f"atrim=start=0:end={_fmt_num(total_dur)},asetpts=PTS-STARTPTS[abus]"
        )
        a_cur = "[abus]"

    target_lufs = audio.get("target_lufs")
    if target_lufs is not None:
        fc_parts.append(
            f"{a_cur}loudnorm=I={float(target_lufs):.1f}:TP=-1.5:LRA=11[aout]"
        )
        a_cur = "[aout]"

    filter_complex = ";".join(fc_parts)
    out_str = str(output_path)
    argv = [
        "ffmpeg",
        "-y",
        "-copyts",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        v_cur,
        "-map",
        a_cur,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        out_str,
    ]
    return {
        "argv": argv,
        "filter_complex": filter_complex,
        "output": out_str,
        "total_duration_s": round(total_dur, 6),
        "warnings": validation["warnings"],
    }


def build_ffmpeg_command(
    plan: dict[str, Any],
    output_path: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> list[str]:
    """Return the deterministic ffmpeg argv list for plan -> output_path."""
    return compile_plan(plan, output_path, base_dir=base_dir)["argv"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, compile, and render typed editPlan.json v1 files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate an editPlan.json file.")
    p_val.add_argument("plan_path", help="Path to editPlan.json.")
    p_val.add_argument(
        "--check-files",
        action="store_true",
        help="Verify referenced source media files exist on disk.",
    )

    p_comp = sub.add_parser(
        "compile",
        help="Compile an editPlan.json into a deterministic ffmpeg argv + filter_complex JSON.",
    )
    p_comp.add_argument("plan_path", help="Path to editPlan.json.")
    p_comp.add_argument(
        "-o",
        "--output",
        required=True,
        help="Destination MP4 output path.",
    )
    p_comp.add_argument(
        "--check-files",
        action="store_true",
        help="Verify referenced source media files exist on disk.",
    )

    p_rend = sub.add_parser(
        "render",
        help="Validate, compile, and execute ffmpeg to render the output MP4.",
    )
    p_rend.add_argument("plan_path", help="Path to editPlan.json.")
    p_rend.add_argument(
        "-o",
        "--output",
        required=True,
        help="Destination MP4 output path.",
    )
    p_rend.add_argument(
        "--dry-run",
        action="store_true",
        help="Print exact argv + filter_complex JSON without running ffmpeg.",
    )
    return parser


def _load_plan_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan_path = Path(args.plan_path)
    if not plan_path.exists():
        print(f"error: plan file not found: {plan_path}", file=sys.stderr)
        return 1

    try:
        plan = _load_plan_file(plan_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: failed to read plan JSON: {exc}", file=sys.stderr)
        return 1

    base_dir = plan_path.resolve().parent

    if args.command == "validate":
        res = validate_plan(plan, check_files=args.check_files, base_dir=base_dir)
        print(json.dumps(res, indent=2))
        return 0 if res["valid"] else 1

    if args.command == "compile":
        res = validate_plan(plan, check_files=args.check_files, base_dir=base_dir)
        if not res["valid"]:
            print(json.dumps(res, indent=2), file=sys.stderr)
            return 1
        compiled = compile_plan(plan, args.output, base_dir=base_dir)
        print(json.dumps(compiled, indent=2))
        return 0

    if args.command == "render":
        res = validate_plan(
            plan, check_files=not args.dry_run, base_dir=base_dir
        )
        if not res["valid"]:
            print(json.dumps(res, indent=2), file=sys.stderr)
            return 1
        if args.dry_run:
            compiled = compile_plan(plan, args.output, base_dir=base_dir)
            print(json.dumps(compiled, indent=2))
            return 0

        if shutil.which("ffprobe") is None:
            print("error: ffprobe not found on PATH; ffprobe is required to validate and verify renders", file=sys.stderr)
            return 1

        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="edit_plan_caps_") as cap_tmp:
            compiled = compile_plan(
                plan, args.output, base_dir=base_dir, caption_dir=Path(cap_tmp)
            )
            try:
                proc = subprocess.run(
                    compiled["argv"],
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    check=False,
                )
            except FileNotFoundError:
                print("error: ffmpeg not found on PATH", file=sys.stderr)
                return 1

        if proc.returncode != 0:
            print(
                f"error: ffmpeg failed (exit {proc.returncode}):\n{proc.stderr}",
                file=sys.stderr,
            )
            return 1

        out_info = _probe_media_streams(out_path, count_video_packets=True)
        if out_info is None:
            print("error: ffprobe is required to verify rendered output; cannot confirm video stream", file=sys.stderr)
            return 1
        if not out_info["has_video"]:
            print("error: rendered output contains no video stream (check clip in_s/out_s bounds)", file=sys.stderr)
            return 1
        exp_dur = sum(float(c["out_s"]) - float(c["in_s"]) for c in plan["clips"])
        fps_val = float(plan["canvas"]["fps"])
        tol = max(0.2, 2.0 / max(1.0, fps_val))
        if out_info["video_dur_s"] is None or abs(out_info["video_dur_s"] - exp_dur) > tol:
            print(
                f"error: rendered video duration ({out_info['video_dur_s']}s) differs from planned {exp_dur:.3f}s by > {tol:.3f}s",
                file=sys.stderr,
            )
            return 1
        min_frames = max(1, int(math.floor(exp_dur * fps_val)) - 2)
        if out_info["video_packets"] is None:
            detail = out_info.get("packet_probe_error") or "packet probe failed"
            print(f"error: output video packet verification failed ({detail})", file=sys.stderr)
            return 1
        if out_info["video_packets"] < min_frames:
            print(
                f"error: rendered video has only {out_info['video_packets']} frames (expected >= {min_frames} for {exp_dur:.3f}s @ {fps_val}fps)",
                file=sys.stderr,
            )
            return 1
        print(str(out_path.resolve()))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
