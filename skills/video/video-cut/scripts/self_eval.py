#!/usr/bin/env python3
"""self_eval.py — post-render boundary defect inspector for the video-cut skill.

After a render, this self-contained script inspects the rendered output at each
CUT BOUNDARY (computed from the EDL JSON directly) and reports likely defects as
JSON. It depends ONLY on ffmpeg/ffprobe and the Python standard library — it does
NOT import any other project modules.

CLI:
    python3 self_eval.py <edl.json> <rendered.mp4> [--edit-dir DIR]
                         [--window 0.12] [--json]

Checks per boundary:
    1. Black/flash frame  — mean luma (signalstats YAVG) < 16
    2. Audio pop          — peak level (astats Peak_level) > -0.5 dB

Exit codes:
    0  report generated (even if ok=false)
    1  hard error (missing files, etc.)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edl as edl_lib  # noqa: E402  (the single source of truth for timeline math)

# Detection thresholds.
BLACK_YAVG_THRESHOLD = 16.0          # YAVG below this => near-black / flash
AUDIO_POP_PEAK_DB_THRESHOLD = -0.5   # peak above this (closer to 0) => pop


# ---------------------------------------------------------------------------
# subprocess helpers
# ---------------------------------------------------------------------------
def _run(cmd):
    """Run a command, returning a CompletedProcess. Never raises on non-zero.

    stdout/stderr are captured as text. A timeout or OSError yields a synthetic
    CompletedProcess-like object with returncode 1 and empty streams so callers
    can degrade gracefully.
    """
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover
        class _Failed:
            returncode = 1
            stdout = ""
            stderr = str(exc)

        return _Failed()


# ---------------------------------------------------------------------------
# EDL parsing + boundary math (delegates to edl.py — the single source of truth,
# so the inspected seams are IDENTICAL to what render.py actually produced,
# including padded-span clamping at source edges)
# ---------------------------------------------------------------------------
def probe_source_duration(path):
    """ffprobe a source duration (float seconds), or None on failure."""
    proc = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(path)])
    try:
        return float((proc.stdout or "").strip())
    except (TypeError, ValueError):
        return None


def compute_boundaries(edl):
    """Output-timeline boundaries to inspect, computed via edl.output_segments so
    the math matches render.py exactly. Internal seams are the cumulative output
    offsets; head/mid/tail anchors are always added. Returns (sorted_unique, total).
    """
    source_durations = {}
    for label, p in (edl.get("sources") or {}).items():
        d = probe_source_duration(p)
        if d is not None:
            source_durations[label] = d
    segs = edl_lib.output_segments(edl, source_durations)
    total = sum(s["out_dur"] for s in segs)

    timestamps = [s["offset"] for s in segs[1:]]  # internal seams (skip the head at 0)
    timestamps.append(0.5)
    if total > 0:
        timestamps.append(total / 2.0)
        timestamps.append(total - 0.5)

    clamp = lambda t: round(max(0.0, min(float(t), total if total > 0 else float(t))), 2)
    return sorted({clamp(t) for t in timestamps}), total


# ---------------------------------------------------------------------------
# ffprobe / ffmpeg measurements
# ---------------------------------------------------------------------------
def probe_duration(rendered):
    """Return the rendered file duration (float seconds) via ffprobe, or None."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(rendered),
    ]
    proc = _run(cmd)
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    try:
        return float(out)
    except (TypeError, ValueError):
        return None


def has_audio_stream(rendered):
    """Return True if the rendered file has at least one audio stream."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(rendered),
    ]
    proc = _run(cmd)
    if proc.returncode != 0:
        return False
    return bool((proc.stdout or "").strip())


_YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=([-\d.eE+]+)")
_PEAK_RE = re.compile(r"lavfi\.astats\.Overall\.Peak_level=([-\d.eE+]+)")


def extract_frame(rendered, t, frame_path):
    """Extract one frame at time t to frame_path (PNG). Returns True on success."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{t}",
        "-i", str(rendered),
        "-frames:v", "1",
        str(frame_path),
    ]
    proc = _run(cmd)
    return proc.returncode == 0 and Path(frame_path).exists()


def measure_yavg(rendered, t):
    """Return mean luma (YAVG) of the frame at time t, or None on failure."""
    cmd = [
        "ffmpeg",
        "-ss", f"{t}",
        "-i", str(rendered),
        "-frames:v", "1",
        "-vf", "signalstats,metadata=print",
        "-f", "null", "-",
    ]
    proc = _run(cmd)
    matches = _YAVG_RE.findall(proc.stderr or "")
    if not matches:
        return None
    try:
        return float(matches[-1])
    except (TypeError, ValueError):
        return None


def measure_peak_db(rendered, t, window):
    """Return the audio peak level (dB) in [t-window, t+window], or None."""
    start = max(0.0, t - window)
    dur = 2.0 * window
    cmd = [
        "ffmpeg",
        "-ss", f"{start}",
        "-t", f"{dur}",
        "-i", str(rendered),
        "-af",
        "astats=metadata=1:reset=1,"
        "ametadata=print:key=lavfi.astats.Overall.Peak_level",
        "-f", "null", "-",
    ]
    proc = _run(cmd)
    matches = _PEAK_RE.findall(proc.stderr or "")
    if not matches:
        return None
    # Take the max (closest to 0 / loudest) peak across reported frames.
    peaks = []
    for m in matches:
        try:
            val = float(m)
        except (TypeError, ValueError):
            continue
        peaks.append(val)
    if not peaks:
        return None
    return max(peaks)


