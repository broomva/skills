#!/usr/bin/env python3
"""Motion arithmetic for code-first animation (stdlib only).

Every number a motion prompt needs, computed rather than estimated:

  beats       beat frames on a grid, each rounded from exact time (drift-free)
  damping     damping ratio from stiffness/damping/mass, or the damping for a ratio
  frames      loop frame range, phase formula, and whether a music loop closes
  ms          milliseconds to frames at a frame rate
  hold        minimum on-screen hold for text (0.3 s per word + 0.5 s)
  gif-delays  per-frame GIF delays (centiseconds) that keep the exact duration
  gif-check   read an exported GIF and report its real frame delays and duration

Each subcommand prints JSON. All functions are importable and pure.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

X_GIF_MAX_FRAMES = 350


def round_half_up(x: float) -> int:
    """Round .5 away from zero for positive x (Python's round() is banker's)."""
    return math.floor(x + 0.5)


def frames_per_beat(fps: float, bpm: float) -> float:
    _positive(fps=fps, bpm=bpm)
    return fps * 60.0 / bpm


def beat_frames(fps: float, bpm: float, count: int, offset: float = 0.0) -> list[int]:
    """Frame of beat n = round(offset + n * fps * 60 / bpm), computed per beat.

    Adding a rounded frames-per-beat again and again accumulates the rounding
    error; computing each beat from exact time keeps every beat within half a
    frame of the music.
    """
    fpb = frames_per_beat(fps, bpm)
    if count < 0:
        raise ValueError("count must be >= 0")
    return [round_half_up(offset + n * fpb) for n in range(count)]


def naive_beat_frames(fps: float, bpm: float, count: int, offset: float = 0.0) -> list[int]:
    """The drifting method: one rounded step, added repeatedly."""
    step = round_half_up(frames_per_beat(fps, bpm))
    return [round_half_up(offset) + n * step for n in range(count)]


def damping_ratio(stiffness: float, damping: float, mass: float = 1.0) -> float:
    """zeta = c / (2 sqrt(k m)). Same formula for react-spring tension/friction."""
    if stiffness <= 0 or mass <= 0:
        raise ValueError("stiffness and mass must be positive")
    return damping / (2.0 * math.sqrt(stiffness * mass))


def damping_for_ratio(zeta: float, stiffness: float, mass: float = 1.0) -> float:
    if stiffness <= 0 or mass <= 0:
        raise ValueError("stiffness and mass must be positive")
    return zeta * 2.0 * math.sqrt(stiffness * mass)


def classify_zeta(zeta: float) -> str:
    if zeta >= 1.0:
        return "no bounce"
    if zeta >= 0.85:
        return "barely bounces"
    if zeta >= 0.7:
        return "premium"
    if zeta >= 0.4:
        return "playful"
    if zeta >= 0.3:
        return "bouncy"
    return "cartoon"


def _positive(**kw: float | None) -> None:
    for name, v in kw.items():
        if v is not None and not (math.isfinite(v) and v > 0):
            raise ValueError(f"{name} must be a finite positive number, got {v}")


def loop_frames(seconds: float, fps: float, bpm: float | None = None) -> dict:
    """N frames, render 0..N-1 (frame N is frame 0 again), and music closure."""
    _positive(seconds=seconds, fps=fps, bpm=bpm)
    exact = seconds * fps
    n = round_half_up(exact)
    if n < 1:
        raise ValueError(f"{seconds} s at {fps} fps rounds to zero frames")
    out = {
        "frames": n,
        "render_range": [0, n - 1],
        "phase": f"phase = frame / {n}",
        "whole_frames": abs(exact - n) < 1e-9,
    }
    if bpm:
        beats = seconds * bpm / 60.0
        out["beats_per_loop"] = beats
        out["music_loop_closes"] = abs(beats - round(beats)) < 1e-9
    return out


def ms_to_frames(ms: float, fps: float) -> int:
    _positive(fps=fps)
    if not math.isfinite(ms) or ms < 0:
        raise ValueError("ms must be a finite non-negative number")
    return round_half_up(ms * fps / 1000.0)


def text_hold(words: int, fps: float | None = None) -> dict:
    """Minimum hold: 0.3 s per word plus 0.5 s; frames rounded UP (never shorter)."""
    if words < 0:
        raise ValueError("words must be >= 0")
    _positive(fps=fps)
    secs = 0.3 * words + 0.5
    out = {"seconds": round(secs, 4)}
    if fps:
        out["frames"] = math.ceil(secs * fps - 1e-9)
    return out


def gif_delays(fps: float, frames: int) -> list[int]:
    """Centisecond delays whose running sum tracks the exact timeline.

    GIF stores delays in hundredths of a second, so 24 fps (4.1667 cs) cannot be
    stored exactly. delay_i = round(100 (i+1) / fps) - round(100 i / fps): every
    cumulative time is within half a centisecond of exact, so the loop length is
    exact whenever 100 * frames / fps is whole.
    """
    _positive(fps=fps)
    if frames < 0:
        raise ValueError("frames must be non-negative")
    return [round_half_up(100 * (i + 1) / fps) - round_half_up(100 * i / fps) for i in range(frames)]


def gif_report(fps: float, frames: int) -> dict:
    d = gif_delays(fps, frames)
    naive_cs = round_half_up(100 / fps)
    exact_s = frames / fps
    return {
        "delays_cs": d,
        "duration_s": sum(d) / 100,
        "exact_s": exact_s,
        "naive_delay_cs": naive_cs,
        "naive_duration_s": naive_cs * frames / 100,
        "naive_error_pct": round((naive_cs * frames / 100 - exact_s) / exact_s * 100, 3) if frames else 0.0,
        "over_x_frame_cap": frames > X_GIF_MAX_FRAMES,
    }


def read_gif_delays(data: bytes) -> list[int]:
    """Return the delay (centiseconds) of every frame in a GIF byte string.

    Walks the block structure: header, logical screen descriptor, optional
    global colour table, then extensions (0x21) and images (0x2C) until the
    trailer (0x3B). A frame with no Graphic Control Extension has delay 0.
    """
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError("not a GIF")
    if len(data) < 13:
        raise ValueError("truncated GIF: no logical screen descriptor")
    pos = 13
    packed = data[10]
    if packed & 0x80:
        pos += 3 * (2 ** ((packed & 0x07) + 1))

    def skip_sub_blocks(p: int) -> int:
        while True:
            if p >= len(data):
                raise ValueError("truncated GIF")
            size = data[p]
            p += 1
            if size == 0:
                return p
            p += size

    def need(p: int, k: int) -> None:
        if p + k > len(data):
            raise ValueError(f"truncated GIF at byte {p}")

    delays: list[int] = []
    pending: int | None = None
    while True:
        need(pos, 1)  # running off the end without a 0x3B trailer is truncation
        tag = data[pos]
        if tag == 0x3B:
            break
        if tag == 0x21:
            need(pos, 2)
            label = data[pos + 1]
            if label == 0xF9 and pos + 7 < len(data):
                pending = data[pos + 4] | (data[pos + 5] << 8)
            pos = skip_sub_blocks(pos + 2)
        elif tag == 0x2C:
            need(pos, 11)
            lpacked = data[pos + 9]
            pos += 10
            if lpacked & 0x80:
                pos += 3 * (2 ** ((lpacked & 0x07) + 1))
            pos += 1  # LZW minimum code size
            pos = skip_sub_blocks(pos)
            delays.append(pending if pending is not None else 0)
            pending = None
        else:
            raise ValueError(f"unexpected block 0x{tag:02x} at byte {pos}")
    return delays


def gif_check(path: Path, fps: float | None = None) -> dict:
    d = read_gif_delays(path.read_bytes())
    out = {
        "frames": len(d),
        "duration_s": sum(d) / 100,
        "distinct_delays_cs": sorted(set(d)),
        "over_x_frame_cap": len(d) > X_GIF_MAX_FRAMES,
    }
    if fps:
        exact = len(d) / fps
        out["target_s"] = exact
        out["error_pct"] = round((out["duration_s"] - exact) / exact * 100, 3) if d else 0.0
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("beats", help="beat frames on a drift-free grid")
    b.add_argument("--fps", type=float, required=True)
    b.add_argument("--bpm", type=float, required=True)
    b.add_argument("--count", type=int, default=16)
    b.add_argument("--offset", type=float, default=0.0, help="frame of beat 0")

    d = sub.add_parser("damping", help="damping ratio (or the damping for a ratio)")
    d.add_argument("--stiffness", "--tension", type=float, required=True)
    d.add_argument("--damping", "--friction", type=float)
    d.add_argument("--mass", type=float, default=1.0)
    d.add_argument("--zeta", type=float, help="target ratio: print the damping that gives it")

    f = sub.add_parser("frames", help="loop frame range and music closure")
    f.add_argument("--seconds", type=float, required=True)
    f.add_argument("--fps", type=float, required=True)
    f.add_argument("--bpm", type=float)

    m = sub.add_parser("ms", help="milliseconds to frames")
    m.add_argument("--ms", type=float, required=True)
    m.add_argument("--fps", type=float, required=True)

    h = sub.add_parser("hold", help="minimum text hold")
    h.add_argument("--words", type=int, required=True)
    h.add_argument("--fps", type=float)

    g = sub.add_parser("gif-delays", help="exact per-frame GIF delays")
    g.add_argument("--fps", type=float, required=True)
    g.add_argument("--frames", type=int, required=True)

    c = sub.add_parser("gif-check", help="measure an exported GIF")
    c.add_argument("gif", type=Path)
    c.add_argument("--fps", type=float, help="intended fps, to report the timing error")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "beats":
            exact = beat_frames(a.fps, a.bpm, a.count, a.offset)
            naive = naive_beat_frames(a.fps, a.bpm, a.count, a.offset)
            res = {"frames_per_beat": frames_per_beat(a.fps, a.bpm), "beats": exact,
                   "naive_drift_frames": naive[-1] - exact[-1] if exact else 0}
        elif a.cmd == "damping":
            if a.zeta is not None:
                res = {"damping": damping_for_ratio(a.zeta, a.stiffness, a.mass), "zeta": a.zeta,
                       "feel": classify_zeta(a.zeta)}
            elif a.damping is not None:
                z = damping_ratio(a.stiffness, a.damping, a.mass)
                res = {"zeta": round(z, 4), "feel": classify_zeta(z)}
            else:
                ap.error("damping needs --damping or --zeta")
        elif a.cmd == "frames":
            res = loop_frames(a.seconds, a.fps, a.bpm)
        elif a.cmd == "ms":
            res = {"frames": ms_to_frames(a.ms, a.fps)}
        elif a.cmd == "hold":
            res = text_hold(a.words, a.fps)
        elif a.cmd == "gif-delays":
            res = gif_report(a.fps, a.frames)
        else:
            res = gif_check(a.gif, a.fps)
    except (ValueError, OSError) as e:
        print(f"motion_math: {e}", file=sys.stderr)
        return 2
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
