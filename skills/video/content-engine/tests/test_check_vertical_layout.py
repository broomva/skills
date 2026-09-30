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
        texts = [caption_word(f"word{i}")]
        if i < 5:
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
    assert res["VL5"].status == "SKIP"        # undeclared: not judged as a caption...
    assert run(frames, expect=CAPS)["VL5"].status == "FAIL"   # ...declared: missing from the band


def test_text_on_the_action_rail_fails_vl3_even_inside_the_safe_zone():
    # x 880-935 is inside the safe zone (<=938) but on the rail (>=872) below 48%.
    frames = [cvl.Frame(label="a", texts=[text("like", 880, 1000, 935, 1060)], faces=[])]
    res = run(frames)
    assert res["VL2"].status == "PASS"
    assert res["VL3"].status == "FAIL"
    assert res["VL3"].evidence[0]["why"] == "right action rail"


def timed(texts_per_frame, step=0.5):
    return [cvl.Frame(label=f"t={i * step:.2f}s", t=i * step, texts=ts, faces=[])
            for i, ts in enumerate(texts_per_frame)]


WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]


CAPS = frozenset({"caption"})


def test_declared_captions_parked_at_the_top_fail_vl5():
    # The old campaign-plan template put captions "top-center, 12% from top".
    frames = timed([[text(w, 440, 200, 640, 260)] for w in WORDS])
    res = run(frames, expect=CAPS)
    assert res["VL5"].status == "FAIL"
    assert "outside its band" in res["VL5"].detail


def test_declared_captions_across_the_eyes_fail_vl5_in_video_and_image_mode():
    # CapCut's default: captions at mid-frame, over the face.
    for step in (0.5, None):  # video samples, and stills with no time axis
        frames = [cvl.Frame(label=f"f{i}", t=None if step is None else i * step,
                            texts=[text(w, 440, 930, 640, 990)], faces=[]) for i, w in enumerate(WORDS)]
        res = run(frames, expect=CAPS)
        assert res["VL5"].status == "FAIL", step
        assert "OCR found none" not in res["VL5"].detail


def test_undeclared_text_outside_the_bands_is_a_plain_overlay():
    # Without --expect-captions the gate does not guess: mid-frame words, a CTA below
    # the caption band, rotating chapter titles in the title band all stay legal.
    res = run(timed([[text(w, 440, 930, 640, 990)] for w in WORDS]))
    assert (res["VL2"].status, res["VL5"].status) == ("PASS", "SKIP")
    res = run(timed([[text("Link in bio", 330, 1510, 750, 1550)]] * 4))
    assert (res["VL2"].status, res["VL5"].status) == ("PASS", "SKIP")
    chapters = timed([[text(c, 330, 240, 750, 320)] for c in ("Tip 1", "Tip 1", "Tip 2", "Tip 2", "Tip 3", "Tip 3")])
    res = run(chapters, expect=frozenset({"title"}))
    assert (res["VL4"].status, res["VL5"].status) == ("PASS", "SKIP")


def test_a_larger_static_label_does_not_hide_declared_captions():
    frames = timed([[text(w, 440, 1345, 640, 1405), text("JUN YU founder", 200, 1000, 880, 1100)] for w in WORDS])
    res = run(frames, expect=CAPS)
    assert res["VL5"].status == "PASS"


def test_static_mid_text_is_a_plain_overlay_and_an_expected_title_names_it():
    frames = timed([[text("Why agents fail", 300, 540, 780, 620)]] * 6)
    res = run(frames)
    assert (res["VL2"].status, res["VL4"].status, res["VL5"].status) == ("PASS", "SKIP", "SKIP")
    res = run(timed([[text("Why agents fail", 300, 540, 780, 620)]] * 6), expect=frozenset({"title"}))
    assert res["VL4"].status == "FAIL"
    assert "6 other overlay box(es)" in res["VL4"].detail and "outside its band" in res["VL4"].detail


