#!/usr/bin/env python3
"""Render an EDL to a finished video with ffmpeg.

Pipeline (see references/hard-rules.md):
  per-range extract + grade + 30ms fades  (encode pass 1, per segment)
    -> lossless concat (-c copy)          (no encode)
    -> overlays (PTS-shifted) + subtitles LAST in one final pass (encode pass 2)

Subtitles are built on the OUTPUT timeline from cached word transcripts (scripts/edl.py).
All artifacts stay under <edit_dir> (Hard Rule 9).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edl as edl_lib  # noqa: E402


def run(cmd: list[str], cwd: str | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=cwd, stdin=subprocess.DEVNULL)


def ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def has_audio(path: str) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return bool(out)


def probe_resolution(path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=s=x:p=0", path],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    w, h = out.split("x")
    return int(w), int(h)


def extract_segment(seg: dict, src: str, idx: int, out_dir: Path, fade: float,
                    src_has_audio: bool, canvas: tuple[int, int], preview: bool) -> Path:
    """Extract one EDL range, baking in grade + 30ms fades, normalized to the common
    canvas (so a `-c copy` concat across mixed-resolution sources stays valid), and
    always carrying a stereo 48k audio track (real, or silent via anullsrc for a
    source with no audio — keeps the concat uniform).

    Audio is encoded LOSSLESS (pcm_s16le) into an .mkv intermediate, NOT AAC: AAC's
    ~1024-sample encoder priming delay would be baked into every segment and, under a
    `-c copy` concat, accumulate as ~21ms of A/V drift per cut seam. PCM has no priming,
    so the concat is sample-exact; AAC is encoded exactly once in the final pass."""
    out = out_dir / f"seg_{idx:03d}.mkv"
    w, h = canvas
    dur = seg["out_dur"]
    cmd = ["ffmpeg", "-y", "-ss", f"{seg['src_start']:.3f}", "-t", f"{dur:.3f}", "-i", src]
    if not src_has_audio:
        # exact-length silent track (explicit -t, not -shortest, to avoid frame-boundary
        # truncation shortfall at the seam)
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000"]
    vf = []
    if seg["grade"]:
        vf.append(seg["grade"])
    vf += [f"scale={w}:{h}:force_original_aspect_ratio=decrease",
           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2", "setsar=1"]
    cmd += ["-vf", ",".join(vf)]
    if src_has_audio:
        d = max(0.0, dur - fade)
        cmd += ["-af", f"afade=t=in:st=0:d={fade},afade=t=out:st={d:.3f}:d={fade}",
                "-map", "0:v:0", "-map", "0:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    crf = "28" if preview else "18"
    preset = "ultrafast" if preview else "medium"
    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
            "-fps_mode", "cfr", "-r", "30", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
            str(out)]
    run(cmd)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Render an EDL to a finished video")
    ap.add_argument("edl", help="path to edl.json")
    ap.add_argument("-o", "--output", help="output path (default from EDL or final.mp4)")
    ap.add_argument("--preview", action="store_true", help="720p ultrafast preview")
    args = ap.parse_args()

    edl_path = Path(args.edl).resolve()
    edit_dir = edl_path.parent
    videos_dir = edit_dir.parent
    clips_dir = edit_dir / "clips_graded"
    clips_dir.mkdir(parents=True, exist_ok=True)

    try:
        edl = edl_lib.load_edl(edl_path)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: invalid EDL: {e}", file=sys.stderr)
        return 1

    # source durations + per-source audio presence + common canvas.
    # Relative source paths resolve against the videos dir (parent of edit/), matching
    # how overlay paths are resolved later — so the EDL is portable, not CWD-dependent.
    src_paths = {
        label: (p if Path(p).is_absolute() else str((videos_dir / p).resolve()))
        for label, p in edl["sources"].items()
    }
    for label, p in src_paths.items():
        if not Path(p).exists():
            print(f"error: source {label!r} not found: {p}", file=sys.stderr)
            return 1
    source_durations = {label: ffprobe_duration(p) for label, p in src_paths.items()}
    src_audio = {label: has_audio(p) for label, p in src_paths.items()}
    resolutions = [probe_resolution(p) for p in src_paths.values()]
    cw = max(w for w, _ in resolutions)
    ch = max(h for _, h in resolutions)
    canvas = (cw - cw % 2, ch - ch % 2)  # libx264 requires even dimensions
    if not all(src_audio.values()):
        print("warning: a source has no audio; a silent track is synthesized for "
              "those segments to keep the concat uniform", file=sys.stderr)

    fade = float(edl["fade_ms"]) / 1000.0

    # Drop degenerate (near-zero) ranges — e.g. a range entirely past a source edge —
    # from the EDL up front, so render AND build_srt share one consistent timeline.
    MIN_SEG = 0.05
    segs_all = edl_lib.output_segments(edl, source_durations)
    keep_idx = [i for i, s in enumerate(segs_all) if s["out_dur"] >= MIN_SEG]
    if len(keep_idx) < len(segs_all):
        dropped = [i for i in range(len(segs_all)) if i not in keep_idx]
        print(f"warning: dropped near-zero-duration range(s) {dropped} "
              "(clamped to < 50ms against source bounds)", file=sys.stderr)
        edl["ranges"] = [edl["ranges"][i] for i in keep_idx]
    if not edl["ranges"]:
        print("error: no renderable ranges after dropping near-zero segments",
              file=sys.stderr)
        return 1
    segs = edl_lib.output_segments(edl, source_durations)

    # pass 1: per-segment extract + grade + fades, normalized to the canvas
    seg_files = []
    for i, seg in enumerate(segs):
        seg_files.append(
            extract_segment(seg, src_paths[seg["label"]], i, clips_dir, fade,
                            src_audio[seg["label"]], canvas, args.preview)
        )

    # concat (lossless): .mkv with h264 (copy) + pcm_s16le (copy). PCM concatenates
    # sample-exact, so there is NO per-seam audio drift; AAC is encoded once below.
    concat_txt = edit_dir / "concat.txt"
    concat_txt.write_text("".join(f"file '{f.resolve()}'\n" for f in seg_files))
    concatenated = edit_dir / "concatenated.mkv"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
         "-c", "copy", str(concatenated)])

    # subtitles: build on output timeline from cached transcripts (independent of audio)
    sub = edl.get("subtitles", {"mode": "none"})
    want_subs = sub.get("mode") == "burn"
    srt_rel = None
    if want_subs:
        transcripts = {}
        missing = []
        for label, p in src_paths.items():
            tj = edit_dir / "transcripts" / f"{Path(p).stem}.json"
            if tj.exists():
                transcripts[label] = json.loads(tj.read_text())
            else:
                missing.append(tj.name)
        if missing:
            print(f"warning: no transcript for {missing}; those sources contribute "
                  "no captions (e.g. silent B-roll)", file=sys.stderr)
        if not transcripts:
            print("warning: no transcripts found at all; skipping subtitles",
                  file=sys.stderr)
            want_subs = False
        else:
            srt = edl_lib.build_srt(edl, transcripts, source_durations)
            (edit_dir / "master.srt").write_text(srt)
            srt_rel = "master.srt"

    overlays = edl.get("overlays", [])
    out_path = Path(args.output) if args.output else (
        edit_dir / ("preview.mp4" if args.preview else Path(edl["output"]).name)
    )

    # final pass: overlays then subtitles LAST (single encode); else copy/scale
    style_force = None
    if want_subs:
        style_name = sub.get("style", "bold-overlay")
        style_force = edl_lib.SUBTITLE_STYLES.get(
            style_name, edl_lib.SUBTITLE_STYLES["bold-overlay"])[0]

    if not overlays and not want_subs and not args.preview:
        # video already h264 (copy through, lossless); encode the PCM track to AAC once
        run(["ffmpeg", "-y", "-i", str(concatenated), "-c:v", "copy",
             "-c:a", "aac", "-ar", "48000", "-ac", "2",
             "-movflags", "+faststart", str(out_path)])
        print(str(out_path.resolve()))
        return 0

    # build filter_complex
    inputs = ["-i", str(concatenated)]
    parts = []
    base = "[0:v]"
    for j, ov in enumerate(overlays):
        ov_file = ov["file"]
        if not Path(ov_file).is_absolute():
            ov_file = str((videos_dir / ov_file).resolve())
        inputs += ["-i", ov_file]
        start = float(ov.get("start_in_output", 0.0))
        dur = float(ov.get("duration", 0.0))
        end = start + dur if dur > 0 else start + 10**6
        parts.append(f"[{j + 1}:v]setpts=PTS-STARTPTS+{start}/TB[ov{j}]")
        parts.append(
            f"{base}[ov{j}]overlay=(W-w)/2:(H-h)/2:"
            f"enable='between(t,{start},{end})'[v{j}]"
        )
        base = f"[v{j}]"
    if args.preview:
        parts.append(f"{base}scale=-2:720[vs]")
        base = "[vs]"
    if want_subs:
        parts.append(f"{base}subtitles={srt_rel}:force_style='{style_force}'[vout]")
        vmap = "[vout]"
    else:
        # need a terminal label; if no filters applied to base yet, alias it
        if base == "[0:v]":
            parts.append("[0:v]null[vout]")
            vmap = "[vout]"
        else:
            vmap = base

    crf = "28" if args.preview else "18"
    preset = "ultrafast" if args.preview else "medium"
    # cwd=edit_dir keeps the `subtitles=master.srt` reference a clean relative path
    # (absolute SRT paths need lavfi ':' escaping); the OUTPUT is passed absolute so
    # an explicit -o lands where the user asked, not as a basename inside edit/.
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts),
           "-map", vmap, "-map", "0:a?", "-c:v", "libx264", "-preset", preset,
           "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", str(out_path.resolve())]
    run(cmd, cwd=str(edit_dir))
    print(str(out_path.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
