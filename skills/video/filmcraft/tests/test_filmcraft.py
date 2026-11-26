"""Test suite for skills/video/filmcraft/scripts/filmcraft.py.

Covers:
  - `doctor`: required vs optional tools, sibling skill resolution (flat and
    category-bucketed), actionable hints, and non-zero exit when required tools
    are absent.
  - `route`: raw footage, code-first motion, Liquid Midnight launch film,
    Liquid Dawn film, hybrid footage+motion, reference-based film, reference
    dissection only, silent motion loop, and audio-only rejection/routing.
  - `verify`: combined pass receipt, visual failure, audio failure, duration
    mismatch, explicit `--skip-audio`, missing target MP4, AND prove-the-negative
    checks ensuring missing sibling gates report `skipped_missing_tool` and
    NEVER exit 0 (never fake-green).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import filmcraft  # noqa: E402

SCRIPT_PATH = SCRIPTS_DIR / "filmcraft.py"


def _write_strict_video_gate(path: Path, exit_code: int) -> Path:
    """Strict mock enforcing motion-lab video_qa.py grade CLI contract."""
    path.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "import argparse, json, sys" + chr(10)
        + "p = argparse.ArgumentParser()" + chr(10)
        + "sub = p.add_subparsers(dest='cmd', required=True)" + chr(10)
        + "g = sub.add_parser('grade')" + chr(10)
        + "g.add_argument('input')" + chr(10)
        + "g.add_argument('--beats')" + chr(10)
        + "g.add_argument('--json', action='store_true')" + chr(10)
        + "ns = p.parse_args()" + chr(10)
        + f"print(json.dumps({{'gate': 'video_qa', 'pass': {exit_code == 0!r}, 'argv': sys.argv[1:]}}))" + chr(10)
        + f"sys.exit({exit_code})" + chr(10)
    )
    path.write_text(code, encoding="utf-8")
    return path


def _write_strict_audio_gate(path: Path, exit_code: int) -> Path:
    """Strict mock enforcing soundcraft audio_qa.py check CLI contract."""
    path.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "import argparse, json, sys" + chr(10)
        + "p = argparse.ArgumentParser()" + chr(10)
        + "sub = p.add_subparsers(dest='cmd', required=True)" + chr(10)
        + "c = sub.add_parser('check')" + chr(10)
        + "c.add_argument('media_path')" + chr(10)
        + "c.add_argument('--expected-dur', type=float)" + chr(10)
        + "c.add_argument('--json', action='store_true')" + chr(10)
        + "ns = p.parse_args()" + chr(10)
        + f"print(json.dumps({{'gate': 'audio_qa', 'passed': {exit_code == 0!r}, 'argv': sys.argv[1:]}}))" + chr(10)
        + f"sys.exit({exit_code})" + chr(10)
    )
    path.write_text(code, encoding="utf-8")
    return path


def _make_fake_mp4(tmp_path: Path, name: str = "clip.mp4") -> Path:
    p = tmp_path / name
    p.write_bytes(b"ftypmp42isom0000")
    return p


def _write_stub_skill_md(skill_dir: Path, name: str) -> None:
    lines = ["---", f"name: {name}", "description: test stub", "---", ""]
    (skill_dir / "SKILL.md").write_text(chr(10).join(lines), encoding="utf-8")


def _make_skill_tree(
    tmp_path: Path,
    *,
    bucketed: bool = False,
    video_rc: int | None = 0,
    audio_rc: int | None = 0,
) -> Path:
    root = tmp_path / "skills_root"
    root.mkdir(parents=True, exist_ok=True)
    if video_rc is not None:
        vdir = root / ("video/motion-lab" if bucketed else "motion-lab")
        vdir.mkdir(parents=True, exist_ok=True)
        _write_stub_skill_md(vdir, "motion-lab")
        _write_strict_video_gate(vdir / "scripts/video_qa.py", video_rc)
    if audio_rc is not None:
        adir = root / ("audio/soundcraft" if bucketed else "soundcraft")
        adir.mkdir(parents=True, exist_ok=True)
        _write_stub_skill_md(adir, "soundcraft")
        _write_strict_audio_gate(adir / "scripts/audio_qa.py", audio_rc)
    return root


# --- doctor tests ---


def test_doctor_all_present_ready(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    for skill, scripts in filmcraft.SKILL_KEY_SCRIPTS.items():
        sdir = root / skill
        sdir.mkdir(parents=True, exist_ok=True)
        _write_stub_skill_md(sdir, skill)
        for rel in scripts:
            p = sdir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# stub" + chr(10), encoding="utf-8")

    report = filmcraft.run_doctor(
        skills_root=root,
        which_fn=lambda name: f"/usr/bin/{name}",
        playwright_probe=lambda _: {"found": True, "path": "/usr/bin/playwright", "source": "PATH"},
    )
    assert report["ok"] is True
    assert report["status"] == "ready"
    assert report["missing_required"] == []
    assert report["missing_optional"] == []
    assert report["missing_skills"] == []
    assert report["hints"] == []


def test_doctor_missing_required_tool_fails(tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return None if name == "ffmpeg" else f"/usr/bin/{name}"

    report = filmcraft.run_doctor(
        skills_root=tmp_path,
        which_fn=fake_which,
        playwright_probe=lambda _: {"found": False, "path": None, "source": None},
    )
    assert report["ok"] is False
    assert report["status"] == "missing_required"
    assert "ffmpeg" in report["missing_required"]
    assert any("[required:ffmpeg]" in h for h in report["hints"])


def test_doctor_missing_optional_and_skills_reports_degraded(tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in filmcraft.REQUIRED_TOOLS else None

    report = filmcraft.run_doctor(
        skills_root=tmp_path,
        which_fn=fake_which,
        playwright_probe=lambda _: {"found": False, "path": None, "source": None},
    )
    assert report["ok"] is True
    assert report["status"] == "degraded"
    assert set(report["missing_optional"]) == set(filmcraft.OPTIONAL_TOOLS)
    assert set(report["missing_skills"]) == set(filmcraft.SIBLING_SKILLS)
    assert len(report["hints"]) >= len(filmcraft.OPTIONAL_TOOLS) + len(filmcraft.SIBLING_SKILLS)


def test_doctor_resolves_bucketed_skill_layout(tmp_path: Path) -> None:
    root = _make_skill_tree(tmp_path, bucketed=True, video_rc=0, audio_rc=0)
    report = filmcraft.run_doctor(
        skills_root=root,
        which_fn=lambda name: f"/usr/bin/{name}",
        playwright_probe=lambda _: {"found": True, "path": "/usr/bin/playwright", "source": "PATH"},
    )
    assert report["skills"]["motion-lab"]["found"] is True
    assert report["skills"]["soundcraft"]["found"] is True
    assert report["skills"]["motion-lab"]["scripts"]["scripts/video_qa.py"] is True
    assert report["skills"]["soundcraft"]["scripts"]["scripts/audio_qa.py"] is True


def test_doctor_cli_json_output(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "doctor", "--skills-root", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(proc.stdout)
    assert "required_tools" in data
    assert "optional_tools" in data
    assert "skills" in data
    assert proc.returncode == (0 if data["ok"] else 1)


# --- route tests ---


def test_route_raw_footage() -> None:
    res = filmcraft.route_intent(
        "trim retakes and dead air from my raw talking-head interview footage",
        has_footage=True,
    )
    assert res["in_scope"] is True
    assert res["rejected"] is False
    assert res["lane"] == "raw_footage"
    assert res["skills"] == ["video-cut", "soundcraft"]
    assert res["needs_ingest"] is False
    assert any("unheard.py" in cmd for cmd in res["next_commands"])


def test_route_code_first_motion_with_sound() -> None:
    res = filmcraft.route_intent("create a 12s animated logo reveal with sound effects")
    assert res["in_scope"] is True
    assert res["lane"] == "code_first_motion"
    assert res["skills"] == ["motion-lab", "soundcraft"]
    assert res["extracted_duration_sec"] == 12.0
    assert any("render.mjs" in cmd and "--verify" in cmd for cmd in res["next_commands"])


def test_route_liquid_midnight_launch_film() -> None:
    res = filmcraft.route_intent("make a 45s liquid midnight launch film with sound")
    assert res["in_scope"] is True
    assert res["lane"] == "code_first_motion"
    assert res["skills"] == ["motion-lab", "liquid-midnight", "soundcraft"]
    assert res["extracted_duration_sec"] == 45.0
    assert any("materialize.mjs" in cmd for cmd in res["next_commands"])
    assert any("--expected-dur 45" in cmd for cmd in res["next_commands"])


def test_route_liquid_dawn_silent_loop() -> None:
    res = filmcraft.route_intent("build a silent 6s liquid dawn animated loop")
    assert res["in_scope"] is True
    assert res["lane"] == "code_first_motion"
    assert res["skills"] == ["motion-lab", "liquid-dawn"]
    assert "soundcraft" not in res["skills"]
    assert any("--skip-audio" in cmd for cmd in res["next_commands"])


def test_route_reference_based_film() -> None:
    res = filmcraft.route_intent(
        "recreate this reference video https://example.com/spot.mp4 as a 30s launch film",
        has_reference=True,
        needs_audio=True,
    )
    assert res["in_scope"] is True
    assert res["needs_ingest"] is True
    assert res["lane"] == "code_first_motion"
    assert res["skills"] == ["motion-lab", "soundcraft"]
    assert res["stages"][0]["name"] == "ingest_dissect"
    assert res["stages"][0]["active"] is True
    assert any("video_ingest.py" in cmd for cmd in res["next_commands"])


def test_route_reference_dissection_only() -> None:
    res = filmcraft.route_intent("dissect https://youtube.com/watch?v=demo123")
    assert res["in_scope"] is True
    assert res["needs_ingest"] is True
    assert res["lane"] == "reference_dissection"
    assert res["skills"] == []
    assert any("video_ingest.py" in cmd for cmd in res["next_commands"])


def test_route_hybrid_footage_and_motion() -> None:
    res = filmcraft.route_intent(
        "edit my raw interview footage and add liquid midnight animated title cards with sound",
        has_footage=True,
    )
    assert res["in_scope"] is True
    assert res["lane"] == "hybrid"
    assert res["skills"] == ["video-cut", "motion-lab", "liquid-midnight", "soundcraft"]


def test_route_audio_only_rejected_and_handed_to_soundcraft() -> None:
    res = filmcraft.route_intent("mix and master my podcast audio track to -14 LUFS")
    assert res["in_scope"] is False
    assert res["rejected"] is True
    assert res["lane"] == "audio_only"
    assert res["skills"] == ["soundcraft"]
    assert "soundcraft" in (res["rejection_reason"] or "")


def test_route_both_styles_emits_warning() -> None:
    res = filmcraft.route_intent("make a launch film mixing liquid midnight and liquid dawn")
    assert res["in_scope"] is True
    assert len(res["warnings"]) == 1
    assert "Never mix" in res["warnings"][0]
    assert ("liquid-midnight" in res["skills"]) ^ ("liquid-dawn" in res["skills"])


def test_route_cli_json_output() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "route",
            "make a 45s liquid midnight launch film with sound",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["skills"] == ["motion-lab", "liquid-midnight", "soundcraft"]


# --- verify tests (including prove-the-negative) ---


def test_verify_all_gates_pass(tmp_path: Path) -> None:
    mp4 = _make_fake_mp4(tmp_path)
    root = _make_skill_tree(tmp_path, bucketed=True, video_rc=0, audio_rc=0)

    receipt, code = filmcraft.run_verify(
        mp4,
        beats="0,12,24",
        skills_root=root,
        which_fn=lambda _: None,
    )
    assert code == 0
    assert receipt["ok"] is True
    assert receipt["gates"]["video_qa"]["status"] == "pass"
    assert receipt["gates"]["audio_qa"]["status"] == "pass"
    assert "--beats" in receipt["gates"]["video_qa"]["parsed_output"]["argv"]
    assert "0,12,24" in receipt["gates"]["video_qa"]["parsed_output"]["argv"]
    assert "grade" in receipt["gates"]["video_qa"]["parsed_output"]["argv"]
    assert "check" in receipt["gates"]["audio_qa"]["parsed_output"]["argv"]


def test_verify_prove_the_negative_missing_video_gate_never_passes(tmp_path: Path) -> None:
    """When motion-lab/scripts/video_qa.py is absent, verify MUST NOT fake-green."""
    mp4 = _make_fake_mp4(tmp_path)
    root = _make_skill_tree(tmp_path, bucketed=False, video_rc=None, audio_rc=0)

    receipt, code = filmcraft.run_verify(mp4, skills_root=root, which_fn=lambda _: None)
    assert code == 2
    assert receipt["ok"] is False
    assert receipt["gates"]["video_qa"]["status"] == "skipped_missing_tool"
    assert receipt["gates"]["audio_qa"]["status"] == "pass"
    assert receipt["missing_tools"] == ["video_qa"]


def test_verify_prove_the_negative_missing_audio_gate_never_passes(tmp_path: Path) -> None:
    """When soundcraft/scripts/audio_qa.py is absent, verify MUST NOT fake-green."""
    mp4 = _make_fake_mp4(tmp_path)
    root = _make_skill_tree(tmp_path, bucketed=False, video_rc=0, audio_rc=None)

    receipt, code = filmcraft.run_verify(mp4, skills_root=root, which_fn=lambda _: None)
    assert code == 2
    assert receipt["ok"] is False
    assert receipt["gates"]["video_qa"]["status"] == "pass"
    assert receipt["gates"]["audio_qa"]["status"] == "skipped_missing_tool"
    assert receipt["missing_tools"] == ["audio_qa"]


def test_verify_prove_the_negative_both_gates_missing(tmp_path: Path) -> None:
    mp4 = _make_fake_mp4(tmp_path)
    empty_root = tmp_path / "empty_skills"
    empty_root.mkdir()

    receipt, code = filmcraft.run_verify(mp4, skills_root=empty_root, which_fn=lambda _: None)
    assert code == 2
    assert receipt["ok"] is False
    assert receipt["missing_tools"] == ["video_qa", "audio_qa"]


def test_verify_skip_audio_allows_silent_pass(tmp_path: Path) -> None:
    mp4 = _make_fake_mp4(tmp_path)
    root = _make_skill_tree(tmp_path, bucketed=False, video_rc=0, audio_rc=None)

    receipt, code = filmcraft.run_verify(mp4, skills_root=root, skip_audio=True, which_fn=lambda _: None)
    assert code == 0
    assert receipt["ok"] is True
    assert receipt["gates"]["audio_qa"]["status"] == "skipped_by_flag"


def test_verify_visual_gate_failure_returns_exit_1(tmp_path: Path) -> None:
    mp4 = _make_fake_mp4(tmp_path)
    root = _make_skill_tree(tmp_path, bucketed=False, video_rc=1, audio_rc=0)

    receipt, code = filmcraft.run_verify(mp4, skills_root=root, which_fn=lambda _: None)
    assert code == 1
    assert receipt["ok"] is False
    assert receipt["gates"]["video_qa"]["status"] == "fail"
    assert receipt["failed_gates"] == ["video_qa"]


def test_verify_audio_gate_failure_returns_exit_1(tmp_path: Path) -> None:
    mp4 = _make_fake_mp4(tmp_path)
    root = _make_skill_tree(tmp_path, bucketed=False, video_rc=0, audio_rc=1)

    receipt, code = filmcraft.run_verify(mp4, skills_root=root, which_fn=lambda _: None)
    assert code == 1
    assert receipt["ok"] is False
    assert receipt["gates"]["audio_qa"]["status"] == "fail"
    assert receipt["failed_gates"] == ["audio_qa"]


def test_verify_missing_mp4_returns_exit_2(tmp_path: Path) -> None:
    root = _make_skill_tree(tmp_path, bucketed=False, video_rc=0, audio_rc=0)
    receipt, code = filmcraft.run_verify(tmp_path / "does-not-exist.mp4", skills_root=root)
    assert code == 2
    assert receipt["ok"] is False
    assert "not found" in receipt["error"]


def test_verify_expected_dur_unverified_without_ffprobe_fails(tmp_path: Path) -> None:
    """If --expected-dur is requested but ffprobe is unavailable, duration_check fails closed."""
    mp4 = _make_fake_mp4(tmp_path)
    root = _make_skill_tree(tmp_path, bucketed=False, video_rc=0, audio_rc=0)
    receipt, code = filmcraft.run_verify(
        mp4,
        expected_dur=10.0,
        skills_root=root,
        which_fn=lambda _: None,
    )
    assert code == 1
    assert receipt["ok"] is False
    assert receipt["duration_check"]["status"] == "unverified_duration"


def test_verify_expected_dur_check_with_real_ffmpeg(tmp_path: Path) -> None:
    """Generate a real 2.0s synthetic MP4 when ffmpeg is installed and verify duration checking."""
    ffmpeg = filmcraft.shutil.which("ffmpeg")
    ffprobe = filmcraft.shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe not installed")

    mp4 = tmp_path / "synth.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f", "lavfi", "-i", "color=c=0x101828:s=320x180:d=2:r=24",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(mp4),
        ],
        capture_output=True,
        check=True,
    )
    root = _make_skill_tree(tmp_path, bucketed=True, video_rc=0, audio_rc=0)

    ok_receipt, ok_code = filmcraft.run_verify(mp4, expected_dur=2.0, skills_root=root)
    assert ok_code == 0
    assert ok_receipt["ok"] is True
    assert ok_receipt["duration_check"]["status"] == "pass"

    bad_receipt, bad_code = filmcraft.run_verify(mp4, expected_dur=10.0, skills_root=root)
    assert bad_code == 1
    assert bad_receipt["ok"] is False
    assert bad_receipt["duration_check"]["status"] == "fail"


def test_p20_empty_stdout_exit_zero_never_passes(tmp_path: Path) -> None:
    """A child gate exiting 0 with empty stdout must fail closed as status='error' (exit 2)."""
    mp4 = _make_fake_mp4(tmp_path)
    root = tmp_path / "empty_gates"
    for rel in ("video/motion-lab/scripts/video_qa.py", "audio/soundcraft/scripts/audio_qa.py"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("import sys; sys.exit(0)" + chr(10), encoding="utf-8")
    receipt, code = filmcraft.run_verify(mp4, skills_root=root, which_fn=lambda _: None)
    assert code == 2
    assert receipt["ok"] is False
    assert receipt["gates"]["video_qa"]["status"] == "error"
    assert receipt["gates"]["audio_qa"]["status"] == "error"


def test_p20_route_never_silently_waives_audio_and_podcast_recording_is_audio_only() -> None:
    r_logo = filmcraft.route_intent("make a 6s animated logo reveal")
    assert "soundcraft" in r_logo["skills"]
    assert all("--skip-audio" not in cmd for cmd in r_logo["next_commands"])
    assert any("verify out/final.mp4" in cmd for cmd in r_logo["next_commands"])
    assert any("audio_qa.py sheet out/final.mp4 --out " in cmd for cmd in r_logo["next_commands"])

    r_pod = filmcraft.route_intent("mix my podcast recording")
    assert r_pod["in_scope"] is False
    assert r_pod["lane"] == "audio_only"
    assert r_pod["skills"] == ["soundcraft"]


def test_p20_footage_route_emits_real_unheard_and_edit_plan_clis() -> None:
    r = filmcraft.route_intent("cut raw footage into a talking-head video")
    cmds = r["next_commands"]
    assert any("unheard.py detect " in c and "--transcript " in c for c in cmds)
    assert any("edit_plan.py validate " in c for c in cmds)
    assert any("edit_plan.py render " in c for c in cmds)
    assert any("audio_qa.py sheet out/final.mp4 --out " in c for c in cmds)


def test_p20_ffprobe_na_duration_does_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the real _probe_media_ffprobe parser when ffprobe returns duration='N/A'."""
    mp4 = _make_fake_mp4(tmp_path)
    root = _make_skill_tree(tmp_path, bucketed=True, video_rc=0, audio_rc=0)
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd and "ffprobe" in str(cmd[0]):
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps({"format": {"duration": "N/A"}, "streams": [{"codec_type": "video"}]}), stderr=""
            )
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(filmcraft.subprocess, "run", fake_run)
    receipt, code = filmcraft.run_verify(mp4, expected_dur=5.0, skills_root=root, which_fn=lambda n: "/usr/bin/" + n)
    assert code == 1
    assert receipt["probe"]["duration_sec"] is None
    assert receipt["duration_check"]["status"] == "unverified_duration"


