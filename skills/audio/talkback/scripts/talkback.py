#!/usr/bin/env python3
"""talkback — speak an explanation out loud, from any project directory.

Tiered TTS with a pluggable backend:

    say         macOS native. Free, unlimited, instant. The default.
    elevenlabs  Best quality. Opt-in per call, quota-guarded.
    omnivoice   Local OmniVoice Studio. Unlimited + private. Requires the
                backend up on $OMNIVOICE_API_URL (default localhost:3900).

Every utterance is saved to disk so it can be replayed later.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HOME = Path.home()
STATE_DIR = Path(os.environ.get("TALKBACK_HOME", HOME / ".talkback"))
AUDIO_DIR = STATE_DIR / "audio"
LEDGER = STATE_DIR / "ledger.jsonl"
ENABLED_FLAG = STATE_DIR / "hook-enabled"

ELEVEN_API = "https://api.elevenlabs.io"
ELEVEN_DEFAULT_VOICE = "SAz9YHcvj6GT2YYXdXww"  # River — relaxed, neutral, informative
ELEVEN_DEFAULT_MODEL = "eleven_turbo_v2_5"
SAY_DEFAULT_VOICE = os.environ.get("TALKBACK_SAY_VOICE", "Samantha")
OMNIVOICE_URL = os.environ.get("OMNIVOICE_API_URL", "http://localhost:3900")

# Keep a floor of characters in reserve so a quota is never fully drained by
# one long explanation; the next short one should still get through.
ELEVEN_RESERVE_CHARS = 250


# --------------------------------------------------------------------------
# text preparation
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```.*?```", re.S)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_PATH_RE = re.compile(r"(?<![\w/])(?:[\w.-]+/){1,}[\w.-]+")
_WS_RE = re.compile(r"\s+")

# Emphasis is stripped only where the marker actually delimits a span. A bare
# underscore inside an identifier (resolve_backend) is not emphasis, and eating
# it turns a symbol the listener could search for into one they cannot.
_EMPH_PATTERNS = [
    re.compile(r"\*\*(.+?)\*\*", re.S),
    re.compile(r"__(.+?)__", re.S),
    re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", re.S),
    re.compile(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])", re.S),
]

_ENDS_SENTENCE = tuple(".!?:;,")


def speakify(text: str, keep_paths: bool = False) -> str:
    """Turn markdown-ish agent prose into something worth hearing.

    Code fences, URLs and deep paths read as noise when spoken, so they collapse
    to a short placeholder. Structural markers (headings, bullets) become
    sentence breaks, otherwise every list runs into the next line as one breath.
    """
    t = _FENCE_RE.sub(" (code omitted) ", text)
    t = _MD_LINK_RE.sub(r"\1", t)
    t = _BARE_URL_RE.sub(" (link) ", t)
    t = _INLINE_CODE_RE.sub(r"\1", t)

    lines = []
    for line in t.splitlines():
        line = _HEADING_RE.sub("", line)
        line = _BULLET_RE.sub("", line)
        line = line.strip()
        if not line:
            continue
        if not line.endswith(_ENDS_SENTENCE):
            line += "."
        lines.append(line)
    t = " ".join(lines)

    for pat in _EMPH_PATTERNS:
        t = pat.sub(r"\1", t)

    if not keep_paths:
        t = _PATH_RE.sub(lambda m: m.group(0).rsplit("/", 1)[-1], t)
    t = t.replace("\u2014", ", ").replace("\u2013", ", ")
    t = _WS_RE.sub(" ", t).strip()
    return t


def slugify(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (s[:n] or "utterance").strip("-")


# --------------------------------------------------------------------------
# credentials + quota
# --------------------------------------------------------------------------

def eleven_key() -> str | None:
    """Resolve the ElevenLabs key: env first, then the CLI's stored key."""
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if k:
        return k
    for p in (HOME / ".elevenlabs" / "api_key",):
        if p.is_file():
            k = p.read_text().strip()
            if k:
                return k
    env_local = HOME / "broomva" / ".env.local"
    if env_local.is_file():
        for line in env_local.read_text().splitlines():
            if "ELEVENLABS_API_KEY" in line and "=" in line:
                return line.split("=", 1)[1].strip().strip("\"'")
    return None