def test_static_title_in_the_band_is_a_title_and_passes():
    frames = timed([[text("How I edit", 330, 240, 750, 320)]] * 6)
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
    # Inside the band (x 220-860) but centred at x 322, not 540.
    frames = [cvl.Frame(label="a", texts=[text("left", 222, 1345, 422, 1405)], faces=[])]
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
    assert res["VL3"].status == "PASS"


def test_small_text_on_the_rail_warns_instead_of_vanishing():
    # A 24px "@brand" on the like/comment rail: scene-sized, but in the avoid zone.
    frames = [cvl.Frame(label="a", texts=[text("@brand", 880, 1500, 1060, 1524)], faces=[])]
    res = run(frames)
    assert res["VL3"].status == "WARN"
    assert "small text" in res["VL3"].evidence[0]["why"]


def test_caption_band_stops_at_the_action_rail():
    # Inside the safe zone and the old 143-938 band, but its right end is on the rail.
    res = run([cvl.Frame(label="a", texts=[text("a long caption line", 150, 1300, 930, 1360)], faces=[])])
    assert res["VL3"].status == "FAIL"
    assert res["VL5"].status == "FAIL"


def test_eye_line_outside_the_band_fails_vl6():
    frames = [cvl.Frame(label=f"t{i}", faces=[face(334, 300, 690, 650, 420)]) for i in range(4)]
    res = run(frames)
    assert res["VL6"].status == "FAIL"
    assert res["VL8"].status == "PASS"


def test_eye_line_out_of_band_in_a_third_of_samples_fails_even_with_a_good_median():
    eyes = [700, 700, 700, 700, 900, 900, 900]  # median 700 is inside; 3/7 are not
    frames = [cvl.Frame(label=f"t{i}", faces=[face(334, 600, 690, 956, y)]) for i, y in enumerate(eyes)]
    assert run(frames)["VL6"].status == "FAIL"


def test_face_without_eye_landmarks_is_unchecked_for_vl6():
    frames = [cvl.Frame(label=f"t{i}", faces=[face(334, 600, 690, 956, None)]) for i in range(3)]
    assert run(frames)["VL6"].status == "UNCHECKED"


def test_punch_in_that_holds_the_eye_line_passes_vl7():
    wide = [cvl.Frame(label=f"w{i}", faces=[face(360, 620, 700, 960, 730)]) for i in range(4)]
    tight = [cvl.Frame(label=f"p{i}", faces=[face(330, 610, 750, 1030, 770)]) for i in range(4)]
    res = run(wide + tight)
    assert res["VL7"].status == "PASS"
    assert res["VL7"].evidence[0]["shift_px"] == 40


def test_punch_in_that_drops_the_eye_line_warns_vl7():
    # Scaling about the frame centre instead of the eye line moves the eyes a lot.
    # WARN, not FAIL: the same geometry is a cut between two centred speakers.
    wide = [cvl.Frame(label=f"w{i}", faces=[face(360, 620, 700, 960, 730)]) for i in range(4)]
    tight = [cvl.Frame(label=f"p{i}", faces=[face(300, 700, 780, 1180, 840)]) for i in range(4)]
    res = run(wide + tight)
    assert res["VL7"].status == "WARN"
    assert cvl.verdict(list(run(wide + tight).values()), strict=False)[0] == "PASS"


def test_a_cut_between_two_centred_speakers_only_warns_vl7():
    a = [cvl.Frame(label=f"a{i}", faces=[face(360, 560, 720, 880, 680)]) for i in range(4)]
    b = [cvl.Frame(label=f"b{i}", faces=[face(340, 600, 740, 1000, 810)]) for i in range(4)]
    res = run(a + b)
    assert res["VL6"].status == "PASS"
    assert res["VL7"].status == "WARN"


def test_a_face_drifting_onto_the_rail_for_part_of_a_shot_fails_vl3_and_vl8():
    # Same scale throughout (one shot); the median face is fine, 4 of 10 samples are not.
    frames = [cvl.Frame(label=f"t{i}", faces=[face(334, 616, 690, 972, 730)]) for i in range(6)]
    frames += [cvl.Frame(label=f"d{i}", faces=[face(620, 616, 976, 972, 730)]) for i in range(4)]
    res = run(frames)
    assert res["VL3"].status == "FAIL" and "of samples" in res["VL3"].evidence[0]["why"]
    assert res["VL8"].status == "FAIL"


