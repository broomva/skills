"""Unit tests for transcript packing — phrase boundary rule + render format."""
import pack_transcripts as pack


WORDS = [
    {"word": "a", "start": 0.0, "end": 0.3, "speaker": None},
    {"word": "b", "start": 0.4, "end": 0.7, "speaker": None},   # gap 0.1 -> same phrase
    {"word": "c", "start": 1.5, "end": 1.8, "speaker": None},   # gap 0.8 >=0.5 -> new
    {"word": "d", "start": 1.9, "end": 2.2, "speaker": "S1"},   # speaker change -> new
]


def test_group_phrases_gap_and_speaker_breaks():
    phrases = pack.group_phrases(WORDS, gap=0.5)
    assert [p["text"] for p in phrases] == ["a b", "c", "d"]
    assert phrases[0]["start"] == 0.0 and phrases[0]["end"] == 0.7
    assert phrases[2]["speaker"] == "S1"


def test_group_phrases_empty():
    assert pack.group_phrases([]) == []


def test_group_phrases_tighter_gap():
    # gap threshold 0.05 -> the 0.1 gap now also breaks
    phrases = pack.group_phrases(WORDS, gap=0.05)
    assert [p["text"] for p in phrases] == ["a", "b", "c", "d"]


def test_render_pack_format():
    transcript = {"duration": 2.2, "words": WORDS}
    out = pack.render_pack(transcript, "clip", gap=0.5)
    lines = out.splitlines()
    assert lines[0] == "## clip  (duration: 2.2s, 3 phrases)"
    assert lines[1] == "  [000.00-000.70] S0 a b"
    assert lines[3] == "  [001.90-002.20] S1 d"
