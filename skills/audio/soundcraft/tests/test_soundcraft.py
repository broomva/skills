"""Exercise the shipped CLI using generated audio and video."""

from array import array
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import wave

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audio_qa.py"
RATE = 24000
DURATION = 12.0
PERIOD = [math.sin(2 * math.pi * index / 24) for index in range(24)]


def encode(*args):
    return subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", *map(str, args)],
        check=True, capture_output=True,
    ).stdout


def wav(path, envelope, seconds=DURATION, *, offsets=(0,), overrides=None):
    amplitudes = [envelope(index / 50) for index in range(math.ceil(seconds * 50))]
    frame_size = RATE // 50
    samples = array("h", (
        round(32768 * (amplitudes[index // frame_size] * PERIOD[index % 24] + offset))
        for index in range(round(seconds * RATE))
        for offset in offsets
    ))
    for index, sample in (overrides or {}).items():
        samples[index] = sample
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setparams((len(offsets), 2, RATE, 0, "NONE", "not compressed"))
        out.writeframes(samples.tobytes())
    return path


def mix_envelope(time):
    if 5.5 <= time < 6.5:
        return 0.46
    if 4 <= time < 8:
        return 0.40
    return 0.145


@pytest.fixture(scope="session")
def mix(tmp_path_factory):
    return wav(tmp_path_factory.mktemp("mix") / "mix.wav", mix_envelope)


def video(path, audio, *, delay=0, codec="alac"):
    encode(
        "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=20:duration=12",
        "-itsoffset", delay, "-i", audio, "-map", "0:v", "-map", "1:a",
        "-c:v", "mpeg4", "-threads", "1", "-c:a", codec, path,
    )
    return path


@pytest.fixture(scope="session")
def synced_video(tmp_path_factory, mix):
    return video(tmp_path_factory.mktemp("video") / "synced.mp4", mix)


def cli(*args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=env,
    )


def check(path, *args, fails=()):
    result = cli("check", path, "--json", *args)
    expected_code = 1 if fails else 0
    assert result.returncode == expected_code, (result.stdout, result.stderr)
    report = json.loads(result.stdout)
    assert report["passed"] is (not fails)
    assert set(report["failed_gates"]) == set(fails)
    assert {gate for gate, passed in report["gates"].items() if not passed} == set(fails)
    return report


def test_default_audio_only_passes(mix):
    report = check(mix, "--expected-dur", DURATION, "--check-peak-window")
    assert report["audio_duration_s"] == DURATION
    assert report["video_duration_s"] is None and report["av_delta_ms"] is None
    assert "av_duration" not in report["gates"]
    assert report["integrated_lufs"] == pytest.approx(-14, abs=0.8)
    assert report["true_peak_dbtp"] < -0.9 and report["lra_lu"] >= 3.5
    assert report["clipped_samples"] == 0
    assert report["peak_time_frac"] == pytest.approx(0.5, abs=0.003)


def test_integrated_loudness_failure(tmp_path):
    quiet = wav(tmp_path / "quiet.wav", lambda t: 0.5 * mix_envelope(t))
    report = check(quiet, fails=("integrated_loudness",))
    assert report["integrated_lufs"] < -14.8


def test_true_peak_failure_without_pcm_clip(tmp_path):
    peaked = wav(tmp_path / "peak.wav", mix_envelope, overrides={1057: -31600})
    report = check(peaked, fails=("true_peak",))
    assert report["true_peak_dbtp"] > -0.9 and report["clipped_samples"] == 0


def test_loudness_range_failure(tmp_path):
    flat = wav(tmp_path / "flat.wav", lambda _: 0.282)
    report = check(flat, fails=("loudness_range",))
    assert report["lra_lu"] < 3.5


def test_clipping_threshold_includes_both_polarities(tmp_path):
    samples = {500: 32735, 1500: -32735, 2500: 32767, 3500: -32768, 4500: 32734}
    clipped = wav(tmp_path / "clipped.wav", mix_envelope, overrides=samples)
    report = check(clipped, "--max-tp", 2, fails=("clipping",))
    assert report["clipped_samples"] == 4
    check(clipped, "--max-clipped", 4, "--max-tp", 2)


def test_dc_offset_checks_each_channel(tmp_path):
    biased = wav(tmp_path / "dc.wav", lambda t: mix_envelope(t) / math.sqrt(2),
                 offsets=(0.02, -0.02))
    report = check(biased, fails=("dc_offset",))
    assert report["dc_offset_by_channel"] == pytest.approx([0.02, -0.02], abs=1e-5)


def test_dead_silence_failure(tmp_path):
    silent = wav(tmp_path / "silent.wav", lambda _: 0)
    report = check(silent, "--target-lufs", -70, "--min-lra", 0, fails=("dead_silence",))
    assert report["rms_dbfs"] == -120
    assert report["true_peak_dbtp"] is None


def test_synchronized_video_passes(synced_video):
    report = check(synced_video)
    assert report["video_duration_s"] == DURATION
    assert report["av_delta_ms"] == 0
    assert report["av_start_delta_ms"] == 0


def test_av_duration_failure(tmp_path):
    short = wav(tmp_path / "short.wav", mix_envelope, DURATION - 0.2)
    report = check(video(tmp_path / "short.mp4", short), fails=("av_duration",))
    assert report["av_delta_ms"] == pytest.approx(200)
    assert report["av_start_delta_ms"] == 0


def test_av_start_failure(tmp_path, mix):
    delayed = video(tmp_path / "delayed.mp4", mix, delay=0.13)
    report = check(delayed, fails=("av_start",))
    assert report["av_start_delta_ms"] == pytest.approx(130)
    assert report["av_delta_ms"] == 0


def test_video_without_stream_duration_uses_packets(tmp_path, mix):
    mkv = video(tmp_path / "synced.mkv", mix, codec="pcm_s16le")
    report = check(mkv)
    assert report["video_duration_s"] == DURATION
    assert report["av_delta_ms"] == 0


def test_expected_duration_failure_and_boundary(mix):
    report = check(mix, "--expected-dur", 12.051, fails=("expected_duration",))
    assert report["expected_delta_ms"] == pytest.approx(51)
    check(mix, "--expected-dur", 12.05)


def test_logo_peak_gate_is_opt_in(tmp_path):
    late = wav(tmp_path / "late.wav", lambda t: mix_envelope((t - 5.1) % DURATION))
    report = check(late)
    assert report["peak_time_frac"] == pytest.approx(0.925, abs=0.005)
    assert "peak_window" not in report["gates"]
    check(late, "--check-peak-window", fails=("peak_window",))


@pytest.fixture
def voice(tmp_path):
    def speech(time):
        if 0.4 <= time < 0.8:
            return 0.16
        if 0.8 <= time < 1.8:
            return 0.23
        return 0.001
    return wav(tmp_path / "voice.wav", speech, 2)


def test_voice_snr_passes(mix, voice, tmp_path):
    bed = wav(tmp_path / "bed.wav", lambda _: 0.11, 2, offsets=(0, 0))
    report = check(mix, "--voice", voice, "--bed", bed)
    assert report["median_snr_db"] == pytest.approx(20 * math.log10(0.23 / 0.11), abs=0.02)
    assert report["p15_snr_db"] == pytest.approx(20 * math.log10(0.16 / 0.11), abs=0.02)
    assert report["active_speech_frames"] == report["covered_speech_frames"] == 70


def test_voice_has_independent_median_and_soft_frame_gates(mix, voice, tmp_path):
    cases = [
        ("median", lambda t: 0.16 if t < 0.8 else 0.15, ("median_snr", "p15_snr")),
        ("median_only", lambda t: 0.10 if t < 0.8 else 0.16, ("median_snr",)),
        ("soft_only", lambda t: 0.16 if t < 0.8 else 0.11, ("p15_snr",)),
    ]
    for name, envelope, fails in cases:
        bed = wav(tmp_path / f"{name}.wav", envelope, 2)
        check(mix, "--voice", voice, "--bed", bed, fails=fails)


def test_voice_snr_checks_coverage(mix, voice, tmp_path):
    short = wav(tmp_path / "short-bed.wav", lambda _: 0.04, 1)
    report = check(mix, "--voice", voice, "--bed", short, fails=("speech_coverage",))
    assert report["covered_speech_frames"] == 30
    assert report["active_speech_frames"] == 70


def test_voice_snr_rejects_no_activity(mix, tmp_path):
    quiet = wav(tmp_path / "quiet-voice.wav", lambda t: 0.005 if t > 0.4 else 0, 2)
    bed = wav(tmp_path / "bed.wav", lambda _: 0.0002, 2)
    report = check(mix, "--voice", quiet, "--bed", bed,
                   fails=("speech_coverage", "median_snr", "p15_snr"))
    assert report["active_speech_frames"] == 0
    assert report["median_snr_db"] is None and report["p15_snr_db"] is None


def test_voice_snr_activity_is_relative_to_noise_floor(mix, tmp_path):
    noisy = wav(tmp_path / "noisy-voice.wav", lambda t: 0.15 if t >= 0.5 else 0.025, 2)
    bed = wav(tmp_path / "bed.wav", lambda _: 0.02, 2)
    report = check(mix, "--voice", noisy, "--bed", bed)
    assert report["active_speech_frames"] == 75


def test_repeatable_stem_peak_gate(mix, tmp_path):
    clipped = wav(tmp_path / "clipped.wav", lambda _: 0.1, overrides={500: -32736})
    report = check(mix, "--stem", mix, "--stem", clipped, fails=("stem_peak",))
    assert [stem["peak_passed"] for stem in report["stems"]] == [True, False]
    assert report["stems"][1]["peak_amplitude"] >= 0.999
    assert "stem_duration" not in report["gates"]


def test_stem_truncation_and_sidechain_pad(mix, tmp_path):
    def duck(bed, out):
        encode(
            "-i", bed, "-i", mix, "-filter_complex",
            # Equal 10 ms packets keep the fixture independent of demuxer packet sizes.
            "[0:a]asetnsamples=n=240:p=0[bed];"
            "[1:a]apad=pad_dur=1,asetnsamples=n=240:p=0[key];"
            "[bed][key]sidechaincompress,atrim=duration=12[a]",
            "-map", "[a]", out,
        )
        return out

    short = wav(tmp_path / "short.wav", lambda _: 0.08, 11.41)
    stem = duck(short, tmp_path / "short-ducked.wav")
    report = check(mix, "--expected-dur", DURATION, "--stem", stem, fails=("stem_duration",))
    assert report["stems"][0]["shortfall_s"] == pytest.approx(0.59, abs=0.001)

    padded = tmp_path / "padded.wav"
    result = cli("pad-sidechain", short, padded)
    assert result.returncode == 0, result.stderr
    with wave.open(str(short), "rb") as original:
        original_pcm = original.readframes(original.getnframes())
    padded_pcm = encode("-i", padded, "-f", "s16le", "-")
    assert padded_pcm == original_pcm + bytes(2 * RATE)
    fixed = duck(padded, tmp_path / "fixed-ducked.wav")
    report = check(mix, "--expected-dur", DURATION, "--stem", fixed)
    assert report["stems"][0]["duration_s"] == DURATION


def test_stem_allows_quarter_second_shortfall(mix, tmp_path):
    stem = wav(tmp_path / "boundary.wav", lambda _: 0.1, 11.75)
    check(mix, "--expected-dur", DURATION, "--stem", stem)


@pytest.mark.parametrize("fixture,has_video", [("mix", False), ("synced_video", True)])
def test_sheet_generates_annotated_png(request, fixture, has_video, tmp_path):
    output = tmp_path / "sheet.png"
    result = cli("sheet", request.getfixturevalue(fixture), "--out", output)
    assert result.returncode == 0, result.stderr
    png = output.read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    assert width == 1200
    assert height > (600 if has_video else 440)
    assert len(png) > 10_000

    pixels = encode("-i", output, "-pix_fmt", "rgb24", "-f", "rawvideo", "-threads", "1", "-")
    assert len(pixels) == width * height * 3
    waveform_y = 142 if has_video else 0
    label_row = pixels[width * (waveform_y + 11) * 3:width * (waveform_y + 12) * 3]
    assert max(label_row) > 180
    if has_video:
        for index in range(8):
            start = (width * 65 + index * 150) * 3
            tile = pixels[start:start + 150 * 3]
            assert len(set(tile)) > 25


def test_sheet_handles_audio_with_fewer_samples_than_pixels(tmp_path):
    short = wav(tmp_path / "short.wav", lambda _: 0.2, 0.02)
    output = tmp_path / "short.png"
    result = cli("sheet", short, "--out", output)
    assert result.returncode == 0, result.stderr
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_cli_text_success_and_gate_failure(mix):
    assert cli("check", mix).stdout.startswith("PASS ")
    result = cli("check", mix, "--min-lra", 100)
    assert result.returncode == 1
    assert "FAIL loudness_range" in result.stdout


@pytest.mark.parametrize("args", [
    (),
    ("check", "missing.wav"),
    ("check", "missing.wav", "--voice", "voice.wav"),
    ("check", "missing.wav", "--lufs-tol", "NaN"),
    ("check", "missing.wav", "--max-clipped", "-1"),
])
def test_cli_invalid_use_exits_two(args):
    result = cli(*args)
    assert result.returncode == 2
    assert "error:" in result.stderr or "audio_qa:" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_ffmpeg_exits_two(mix):
    result = cli("check", mix, env=dict(os.environ, PATH=""))
    assert result.returncode == 2
    assert "ffmpeg was not found" in result.stderr