def test_one_leaning_frame_does_not_fail_vl3_for_the_shot():
    frames = [cvl.Frame(label=f"t{i}", faces=[face(334, 616, 690, 972, 730)]) for i in range(5)]
    frames.append(cvl.Frame(label="lean", faces=[face(560, 900, 900, 1240, 1000)]))
    frames += [cvl.Frame(label=f"u{i}", faces=[face(334, 616, 690, 972, 730)]) for i in range(5)]
    res = run(frames)
    assert res["VL3"].status == "PASS"
    assert res["VL8"].status == "PASS"


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


def test_segments_ignore_a_glitch_on_the_first_or_last_sample():
    # sample_frames appends a "last" frame, so a glitch there happens on any video.
    assert len(cvl.punch_in_segments(_ff([350, 345, 352, 348, 351, 450]), 0.12)) == 1
    assert len(cvl.punch_in_segments(_ff([450, 350, 345, 352, 348, 351]), 0.12)) == 1


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


def test_halo_share_skips_the_anti_aliased_first_ring():
    # Stroked text as rendered: 255 fill, a 1px anti-aliased 170 edge, then a 6px
    # black stroke. Only the stroke should be judged.
    def light(x, y):
        return 200

    img = _canvas(200, 120, light)
    for gx in range(40, 160, 30):
        _draw_glyph(img, gx - 1, 39, gx + 13, 81, stroke=6)  # stroke band, glyph area
        for y in range(39, 81):
            for x in range(gx - 1, gx + 13):
                img[y][x] = 170  # anti-aliased edge ring ...
        for y in range(40, 80):
            for x in range(gx, gx + 12):
                img[y][x] = 255  # ... around the fill
    share = cvl.halo_contrast_share(_bytes(img), 200, 120, cvl.Box(30, 30, 170, 90), 3.0)
    assert share is not None and share > 0.9


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


@pytest.mark.parametrize("spec", [
    {"canvas": [1080, 1920], "elements": []},
    {"canvas": [1080, 1920], "element": [{"role": "caption", "box": [440, 1345, 640, 1405]}]},
    # Typos next to valid content: only the unknown-key check can reject these.
    {"canvas": [1080, 1920], "elements": [{"role": "caption", "box": [440, 1345, 640, 1405]}],
     "shot": [{"eye_y": 300, "face_box": [300, 200, 700, 600]}]},
    {"canvas": [1080, 1920], "elements": [{"roll": "caption", "box": [440, 1345, 640, 1405]}]},
    {"canvas": [1080, 0], "elements": [{"box": [1, 2, 3, 4]}]},
    {"canvas": ["1080", "1920"], "elements": [{"box": [1, 2, 3, 4]}]},
    {"canvas": {"w": 1080, "h": 1920}, "elements": [{"box": [1, 2, 3, 4]}]},
    {"canvas": [1080, 1920], "elements": [{"box": None}]},
    {"canvas": [1080, 1920], "elements": ["caption"]},
    {"canvas": [1080, 1920], "elements": {"box": [1, 2, 3, 4]}},
    {"canvas": [1080, 1920], "elements": [{"box": [640, 1345, 440, 1405]}]},
    {"canvas": [1080, 1920], "elements": [{"box": [1, 2, 3, 4], "background": "noisy"}]},
    {"canvas": [1080, 1920], "shots": [{"eye_y": 300}]},
    {"canvas": [1080, 1920], "shots": [{"face_box": [1, 2, 3]}]},
    {"canvas": [1080, 1920], "shots": [5]},
    {"canvas": [1080, 0.5], "elements": [{"box": [1, 2, 3, 4]}]},
    {"canvas": [1080, 1920], "elements": [{"role": "captions", "box": [440, 930, 640, 990]}]},
])
def test_malformed_spec_exits_2_never_a_verdict(tmp_path, spec):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec))
    r = _cli("spec", str(p))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "Traceback" not in r.stderr


