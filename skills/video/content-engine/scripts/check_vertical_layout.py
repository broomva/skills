#!/usr/bin/env python3
"""Check a 9:16 video, frame set, or declared layout against the content-engine
vertical layout contract (layout/vertical-9x16.json; rules in
references/vertical-layout.md).

    python3 scripts/check_vertical_layout.py video final.mp4
    python3 scripts/check_vertical_layout.py image still-1.png still-2.png
    python3 scripts/check_vertical_layout.py spec overlays.json
    python3 scripts/check_vertical_layout.py guide final.mp4 --out guide.png
    python3 scripts/check_vertical_layout.py zones            # the zones in pixels

Rules
    VL1 canvas            9:16, at least 1080 wide
    VL2 safe zone         overlay text inside the safe zone (title band excepted)
    VL3 avoid zones       no overlay text or face on the action rail / bottom band
    VL4 title hook band   top text sits in the title band
    VL5 caption band      captions sit in the caption band, centred
    VL6 eye line          eyes sit in the eye-line band
    VL7 punch-in          eye line holds across punch-ins
    VL8 subject           face inside the safe zone
    VL9 legibility        stroke on busy backgrounds (declared) / halo contrast (measured)

Statuses: PASS, FAIL, WARN, SKIP (nothing in the input for this rule), N/A (the
profile does not define it), UNCHECKED (the detector cannot measure it). Only FAIL
fails the run; --strict also fails on UNCHECKED. Exit: 0 ok, 1 FAIL, 2 usage or
tool error.

Stdlib only. Video and image input need ffmpeg/ffprobe plus a detector: macOS
Vision (text and faces; vision_probe.swift, compiled on first use) or tesseract
(text only, so the face rules report UNCHECKED).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAYOUT = SKILL_ROOT / "layout" / "vertical-9x16.json"
VISION_SRC = Path(__file__).resolve().parent / "vision_probe.swift"

RULES = [
    ("VL1", "canvas"),
    ("VL2", "safe zone"),
    ("VL3", "avoid zones"),
    ("VL4", "title hook band"),
    ("VL5", "caption band"),
    ("VL6", "eye line"),
    ("VL7", "eye line across punch-ins"),
    ("VL8", "subject in safe zone"),
    ("VL9", "stroke / legibility"),
]
MAX_EVIDENCE = 6
BOX_SLACK = 0.002  # fraction of height a detector box may overhang a zone edge


class ToolError(Exception):
    """A required tool or input is missing; exit 2, never a verdict."""


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def inside(self, other: "Box", slack: float = 0.0) -> bool:
        return (self.x0 >= other.x0 - slack and self.y0 >= other.y0 - slack
                and self.x1 <= other.x1 + slack and self.y1 <= other.y1 + slack)

    def intersects(self, other: "Box") -> bool:
        return (min(self.x1, other.x1) > max(self.x0, other.x0)
                and min(self.y1, other.y1) > max(self.y0, other.y0))

    def as_list(self) -> list[int]:
        return [round(self.x0), round(self.y0), round(self.x1), round(self.y1)]


@dataclass
class Text:
    text: str
    box: Box
    role: str | None = None          # declared (spec mode)
    stroke: bool | None = None       # declared (spec mode)
    background: str | None = None    # declared (spec mode): busy | calm
    halo_share: float | None = None  # measured (video/image mode)
    region: str = ""                 # title | caption | mid | other


@dataclass
class Face:
    box: Box
    eye_y: float | None


@dataclass
class Frame:
    label: str
    t: float | None = None
    texts: list[Text] = field(default_factory=list)
    faces: list[Face] | None = None  # None: the detector cannot see faces
    path: str | None = None
    shot: int | None = None          # declared shot index (spec mode)


@dataclass
class Result:
    rule: str
    name: str
    status: str
    detail: str
    evidence: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Layout contract
# ---------------------------------------------------------------------------

def load_layout(path: Path | None = None) -> dict:
    path = path or DEFAULT_LAYOUT
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"cannot read layout contract {path}: {exc}") from exc


def get_profile(layout: dict, name: str | None) -> tuple[str, dict]:
    name = name or layout["default_profile"]
    if name not in layout["profiles"]:
        raise ToolError(f"unknown profile {name!r}; have {sorted(layout['profiles'])}")
    return name, layout["profiles"][name]


def zone(z: dict, W: float, H: float) -> Box:
    return Box(z["x0"] * W, z["y0"] * H, z["x1"] * W, z["y1"] * H)


def band(z: dict, safe: Box, H: float) -> Box:
    """A horizontal band, bounded left and right by the safe zone."""
    return Box(safe.x0, z["y0"] * H, safe.x1, z["y1"] * H)


def pct(v: float, whole: float) -> str:
    return f"{100 * v / whole:.1f}%"


# ---------------------------------------------------------------------------
# Rule engine (pure: frames in, results out)
# ---------------------------------------------------------------------------

def _ev(frame: Frame, item, what: str = "") -> dict:
    out = {"at": frame.label}
    if isinstance(item, Text):
        out.update(text=item.text, box=item.box.as_list())
    elif isinstance(item, Face):
        out.update(face=item.box.as_list())
    if what:
        out["why"] = what
    return out


def _primary_face(frame: Frame) -> Face | None:
    if not frame.faces:
        return None
    return max(frame.faces, key=lambda f: f.box.w * f.box.h)


def punch_in_segments(face_frames: list[tuple[Frame, Face]], jump: float) -> list[list[tuple[Frame, Face]]]:
    """Split face frames into shots: by declared shot index when present, else where
    the face scale moves >= `jump` off the current shot's median face height and
    stays there on the next sample (a punch-in or punch-out). Measuring against the
    shot median, not the previous sample, keeps a subject leaning in (the source reel
    drifts 14% sample-to-sample inside one shot) from reading as a cut."""
    if not face_frames:
        return []
    if all(f.shot is not None for f, _ in face_frames):
        segs: dict[int, list] = {}
        for f, face in face_frames:
            segs.setdefault(f.shot, []).append((f, face))
        return [segs[k] for k in sorted(segs)]

    def off(item, seg) -> bool:
        med = statistics.median(face.box.h for _, face in seg)
        return med > 0 and abs(item[1].box.h / med - 1) >= jump

    segs_l = [[face_frames[0]]]
    for i, cur in enumerate(face_frames[1:], start=1):
        seg = segs_l[-1]
        nxt = face_frames[i + 1] if i + 1 < len(face_frames) else None
        if off(cur, seg) and (nxt is None or off(nxt, seg)):
            segs_l.append([cur])
        else:
            seg.append(cur)
    return segs_l


def _seg_label(seg) -> str:
    first, last = seg[0][0].label, seg[-1][0].label
    return first if first == last else f"{first}..{last}"


def evaluate(W: float, H: float, frames: list[Frame], profile: dict, cls: dict,
             canvas_cfg: dict, expect: frozenset = frozenset()) -> list[Result]:
    """`expect` holds "title" and/or "caption" when the caller knows it burned that
    text in. OCR cannot tell missing text from text too illegible to read, so without
    it an absent caption is a SKIP; with it, the absence is a FAIL."""
    results: list[Result] = []
    names = dict(RULES)

    def add(rule, status, detail, evidence=None):
        results.append(Result(rule, names[rule], status, detail, (evidence or [])[:MAX_EVIDENCE]))

    # VL1 canvas -----------------------------------------------------------
    aw, ah = canvas_cfg["aspect"]
    aspect_off = abs((W / H) / (aw / ah) - 1)
    if aspect_off > canvas_cfg["aspect_tolerance"]:
        add("VL1", "FAIL", f"{W:.0f}x{H:.0f} is not {aw}:{ah}; every zone below is defined on a {aw}:{ah} canvas")
        for rule, _ in RULES[1:]:
            add(rule, "N/A", "canvas is not 9:16")
        return results
    if W < canvas_cfg["min_width"]:
        add("VL1", "WARN", f"{W:.0f}x{H:.0f} is 9:16 but below {canvas_cfg['min_width']} wide")
    else:
        add("VL1", "PASS", f"{W:.0f}x{H:.0f} (9:16)")

    slack = BOX_SLACK * H
    safe = zone(profile["safe_zone"], W, H)
    title_rect = band(profile["title_band"], safe, H) if profile.get("title_band") else None
    cap_cfg = profile.get("caption_band")
    cap_rect = band(cap_cfg, safe, H) if cap_cfg else None

    # Overlay vs scene text, then region ------------------------------------
    overlay: list[tuple[Frame, Text]] = []
    scene = 0
    for f in frames:
        for t in f.texts:
            if t.role or t.box.h >= cls["overlay_min_text_height"] * H:
                overlay.append((f, t))
            else:
                scene += 1
    for _, t in overlay:
        if t.role:
            t.region = t.role if t.role in ("title", "caption") else "other"
        elif t.box.cy <= cls["title_region_max_centre_y"] * H:
            t.region = "title"
        elif t.box.cy >= cls["caption_region_min_centre_y"] * H:
            t.region = "caption"
        else:
            t.region = "mid"

    # Word-by-word text parked in the title band is a caption, not a title.
    captions_in_top = False
    measured_top = [(f, t) for f, t in overlay if t.region == "title" and not t.role]
    if measured_top:
        by_frame: dict[str, list[str]] = {}
        order: list[str] = []
        for f, t in measured_top:
            if f.label not in by_frame:
                order.append(f.label)
            by_frame.setdefault(f.label, []).append(t.text.strip().lower())
        seq = [" ".join(sorted(by_frame[k])) for k in order]
        n = len(seq)
        changes = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
        if n >= cls["caption_like_min_samples"] and changes / (n - 1) >= cls["caption_like_change_fraction"]:
            captions_in_top = True
            for _, t in measured_top:
                t.region = "caption"

    unread = "OCR found none: the text is missing or too illegible to read, which is itself a legibility failure"
    scene_note = f"; {scene} small text box(es) under {pct(cls['overlay_min_text_height'] * H, H)} of height ignored as scene text" if scene else ""

    # VL2 safe zone --------------------------------------------------------
    # An expected title/caption is failed by its own band rule (VL4/VL5); VL2 carries
    # it only for a profile that has no band for it.
    uncovered = sorted(e for e in expect if not {"title": title_rect, "caption": cap_rect}.get(e))
    if not overlay and uncovered:
        add("VL2", "FAIL", f"expected {' and '.join(uncovered)} text; {unread}" + scene_note)
    elif not overlay:
        add("VL2", "SKIP", "no overlay text found" + scene_note)
    else:
        bad = [(f, t) for f, t in overlay
               if not t.box.inside(safe, slack)
               and not (t.region == "title" and title_rect and t.box.inside(title_rect, slack))]
        where = f"safe zone x {safe.x0:.0f}-{safe.x1:.0f}, y {safe.y0:.0f}-{safe.y1:.0f}"
        if bad:
            add("VL2", "FAIL", f"{len(bad)}/{len(overlay)} overlay text box(es) leave the {where}" + scene_note,
                [_ev(f, t) for f, t in bad])
        else:
            extra = " (title band excepted)" if title_rect else ""
            add("VL2", "PASS", f"{len(overlay)} overlay text box(es) inside the {where}{extra}" + scene_note)

    # VL3 avoid zones ------------------------------------------------------
    avoid = [(a["name"], zone(a, W, H)) for a in profile.get("avoid") or []]
    faces_seen = any(f.faces is not None for f in frames)
    if not avoid:
        add("VL3", "N/A", "profile defines no avoid zones")
    else:
        items = [(f, t) for f, t in overlay]
        items += [(f, face) for f in frames for face in ([_primary_face(f)] if _primary_face(f) else [])]
        if not items:
            add("VL3", "SKIP", "no overlay text or face found")
        else:
            hits = []
            for f, item in items:
                for name, rect in avoid:
                    if item.box.intersects(rect):
                        hits.append(_ev(f, item, name))
            faces_note = "" if faces_seen else " (faces not measured by this detector)"
            if hits:
                add("VL3", "FAIL", f"{len(hits)} element(s) touch an avoid zone{faces_note}", hits)
            else:
                add("VL3", "PASS", f"{len(items)} element(s) clear of {', '.join(n for n, _ in avoid)}{faces_note}")

    # VL4 title hook band --------------------------------------------------
    if not title_rect:
        add("VL4", "N/A", "profile defines no title band")
    else:
        titles = [(f, t) for f, t in overlay if t.region == "title"]
        if not titles and "title" in expect:
            add("VL4", "FAIL", f"expected a title hook; {unread}")
        elif not titles:
            add("VL4", "SKIP", "no title-hook text found")
        else:
            bad = [(f, t) for f, t in titles if not t.box.inside(title_rect, slack)]
            span = f"y {title_rect.y0:.0f}-{title_rect.y1:.0f} ({pct(title_rect.y0, H)}-{pct(title_rect.y1, H)})"
            if bad:
                add("VL4", "FAIL", f"{len(bad)}/{len(titles)} title box(es) outside the title band {span}",
                    [_ev(f, t) for f, t in bad])
            else:
                cys = [t.box.cy for _, t in titles]
                add("VL4", "PASS", f"{len(titles)} title box(es) in the title band {span}; "
                                   f"centre y {min(cys):.0f}-{max(cys):.0f}")

    # VL5 caption band -----------------------------------------------------
    if not cap_rect:
        add("VL5", "N/A", "profile defines no caption band; captions are held to VL2 only")
    else:
        caps = [(f, t) for f, t in overlay if t.region == "caption"]
        if not caps and "caption" in expect:
            add("VL5", "FAIL", f"expected captions; {unread}")
        elif not caps:
            add("VL5", "SKIP", "no caption text found")
        else:
            tol = cap_cfg["centre_x_tolerance"] * W
            bad = [_ev(f, t, "outside caption band") for f, t in caps if not t.box.inside(cap_rect, slack)]
            # Centring is judged on the median centre: OCR that reads a fragment of a
            # word ("nd" of "background") puts that one box off-centre, while a
            # placement error moves every box.
            med_dx = statistics.median(t.box.cx for _, t in caps) - W / 2
            strays = sum(1 for _, t in caps if abs(t.box.cx - W / 2) > tol)
            if abs(med_dx) > tol:
                bad.append({"at": "all captions", "why": f"median centre off by {med_dx:+.0f}px"})
            span = f"y {cap_rect.y0:.0f}-{cap_rect.y1:.0f} ({pct(cap_rect.y0, H)}-{pct(cap_rect.y1, H)})"
            top = "; word-by-word text found in the title band is treated as captions" if captions_in_top else ""
            if bad:
                add("VL5", "FAIL", f"{len(bad)} caption problem(s): boxes must sit in {span} with the median "
                                   f"centre within +/-{tol:.0f}px{top}", bad)
            else:
                cys = [t.box.cy for _, t in caps]
                stray = f"; {strays} box(es) off-centre on their own (partial OCR reads)" if strays else ""
                add("VL5", "PASS", f"{len(caps)} caption box(es) in {span}, median centre {med_dx:+.0f}px; centre y "
                                   f"{min(cys):.0f}-{max(cys):.0f} ({pct(min(cys), H)}-{pct(max(cys), H)}){stray}")

    # Faces: VL6, VL7, VL8 -------------------------------------------------
    eye_cfg = profile.get("eye_line")
    face_frames = [(f, _primary_face(f)) for f in frames if _primary_face(f)]
    no_faces_detector = "detector reports no faces (tesseract); run on macOS (Vision) or check the guide sheet by eye"
    segs = punch_in_segments(face_frames, eye_cfg["punch_in_scale_jump"]) if eye_cfg else []

    def seg_eye(seg) -> float | None:
        ys = [face.eye_y for _, face in seg if face.eye_y is not None]
        return statistics.median(ys) if ys else None

    if not eye_cfg:
        add("VL6", "N/A", "profile defines no eye line")
        add("VL7", "N/A", "profile defines no eye line")
    elif not faces_seen:
        add("VL6", "UNCHECKED", no_faces_detector)
        add("VL7", "UNCHECKED", no_faces_detector)
    elif not face_frames:
        add("VL6", "SKIP", "no face found")
        add("VL7", "SKIP", "no face found")
    else:
        lo, hi = eye_cfg["y0"] * H, eye_cfg["y1"] * H
        rows = [(seg, seg_eye(seg)) for seg in segs]
        measured = [(seg, y) for seg, y in rows if y is not None]
        if not measured:
            add("VL6", "UNCHECKED", "faces found but no eye landmarks")
        else:
            bad = [{"at": _seg_label(seg), "eye_y": round(y), "why": f"{pct(y, H)} outside {pct(lo, H)}-{pct(hi, H)}"}
                   for seg, y in measured if not lo <= y <= hi]
            span = f"y {lo:.0f}-{hi:.0f} ({pct(lo, H)}-{pct(hi, H)})"
            if bad:
                add("VL6", "FAIL", f"{len(bad)}/{len(measured)} shot(s) put the eyes outside {span}", bad)
            else:
                ys = [y for _, y in measured]
                add("VL6", "PASS", f"eye line {min(ys):.0f}-{max(ys):.0f}px ({pct(min(ys), H)}-{pct(max(ys), H)}) "
                                   f"across {len(measured)} shot(s), inside {span}")
        if len(measured) < 2:
            add("VL7", "SKIP", f"no punch-in found (face-scale jump >= {eye_cfg['punch_in_scale_jump']:.0%})")
        else:
            limit = eye_cfg["max_shift_across_punch_in"] * H
            shifts = []
            for (sa, ya), (sb, yb) in zip(measured, measured[1:]):
                shifts.append({"at": f"{_seg_label(sa)} -> {_seg_label(sb)}", "shift_px": round(yb - ya)})
            bad = [s for s in shifts if abs(s["shift_px"]) > limit]
            if bad:
                add("VL7", "FAIL", f"eye line moves more than {limit:.0f}px ({pct(limit, H)}) across "
                                   f"{len(bad)}/{len(shifts)} cut(s)", bad)
            else:
                worst = max(abs(s["shift_px"]) for s in shifts)
                add("VL7", "PASS", f"{len(shifts)} cut(s); largest eye-line shift {worst}px, limit {limit:.0f}px",
                    shifts)

    if not faces_seen:
        add("VL8", "UNCHECKED", no_faces_detector)
    elif not face_frames:
        add("VL8", "SKIP", "no face found")
    else:
        bad = []
        for seg in segs or [face_frames]:
            med = Box(*(statistics.median(getattr(face.box, k) for _, face in seg) for k in ("x0", "y0", "x1", "y1")))
            if not med.inside(safe, slack):
                bad.append({"at": _seg_label(seg), "face": med.as_list()})
        if bad:
            add("VL8", "FAIL", f"the face leaves the safe zone in {len(bad)} shot(s)", bad)
        else:
            add("VL8", "PASS", f"face inside the safe zone across {len(segs) or 1} shot(s)")

    # VL9 legibility -------------------------------------------------------
    leg = profile.get("legibility") or {}
    declared = [(f, t) for f, t in overlay if t.background is not None]
    measured_leg = [(f, t) for f, t in overlay if t.halo_share is not None]
    if declared:
        bad = [_ev(f, t, "busy background, no stroke") for f, t in declared
               if t.background == "busy" and t.stroke is not True]
        if bad:
            add("VL9", "FAIL", f"{len(bad)} element(s) declared over a busy background without a stroke", bad)
        else:
            add("VL9", "PASS", f"{len(declared)} element(s) declare a background; every busy one has a stroke")
    elif measured_leg:
        need = leg.get("min_halo_contrast_share", 0.6)
        ratio = leg.get("contrast_ratio", 3.0)
        weak = [dict(_ev(f, t), halo_share=round(t.halo_share, 2)) for f, t in measured_leg if t.halo_share < need]
        if weak:
            add("VL9", "WARN", f"{len(weak)}/{len(measured_leg)} text box(es) have under {need:.0%} of their edge "
                               f"halo at >= {ratio}:1 contrast; add a stroke (or a backing) on busy backgrounds", weak)
        else:
            lows = min(t.halo_share for _, t in measured_leg)
            add("VL9", "PASS", f"{len(measured_leg)} light text box(es); lowest halo contrast share {lows:.2f} "
                               f"(>= {need:.0%} at {ratio}:1)")
    elif overlay:
        add("VL9", "UNCHECKED", "no light-on-dark overlay text to measure, and no element declares its background")
    else:
        add("VL9", "SKIP", "no overlay text found")

    return results


# ---------------------------------------------------------------------------
# Media helpers (ffmpeg / ffprobe)
# ---------------------------------------------------------------------------

def _need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ToolError(f"{tool} not found on PATH")
    return path


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, **kw)


def probe(path: str) -> dict:
    _need("ffprobe")
    p = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
              "stream=width,height:format=duration", "-of", "json", path], text=True)
    if p.returncode != 0:
        raise ToolError(f"ffprobe failed on {path}: {p.stderr.strip()}")
    data = json.loads(p.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise ToolError(f"no video stream in {path}")
    dur = data.get("format", {}).get("duration")
    return {"w": int(streams[0]["width"]), "h": int(streams[0]["height"]),
            "duration": float(dur) if dur not in (None, "N/A") else None}


def sample_frames(video: str, duration: float | None, fps: float, max_frames: int, out: Path) -> list[Frame]:
    _need("ffmpeg")
    rate = fps
    if duration and duration * fps > max_frames:
        rate = max_frames / duration
    p = _run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={rate}", "-q:v", "2",
              str(out / "f_%05d.jpg")])
    if p.returncode != 0:
        raise ToolError(f"ffmpeg frame extraction failed: {p.stderr.decode(errors='replace').strip()}")
    frames = [Frame(label=f"t={i / rate:.2f}s", t=i / rate, path=str(fp))
              for i, fp in enumerate(sorted(out.glob("f_*.jpg")))]
    # Progressive overlays often complete only on the final frame.
    if duration and duration > 0.3:
        last = out / "last.jpg"
        _run(["ffmpeg", "-v", "error", "-sseof", "-0.15", "-i", video, "-frames:v", "1", "-q:v", "2", str(last)])
        if last.exists():
            frames.append(Frame(label=f"t={duration - 0.15:.2f}s (last)", t=duration - 0.15, path=str(last)))
    if not frames:
        raise ToolError(f"no frames extracted from {video}")
    return frames


def gray_frame(path: str) -> tuple[bytes, int, int]:
    info = probe(path)
    p = _run(["ffmpeg", "-v", "error", "-i", path, "-frames:v", "1", "-vf", "format=gray",
              "-f", "rawvideo", "-"])
    if p.returncode != 0 or len(p.stdout) != info["w"] * info["h"]:
        raise ToolError(f"cannot decode {path} to grayscale")
    return p.stdout, info["w"], info["h"]


def _linear(v: int) -> float:
    c = v / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _dilate(mask: list[list[bool]], r: int) -> list[list[bool]]:
    h, w = len(mask), len(mask[0]) if mask else 0

    def run1d(row: list[bool]) -> list[bool]:
        n = len(row)
        pre = [0] * (n + 1)
        for i, v in enumerate(row):
            pre[i + 1] = pre[i] + v
        return [pre[min(n, i + r + 1)] - pre[max(0, i - r)] > 0 for i in range(n)]

    rows = [run1d(row) for row in mask]
    cols = [run1d([rows[y][x] for y in range(h)]) for x in range(w)]
    return [[cols[x][y] for x in range(w)] for y in range(h)]


def halo_contrast_share(gray: bytes, W: int, H: int, box: Box, ratio: float,
                        glyph_min: int = 215, radius: int = 3, pad: int = 6) -> float | None:
    """Share of the pixels in a ring around light glyphs (2..radius+1 px out, which
    skips the anti-aliased first pixel) that reach `ratio`:1 contrast against the
    glyph fill. A stroke or a dark backing drives it towards 1; light text over a
    busy or light background drags it down. Glyph pixels are those within 30 levels
    of the box's brightest 2%, so a light background is not mistaken for text. None
    when the box holds no light text to measure."""
    x0, y0 = max(0, int(box.x0) - pad), max(0, int(box.y0) - pad)
    x1, y1 = min(W, int(box.x1) + pad), min(H, int(box.y1) + pad)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    rows = [gray[y * W + x0: y * W + x1] for y in range(y0, y1)]
    inner = sorted(gray[y * W + x] for y in range(max(0, int(box.y0)), min(H, int(box.y1)))
                   for x in range(max(0, int(box.x0)), min(W, int(box.x1))))
    if not inner:
        return None
    cut = max(glyph_min, inner[int(0.98 * (len(inner) - 1))] - 30)
    glyph = [[v >= cut for v in row] for row in rows]
    fill = sorted(v for row in rows for v in row if v >= cut)
    if len(fill) < 50:
        return None
    lf = _linear(fill[len(fill) // 2])
    skip = _dilate(glyph, 1)
    ring = _dilate(glyph, radius + 1)
    ok = n = 0
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            if ring[y][x] and not skip[y][x]:
                n += 1
                if (lf + 0.05) / (_linear(v) + 0.05) >= ratio:
                    ok += 1
    return ok / n if n else None


def draw_filter(W: int, H: int, profile: dict) -> str:
    """ffmpeg drawbox chain that paints the profile's zones onto a frame."""
    safe = zone(profile["safe_zone"], W, H)
    parts = []

    def box(b: Box, color: str, t: str) -> str:
        return (f"drawbox=x={b.x0:.0f}:y={b.y0:.0f}:w={max(1, b.w):.0f}:h={max(1, b.h):.0f}"
                f":color={color}:t={t}")

    # Outside the safe zone: dim red.
    parts += [box(Box(0, 0, W, safe.y0), "red@0.18", "fill"),
              box(Box(0, safe.y1, W, H), "red@0.18", "fill"),
              box(Box(0, safe.y0, safe.x0, safe.y1), "red@0.18", "fill"),
              box(Box(safe.x1, safe.y0, W, safe.y1), "red@0.18", "fill")]
    for a in profile.get("avoid") or []:
        parts.append(box(zone(a, W, H), "red@0.40", "fill"))
    parts.append(box(safe, "lime@0.9", "6"))
    for key in ("title_band", "caption_band"):
        if profile.get(key):
            parts.append(box(band(profile[key], safe, H), "yellow@0.9", "4"))
    eye = profile.get("eye_line")
    if eye:
        for y in (eye["y0"], eye["y1"]):
            parts.append(box(Box(0, y * H - 2, W, y * H + 2), "cyan@0.9", "fill"))
    # Blend in RGB: drawbox alpha on subsampled YUV smears the red far past its alpha.
    return ",".join(["format=rgb24", *parts])


