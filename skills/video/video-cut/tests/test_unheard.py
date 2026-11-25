"""Unit + synthetic FFmpeg E2E tests for scripts/unheard.py."""

from __future__ import annotations

import array
import json
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

import unheard

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _write_synthetic_wav(
    path: Path,
    duration_s: float,
    bursts: list[tuple[float, float, list[float], float]],
    sample_rate: int = 16000,
    noise_db: float | None = None,
) -> Path:
    """Write a mono 16-bit PCM WAV with deterministic sine-sum speech bursts."""
    n = int(round(sample_rate * duration_s))
    buf = [0.0] * n

    if noise_db is not None:
        # Deterministic low-level room tone (2-tone hum, avoids RNG flakiness)
        n_amp = 32767.0 * (10.0 ** (noise_db / 20.0)) * math.sqrt(2.0)
        for i in range(n):
            t = i / sample_rate
            buf[i] += n_amp * math.sin(2.0 * math.pi * 60.0 * t)

    for t0, t1, freqs, db in bursts:
        amp = 32767.0 * (10.0 ** (db / 20.0)) * math.sqrt(2.0) / math.sqrt(len(freqs))
        i0 = max(0, int(round(t0 * sample_rate)))
        i1 = min(n, int(round(t1 * sample_rate)))
        for i in range(i0, i1):
            t = i / sample_rate
            buf[i] += sum(amp * math.sin(2.0 * math.pi * f * t) for f in freqs)

    pcm = [max(-32768, min(32767, int(round(v)))) for v in buf]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n}h", *pcm))
    return path


# ---------------------------------------------------------------------------
# Pure unit tests
# ---------------------------------------------------------------------------
def test_rms_envelope_silence_and_tone():
    sr = 16000
    # 0.2s silence + 0.2s -18 dBFS sine
    n_half = int(sr * 0.2)
    amp = 32767.0 * (10.0 ** (-18.0 / 20.0)) * math.sqrt(2.0)
    tone = [int(round(amp * math.sin(2.0 * math.pi * 400.0 * i / sr))) for i in range(n_half)]
    samples = array.array("h", [0] * n_half + tone)

    env = unheard.compute_rms_envelope(samples, sr, frame_ms=20.0)
    assert len(env) == 20
    assert all(f["db"] == unheard.SILENCE_FLOOR_DB for f in env[:10])
    assert all(-18.5 <= f["db"] <= -17.5 for f in env[10:])


def test_adaptive_threshold_and_explicit_override():
    # Room tone at -46 dBFS -> adaptive floor = max(-46 + 12, -42) = -34 dBFS
    env_noisy = [{"start": i * 0.02, "end": (i + 1) * 0.02, "rms": 0.005, "db": -46.0} for i in range(40)]
    env_noisy += [{"start": i * 0.02, "end": (i + 1) * 0.02, "rms": 0.12, "db": -18.0} for i in range(40, 50)]
    floor_db, thresh_db = unheard.compute_speech_threshold_db(env_noisy)
    assert floor_db == pytest.approx(-46.0)
    assert thresh_db == pytest.approx(-34.0)

    # Quiet digital silence -> clamps to -42.0 dBFS
    env_quiet = [{"start": i * 0.02, "end": (i + 1) * 0.02, "rms": 0.0, "db": -120.0} for i in range(40)]
    _, thresh_quiet = unheard.compute_speech_threshold_db(env_quiet)
    assert thresh_quiet == pytest.approx(-42.0)

    # Explicit override
    _, thresh_explicit = unheard.compute_speech_threshold_db(env_noisy, speech_db=-28.5)
    assert thresh_explicit == pytest.approx(-28.5)


def test_detect_active_speech_merges_intra_word_pauses():
    # Two active chunks separated by 0.12s (<= 0.15s -> merged) and a third separated by 0.30s (> 0.15s)
    env = []
    for i in range(100):  # 2.0s total at 20ms/frame
        t0, t1 = i * 0.02, (i + 1) * 0.02
        active = (0.20 <= t0 < 0.60) or (0.72 <= t0 < 1.10) or (1.40 <= t0 < 1.80)
        env.append({"start": t0, "end": t1, "rms": 0.1 if active else 0.0, "db": -20.0 if active else -120.0})

    intervals = unheard.detect_active_speech(env, threshold_db=-42.0, merge_pause_s=0.15)
    assert len(intervals) == 2
    assert intervals[0][0] == pytest.approx(0.20, abs=0.02)
    assert intervals[0][1] == pytest.approx(1.10, abs=0.02)
    assert intervals[1][0] == pytest.approx(1.40, abs=0.02)
    assert intervals[1][1] == pytest.approx(1.80, abs=0.02)