def test_spec_roles_and_backgrounds_are_case_insensitive(tmp_path):
    p = _spec(tmp_path, [{"role": "Caption", "box": [440, 1345, 640, 1405], "background": "Busy", "stroke": False}])
    rep = json.loads(_cli("spec", str(p), "--json").stdout)
    by = {r["rule"]: r["status"] for r in rep["results"]}
    assert by["VL5"] == "PASS"   # a caption, not "other"
    assert by["VL9"] == "FAIL"   # busy, unstroked


def _break_contract(path):
    """Apply `path` = (keys..., new value or DELETE) to a copy of the contract."""
    c = json.loads((SKILL / "layout" / "vertical-9x16.json").read_text())
    *keys, value = path
    node = c
    for k in keys[:-1]:
        node = node[k]
    if value == "DELETE":
        del node[keys[-1]]
    else:
        node[keys[-1]] = value
    return c


@pytest.mark.parametrize("path", [
    ("profiles", "reels-organic", "safe_zone", "DELETE"),
    ("profiles", "reels-organic", "safe_zone", "x0", 0.9),                  # x0 > x1
    ("profiles", "reels-organic", "caption_band", "centre_x_tolerance", "DELETE"),
    ("profiles", "reels-organic", "avoid", 0, "name", "DELETE"),
    ("profiles", "reels-organic", "eye_line", [0.33, 0.45]),
    ("profiles", "reels-organic", "caption_band", "y1", 1.4),
    ("classification", "max_share_outside", 2),
    ("profiles", "reels-organic", "legibility", "strong"),
    ("profiles", "reels-organic", "eye_line", "y0", 0.5),                  # y0 > y1
    ("profiles", "reels-organic", "caption_band", "centre_x_tolerance", -0.05),
    ("default_profile", "nope"),
])
def test_malformed_layout_contract_exits_2(tmp_path, path):
    p = tmp_path / "layout.json"
    p.write_text(json.dumps(_break_contract(path)))
    r = _cli("--layout", str(p), "zones")
    assert r.returncode == 2, (path, r.stdout, r.stderr)
    assert "Traceback" not in r.stderr


def test_expected_title_missing_fails_vl4_and_meta_needs_any_text():
    frames = [cvl.Frame(label="a", texts=[caption_word("hello")], faces=[])]
    res = run(frames, expect=frozenset({"title"}))
    assert res["VL4"].status == "FAIL"
    assert "OCR found none" in res["VL4"].detail   # the caption in its band is not blamed
    # meta-ads has no bands to look in: any overlay text satisfies an expectation...
    res = run([cvl.Frame(label="a", texts=[text("buy now", 300, 1060, 780, 1120)], faces=[])],
              profile=META, expect=frozenset({"title", "caption"}))
    assert res["VL2"].status == "PASS"
    # ...and no text at all fails it.
    res = run([cvl.Frame(label="a", texts=[], faces=[])], profile=META, expect=frozenset({"caption"}))
    assert res["VL2"].status == "FAIL"


def test_spec_without_shots_skips_the_face_rules(tmp_path):
    rep = json.loads(_cli("spec", str(_spec(tmp_path, [{"role": "title", "box": [312, 233, 765, 323]}])),
                          "--json").stdout)
    by = {r["rule"]: r["status"] for r in rep["results"]}
    assert by["VL6"] == by["VL8"] == "SKIP"


def test_vision_unavailable_says_why(monkeypatch):
    monkeypatch.setattr(cvl.sys, "platform", "darwin")
    monkeypatch.setattr(cvl.shutil, "which", lambda name: None)
    binary, why = cvl.vision_binary()
    assert binary is None and "swiftc" in why


