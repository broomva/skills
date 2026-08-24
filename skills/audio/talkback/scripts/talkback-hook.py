#!/usr/bin/env python3
"""talkback Stop hook — speak a short readback when a turn ends.

OFF by default. It speaks only while the flag file ~/.talkback/hook-enabled
exists, so an unconfigured machine stays silent; and it always exits 0, so it
can never block a turn from completing.

What it says, in order of preference:
  1. an explicit `<!-- talkback: ... -->` marker the agent left in its message
  2. otherwise, the opening sentences of the final message, up to a char cap

It never uses a metered backend. An automatic per-turn readback is exactly the
thing that would silently drain a quota, so this is hardwired to `say`.
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

MARKER_RE = re.compile(r"<!--\s*talkback:\s*(.+?)\s*-->", re.S | re.I)


def toggle(argv: list[str]) -> int | None:
    if not argv:
        return None
    cmd = argv[0]
    if cmd == "--on":
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        FLAG.touch()
        print("talkback stop-hook: ON")
        return 0
    if cmd == "--off":
        FLAG.unlink(missing_ok=True)
        print("talkback stop-hook: OFF")
        return 0
    if cmd == "--status":
        print(f"talkback stop-hook: {'ON' if FLAG.exists() else 'OFF'}")
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


def condense(text: str) -> str:
    m = MARKER_RE.search(text)
    if m:
        return m.group(1).strip()
    body = MARKER_RE.sub("", text).strip()
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

    spoken = condense(text)
    if not spoken.strip():
        return 0

    # Detach so the turn is never held open for the length of the audio.
    try:
        subprocess.Popen(
            [sys.executable, str(HERE / "talkback.py"), "-b", "say", "--", spoken],
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
