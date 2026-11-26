#!/usr/bin/env python3
"""Mutation proofs for video-cut v2 gates (unheard.py + edit_plan.py).

Proves that each critical validation and detection gate is genuinely load-bearing:
  1. Unmutated code catches the defective input / signal.
  2. Mutating the gate threshold causes the defective input / signal to slip through.

Run standalone:
    python3 tests/mutation_proof_v2.py
Or automatically via pytest (`tests/test_mutation_proof_v2.py`).
"""

from __future__ import annotations

import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import edit_plan  # noqa: E402
import unheard  # noqa: E402


def _base_plan() -> dict:
    return {
        "version": 1,
        "canvas": {"width": 1080, "height": 1920, "fps": 30, "safe_area": "9:16-reels"},
        "clips": [
            {
                "id": "c1",
                "source": "/tmp/a.mp4",
                "in_s": 0.0,
                "out_s": 2.0,
                "punch_in": {"scale": 1.25, "anchor_x": 0.5, "anchor_y": 0.5},
            }
        ],
        "audio": {
            "music": {
                "source": "/tmp/m.wav",
                "gain_db": -16.0,
                "duck_db": -10.0,
                "pad_tail_s": 0.75,
            }
        },
        "captions": {
            "enabled": True,
            "safe_zone_check": True,
            "entries": [{"start_s": 0.1, "end_s": 1.0, "text": "Safe", "y_frac": 0.72}],
        },
    }


def prove_pad_tail_gate() -> str:
    """Mutating MIN_DUCK_PAD_TAIL_S to 0.0 breaks protection against sidechaincompress truncation."""
    bad = _base_plan()
    bad["audio"]["music"]["pad_tail_s"] = 0.1
    assert not edit_plan.validate_plan(bad)["valid"], "baseline gate must reject pad_tail_s=0.1"

    orig = edit_plan.MIN_DUCK_PAD_TAIL_S
    try:
        edit_plan.MIN_DUCK_PAD_TAIL_S = 0.0
        assert edit_plan.validate_plan(bad)["valid"], "mutant should have slipped past gate"
    finally:
        edit_plan.MIN_DUCK_PAD_TAIL_S = orig
    return "pad_tail_gate: KILLED"


def prove_punch_in_scale_gate() -> str:
    """Mutating MAX_PUNCH_SCALE breaks protection against excessive punch-in zoom."""
    bad = _base_plan()
    bad["clips"][0]["punch_in"]["scale"] = 2.6
    assert not edit_plan.validate_plan(bad)["valid"], "baseline gate must reject scale=2.6"

    orig = edit_plan.MAX_PUNCH_SCALE
    try:
        edit_plan.MAX_PUNCH_SCALE = 5.0
        assert edit_plan.validate_plan(bad)["valid"], "mutant should have slipped past gate"
    finally:
        edit_plan.MAX_PUNCH_SCALE = orig
    return "punch_in_scale_gate: KILLED"


def prove_caption_safe_area_gate() -> str:
    """Mutating 9:16-reels bottom margin to 0.0 lets UI-occluded captions slip through."""
    bad = _base_plan()
    bad["captions"]["entries"][0]["y_frac"] = 0.90
    assert not edit_plan.validate_plan(bad)["valid"], "baseline gate must reject y_frac=0.90"

    orig = edit_plan.SAFE_AREA_PRESETS["9:16-reels"]["bottom"]
    try:
        edit_plan.SAFE_AREA_PRESETS["9:16-reels"]["bottom"] = 0.0
        assert edit_plan.validate_plan(bad)["valid"], "mutant should have slipped past gate"
    finally:
        edit_plan.SAFE_AREA_PRESETS["9:16-reels"]["bottom"] = orig
    return "caption_safe_area_gate: KILLED"


def _make_probe_wav(path: Path) -> Path:
    sr = 16000
    n = int(sr * 5.0)
    buf = [0.0] * n

    def add(t0: float, t1: float, freq: float, db: float) -> None:
        amp = 32767.0 * (10.0 ** (db / 20.0)) * math.sqrt(2.0)
        for i in range(int(t0 * sr), int(t1 * sr)):
            buf[i] += amp * math.sin(2.0 * math.pi * freq * i / sr)

    add(0.4, 0.65, 250.0, -24.0)  # 0.25s breath (must be ignored)
    add(2.0, 3.0, 420.0, -18.0)   # 1.0s UNHEARD burst (must be caught)

    pcm = [max(-32768, min(32767, int(round(v)))) for v in buf]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{n}h", *pcm))
    return path


def prove_unheard_min_gap_gate() -> str:
    """Lowering min_gap_s from 0.6s to 0.15s causes short 0.25s breaths to false-alarm."""
    with tempfile.TemporaryDirectory() as td:
        wav_path = _make_probe_wav(Path(td) / "probe.wav")
        empty_t = {"words": []}

        base = unheard.detect_unheard(wav_path, empty_t, min_gap_s=unheard.DEFAULT_MIN_GAP_S)
        assert base["unheard_count"] == 1, f"baseline should catch only the 1.0s burst, got {base['unheard_count']}"

        mutated = unheard.detect_unheard(wav_path, empty_t, min_gap_s=0.15)
        assert mutated["unheard_count"] == 2, "mutant should falsely flag the 0.25s breath"
    return "unheard_min_gap_gate: KILLED"


def prove_unheard_adaptive_floor_gate() -> str:
    """Mutating ADAPTIVE_FLOOR_DB to 0.0 blinds the detector to real -18 dBFS speech."""
    with tempfile.TemporaryDirectory() as td:
        wav_path = _make_probe_wav(Path(td) / "probe.wav")
        empty_t = {"words": []}

        base = unheard.detect_unheard(wav_path, empty_t)
        assert base["unheard_count"] == 1, "baseline must detect the 1.0s -18 dBFS burst"

        orig = unheard.ADAPTIVE_FLOOR_DB
        try:
            unheard.ADAPTIVE_FLOOR_DB = 0.0
            mutated = unheard.detect_unheard(wav_path, empty_t)
            assert mutated["unheard_count"] == 0, "mutant should blind detection"
        finally:
            unheard.ADAPTIVE_FLOOR_DB = orig
    return "unheard_adaptive_floor_gate: KILLED"


ALL_PROOFS = [
    prove_pad_tail_gate,
    prove_punch_in_scale_gate,
    prove_caption_safe_area_gate,
    prove_unheard_min_gap_gate,
    prove_unheard_adaptive_floor_gate,
]


def run_all() -> list[str]:
    return [fn() for fn in ALL_PROOFS]


def main() -> int:
    results = run_all()
    for line in results:
        print(f"  ✓ {line}")
    print(f"All {len(results)}/{len(results)} mutation proofs killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