def test_tesseract_tsv_drops_punctuation_and_unsure_single_glyphs():
    head = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [
        "5\t1\t1\t1\t1\t1\t400\t1340\t40\t60\t95\t=",       # punctuation: never text
        "5\t1\t2\t1\t1\t1\t100\t500\t30\t60\t80\t7",        # single glyph, unsure
        "5\t1\t3\t1\t1\t1\t600\t500\t30\t60\t90\t8",        # single glyph, sure
        "5\t1\t4\t1\t1\t1\t300\t900\t60\t40\t61\the",       # short word, above min_conf
        "5\t1\t5\t1\t1\t1\t300\t1200\t60\t40\t40\tnope",    # below min_conf
    ]
    got = sorted(t.text for t in cvl.parse_tesseract_tsv("\n".join([head, *rows])))
    assert got == ["8", "he"]


def test_merge_words_joins_a_line_left_to_right():
    words = [("was", cvl.Box(300, 1360, 400, 1400)), ("Tide", cvl.Box(420, 1340, 540, 1400)),
             ("now", cvl.Box(560, 1360, 660, 1400))]
    lines = cvl._merge_words(words)
    assert [t.text for t in lines] == ["was Tide now"]


def test_cli_usage_errors_exit_2(tmp_path):
    assert _cli("spec", str(tmp_path / "missing.json")).returncode == 2
    assert _cli("--profile", "nope", "zones").returncode == 2
    assert _cli("zones", "--canvas", "0x1920").returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"canvas": [1080, 1920], "elements": [{"box": [1, 2, 3]}]}))
    assert _cli("spec", str(bad)).returncode == 2
    # An unwritable report is a tool error, not a FAIL verdict.
    ok = _spec(tmp_path, [{"role": "title", "box": [312, 233, 765, 323]}])
    r = _cli("spec", str(ok), "--report", str(tmp_path / "no-such-dir" / "r.json"))
    assert r.returncode == 2 and "Traceback" not in r.stderr, r.stderr


def test_report_fingerprints_the_input_and_the_contract(tmp_path):
    import hashlib
    ok = _spec(tmp_path, [{"role": "title", "box": [312, 233, 765, 323]}])
    rep = json.loads(_cli("spec", str(ok), "--json").stdout)
    assert rep["input_sha256"] == {str(ok): hashlib.sha256(ok.read_bytes()).hexdigest()}
    contract = SKILL / "layout" / "vertical-9x16.json"
    assert rep["contract_sha256"] == hashlib.sha256(contract.read_bytes()).hexdigest()
    # --layout is what gets fingerprinted, not the default contract.
    other = tmp_path / "layout.json"
    other.write_text(contract.read_text() + "\n")
    rep = json.loads(_cli("--layout", str(other), "spec", str(ok), "--json").stdout)
    assert rep["contract_sha256"] == hashlib.sha256(other.read_bytes()).hexdigest()


def test_waiver_turns_a_fail_into_waived_and_is_recorded(tmp_path):
    # The pre-contract watermark on the rail FAILs VL3; a waiver records why it is
    # acceptable and lets the run pass, with the reason kept in the report.
    bad = _spec(tmp_path, [{"role": "watermark", "label": "brand", "box": [870, 1830, 1048, 1888]}])
    assert _cli("spec", str(bad)).returncode == 1
    # It FAILs VL2 (outside the safe zone) and VL3 (on the rail); each waiver names one rule.
    assert _cli("spec", str(bad), "--waive", "VL3=client-approved end card").returncode == 1
    r = _cli("spec", str(bad), "--json", "--waive", "VL3=client-approved end card",
             "--waive", "VL2=client-approved end card", "--waive", "VL6=unused")
    assert r.returncode == 0, r.stdout
    rep = json.loads(r.stdout)
    assert {x["rule"]: x["status"] for x in rep["results"]}["VL3"] == "WAIVED"
    assert {"rule": "VL3", "reason": "client-approved end card"} in rep["waivers"]
    assert rep["waivers_unused"] == ["VL6"]
    table = _cli("spec", str(bad), "--waive", "VL3=ok", "--waive", "VL2=ok").stdout
    assert table.rstrip().splitlines()[-1].startswith("VERDICT: PASS") and "2 WAIVED" in table
    for bad_waiver in ("VL3", "VL99=x", "=reason"):
        assert _cli("spec", str(bad), "--waive", bad_waiver).returncode == 2, bad_waiver


