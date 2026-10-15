"""Tests for the motion-lab deterministic core.

Unit tests cover motion_lint.py (the render-contract linter), motion_math.py
(beat grid, springs, loops, holds, GIF timing) and the shipped assets. The
end-to-end render tests live in test_render_integration.py.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
FIX = HERE / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))

import motion_lint as ml  # noqa: E402
import motion_math as mm  # noqa: E402


def rules(findings, severity=None):
    return {f.rule for f in findings if severity is None or f.severity == severity}


def html(script: str = "", style: str = "", head: str = "") -> str:
    return f"<!doctype html><html><head>{head}<style>{style}</style></head><body><script>{script}</script></body></html>"


GUARD = "const q = new URLSearchParams(location.search); if (q.has('t')) { renderAt(+q.get('t')); }"


# --------------------------------------------------------------------------- lint

class TestLintFixtures:
    def test_good_fixture_has_no_errors(self):
        found = ml.lint_path(FIX / "good.html")
        assert rules(found, "error") == set()
        # the preview loop is reported, as a warning, because the guard exists
        assert rules(found, "warn") == {"MC01"}

    def test_bad_fixture_trips_every_rule(self):
        found = ml.lint_path(FIX / "bad.html")
        assert rules(found, "error") == {"MC01", "MC02", "MC03", "MC04", "MC05", "MC06"}
        assert rules(found, "warn") == {"MC07", "MC08", "MC09"}

    def test_impure_fixture_is_statically_clean(self):
        # documents the linter's boundary: this impurity needs render.mjs --verify
        assert ml.lint_path(FIX / "impure.html") == []


class TestLintRules:
    def test_clock_without_guard_is_an_error(self):
        found = ml.lint_text(html("window.renderAt = t => {}; const s = performance.now();"))
        assert [f.severity for f in found if f.rule == "MC01"] == ["error"]

    def test_clock_with_renderat_and_guard_is_a_warning(self):
        found = ml.lint_text(html("window.renderAt = t => {}; " + GUARD + " else { requestAnimationFrame(f); }"))
        assert [f.severity for f in found if f.rule == "MC01"] == ["warn"]

    def test_guard_without_renderat_does_not_excuse_the_clock(self):
        found = ml.lint_text(html(GUARD.replace("renderAt", "draw") + " Date.now();"))
        assert "MC01" in rules(found, "error")

    def test_new_date_is_a_clock(self):
        assert "MC01" in rules(ml.lint_text(html("const d = new Date();")), "error")

    def test_comments_and_strings_do_not_trip_api_rules(self):
        src = "// Date.now() and setTimeout(f) are banned here\n/* Math.random() */\nconst s = 'Math.random() fetch(';"
        assert ml.lint_text(html(src)) == []

    def test_url_inside_a_string_is_still_checked(self):
        found = ml.lint_text(html("import('https://unpkg.com/gsap/dist/gsap.js');"))
        assert "MC06" in rules(found, "error")

    def test_timers_and_random(self):
        found = ml.lint_text(html("setTimeout(f, 10); crypto.getRandomValues(a);"))
        assert {"MC02", "MC03"} <= rules(found, "error")

    @pytest.mark.parametrize("url", [
        "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
        "https://unpkg.com/gsap@3.12.5/dist/gsap.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js",
        "https://fonts.googleapis.com/css2?family=Geist+Mono",
    ])
    def test_pinned_or_font_urls_pass(self, url):
        assert "MC06" not in rules(ml.lint_text(html(head=f'<script src="{url}"></script>')))

    @pytest.mark.parametrize("url", [
        "https://cdn.jsdelivr.net/npm/three@latest/build/three.module.js",
        "https://cdn.jsdelivr.net/npm/three@0.160/build/three.module.js",
        "https://unpkg.com/gsap@3/dist/gsap.min.js",
        "https://cdn.jsdelivr.net/npm/three/build/three.module.js",
    ])
    def test_unpinned_urls_fail(self, url):
        assert "MC06" in rules(ml.lint_text(html(head=f'<script src="{url}"></script>')), "error")

    def test_importmap_urls_are_checked(self):
        im = '<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js","x":"https://esm.sh/x"}}</script>'
        found = ml.lint_text(html(head=im))
        assert [f.message.split(": ")[-1] for f in found if f.rule == "MC06"] == ["https://esm.sh/x"]

    def test_network_apis(self):
        found = ml.lint_text(html("new WebSocket(u); new XMLHttpRequest(); new EventSource(u);"))
        assert len([f for f in found if f.rule == "MC06"]) == 3

    def test_canvas_without_renderat_is_mc04(self):
        assert "MC04" in rules(ml.lint_text(html("document.querySelector('c').getContext('2d');")), "error")

    def test_canvas_with_renderat_is_not_mc04(self):
        found = ml.lint_text(html("const g = c.getContext('2d'); window.renderAt = function (t) {};"))
        assert "MC04" not in rules(found)

    def test_waapi_only_needs_no_renderat(self):
        # el.animate() lands in document.getAnimations(), which the renderer seeks
        assert ml.lint_text(html("el.animate([{opacity: 0}, {opacity: 1}], 400);")) == []

    @pytest.mark.parametrize("value,flagged", [
        ("transform 0.3s ease", True), ("none", False), ("opacity 200ms", True),
    ])
    def test_css_transition(self, value, flagged):
        found = ml.lint_text(html(style=f".a {{ transition: {value}; }}"))
        assert ("MC05" in rules(found, "error")) is flagged

    def test_transition_longhand_is_flagged(self):
        assert "MC05" in rules(ml.lint_text(html(style=".a { transition-duration: 1s; }")))

    def test_class_named_transition_is_not_a_property(self):
        assert ml.lint_text(html(style=".transition:hover { color: red; }")) == []

    def test_layout_keyframes_warn_but_transform_does_not(self):
        bad = ml.lint_text(html(style="@keyframes k { from { left: 0; } to { left: 9px; } }"))
        good = ml.lint_text(html(style="@keyframes k { from { transform: none; } to { transform: scale(2); } }"))
        assert rules(bad, "warn") == {"MC09"} and good == []

    def test_webfont_without_fonts_ready_warns(self):
        link = '<link href="https://fonts.googleapis.com/css2?family=Geist" rel="stylesheet">'
        assert rules(ml.lint_text(html(head=link)), "warn") == {"MC08"}
        assert ml.lint_text(html("await document.fonts.ready;", head=link)) == []

    def test_local_reference_warns(self):
        assert rules(ml.lint_text(html(head='<script src="lib.js"></script>')), "warn") == {"MC07"}

    def test_shader_and_json_scripts_are_inert(self):
        doc = html(head='<script type="x-shader/x-fragment">float r = random(); // Date.now()</script>')
        assert ml.lint_text(doc) == []

    def test_module_mode_skips_html_only_rules(self):
        # a Remotion component: no renderAt expected, but Math.random still breaks purity
        src = "export const C = () => { const f = useCurrentFrame(); return Math.random() * f; };"
        found = ml.lint_text(src, is_html=False)
        assert rules(found) == {"MC03"}

    def test_line_numbers_point_at_the_offence(self):
        doc = "<html><body>\n<script>\nconst a = 1;\nsetTimeout(f, 1);\n</script></body></html>"
        assert [f.line for f in ml.lint_text(doc) if f.rule == "MC02"] == [4]

    def test_identical_findings_are_deduplicated(self):
        found = ml.lint_text(html(style="@keyframes g { from { width: 1px; } to { width: 2px; } }"))
        assert len([f for f in found if f.rule == "MC09"]) == 1


class TestLintCli:
    def run(self, *args):
        return subprocess.run([sys.executable, str(SKILL / "scripts" / "motion_lint.py"), *args],
                              capture_output=True, text=True)

    def test_exit_codes(self, tmp_path):
        assert self.run(str(FIX / "good.html")).returncode == 0
        assert self.run(str(FIX / "bad.html")).returncode == 1
        assert self.run(str(tmp_path / "missing.html")).returncode == 2

    def test_strict_fails_on_warnings(self):
        assert self.run("--strict", str(FIX / "good.html")).returncode == 1

    def test_json_output(self):
        out = json.loads(self.run("--json", str(FIX / "bad.html")).stdout)
        assert {x["rule"] for x in out[str(FIX / "bad.html")]} >= {"MC01", "MC06"}


# --------------------------------------------------------------------------- math

class TestBeats:
    def test_120_bpm_24_fps_is_12_frames(self):
        assert mm.frames_per_beat(24, 120) == 12
        assert mm.beat_frames(24, 120, 4) == [0, 12, 24, 36]

    def test_drift_free_grid_vs_naive(self):
        # 128 BPM at 30 fps = 14.0625 frames per beat: adding a rounded 14 drifts
        # 2 frames by beat 32 (the article's worked example).
        exact = mm.beat_frames(30, 128, 32)
        naive = mm.naive_beat_frames(30, 128, 32)
        assert exact[-1] == 436 and naive[-1] == 434
        assert all(abs(f - n * 14.0625) <= 0.5 for n, f in enumerate(exact))

    def test_offset(self):
        assert mm.beat_frames(60, 120, 3, offset=67) == [67, 97, 127]

    def test_half_rounds_up(self):
        assert mm.round_half_up(2.5) == 3 and mm.round_half_up(3.5) == 4

    def test_rejects_nonpositive(self):
        with pytest.raises(ValueError):
            mm.frames_per_beat(0, 120)


class TestSprings:
    def test_library_defaults(self):
        assert mm.damping_ratio(100, 10, 1) == pytest.approx(0.5)          # Remotion default
        assert mm.damping_ratio(170, 26, 1) == pytest.approx(0.997, abs=1e-3)  # react-spring default

    def test_inverse_round_trips(self):
        c = mm.damping_for_ratio(0.7, 100, 1)
        assert mm.damping_ratio(100, c, 1) == pytest.approx(0.7)

    @pytest.mark.parametrize("zeta,feel", [
        (1.0, "no bounce"), (0.9, "barely bounces"), (0.8, "premium"), (0.5, "playful"),
        (0.35, "bouncy"), (0.2, "cartoon"),
    ])
    def test_classification(self, zeta, feel):
        assert mm.classify_zeta(zeta) == feel


class TestLoopsAndHolds:
    def test_loop_range_excludes_frame_n(self):
        r = mm.loop_frames(6, 24)
        assert r["frames"] == 144 and r["render_range"] == [0, 143]

    def test_music_loop_closure(self):
        assert mm.loop_frames(6, 60, bpm=120)["music_loop_closes"] is True
        assert mm.loop_frames(6, 60, bpm=128)["music_loop_closes"] is False

    def test_fractional_frame_count_is_reported(self):
        assert mm.loop_frames(1.01, 24)["whole_frames"] is False

    def test_ms_to_frames(self):
        assert mm.ms_to_frames(400, 24) == 10 and mm.ms_to_frames(750, 24) == 18

    def test_text_hold_rounds_frames_up(self):
        assert mm.text_hold(2) == {"seconds": 1.1}
        assert mm.text_hold(2, 24)["frames"] == 27  # 26.4 frames -> never shorter


class TestGifTiming:
    @pytest.mark.parametrize("fps", [24, 30, 25, 60, 12, 23.976])
    def test_cumulative_time_stays_within_half_a_centisecond(self, fps):
        d = mm.gif_delays(fps, 200)
        total = 0
        for i, x in enumerate(d):
            total += x
            assert abs(total - 100 * (i + 1) / fps) <= 0.5 + 1e-9

    def test_24fps_six_second_loop_is_exact(self):
        r = mm.gif_report(24, 144)
        assert r["duration_s"] == 6.0
        assert r["naive_error_pct"] == -4.0  # every frame rounded to 40 ms: 4% fast
        assert set(r["delays_cs"]) == {4, 5}

    def test_x_frame_cap(self):
        assert mm.gif_report(24, 351)["over_x_frame_cap"] is True


def make_gif(delays, local_table_on=1):
    """A minimal valid 1x1 GIF89a with one frame per delay."""
    out = bytearray(b"GIF89a" + struct.pack("<HH", 1, 1) + bytes([0x80, 0, 0]) + b"\x00\x00\x00\xff\xff\xff")
    out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"  # application extension: must be skipped
    for i, d in enumerate(delays):
        out += b"\x21\xf9\x04\x00" + struct.pack("<H", d) + b"\x00\x00"
        packed = 0x80 if i == local_table_on else 0x00
        out += b"\x2c" + struct.pack("<HHHH", 0, 0, 1, 1) + bytes([packed])
        if packed:
            out += b"\x00\x00\x00\xff\xff\xff"
        out += b"\x02\x02\x4c\x01\x00"
    out += b"\x3b"
    return bytes(out)


class TestGifReader:
    def test_reads_every_delay(self):
        assert mm.read_gif_delays(make_gif([4, 5, 4, 7])) == [4, 5, 4, 7]

    def test_frame_without_gce_is_zero(self):
        data = bytearray(make_gif([]))[:-1] + b"\x2c" + struct.pack("<HHHH", 0, 0, 1, 1) + b"\x00\x02\x02\x4c\x01\x00\x3b"
        assert mm.read_gif_delays(bytes(data)) == [0]

    def test_rejects_non_gif_and_truncation(self):
        with pytest.raises(ValueError):
            mm.read_gif_delays(b"\x89PNG\r\n\x1a\n")
        with pytest.raises(ValueError):
            mm.read_gif_delays(make_gif([4, 4])[:-6])

    def test_gif_check_reports_error_against_target(self, tmp_path):
        p = tmp_path / "a.gif"
        p.write_bytes(make_gif([4] * 24))
        r = mm.gif_check(p, fps=24)
        assert r["frames"] == 24 and r["duration_s"] == 0.96 and r["error_pct"] == -4.0

    def test_cli_prints_json(self):
        out = subprocess.run([sys.executable, str(SKILL / "scripts" / "motion_math.py"), "beats", "--fps", "24",
                              "--bpm", "120", "--count", "3"], capture_output=True, text=True, check=True)
        assert json.loads(out.stdout)["beats"] == [0, 12, 24]


# --------------------------------------------------------------------------- shipped assets

needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def test_shipped_tokens_file_obeys_the_contract():
    assert [f for f in ml.lint_path(SKILL / "assets" / "motion.js") if f.severity == "error"] == []


@needs_node
def test_motion_js_spring_and_tokens_agree_with_the_python_math():
    probe = """
    const m = await import(process.argv[1]);
    const out = {
      z: m.dampingRatio(100, 10, 1),
      s0: m.spring(0), sNeg: m.spring(-1), sEnd: m.spring(10, 0.7, 2),
      peak: Math.max(...Array.from({length: 400}, (_, i) => m.spring(i / 200, 0.5, 2))),
      crit: Array.from({length: 50}, (_, i) => m.spring(i / 25, 1, 2)),
      f: m.frames(400, 24), ph: m.phase(-1, 96),
      r1: m.mulberry32(7)(), r2: m.mulberry32(7)(),
    };
    console.log(JSON.stringify(out));
    """
    r = subprocess.run(["node", "--input-type=module", "-e", probe, (SKILL / "assets" / "motion.js").as_uri()],
                       capture_output=True, text=True, check=True)
    o = json.loads(r.stdout)
    assert o["z"] == pytest.approx(mm.damping_ratio(100, 10, 1))
    assert o["s0"] == 0 and o["sNeg"] == 0 and o["sEnd"] == pytest.approx(1, abs=1e-6)
    assert o["peak"] > 1.1  # zeta 0.5 overshoots (about 16%)
    assert all(b >= a for a, b in zip(o["crit"], o["crit"][1:]))  # zeta 1 never overshoots
    assert o["f"] == mm.ms_to_frames(400, 24)
    assert o["ph"] == pytest.approx(95 / 96)
    assert o["r1"] == o["r2"]  # same seed, same sequence