def test_p20_r3_silence_scope_reference_dissection_and_hybrid_rgba_composite(tmp_path: Path) -> None:
    # 1. "no audio" waives audio even though the word "audio" appears
    r_no_audio = filmcraft.route_intent("make a launch video with no audio")
    assert "soundcraft" not in r_no_audio["skills"]
    assert any("--skip-audio" in c for c in r_no_audio["next_commands"])
    assert all("master.wav" not in c for c in r_no_audio["next_commands"])

    # 2. Section-scoped "silent intro" does NOT waive whole-video audio (even without mentioning voiceover)
    r_si = filmcraft.route_intent("make a launch video with a silent intro")
    assert "soundcraft" in r_si["skills"]
    assert all("--skip-audio" not in c for c in r_si["next_commands"])

    # 3. Silent intro + voiceover keeps soundcraft + mux
    r_vo = filmcraft.route_intent("make a launch video with a silent intro and voiceover")
    assert "soundcraft" in r_vo["skills"]
    assert any("ffmpeg" in c and "master.wav" in c and "out/final.mp4" in c for c in r_vo["next_commands"])

    # 4. Reference-only URL dissection keeps video and reads manifest.json video_path
    r_ref = filmcraft.route_intent("dissect https://example.com/demo")
    assert r_ref["lane"] == "reference_dissection"
    assert any("--keep-video" in c for c in r_ref["next_commands"])
    assert any("manifest.json" in c for c in r_ref["next_commands"])

    # 5. Hybrid route emits RGBA PNG overlay with mkdir -p out and eof_action=pass, empirically verified via FFmpeg!
    r_hyb = filmcraft.route_intent("cut raw talking-head footage and add animated motion graphics overlay")
    assert r_hyb["lane"] == "hybrid"
    assert any("--edit-dir edit" in c for c in r_hyb["next_commands"])
    assert any("mkdir -p out" in c and "work/overlay/frames/%04d.png" in c and "eof_action=pass" in c for c in r_hyb["next_commands"])

    ffmpeg = filmcraft.shutil.which("ffmpeg")
    ffprobe = filmcraft.shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        # 1.0s red footage + 0.2s half-transparent blue RGBA PNG overlay -> red stays visible AND duration stays 1.0s!
        work = tmp_path / "work"
        frames_dir = work / "overlay" / "frames"
        frames_dir.mkdir(parents=True)
        footage = work / "footage-cut.mp4"
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error",
                "-f", "lavfi", "-i", "color=c=red:s=64x64:r=24:d=1.0",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(footage),
            ],
            check=True,
        )
        # Generate 5 RGBA PNG frames (~0.21s @ 24fps): left half opaque blue, right half transparent (alpha=0)
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error",
                "-f", "lavfi", "-i", "color=c=blue@0.0:s=64x64:r=24:d=0.21,format=rgba,geq=r='if(lt(X,32),0,0)':g='0':b='if(lt(X,32),255,0)':a='if(lt(X,32),255,0)'",
                "-frames:v", "5", str(frames_dir / "%04d.png"),
            ],
            check=True,
        )
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        out_mp4 = out_dir / "final.mp4"
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error",
                "-i", str(footage),
                "-framerate", "24", "-i", str(frames_dir / "%04d.png"),
                "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass[v]",
                "-map", "[v]", "-map", "0:a?",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy",
                str(out_mp4),
            ],
            check=True,
        )
        # Verify full 1.0s duration preserved (not cut to 0.2s)
        pr = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(out_mp4)],
            capture_output=True, text=True, check=True,
        )
        assert float(pr.stdout.strip()) >= 0.9
        # Verify frame 0 right half (x=48, y=32) still shows red footage through transparent overlay!
        rgb = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(out_mp4), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        ).stdout
        idx_right = (32 * 64 + 48) * 3
        r_ch, g_ch, b_ch = rgb[idx_right], rgb[idx_right + 1], rgb[idx_right + 2]
        assert r_ch > 180 and b_ch < 60, f"red footage hidden under overlay: rgb=({r_ch},{g_ch},{b_ch})"
        idx_left = (32 * 64 + 16) * 3
        rl, gl, bl = rgb[idx_left], rgb[idx_left + 1], rgb[idx_left + 2]
        assert bl > 180 and rl < 60, f"blue overlay missing on left half: rgb=({rl},{gl},{bl})"