# ---------------------------------------------------------------------------
# per-boundary inspection
# ---------------------------------------------------------------------------
def inspect_boundary(rendered, t, window, verify_dir, audio_present):
    """Run all checks at boundary t and return the result dict."""
    result = {
        "t": t,
        "black": None,
        "yavg": None,
        "audio_pop": None,
        "peak_db": None,
        "frame": None,
        "ok": None,
    }

    # --- Visual: extract evidence frame + measure YAVG ---
    frame_path = verify_dir / f"eval_{t}.png"
    try:
        if extract_frame(rendered, t, frame_path):
            result["frame"] = str(frame_path)
    except Exception:  # noqa: BLE001 — one failing check must not abort the rest
        result["frame"] = None

    try:
        yavg = measure_yavg(rendered, t)
        result["yavg"] = yavg
        if yavg is not None:
            result["black"] = yavg < BLACK_YAVG_THRESHOLD
    except Exception:  # noqa: BLE001
        result["yavg"] = None
        result["black"] = None

    # --- Audio: peak level => pop detection ---
    if not audio_present:
        result["audio_pop"] = None
        result["peak_db"] = None
    else:
        try:
            peak = measure_peak_db(rendered, t, window)
            result["peak_db"] = peak
            if peak is not None:
                result["audio_pop"] = peak > AUDIO_POP_PEAK_DB_THRESHOLD
        except Exception:  # noqa: BLE001
            result["peak_db"] = None
            result["audio_pop"] = None

    # --- Aggregate ok. An UNMEASURABLE frame (black is None — ffmpeg returned no
    # YAVG, i.e. a corrupt/unsupported render) is a failure to VERIFY, not a pass.
    # audio_pop None = no audio stream, which is legitimately acceptable. ---
    black_ok = result["black"] is False          # None or True => not ok
    pop_ok = result["audio_pop"] is not True     # None (no audio) => ok
    result["ok"] = black_ok and pop_ok

    return result


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build_report(edl_path, rendered_path, edit_dir, window):
    edl = edl_lib.load_edl(edl_path)
    # Resolve relative EDL source paths against the videos dir (parent of edit/),
    # so duration probing is CWD-independent and the inspected seams match render.py.
    videos_dir = Path(edl_path).resolve().parent.parent
    edl["sources"] = {
        label: (p if Path(p).is_absolute() else str((videos_dir / p).resolve()))
        for label, p in (edl.get("sources") or {}).items()
    }
    boundaries, computed_total = compute_boundaries(edl)

    # Resolve the verify directory. Default to the EDL's own edit dir (its parent),
    # not <rendered>/edit — the latter nests as edit/edit/verify for edit/final.mp4.
    if edit_dir is not None:
        base_dir = Path(edit_dir)
    else:
        base_dir = Path(edl_path).resolve().parent
    verify_dir = base_dir / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)

    total_duration = probe_duration(rendered_path)
    audio_present = has_audio_stream(rendered_path)

    boundary_results = []
    for t in boundaries:
        boundary_results.append(
            inspect_boundary(rendered_path, t, window, verify_dir, audio_present)
        )

    passes = sum(1 for b in boundary_results if b["ok"])
    fails = sum(1 for b in boundary_results if not b["ok"])

    report = {
        "rendered": str(Path(rendered_path).resolve()),
        "total_duration_s": total_duration,
        "computed_total_s": round(computed_total, 4),
        "boundaries": boundary_results,
        "passes": passes,
        "fails": fails,
        "ok": fails == 0,
    }
    return report


def human_summary(report):
    """Render a short human-readable summary string for stderr."""
    lines = []
    lines.append(f"self_eval: {report['rendered']}")
    td = report["total_duration_s"]
    td_str = f"{td:.2f}s" if isinstance(td, (int, float)) else "unknown"
    lines.append(
        f"  duration: rendered={td_str} "
        f"computed={report['computed_total_s']:.2f}s"
    )
    lines.append(
        f"  boundaries: {len(report['boundaries'])} "
        f"({report['passes']} pass / {report['fails']} fail)"
    )
    for b in report["boundaries"]:
        flags = []
        if b["black"]:
            flags.append("BLACK")
        if b["audio_pop"]:
            flags.append("POP")
        status = "ok" if b["ok"] else ("FAIL[" + ",".join(flags) + "]")
        yavg = b["yavg"]
        yavg_str = f"{yavg:.1f}" if isinstance(yavg, (int, float)) else "n/a"
        peak = b["peak_db"]
        peak_str = f"{peak:.1f}dB" if isinstance(peak, (int, float)) else "n/a"
        lines.append(
            f"    t={b['t']:<8} yavg={yavg_str:<8} peak={peak_str:<8} {status}"
        )
    lines.append(f"  result: {'OK' if report['ok'] else 'DEFECTS FOUND'}")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect a rendered video at each cut boundary for defects."
    )
    parser.add_argument("edl", help="Path to the EDL JSON file.")
    parser.add_argument("rendered", help="Path to the rendered .mp4 to inspect.")
    parser.add_argument(
        "--edit-dir",
        default=None,
        help="Edit directory (verify/ goes inside). "
        "Defaults to <rendered dir>/edit.",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=0.12,
        help="Seconds around each boundary to sample (default 0.12).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the JSON report to stdout.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    edl_path = Path(args.edl)
    rendered_path = Path(args.rendered)

    # Hard-error preconditions.
    if not edl_path.exists():
        print(f"error: EDL file not found: {edl_path}", file=sys.stderr)
        return 1
    if not rendered_path.exists():
        print(f"error: rendered file not found: {rendered_path}", file=sys.stderr)
        return 1

    try:
        report = build_report(edl_path, rendered_path, args.edit_dir, args.window)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: failed to build report: {exc}", file=sys.stderr)
        return 1

    if not args.json:
        print(human_summary(report), file=sys.stderr)

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