def _api_get(path: str, key: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        ELEVEN_API + path, headers={"xi-api-key": key, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def eleven_quota(key: str) -> dict | None:
    """Return {used, limit, remaining, tier} or None if unreachable."""
    try:
        d = _api_get("/v1/user/subscription", key)
    except Exception:
        return None
    used = int(d.get("character_count") or 0)
    limit = int(d.get("character_limit") or 0)
    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "tier": d.get("tier", "unknown"),
        "resets_unix": d.get("next_character_count_reset_unix"),
    }


# --------------------------------------------------------------------------
# backends — each returns a path to the audio it produced
# --------------------------------------------------------------------------

def _to_mp3(src: Path, dest: Path) -> Path:
    """Normalise to mp3 when ffmpeg is around, so saved audio is portable."""
    if not shutil.which("ffmpeg"):
        return src
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), str(dest)],
            check=True,
        )
        src.unlink(missing_ok=True)
        return dest
    except subprocess.CalledProcessError:
        return src


def backend_say(text: str, out_base: Path, voice: str) -> Path:
    if not shutil.which("say"):
        raise RuntimeError("`say` is unavailable (macOS only)")
    aiff = out_base.with_suffix(".aiff")
    cmd = ["say", "-o", str(aiff)]
    if voice:
        cmd += ["-v", voice]
    cmd += ["--", text]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # An unavailable named voice is the common cause; retry with the default.
        proc = subprocess.run(
            ["say", "-o", str(aiff), "--", text], capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(f"say failed: {proc.stderr.strip()}")
    return _to_mp3(aiff, out_base.with_suffix(".mp3"))


def backend_elevenlabs(text: str, out_base: Path, voice: str, model: str) -> Path:
    key = eleven_key()
    if not key:
        raise RuntimeError(
            "no ElevenLabs key — run `elevenlabs auth login` or set ELEVENLABS_API_KEY"
        )
    payload = json.dumps({"text": text, "model_id": model}).encode()
    url = f"{ELEVEN_API}/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"ElevenLabs HTTP {e.code}: {detail}")
    mp3 = out_base.with_suffix(".mp3")
    mp3.write_bytes(audio)
    return mp3


def omnivoice_up() -> bool:
    try:
        urllib.request.urlopen(OMNIVOICE_URL + "/health", timeout=3)
        return True
    except Exception:
        return False


def backend_omnivoice(text: str, out_base: Path, profile: str | None) -> Path:
    """NOTE: unverified — the local backend was down when this shipped."""
    body: dict = {"text": text}
    if profile:
        body["profile_id"] = profile
    req = urllib.request.Request(
        OMNIVOICE_URL + "/api/tts",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
    # The server may hand back raw audio or base64 wrapped in JSON.
    if raw[:1] in (b"{", b"["):
        import base64

        d = json.loads(raw.decode())
        b64 = d.get("audio") or d.get("audio_base64") or d.get("data")
        if not b64:
            raise RuntimeError(f"omnivoice: unexpected response keys {list(d)[:6]}")
        raw = base64.b64decode(b64)
    wav = out_base.with_suffix(".wav")
    wav.write_bytes(raw)
    return _to_mp3(wav, out_base.with_suffix(".mp3"))


# --------------------------------------------------------------------------
# playback + ledger
# --------------------------------------------------------------------------

def play(path: Path) -> None:
    player = shutil.which("afplay") or shutil.which("ffplay")
    if not player:
        print(f"[talkback] no player found; audio at {path}", file=sys.stderr)
        return
    cmd = [player, str(path)]
    if player.endswith("ffplay"):
        cmd = [player, "-autoexit", "-nodisp", "-loglevel", "quiet", str(path)]
    subprocess.run(cmd, check=False)


def record(entry: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry) + "\n")


# --------------------------------------------------------------------------

def resolve_backend(requested: str, n_chars: int, strict: bool) -> tuple[str, str]:
    """Return (backend, note). Falls back to `say` rather than failing loudly."""
    if requested == "say":
        return "say", ""
    if requested == "omnivoice":
        if omnivoice_up():
            return "omnivoice", ""
        if strict:
            raise RuntimeError(f"omnivoice backend unreachable at {OMNIVOICE_URL}")
        return "say", f"omnivoice down at {OMNIVOICE_URL} — fell back to say"
    if requested == "elevenlabs":
        key = eleven_key()
        if not key:
            if strict:
                raise RuntimeError("no ElevenLabs key")
            return "say", "no ElevenLabs key — fell back to say"
        q = eleven_quota(key)
        if q is None:
            if strict:
                raise RuntimeError("could not read ElevenLabs quota")
            return "say", "ElevenLabs quota unreadable — fell back to say"
        if q["remaining"] - n_chars < ELEVEN_RESERVE_CHARS:
            msg = (
                f"ElevenLabs quota too low ({q['remaining']}/{q['limit']} left, "
                f"need {n_chars}) — fell back to say"
            )
            if strict:
                raise RuntimeError(msg.replace(" — fell back to say", ""))
            return "say", msg
        return "elevenlabs", ""
    return "say", ""


def main() -> int:
    p = argparse.ArgumentParser(
        prog="talkback", description="Speak an explanation out loud."
    )
    p.add_argument("text", nargs="*", help="text to speak (or pipe via stdin)")
    p.add_argument(
        "-b", "--backend", default=os.environ.get("TALKBACK_BACKEND", "say"),
        choices=["say", "elevenlabs", "omnivoice"],
        help="TTS backend (default: say)",
    )
    p.add_argument("--good", action="store_true",
                   help="shorthand for --backend elevenlabs")
    p.add_argument("-v", "--voice", default=None,
                   help="backend voice: a `say` voice name, or an ElevenLabs voice id")
    p.add_argument("--model", default=ELEVEN_DEFAULT_MODEL, help="ElevenLabs model id")
    p.add_argument("--out-dir", default=None, help=f"where audio lands (default {AUDIO_DIR})")
    p.add_argument("--no-save", action="store_true", help="discard the audio after playing")
    p.add_argument("--no-play", action="store_true", help="synthesise without playing")
    p.add_argument("--strict", action="store_true",
                   help="fail instead of silently falling back to say")
    p.add_argument("--keep-paths", action="store_true",
                   help="read full file paths aloud instead of just the basename")
    p.add_argument("--quota", action="store_true", help="report ElevenLabs quota and exit")
    p.add_argument("--voices", action="store_true", help="list available voices and exit")
    p.add_argument("--dry-run", action="store_true",
                   help="show the spoken text and chosen backend, synthesise nothing")
    a = p.parse_args()

    if a.quota:
        key = eleven_key()
        if not key:
            print("no ElevenLabs key found")
            return 1
        q = eleven_quota(key)
        if not q:
            print("could not reach ElevenLabs")
            return 1
        reset = ""
        if q.get("resets_unix"):
            reset = " · resets " + datetime.fromtimestamp(q["resets_unix"]).strftime("%Y-%m-%d")
        print(f"ElevenLabs [{q['tier']}] {q['used']}/{q['limit']} used · "
              f"{q['remaining']} remaining{reset}")
        return 0

    if a.voices:
        print("# macOS `say` voices")
        subprocess.run(["say", "-v", "?"], check=False)
        key = eleven_key()
        if key:
            try:
                d = _api_get("/v1/voices", key)
                print("\n# ElevenLabs voices")
                for v in d.get("voices", []):
                    print(f"{v['voice_id']}  {v['name']}")
            except Exception as e:
                print(f"(ElevenLabs voice list unavailable: {e})")
        return 0

    raw = " ".join(a.text).strip()
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
    if not raw:
        p.error("no text given (pass as arguments or pipe via stdin)")

    text = speakify(raw, keep_paths=a.keep_paths)
    if not text:
        print("[talkback] nothing speakable in that input", file=sys.stderr)
        return 1

    requested = "elevenlabs" if a.good else a.backend
    try:
        backend, note = resolve_backend(requested, len(text), a.strict)
    except RuntimeError as e:
        print(f"[talkback] {e}", file=sys.stderr)
        return 1
    if note:
        print(f"[talkback] {note}", file=sys.stderr)

    if a.dry_run:
        print(f"[talkback] backend={backend} chars={len(text)}")
        print(text)
        return 0

    out_dir = Path(a.out_dir) if a.out_dir else AUDIO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_base = out_dir / f"{stamp}-{slugify(text)}"

    try:
        if backend == "elevenlabs":
            voice = a.voice or os.environ.get("TALKBACK_ELEVEN_VOICE", ELEVEN_DEFAULT_VOICE)
            path = backend_elevenlabs(text, out_base, voice, a.model)
        elif backend == "omnivoice":
            path = backend_omnivoice(text, out_base, a.voice)
        else:
            path = backend_say(text, out_base, a.voice or SAY_DEFAULT_VOICE)
    except Exception as e:
        print(f"[talkback] {backend} failed: {e}", file=sys.stderr)
        if backend != "say" and not a.strict:
            print("[talkback] retrying with say", file=sys.stderr)
            try:
                path = backend_say(text, out_base, SAY_DEFAULT_VOICE)
                backend = "say"
            except Exception as e2:
                print(f"[talkback] say also failed: {e2}", file=sys.stderr)
                return 1
        else:
            return 1

    if not a.no_play:
        play(path)

    record({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "backend": backend,
        "chars": len(text),
        "audio": str(path) if not a.no_save else None,
        "cwd": os.getcwd(),
    })

    if a.no_save:
        path.unlink(missing_ok=True)
    else:
        print(f"[talkback] {backend} · {len(text)} chars · {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
