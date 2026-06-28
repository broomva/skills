#!/usr/bin/env python3
"""Pack per-source word-level transcripts into edit/takes_packed.md — the primary
phrase-level reading artifact for the editor.

Phrase boundary rule: start a new phrase when the gap between consecutive words is
>= GAP seconds (default 0.5) OR the speaker changes. See references/edl-format.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

GAP = 0.5


def group_phrases(words: list[dict], gap: float = GAP) -> list[dict]:
    """Pure function: group word dicts into phrases. Importable + unit-tested.

    Each word: {"word", "start", "end", "speaker"(optional)}.
    Returns phrases: [{"start", "end", "speaker", "text"}].
    """
    phrases: list[dict] = []
    cur: list[dict] = []
    for w in words:
        if not cur:
            cur = [w]
            continue
        prev = cur[-1]
        gap_break = float(w["start"]) - float(prev["end"]) >= gap
        spk_break = (w.get("speaker") or None) != (prev.get("speaker") or None)
        if gap_break or spk_break:
            phrases.append(_finish(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        phrases.append(_finish(cur))
    return phrases


def _finish(group: list[dict]) -> dict:
    return {
        "start": float(group[0]["start"]),
        "end": float(group[-1]["end"]),
        "speaker": group[0].get("speaker") or None,
        "text": " ".join(str(w["word"]).strip() for w in group).strip(),
    }


def render_pack(transcript: dict, label: str, gap: float = GAP) -> str:
    words = transcript.get("words", [])
    phrases = group_phrases(words, gap)
    dur = float(transcript.get("duration", phrases[-1]["end"] if phrases else 0.0))
    out = [f"## {label}  (duration: {dur:.1f}s, {len(phrases)} phrases)"]
    for p in phrases:
        spk = p["speaker"] or "S0"
        out.append(f"  [{p['start']:06.2f}-{p['end']:06.2f}] {spk} {p['text']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Pack word-level transcripts to takes_packed.md")
    ap.add_argument("--edit-dir", required=True, help="edit/ dir containing transcripts/")
    ap.add_argument("--gap", type=float, default=GAP, help="silence gap threshold (s)")
    ap.add_argument("-o", "--output", help="output path (default <edit-dir>/takes_packed.md)")
    args = ap.parse_args()

    edit_dir = Path(args.edit_dir)
    tdir = edit_dir / "transcripts"
    if not tdir.is_dir():
        print(f"error: no transcripts dir at {tdir}", flush=True)
        return 1
    files = sorted(tdir.glob("*.json"))
    if not files:
        print(f"error: no transcript JSON files in {tdir}", flush=True)
        return 1

    blocks = []
    for f in files:
        try:
            transcript = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"warning: skipping {f.name}: {e}", flush=True)
            continue
        blocks.append(render_pack(transcript, f.stem, args.gap))

    out_path = Path(args.output) if args.output else edit_dir / "takes_packed.md"
    out_path.write_text("\n\n".join(blocks) + "\n")
    print(str(out_path.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
