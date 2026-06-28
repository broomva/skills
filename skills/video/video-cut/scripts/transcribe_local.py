#!/usr/bin/env python3
"""Local-first word-level transcription for the video-cut skill.

Produces a word-level transcript JSON for a source video/audio file using
faster_whisper. Runs entirely on-device — NO cloud APIs.

Usage:
    python3 transcribe_local.py <video> [--model base] [--edit-dir DIR] \
        [--force] [--diarize] [--language LANG]

Output:
    <edit-dir>/transcripts/<stem>.json   (default edit-dir = <dir-of-video>/edit)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_CHUNK = 1024 * 1024  # 1 MiB streaming chunk for hashing


def eprint(*args: object) -> None:
    """Print to stderr."""
    print(*args, file=sys.stderr)


def sha256_file(path: Path) -> str:
    """Return the sha256 hex digest of a file, streamed in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def cached_transcript_valid(out_path: Path, source_hash: str,
                            model_size: str, language) -> bool:
    """True iff a cached transcript matches the source bytes AND the requested
    transcription settings (model + language). A different --model or --language
    must invalidate the cache, else a second run silently returns stale text for
    a different request."""
    if not out_path.exists():
        return False
    try:
        with out_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return False
    return (
        data.get("source_hash") == source_hash
        and data.get("model") == f"faster-whisper:{model_size}"
        and data.get("requested_language") == language
    )


def extract_audio(video: Path, wav_out: Path) -> None:
    """Extract 16kHz mono wav from the source via ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-vn",
        str(wav_out),
    ]
    subprocess.run(cmd, check=True)


def load_model(model_size: str):
    """Load a WhisperModel, falling back from device='auto' to cpu on failure."""
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(model_size, device="auto", compute_type="int8")
    except Exception:  # noqa: BLE001 - any device/compute failure → cpu fallback
        return WhisperModel(model_size, device="cpu", compute_type="int8")


def _round_or_none(value, ndigits: int = 3):
    """Round value to ndigits, or return None if value is None."""
    if value is None:
        return None
    return round(value, ndigits)


def build_payload(video: Path, source_hash: str, model_size: str, language,
                  segments, info) -> dict:
    """Assemble the output JSON payload from faster_whisper results."""
    words: list[dict] = []
    seg_out: list[dict] = []

    for seg in segments:  # segments is a generator — iterate once
        seg_out.append(
            {
                "start": _round_or_none(seg.start),
                "end": _round_or_none(seg.end),
                "text": (seg.text or "").strip(),
            }
        )
        for w in seg.words or []:
            # Skip words with missing timing — they are unusable for cutting.
            if w.start is None or w.end is None:
                continue
            words.append(
                {
                    "word": w.word,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "prob": _round_or_none(w.probability),
                    "speaker": None,
                }
            )

    return {
        "source": str(video),
        "source_hash": source_hash,
        "duration": float(info.duration),
        "language": info.language,
        "requested_language": language,
        "model": f"faster-whisper:{model_size}",
        "words": words,
        "segments": seg_out,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local-first word-level transcription via faster_whisper.",
    )
    parser.add_argument("video", help="Path to a source video/audio file.")
    parser.add_argument(
        "--model",
        default="base",
        help="faster_whisper model size (default: base).",
    )
    parser.add_argument(
        "--edit-dir",
        default=None,
        help="Output dir root. Default: <dir-of-video>/edit.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-transcribe even if a valid cached transcript exists.",
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="NO-OP in v0 — accepted but speaker stays null.",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Optional language hint (default: auto-detect).",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        eprint(f"error: source file not found: {video}")
        return 1

    edit_dir = (
        Path(args.edit_dir).expanduser().resolve()
        if args.edit_dir
        else video.parent / "edit"
    )
    transcripts_dir = edit_dir / "transcripts"
    out_path = transcripts_dir / f"{video.stem}.json"

    # 1. Source hash.
    source_hash = sha256_file(video)

    # 2. Cache short-circuit.
    if not args.force and cached_transcript_valid(
        out_path, source_hash, args.model, args.language
    ):
        print(str(out_path))
        return 0

    # Import guard for faster_whisper before doing expensive ffmpeg work.
    import importlib.util

    if importlib.util.find_spec("faster_whisper") is None:
        eprint(
            "error: faster_whisper is not available. "
            "Install it with: pip install 'faster-whisper>=1.1.0'"
        )
        return 1

    # 3. Extract audio to a temp wav, transcribe, clean up.
    tmp_wav: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(suffix=".wav")
        # Close the descriptor — ffmpeg writes the file by path.
        import os

        os.close(fd)
        tmp_wav = Path(tmp_name)

        try:
            extract_audio(video, tmp_wav)
        except FileNotFoundError:
            eprint(
                "error: ffmpeg not found on PATH. Install ffmpeg "
                "(brew install ffmpeg / apt install ffmpeg) and retry."
            )
            return 1
        except subprocess.CalledProcessError as exc:
            eprint(f"error: ffmpeg failed to extract audio (exit {exc.returncode}).")
            return 1

        # 4. Load model with device fallback.
        model = load_model(args.model)

        # 5. Transcribe — segments is a generator.
        segments, info = model.transcribe(
            str(tmp_wav),
            word_timestamps=True,
            vad_filter=True,
            language=args.language,
        )

        # 6. Build payload.
        payload = build_payload(video, source_hash, args.model, args.language,
                                segments, info)

        # 7. Write output.
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

        print(str(out_path))
        return 0
    finally:
        if tmp_wav is not None and tmp_wav.exists():
            try:
                tmp_wav.unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