def test_p20_real_sibling_parsers_accept_verify_arguments(tmp_path: Path) -> None:
    """When running inside broomva/skills with real sibling scripts, verify passes flags accepted by both real parsers."""
    repo_skills = Path(__file__).resolve().parents[3]
    vqa = repo_skills / "video/motion-lab/scripts/video_qa.py"
    aqa = repo_skills / "audio/soundcraft/scripts/audio_qa.py"
    if not (vqa.is_file() and aqa.is_file()):
        pytest.skip("real sibling scripts not colocated outside monorepo")
    ffmpeg = filmcraft.shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not installed")
    mp4 = tmp_path / "real_check.mp4"
    subprocess.run(
        [
            ffmpeg, "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            str(mp4),
        ],
        check=True,
    )
    receipt, code = filmcraft.run_verify(mp4, expected_dur=2.0, beats="0,24", skills_root=repo_skills)
    # Neither real sibling parser may exit 2 (argument rejection)!
    assert receipt["gates"]["video_qa"]["exit_code"] in (0, 1), receipt["gates"]["video_qa"]
    assert receipt["gates"]["audio_qa"]["exit_code"] in (0, 1), receipt["gates"]["audio_qa"]
    assert receipt["gates"]["video_qa"]["status"] in ("pass", "fail")
    assert receipt["gates"]["audio_qa"]["status"] in ("pass", "fail")