def write_guide(src: str, W: int, H: int, duration: float | None, profile: dict, out: Path,
                n: int = 6, is_image: bool = False) -> Path:
    _need("ffmpeg")
    chain = draw_filter(W, H, profile)
    if is_image:
        vf = f"{chain},scale=360:-2"
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf, "-frames:v", "1", str(out)]
    else:
        rate = n / duration if duration else 1
        vf = f"fps={rate},{chain},scale=360:-2,tile={n}x1"
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf, "-frames:v", "1", str(out)]
    p = _run(cmd)
    if p.returncode != 0 or not out.exists():
        raise ToolError(f"guide render failed: {p.stderr.decode(errors='replace').strip()}")
    return out


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _is_words(text: str) -> bool:
    """OCR on busy footage returns punctuation out of noise ('=', '|', '.'); a box
    with no letter or digit is not overlay text."""
    return any(ch.isalnum() for ch in text)


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    d = Path(base) / "content-engine"
    d.mkdir(parents=True, exist_ok=True)
    return d


def vision_binary() -> Path | None:
    if sys.platform != "darwin" or not shutil.which("swiftc") or not VISION_SRC.exists():
        return None
    digest = hashlib.sha256(VISION_SRC.read_bytes()).hexdigest()[:12]
    binary = _cache_dir() / f"vision_probe-{digest}"
    if not binary.exists():
        p = _run(["swiftc", "-O", str(VISION_SRC), "-o", str(binary)])
        if p.returncode != 0:
            return None
    return binary


