#!/usr/bin/env python3
"""Inspect decoded video frames using Python's standard library and FFmpeg."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import count, islice
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryFile


@dataclass
class Video:
    width: int
    height: int
    fps: Fraction
    pix_fmt: str
    timestamps: list[float]
    fixed_size: bool


def probe(path: Path) -> Video:
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "V:0", "-show_frames",
        "-show_entries", "stream=width,height,avg_frame_rate,pix_fmt:frame=best_effort_timestamp_time,width,height",
        "-of", "json", str(path.resolve()),
    ]))
    if not data.get("streams"):
        raise ValueError("input has no video stream")
    stream = data["streams"][0]
    frames = data.get("frames", [])
    if not frames:
        raise ValueError("input has no decoded frames")
    try:
        fps = Fraction(stream["avg_frame_rate"])
    except (KeyError, ValueError, ZeroDivisionError):
        fps = Fraction(0)
    width, height = int(stream["width"]), int(stream["height"])
    first = float(frames[0].get("best_effort_timestamp_time", 0))
    timestamps = [
        float(frame["best_effort_timestamp_time"]) - first if "best_effort_timestamp_time" in frame
        else float(i / fps) if fps > 0 else 0.0
        for i, frame in enumerate(frames)
    ]
    fixed_size = all((f.get("width"), f.get("height")) == (width, height) for f in frames)
    return Video(width, height, fps, stream.get("pix_fmt", ""), timestamps, fixed_size)


def ffmpeg(*args: str) -> list[str]:
    return ["ffmpeg", "-nostdin", "-v", "error", *args]


@contextmanager
def rgb_frames(inputs: list[str], width: int, height: int, *, filters: list[str], count: int):
    """Yield exactly count display-order rgb24 frames with bounded memory."""
    cmd = ffmpeg("-xerror", "-filter_threads", "1", *inputs, "-map", "0:V:0")
    if filters:
        cmd += ["-vf", ",".join(filters)]
    cmd += ["-frames:v", str(count), "-fps_mode", "passthrough", "-c:v", "rawvideo",
            "-threads:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    size = width * height * 3

    def read_frames(stream):
        for _ in range(count):
            frame = stream.read(size)
            if len(frame) != size:
                raise ValueError("FFmpeg returned fewer RGB frames than expected")
            yield frame

    with TemporaryFile() as stderr, subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr) as proc:
        try:
            yield read_frames(proc.stdout)
            if proc.wait():
                raise ValueError("FFmpeg frame decode failed")
        except BaseException as exc:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            stderr.seek(0)
            detail = stderr.read().decode(errors="replace").strip()
            if detail and isinstance(exc, ValueError):
                raise ValueError(f"{exc}: {detail}") from exc
            raise


def video_input(path: Path) -> list[str]:
    return ["-noautorotate", "-i", str(path.resolve())]


def select_frames(indices: list[int]) -> str:
    return "select=" + "+".join(f"eq(n\\,{i})" for i in indices)


def tile_filter(w: int, h: int) -> str:
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")


# Compact digits keep the contact sheets independent of fonts and FFmpeg drawtext.
DIGITS = dict(zip("0123456789:.-#", (
    ("111", "101", "101", "101", "111"), ("010", "110", "010", "010", "111"),
    ("111", "001", "111", "100", "111"), ("111", "001", "111", "001", "111"),
    ("101", "101", "111", "001", "001"), ("111", "100", "111", "001", "111"),
    ("111", "100", "111", "101", "111"), ("111", "001", "010", "010", "010"),
    ("111", "101", "111", "101", "111"), ("111", "101", "111", "001", "111"),
    ("0", "1", "0", "1", "0"), ("0", "0", "0", "0", "1"),
    ("000", "000", "111", "000", "000"), ("01010", "11111", "01010", "11111", "01010"),
)))


def timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    sign = "-" if total_ms < 0 else ""
    minutes, millis = divmod(abs(total_ms), 60_000)
    return f"{sign}{minutes:02d}:{millis // 1000:02d}.{millis % 1000:03d}"


def sheet(path: Path, tiles: list[tuple[int, float, bytes]], cols: int, w: int, h: int) -> None:
    cols = min(cols, len(tiles))
    zoom = 2 if w < 320 else 3
    labels = [f"#{i} {timestamp(t)}" for i, t, _ in tiles]
    def label_width(label):
        return sum(len(DIGITS.get(c, ("00",))[0]) + 1 for c in label)

    # Narrow thumbnail options still get labels, with an expanded label band.
    if max(map(label_width, labels)) * zoom + 4 > w:
        zoom = 1
    cell_width = max(w, max(map(label_width, labels)) * zoom + 4)
    cell_height = h + 5 * zoom + 8
    width, height = cols * cell_width, math.ceil(len(tiles) / cols) * cell_height
    canvas = bytearray(width * height * 3)
    for pos, ((_, _, pixels), label) in enumerate(zip(tiles, labels)):
        row, col = divmod(pos, cols)
        x, y = col * cell_width, row * cell_height
        for dy in range(h):
            dest = ((y + dy) * width + x) * 3
            canvas[dest:dest + w * 3] = pixels[dy * w * 3:(dy + 1) * w * 3]
        x += 2
        for char in label:
            glyph = DIGITS.get(char, ("00",) * 5)
            for dy, dots in enumerate(glyph):
                for dx, dot in enumerate(dots):
                    if dot == "1":
                        for sy in range(zoom):
                            dest = ((y + h + 4 + dy * zoom + sy) * width + x + dx * zoom) * 3
                            canvas[dest:dest + zoom * 3] = b"\xff" * (zoom * 3)
            x += (len(glyph[0]) + 1) * zoom
    path.parent.mkdir(parents=True, exist_ok=True)
    is_png = path.suffix.lower() == ".png"
    enc_args = ("-c:v", "png", "-update", "1", "-f", "image2") if is_png else ("-q:v", "2", "-f", "mjpeg")
    subprocess.run(ffmpeg("-y", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size",
                          f"{width}x{height}", "-i", "pipe:0", "-frames:v", "1",
                          "-threads:v", "1", *enc_args, str(path.resolve())),
                   input=canvas, check=True)


def scan_pages(frames, args) -> None:
    page_size = args.cols * args.rows
    for page in count(1):
        tiles = list(islice(frames, page_size))
        if not tiles:
            break
        path = args.out / f"scan-{page:04}.jpg"
        sheet(path, tiles, args.cols, args.tile_w, args.tile_h)
        print(path)


def directory_frames(path: Path, fps: Fraction, w: int, h: int):
    files = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if not files:
        raise ValueError("frames directory contains no PNG or JPEG images")
    numbered = all(re.fullmatch(r"[0-9]+", p.stem) for p in files)
    if numbered:
        files.sort(key=lambda p: int(p.stem))
    indices = [int(p.stem) for p in files] if numbered else list(range(len(files)))
    times = [float(i / fps) for i in indices]
    filters = [tile_filter(w, h)]
    start = indices[0]
    if all(p.name == f"{start + i:04}.png" for i, p in enumerate(files)):
        # Fast path for render.mjs sequences. Escape literal '%' in the directory.
        pattern = str(path.resolve()).replace("%", "%%") + "/%04d.png"
        inputs = ["-framerate", str(fps), "-start_number", str(start), "-i", pattern]
        with rgb_frames(inputs, w, h, filters=filters, count=len(files)) as frames:
            yield from zip(indices, times, frames)
    else:
        for idx, time, file in zip(indices, times, files):
            with rgb_frames(video_input(file), w, h, filters=filters, count=1) as frames:
                yield idx, time, next(frames)


def check_indices(indices: list[int], video: Video) -> None:
    if max(indices) >= len(video.timestamps):
        raise ValueError(f"frame index {max(indices)} is outside 0..{len(video.timestamps) - 1}")


def scan(args) -> None:
    w, h = args.tile_w, args.tile_h
    if args.input.is_dir():
        fps = args.fps
        if fps is None:
            manifest = args.input.parent / "manifest.json"
            fps = Fraction(str(json.loads(manifest.read_text())["fps"])) if manifest.is_file() else Fraction(24)
        if fps <= 0:
            raise ValueError("frames directory FPS must be positive")
        frames = directory_frames(args.input, fps, w, h)
        try:
            scan_pages(frames, args)
        finally:
            frames.close()
    else:
        if args.fps is not None:
            raise ValueError("--fps applies only to a frames directory")
        video = probe(args.input)
        with rgb_frames(video_input(args.input), w, h, filters=[tile_filter(w, h)],
                        count=len(video.timestamps)) as frames:
            scan_pages(((i, t, rgb) for i, (t, rgb) in enumerate(zip(video.timestamps, frames))), args)


def hero(args) -> None:
    if args.out.resolve() == args.input.resolve():
        raise ValueError("hero output must differ from the input")
    video = probe(args.input)
    indices = sorted(set(args.frames))
    check_indices(indices, video)
    w, h = args.tile_w, args.tile_h
    with rgb_frames(video_input(args.input), w, h,
                    filters=[select_frames(indices), tile_filter(w, h)], count=len(indices)) as frames:
        decoded = dict(zip(indices, frames))
    sheet(args.out, [(i, video.timestamps[i], decoded[i]) for i in args.frames], args.cols, w, h)
    print(args.out)


def srgb_linear(value: int) -> float:
    v = value / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


SRGB_LINEAR = tuple(srgb_linear(v) for v in range(256))


def lab_curve(value: float) -> float:
    delta = 6 / 29
    return math.cbrt(value) if value > delta ** 3 else value / (3 * delta ** 2) + 4 / 29


@lru_cache(maxsize=65536)
def pixel_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float, float, float]:
    """8-bit sRGB to XYZ and Lab using the D65 reference white."""
    r, g, b = (SRGB_LINEAR[v] for v in rgb)
    x = lab_curve((0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047)
    y = lab_curve((0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.0000001)
    z = lab_curve((0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883)
    light, a, b_star = 116 * y - 16, 500 * (x - y), 200 * (y - z)
    luma = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
    return light, a, b_star, math.hypot(a, b_star), luma


def frame_metrics(rgb: bytes) -> dict[str, float]:
    if not rgb or len(rgb) % 3:
        raise ValueError("expected a non-empty rgb24 frame")
    triples = iter(rgb)
    colors = Counter(zip(triples, triples, triples))
    pixels = len(rgb) // 3
    totals = [0.0] * 5
    histogram = Counter()
    for color, weight in colors.items():
        lab = pixel_lab(color)
        for i, value in enumerate(lab):
            totals[i] += value * weight
        histogram[lab[0]] += weight
    light, a, b, chroma, luma = (total / pixels for total in totals)
    sd_l = math.sqrt(sum((value - light) ** 2 * count for value, count in histogram.items()) / pixels)
    rank = (pixels + 19) // 20
    for p5 in sorted(histogram):
        rank -= histogram[p5]
        if rank <= 0:
            break
    return {"L*": light, "a*": a, "b*": b, "C*": chroma, "sd_L": sd_l, "p5_L": p5, "luma": luma}


def grade(args) -> int:
    video = probe(args.input)
    last = len(video.timestamps) - 1
    beats = sorted(set(args.beats if args.beats is not None else [0, last // 2, last]))
    check_indices(beats, video)
    errors = []
    if video.pix_fmt != "yuv420p":
        errors.append(f"pixel format {video.pix_fmt!r} must be yuv420p")
    if video.fps <= 0:
        errors.append("average frame rate must be positive")
    geometry_ok = video.width > 0 and video.height > 0 and video.fixed_size
    if not geometry_ok or video.width % 2 or video.height % 2:
        errors.append("resolution must be fixed, positive and even on both axes")
    report = {
        "stream": {"pixel_format": video.pix_fmt, "fps": float(video.fps), "fps_ratio": str(video.fps),
                   "width": video.width, "height": video.height, "frames": last + 1},
        "errors": errors, "beats": [],
    }
    if geometry_ok:
        indices = sorted({0, last, *beats})
        with rgb_frames(video_input(args.input), video.width, video.height,
                        filters=[select_frames(indices)], count=len(indices)) as frames:
            measured = {i: frame_metrics(rgb) for i, rgb in zip(indices, frames)}
        report["first_luma"], report["last_luma"] = measured[0]["luma"], measured[last]["luma"]
        for name, idx, minimum in (("first", 0, args.min_first_luma), ("last", last, args.min_last_luma)):
            if measured[idx]["luma"] < minimum:
                errors.append(f"{name} frame {idx} is blank: luma {measured[idx]['luma']:.4f} < {minimum:g}")
        for i in beats:
            metrics = measured[i]
            is_dark_key = metrics["L*"] < 50.0
            report["beats"].append({
                "frame": i,
                "time_s": video.timestamps[i],
                "polarity": "dark" if is_dark_key else "light",
                **metrics,
            })
            if is_dark_key and metrics["p5_L"] > args.max_dark_p5:
                errors.append(f"frame {i} washed-out blacks: p5_L {metrics['p5_L']:.2f} > {args.max_dark_p5:g}")
            if metrics["sd_L"] < args.min_sd_l:
                errors.append(f"frame {i} flatline contrast: sd_L {metrics['sd_L']:.2f} < {args.min_sd_l:g}")
    report["pass"] = not errors
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'FAIL' if errors else 'PASS'} {video.width}x{video.height} {video.fps} fps {video.pix_fmt}")
        for beat in report["beats"]:
            numbers = " ".join(f"{key}={beat[key]:.2f}" for key in ("L*", "a*", "b*", "C*", "sd_L", "p5_L"))
            print(f"frame {beat['frame']} @ {timestamp(beat['time_s'])}  {numbers}")
        for error in errors:
            print(error)
    return int(bool(errors))


def positive_int(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def frame_indices(value: str) -> list[int]:
    if not re.fullmatch(r"[0-9]+(?:\s*,\s*[0-9]+)*", value.strip()):
        raise argparse.ArgumentTypeError("expected comma-separated non-negative frame indices")
    return [int(i) for i in value.split(",")]


def positive_fps(value: str) -> Fraction:
    try:
        fps = Fraction(value)
        if fps > 0:
            return fps
    except (ValueError, ZeroDivisionError):
        pass
    raise argparse.ArgumentTypeError("must be a positive frame rate")


def add_sheet_args(parser, *, cols: int, w: int, h: int):
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cols", type=positive_int, default=cols)
    parser.add_argument("--tile-w", type=positive_int, default=w)
    parser.add_argument("--tile-h", type=positive_int, default=h)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan_cli = sub.add_parser("scan", help="page through every frame of a video or directory")
    scan_cli.add_argument("input", type=Path)
    add_sheet_args(scan_cli, cols=18, w=160, h=90)
    scan_cli.add_argument("--rows", type=positive_int, default=12)
    scan_cli.add_argument("--fps", type=positive_fps, help="frames directory FPS (manifest FPS or 24 by default)")
    hero_cli = sub.add_parser("hero", help="make a high-resolution sheet of selected frames")
    hero_cli.add_argument("input", type=Path)
    hero_cli.add_argument("--frames", type=frame_indices, required=True)
    add_sheet_args(hero_cli, cols=4, w=480, h=270)
    grade_cli = sub.add_parser("grade", help="measure delivery format, endpoint luma and beat contrast")
    grade_cli.add_argument("input", type=Path)
    grade_cli.add_argument("--beats", type=frame_indices)
    grade_cli.add_argument("--min-first-luma", type=float, default=0.02)
    grade_cli.add_argument("--min-last-luma", type=float, default=0.02)
    grade_cli.add_argument("--max-dark-p5", type=float, default=38)
    grade_cli.add_argument("--min-sd-l", type=float, default=1, help="minimum per-beat lightness deviation")
    grade_cli.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "grade":
        for option, upper in (("min_first_luma", 1), ("min_last_luma", 1), ("max_dark_p5", 100), ("min_sd_l", 50)):
            if not 0 <= getattr(args, option) <= upper:
                parser.error(f"--{option.replace('_', '-')} must be between 0 and {upper}")
    try:
        for tool in ("ffmpeg", "ffprobe"):
            if not shutil.which(tool):
                raise ValueError(f"{tool} is required on PATH")
        if args.command == "grade":
            return grade(args)
        if args.command == "scan":
            scan(args)
        else:
            hero(args)
        return 0
    except (ValueError, OSError, KeyError, ZeroDivisionError, subprocess.CalledProcessError) as exc:
        print(f"video_qa: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
