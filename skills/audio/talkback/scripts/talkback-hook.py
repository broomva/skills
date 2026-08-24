#!/usr/bin/env python3
"""talkback Stop hook — speak a short readback when a turn ends.

OFF by default. It speaks only while the flag file ~/.talkback/hook-enabled
exists, so an unconfigured machine stays silent; and it always exits 0, so it
can never block a turn from completing.

Two modes, stored as the content of the flag file:

  marker  (default)  speak ONLY when the agent deliberately left a
                     `<!-- talkback: ... -->` marker. Silent otherwise, so a
                     one-line "done" never becomes audio.
  always             speak on every turn, falling back to the opening sentences
                     of the message when there is no marker. Short turns below
                     MIN_CHARS stay silent even here.

It defaults to the free backend even when a metered one is affordable. A
readback fires on every turn, unattended, for audio nobody asked for — on a
130k-character plan a couple of busy days would still eat a third of the month.
Set TALKBACK_HOOK_BACKEND=elevenlabs to override deliberately.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("TALKBACK_HOME", Path.home() / ".talkback"))
FLAG = STATE_DIR / "hook-enabled"
CAP = int(os.environ.get("TALKBACK_HOOK_CHARS", "320"))
HOOK_BACKEND = os.environ.get("TALKBACK_HOOK_BACKEND", "say")
MODES = ("marker", "always")
DEFAULT_MODE = "marker"
# In `always` mode, a turn shorter than this is an acknowledgement, not a
# report. Narrating it costs more attention than it returns.
MIN_CHARS = int(os.environ.get("TALKBACK_HOOK_MIN_CHARS", "80"))

MARKER_RE = re.compile(r"<!--\s*talkback:\s*(.+?)\s*-->", re.S | re.I)


def current_mode() -> str:
    """Mode lives in the flag file's body; env wins; empty file = default."""
    env = os.environ.get("TALKBACK_HOOK_MODE", "").strip().lower()
    if env in MODES:
        return env
    try:
        body = FLAG.read_text().strip().lower()
    except OSError:
        return DEFAULT_MODE
    return body if body in MODES else DEFAULT_MODE


def toggle(argv: list[str]) -> int | None:
    if not argv:
        return None
    cmd = argv[0]
    if cmd == "--on":
        mode = (argv[1].strip().lower() if len(argv) > 1 else DEFAULT_MODE)
        if mode not in MODES:
            print(f"unknown mode {mode!r} — expected one of {', '.join(MODES)}")
            return 2
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        FLAG.write_text(mode + "\n")
        print(f"talkback stop-hook: ON (mode={mode})")
        if mode == "marker":
            print("  speaks only on turns carrying a <!-- talkback: ... --> marker")
        else:
            print(f"  speaks on every turn over {MIN_CHARS} chars")
        return 0
    if cmd == "--off":
        FLAG.unlink(missing_ok=True)
        print("talkback stop-hook: OFF")
        return 0
    if cmd == "--status":
        if not FLAG.exists():
            print("talkback stop-hook: OFF")
        else:
            print(f"talkback stop-hook: ON (mode={current_mode()}, backend={HOOK_BACKEND})")
        return 0
    return None


def last_assistant_text(transcript: Path) -> str:
    """Pull the final assistant prose out of a Claude Code JSONL transcript."""
    text = ""
    try:
        with transcript.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("type") != "assistant":
                    continue
                content = (e.get("message") or {}).get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    joined = "\n".join(p for p in parts if p.strip())
                    if joined.strip():
                        text = joined
    except OSError:
        return ""
    return text


def condense(text: str, mode: str = DEFAULT_MODE) -> str | None:
    """Return what to speak, or None when this turn should stay silent."""
    m = MARKER_RE.search(text)
    if m:
        return m.group(1).strip() or None
    if mode == "marker":
        return None  # no marker, no audio — the whole point of this mode
    body = MARKER_RE.sub("", text).strip()
    if len(body) < MIN_CHARS:
        return None
    if len(body) <= CAP:
        return body
    cut = body[:CAP]
    for sep in (". ", "! ", "? "):
        i = cut.rfind(sep)
        if i > CAP // 3:
            return cut[: i + 1]
    return cut.rsplit(" ", 1)[0] + "..."


def main() -> int:
    rc = toggle(sys.argv[1:])
    if rc is not None:
        return rc

    if not FLAG.exists():
        return 0  # disabled: stay silent, leave no trace

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tp = payload.get("transcript_path")
    if not tp:
        return 0
    text = last_assistant_text(Path(tp).expanduser())
    if not text.strip():
        return 0

    spoken = condense(text, current_mode())
    if not spoken or not spoken.strip():
        return 0

    # Detach so the turn is never held open for the length of the audio.
    try:
        subprocess.Popen(
            [sys.executable, str(HERE / "talkback.py"), "-b", HOOK_BACKEND, "--", spoken],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
