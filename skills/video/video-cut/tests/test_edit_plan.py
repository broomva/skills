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
    assert "crop=w='max(min(2,iw),trunc(iw/1.3/2)*2)'" in fc
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


def test_p20_rejects_explicit_null_optional_numbers():
    """Explicit null on optional numeric fields must fail validation, not crash compile_plan."""
    p = _valid_plan()
    p["clips"][0]["punch_in"]["anchor_x"] = None
    assert edit_plan.validate_plan(p)["valid"] is False

    p2 = _valid_plan()
    p2["audio"]["music"]["gain_db"] = None
    assert edit_plan.validate_plan(p2)["valid"] is False

    p3 = _valid_plan()
    del p3["audio"]["music"]["duck_db"]
    p3["audio"]["music"]["pad_tail_s"] = None
    assert edit_plan.validate_plan(p3)["valid"] is False


def test_p20_safe_area_checks_caption_bounding_box():
    """Caption glyphs spilling past safe margin must be rejected even when anchor is inside."""
    p = _valid_plan()
    p["canvas"] = {"width": 180, "height": 320, "fps": 30, "safe_area": "9:16-reels"}
    p["captions"] = {
        "enabled": True,
        "safe_zone_check": True,
        "entries": [{"start_s": 0.1, "end_s": 0.9, "text": "EDGE", "x_frac": 0.86, "y_frac": 0.78}],
    }
    res = edit_plan.validate_plan(p)
    assert res["valid"] is False
    assert any("safe_area" in e for e in res["errors"])


def test_p20_render_caption_punctuation_percent_silent_broll_no_duck_and_short_audio(tmp_path):
    """Covers BLOCKER 1 (apostrophe/colon/percent pixels drawn + no Stray %), BLOCKER 2 (duck_db=0),
    MAJOR 3 (silent B-roll), MAJOR 4 (0.5s audio inside 2.0s video keeps full 2.0s mixed audio),
    and MINOR 2 (1x1 punch-in crop)."""
    # 1. Video with 2.0s black video + only 0.5s of audio
    v_short_a = tmp_path / "short_audio.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=black:s=640x360:r=24:d=2.0",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            str(v_short_a),
        ],
        check=True,
    )
    # 2. Silent video-only B-roll clip (no audio stream)
    v_silent = tmp_path / "silent_broll.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=navy:s=640x360:r=24:d=1.0",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(v_silent),
        ],
        check=True,
    )
    # 3. Music bed
    music = tmp_path / "bed.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=2.0",
            "-ar", "48000", "-ac", "2",
            str(music),
        ],
        check=True,
    )

    # Plan A: duck_db=0 (disabled ducking) + silent B-roll + short dialogue + apostrophe/colon/percent captions
    plan_a = {
        "version": 1,
        "canvas": {"width": 640, "height": 360, "fps": 24, "safe_area": "16:9-youtube"},
        "clips": [
            {"id": "c1", "source": str(v_short_a), "in_s": 0.0, "out_s": 2.0},
            {"id": "c2", "source": str(v_silent), "in_s": 0.0, "out_s": 1.0},
        ],
        "audio": {"music": {"source": str(music), "gain_db": -12.0, "duck_db": 0.0}},
        "captions": {
            "enabled": True,
            "safe_zone_check": True,
            "entries": [
                {"start_s": 0.1, "end_s": 1.0, "text": "It's live: cut 1", "y_frac": 0.5},
                {"start_s": 1.1, "end_s": 1.9, "text": "50% off", "y_frac": 0.5},
            ],
        },
    }
    pf_a = tmp_path / "plan_a.json"
    pf_a.write_text(json.dumps(plan_a), encoding="utf-8")
    out_a = tmp_path / "out_a.mp4"
    r_a = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf_a), "-o", str(out_a)],
        capture_output=True, text=True, check=False,
    )
    assert r_a.returncode == 0, f"render failed: {r_a.stderr}"
    assert "Stray %" not in r_a.stderr

    # Verify full 3.0s audio duration (music NOT truncated at 0.5s short dialogue!)
    pr = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", str(out_a)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(pr.stdout)["streams"]
    a_dur = float(next(s for s in streams if s["codec_type"] == "audio")["duration"])
    assert a_dur >= 2.85, f"mixed audio truncated early: {a_dur}s"

    # Verify BOTH caption frames actually drew bright white glyph pixels over the black background!
    for ts in ("0.5", "1.5"):
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", ts, "-i", str(out_a), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True,
        ).stdout
        bright = sum(1 for b in raw if b > 180)
        assert bright > 50, f"caption at t={ts}s failed to draw pixels (bright={bright})"

    # Plan B: 1x1 RGB source punch-in crop must succeed
    one_px = tmp_path / "one_px.png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=2x2:d=1", "-vf", "scale=1:1", "-frames:v", "1", str(one_px)],
        check=True,
    )
    plan_b = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "tiny", "source": str(one_px), "in_s": 0.0, "out_s": 0.5, "punch_in": {"scale": 1.5}}],
    }
    pf_b = tmp_path / "plan_b.json"
    pf_b.write_text(json.dumps(plan_b), encoding="utf-8")
    out_b = tmp_path / "out_b.mp4"
    r_b = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf_b), "-o", str(out_b)],
        capture_output=True, text=True, check=False,
    )
    assert r_b.returncode == 0, f"1x1 punch-in render failed: {r_b.stderr}"