def test_p20_r4_section_silence_variants_and_silent_hybrid_strips_audio(tmp_path: Path) -> None:
    import shlex

    for brief in (
        "make a launch video with a muted intro",
        "make a launch video with no audio in the intro",
        "cut raw footage and add motion graphics overlay but mute the intro",
        "make a launch video with no audio during the final three seconds",
    ):
        r = filmcraft.route_intent(brief)
        assert "soundcraft" in r["skills"], f"{brief!r} dropped soundcraft"
        assert all("--skip-audio" not in c for c in r["next_commands"])

    # Silent hybrid brief must pass --transparent AND strip audio (-an), never copying source AAC!
    r_sh = filmcraft.route_intent("cut raw footage and add motion graphics overlay with no audio")
    assert r_sh["lane"] == "hybrid"
    assert "soundcraft" not in r_sh["skills"]
    assert any("--transparent" in c for c in r_sh["next_commands"])
    comp_cmd = next(c for c in r_sh["next_commands"] if "overlay=0:0:eof_action=pass" in c)
    assert " -an " in comp_cmd
    assert "-map 0:a?" not in comp_cmd

    ffmpeg = filmcraft.shutil.which("ffmpeg")
    ffprobe = filmcraft.shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        # Execute the ACTUAL emitted compositor command in tmp_path on footage WITH an audio track -> output has 0 audio streams!
        (tmp_path / "work/overlay/frames").mkdir(parents=True)
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error",
                "-f", "lavfi", "-i", "color=c=red:s=64x64:r=24:d=1.0",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(tmp_path / "work/footage-cut.mp4"),
            ],
            check=True,
        )
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error",
                "-f", "lavfi", "-i", "color=c=blue@0.0:s=64x64:r=24:d=0.21,format=rgba,geq=r='0':g='0':b='if(lt(X,32),255,0)':a='if(lt(X,32),255,0)'",
                "-frames:v", "5", str(tmp_path / "work/overlay/frames/%04d.png"),
            ],
            check=True,
        )
        # Split off `mkdir -p out && ` and run the emitted ffmpeg command directly inside tmp_path
        (tmp_path / "out").mkdir()
        ff_part = comp_cmd.split("&&", 1)[1].strip()
        argv = shlex.split(ff_part)
        argv[0] = ffmpeg
        r_run = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, check=False)
        assert r_run.returncode == 0, r_run.stderr
        pr = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(tmp_path / "out/final.mp4")],
            capture_output=True, text=True, check=True,
        )
        assert pr.stdout.strip() == "", f"silent hybrid kept audio stream: {pr.stdout}"
        # Also verify the ACTUAL routed compositor preserved full duration, red footage on transparent right half, and blue overlay on left half!
        dur_p = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(tmp_path / "out/final.mp4")],
            capture_output=True, text=True, check=True,
        )
        assert float(dur_p.stdout.strip()) >= 0.9
        rgb = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(tmp_path / "out/final.mp4"), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        ).stdout
        idx_r = (32 * 64 + 48) * 3
        assert rgb[idx_r] > 180 and rgb[idx_r + 2] < 60, f"routed compositor hid red footage: rgb={tuple(rgb[idx_r:idx_r+3])}"
        idx_l = (32 * 64 + 16) * 3
        assert rgb[idx_l + 2] > 180 and rgb[idx_l] < 60, f"routed compositor dropped blue overlay: rgb={tuple(rgb[idx_l:idx_l+3])}"