def detect_vision(binary: Path, frames: list[Frame]) -> None:
    by_path = {f.path: f for f in frames}
    p = _run([str(binary), *by_path], text=True)
    if p.returncode != 0:
        raise ToolError(f"vision_probe failed: {p.stderr.strip()[-400:]}")
    seen = 0
    for line in p.stdout.splitlines():
        if not line.startswith("{"):
            continue
        d = json.loads(line)
        f = by_path.get(d.get("image"))
        if f is None:
            continue
        if "error" in d:
            raise ToolError(f"vision_probe: {d['image']}: {d['error']}")
        seen += 1
        f.texts = [Text(t["text"], Box(*t["box"])) for t in d["text"] if _is_words(t["text"])]
        f.faces = [Face(Box(*fc["box"]), fc.get("eye_y")) for fc in d["faces"]]
    if seen != len(frames):
        raise ToolError(f"vision_probe answered for {seen}/{len(frames)} frames")


def _merge_words(words: list[tuple[str, Box]]) -> list[Text]:
    """Join tesseract word boxes into line boxes."""
    lines: list[list] = []
    for text, b in sorted(words, key=lambda w: (w[1].y0, w[1].x0)):
        for line in lines:
            lb = line[1]
            overlap = min(lb.y1, b.y1) - max(lb.y0, b.y0)
            gap = b.x0 - lb.x1
            if overlap >= 0.5 * min(lb.h, b.h) and -lb.h < gap <= 1.5 * max(lb.h, b.h):
                line[0].append(text)
                line[1] = Box(min(lb.x0, b.x0), min(lb.y0, b.y0), max(lb.x1, b.x1), max(lb.y1, b.y1))
                break
        else:
            lines.append([[text], b])
    return [Text(" ".join(ws), b) for ws, b in lines]


