"""Integration tests: drive scripts/render.mjs end to end through Playwright.

Skipped when Playwright cannot be resolved; set MOTION_LAB_NODE_DIR to a
directory whose node_modules has playwright. CI also sets
MOTION_LAB_REQUIRE_RENDER=1, which turns a missing Playwright into a failure
instead of a silent skip.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
FIX = HERE / "fixtures"


NODE_DIR = Path(os.environ.get("MOTION_LAB_NODE_DIR", SKILL))


def _playwright_available() -> bool:
    if not shutil.which("node"):
        return False
    probe = subprocess.run(["node", "-e", "require.resolve('playwright')"], cwd=NODE_DIR, capture_output=True)
    return probe.returncode == 0


_RENDER_OK = _playwright_available()
if os.environ.get("MOTION_LAB_REQUIRE_RENDER") and not _RENDER_OK:
    # CI sets this: a render suite that silently skips is a false green.
    raise RuntimeError(f"MOTION_LAB_REQUIRE_RENDER is set but playwright is not resolvable from {NODE_DIR}")

needs_playwright = pytest.mark.skipif(not _RENDER_OK,
                                      reason="node + playwright not resolvable (set MOTION_LAB_NODE_DIR)")


def render(fixture: str, out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / fixture), "--seconds", "1",
                           "--fps", "12", "--width", "160", "--height", "90", "--out", str(out), *extra],
                          cwd=NODE_DIR, capture_output=True, text=True, timeout=180)


def digests(d: Path) -> list[str]:
    return [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((d / "frames").glob("*.png"))]


@needs_playwright
class TestRender:
    def test_renders_frames_0_to_n_minus_1_with_a_sheet(self, tmp_path):
        r = render("good.html", tmp_path, "--verify")
        assert r.returncode == 0, r.stderr
        m = json.loads(r.stdout)
        assert m["frames"] == 12 and m["render_range"] == [0, 11]
        assert len(list((tmp_path / "frames").glob("*.png"))) == 12
        assert (tmp_path / "contact.png").stat().st_size > 0
        assert m["verify"]["pure"] is True and m["driven_by"] == {"renderAt": True, "animations": 1, "smil": 0}

    def test_frames_actually_change_over_time(self, tmp_path):
        render("good.html", tmp_path, "--no-sheet")
        assert len(set(digests(tmp_path))) > 1

    def test_two_independent_renders_are_byte_identical(self, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        render("good.html", a, "--no-sheet")
        render("good.html", b, "--no-sheet")
        assert digests(a) == digests(b)

    def test_verify_catches_an_impure_renderat(self, tmp_path):
        r = render("impure.html", tmp_path, "--verify", "--no-sheet")
        assert r.returncode == 3
        assert json.loads(r.stdout)["verify"]["mismatches"]

    def test_usage_error(self, tmp_path):
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), "--fps", "0", str(FIX / "good.html")],
                           cwd=NODE_DIR, capture_output=True, text=True)
        assert r.returncode == 2 and "positive" in r.stderr



    def test_svg_smil_is_seeked(self, tmp_path):
        # <animate> is not in document.getAnimations(); without an SVG timeline
        # seek the frames follow the wall clock and --verify fails.
        r = render("smil.html", tmp_path, "--verify", "--no-sheet")
        assert r.returncode == 0, r.stderr
        m = json.loads(r.stdout)
        assert m["driven_by"]["smil"] == 1 and m["verify"]["pure"] is True
        assert len(set(digests(tmp_path))) == 12

    def test_warm_up_keeps_the_first_frame_pure_on_composited_animations(self, tmp_path):
        # Measured: removing the animation.ready await before pausing fails this
        # at frame 0 on every cold run (4/4); the shipped code passes.
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "warmup.html"), "--seconds", "1",
                            "--fps", "12", "--width", "1080", "--height", "1080", "--out", str(tmp_path),
                            "--verify", "--no-sheet"], cwd=NODE_DIR, capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads(r.stdout)["verify"]["mismatches"] == []

    def test_a_page_that_throws_exits_5(self, tmp_path):
        r = render("throws.html", tmp_path, "--no-sheet")
        assert r.returncode == 5 and json.loads(r.stdout)["page_errors"]

    def test_a_static_page_exits_6_unless_allowed(self, tmp_path):
        assert render("static.html", tmp_path / "a", "--no-sheet").returncode == 6
        assert render("static.html", tmp_path / "b", "--no-sheet", "--allow-static").returncode == 0

    def test_zero_frame_duration_is_rejected(self, tmp_path):
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "good.html"), "--seconds", "0.01",
                            "--fps", "24", "--out", str(tmp_path)], cwd=NODE_DIR, capture_output=True, text=True)
        assert r.returncode == 2 and "zero frames" in r.stderr

    def test_contact_sheet_spans_frame_0_to_n_minus_1(self, tmp_path):
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "good.html"), "--seconds", "2",
                            "--fps", "12", "--width", "160", "--height", "90", "--out", str(tmp_path)],
                           cwd=NODE_DIR, capture_output=True, text=True, timeout=180)
        picks = json.loads(r.stdout)["contact_frames"]
        assert picks[0] == 0 and picks[-1] == 23 and len(picks) == 12

    def test_verify_reports_its_scope_and_verify_all_checks_every_frame(self, tmp_path):
        sampled = json.loads(render("impure.html", tmp_path / "s", "--verify", "--no-sheet").stdout)["verify"]
        full = json.loads(render("impure.html", tmp_path / "a", "--verify-all", "--no-sheet").stdout)["verify"]
        assert sampled["scope"] == "sampled 3 of 12 frames" and full["scope"] == "all 12 frames"
        assert len(full["mismatches"]) > len(sampled["mismatches"])

    def test_undriven_motion_is_reported_not_called_static(self, tmp_path):
        r = render("undriven.html", tmp_path, "--no-sheet")
        assert r.returncode == 3 and "own clock" in json.loads(r.stdout)["warning"]

    def test_a_preview_loop_running_under_t_exits_7(self, tmp_path):
        # the ?t= check exists but the loop starts unconditionally; no --verify needed
        r = render("loop_unguarded.html", tmp_path, "--no-sheet")
        assert r.returncode == 7, r.stdout + r.stderr
        assert json.loads(r.stdout)["loop_probe"]["raf_during_render"] >= 2

    def test_a_guarded_preview_loop_does_not_trip_the_probe(self, tmp_path):
        m = json.loads(render("good.html", tmp_path, "--no-sheet").stdout)
        assert m["loop_probe"] == {"raf_during_render": 0, "intervals": 0}

    def test_renderat_throwing_mid_render_exits_5_with_a_manifest(self, tmp_path):
        r = render("throws_mid.html", tmp_path, "--no-sheet")
        assert r.returncode == 5
        assert any("boom" in e for e in json.loads(r.stdout)["page_errors"])
        assert (tmp_path / "manifest.json").exists()

    @pytest.mark.parametrize("every", ["0", "0.5", "abc"])
    def test_every_must_be_a_positive_integer(self, tmp_path, every):
        r = render("good.html", tmp_path, "--every", every)
        assert r.returncode == 2 and "--every" in r.stderr

    def test_every_keeps_the_seam_frame(self, tmp_path):
        picks = json.loads(render("good.html", tmp_path, "--every", "5").stdout)["contact_frames"]
        assert picks == [0, 5, 10, 11]


needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@needs_playwright
@needs_ffmpeg
def test_ffmpeg_gif_export_keeps_exact_loop_timing(tmp_path):
    """Receipt for the SKILL.md GIF claim: re-measures whatever ffmpeg is installed.

    24 fps cannot be stored in centisecond GIF delays; a per-frame-rounding encoder
    runs 4% fast. ffmpeg 8.1 alternated 4 and 5 cs and held 6.00 s exactly.
    """
    import sys
    sys.path.insert(0, str(SKILL / "scripts"))
    import motion_math as mm
    r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "good.html"), "--seconds", "6",
                        "--fps", "24", "--width", "160", "--height", "90", "--out", str(tmp_path), "--no-sheet"],
                       cwd=NODE_DIR, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    gif = tmp_path / "anim.gif"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "24", "-i", str(tmp_path / "frames" / "%04d.png"),
                    "-vf", "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse", "-loop", "0", str(gif)],
                   check=True)
    report = mm.gif_check(gif, fps=24)
    assert report["frames"] == 144
    assert report["duration_s"] == pytest.approx(6.0, abs=0.011), report
