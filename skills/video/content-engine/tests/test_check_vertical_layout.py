"""Tests for scripts/check_vertical_layout.py — the 9:16 layout gate.

Four layers:
  * rule engine on hand-built detections (no tools needed),
  * the legibility metric on synthetic pixel buffers,
  * the CLI and the layout contract (JSON <-> doc drift),
  * real videos rendered with ffmpeg drawtext, run through every detector that is
    installed (macOS Vision, tesseract). These skip, loudly, when a tool is missing.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import check_vertical_layout as cvl

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "check_vertical_layout.py"
DOC = SKILL / "references" / "vertical-layout.md"
LAYOUT = cvl.load_layout()
CLS = LAYOUT["classification"]
CANVAS = LAYOUT["canvas"]
_, ORGANIC = cvl.get_profile(LAYOUT, "reels-organic")
_, META = cvl.get_profile(LAYOUT, "meta-ads-9x16")
W, H = 1080, 1920


def text(s, x0, y0, x1, y1, **kw):
    return cvl.Text(s, cvl.Box(x0, y0, x1, y1), **kw)


def face(x0, y0, x1, y1, eye_y):
    return cvl.Face(cvl.Box(x0, y0, x1, y1), eye_y)


def caption_word(word):
    """A caption word where the source reel puts one: centre y ~1376, centred."""
    return text(word, 440, 1345, 640, 1405)


def reel_like_frames(n=10, faces=True):
    """Detections shaped like the source reel: a static title hook, word-by-word
    captions, one talking head at eye line ~730px."""
    frames = []
    for i in range(n):
        texts = [caption_word(f"w{i}")]
        if i < 3:
            texts.append(text("Title hook", 312, 233, 765, 323))
        fc = [face(334, 616, 690, 972, 730 + (i % 3) * 8)] if faces else None
        frames.append(cvl.Frame(label=f"t={i / 2:.2f}s", t=i / 2, texts=texts, faces=fc))
    return frames


def run(frames, profile=ORGANIC, w=W, h=H, expect=frozenset()):
    return {r.rule: r for r in cvl.evaluate(w, h, frames, profile, CLS, CANVAS, expect)}


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------

def test_reel_like_layout_passes_every_rule():
    res = run(reel_like_frames())
    assert {k: v.status for k, v in res.items()} == {
        "VL1": "PASS", "VL2": "PASS", "VL3": "PASS", "VL4": "PASS", "VL5": "PASS",
        "VL6": "PASS", "VL7": "SKIP", "VL8": "PASS", "VL9": "UNCHECKED"}


def test_landscape_canvas_fails_vl1_and_voids_the_rest():
    res = run(reel_like_frames(), w=1920, h=1080)
    assert res["VL1"].status == "FAIL"
    assert all(res[r].status == "N/A" for r in res if r != "VL1")


def test_small_9x16_canvas_warns():
    assert run([], w=720, h=1280)["VL1"].status == "WARN"


def test_bottom_captions_fail_safe_zone_avoid_zone_and_caption_band():
    frames = [cvl.Frame(label="a", texts=[text("hello", 440, 1780, 640, 1840)], faces=[])]
    res = run(frames)
    assert res["VL2"].status == "FAIL"
    assert res["VL3"].status == "FAIL"
    assert "bottom" in res["VL3"].evidence[0]["why"]
    assert res["VL5"].status == "FAIL"


def test_text_on_the_action_rail_fails_vl3_even_inside_the_safe_zone():
    # x 880-935 is inside the safe zone (<=938) but on the rail (>=872) below 48%.
    frames = [cvl.Frame(label="a", texts=[text("like", 880, 1000, 935, 1060)], faces=[])]
    res = run(frames)
    assert res["VL2"].status == "PASS"
    assert res["VL3"].status == "FAIL"
    assert res["VL3"].evidence[0]["why"] == "right action rail"


def test_word_by_word_text_in_the_title_band_is_treated_as_captions():
    # The old campaign-plan template put captions "top-center, 12% from top".
    frames = [cvl.Frame(label=f"t{i}", texts=[text(f"word{i}", 440, 200, 640, 260)], faces=[])
              for i in range(6)]
    res = run(frames)
    assert res["VL5"].status == "FAIL"
    assert "treated as captions" in res["VL5"].detail
    assert res["VL2"].status == "FAIL"  # 200 < 277: no title-band exemption for captions


def test_static_title_in_the_band_is_a_title_and_passes():
    frames = [cvl.Frame(label=f"t{i}", texts=[text("How I edit", 330, 240, 750, 320)], faces=[])
              for i in range(6)]
    res = run(frames)
    assert res["VL4"].status == "PASS"
    assert res["VL2"].status == "PASS"  # 240 < 277 but inside the title band
    assert res["VL5"].status == "SKIP"


def test_title_above_the_band_fails_vl4_and_vl2():
    frames = [cvl.Frame(label="a", texts=[text("Too high", 330, 40, 750, 110)], faces=[])]
    res = run(frames)
    assert res["VL4"].status == "FAIL"
    assert res["VL2"].status == "FAIL"


def test_off_centre_caption_fails_vl5():
    frames = [cvl.Frame(label="a", texts=[text("left", 150, 1345, 350, 1405)], faces=[])]
    res = run(frames)
    assert res["VL5"].status == "FAIL"
    assert "median centre off" in res["VL5"].evidence[0]["why"]


def test_one_fragmentary_caption_read_does_not_fail_centring():
    # tesseract read "nd" of "background": one box off-centre, the rest centred.
    texts = [caption_word(f"w{i}") for i in range(6)] + [text("nd", 660, 1342, 743, 1398)]
    res = run([cvl.Frame(label=f"t{i}", texts=[t], faces=[]) for i, t in enumerate(texts)])
    assert res["VL5"].status == "PASS"
    assert "1 box(es) off-centre on their own" in res["VL5"].detail


def test_small_scene_text_is_ignored_but_counted():
    # The source reel's bookshelf spines: 17px tall at the left edge.
    frames = [cvl.Frame(label="a", texts=[text("spine", 0, 996, 70, 1013)], faces=[])]
    res = run(frames)
    assert res["VL2"].status == "SKIP"
    assert "1 small text box" in res["VL2"].detail


def test_eye_line_outside_the_band_fails_vl6():
    frames = [cvl.Frame(label=f"t{i}", faces=[face(334, 300, 690, 650, 420)]) for i in range(4)]
    res = run(frames)
    assert res["VL6"].status == "FAIL"
    assert res["VL8"].status == "PASS"


def test_punch_in_that_holds_the_eye_line_passes_vl7():
    wide = [cvl.Frame(label=f"w{i}", faces=[face(360, 620, 700, 960, 730)]) for i in range(4)]
    tight = [cvl.Frame(label=f"p{i}", faces=[face(330, 610, 750, 1030, 770)]) for i in range(4)]
    res = run(wide + tight)
    assert res["VL7"].status == "PASS"
    assert res["VL7"].evidence[0]["shift_px"] == 40


def test_punch_in_that_drops_the_eye_line_fails_vl7():
    # Scaling about the frame centre instead of the eye line moves the eyes a lot.
    wide = [cvl.Frame(label=f"w{i}", faces=[face(360, 620, 700, 960, 730)]) for i in range(4)]
    tight = [cvl.Frame(label=f"p{i}", faces=[face(300, 700, 780, 1180, 840)]) for i in range(4)]
    res = run(wide + tight)
    assert res["VL7"].status == "FAIL"


def test_face_on_the_rail_fails_vl3_and_vl8():
    frames = [cvl.Frame(label=f"t{i}", faces=[face(700, 900, 1000, 1200, 1000)]) for i in range(3)]
    res = run(frames)
    assert res["VL3"].status == "FAIL"
    assert res["VL8"].status == "FAIL"


def test_detector_without_faces_reports_unchecked_and_strict_fails():
    results = cvl.evaluate(W, H, reel_like_frames(faces=False), ORGANIC, CLS, CANVAS)
    by = {r.rule: r.status for r in results}
    assert by["VL6"] == by["VL7"] == by["VL8"] == "UNCHECKED"
    assert cvl.verdict(results, strict=False)[0] == "PASS"
    assert cvl.verdict(results, strict=True)[0] == "FAIL"


def test_expected_captions_that_ocr_cannot_find_fail_instead_of_skip():
    frames = [cvl.Frame(label="a", texts=[], faces=[])]
    assert run(frames)["VL5"].status == "SKIP"
    res = run(frames, expect=frozenset({"caption"}))
    assert res["VL5"].status == "FAIL"
    assert res["VL2"].status == "SKIP"  # VL5 owns it; no double count
    res_meta = run(frames, profile=META, expect=frozenset({"caption"}))
    assert res_meta["VL5"].status == "N/A"
    assert res_meta["VL2"].status == "FAIL"  # no caption band in this profile: VL2 carries it


def test_meta_ads_profile_rejects_the_organic_caption_position():
    frames = [cvl.Frame(label="a", texts=[caption_word("buy")], faces=[])]
    res = run(frames, profile=META)
    assert res["VL2"].status == "FAIL"  # y 1405 > 65% (1248)
    assert res["VL4"].status == "N/A"


def test_legibility_measured_warns_below_the_share():
    t = caption_word("busy")
    t.halo_share = 0.3
    res = run([cvl.Frame(label="a", texts=[t], faces=[])])
    assert res["VL9"].status == "WARN"
    t.halo_share = 0.9
    assert run([cvl.Frame(label="a", texts=[t], faces=[])])["VL9"].status == "PASS"


def test_legibility_declared_busy_without_stroke_fails():
    no = text("cap", 440, 1345, 640, 1405, role="caption", background="busy", stroke=False)
    yes = text("cap", 440, 1345, 640, 1405, role="caption", background="busy", stroke=True)
    assert run([cvl.Frame(label="a", texts=[no], faces=[])])["VL9"].status == "FAIL"
    assert run([cvl.Frame(label="a", texts=[yes], faces=[])])["VL9"].status == "PASS"


# ---------------------------------------------------------------------------
# Punch-in segmentation
# ---------------------------------------------------------------------------

def _ff(heights, eye=730):
    return [(cvl.Frame(label=f"t{i}"), face(0, 0, h, h, eye)) for i, h in enumerate(heights)]


def test_segments_ignore_in_shot_drift():
    # The source reel's wide shot: 325-371px faces, 14% sample-to-sample swing.
    wide = [354, 352, 358, 326, 346, 330, 371, 338, 345, 325, 352, 343, 329, 337]
    assert len(cvl.punch_in_segments(_ff(wide), 0.12)) == 1


def test_segments_split_on_a_held_punch_in_and_out():
    heights = [350, 345, 352, 435, 410, 438, 447, 362, 370, 364]
    segs = cvl.punch_in_segments(_ff(heights), 0.12)
    assert [len(s) for s in segs] == [3, 4, 3]


def test_segments_ignore_a_one_sample_glitch():
    heights = [350, 345, 352, 450, 348, 351, 349]
    assert len(cvl.punch_in_segments(_ff(heights), 0.12)) == 1


# ---------------------------------------------------------------------------
# Legibility metric on synthetic pixels
# ---------------------------------------------------------------------------

def _canvas(w, h, bg):
    return [[bg(x, y) for x in range(w)] for y in range(h)]


def _draw_glyph(img, x0, y0, x1, y1, stroke=0):
    for y in range(y0 - stroke, y1 + stroke):
        for x in range(x0 - stroke, x1 + stroke):
            img[y][x] = 255 if (x0 <= x < x1 and y0 <= y < y1) else 0


def _bytes(img):
    return bytes(v for row in img for v in row)


def test_halo_share_is_high_with_a_stroke_and_low_on_a_light_busy_background():
    def noise(x, y):
        return 150 + ((x * 7919 + y * 104729) % 70)  # light, busy, never >= 225

    plain = _canvas(200, 120, noise)
    for gx in range(40, 160, 30):
        _draw_glyph(plain, gx, 40, gx + 12, 80)
    stroked = _canvas(200, 120, noise)
    for gx in range(40, 160, 30):
        _draw_glyph(stroked, gx, 40, gx + 12, 80, stroke=6)
    box = cvl.Box(30, 30, 170, 90)
    low = cvl.halo_contrast_share(_bytes(plain), 200, 120, box, 3.0)
    high = cvl.halo_contrast_share(_bytes(stroked), 200, 120, box, 3.0)
    assert low is not None and high is not None
    assert low < 0.2 < 0.9 < high


def test_halo_share_is_none_without_light_text():
    img = _canvas(100, 60, lambda x, y: 40)
    assert cvl.halo_contrast_share(_bytes(img), 100, 60, cvl.Box(10, 10, 90, 50), 3.0) is None


# ---------------------------------------------------------------------------
# CLI + contract
# ---------------------------------------------------------------------------

def _cli(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd)


def _spec(tmp_path, elements, shots=None):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"canvas": [1080, 1920], "elements": elements, "shots": shots or []}))
    return p


def test_spec_mode_exit_codes(tmp_path):
    good = _spec(tmp_path, [
        {"role": "title", "label": "hook", "box": [312, 233, 765, 323]},
        {"role": "caption", "label": "word", "box": [440, 1345, 640, 1405], "stroke": True, "background": "busy"},
        {"role": "watermark", "label": "brand", "box": [143, 1580, 330, 1640]},
    ], shots=[{"eye_y": 730, "face_box": [334, 616, 690, 972]}, {"eye_y": 772, "face_box": [320, 600, 760, 1040]}])
    p = _cli("spec", str(good), "--json")
    assert p.returncode == 0, p.stdout + p.stderr
    rep = json.loads(p.stdout)
    assert rep["verdict"] == "PASS"
    assert {r["rule"]: r["status"] for r in rep["results"]}["VL7"] == "PASS"

    # The pre-change BrandWatermark: bottom-right, padding 32.
    bad = _spec(tmp_path, [{"role": "watermark", "label": "brand", "box": [870, 1830, 1048, 1888]}])
    p = _cli("spec", str(bad))
    assert p.returncode == 1
    assert "VL3" in p.stdout and "FAIL" in p.stdout


def test_cli_usage_errors_exit_2(tmp_path):
    assert _cli("spec", str(tmp_path / "missing.json")).returncode == 2
    assert _cli("--profile", "nope", "zones").returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"canvas": [1080, 1920], "elements": [{"box": [1, 2, 3]}]}))
    assert _cli("spec", str(bad)).returncode == 2


def test_contract_fractions_are_sane():
    for name, prof in LAYOUT["profiles"].items():
        zones = [prof["safe_zone"], *(prof.get("avoid") or [])]
        for z in zones:
            assert 0 <= z["x0"] < z["x1"] <= 1 and 0 <= z["y0"] < z["y1"] <= 1, name
        for key in ("title_band", "caption_band"):
            if prof.get(key):
                assert 0 <= prof[key]["y0"] < prof[key]["y1"] <= 1, (name, key)
        eye = prof.get("eye_line")
        if eye:
            assert 0 < eye["y0"] < eye["y1"] < 1


def test_contract_reproduces_the_measured_reel_pixels():
    """The organic profile is a measurement of the source reel's own overlays; these
    are the pixels it drew. Changing a fraction must be a deliberate re-measurement."""
    safe = cvl.zone(ORGANIC["safe_zone"], W, H)
    assert safe.as_list() == [143, 277, 938, 1643]
    rail, bottom = (cvl.zone(a, W, H) for a in ORGANIC["avoid"])
    assert (round(rail.x0), round(rail.y0), round(bottom.y0)) == (872, 922, 1686)


def test_doc_embeds_the_generated_zone_tables():
    doc = DOC.read_text()
    for name, prof in LAYOUT["profiles"].items():
        table = cvl.zones_table(prof, W, H)
        assert table in doc, f"references/vertical-layout.md is stale for {name}; paste `zones --profile {name}`"


# ---------------------------------------------------------------------------
# Real videos (ffmpeg drawtext -> detector)
# ---------------------------------------------------------------------------

FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
FONT = next((f for f in FONTS if Path(f).exists()), None)
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
DETECTORS = [d for d, ok in (("vision", cvl.vision_binary() is not None),
                             ("tesseract", bool(shutil.which("tesseract")))) if ok]

media = pytest.mark.skipif(not (HAVE_FFMPEG and FONT and DETECTORS),
                           reason="needs ffmpeg, a bold TTF font and a detector (tesseract or macOS Vision)")


def _dt(txt, y_centre, size=64, x="(w-tw)/2", enable=None, stroke=0):
    esc = FONT.replace(":", r"\:")
    f = (f"drawtext=fontfile='{esc}':text='{txt}':fontsize={size}:fontcolor=white"
         f":x={x}:y={y_centre}-th/2")
    if stroke:
        f += f":borderw={stroke}:bordercolor=black"
    if enable:
        f += f":enable='{enable}'"
    return f


def _render(path, filters, size="1080x1920", bg="color=c=0x303030", dur=2):
    src = f"{bg}:s={size}:d={dur}:r=30" if bg.startswith("color") else bg
    vf = ",".join(["format=yuv420p", *filters]) if filters else "format=yuv420p"
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-vf", vf,
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return path


def _words(y_centre, words=("alpha", "bravo", "charlie", "delta")):
    return [_dt(w, y_centre, enable=f"between(t,{i * 0.5},{i * 0.5 + 0.499})") for i, w in enumerate(words)]


@pytest.fixture(scope="module")
def videos(tmp_path_factory):
    if not (HAVE_FFMPEG and FONT and DETECTORS):
        pytest.skip("media tools missing")
    d = tmp_path_factory.mktemp("vl")
    return {
        "good": _render(d / "good.mp4", [_dt("Watch this", 278, size=72), *_words(1376)]),
        "bottom": _render(d / "bottom.mp4", _words(1800)),
        "top_captions": _render(d / "top.mp4", _words(230)),
        "rail": _render(d / "rail.mp4", [_dt("Tap", 1100, size=72, x="900")]),
        "landscape": _render(d / "landscape.mp4", _words(900), size="1920x1080"),
    }


def _check(video, detector, *extra):
    p = _cli("video", str(video), "--detector", detector, "--json", "--no-report", "--no-guide", *extra)
    assert p.returncode in (0, 1), p.stderr
    rep = json.loads(p.stdout)
    return p.returncode, {r["rule"]: r for r in rep["results"]}, rep


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_good_layout_passes(videos, detector):
    code, res, rep = _check(videos["good"], detector, "--expect-captions", "--expect-title")
    assert rep["detector"] == detector
    assert code == 0, json.dumps(res, indent=1)
    for rule in ("VL1", "VL2", "VL3", "VL4", "VL5"):
        assert res[rule]["status"] == "PASS", (rule, res[rule])


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_bottom_captions_fail(videos, detector):
    code, res, _ = _check(videos["bottom"], detector)
    assert code == 1
    assert res["VL3"]["status"] == "FAIL"
    assert res["VL5"]["status"] == "FAIL"


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_captions_in_the_title_band_fail(videos, detector):
    code, res, _ = _check(videos["top_captions"], detector)
    assert code == 1
    assert res["VL5"]["status"] == "FAIL"


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_text_on_the_rail_fails(videos, detector):
    code, res, _ = _check(videos["rail"], detector)
    assert code == 1
    assert res["VL3"]["status"] == "FAIL"


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_landscape_fails_vl1(videos, detector):
    code, res, _ = _check(videos["landscape"], detector)
    assert code == 1
    assert res["VL1"]["status"] == "FAIL"


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_writes_report_and_guide(videos, detector, tmp_path):
    report, guide = tmp_path / "r.json", tmp_path / "g.png"
    p = _cli("video", str(videos["good"]), "--detector", detector, "--report", str(report), "--guide", str(guide))
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(report.read_text())["verdict"] == "PASS"
    assert guide.stat().st_size > 10_000
    assert "VERDICT: PASS" in p.stdout


NOISE = "nullsrc=s=216x384:d=1,geq=90+random(1)*110:128:128,scale=1080:1920:flags=neighbor"


@media
@pytest.mark.skipif("vision" not in DETECTORS,
                    reason="macOS Vision only: tesseract reads noise texture as words and misses stroked text on it")
def test_legibility_warns_without_a_stroke_and_passes_with_one(tmp_path):
    plain = _render(tmp_path / "plain.mp4", [_dt("noisy", 1376, size=96)], bg=NOISE)
    stroked = _render(tmp_path / "stroked.mp4", [_dt("noisy", 1376, size=96, stroke=6)], bg=NOISE)
    assert _check(plain, "vision")[1]["VL9"]["status"] == "WARN"
    res = _check(stroked, "vision", "--expect-captions")[1]
    assert res["VL5"]["status"] == "PASS"
    assert res["VL9"]["status"] == "PASS"


@media
def test_compose_video_gate_passes_good_and_fails_bad(videos):
    """compose-video.py's run_layout_gate is what blocks a 9:16 campaign asset."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("compose_video", SKILL / "scripts" / "compose-video.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.run_layout_gate(videos["good"], expect_text=True) is True
    assert mod.run_layout_gate(videos["bottom"], expect_text=True) is False