def detect_tesseract(frames: list[Frame], min_conf: float = 60.0) -> None:
    """Portable text-only fallback. Reliable on calm backgrounds; on busy footage it
    both misses stroked words and reads texture as words, so treat its FAILs as
    leads to confirm on the guide sheet, and gate finals with Vision."""
    _need("tesseract")
    for f in frames:
        p = _run(["tesseract", f.path, "-", "--psm", "11", "tsv"], text=True)
        if p.returncode != 0:
            raise ToolError(f"tesseract failed on {f.path}: {p.stderr.strip()[-300:]}")
        words = []
        for row in p.stdout.splitlines()[1:]:
            cols = row.split("\t")
            if len(cols) < 12 or not _is_words(cols[11]):
                continue
            try:
                conf = float(cols[10])
            except ValueError:
                continue
            # Busy footage makes tesseract read texture as short words; a single
            # glyph must be near-certain to count.
            if conf < min_conf or (sum(ch.isalnum() for ch in cols[11]) < 2 and conf < 85):
                continue
            x, y, w, h = (int(c) for c in cols[6:10])
            words.append((cols[11].strip(), Box(x, y, x + w, y + h)))
        f.texts = _merge_words(words)
        f.faces = None


def run_detector(name: str, frames: list[Frame]) -> str:
    if name in ("auto", "vision"):
        binary = vision_binary()
        if binary:
            detect_vision(binary, frames)
            return "vision"
        if name == "vision":
            raise ToolError("macOS Vision is unavailable (needs darwin + swiftc)")
    if name in ("auto", "tesseract"):
        if shutil.which("tesseract"):
            detect_tesseract(frames)
            return "tesseract"
        raise ToolError("no detector: tesseract is not installed and macOS Vision is unavailable")
    raise ToolError(f"unknown detector {name!r}")


