#!/usr/bin/env python3
"""Measure a rendered mix, make a visual audio sheet, or pad a sidechain bed."""

from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile


PCM_FULL_SCALE = 32768
CLIP_LEVEL = 32735
MAX_DC_OFFSET = 0.01
MIN_RMS_DBFS = -60.0
MIN_MEDIAN_SNR_DB = 4.2
MIN_P15_SNR_DB = 1.2
MAX_STEM_SHORTFALL_S = 0.25
MAX_PEAK_TIME_FRAC = 0.88
SNR_RATE = 48000
DBFS_FLOOR = -120.0


class UsageError(Exception):
    """An input or a required tool cannot be used."""


def run(*command: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, LC_ALL="C", AV_LOG_FORCE_NOCOLOR="1")
    result = subprocess.run(command, capture_output=True, env=env)
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise UsageError(f"{command[0]} failed: {detail[-2000:]}")
    return result


def ffmpeg(*args: str, loglevel: str = "error") -> subprocess.CompletedProcess:
    return run("ffmpeg", "-nostdin", "-hide_banner", "-loglevel", loglevel, *args)


@dataclass(frozen=True)
class Audio:
    index: int
    rate: int
    channels: int
    start: float


@dataclass(frozen=True)
class Video:
    index: int
    duration: float
    start: float


def optional_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def packet_bounds(path: Path, index: int) -> tuple[float, float]:
    # Some containers (e.g. Matroska) omit stream duration in their headers.
    result = run(
        "ffprobe", "-v", "error", "-select_streams", str(index),
        "-show_entries", "packet=pts_time,duration_time", "-of", "json", str(path),
    )
    starts, ends = [], []
    for packet in json.loads(result.stdout).get("packets", []):
        start = optional_number(packet.get("pts_time"))
        duration = optional_number(packet.get("duration_time"))
        if start is not None:
            starts.append(start)
            ends.append(start + (duration or 0.0))
    if not starts:
        raise UsageError(f"cannot measure video timestamps in {path}")
    # When packets omit their duration, infer the last frame interval from
    # adjacent presentation timestamps. Packet order need not be display order.
    last = max(starts)
    end = max(ends)
    if end == last:
        previous = max((start for start in starts if start < last), default=last)
        end += last - previous
    return min(starts), end


