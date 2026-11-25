"""Synthetic delivery fixtures with known decoded pixel and frame properties."""

from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import video_qa as qa

HAS_FFMPEG = all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe"))
if os.environ.get("MOTION_LAB_REQUIRE_FFMPEG") and not HAS_FFMPEG:
    raise RuntimeError("MOTION_LAB_REQUIRE_FFMPEG is set but FFmpeg/ffprobe are unavailable")
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg/ffprobe unavailable")
W, H = 64, 36
BLACK, WHITE = b"\x00" * 3, b"\xff" * 3
RED, GREEN, BLUE = b"\xff\x00\x00", b"\x00\xff\x00", b"\x00\x00\xff"


def solid(color):
    return color * (W * H)


def split(color):
    return (BLACK * (W // 4) + color * (3 * W // 4)) * H


def encode(path, frames, pix_fmt="yuv420p"):
    subprocess.run(["ffmpeg", "-v", "error", "-filter_threads", "1", "-f", "rawvideo", "-pixel_format", "rgb24",
                    "-video_size", f"{W}x{H}", "-framerate", "4", "-i", "pipe:0", "-c:v", "libx264",
                    "-threads:v", "1", "-crf", "0", "-pix_fmt", pix_fmt, str(path)],
                   input=b"".join(frames), check=True)
    return path


def cli(*args, **kwargs):
    return subprocess.run([sys.executable, str(SKILL / "scripts" / "video_qa.py"), *map(str, args)],
                          capture_output=True, text=True, timeout=45, **kwargs)


def jpg_rgb(path):
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                                               "-of", "json", str(path)]))["streams"][0]
    width, height = info["width"], info["height"]
    pixels = subprocess.check_output(["ffmpeg", "-v", "error", "-filter_threads", "1", "-i", str(path),
                                      "-frames:v", "1", "-threads:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    return width, height, lambda x, y: tuple(pixels[(y * width + x) * 3:(y * width + x) * 3 + 3])


@pytest.mark.parametrize("color,lab", [
    (BLACK, (0, 0, 0, 0)), (WHITE, (100, 0, 0, 0)), (b"\x80" * 3, (53.5850, 0, 0, 0)),
    (RED, (53.2408, 80.0925, 67.2032, 104.5518)),
    (GREEN, (87.7347, -86.1827, 83.1793, 119.7759)),
    (BLUE, (32.2970, 79.1875, -107.8602, 133.8076)),
])
def test_cielab_known_srgb_colors(color, lab):
    report = qa.frame_metrics(solid(color))
    assert [report[key] for key in ("L*", "a*", "b*", "C*")] == pytest.approx(lab, abs=0.001)
    assert report["sd_L"] == pytest.approx(0, abs=1e-10)
    assert report["p5_L"] == pytest.approx(lab[0], abs=0.001)


def test_cielab_uses_pixel_weighted_percentile_and_population_deviation():
    frame = BLACK * 5 + WHITE * 95
    m = qa.frame_metrics(frame)
    assert m["L*"] == pytest.approx(95)
    assert m["p5_L"] == 0
    assert m["sd_L"] == pytest.approx((0.05 * 95**2 + 0.95 * 5**2) ** 0.5)
    assert qa.frame_metrics(BLACK * 4 + WHITE * 96)["p5_L"] == pytest.approx(100)


@needs_ffmpeg
def test_grade_reports_sampled_beat_metrics_and_contract(tmp_path):
    video = encode(tmp_path / "colors.mp4", [split(RED), solid(RED), split(GREEN), split(BLUE)])
    result = cli("grade", video, "--beats", "2, 0,2", "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["pass"] is True and not report["errors"]
    assert report["stream"] == {"pixel_format": "yuv420p", "fps": 4, "fps_ratio": "4",
                                "width": W, "height": H, "frames": 4}
    assert [b["frame"] for b in report["beats"]] == [0, 2]
    assert [b["time_s"] for b in report["beats"]] == [0, 0.5]
    assert report["beats"][0]["L*"] == pytest.approx(53.2408 * 0.75, abs=1)
    assert report["beats"][1]["a*"] == pytest.approx(-86.1827 * 0.75, abs=1)
    assert report["beats"][1]["sd_L"] > 30
    assert report["beats"][1]["p5_L"] == pytest.approx(0, abs=0.5)


@needs_ffmpeg
def test_grade_rejects_blank_first_and_last_even_when_beats_exclude_them(tmp_path):
    video = encode(tmp_path / "blank.mp4", [solid(BLACK), split(RED), solid(BLACK)])
    result = cli("grade", video, "--beats", "1", "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["errors"] == [
        "first frame 0 is blank: luma 0.0000 < 0.02",
        "last frame 2 is blank: luma 0.0000 < 0.02",
    ]
    assert report["first_luma"] == report["last_luma"] == 0
    assert cli("grade", video, "--beats", "1", "--min-first-luma", 0, "--min-last-luma", 0).returncode == 0


@needs_ffmpeg
def test_grade_fails_independent_washed_out_and_flatline_checks(tmp_path):
    washed_lo = b"\x64" * 3  # L* ~ 42.4 (> 38)
    washed_hi = b"\x78" * 3  # L* ~ 50.4 -> mean L* ~ 46.4 (< 50 dark-key), sd_L ~ 4.0 (>= 1)
    washed = (washed_lo * (W // 2) + washed_hi * (W // 2)) * H
    flat_dark = solid(washed_lo)  # L* ~ 42.4 (< 50 dark-key), p5_L ~ 42.4 (> 38), sd_L = 0 (< 1)
    video = encode(tmp_path / "contrast.mp4", [split(RED), washed, flat_dark, split(RED)])
    r = cli("grade", video, "--beats", "1,2", "--json")
    assert r.returncode == 1
    errors = json.loads(r.stdout)["errors"]
    assert len(errors) == 3
    assert errors[0].startswith("frame 1 washed-out blacks")
    assert errors[1].startswith("frame 2 washed-out blacks")
    assert errors[2].startswith("frame 2 flatline contrast")
    assert cli("grade", video, "--beats", "1,2", "--max-dark-p5", 100, "--min-sd-l", 0).returncode == 0


@needs_ffmpeg
def test_grade_rejects_wrong_pixel_format(tmp_path):
    video = encode(tmp_path / "444.mp4", [split(WHITE)], "yuv444p")
    result = cli("grade", video, "--json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["errors"] == ["pixel format 'yuv444p' must be yuv420p"]


def test_grade_gates_invalid_fps_and_resolution(monkeypatch, capsys):
    monkeypatch.setattr(qa, "probe", lambda path: qa.Video(63, 0, Fraction(0), "yuv420p", [0], False))
    assert qa.grade(type("Args", (), {"input": None, "beats": None, "json": True})()) == 1
    assert json.loads(capsys.readouterr().out)["errors"] == [
        "average frame rate must be positive", "resolution must be fixed, positive and even on both axes",
    ]


@needs_ffmpeg
def test_scan_pages_cover_every_video_frame_and_draw_timestamp_labels(tmp_path):
    video = encode(tmp_path / "clip.mp4", [solid(c) for c in (RED, GREEN, BLUE, WHITE, RED)])
    out = tmp_path / "scan"
    result = cli("scan", video, "--out", out, "--cols", 2, "--rows", 1, "--tile-w", 100, "--tile-h", 50)
    assert result.returncode == 0, result.stderr
    pages = sorted(out.glob("*.jpg"))
    assert [p.name for p in pages] == ["scan-0001.jpg", "scan-0002.jpg", "scan-0003.jpg"]
    assert timestamp_pixels(pages[0], 0) != timestamp_pixels(pages[0], 100)
    for page, expected in zip(pages, ((RED, GREEN), (BLUE, WHITE), (RED,))):
        w, h, pixel = jpg_rgb(page)
        assert (w, h) == (100 * len(expected), 68)
        for i, c in enumerate(expected):
            assert pixel(100 * i + 50, 25) == pytest.approx(tuple(c), abs=8)


def timestamp_pixels(page, left):
    _, _, pixel = jpg_rgb(page)
    label = tuple(pixel(left + x, y)[0] > 128 for y in range(54, 64) for x in range(95))
    assert any(label)
    return label


@needs_ffmpeg
def test_scan_frames_uses_numeric_order_and_manifest_fps(tmp_path, monkeypatch):
    root = tmp_path / "dir %1"
    root.mkdir()
    for idx, color in [(10, RED), (2, BLUE)]:
        subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size",
                        f"{W}x{H}", "-i", "pipe:0", "-frames:v", "1", "-threads:v", "1", str(root / f"{idx:04}.png")],
                       input=solid(color), check=True)
    (tmp_path / "manifest.json").write_text('{"fps": 10}')
    tiles = []
    monkeypatch.setattr(qa, "sheet", lambda path, frames, *args: tiles.extend(frames))
    assert qa.main(["scan", str(root), "--out", str(tmp_path / "out")]) == 0
    assert [(i, t) for i, t, _ in tiles] == [(2, 0.2), (10, 1.0)]
    assert qa.main(["scan", str(root), "--out", str(tmp_path / "out"), "--fps", "20"]) == 0
    assert [(i, t) for i, t, _ in tiles[2:]] == [(2, 0.1), (10, 0.5)]


@needs_ffmpeg
def test_hero_keeps_requested_order_and_exact_frame_numbers(tmp_path):
    video = encode(tmp_path / "color.mp4", [solid(RED), solid(BLUE), solid(GREEN)])
    out = tmp_path / "hero.jpg"
    result = cli("hero", video, "--frames", "2,0,2,1", "--out", out, "--cols", 3,
                 "--tile-w", 120, "--tile-h", 68)
    assert result.returncode == 0, result.stderr
    w, h, pixel = jpg_rgb(out)
    assert (w, h) == (360, 172)
    for (x, y), c in zip(((60, 30), (180, 30), (300, 30), (60, 115)), (GREEN, RED, GREEN, BLUE)):
        assert pixel(x, y) == pytest.approx(tuple(c), abs=8)


def test_invalid_arguments_and_missing_tools_exit_two(tmp_path):
    assert cli("scan", tmp_path, "--out", tmp_path / "out", "--cols", 0).returncode == 2
    assert cli("hero", "x.mp4", "--frames", "1,,2", "--out", "a.jpg").returncode == 2
    assert cli("grade", "x.mp4", "--min-first-luma", "nan").returncode == 2
    r = cli("grade", "x.mp4", env={"PATH": str(tmp_path)})
    assert r.returncode == 2 and "ffmpeg is required" in r.stderr


@needs_ffmpeg
def test_out_of_range_frame_is_invalid_input(tmp_path):
    video = encode(tmp_path / "one.mp4", [solid(RED)])
    r = cli("hero", video, "--frames", "1", "--out", tmp_path / "outside.jpg")
    assert r.returncode == 2 and "outside 0..0" in r.stderr


def test_p20_light_day_paper_and_mixed_polarity_and_png_and_negative_timestamp(tmp_path):
    """Light/day-paper beats (L* >= 50) must not false-fail washed-out blacks; negative timestamps and PNG sheets work."""
    assert qa.timestamp(-0.5) == "-00:00.500"
    if not shutil.which("ffmpeg"):
        return
    # Day-paper frame (#F5F2EB with 4% dark ink -> L* > 90, p5_L > 90, sd_L > 10)
    paper = bytes([0xF5, 0xF2, 0xEB])
    ink = bytes([0x1A, 0x1A, 0x1A])
    ink_rows = max(1, H // 16)
    day_frame = (ink * W) * ink_rows + (paper * W) * (H - ink_rows)
    dark_clean = (b"\x08\x0c\x14" * (W // 2) + b"\x38\x60\x98" * (W // 2)) * H
    video = encode(tmp_path / "mixed.mp4", [day_frame, dark_clean, day_frame])
    r = cli("grade", video, "--beats", "0,1,2", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["pass"] is True
    assert [b["polarity"] for b in data["beats"]] == ["light", "dark", "light"]

    out_png = tmp_path / "hero.png"
    r_png = cli("hero", video, "--frames", "0,1", "--out", out_png)
    assert r_png.returncode == 0, r_png.stderr
    assert out_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