def test_p20_r2_compiled_inline_argv_draws_apostrophe_colon_and_percent(tmp_path):
    """Executing compile_plan() inline argv directly must draw pixels for apostrophes, colons, and %."""
    clip = tmp_path / "black.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=black:s=640x360:r=24:d=2.0",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            str(clip),
        ],
        check=True,
    )
    plan = {
        "version": 1,
        "canvas": {"width": 640, "height": 360, "fps": 24, "safe_area": "16:9-youtube"},
        "clips": [{"id": "c1", "source": str(clip), "in_s": 0.0, "out_s": 2.0}],
        "captions": {
            "enabled": True,
            "safe_zone_check": True,
            "entries": [
                {"start_s": 0.0, "end_s": 0.6, "text": "It's live: cut 1", "y_frac": 0.5},
                {"start_s": 0.6, "end_s": 1.2, "text": "O'Brien", "y_frac": 0.5},
                {"start_s": 1.2, "end_s": 1.9, "text": "a:b 50% off", "y_frac": 0.5},
            ],
        },
    }
    out_mp4 = tmp_path / "compiled_inline.mp4"
    argv = edit_plan.build_ffmpeg_command(plan, out_mp4)
    r = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert r.returncode == 0, f"compiled inline argv failed: {r.stderr}"
    for ts in ("0.3", "0.9", "1.5"):
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", ts, "-i", str(out_mp4), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True,
        ).stdout
        bright = sum(1 for b in raw if b > 180)
        assert bright > 50, f"inline compiled caption at t={ts}s drew {bright} bright pixels"


