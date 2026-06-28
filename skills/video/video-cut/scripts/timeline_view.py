#!/usr/bin/env python3
"""timeline_view.py — on-demand visual composite for a video time range.

Part of the `video-cut` skill (local video editor). Renders a single PNG that
stacks a horizontal filmstrip (N frames sampled evenly across [start, end])
above a waveform image of the same range. ffmpeg-only — no PIL dependency.

This is the "on-demand visual layer" the agent calls at decision points
(NOT a scanning tool). Call it when you need to *see* a range before deciding
where to cut.

CLI:
    python3 timeline_view.py <video> <start> <end> [-o OUT.png] [--frames N] [--edit-dir DIR]

Example:
    python3 timeline_view.py clip.mp4 12.5 18.0 --frames 10
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

# Per-frame width used in the filmstrip scale filter; total strip width is
# FRAME_W * N (and the waveform is rendered at the same width so vstack lines up).
FRAME_W = 320
WAVE_H = 140


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    """Run ffmpeg with check=True, capturing stderr for diagnostics."""
    return subprocess.run(
        ["ffmpeg", "-y", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _fmt_num(x: float) -> str:
    """Compact float formatting for filenames/labels (drops trailing zeros)."""
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


def build_filmstrip(video: Path, start: float, end: float, n: int, out: Path) -> None:
    """Extract N frames evenly spaced across [start, end], tiled horizontally.

    Uses fps=N/duration so exactly ~N frames are selected over the range. Guards
    against tiny/zero durations by falling back to a 1-frame strip.
    """
    duration = end - start
    if duration <= 0:
        raise ValueError("duration must be positive")

    # fps expression must be > 0. For very tiny ranges N/duration could be huge
    # (fine) but if duration is so small that fewer than 1 frame fits, fall back.
    fps = n / duration
    tile = n
    if fps <= 0 or n < 1:
        fps = 1.0
        tile = 1

    vf = f"fps={fps},scale={FRAME_W}:-1,tile={tile}x1"
    try:
        _run_ffmpeg([
            "-ss", _fmt_num(start),
            "-to", _fmt_num(end),
            "-i", str(video),
            "-vf", vf,
            "-frames:v", "1",
            str(out),
        ])
    except subprocess.CalledProcessError:
        # Fallback: grab a single frame at the start of the range.
        _run_ffmpeg([
            "-ss", _fmt_num(start),
            "-i", str(video),
            "-vf", f"scale={FRAME_W}:-1",
            "-frames:v", "1",
            str(out),
        ])


def build_waveform(video: Path, start: float, end: float, width: int, out: Path) -> bool:
    """Render a waveform image for [start, end] at the given width.

    Returns True on success, False if it failed (e.g., no audio stream) — in
    which case the caller produces a filmstrip-only composite.
    """
    try:
        _run_ffmpeg([
            "-ss", _fmt_num(start),
            "-to", _fmt_num(end),
            "-i", str(video),
            "-filter_complex",
            f"showwavespic=s={width}x{WAVE_H}:colors=white",
            "-frames:v", "1",
            str(out),
        ])
        return out.exists() and out.stat().st_size > 0
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            "timeline_view: waveform skipped (no audio stream or render failed)\n"
        )
        if exc.stderr:
            # Surface the last line of ffmpeg's error for context, but don't abort.
            tail = exc.stderr.strip().splitlines()[-1:] or [""]
            sys.stderr.write(f"  ffmpeg: {tail[0]}\n")
        return False


def vstack(strip: Path, wave: Path, out: Path) -> None:
    """Stack filmstrip over waveform vertically into out."""
    _run_ffmpeg([
        "-i", str(strip),
        "-i", str(wave),
        "-filter_complex", "[0:v][1:v]vstack=inputs=2",
        str(out),
    ])


def copy_image(src: Path, dst: Path) -> None:
    """Re-encode/copy a single image to dst via ffmpeg (no PIL)."""
    _run_ffmpeg(["-i", str(src), str(dst)])


def add_label(image: Path, start: float, end: float) -> None:
    """Overlay the time-range text onto `image` in place. Skips gracefully on failure."""
    label = f"{_fmt_num(start)}s - {_fmt_num(end)}s"
    # Escape characters that are special inside drawtext.
    safe = label.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    drawtext = (
        f"drawtext=text='{safe}':x=8:y=8:fontsize=18:"
        "fontcolor=yellow:box=1:boxcolor=black@0.5"
    )
    fd, tmp = tempfile.mkstemp(suffix=image.suffix or ".png")
    tmp_path = Path(tmp)
    try:
        import os

        os.close(fd)
        _run_ffmpeg(["-i", str(image), "-vf", drawtext, str(tmp_path)])
        # Success — move labeled version over the original.
        tmp_path.replace(image)
    except subprocess.CalledProcessError:
        sys.stderr.write("timeline_view: label skipped (drawtext/font unavailable)\n")
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def default_output(video: Path, start: float, end: float, edit_dir: Path | None) -> Path:
    base = edit_dir if edit_dir is not None else video.parent / "edit"
    return base / "verify" / f"{video.stem}_{_fmt_num(start)}-{_fmt_num(end)}.png"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Render a filmstrip + waveform composite PNG for a video time range.",
    )
    p.add_argument("video", type=Path, help="source video path")
    p.add_argument("start", type=float, help="range start (seconds)")
    p.add_argument("end", type=float, help="range end (seconds)")
    p.add_argument("-o", "--output", type=Path, default=None, help="output PNG path")
    p.add_argument(
        "--frames", type=int, default=8, help="number of filmstrip frames (default 8)"
    )
    p.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="edit directory (default <dir-of-video>/edit)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    video: Path = args.video
    if not video.exists():
        sys.stderr.write(f"timeline_view: source not found: {video}\n")
        return 1

    start, end = args.start, args.end
    if end <= start:
        sys.stderr.write(
            f"timeline_view: end ({end}) must be greater than start ({start})\n"
        )
        return 1

    n = max(1, int(args.frames))

    out = args.output if args.output is not None else default_output(
        video, start, end, args.edit_dir
    )
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    tmpdir = Path(tempfile.mkdtemp(prefix="timeline_view_"))
    strip = tmpdir / "strip.png"
    wave = tmpdir / "wave.png"

    try:
        # 1) Filmstrip (required).
        try:
            build_filmstrip(video, start, end, n, strip)
        except (subprocess.CalledProcessError, ValueError) as exc:
            sys.stderr.write(f"timeline_view: filmstrip failed: {exc}\n")
            return 1

        if not (strip.exists() and strip.stat().st_size > 0):
            sys.stderr.write("timeline_view: filmstrip produced no output\n")
            return 1

        # The waveform width must match the filmstrip width so vstack aligns.
        strip_width = FRAME_W * n

        # 2) Waveform (optional — skip gracefully if no audio).
        have_wave = build_waveform(video, start, end, strip_width, wave)

        # 3) Compose.
        try:
            if have_wave:
                vstack(strip, wave, out)
            else:
                copy_image(strip, out)
        except subprocess.CalledProcessError as exc:
            # As a last resort, fall back to filmstrip-only.
            sys.stderr.write(
                "timeline_view: compose failed, falling back to filmstrip-only\n"
            )
            if exc.stderr:
                tail = exc.stderr.strip().splitlines()[-1:] or [""]
                sys.stderr.write(f"  ffmpeg: {tail[0]}\n")
            try:
                copy_image(strip, out)
            except subprocess.CalledProcessError as exc2:
                sys.stderr.write(f"timeline_view: fallback copy failed: {exc2}\n")
                return 1

        # 4) Label (optional).
        add_label(out, start, end)

        if not (out.exists() and out.stat().st_size > 0):
            sys.stderr.write("timeline_view: output PNG was not produced\n")
            return 1

        print(str(out))
        return 0
    finally:
        # Clean up temp files / dir.
        for f in (strip, wave):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            tmpdir.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