def test_subtract_intervals():
    active = [(0.5, 5.0), (6.0, 8.0)]
    covered = [(0.4, 1.5), (3.0, 4.0), (6.0, 8.1)]
    uncovered = unheard.subtract_intervals(active, covered)
    assert uncovered == [(1.5, 3.0), (4.0, 5.0)]


def test_load_transcript_spans_all_layouts():
    # 1. transcribe_local.py layout
    t_words = {
        "words": [
            {"word": "Hello", "start": 0.2, "end": 0.6},
            {"word": "world", "start": 0.7, "end": 1.1},
        ],
        "segments": [{"start": 0.2, "end": 1.1, "text": "Hello world"}],
    }
    words, phrases = unheard.load_transcript_spans(t_words)
    assert [w["word"] for w in words] == ["Hello", "world"]
    assert phrases[0]["text"] == "Hello world"

    # 2. segments with nested words
    t_nested = {
        "segments": [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "Good morning",
                "words": [
                    {"word": "Good", "start": 1.0, "end": 1.4},
                    {"word": "morning", "start": 1.5, "end": 2.0},
                ],
            }
        ]
    }
    words2, phrases2 = unheard.load_transcript_spans(t_nested)
    assert len(words2) == 2 and words2[1]["word"] == "morning"
    assert len(phrases2) == 1

    # 3. segments-only without nested words
    t_seg_only = {"segments": [{"start": 2.0, "end": 3.5, "text": "Single line"}]}
    words3, phrases3 = unheard.load_transcript_spans(t_seg_only)
    assert len(words3) == 1 and words3[0]["start"] == 2.0 and words3[0]["end"] == 3.5
    assert phrases3[0]["text"] == "Single line"

    # 4. clips dict (matches media stem)
    t_clips = {
        "clips": {
            "take_a": {"words": [{"word": "alpha", "start": 0.1, "end": 0.5}]},
            "take_b": {"words": [{"word": "beta", "start": 1.0, "end": 1.5}]},
        }
    }
    words4, _ = unheard.load_transcript_spans(t_clips, media_path="/tmp/take_b.mp4")
    assert [w["word"] for w in words4] == ["beta"]
    words4_explicit, _ = unheard.load_transcript_spans(t_clips, clip_name="take_a")
    assert [w["word"] for w in words4_explicit] == ["alpha"]


def test_annotate_transcript_interleaves_markers():
    phrases = [
        {"start": 0.5, "end": 1.5, "text": "First take"},
        {"start": 4.8, "end": 5.5, "text": "Final line"},
    ]
    regions = [
        {"start": 3.2, "end": 4.2, "duration": 1.0, "mean_db": -18.2},
    ]
    out = unheard.annotate_transcript(phrases, regions)
    lines = out.strip().splitlines()
    assert lines == [
        "[000.50s-001.50s] First take",
        "[UNHEARD 3.20s-4.20s (1.00s, -18.2 dBFS)]",
        "[004.80s-005.50s] Final line",
    ]