def test_p20_r2_rejects_out_of_bounds_video_trim_and_wide_glyph_safe_area_and_handles_short_and_2x2(tmp_path):
    """Covers BLOCKER 2 (4-5s cut from 3s video rejected), MAJOR 1 (1-2s cut with 0.5s audio + music bed),
    MAJOR 2 (wide WWWWWWWWMMM on 180x320 rejected), MINOR 1 (2x2 yuv420p scale=2)."""
    # 1. Wide glyphs on 180x320 Reels rejected
    p_wide = _valid_plan()
    p_wide["canvas"] = {"width": 180, "height": 320, "fps": 30, "safe_area": "9:16-reels"}
    p_wide["captions"] = {
        "enabled": True,
        "safe_zone_check": True,
        "entries": [{"start_s": 0.1, "end_s": 0.9, "text": "WWWWWWWWMMM", "x_frac": 0.5, "y_frac": 0.5}],
    }
    assert edit_plan.validate_plan(p_wide)["valid"] is False

    # 2. Out-of-bounds trim (4-5s on 2s video-only source) rejected by validate_plan(check_files=True)
    v2s = tmp_path / "v2s.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=24:d=2.0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v2s)],
        check=True,
    )
    p_oob = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "oob", "source": str(v2s), "in_s": 4.0, "out_s": 5.0}],
    }
    res_oob = edit_plan.validate_plan(p_oob, check_files=True)
    assert res_oob["valid"] is False

    # 3. 1-2s video cut whose audio ends at 0.5s + music bed (with ducking) renders cleanly
    v_short = tmp_path / "v3_a05.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:r=24:d=3.0",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
            str(v_short),
        ],
        check=True,
    )
    bed = tmp_path / "bed.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=2.0", "-ar", "48000", "-ac", "2", str(bed)],
        check=True,
    )
    p_late = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "c1", "source": str(v_short), "in_s": 1.0, "out_s": 2.0}],
        "audio": {"music": {"source": str(bed), "gain_db": -12.0, "duck_db": -8.0, "pad_tail_s": 0.75}},
    }
    pf = tmp_path / "p_late.json"
    pf.write_text(json.dumps(p_late), encoding="utf-8")
    out_late = tmp_path / "out_late.mp4"
    r_late = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf), "-o", str(out_late)],
        capture_output=True, text=True, check=False,
    )
    assert r_late.returncode == 0, f"short-audio cut failed: {r_late.stderr}"

    # 4. 2x2 yuv420p source with scale=2 punch-in renders cleanly
    v2x2 = tmp_path / "v2x2.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=2x2:r=24:d=1.0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v2x2)],
        check=True,
    )
    p_2x2 = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "t2", "source": str(v2x2), "in_s": 0.0, "out_s": 0.5, "punch_in": {"scale": 2.0}}],
    }
    pf2 = tmp_path / "p2x2.json"
    pf2.write_text(json.dumps(p_2x2), encoding="utf-8")
    out2 = tmp_path / "out2x2.mp4"
    r2 = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf2), "-o", str(out2)],
        capture_output=True, text=True, check=False,
    )
    assert r2.returncode == 0, f"2x2 yuv420p punch-in failed: {r2.stderr}"


def test_p20_r3_video_bounds_offset_start_and_lowercase_wide_glyphs(tmp_path):
    """Covers R3 BLOCKER (1.99-2.49s & 1-6s on 2s source rejected), R3 MAJOR 1 (2.2-2.7s on 1-3s offset video passes),
    and R3 MAJOR 2 (lowercase mmmmmmmmmm rejected on 180x320 Reels)."""
    # 1. Lowercase wide glyphs rejected on 180x320 Reels
    p_m = _valid_plan()
    p_m["canvas"] = {"width": 180, "height": 320, "fps": 30, "safe_area": "9:16-reels"}
    p_m["captions"] = {
        "enabled": True,
        "safe_zone_check": True,
        "entries": [{"start_s": 0.1, "end_s": 0.9, "text": "mmmmmmmmmm", "x_frac": 0.5, "y_frac": 0.5}],
    }
    assert edit_plan.validate_plan(p_m)["valid"] is False

    # 2. 1.99-2.49s and 1-6s on 2.0s video rejected by validate_plan(check_files=True)
    v2s = tmp_path / "src2s.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=24:d=2.0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v2s)],
        check=True,
    )
    for lo, hi in ((1.99, 2.49), (1.0, 6.0)):
        p_bad = {
            "version": 1,
            "canvas": {"width": 64, "height": 64, "fps": 24},
            "clips": [{"id": "c1", "source": str(v2s), "in_s": lo, "out_s": hi}],
        }
        assert edit_plan.validate_plan(p_bad, check_files=True)["valid"] is False

    # 3. Source whose video starts at 1.0s (spans 1.0-3.0s) while audio starts at 0.0s: 2.2-2.7s cut must PASS and render!
    v_off = tmp_path / "offset_v1_3.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-itsoffset", "1.0", "-f", "lavfi", "-i", "color=c=green:s=64x64:r=24:d=2.0",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3.0",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
            str(v_off),
        ],
        check=True,
    )
    p_ok = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "off", "source": str(v_off), "in_s": 2.2, "out_s": 2.7}],
    }
    res_ok = edit_plan.validate_plan(p_ok, check_files=True)
    assert res_ok["valid"] is True, res_ok["errors"]
    pf = tmp_path / "p_off.json"
    pf.write_text(json.dumps(p_ok), encoding="utf-8")
    out_off = tmp_path / "out_off.mp4"
    r = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf), "-o", str(out_off)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, f"offset render failed: {r.stderr}"