def test_p20_r6_decimal_and_word_section_silence_and_duration_isolation() -> None:
    r_dec = filmcraft.route_intent("make a 30s launch video with no audio for 2.5 seconds")
    assert "soundcraft" in r_dec["skills"]
    assert r_dec["extracted_duration_sec"] == 30.0
    assert all("--skip-audio" not in c for c in r_dec["next_commands"])
    assert any("--expected-dur 30" in c for c in r_dec["next_commands"])

    r_word = filmcraft.route_intent("make a launch video with no audio for three seconds")
    assert "soundcraft" in r_word["skills"]
    assert r_word["extracted_duration_sec"] is None
    assert all("--skip-audio" not in c for c in r_word["next_commands"])

    r_final = filmcraft.route_intent("make a launch video with no audio during the final 3 seconds")
    assert "soundcraft" in r_final["skills"]
    assert r_final["extracted_duration_sec"] is None
    assert all("--seconds 3" not in c and "--expected-dur 3" not in c for c in r_final["next_commands"])


def test_p20_r7_compound_number_words_and_section_for_duration() -> None:
    r_compound = filmcraft.route_intent("Make a 30s launch video with no audio for twenty-one seconds")
    assert "soundcraft" in r_compound["skills"]
    assert r_compound["extracted_duration_sec"] == 30.0
    assert all("--skip-audio" not in c for c in r_compound["next_commands"])

    r_mute_for = filmcraft.route_intent("Make a launch video and mute the intro for 3 seconds")
    assert "soundcraft" in r_mute_for["skills"]
    assert r_mute_for["extracted_duration_sec"] is None
    assert all("--seconds 3" not in c and "--expected-dur 3" not in c for c in r_mute_for["next_commands"])