def measure_legibility(frames: list[Frame], ratio: float, min_text_height: float) -> None:
    for f in frames:
        big = [t for t in f.texts if t.box.h >= min_text_height]
        if not big or not f.path:
            continue
        gray, W, H = gray_frame(f.path)
        for t in big:
            t.halo_share = halo_contrast_share(gray, W, H, t.box, ratio)


# ---------------------------------------------------------------------------
# Spec input
# ---------------------------------------------------------------------------

def frames_from_spec(spec: dict) -> tuple[int, int, list[Frame]]:
    try:
        W, H = spec["canvas"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolError('spec needs "canvas": [width, height]') from exc
    texts = []
    for i, el in enumerate(spec.get("elements") or []):
        if "box" not in el or len(el["box"]) != 4:
            raise ToolError(f"spec element {i} needs a 4-number box [x0, y0, x1, y1] in pixels")
        texts.append(Text(el.get("label") or el.get("role") or f"element {i}", Box(*el["box"]),
                          role=el.get("role") or "other", stroke=el.get("stroke"),
                          background=el.get("background")))
    frames = [Frame(label="overlays", texts=texts, faces=None)]
    shots = spec.get("shots") or []
    for i, shot in enumerate(shots):
        face = Face(Box(*shot["face_box"]), shot.get("eye_y")) if shot.get("face_box") else None
        frames.append(Frame(label=f"shot {i + 1}", faces=[face] if face else [], shot=i))
    if not shots:
        frames[0].faces = []  # nothing declared: the face rules SKIP, they are not unmeasurable
    return W, H, frames


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def verdict(results: list[Result], strict: bool) -> tuple[str, dict]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    failed = counts.get("FAIL", 0) or (strict and counts.get("UNCHECKED", 0))
    return ("FAIL" if failed else "PASS"), counts


def render_table(meta: dict, results: list[Result], v: str, counts: dict) -> str:
    lines = [f"vertical layout check: {meta['input']}  (profile {meta['profile']}, "
             f"detector {meta.get('detector', '-')}, {meta.get('samples', 0)} sample(s))"]
    for r in results:
        lines.append(f"  {r.rule}  {r.name:<26} {r.status:<9} {r.detail}")
        for e in r.evidence:
            lines.append(f"        - {json.dumps(e, ensure_ascii=False)}")
    tally = ", ".join(f"{counts[k]} {k}" for k in ("PASS", "FAIL", "WARN", "SKIP", "N/A", "UNCHECKED") if counts.get(k))
    lines.append(f"VERDICT: {v}  ({tally})")
    for key in ("report", "guide"):
        if meta.get(key):
            lines.append(f"{key}: {meta[key]}")
    return "\n".join(lines)


def emit(args, meta: dict, results: list[Result]) -> int:
    v, counts = verdict(results, args.strict)
    payload = {**meta, "verdict": v, "counts": counts,
               "results": [r.__dict__ for r in results]}
    if args.report:
        Path(args.report).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else render_table(meta, results, v, counts))
    return 1 if v == "FAIL" else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _default_out(inp: str, suffix: str) -> str:
    p = Path(inp)
    return str(p.with_name(f"{p.stem}.{suffix}"))