def probe(path: Path, *, include_video: bool = False) -> tuple[Audio, Video | None]:
    result = run("ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path))
    streams = json.loads(result.stdout).get("streams", [])
    audio = next((s for s in streams if s["codec_type"] == "audio"), None)
    if audio is None:
        raise UsageError(f"{path} has no audio stream")
    rate = int(audio.get("sample_rate") or 0)
    channels = int(audio.get("channels") or 0)
    if rate <= 0 or channels <= 0:
        raise UsageError(f"cannot read audio rate and channels in {path}")
    sound = Audio(audio["index"], rate, channels, optional_number(audio.get("start_time")) or 0.0)
    if not include_video:
        return sound, None

    video = next(
        (s for s in streams if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")),
        None,
    )
    if video is None:
        return sound, None
    index = video["index"]
    start = optional_number(video.get("start_time"))
    duration = optional_number(video.get("duration"))
    if duration is None or duration <= 0:
        start, end = packet_bounds(path, index)
        duration = end - start
    if duration <= 0:
        raise UsageError(f"cannot measure video duration in {path}")
    return sound, Video(index, duration, start or 0.0)


def decode(path: Path, audio: Audio, *, floating: bool = False, rate: int | None = None) -> array:
    encoding, kind = ("f32", "f") if floating else ("s16", "h")
    args = ["-ar", str(rate)] if rate is not None else []
    result = ffmpeg(
        "-i", str(path), "-map", f"0:{audio.index}", *args,
        "-c:a", f"pcm_{encoding}le", "-f", f"{encoding}le", "-",
    )
    pcm = array(kind)
    pcm.frombytes(result.stdout)
    if sys.byteorder != "little":
        pcm.byteswap()
    if not pcm or len(pcm) % audio.channels:
        raise UsageError(f"{path} did not decode to complete audio frames")
    return pcm


def loudness(path: Path, audio: Audio) -> dict[str, float]:
    result = ffmpeg(
        "-nostats", "-i", str(path), "-map", f"0:{audio.index}",
        "-af", "ebur128=peak=true:framelog=verbose", "-f", "null", "-",
        loglevel="info",
    )
    report = result.stderr.decode(errors="replace").rsplit("Summary:", 1)[-1]
    values = {}
    for key, label, unit in (
        ("integrated_lufs", "I", "LUFS"),
        ("true_peak_dbtp", "Peak", "dBFS"),
        ("lra_lu", "LRA", "LU"),
    ):
        match = re.search(rf"^\s*{label}:\s+(\S+)\s+{unit}\b", report, re.MULTILINE)
        if match is None:
            raise UsageError(f"cannot read {label} from the FFmpeg ebur128 summary")
        values[key] = float(match[1])
    return values


def square_sum(samples: array) -> float:
    return sum(sample * sample for sample in samples)


def dbfs(mean_square: float) -> float:
    if mean_square <= 10 ** (DBFS_FLOOR / 10):
        return DBFS_FLOOR
    return 10 * math.log10(mean_square)


def peak_time(pcm: array, audio: Audio) -> float:
    """Center of the loudest one-second RMS window, searched every 20 ms."""
    window = min(len(pcm), audio.rate * audio.channels)
    hop = max(1, round(audio.rate * 0.02)) * audio.channels
    last = len(pcm) - window
    start = best_start = 0
    energy = best_energy = square_sum(pcm[:window])
    while start < last:
        following = min(start + hop, last)
        energy += square_sum(pcm[start + window:following + window])
        energy -= square_sum(pcm[start:following])
        if energy > best_energy:
            best_start, best_energy = following, energy
        start = following
    return (best_start + window / 2) / len(pcm)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def frame_levels(path: Path) -> list[float]:
    audio, _ = probe(path)
    pcm = decode(path, audio, floating=True, rate=SNR_RATE)
    frame = SNR_RATE // 50 * audio.channels
    levels = [dbfs(square_sum(pcm[start:start + frame]) / frame)
              for start in range(0, len(pcm) - frame + 1, frame)]
    if any(not math.isfinite(level) for level in levels):
        raise UsageError(f"{path} contains nonfinite audio samples")
    return levels


def speech_snr(voice: Path, bed: Path) -> dict:
    voice_levels = frame_levels(voice)
    bed_levels = frame_levels(bed)
    noise_floor = percentile(voice_levels, 0.20) if voice_levels else None
    active = []
    if noise_floor is not None:
        active = [
            index for index, voice_db in enumerate(voice_levels)
            if voice_db > noise_floor + 12 and voice_db > -42
        ]
    differences = [voice_levels[index] - bed_levels[index] for index in active if index < len(bed_levels)]
    return {
        "voice_noise_floor_dbfs": noise_floor,
        "active_speech_frames": len(active),
        "covered_speech_frames": len(differences),
        "median_snr_db": statistics.median(differences) if differences else None,
        "p15_snr_db": percentile(differences, 0.15) if differences else None,
    }


def check_stem(path: Path, expected_dur: float | None) -> dict:
    audio, _ = probe(path)
    pcm = decode(path, audio, floating=True)
    peak = max(abs(sample) if math.isfinite(sample) else math.inf for sample in pcm)
    duration = len(pcm) / (audio.channels * audio.rate)
    result = {
        "path": str(path),
        "duration_s": duration,
        "peak_amplitude": peak if math.isfinite(peak) else None,
        "peak_passed": peak < 0.999,
    }
    if expected_dur is not None:
        result["shortfall_s"] = max(0.0, expected_dur - duration)
        result["duration_passed"] = duration >= expected_dur - MAX_STEM_SHORTFALL_S
    return result


def check(args: argparse.Namespace) -> int:
    audio, video = probe(args.media_path, include_video=True)
    pcm = decode(args.media_path, audio)
    duration = len(pcm) / (audio.channels * audio.rate)
    clipped = sum(abs(sample) >= CLIP_LEVEL for sample in pcm)
    dc = [sum(pcm[channel::audio.channels]) / (len(pcm) // audio.channels * PCM_FULL_SCALE)
          for channel in range(audio.channels)]
    rms = dbfs(square_sum(pcm) / (len(pcm) * PCM_FULL_SCALE ** 2))
    peak_frac = peak_time(pcm, audio)
    levels = loudness(args.media_path, audio)
    integrated, true_peak, lra = levels.values()
    gates = {
        "integrated_loudness": math.isfinite(integrated)
        and abs(integrated - args.target_lufs) <= args.lufs_tol + 1e-9,
        "true_peak": true_peak <= args.max_tp,
        "loudness_range": lra >= args.min_lra,
        "clipping": clipped <= args.max_clipped,
        "dc_offset": max(map(abs, dc)) <= MAX_DC_OFFSET,
        "dead_silence": rms > MIN_RMS_DBFS,
    }
    metrics = {
        "audio_duration_s": duration,
        "video_duration_s": None,
        "av_delta_ms": None,
        "av_start_delta_ms": None,
        "expected_delta_ms": None,
        **{key: value if math.isfinite(value) else None for key, value in levels.items()},
        "clipped_samples": clipped,
        "dc_offset_by_channel": dc,
        "rms_dbfs": rms,
        "peak_time_frac": peak_frac,
    }
    if video is not None:
        metrics["video_duration_s"] = video.duration
        metrics["av_delta_ms"] = abs(duration - video.duration) * 1000
        metrics["av_start_delta_ms"] = abs(audio.start - video.start) * 1000
        gates["av_duration"] = metrics["av_delta_ms"] <= args.max_av_delta_ms + 1e-9
        gates["av_start"] = metrics["av_start_delta_ms"] <= args.max_av_delta_ms + 1e-9
    if args.expected_dur is not None:
        metrics["expected_delta_ms"] = abs(duration - args.expected_dur) * 1000
        gates["expected_duration"] = metrics["expected_delta_ms"] <= args.max_av_delta_ms + 1e-9
    if args.check_peak_window:
        gates["peak_window"] = peak_frac <= MAX_PEAK_TIME_FRAC

    if args.voice is not None:
        snr = speech_snr(args.voice, args.bed)
        metrics.update(snr)
        gates["speech_coverage"] = snr["covered_speech_frames"] == snr["active_speech_frames"] > 0
        median, p15 = snr["median_snr_db"], snr["p15_snr_db"]
        gates["median_snr"] = median is not None and median >= MIN_MEDIAN_SNR_DB
        gates["p15_snr"] = p15 is not None and p15 >= MIN_P15_SNR_DB

    stems = [check_stem(path, args.expected_dur) for path in args.stem]
    if stems:
        gates["stem_peak"] = all(stem["peak_passed"] for stem in stems)
        if args.expected_dur is not None:
            gates["stem_duration"] = all(stem["duration_passed"] for stem in stems)

    failed = [gate for gate, passed in gates.items() if not passed]
    if args.json:
        print(json.dumps({
            "passed": not failed, **metrics, "gates": gates, "failed_gates": failed, "stems": stems,
        }, indent=2, allow_nan=False))
    else:
        print(f"{'FAIL' if failed else 'PASS'} {args.media_path}")
        for name, passed in gates.items():
            print(f"  {'PASS' if passed else 'FAIL'} {name}")
        for name, value in metrics.items():
            if value is not None:
                print(f"  {name} = {value}")
        for stem in stems:
            print(f"  stem {stem['path']} = {json.dumps(stem)}")
    return int(bool(failed))


def label(text: str, x: str = "12", y: int = 8, size: int = 16) -> str:
    return f"drawtext=text='{text}':fontsize={size}:fontcolor=white:x={x}:y={y}"


def write_output(source: Path, target: Path, *ffmpeg_args: str) -> None:
    if source.resolve() == target.resolve():
        raise UsageError("input and output must be different paths")
    with tempfile.TemporaryDirectory(prefix=".soundcraft-", dir=target.parent) as work:
        output = Path(work) / target.name
        ffmpeg(*ffmpeg_args, str(output))
        if not output.is_file() or not output.stat().st_size:
            raise UsageError("FFmpeg did not produce an output file")
        output.replace(target)


def sheet(args: argparse.Namespace) -> int:
    audio, video = probe(args.media_path, include_video=True)
    pcm = decode(args.media_path, audio)
    frames = len(pcm) // audio.channels
    duration = frames / audio.rate
    del pcm

    width = 1200
    wave_width = min(width, frames)
    bg = "0x121824"
    wave_title = f"Waveform   {duration:.3f} s decoded audio"
    if video is not None:
        offset_ms = (audio.start - video.start) * 1000
        wave_title += f"   |   {video.duration:.3f} s video   |   audio start offset {offset_ms:+.1f} ms"

    graphs = [
        f"[0:{audio.index}]asetpts=N/SR/TB,asplit=2[wave_audio][spectrum_audio]",
        f"[wave_audio]showwavespic=s={wave_width}x154:colors=0x83deee:filter=peak,format=rgb24,"
        f"scale={width}:154:flags=neighbor,"
        f"pad={width}:ih+57:0:32:color={bg},{label(wave_title)},"
        f"{label('0 s', y=189, size=13)},"
        f"{label(f'{duration / 2:.3f} s', x='(w-tw)/2', y=189, size=13)},"
        f"{label(f'{duration:.3f} s', x='w-tw-12', y=189, size=13)},setsar=1[wave]",
        "[spectrum_audio]showspectrumpic=s=1120x256:fscale=log:legend=1:color=intensity:"
        "scale=log:drange=90,format=rgb24,"
        f"scale={width}:-1,pad={width}:ih+32:0:32:color={bg},"
        f"{label('Spectrogram   |   frequency vs decoded audio time')},setsar=1[spectrum]",
    ]
    panels = ["[wave]", "[spectrum]"]
    if video is not None:
        # Sample the center of each of eight equally spaced timeline bins.
        # Clone a trailing frame when sparse or very short footage needs filling.
        graphs.append(
            f"[0:{video.index}]setpts=PTS-STARTPTS-{video.duration / 16:.9f}/TB,"
            f"fps=fps=8/{video.duration:.9f}:start_time=0:round=up,"
            "tpad=stop=8:stop_mode=clone,scale=148:82:force_original_aspect_ratio=decrease,"
            f"setsar=1,pad=150:84:(ow-iw)/2:(oh-ih)/2:color={bg},"
            f"tile=8x1,format=rgb24,pad={width}:ih+58:0:32:color={bg},"
            f"{label('Filmstrip   |   elapsed video time')},"
            + ",".join(label(f"{(index + 0.5) * video.duration / 8:.2f} s", x=str(index * 150 + 12),
                             y=121, size=13) for index in range(8))
            + "[film]"
        )
        panels.insert(0, "[film]")
    graphs.append(f"{''.join(panels)}vstack=inputs={len(panels)}[sheet]")
    write_output(
        args.media_path, args.out, "-filter_complex_threads", "1", "-i", str(args.media_path),
        "-filter_complex", ";".join(graphs), "-map", "[sheet]", "-frames:v", "1",
        "-c:v", "png", "-threads", "1", "-f", "image2", "-update", "1",
    )
    print(args.out)
    return 0


def pad_sidechain(args: argparse.Namespace) -> int:
    audio, _ = probe(args.bed_in)
    encoding = ["-c:a", "pcm_f32le"] if args.bed_out.suffix.lower() == ".wav" else []
    write_output(
        args.bed_in, args.bed_out, "-i", str(args.bed_in), "-map", f"0:{audio.index}",
        "-af", f"apad=pad_dur={args.pad_s:.9f}", *encoding,
    )
    print(args.bed_out)
    return 0


def finite(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def nonnegative(value: str) -> float:
    number = finite(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def positive(value: str) -> float:
    number = nonnegative(value)
    if number == 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    qa = sub.add_parser("check", help="measure a rendered audio mix and apply QA gates")
    qa.add_argument("media_path", type=Path)
    qa.add_argument("--target-lufs", type=finite, default=-14.0)
    qa.add_argument("--lufs-tol", type=nonnegative, default=0.8)
    qa.add_argument("--max-tp", type=finite, default=-0.9)
    qa.add_argument("--min-lra", type=nonnegative, default=3.5)
    qa.add_argument("--max-av-delta-ms", type=nonnegative, default=50.0)
    qa.add_argument("--expected-dur", type=positive)
    qa.add_argument("--max-clipped", type=int, default=3)
    qa.add_argument("--voice", type=Path)
    qa.add_argument("--bed", type=Path)
    qa.add_argument("--stem", type=Path, action="append", default=[])
    qa.add_argument("--check-peak-window", action="store_true")
    qa.add_argument("--json", action="store_true")
    qa.set_defaults(handler=check)

    visual = sub.add_parser("sheet", help="make an annotated waveform and spectrogram PNG")
    visual.add_argument("media_path", type=Path)
    visual.add_argument("--out", type=Path, required=True)
    visual.set_defaults(handler=sheet)

    pad = sub.add_parser("pad-sidechain", help="add a fixed silence tail before sidechain compression")
    pad.add_argument("bed_in", type=Path)
    pad.add_argument("bed_out", type=Path)
    pad.add_argument("--pad-s", type=nonnegative, default=1.0)
    pad.set_defaults(handler=pad_sidechain)

    args = parser.parse_args(argv)
    if args.command == "check":
        if (args.voice is None) != (args.bed is None):
            qa.error("--voice and --bed must be supplied together")
        if args.max_clipped < 0:
            qa.error("--max-clipped must be nonnegative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        for command in ("ffmpeg", "ffprobe"):
            if shutil.which(command) is None:
                raise UsageError(f"{command} was not found on PATH")
        # FFmpeg treats names such as "-" as protocols even when they came
        # from valid CLI path arguments. Feed only absolute local paths.
        for name in ("media_path", "voice", "bed", "bed_in"):
            path = getattr(args, name, None)
            if path is not None:
                setattr(args, name, path.absolute())
        if args.command == "check":
            args.stem = [path.absolute() for path in args.stem]
        return args.handler(args)
    except (UsageError, OSError) as exc:
        print(f"audio_qa: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