def test_shots_without_eye_landmarks_are_counted_not_hidden():
    a = [cvl.Frame(label=f"a{i}", faces=[face(334, 616, 690, 972, 730)]) for i in range(4)]
    b = [cvl.Frame(label=f"b{i}", faces=[face(300, 1100, 800, 1500, None)]) for i in range(4)]
    res = run(a + b)
    assert res["VL6"].status == "PASS" and "1 shot(s) without eye landmarks" in res["VL6"].detail
    assert "fewer than two shots have eye landmarks" in res["VL7"].detail


def test_compose_prints_gate_commands_only_for_what_this_run_produced(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("compose_video", SKILL / "scripts" / "compose-video.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    final, rendered = tmp_path / "x-final.mp4", tmp_path / "x-rendered.mp4"
    assert mod.gate_commands(None, None) == []
    cmds = mod.gate_commands(final, rendered)
    assert len(cmds) == 2 and str(final) in cmds[0] and cmds[1].endswith("--expect-captions --expect-title")
    assert mod.gate_commands(final, None) == [cmds[0]]


def test_io_failures_are_tool_errors(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise OSError("read-only file system")
    monkeypatch.setattr(cvl.Path, "mkdir", boom)
    with pytest.raises(cvl.ToolError):
        cvl._cache_dir()
    monkeypatch.undo()
    monkeypatch.setattr(cvl, "_need", lambda tool: tool)
    monkeypatch.setattr(cvl, "_run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="not json", stderr=""))
    with pytest.raises(cvl.ToolError):
        cvl.probe(str(tmp_path / "x.mp4"))


def test_contract_reproduces_the_measured_reel_pixels():
    """The organic profile is a measurement of the source reel's own overlays; these
    are the pixels it drew. Changing a fraction must be a deliberate re-measurement."""
    safe = cvl.zone(ORGANIC["safe_zone"], W, H)
    assert safe.as_list() == [143, 277, 938, 1643]
    rail, bottom = (cvl.zone(a, W, H) for a in ORGANIC["avoid"])
    assert (round(rail.x0), round(rail.y0), round(bottom.y0)) == (872, 922, 1686)


def test_brainrot_caption_band_constant_is_the_contracts_band():
    """brainrot-for-good hard-codes the band for its Remotion snippet; it must be the
    contract's band exactly, not merely numbers that appear somewhere in the contract."""
    import re
    doc = (SKILL.parent / "brainrot-for-good" / "SKILL.md").read_text()
    m = re.search(r"CAPTION_BAND = \{ left: (\d+), top: (\d+), width: (\d+), height: (\d+) \}", doc)
    assert m, "brainrot-for-good/SKILL.md: CAPTION_BAND constant not found"
    left, top, width, height = (int(v) for v in m.groups())
    cap = cvl.band(ORGANIC["caption_band"], cvl.zone(ORGANIC["safe_zone"], W, H), W, H).as_list()
    assert [left, top, left + width, top + height] == cap


def test_caption_band_clears_the_action_rail():
    """The contract must not contradict itself: a caption filling its band cannot
    touch an avoid zone."""
    for name, prof in LAYOUT["profiles"].items():
        if not prof.get("caption_band"):
            continue
        safe = cvl.zone(prof["safe_zone"], W, H)
        cap = cvl.Box(*cvl.band(prof["caption_band"], safe, W, H).as_list())  # rendered pixels
        slack = cvl.BOX_SLACK * H
        grown = cvl.Box(cap.x0 - slack, cap.y0 - slack, cap.x1 + slack, cap.y1 + slack)
        for a in prof.get("avoid") or []:
            # Even a caption overhanging the band by the checker's slack stays clear.
            assert not grown.intersects(cvl.zone(a, W, H)), (name, a["name"])


def _contract_pixels() -> set[int]:
    """Every pixel value a doc may quote: zone edges and sizes, band centres, the
    derived limits, the canvas."""
    vals = {W, H}
    for prof in LAYOUT["profiles"].values():
        safe = cvl.zone(prof["safe_zone"], W, H)
        rects = [safe, *(cvl.zone(a, W, H) for a in prof.get("avoid") or [])]
        rects += [cvl.band(prof[k], safe, W, H) for k in ("title_band", "caption_band") if prof.get(k)]
        for r in rects:
            x0, y0, x1, y1 = r.as_list()
            vals |= {x0, y0, x1, y1, x1 - x0, y1 - y0, int((y0 + y1) / 2), int((y0 + y1) / 2 + 0.5)}
        eye = prof.get("eye_line")
        if eye:
            vals |= {round(eye["y0"] * H), round(eye["y1"] * H), round(eye["max_shift_across_punch_in"] * H)}
        if prof.get("caption_band"):
            vals.add(round(prof["caption_band"]["centre_x_tolerance"] * W))
    vals.add(round(CLS["overlay_min_text_height"] * H))
    org = LAYOUT["profiles"]["reels-organic"]
    safe = cvl.zone(org["safe_zone"], W, H)
    cap = cvl.band(org["caption_band"], safe, W, H).as_list()
    vals.add(cvl.zone(org["avoid"][0], W, H).as_list()[0] - cap[2])  # caption band's margin to the rail
    return vals


GATE_SECTIONS = [
    # (doc, section start, section end, non-geometry px values quoted there, e.g. font sizes)
    (SKILL / "SKILL.md", "## Vertical Layout Gate", "## Extension Points", set()),
    (SKILL / "skills/content-engine-cinema/SKILL.md", "### Framing for 9:16", "## Tool Priority Matrix", set()),
    (SKILL / "templates/campaign-plan.md", "### Reels (9:16)", "### Carousels", set()),
    (SKILL / "templates/scene-brief.md", "**9:16 layout", "### Tool Selection", set()),
    (SKILL / "extensions/opencaptions/references/cwi-remotion-bridge.md", "### Safe Zones", "### Multi-Speaker", set()),
    (SKILL.parent / "brainrot-for-good/SKILL.md", "Placement follows content-engine", "const WordByWordCaption", {72}),
]


@pytest.mark.parametrize("path,start,end,extra", GATE_SECTIONS,
                         ids=[str(p.relative_to(SKILL.parent)) for p, _, _, _ in GATE_SECTIONS])
def test_skill_docs_quote_only_contract_pixels(path, start, end, extra):
    """Pixel values are copied into the skills' prose; each must still be derivable
    from the JSON, so moving a zone without updating the docs fails here."""
    import re
    doc = path.read_text()
    assert start in doc and end in doc, f"{path}: section markers moved"
    section = doc[doc.index(start):doc.index(end, doc.index(start))]
    allowed = _contract_pixels() | extra
    # Numbers glued to a word ("sha256") are identifiers, not pixels; "1080x1920" still counts.
    # A sentence-ending period is not a decimal point: "(?!\.\d)", not "(?!\.)".
    quoted = {int(n) for n in re.findall(r"(?<![A-Za-wyz\d.])(\d{3,4})(?!\d|\.\d)", section)}
    quoted |= {int(n) for n in re.findall(r"(?<![A-Za-wyz\d.])(\d{2}) ?px\b", section)}  # e.g. "58px"
    stray = sorted(quoted - allowed)
    assert not stray, f"{path.name}: {stray} are not derivable from layout/vertical-9x16.json"


def test_doc_embeds_the_generated_zone_tables():
    """Each table in the doc is the checker's output row for row: a substring check
    let a stale extra row (an eye line the meta profile no longer has) survive."""
    doc = DOC.read_text()
    for name, prof in LAYOUT["profiles"].items():
        flag = "" if name == LAYOUT["default_profile"] else f"--profile {name} "
        marker = f"Output of `python3 scripts/check_vertical_layout.py {flag}zones`"
        assert marker in doc, f"doc has no zones table for {name}"
        after = doc[doc.index(marker):]
        start = after.index("| Zone (")
        block = after[start:].split("\n\n", 1)[0].strip()
        assert block == cvl.zones_table(prof, W, H), f"references/vertical-layout.md is stale for {name}"


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
DETECTORS = [d for d, ok in (("vision", cvl.vision_binary()[0] is not None),
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
        "mid_captions": _render(d / "mid.mp4", _words(960)),
        "lowercase": _render(d / "lower.mp4", _words(1376, words=("one", "see", "was", "now"))),
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
    for rule in ("VL1", "VL2", "VL3", "VL4", "VL5", "VL9"):
        assert res[rule]["status"] == "PASS", (rule, res[rule])  # VL9: legibility was measured


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_bottom_captions_fail(videos, detector):
    code, res, _ = _check(videos["bottom"], detector, "--expect-captions")
    assert code == 1
    assert res["VL3"]["status"] == "FAIL"
    assert res["VL5"]["status"] == "FAIL"


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_captions_in_the_title_band_fail(videos, detector):
    code, res, _ = _check(videos["top_captions"], detector, "--expect-captions")
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
    assert p.stdout.rstrip().splitlines()[-1].startswith("VERDICT: PASS")  # tail -1 reads the verdict


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
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_captions_across_the_eyes_fail(videos, detector):
    code, res, _ = _check(videos["mid_captions"], detector, "--expect-captions")
    assert code == 1
    assert res["VL5"]["status"] == "FAIL"


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_lowercase_captions_are_overlay_not_scene_text(videos, detector):
    # tesseract boxes "one" at 64px as 36px of ink: under the old 2% (38px) cut.
    code, res, _ = _check(videos["lowercase"], detector, "--expect-captions")
    assert code == 0, res["VL5"]
    assert res["VL5"]["status"] == "PASS"


@media
@pytest.mark.parametrize("detector", DETECTORS)
def test_video_rotated_phone_footage_is_measured_upright(tmp_path, detector):
    up = _render(tmp_path / "up.mp4", _words(1376))
    side = tmp_path / "side.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(up), "-vf", "transpose=1", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(side)], check=True)
    rot = tmp_path / "rot.mp4"
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-display_rotation", "90", "-i", str(side), "-c", "copy",
                        str(rot)], capture_output=True, text=True)
    if p.returncode != 0:
        pytest.skip(f"this ffmpeg cannot write rotation metadata: {p.stderr.strip()[:120]}")
    code, res, rep = _check(rot, detector, "--expect-captions")
    assert rep["canvas"] == [1080, 1920]
    assert res["VL1"]["status"] == "PASS"
    assert res["VL5"]["status"] == "PASS"


@media
def test_guide_paints_the_zones_where_the_contract_puts_them(tmp_path):
    img = tmp_path / "gray.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x808080:s=1080x1920",
                    "-frames:v", "1", str(img)], check=True)
    out = tmp_path / "guide.png"
    assert _cli("guide", str(img), "--out", str(out)).returncode == 0

    def rgb(x, y):  # the guide is scaled to 360 wide: 1/3 of the canvas
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-vf", f"crop=1:1:{x // 3}:{y // 3}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        return tuple(raw)

    r, g, b = rgb(1000, 1300)          # on the action rail
    assert r > g + 40 and r > b + 40
    r, g, b = rgb(540, 1000)           # middle of the safe zone: untouched grey
    assert max(r, g, b) - min(r, g, b) <= 3 and abs(r - 128) <= 4




@media
def test_report_records_the_declared_flags(videos, tmp_path):
    """A verdict means little without knowing whether captions were declared."""
    for flags, declared in (((), []), (("--expect-captions",), ["caption"])):
        r = tmp_path / "r.json"
        p = _cli("video", str(videos["good"]), "--detector", DETECTORS[0], "--report", str(r), "--no-guide", *flags)
        assert p.returncode == 0, p.stdout + p.stderr
        report = json.loads(r.read_text())
        assert report["declared"] == declared
        assert "declared:" in p.stdout
        import hashlib
        assert report["input_sha256"] == {str(videos["good"]): hashlib.sha256(videos["good"].read_bytes()).hexdigest()}