def cmd_media(args, layout: dict, pname: str, profile: dict, is_video: bool) -> int:
    inputs = [args.input] if is_video else args.inputs
    for i in inputs:
        if not Path(i).exists():
            raise ToolError(f"no such file: {i}")
    with tempfile.TemporaryDirectory(prefix="vlayout-") as tmp:
        if is_video:
            info = probe(args.input)
            W, H = info["w"], info["h"]
            frames = sample_frames(args.input, info["duration"], args.fps, args.max_frames, Path(tmp))
        else:
            infos = [probe(i) for i in inputs]
            sizes = {(d["w"], d["h"]) for d in infos}
            if len(sizes) != 1:
                raise ToolError(f"images differ in size: {sorted(sizes)}")
            (W, H), info = sizes.pop(), {"duration": None}
            frames = [Frame(label=Path(i).name, path=str(Path(i).resolve())) for i in inputs]
        detector = run_detector(args.detector, frames)
        cls = layout["classification"]
        leg = profile.get("legibility") or {}
        measure_legibility(frames, leg.get("contrast_ratio", 3.0), cls["overlay_min_text_height"] * H)
        expect = frozenset(k for k, on in (("title", args.expect_title), ("caption", args.expect_captions)) if on)
        results = evaluate(W, H, frames, profile, cls, layout["canvas"], expect)
        guide = None
        if not args.no_guide:
            guide = args.guide or _default_out(inputs[0], "layout-guide.png")
            write_guide(inputs[0], W, H, info.get("duration"), profile, Path(guide), is_image=not is_video)
    if args.report is None and not args.no_report:
        args.report = _default_out(inputs[0], "layout-report.json")
    meta = {"input": inputs[0] if is_video else inputs, "mode": "video" if is_video else "image",
            "profile": pname, "detector": detector, "canvas": [W, H], "samples": len(frames),
            "report": args.report, "guide": guide}
    return emit(args, meta, results)