def test_p20_r4_offset_video_only_mp4_mkv_video_duration_and_fail_closed_ffprobe(tmp_path):
    """Covers R4 BLOCKER 1 (offset video-only MP4 renders exact red frames),
    R4 BLOCKER 2 (MKV 2s video + 5s audio rejects 3.5-4.5s cut),
    and R4 MAJOR 1 (render fails closed if ffprobe is absent)."""
    # 1. Video-only MP4 spanning 1-3s: 1-2s red, 2-3s blue -> cut 1.2-1.7s must render RED frames!
    v_off = tmp_path / "v_only_1_3.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=red:s=64x64:r=24:d=1.0",
            "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=24:d=1.0",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,setpts=PTS+1.0/TB[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v_off),
        ],
        check=True,
    )
    p_off = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "c1", "source": str(v_off), "in_s": 1.2, "out_s": 1.7}],
    }
    assert edit_plan.validate_plan(p_off, check_files=True)["valid"] is True
    pf = tmp_path / "p_off_red.json"
    pf.write_text(json.dumps(p_off), encoding="utf-8")
    out_red = tmp_path / "out_red.mp4"
    r_red = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf), "-o", str(out_red)],
        capture_output=True, text=True, check=False,
    )
    assert r_red.returncode == 0, r_red.stderr
    rgb = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out_red), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    assert rgb[0] > 180 and rgb[2] < 60, f"expected red frames from 1.2-1.7s, got rgb=({rgb[0]},{rgb[1]},{rgb[2]})"

    # 2. MKV with 2s video + 5s audio: 3.5-4.5s cut must be rejected by validate_plan(check_files=True)!
    mkv = tmp_path / "v2_a5.mkv"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=green:s=64x64:r=24:d=2.0",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(mkv),
        ],
        check=True,
    )
    p_mkv = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "m1", "source": str(mkv), "in_s": 3.5, "out_s": 4.5}],
    }
    res_mkv = edit_plan.validate_plan(p_mkv, check_files=True)
    assert res_mkv["valid"] is False, f"MKV past-video cut unexpectedly passed: {res_mkv}"

    # 3. Render fails closed when ffprobe is missing from PATH
    import os, shutil
    ff_bin = shutil.which("ffmpeg")
    if ff_bin:
        fake_bin = tmp_path / "bin_no_ffprobe"
        fake_bin.mkdir()
        (fake_bin / "ffmpeg").symlink_to(ff_bin)
        env = dict(os.environ)
        env["PATH"] = str(fake_bin)
        out_no_probe = tmp_path / "out_np.mp4"
        r_np = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf), "-o", str(out_no_probe)],
            capture_output=True, text=True, env=env, check=False,
        )
        assert r_np.returncode == 1
        assert "ffprobe" in r_np.stderr.lower()


