"""Unit tests for the EDL library — the output-timeline + caption offset math."""
import edl


def _edl(pad_ms=0, subtitles=None):
    return {
        "version": 1,
        "sources": {"clip": "/tmp/clip.mp4"},
        "ranges": [
            {"source": "clip", "start": 1.0, "end": 3.0},
            {"source": "clip", "start": 5.0, "end": 6.0},
        ],
        "grade": "neutral_punch",
        "fade_ms": 30,
        "pad_ms": pad_ms,
        "overlays": [],
        "subtitles": subtitles or {"mode": "none"},
        "output": "edit/final.mp4",
    }


def test_resolve_grade():
    assert edl.resolve_grade("none") is None
    assert "eq=" in edl.resolve_grade("neutral_punch")
    assert edl.resolve_grade({"filter": "hue=s=0"}) == "hue=s=0"
    assert edl.resolve_grade("does-not-exist") is None


def test_output_segments_no_pad():
    segs = edl.output_segments(_edl(pad_ms=0), {"clip": 10.0})
    assert len(segs) == 2
    assert segs[0]["src_start"] == 1.0 and segs[0]["src_end"] == 3.0
    assert segs[0]["out_dur"] == 2.0 and segs[0]["offset"] == 0.0
    assert segs[1]["offset"] == 2.0 and segs[1]["out_dur"] == 1.0


def test_output_segments_with_pad_and_clamp():
    # pad 60ms expands each range; clamp keeps within [0, dur]
    segs = edl.output_segments(_edl(pad_ms=60), {"clip": 10.0})
    assert round(segs[0]["src_start"], 3) == 0.94
    assert round(segs[0]["out_dur"], 3) == 2.12
    assert round(segs[1]["offset"], 3) == 2.12
    # clamp: a range ending past source duration is capped
    e = _edl(pad_ms=60)
    e["ranges"][1]["end"] = 9.99
    segs2 = edl.output_segments(e, {"clip": 10.0})
    assert segs2[1]["src_end"] <= 10.0


def test_total_duration():
    assert edl.total_duration(_edl(pad_ms=0), {"clip": 10.0}) == 3.0


def test_srt_time():
    assert edl.srt_time(0) == "00:00:00,000"
    assert edl.srt_time(2.5) == "00:00:02,500"
    assert edl.srt_time(3661.234) == "01:01:01,234"
    assert edl.srt_time(-1) == "00:00:00,000"


def test_build_srt_offset_and_uppercase():
    transcripts = {
        "clip": {
            "words": [
                {"word": "hello", "start": 1.0, "end": 1.4, "speaker": None},
                {"word": "world", "start": 1.5, "end": 1.9, "speaker": None},
                {"word": "again", "start": 5.2, "end": 5.5, "speaker": None},
            ]
        }
    }
    e = _edl(pad_ms=0, subtitles={"mode": "burn", "style": "bold-overlay", "chunk_words": 2})
    srt = edl.build_srt(e, transcripts, {"clip": 10.0})
    # range0 [1,3): "hello world" -> output 0.0..0.9, UPPERCASE
    assert "HELLO WORLD" in srt
    assert "00:00:00,000 --> 00:00:00,900" in srt
    # range1 [5,6) offset 2.0: "again" -> output 2.2..2.5
    assert "AGAIN" in srt
    assert "00:00:02,200 --> 00:00:02,500" in srt


def test_build_srt_none_mode_empty():
    assert edl.build_srt(_edl(subtitles={"mode": "none"}), {}, {"clip": 10.0}) == ""


def test_load_edl_validation(tmp_path):
    import json
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": 2, "sources": {}, "ranges": []}))
    try:
        edl.load_edl(bad)
        assert False, "should have raised"
    except ValueError:
        pass


def _write(tmp_path, obj):
    import json
    p = tmp_path / "e.json"
    p.write_text(json.dumps(obj))
    return p


def test_load_edl_malformed_range_is_valueerror(tmp_path):
    # missing 'start' must surface as a clean ValueError, not KeyError/TypeError
    bad = _write(tmp_path, {
        "version": 1, "sources": {"c": "/tmp/c.mp4"},
        "ranges": [{"source": "c", "end": 2.0}],
    })
    import pytest
    with pytest.raises(ValueError):
        edl.load_edl(bad)
    none_start = _write(tmp_path, {
        "version": 1, "sources": {"c": "/tmp/c.mp4"},
        "ranges": [{"source": "c", "start": None, "end": 2.0}],
    })
    with pytest.raises(ValueError):
        edl.load_edl(none_start)


def test_load_edl_rejects_nonpositive_chunk_words(tmp_path):
    import pytest
    for cw in (0, -1):
        bad = _write(tmp_path, {
            "version": 1, "sources": {"c": "/tmp/c.mp4"},
            "ranges": [{"source": "c", "start": 0.0, "end": 2.0}],
            "subtitles": {"mode": "burn", "chunk_words": cw},
        })
        with pytest.raises(ValueError):
            edl.load_edl(bad)