def cmd_spec(args, layout: dict, pname: str, profile: dict) -> int:
    try:
        spec = json.loads(Path(args.input).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"cannot read spec {args.input}: {exc}") from exc
    W, H, frames = frames_from_spec(spec)
    results = evaluate(W, H, frames, profile, layout["classification"], layout["canvas"])
    meta = {"input": args.input, "mode": "spec", "profile": pname, "detector": "declared",
            "canvas": [W, H], "samples": len(frames), "report": args.report}
    return emit(args, meta, results)


def cmd_guide(args, layout: dict, pname: str, profile: dict) -> int:
    info = probe(args.input)
    is_image = Path(args.input).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    out = Path(args.out or _default_out(args.input, "layout-guide.png"))
    write_guide(args.input, info["w"], info["h"], info["duration"], profile, out, n=args.frames, is_image=is_image)
    print(f"guide ({pname}): {out}")
    return 0


def zones_table(profile: dict, W: int, H: int) -> str:
    """Markdown table of a profile's zones in pixels; references/vertical-layout.md
    embeds this output verbatim and a test keeps the two identical."""
    safe = zone(profile["safe_zone"], W, H)
    rows = [("Safe zone", safe)]
    rows += [(f"Avoid: {a['name']}", zone(a, W, H)) for a in profile.get("avoid") or []]
    if profile.get("title_band"):
        rows.append(("Title hook band", band(profile["title_band"], safe, H)))
    if profile.get("caption_band"):
        rows.append(("Caption band", band(profile["caption_band"], safe, H)))
    eye = profile.get("eye_line")
    if eye:
        rows.append(("Eye-line band", Box(0, eye["y0"] * H, W, eye["y1"] * H)))
    out = [f"| Zone ({W}x{H}) | x px | y px | x % | y % |", "|---|---|---|---|---|"]
    for name, b in rows:
        x0, y0, x1, y1 = b.as_list()
        out.append(f"| {name} | {x0}-{x1} | {y0}-{y1} | {100 * b.x0 / W:.1f}-{100 * b.x1 / W:.1f} "
                   f"| {100 * b.y0 / H:.1f}-{100 * b.y1 / H:.1f} |")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", type=Path, default=None, help="layout contract JSON (default: layout/vertical-9x16.json)")
    ap.add_argument("--profile", default=None, help="profile name (default: the contract's default_profile)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, media: bool):
        p.add_argument("--report", default=None, help="write the JSON report here")
        p.add_argument("--json", action="store_true", help="print the JSON report instead of the table")
        p.add_argument("--strict", action="store_true", help="UNCHECKED rules fail the run too")
        if media:
            p.add_argument("--detector", default="auto", choices=["auto", "vision", "tesseract"])
            p.add_argument("--guide", default=None, help="guide sheet path (default: <input>.layout-guide.png)")
            p.add_argument("--no-guide", action="store_true")
            p.add_argument("--no-report", action="store_true", help="do not write the default report file")
            p.add_argument("--expect-captions", action="store_true",
                           help="captions were burned in: finding none is a FAIL, not a SKIP")
            p.add_argument("--expect-title", action="store_true",
                           help="a title hook was burned in: finding none is a FAIL, not a SKIP")

    v = sub.add_parser("video", help="sample a video and check it")
    v.add_argument("input")
    v.add_argument("--fps", type=float, default=2.0, help="samples per second (default 2)")
    v.add_argument("--max-frames", type=int, default=120)
    common(v, True)
    im = sub.add_parser("image", help="check one or more frames of the same size")
    im.add_argument("inputs", nargs="+")
    common(im, True)
    sp = sub.add_parser("spec", help="check declared overlay boxes (no detector)")
    sp.add_argument("input")
    common(sp, False)
    g = sub.add_parser("guide", help="paint the zones onto frames for a visual check")
    g.add_argument("input")
    g.add_argument("--out", default=None)
    g.add_argument("--frames", type=int, default=6)
    z = sub.add_parser("zones", help="print the profile's zones in pixels (markdown)")
    z.add_argument("--canvas", default="1080x1920", help="WIDTHxHEIGHT (default 1080x1920)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        layout = load_layout(args.layout)
        pname, profile = get_profile(layout, args.profile)
        if args.cmd == "video":
            return cmd_media(args, layout, pname, profile, is_video=True)
        if args.cmd == "image":
            return cmd_media(args, layout, pname, profile, is_video=False)
        if args.cmd == "spec":
            return cmd_spec(args, layout, pname, profile)
        if args.cmd == "zones":
            try:
                W, H = (int(v) for v in args.canvas.lower().split("x"))
            except ValueError as exc:
                raise ToolError(f"--canvas wants WIDTHxHEIGHT, got {args.canvas!r}") from exc
            print(zones_table(profile, W, H))
            return 0
        return cmd_guide(args, layout, pname, profile)
    except ToolError as exc:
        print(f"check_vertical_layout: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