def test_p20_r5_vfr_mkv_valid_cut_and_packet_probe_failure_fails_closed(tmp_path):
    """Covers R5 BLOCKER (VFR Matroska with few packets spanning 0-3.8s accepts 3.0-3.5s cut)
    and R5 MAJOR (failing packet count probe fails closed instead of exiting 0)."""
    # Create a VFR MKV: 0-2.0s @ 2fps (4 frames) + 2.0-3.8s @ 24fps (~43 frames) -> ~47 packets total, end ~3.8s
    seg1 = tmp_path / "slow.mkv"
    seg2 = tmp_path / "fast.mkv"
    vfr = tmp_path / "vfr.mkv"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=2:d=2.0", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(seg1)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=24:d=1.8", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(seg2)],
        check=True,
    )
    lst = tmp_path / "list.txt"
    lst.write_text(f"file '{seg1}'" + chr(10) + f"file '{seg2}'" + chr(10), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(vfr)],
        check=True,
    )
    p_vfr = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "v1", "source": str(vfr), "in_s": 3.0, "out_s": 3.5}],
    }
    res_vfr = edit_plan.validate_plan(p_vfr, check_files=True)
    assert res_vfr["valid"] is True, f"VFR MKV valid 3.0-3.5s cut rejected: {res_vfr}"
    pf = tmp_path / "p_vfr.json"
    pf.write_text(json.dumps(p_vfr), encoding="utf-8")
    out_vfr = tmp_path / "out_vfr.mp4"
    r_vfr = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf), "-o", str(out_vfr)],
        capture_output=True, text=True, check=False,
    )
    assert r_vfr.returncode == 0, r_vfr.stderr

    # Fault injection: ffprobe wrapper that fails ONLY on packet-inspection probe -> render must fail closed (exit 1)!
    import os, shutil, stat
    real_ffprobe = shutil.which("ffprobe")
    real_ffmpeg = shutil.which("ffmpeg")
    if real_ffprobe and real_ffmpeg:
        bin_dir = tmp_path / "fault_bin"
        bin_dir.mkdir()
        (bin_dir / "ffmpeg").symlink_to(real_ffmpeg)
        wrapper = bin_dir / "ffprobe"
        wrapper.write_text(
            '#!/bin/sh' + chr(10)
            + 'for a in "$@"; do' + chr(10)
            + '  case "$a" in *packet=*) exit 1 ;; esac' + chr(10)
            + 'done' + chr(10)
            + f'exec "{real_ffprobe}" "$@"' + chr(10),
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        out_fail = tmp_path / "out_fault.mp4"
        # Use a simple MP4 fixture whose header has stream.duration so only post-render packet probe fails
        p_ok = {
            "version": 1,
            "canvas": {"width": 64, "height": 64, "fps": 24},
            "clips": [{"id": "c1", "source": str(out_vfr), "in_s": 0.0, "out_s": 0.4}],
        }
        pf2 = tmp_path / "p_ok.json"
        pf2.write_text(json.dumps(p_ok), encoding="utf-8")
        r_fault = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf2), "-o", str(out_fail)],
            capture_output=True, text=True, env=env, check=False,
        )
        assert r_fault.returncode == 1, f"expected fail-closed exit 1 on packet probe failure, got {r_fault.returncode}"


