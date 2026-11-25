"""Unit + synthetic FFmpeg E2E tests for scripts/edit_plan.py."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import edit_plan

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _valid_plan() -> dict:
    return {
        "version": 1,
        "canvas": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "safe_area": "9:16-reels",
        },
        "clips": [
            {
                "id": "c1",
                "source": "/tmp/a.mp4",
                "in_s": 0.5,
                "out_s": 2.0,
                "punch_in": {"scale": 1.3, "anchor_x": 0.5, "anchor_y": 0.4},
                "grade": {"brightness": 0.02, "contrast": 1.05, "saturation": 1.08},
                "gain_db": 0.0,
            },
            {
                "id": "c2",
                "source": "/tmp/b.mp4",
                "in_s": 1.0,
                "out_s": 2.5,
                "punch_in": {"scale": 1.6, "anchor_x": 1.0, "anchor_y": 1.0},
                "gain_db": -2.0,
            },
        ],
        "audio": {
            "music": {
                "source": "/tmp/music.wav",
                "gain_db": -16.0,
                "duck_db": -10.0,
                "pad_tail_s": 0.75,
            },
            "target_lufs": -14.0,
        },
        "captions": {
            "enabled": True,
            "safe_zone_check": True,
            "entries": [
                {"start_s": 0.1, "end_s": 1.4, "text": "Hello world", "y_frac": 0.72},
                {"start_s": 1.6, "end_s": 2.8, "text": "It's working!", "y_frac": 0.72},
            ],
        },
    }


# ---------------------------------------------------------------------------
# Validator unit tests
# ---------------------------------------------------------------------------
def test_validate_valid_plan():
    res = edit_plan.validate_plan(_valid_plan())
    assert res["valid"] is True
    assert res["errors"] == []


@pytest.mark.parametrize("bad_version", [None, 0, 2, "1", True])
def test_validate_rejects_bad_version(bad_version):
    p = _valid_plan()
    p["version"] = bad_version
    res = edit_plan.validate_plan(p)
    assert res["valid"] is False
    assert any("version" in e for e in res["errors"])


def test_validate_rejects_inverted_and_negative_clip_times():
    p = _valid_plan()
    p["clips"][0]["in_s"] = -0.2
    res = edit_plan.validate_plan(p)
    assert not res["valid"]
    assert any("in_s" in e for e in res["errors"])

    p2 = _valid_plan()
    p2["clips"][0]["in_s"] = 2.0
    p2["clips"][0]["out_s"] = 2.0
    res2 = edit_plan.validate_plan(p2)
    assert not res2["valid"]
    assert any("in_s < out_s" in e for e in res2["errors"])

    p3 = _valid_plan()
    p3["clips"][0]["in_s"] = 3.0
    p3["clips"][0]["out_s"] = 1.0
    res3 = edit_plan.validate_plan(p3)
    assert not res3["valid"]
    assert any("in_s < out_s" in e for e in res3["errors"])


def test_validate_rejects_duplicate_clip_ids():
    p = _valid_plan()
    p["clips"][1]["id"] = "c1"
    res = edit_plan.validate_plan(p)
    assert not res["valid"]
    assert any("duplicate clip id" in e for e in res["errors"])


@pytest.mark.parametrize(
    "punch_in",
    [
        {"scale": 0.99, "anchor_x": 0.5, "anchor_y": 0.5},
        {"scale": 2.01, "anchor_x": 0.5, "anchor_y": 0.5},
        {"scale": 1.2, "anchor_x": -0.05, "anchor_y": 0.5},
        {"scale": 1.2, "anchor_x": 1.05, "anchor_y": 0.5},
        {"scale": 1.2, "anchor_x": 0.5, "anchor_y": -0.01},
        {"scale": 1.2, "anchor_x": 0.5, "anchor_y": 1.1},
    ],
)
def test_validate_rejects_out_of_range_punch_in(punch_in):
    p = _valid_plan()
    p["clips"][0]["punch_in"] = punch_in
    res = edit_plan.validate_plan(p)
    assert not res["valid"]
    assert any("punch_in" in e for e in res["errors"])


def test_validate_rejects_unsafe_captions_for_presets_and_custom():
    # Bottom unsafe on 9:16-reels (bottom margin 0.22 -> max y_frac = 0.78)
    p = _valid_plan()
    p["captions"]["entries"][0]["y_frac"] = 0.88
    res = edit_plan.validate_plan(p)
    assert not res["valid"]
    assert any("safe_area vertical" in e for e in res["errors"])

    # Top unsafe on 9:16-reels (top margin 0.14)
    p2 = _valid_plan()
    p2["captions"]["entries"][0]["y_frac"] = 0.08
    res2 = edit_plan.validate_plan(p2)
    assert not res2["valid"]
    assert any("safe_area vertical" in e for e in res2["errors"])

    # Right side unsafe on 9:16-reels (right margin 0.14 -> max x_frac = 0.86)
    p3 = _valid_plan()
    p3["captions"]["entries"][0]["x_frac"] = 0.93
    res3 = edit_plan.validate_plan(p3)
    assert not res3["valid"]
    assert any("safe_area horizontal" in e for e in res3["errors"])

    # Custom safe_area dict
    p4 = _valid_plan()
    p4["canvas"]["safe_area"] = {"top": 0.20, "bottom": 0.20, "left": 0.10, "right": 0.10}
    p4["captions"]["entries"][0]["y_frac"] = 0.85
    res4 = edit_plan.validate_plan(p4)
    assert not res4["valid"]

    # Disabling safe_zone_check allows explicit placement
    p5 = copy.deepcopy(p)
    p5["captions"]["safe_zone_check"] = False
    res5 = edit_plan.validate_plan(p5)
    assert res5["valid"] is True


def test_validate_rejects_short_or_missing_sidechain_pad_tail():
    # pad_tail_s < 0.5
    p = _valid_plan()
    p["audio"]["music"]["pad_tail_s"] = 0.25
    res = edit_plan.validate_plan(p)
    assert not res["valid"]
    assert any("pad_tail_s" in e for e in res["errors"])

    # omitted pad_tail_s when duck_db != 0
    p2 = _valid_plan()
    del p2["audio"]["music"]["pad_tail_s"]
    res2 = edit_plan.validate_plan(p2)
    assert not res2["valid"]
    assert any("pad_tail_s" in e for e in res2["errors"])

    # boundary 0.5 is accepted
    p3 = _valid_plan()
    p3["audio"]["music"]["pad_tail_s"] = 0.5
    res3 = edit_plan.validate_plan(p3)
    assert res3["valid"] is True


def test_validate_check_files(tmp_path):
    p = _valid_plan()
    res = edit_plan.validate_plan(p, check_files=True, base_dir=tmp_path)
    assert not res["valid"]
    assert any("file not found" in e for e in res["errors"])


# ---------------------------------------------------------------------------
# Compiler determinism & CLI dry-run tests
# ---------------------------------------------------------------------------
def test_build_ffmpeg_command_is_deterministic_and_complete():
    p = _valid_plan()
    argv1 = edit_plan.build_ffmpeg_command(p, "/tmp/out.mp4")
    argv2 = edit_plan.build_ffmpeg_command(p, "/tmp/out.mp4")
    assert argv1 == argv2
    assert argv1[0] == "ffmpeg"
    assert "-pix_fmt" in argv1 and "yuv420p" in argv1
    assert "-movflags" in argv1 and "+faststart" in argv1

    fc = argv1[argv1.index("-filter_complex") + 1]
    assert "trim=start=0.5:end=2,setpts=PTS-STARTPTS" in fc
    assert "crop=w='max(2,trunc(iw/1.3/2)*2)'" in fc
    assert "x='max(0,min(iw-ow,0.5*iw-ow/2))'" in fc
    assert "apad=pad_dur=0.75" in fc
    assert "sidechaincompress=" in fc
    assert "loudnorm=I=-14.0" in fc
    # Captions applied LAST after concat
    assert fc.index("concat=n=2:v=1:a=1") < fc.index("drawtext=")


def test_build_ffmpeg_command_raises_on_invalid_plan():
    p = _valid_plan()
    p["audio"]["music"]["pad_tail_s"] = 0.1
    with pytest.raises(ValueError, match="pad_tail_s"):
        edit_plan.build_ffmpeg_command(p, "/tmp/out.mp4")


def test_cli_validate_compile_and_dry_run(tmp_path):
    plan_file = tmp_path / "editPlan.json"
    plan_file.write_text(json.dumps(_valid_plan()), encoding="utf-8")

    # validate -> exit 0
    r_val = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "validate", str(plan_file)],
        capture_output=True, text=True, check=False,
    )
    assert r_val.returncode == 0
    assert json.loads(r_val.stdout)["valid"] is True

    # render --dry-run -> exit 0, prints argv + filter_complex JSON without touching output
    out_mp4 = tmp_path / "dry.mp4"
    r_dry = subprocess.run(
        [
            sys.executable, str(SCRIPTS_DIR / "edit_plan.py"),
            "render", str(plan_file), "-o", str(out_mp4), "--dry-run",
        ],
        capture_output=True, text=True, check=False,
    )
    assert r_dry.returncode == 0
    dry_json = json.loads(r_dry.stdout)
    assert dry_json["argv"][0] == "ffmpeg"
    assert "filter_complex" in dry_json
    assert not out_mp4.exists()

    # invalid plan -> exit 1
    bad_plan = _valid_plan()
    bad_plan["clips"][0]["punch_in"]["scale"] = 3.0
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps(bad_plan), encoding="utf-8")
    r_bad = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "validate", str(bad_file)],
        capture_output=True, text=True, check=False,
    )
    assert r_bad.returncode == 1
    assert json.loads(r_bad.stdout)["valid"] is False


# ---------------------------------------------------------------------------
# Real synthetic FFmpeg E2E render test verified with ffprobe
# ---------------------------------------------------------------------------
def _find_mp4_atom_order(mp4_path: Path) -> list[str]:
    """Read top-level MP4 box types in file order to verify +faststart (moov before mdat)."""
    data = mp4_path.read_bytes()
    atoms: list[str] = []
    pos = 0
    n = len(data)
    while pos + 8 <= n:
        size = int.from_bytes(data[pos : pos + 4], "big")
        box_type = data[pos + 4 : pos + 8].decode("latin1", errors="replace")
        atoms.append(box_type)
        if size == 0:
            break
        if size == 1:
            if pos + 16 > n:
                break
            size = int.from_bytes(data[pos + 8 : pos + 16], "big")
        if size < 8:
            break
        pos += size
    return atoms


def test_e2e_render_two_clip_punch_in_ducked_music_verified_by_ffprobe(tmp_path):
    """Compile + render a real 2-clip punch-in + ducked-music yuv420p MP4 and verify with ffprobe."""
    clip1 = tmp_path / "clip1.mp4"
    clip2 = tmp_path / "clip2.mp4"
    music = tmp_path / "music.wav"

    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=320:duration=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            "-shortest", str(clip1),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=size=960x540:rate=30:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=480:duration=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            "-shortest", str(clip2),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=160:duration=2",
            "-ar", "48000", "-ac", "2",
            str(music),
        ],
        check=True,
    )

    plan = {
        "version": 1,
        "canvas": {"width": 640, "height": 360, "fps": 30, "safe_area": "16:9-youtube"},
        "clips": [
            {
                "id": "intro",
                "source": str(clip1),
                "in_s": 0.2,
                "out_s": 1.4,
                "punch_in": {"scale": 1.4, "anchor_x": 0.5, "anchor_y": 0.5},
                "grade": {"brightness": 0.02, "contrast": 1.05, "saturation": 1.1},
                "gain_db": 0.0,
            },
            {
                "id": "closeup",
                "source": str(clip2),
                "in_s": 0.5,
                "out_s": 1.8,
                "punch_in": {"scale": 1.8, "anchor_x": 1.0, "anchor_y": 1.0},
                "gain_db": -2.0,
            },
        ],
        "audio": {
            "music": {
                "source": str(music),
                "gain_db": -16.0,
                "duck_db": -10.0,
                "pad_tail_s": 0.75,
            },
            "target_lufs": -14.0,
        },
        "captions": {
            "enabled": True,
            "safe_zone_check": True,
            "entries": [
                {"start_s": 0.1, "end_s": 1.0, "text": "It's live: cut 1", "y_frac": 0.75},
                {"start_s": 1.3, "end_s": 2.3, "text": "Cut 2 punch-in", "y_frac": 0.75},
            ],
        },
    }
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    out_mp4 = tmp_path / "rendered.mp4"

    proc = subprocess.run(
        [
            sys.executable, str(SCRIPTS_DIR / "edit_plan.py"),
            "render", str(plan_file), "-o", str(out_mp4),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"render failed: {proc.stderr}"
    assert out_mp4.exists() and out_mp4.stat().st_size > 0

    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(out_mp4)],
            capture_output=True, text=True, check=True,
        ).stdout
    )
    v_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
    a_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    assert len(v_streams) == 1
    assert len(a_streams) == 1

    vs = v_streams[0]
    assert vs["codec_name"] == "h264"
    assert vs["pix_fmt"] == "yuv420p"
    assert int(vs["width"]) == 640
    assert int(vs["height"]) == 360
    assert vs["r_frame_rate"] == "30/1"

    aus = a_streams[0]
    assert aus["codec_name"] == "aac"
    assert int(aus["sample_rate"]) == 48000
    assert int(aus["channels"]) == 2

    # Expected total duration = (1.4 - 0.2) + (1.8 - 0.5) = 2.5s
    dur = float(probe["format"]["duration"])
    assert dur == pytest.approx(2.5, abs=0.15)

    # Verify +faststart placed moov before mdat
    atoms = _find_mp4_atom_order(out_mp4)
    assert "moov" in atoms and "mdat" in atoms
    assert atoms.index("moov") < atoms.index("mdat")
