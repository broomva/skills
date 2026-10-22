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
        assert m["verify"]["pure"] is True and m["driven_by"] == {"renderAt": True, "animations": 1, "smil": 0, "page_owned": 0}

    def test_frames_actually_change_over_time(self, tmp_path):
        render("good.html", tmp_path, "--no-sheet")
        assert len(set(digests(tmp_path))) > 1

    def test_two_independent_renders_are_byte_identical(self, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        assert render("good.html", a, "--no-sheet").returncode == 0
        assert render("good.html", b, "--no-sheet").returncode == 0
        assert len(digests(a)) == 12 and digests(a) == digests(b)

    def test_verify_catches_an_impure_renderat(self, tmp_path):
        r = render("impure.html", tmp_path, "--verify", "--no-sheet")
        assert r.returncode == 3
        assert json.loads(r.stdout)["verify"]["mismatches"]

    def test_renderat_that_creates_a_css_keyframe_fails_by_default(self, tmp_path):
        # The ownership probe must reject a CSS Animation that first appears when
        # renderAt toggles its class, even without --verify or --verify-all.
        r = render("renderat_creates_keyframe.html", tmp_path, "--no-sheet")
        m = json.loads(r.stdout)
        assert r.returncode == 3, r.stdout + r.stderr
        assert m["renderat_created_animations"][0]["frame_time"] == 0.5
        assert "frame t=0.5" in m["warning"]

    def test_an_animation_renderat_awaits_and_owns_is_not_reported(self, tmp_path):
        # It appears during the first renderAt call, but load code created it and
        # renderAt seeks it, so it is page-owned, not wall-clock motion.
        r = render("async_owned_pop.html", tmp_path, "--no-sheet")
        m = json.loads(r.stdout)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "renderat_created_animations" not in m

    def test_a_capture_call_that_creates_a_keyframe_fails(self, tmp_path):
        # renderAt reads a call counter, so the probe sees nothing; the capture
        # call at frame 3 creates the keyframe and must be reported.
        r = render("history_creates_keyframe.html", tmp_path, "--no-sheet")
        m = json.loads(r.stdout)
        assert r.returncode == 3, r.stdout + r.stderr
        assert m["renderat_created_animations"][0]["frame_time"] == 0.25
        assert m["drift"]["drifting"] == []  # the drift samples alone would miss it

    def test_a_finding_survives_a_later_probe_timeout(self, tmp_path):
        env = {**os.environ, "MOTION_LAB_FRAME_TIMEOUT_MS": "1500"}
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "created_then_hang.html"),
                            "--seconds", "1", "--fps", "12", "--width", "160", "--height", "90",
                            "--out", str(tmp_path), "--no-sheet"],
                           cwd=NODE_DIR, env=env, capture_output=True, text=True, timeout=60)
        m = json.loads((tmp_path / "manifest.json").read_text())
        assert r.returncode == 3, r.stdout + r.stderr
        assert m["renderat_created_animations"][0]["frame_time"] == 0.5
        assert m["aborted_at_frame"] == 0

    def test_seekable_pop_matches_the_direct_pose(self, tmp_path):
        # Linear easing makes the WAAPI and direct forms byte-identical.
        for fixture, out in (("seekable_pop.html", tmp_path / "seekable"),
                             ("direct_pop.html", tmp_path / "direct")):
            r = render(fixture, out, "--no-sheet")
            assert r.returncode == 0, r.stdout + r.stderr
        assert digests(tmp_path / "seekable") == digests(tmp_path / "direct")

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
        # Measured: removing the animation.ready awaits before pausing (warm-up and
        # per-frame) fails this at frame 0 on 5/5 cold runs; the shipped code passes.
        # The race is timing-dependent (a mutant without the awaits failed 24 of 25
        # cold runs on macOS), so two independent cold renders must both be pure.
        for run in ("a", "b"):
            r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "warmup.html"), "--seconds", "1",
                                "--fps", "12", "--width", "1080", "--height", "1080", "--out", str(tmp_path / run),
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
        # history.html replays exactly when re-rendered in rising order; only the
        # reverse-order --verify-all exposes it (an in-order check found 0 mismatches)
        sampled = json.loads(render("history.html", tmp_path / "s", "--verify", "--no-sheet").stdout)["verify"]
        full = json.loads(render("history.html", tmp_path / "a", "--verify-all", "--no-sheet").stdout)["verify"]
        assert sampled["scope"] == "sampled 3 of 12 frames" and full["scope"] == "all 12 frames"
        assert full["mismatches"] and len(full["mismatches"]) > len(sampled["mismatches"])

    def test_undriven_motion_is_reported_not_called_static(self, tmp_path):
        r = render("undriven.html", tmp_path, "--no-sheet")
        assert r.returncode == 3 and "own clock" in json.loads(r.stdout)["warning"]

    def test_a_preview_loop_running_under_t_exits_7(self, tmp_path):
        # the ?t= check exists but the loop starts unconditionally; no --verify needed
        r = render("loop_unguarded.html", tmp_path, "--no-sheet")
        assert r.returncode == 7, r.stdout + r.stderr
        assert json.loads(r.stdout)["drift"]["drifting"]

    def test_a_guarded_preview_loop_does_not_trip_the_probe(self, tmp_path):
        m = json.loads(render("good.html", tmp_path, "--no-sheet").stdout)
        assert m["loop_probe"] == {"raf_during_render": 0, "intervals": 0} and m["drift"]["drifting"] == []

    def test_an_idle_ticker_is_not_a_live_loop(self, tmp_path):
        # the paused-GSAP shape: rAF scheduled every frame, nothing drawn (round 4)
        r = render("ticker_idle.html", tmp_path, "--no-sheet")
        m = json.loads(r.stdout)
        assert r.returncode == 0, m
        assert m["loop_probe"]["raf_during_render"] >= 2 and m["drift"]["drifting"] == []

    def test_a_timeout_loop_exits_7(self, tmp_path):
        r = render("timeout_loop.html", tmp_path, "--no-sheet")
        assert r.returncode == 7 and json.loads(r.stdout)["loop_probe"]["raf_during_render"] == 0

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

    def test_a_hung_renderat_times_out_with_exit_5(self, tmp_path):
        env = {**os.environ, "MOTION_LAB_FRAME_TIMEOUT_MS": "1000"}
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "hang.html"), "--seconds", "1",
                            "--fps", "12", "--width", "160", "--height", "90", "--out", str(tmp_path), "--no-sheet"],
                           cwd=NODE_DIR, env=env, capture_output=True, text=True, timeout=90)
        m = json.loads(r.stdout)
        # an async hang still lets screenshots work, so only the timeout path stops
        # the render: without it every later frame pays the timeout too, and each
        # one is recorded
        timeouts = [e for e in m["page_errors"] if "timed out" in e]
        assert r.returncode == 5 and m["aborted_at_frame"] == 6 and len(timeouts) == 1, m["page_errors"]

    def test_local_files_outside_the_input_dir_are_blocked(self, tmp_path):
        page = tmp_path / "page"
        page.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("TOKEN=do-not-render")
        (page / "index.html").write_text(
            f'<!doctype html><body><iframe src="{secret.as_uri()}"></iframe>'
            '<style>@keyframes x{to{transform:translateX(9px)}} div{animation:x 1s infinite}</style><div>.</div></body>')
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(page / "index.html"), "--seconds", "0.25",
                            "--fps", "12", "--width", "160", "--height", "90", "--out", str(tmp_path / "out"), "--no-sheet"],
                           cwd=NODE_DIR, capture_output=True, text=True, timeout=120)
        assert secret.as_uri() in json.loads(r.stdout)["blocked_requests"]

    def test_cleanup_keeps_files_that_are_not_frames(self, tmp_path):
        frames = tmp_path / "frames"
        frames.mkdir()
        (frames / "storyboard-notes.txt").write_text("keep me")
        (frames / "0099.png").write_bytes(b"stale")
        assert render("good.html", tmp_path, "--no-sheet").returncode == 0
        assert (frames / "storyboard-notes.txt").exists() and not (frames / "0099.png").exists()

    def test_a_directory_is_a_usage_error(self, tmp_path):
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX)], cwd=NODE_DIR,
                           capture_output=True, text=True)
        assert r.returncode == 2 and "not a file" in r.stderr

    @pytest.mark.parametrize("fixture,offset", [("scrub_negdelay.html", "0"), ("scrub_waapi.html", "0.25")])
    def test_renderat_wins_over_the_renderers_own_seek(self, tmp_path, fixture, offset):
        # round 5: seeking every animation AFTER renderAt doubled a negative-delay
        # scrub and overwrote a WAAPI offset. Each scrub page must match a reference
        # that sets the same transform directly.
        ref = tmp_path / "ref.html"
        ref.write_text((FIX / "scrub_reference.html").read_text().replace("get('offset') || '0'", f"get('offset') || '{offset}'"))
        args = ["--seconds", "1", "--fps", "8", "--width", "160", "--height", "90", "--no-sheet"]
        for src, out in ((FIX / fixture, tmp_path / "a"), (ref, tmp_path / "b")):
            r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(src), "--out", str(out), *args],
                               cwd=NODE_DIR, capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stdout + r.stderr
        assert digests(tmp_path / "a") == digests(tmp_path / "b")
        assert len(set(digests(tmp_path / "a"))) > 2  # it actually moves

    def test_a_one_shot_intro_is_caught_by_the_early_drift_sample(self, tmp_path):
        r = render("intro_oneshot.html", tmp_path, "--no-sheet")
        m = json.loads(r.stdout)
        assert r.returncode == 7 and m["drift"]["early"] is True

    def test_a_synchronous_hang_aborts_fast_with_a_manifest(self, tmp_path):
        env = {**os.environ, "MOTION_LAB_FRAME_TIMEOUT_MS": "1500"}
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "hang_sync.html"), "--seconds", "1",
                            "--fps", "12", "--width", "160", "--height", "90", "--out", str(tmp_path), "--no-sheet"],
                           cwd=NODE_DIR, env=env, capture_output=True, text=True, timeout=60)
        m = json.loads((tmp_path / "manifest.json").read_text())
        assert r.returncode == 5 and m["aborted_at_frame"] == 6 and "timed out" in m["page_errors"][0]

    def test_symlinks_and_dotfiles_cannot_leak_into_frames(self, tmp_path):
        page = tmp_path / "page"
        page.mkdir()
        (tmp_path / "secret.txt").write_text("TOKEN=outside")
        (page / ".env").write_text("API_KEY=sibling")
        (page / "up").symlink_to(tmp_path)
        (page / "index.html").write_text(
            '<!doctype html><body><iframe src="up/secret.txt"></iframe><iframe src=".env"></iframe>'
            '<style>@keyframes x{to{transform:translateX(9px)}} div{animation:x 1s infinite}</style><div>.</div></body>')
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(page / "index.html"), "--seconds", "0.25",
                            "--fps", "12", "--width", "160", "--height", "90", "--out", str(tmp_path / "out"), "--no-sheet"],
                           cwd=NODE_DIR, capture_output=True, text=True, timeout=120)
        blocked = json.loads(r.stdout)["blocked_requests"]
        assert any(u.endswith("up/secret.txt") for u in blocked) and any(u.endswith("/.env") for u in blocked)

    @pytest.mark.parametrize("fixture,reference", [
        ("paused_css.html", "paused_css_reference.html"),        # no renderAt, CSS paused under ?t=
        ("mixed_frozen.html", "mixed_reference.html"),           # renderAt + a decorative spinner the page froze
        ("scrub_negdelay_inline.html", "scrub_reference.html"),  # renderAt pauses and scrubs inline
        ("shadow_frozen.html", "shadow_reference.html"),         # round 7: a spinner inside a shadow root
    ])
    def test_ownership_is_tested_not_guessed(self, tmp_path, fixture, reference):
        # round 6: "paused by the page = the page's" froze pages nothing drove, and
        # deciding before renderAt ran doubled an inline scrub. Each page must render
        # byte-identical to a reference that has no pause / sets the pose directly.
        args = ["--seconds", "1", "--fps", "8", "--width", "160", "--height", "90", "--no-sheet"]
        for src, out in ((FIX / fixture, tmp_path / "a"), (FIX / reference, tmp_path / "b")):
            r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(src), "--out", str(out), *args],
                               cwd=NODE_DIR, capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stdout + r.stderr
        assert digests(tmp_path / "a") == digests(tmp_path / "b")
        assert len(set(digests(tmp_path / "a"))) == 8

    def test_a_hang_at_t0_aborts_in_the_warm_up_with_a_manifest(self, tmp_path):
        env = {**os.environ, "MOTION_LAB_FRAME_TIMEOUT_MS": "1500"}
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "hang0.html"), "--seconds", "1",
                            "--fps", "12", "--width", "160", "--height", "90", "--out", str(tmp_path), "--no-sheet"],
                           cwd=NODE_DIR, env=env, capture_output=True, text=True, timeout=60)
        m = json.loads((tmp_path / "manifest.json").read_text())
        timeouts = [e for e in m["page_errors"] if "timed out" in e]
        assert r.returncode == 5 and m["aborted_at_frame"] == 0 and len(timeouts) == 1, m["page_errors"]

    def test_a_symlinked_input_renders(self, tmp_path):
        (tmp_path / "real").mkdir()
        (tmp_path / "link").mkdir()
        (tmp_path / "real" / "anim.html").write_text((FIX / "good.html").read_text())
        (tmp_path / "link" / "anim.html").symlink_to(tmp_path / "real" / "anim.html")
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(tmp_path / "link" / "anim.html"),
                            "--seconds", "0.5", "--fps", "8", "--width", "160", "--height", "90",
                            "--out", str(tmp_path / "out"), "--no-sheet"], cwd=NODE_DIR, capture_output=True, text=True,
                           timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_stale_outputs_from_an_earlier_run_are_removed(self, tmp_path):
        for name in ("contact.png", "anim.mp4", "manifest.json"):
            (tmp_path / name).write_text("stale")
        assert render("good.html", tmp_path, "--no-sheet").returncode == 0
        assert not (tmp_path / "contact.png").exists() and not (tmp_path / "anim.mp4").exists()
        assert json.loads((tmp_path / "manifest.json").read_text())["frames"] == 12

    def test_directory_urls_are_refused(self, tmp_path):
        page = tmp_path / "page"
        page.mkdir()
        (page / "assets").mkdir()
        (page / "assets" / "a.txt").write_text("asset")
        (page / "index.html").write_text(
            '<!doctype html><body><iframe src="./"></iframe><iframe src="assets/"></iframe>'
            '<style>@keyframes x{to{transform:translateX(9px)}} div{animation:x 1s infinite}</style><div>.</div></body>')
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(page / "index.html"), "--seconds", "0.25",
                            "--fps", "12", "--width", "160", "--height", "90", "--out", str(tmp_path / "out"), "--no-sheet"],
                           cwd=NODE_DIR, capture_output=True, text=True, timeout=120)
        blocked = json.loads(r.stdout)["blocked_requests"]
        assert any(u.rstrip("/").endswith("/page") for u in blocked)
        assert any(u.rstrip("/").endswith("/page/assets") for u in blocked)  # a subdirectory listing, too

    def test_a_scrub_that_starts_late_is_still_page_owned(self, tmp_path):
        # round 7: probing only t=0 and 0.37 x duration missed a scrub renderAt drives
        # from t=1.5 s; the probe now calls renderAt at every frame time
        args = ["--seconds", "3", "--fps", "4", "--width", "160", "--height", "90", "--no-sheet"]
        outs = {}
        for name in ("scrub_late.html", "scrub_late_reference.html"):
            out = tmp_path / name
            r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / name), "--out", str(out), *args],
                               cwd=NODE_DIR, capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stdout + r.stderr
            outs[name] = json.loads(r.stdout)
        assert outs["scrub_late.html"]["driven_by"]["page_owned"] == 1
        assert digests(tmp_path / "scrub_late.html") == digests(tmp_path / "scrub_late_reference.html")

    def test_a_hang_inside_verify_aborts_with_a_manifest(self, tmp_path):
        env = {**os.environ, "MOTION_LAB_FRAME_TIMEOUT_MS": "1500"}
        r = subprocess.run(["node", str(SKILL / "scripts" / "render.mjs"), str(FIX / "hang_verify.html"), "--seconds", "1",
                            "--fps", "8", "--width", "160", "--height", "90", "--out", str(tmp_path), "--no-sheet",
                            "--verify-all"], cwd=NODE_DIR, env=env, capture_output=True, text=True, timeout=60)
        m = json.loads((tmp_path / "manifest.json").read_text())
        assert r.returncode == 5, m  # a timeout is a page error, not impurity
        assert m["verify"]["aborted"] is True and m["verify"]["pure"] is None
        # the frame timeout stops verify at once; a hung page is never screenshotted
        assert not [e for e in m["page_errors"] if "verify screenshot" in e], m["page_errors"]

    def test_a_symlinked_frames_dir_is_refused_and_nothing_is_deleted(self, tmp_path):
        victim = tmp_path / "victim"
        victim.mkdir()
        (victim / "0000.png").write_bytes(b"not yours")
        out = tmp_path / "out"
        out.mkdir()
        (out / "frames").symlink_to(victim)
        r = render("good.html", out, "--no-sheet")
        assert r.returncode == 2 and "symlink" in r.stderr
        assert (victim / "0000.png").read_bytes() == b"not yours"


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