# ---------------------------------------------------------------------------
# Synthetic FFmpeg E2E tests (WAV direct + MP4 ffmpeg decode + CLI)
# ---------------------------------------------------------------------------
def test_e2e_catches_unheard_burst_ignores_covered_and_breath(tmp_path):
    """Prove unheard.py catches a 1.0s spoken-band burst omitted from transcript
    while ignoring covered words and a 0.25s breath, across WAV and MP4 inputs."""
    wav_path = _write_synthetic_wav(
        tmp_path / "take.wav",
        duration_s=6.0,
        bursts=[
            (0.50, 1.50, [300.0, 620.0], -18.0),  # covered words
            (2.20, 2.45, [240.0], -24.0),          # 0.25s breath -> ignore (< 0.6s)
            (3.20, 4.20, [350.0, 740.0], -18.0),   # 1.0s UNHEARD retake -> catch!
            (4.80, 5.50, [310.0, 680.0], -18.0),   # covered words
        ],
    )
    transcript = {
        "source": str(wav_path),
        "duration": 6.0,
        "words": [
            {"word": "First", "start": 0.50, "end": 0.95},
            {"word": "take", "start": 1.00, "end": 1.50},
            {"word": "Final", "start": 4.80, "end": 5.12},
            {"word": "line", "start": 5.15, "end": 5.50},
        ],
    }
    t_path = tmp_path / "transcript.json"
    t_path.write_text(json.dumps(transcript), encoding="utf-8")

    # 1. Direct PCM WAV path
    res_wav = unheard.detect_unheard(wav_path, t_path)
    assert res_wav["unheard_count"] == 1
    u = res_wav["unheard"][0]
    assert u["start"] == pytest.approx(3.2, abs=0.05)
    assert u["end"] == pytest.approx(4.2, abs=0.05)
    assert u["duration"] == pytest.approx(1.0, abs=0.05)
    assert u["peak_db"] > -30.0
    assert u["mean_db"] > -30.0
    assert u["context_before"] == "First take"
    assert u["context_after"] == "Final line"
    assert u["suggested_action"] == "inspect_possible_retake_or_dropped_speech"

    # 2. Mux to MP4 via real ffmpeg and test ffmpeg decode path
    mp4_path = tmp_path / "take.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=6",
            "-i", str(wav_path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            "-shortest", str(mp4_path),
        ],
        check=True,
    )
    res_mp4 = unheard.detect_unheard(mp4_path, t_path)
    assert res_mp4["unheard_count"] == 1
    assert res_mp4["unheard"][0]["start"] == pytest.approx(3.2, abs=0.06)
    assert res_mp4["unheard"][0]["end"] == pytest.approx(4.2, abs=0.06)

    # 3. CLI detect --json --annotate-out
    ann_out = tmp_path / "annotated.txt"
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPTS_DIR / "unheard.py"),
            "detect", str(mp4_path),
            "--transcript", str(t_path),
            "--json",
            "--annotate-out", str(ann_out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    cli_json = json.loads(proc.stdout)
    assert cli_json["unheard_count"] == 1
    ann_text = ann_out.read_text(encoding="utf-8")
    assert "[UNHEARD 3.20s-4.20s" in ann_text
    assert "First take" in ann_text
    assert "Final line" in ann_text

    # 4. CLI annotate reusing saved detect JSON
    detect_json_path = tmp_path / "detect.json"
    detect_json_path.write_text(proc.stdout, encoding="utf-8")
    proc_ann = subprocess.run(
        [
            sys.executable, str(SCRIPTS_DIR / "unheard.py"),
            "annotate",
            "--transcript", str(t_path),
            "--unheard", str(detect_json_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[UNHEARD 3.20s-4.20s" in proc_ann.stdout


def test_p20_multi_segment_transcript_keeps_all_coverage_spans():
    """All segments (not just segment 0) must contribute coverage spans."""
    transcript_nested = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "one", "words": [{"word": "one", "start": 0.0, "end": 1.0}]},
            {"start": 2.0, "end": 3.0, "text": "two", "words": [{"word": "two", "start": 2.0, "end": 3.0}]},
            {"start": 4.0, "end": 5.0, "text": "three", "words": [{"word": "three", "start": 4.0, "end": 5.0}]},
        ]
    }
    words, phrases = unheard.load_transcript_spans(transcript_nested)
    assert len(words) == 3
    assert [w["word"] for w in words] == ["one", "two", "three"]
    assert len(phrases) == 3

    transcript_seg_only = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "alpha"},
            {"start": 2.0, "end": 3.0, "text": "beta"},
            {"start": 4.0, "end": 5.0, "text": "gamma"},
        ]
    }
    words2, _ = unheard.load_transcript_spans(transcript_seg_only)
    assert len(words2) == 3


def test_p20_ambiguous_multiclip_transcript_raises():
    """Unmatched media stem on multi-clip transcript must fail explicitly rather than merging clips."""
    transcript = {
        "clips": {
            "clip_a": {"words": [{"word": "a", "start": 0.0, "end": 1.0}]},
            "clip_b": {"words": [{"word": "b", "start": 2.0, "end": 3.0}]},
        }
    }
    with pytest.raises(ValueError, match="ambiguous"):
        unheard.load_transcript_spans(transcript, media_path="unknown_stem.wav")


def test_p20_boolean_timestamps_rejected():
    """Boolean start/end values must be rejected, not coerced to 0.0/1.0."""
    words, _ = unheard.load_transcript_spans(
        {"words": [{"word": "bad", "start": False, "end": True}]}
    )
    assert words == []


def test_p20_opposite_phase_stereo_wav_preserves_energy(tmp_path):
    """Equal-and-opposite stereo PCM must not cancel to silence in RMS loudness envelope."""
    import array, math, wave
    sr = 16000
    n = sr  # 1.0s
    pcm = array.array("h")
    for i in range(n):
        v = int(14000 * math.sin(2.0 * math.pi * 440.0 * i / sr))
        pcm.append(v)
        pcm.append(-v)
    wav_path = tmp_path / "antiphase.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    samples, rate = unheard.decode_pcm_mono(wav_path)
    assert rate == sr
    frames = unheard.compute_rms_envelope(samples, rate)
    assert max(f["db"] if isinstance(f, dict) else f[2] for f in frames) > -12.0