def test_p20_r6_corrupt_probe_stderr_and_mkv_source_packet_probe_failure(tmp_path):
    """Covers R6 MAJOR 1 (ffprobe stderr error on exit 0 fails verification),
    R6 MAJOR 2 (MKV source packet probe error does not fall back to 5s audio container duration),
    and R6 MINOR (clear packet verification failure message, never 'only None frames')."""
    import os, shutil, stat
    real_ffprobe = shutil.which("ffprobe")
    real_ffmpeg = shutil.which("ffmpeg")
    if not (real_ffprobe and real_ffmpeg):
        return

    # 1. Source MKV (2s video + 5s audio) with packet probe forced to fail -> validate_plan(check_files=True) MUST fail!
    mkv = tmp_path / "v2_a5_r6.mkv"
    subprocess.run(
        [
            real_ffmpeg, "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=green:s=64x64:r=24:d=2.0",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(mkv),
        ],
        check=True,
    )
    bin_fail = tmp_path / "bin_fail_pkt"
    bin_fail.mkdir()
    (bin_fail / "ffmpeg").symlink_to(real_ffmpeg)
    w_fail = bin_fail / "ffprobe"
    w_fail.write_text(
        '#!/bin/sh' + chr(10)
        + 'for a in "$@"; do' + chr(10)
        + '  case "$a" in *packet=*) exit 1 ;; esac' + chr(10)
        + 'done' + chr(10)
        + f'exec "{real_ffprobe}" "$@"' + chr(10),
        encoding="utf-8",
    )
    w_fail.chmod(w_fail.stat().st_mode | stat.S_IXUSR)
    p_mkv = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "m1", "source": str(mkv), "in_s": 3.5, "out_s": 4.5}],
    }
    pf = tmp_path / "p_mkv_r6.json"
    pf.write_text(json.dumps(p_mkv), encoding="utf-8")
    env_fail = dict(os.environ)
    env_fail["PATH"] = f"{bin_fail}:{env_fail.get('PATH', '')}"
    r_val = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "validate", str(pf), "--check-files"],
        capture_output=True, text=True, env=env_fail, check=False,
    )
    assert r_val.returncode == 1, f"MKV validation fell back to audio tail on packet probe failure: {r_val.stdout}"

    # 2. Output packet probe writing error to stderr while exiting 0 -> render MUST fail closed with clear message!
    clip = tmp_path / "ok1s.mp4"
    subprocess.run(
        [real_ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=24:d=1.0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
        check=True,
    )
    bin_err = tmp_path / "bin_stderr_pkt"
    bin_err.mkdir()
    (bin_err / "ffmpeg").symlink_to(real_ffmpeg)
    w_err = bin_err / "ffprobe"
    w_err.write_text(
        '#!/bin/sh' + chr(10)
        + 'for a in "$@"; do' + chr(10)
        + '  case "$a" in *packet=*) echo "partial file" >&2; exec "' + real_ffprobe + '" "$@" ;; esac' + chr(10)
        + 'done' + chr(10)
        + f'exec "{real_ffprobe}" "$@"' + chr(10),
        encoding="utf-8",
    )
    w_err.chmod(w_err.stat().st_mode | stat.S_IXUSR)
    p_ok = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "c1", "source": str(clip), "in_s": 0.0, "out_s": 0.5}],
    }
    pf2 = tmp_path / "p_ok_r6.json"
    pf2.write_text(json.dumps(p_ok), encoding="utf-8")
    env_err = dict(os.environ)
    env_err["PATH"] = f"{bin_err}:{env_err.get('PATH', '')}"
    r_rend = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "render", str(pf2), "-o", str(tmp_path / "out_r6.mp4")],
        capture_output=True, text=True, env=env_err, check=False,
    )
    assert r_rend.returncode == 1
    assert "partial file" in r_rend.stderr
    assert "only None frames" not in r_rend.stderr


def test_p20_r7_truncated_source_mp4_rejected_and_mkv_packet_error_priority(tmp_path):
    """Covers R7 MAJOR (truncated MP4 with intact header rejected by validate --check-files)
    and R7 MINOR (packet-probe error reported before duration check)."""
    import os, shutil, stat
    real_ffprobe = shutil.which("ffprobe")
    real_ffmpeg = shutil.which("ffmpeg")
    if not (real_ffprobe and real_ffmpeg):
        return

    src = tmp_path / "full1s.mp4"
    subprocess.run(
        [real_ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=24:d=1.0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )
    # Simulate a truncated MP4 where header duration is 1.0s but packet scan emits partial file error on stderr
    bin_trunc = tmp_path / "bin_trunc"
    bin_trunc.mkdir()
    (bin_trunc / "ffmpeg").symlink_to(real_ffmpeg)
    w_trunc = bin_trunc / "ffprobe"
    w_trunc.write_text(
        '#!/bin/sh' + chr(10)
        + 'for a in "$@"; do' + chr(10)
        + '  case "$a" in *packet=*) echo "partial file" >&2; exec "' + real_ffprobe + '" "$@" ;; esac' + chr(10)
        + 'done' + chr(10)
        + f'exec "{real_ffprobe}" "$@"' + chr(10),
        encoding="utf-8",
    )
    w_trunc.chmod(w_trunc.stat().st_mode | stat.S_IXUSR)
    p = {
        "version": 1,
        "canvas": {"width": 64, "height": 64, "fps": 24},
        "clips": [{"id": "c1", "source": str(src), "in_s": 0.0, "out_s": 1.0}],
    }
    pf = tmp_path / "p_trunc.json"
    pf.write_text(json.dumps(p), encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = f"{bin_trunc}:{env.get('PATH', '')}"
    r_val = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "edit_plan.py"), "validate", str(pf), "--check-files"],
        capture_output=True, text=True, env=env, check=False,
    )
    assert r_val.returncode == 1
    assert "partial file" in r_val.stdout
