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
profile does not define it), UNCHECKED (the detector cannot measure it), WAIVED (a
FAIL the owner waived for this exact file: --waive WAIVERS.json, see "Waivers" in the
reference). Only FAIL fails the run; --strict also fails on UNCHECKED. Exit: 0 ok, 1 FAIL, 2 usage or
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
import re
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

# Waiver policy (references/vertical-layout.md, "Waivers"). No waiver covers these
# rules: a wrong canvas puts every zone in the wrong place, and VL9 FAILs only on a
# stroke the caller declared missing, which is fixed by adding the stroke. Declared
# text that is not found (VL2, VL4, VL5 with --expect-*) is marked per result in
# evaluate(), since the same rules can also FAIL for reasons a waiver may cover.
NEVER_WAIVABLE = {"VL1": "a wrong canvas moves every zone",
                  "VL9": "the stroke is declared missing; add it"}
WAIVER_KEYS = frozenset({"rule", "input_sha256", "reason", "granted_by"})
SHA256_HEX = re.compile(r"[0-9a-f]{64}")


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
    region: str = ""                 # title | caption | other


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
    waivable: bool = True        # False: no waiver may turn this FAIL into WAIVED
    waiver: dict | None = None   # the waiver applied, when status is WAIVED


# ---------------------------------------------------------------------------
# Layout contract
# ---------------------------------------------------------------------------

def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _check_zone(z, where: str, keys=("x0", "y0", "x1", "y1")) -> None:
    if not isinstance(z, dict) or not all(_is_num(z.get(k)) for k in keys):
        raise ToolError(f"layout contract: {where} needs numeric {', '.join(keys)}")
    for lo, hi in (("x0", "x1"), ("y0", "y1")):
        if lo in z and hi in z and not 0 <= z[lo] < z[hi] <= 1:
            raise ToolError(f"layout contract: {where} needs 0 <= {lo} < {hi} <= 1")


def load_layout(path: Path | None = None) -> dict:
    """Read and validate the contract. A malformed contract is a tool error (exit 2),
    never a verdict: a KeyError halfway through `evaluate` would exit 1, the FAIL code."""
    path = path or DEFAULT_LAYOUT
    try:
        layout = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"cannot read layout contract {path}: {exc}") from exc
    try:
        canvas, cls, profiles = layout["canvas"], layout["classification"], layout["profiles"]
        if layout["default_profile"] not in profiles:
            raise ToolError(f"layout contract: default_profile {layout['default_profile']!r} is not a profile")
        if not (_is_num(canvas["aspect_tolerance"]) and _is_num(canvas["min_width"])
                and len(canvas["aspect"]) == 2 and all(_is_num(v) and v > 0 for v in canvas["aspect"])):
            raise ToolError("layout contract: canvas needs aspect [w, h], aspect_tolerance, min_width")
        for key in ("overlay_min_text_height", "title_region_max_centre_y", "max_share_outside"):
            if not (_is_num(cls[key]) and 0 < cls[key] < 1):
                raise ToolError(f"layout contract: classification.{key} must be a number in (0, 1)")
        for name, prof in profiles.items():
            _check_zone(prof["safe_zone"], f"{name}.safe_zone")
            for i, a in enumerate(prof.get("avoid") or []):
                _check_zone(a, f"{name}.avoid[{i}]")
                if not (isinstance(a.get("name"), str) and a["name"]):
                    raise ToolError(f"layout contract: {name}.avoid[{i}] needs a name")
            for key in ("title_band", "caption_band"):
                if prof.get(key) is not None:
                    _check_zone(prof[key], f"{name}.{key}", keys=("y0", "y1"))
                    if "x0" in prof[key] or "x1" in prof[key]:
                        _check_zone(prof[key], f"{name}.{key}")
            cap = prof.get("caption_band")
            if cap is not None and not (_is_num(cap.get("centre_x_tolerance")) and 0 < cap["centre_x_tolerance"] < 0.5):
                raise ToolError(f"layout contract: {name}.caption_band needs a centre_x_tolerance in (0, 0.5)")
            leg = prof.get("legibility")
            if leg is not None and not (isinstance(leg, dict) and _is_num(leg.get("contrast_ratio"))
                                        and leg["contrast_ratio"] >= 1
                                        and _is_num(leg.get("min_halo_contrast_share"))
                                        and 0 < leg["min_halo_contrast_share"] <= 1):
                raise ToolError(f"layout contract: {name}.legibility must be null or an object with "
                                f"contrast_ratio >= 1 and min_halo_contrast_share in (0, 1]")
            eye = prof.get("eye_line")
            if eye is not None and not (isinstance(eye, dict) and all(_is_num(eye.get(k)) for k in (
                    "y0", "y1", "max_shift_across_punch_in", "punch_in_scale_jump"))):
                raise ToolError(f"layout contract: {name}.eye_line must be null or an object with numeric "
                                f"y0, y1, max_shift_across_punch_in, punch_in_scale_jump")
            if eye is not None:
                _check_zone(eye, f"{name}.eye_line", keys=("y0", "y1"))
    except (KeyError, TypeError) as exc:
        raise ToolError(f"layout contract {path} is malformed: missing or mistyped {exc}") from exc
    return layout


def get_profile(layout: dict, name: str | None) -> tuple[str, dict]:
    name = name or layout["default_profile"]
    if name not in layout["profiles"]:
        raise ToolError(f"unknown profile {name!r}; have {sorted(layout['profiles'])}")
    return name, layout["profiles"][name]


def zone(z: dict, W: float, H: float) -> Box:
    return Box(z["x0"] * W, z["y0"] * H, z["x1"] * W, z["y1"] * H)


def band(z: dict, safe: Box, W: float, H: float) -> Box:
    """A horizontal band: its own x range when the contract gives one (the caption
    band stops short of the action rail), else the safe zone's."""
    x0 = z["x0"] * W if "x0" in z else safe.x0
    x1 = z["x1"] * W if "x1" in z else safe.x1
    return Box(x0, z["y0"] * H, x1, z["y1"] * H)


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
    stays there on the next sample. Measuring against the shot median, not the
    previous sample, keeps a subject leaning in (the source reel drifts 14% sample to
    sample inside one shot) from reading as a cut. A one-sample shot is a detector
    glitch or the appended last frame, never a shot: it joins its neighbour."""
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
    if len(segs_l) > 1 and len(segs_l[0]) == 1:
        segs_l[1] = segs_l[0] + segs_l[1]
        segs_l.pop(0)
    merged: list[list] = []
    for seg in segs_l:
        if len(seg) == 1 and merged:
            merged[-1].extend(seg)
        else:
            merged.append(seg)
    return merged


def _seg_label(seg) -> str:
    first, last = seg[0][0].label, seg[-1][0].label
    return first if first == last else f"{first}..{last}"


def evaluate(W: float, H: float, frames: list[Frame], profile: dict, cls: dict,
             canvas_cfg: dict, expect: frozenset = frozenset()) -> list[Result]:
    """Apply VL1-VL9 to detections.

    `expect` holds "title" and/or "caption" when the caller burned that text in. Roles
    come from position, not from what text does (see "Why roles are declared" in
    references/vertical-layout.md), so the expectation is what turns "no text in the
    caption band" into a FAIL: captions moved wholly out of the band, or unreadable
    text that OCR reports as absent. It cannot see a caption set that is only partly
    out of the band; nothing measured here can tell that caption from a label."""
    results: list[Result] = []
    names = dict(RULES)

    def add(rule, status, detail, evidence=None, waivable=True):
        results.append(Result(rule, names[rule], status, detail, (evidence or [])[:MAX_EVIDENCE],
                              waivable and rule not in NEVER_WAIVABLE))

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
    title_rect = band(profile["title_band"], safe, W, H) if profile.get("title_band") else None
    cap_cfg = profile.get("caption_band")
    cap_rect = band(cap_cfg, safe, W, H) if cap_cfg else None

    # Overlay vs scene text ------------------------------------------------
    overlay: list[tuple[Frame, Text]] = []
    scene: list[tuple[Frame, Text]] = []
    for f in frames:
        for t in f.texts:
            (overlay if t.role or t.box.h >= cls["overlay_min_text_height"] * H else scene).append((f, t))

    # Role: declared (spec mode), else position. Text centred in the top region is a
    # title (VL4); text centred in the caption band's rows is a caption (VL5);
    # anything else is a plain overlay held to VL2/VL3. A caption placed anywhere
    # else is caught by --expect-captions, not by guessing from its behaviour.
    for _, t in overlay:
        if t.role:
            t.region = t.role if t.role in ("title", "caption") else "other"
        elif title_rect and t.box.cy <= cls["title_region_max_centre_y"] * H:
            t.region = "title"
        elif cap_rect and cap_rect.y0 <= t.box.cy <= cap_rect.y1:
            t.region = "caption"
        else:
            t.region = "other"
    scene_note = (f"; {len(scene)} small text box(es) under {pct(cls['overlay_min_text_height'] * H, H)} "
                  f"of height treated as scene text") if scene else ""

    def none_found(kind: str, rect: Box | None) -> str:
        # Candidates for a misplaced {kind}: plain overlay text, plus title-band text when
        # captions are missing (captions parked at the top). Captions sitting in their
        # own band are never offered as a misplaced title.
        others = [t for _, t in overlay if t.region == "other" or (kind == "caption" and t.region == "title")]
        if others and rect:
            ys = sorted(round(t.box.cy) for t in others)
            return (f"expected {kind} text in the {kind} band (y {rect.y0:.0f}-{rect.y1:.0f}); none is there, "
                    f"but {len(others)} other overlay box(es) are centred at y {ys[0]}-{ys[-1]}: "
                    f"a {kind} placed outside its band")
        return (f"expected {kind} text; OCR found none: the text is missing or too illegible "
                f"to read, which is itself a legibility failure")

    # VL2 safe zone --------------------------------------------------------
    # An expected title/caption is failed by its own band rule (VL4/VL5); VL2 carries
    # it only for a profile that has no band for it.
    uncovered = sorted(e for e in expect if not {"title": title_rect, "caption": cap_rect}.get(e))
    # No band to look in: any overlay text satisfies the expectation.
    missing = [e for e in uncovered if not overlay]
    where = f"safe zone x {safe.x0:.0f}-{safe.x1:.0f}, y {safe.y0:.0f}-{safe.y1:.0f}"
    bad = [(f, t) for f, t in overlay
           if not t.box.inside(safe, slack)
           and not (t.region == "title" and title_rect and t.box.inside(title_rect, slack))]
    if bad or missing:
        detail = "; ".join(
            ([f"{len(bad)}/{len(overlay)} overlay text box(es) leave the {where}"] if bad else [])
            + [none_found(e, None) for e in missing])
        add("VL2", "FAIL", detail + scene_note, [_ev(f, t) for f, t in bad], waivable=not missing)
    elif not overlay:
        add("VL2", "SKIP", "no overlay text found" + scene_note)
    else:
        extra = " (title band excepted)" if title_rect else ""
        add("VL2", "PASS", f"{len(overlay)} overlay text box(es) inside the {where}{extra}" + scene_note)

    # Faces, per shot ------------------------------------------------------
    eye_cfg = profile.get("eye_line") or {}
    faces_seen = any(f.faces is not None for f in frames)
    face_frames = [(f, _primary_face(f)) for f in frames if _primary_face(f)]
    segs = punch_in_segments(face_frames, eye_cfg.get("punch_in_scale_jump", 0.12))

    def seg_face(seg) -> Box:
        return Box(*(statistics.median(getattr(face.box, k) for _, face in seg) for k in ("x0", "y0", "x1", "y1")))

    max_out = cls["max_share_outside"]

    def seg_violates(seg, bad_sample) -> str:
        """A shot violates when its median face does, or when more than `max_out` of
        its samples do: the median alone hides a face that drifts out for 4 of 10."""
        if bad_sample(seg_face(seg)):
            return "median face"
        share = sum(bool(bad_sample(face.box)) for _, face in seg) / len(seg)
        return f"{share:.0%} of samples" if share > max_out else ""

    # VL3 avoid zones ------------------------------------------------------
    avoid = [(a["name"], zone(a, W, H)) for a in profile.get("avoid") or []]
    if not avoid:
        add("VL3", "N/A", "profile defines no avoid zones")
    else:
        hits, small = [], []
        for f, t in overlay:
            hits += [_ev(f, t, name) for name, rect in avoid if t.box.intersects(rect)]
        for seg in segs:
            for name, rect in avoid:
                how = seg_violates(seg, rect.intersects)
                if how:
                    hits.append({"at": _seg_label(seg), "face": seg_face(seg).as_list(), "why": f"{name} ({how})"})
        for f, t in scene:
            small += [_ev(f, t, f"{name} (small text: an overlay, or text in the footage?)")
                      for name, rect in avoid if t.box.intersects(rect)]
        faces_note = "" if faces_seen else " (faces not measured by this detector)"
        checked = len(overlay) + len(segs) + len(scene)
        if hits:
            add("VL3", "FAIL", f"{len(hits)} element(s) touch an avoid zone{faces_note}", hits + small)
        elif small:
            add("VL3", "WARN", f"{len(small)} small text box(es) touch an avoid zone: a handle, link or "
                               f"watermark there is covered by the platform UI; confirm on the guide sheet{faces_note}",
                small)
        elif not checked:
            add("VL3", "SKIP", "no text found" + (" and no face found" if faces_seen else faces_note))
        else:
            add("VL3", "PASS", f"{checked} element(s) clear of {', '.join(n for n, _ in avoid)}{faces_note}")

    # VL4 title hook band --------------------------------------------------
    if not title_rect:
        add("VL4", "N/A", "profile defines no title band")
    else:
        titles = [(f, t) for f, t in overlay if t.region == "title"]
        span = f"y {title_rect.y0:.0f}-{title_rect.y1:.0f} ({pct(title_rect.y0, H)}-{pct(title_rect.y1, H)})"
        if not titles and "title" in expect:
            add("VL4", "FAIL", none_found("title", title_rect), waivable=False)
        elif not titles:
            add("VL4", "SKIP", "no title-hook text found")
        else:
            bad = [(f, t) for f, t in titles if not t.box.inside(title_rect, slack)]
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
        span = (f"x {cap_rect.x0:.0f}-{cap_rect.x1:.0f}, y {cap_rect.y0:.0f}-{cap_rect.y1:.0f} "
                f"({pct(cap_rect.y0, H)}-{pct(cap_rect.y1, H)})")
        if not caps and "caption" in expect:
            add("VL5", "FAIL", none_found("caption", cap_rect), waivable=False)
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
            if bad:
                add("VL5", "FAIL", f"{len(bad)} caption problem(s): boxes must sit in {span} with the median "
                                   f"centre within +/-{tol:.0f}px", bad)
            else:
                cys = [t.box.cy for _, t in caps]
                stray = f"; {strays} box(es) off-centre on their own (partial OCR reads)" if strays else ""
                add("VL5", "PASS", f"{len(caps)} caption box(es) in {span}, median centre {med_dx:+.0f}px; centre y "
                                   f"{min(cys):.0f}-{max(cys):.0f} ({pct(min(cys), H)}-{pct(max(cys), H)}){stray}")

    # VL6 eye line, VL7 punch-ins ------------------------------------------
    no_faces_detector = "detector reports no faces (tesseract); run on macOS (Vision) or check the guide sheet by eye"
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
        measured = []
        for seg in segs:
            ys = [face.eye_y for _, face in seg if face.eye_y is not None]
            if ys:
                measured.append((seg, statistics.median(ys), sum(not lo <= y <= hi for y in ys) / len(ys)))
        blind = len(segs) - len(measured)
        blind_note = f"; {blind} shot(s) without eye landmarks not judged" if blind else ""
        span = f"y {lo:.0f}-{hi:.0f} ({pct(lo, H)}-{pct(hi, H)})"
        if not measured:
            add("VL6", "UNCHECKED", "faces found but no eye landmarks")
        else:
            limit_share = max_out
            bad = [{"at": _seg_label(seg), "eye_y": round(y), "outside": f"{out:.0%}"}
                   for seg, y, out in measured if not lo <= y <= hi or out > limit_share]
            if bad:
                add("VL6", "FAIL", f"{len(bad)}/{len(measured)} shot(s) put the eyes outside {span} "
                                   f"(median, or more than {limit_share:.0%} of samples){blind_note}", bad)
            else:
                ys = [y for _, y, _ in measured]
                add("VL6", "PASS", f"eye line {min(ys):.0f}-{max(ys):.0f}px ({pct(min(ys), H)}-{pct(max(ys), H)}) "
                                   f"across {len(measured)} shot(s), inside {span}{blind_note}")
        if len(measured) < 2 and len(segs) >= 2:
            add("VL7", "UNCHECKED", "fewer than two shots have eye landmarks")
        elif len(measured) < 2:
            add("VL7", "SKIP", f"no punch-in or cut found (face-scale change >= {eye_cfg['punch_in_scale_jump']:.0%})")
        else:
            # WARN, never FAIL: a face-scale change is a punch-in or a cut to another
            # shot, and face geometry cannot tell them apart (two centred speakers look
            # like a punch-in). The rule is the Reel's for punch-ins; the reader decides.
            limit = eye_cfg["max_shift_across_punch_in"] * H
            cuts = []
            for (sa, ya, _), (sb, yb, _) in zip(measured, measured[1:]):
                cuts.append({"at": f"{_seg_label(sa)} -> {_seg_label(sb)}", "shift_px": round(yb - ya),
                             "face_dx_px": round(seg_face(sb).cx - seg_face(sa).cx)})
            over = [c for c in cuts if abs(c["shift_px"]) > limit]
            if over:
                add("VL7", "WARN", f"eye line moves more than {limit:.0f}px ({pct(limit, H)}) across {len(over)} "
                                   f"scale change(s): a punch-in should be scaled about the eye line; a cut to "
                                   f"another shot is fine. Check the guide sheet", cuts)
            else:
                worst = max(abs(c["shift_px"]) for c in cuts)
                add("VL7", "PASS", f"{len(cuts)} cut(s); largest eye-line shift {worst}px, limit {limit:.0f}px", cuts)

    # VL8 subject in safe zone ---------------------------------------------
    if not faces_seen:
        add("VL8", "UNCHECKED", no_faces_detector)
    elif not face_frames:
        add("VL8", "SKIP", "no face found")
    else:
        bad = []
        for seg in segs:
            how = seg_violates(seg, lambda b: not b.inside(safe, slack))
            if how:
                bad.append({"at": _seg_label(seg), "face": seg_face(seg).as_list(), "why": how})
        if bad:
            add("VL8", "FAIL", f"the face leaves the safe zone in {len(bad)} shot(s)", bad)
        else:
            add("VL8", "PASS", f"face inside the safe zone across {len(segs)} shot(s)")

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
              "stream=width,height:stream_side_data=rotation:stream_tags=rotate:format=duration",
              "-of", "json", path], text=True)
    if p.returncode != 0:
        raise ToolError(f"ffprobe failed on {path}: {p.stderr.strip()}")
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError(f"ffprobe returned unreadable output for {path}") from exc
    streams = data.get("streams") or []
    if not streams:
        raise ToolError(f"no video stream in {path}")
    st = streams[0]
    w, h = int(st["width"]), int(st["height"])
    # Phone footage is often stored landscape with a rotation flag; ffmpeg decodes it
    # upright, so the canvas the viewer sees is the swapped one.
    rotation = st.get("tags", {}).get("rotate")
    for sd in st.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = sd["rotation"]
    try:
        if int(float(rotation or 0)) % 180 != 0:
            w, h = h, w
    except ValueError:
        pass
    dur = data.get("format", {}).get("duration")
    return {"w": w, "h": h, "duration": float(dur) if dur not in (None, "N/A") else None}


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
            parts.append(box(band(profile[key], safe, W, H), "yellow@0.9", "4"))
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
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ToolError(f"cannot create the cache dir {d}: {exc}") from exc
    return d


def vision_binary() -> tuple[Path | None, str]:
    """(binary, why-not). The reason is reported, never swallowed: a Vision build that
    fails would otherwise fall back to tesseract and quietly drop the face rules."""
    if sys.platform != "darwin":
        return None, "macOS Vision needs darwin"
    if not shutil.which("swiftc"):
        return None, "macOS Vision needs swiftc (xcode-select --install)"
    if not VISION_SRC.exists():
        return None, f"missing {VISION_SRC}"
    digest = hashlib.sha256(VISION_SRC.read_bytes()).hexdigest()[:12]
    binary = _cache_dir() / f"vision_probe-{digest}"
    if not binary.exists():
        p = _run(["swiftc", "-O", str(VISION_SRC), "-o", str(binary)], text=True)
        if p.returncode != 0:
            return None, f"swiftc failed to build vision_probe: {p.stderr.strip()[-300:]}"
    return binary, ""


def detect_vision(binary: Path, frames: list[Frame]) -> None:
    by_path = {f.path: f for f in frames}
    p = _run([str(binary), *by_path], text=True)
    if p.returncode != 0:
        raise ToolError(f"vision_probe failed: {p.stderr.strip()[-400:]}")
    seen = 0
    for line in p.stdout.splitlines():
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ToolError(f"vision_probe printed an unreadable line: {line[:120]!r}") from exc
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
    # Left to right: sorting by top edge first put "Tide" (capital, taller) ahead of
    # "was", and "was" then started a line of its own.
    for text, b in sorted(words, key=lambda w: (w[1].x0, w[1].y0)):
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
        f.texts = parse_tesseract_tsv(p.stdout, min_conf)
        f.faces = None


def parse_tesseract_tsv(tsv: str, min_conf: float = 60.0) -> list[Text]:
    """Word rows of `tesseract ... tsv` -> line boxes. Busy footage makes tesseract
    read texture as words: rows with no letter or digit are dropped, and a single
    glyph must be near-certain (conf >= 85) to count."""
    words = []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or not _is_words(cols[11]):
            continue
        try:
            conf = float(cols[10])
            x, y, w, h = (int(c) for c in cols[6:10])
        except ValueError:
            continue
        if conf < min_conf or (sum(ch.isalnum() for ch in cols[11]) < 2 and conf < 85):
            continue
        words.append((cols[11].strip(), Box(x, y, x + w, y + h)))
    return _merge_words(words)


def run_detector(name: str, frames: list[Frame]) -> tuple[str, str]:
    """Run the named detector over the frames; returns (detector, note). The note says
    why Vision was not used when `auto` fell back, so a report never hides it."""
    note = ""
    if name in ("auto", "vision"):
        binary, why = vision_binary()
        if binary:
            detect_vision(binary, frames)
            return "vision", ""
        if name == "vision":
            raise ToolError(f"macOS Vision is unavailable: {why}")
        note = f"Vision unavailable ({why}); tesseract has no face detector, so VL6-VL8 are UNCHECKED"
        if sys.platform == "darwin":
            print(f"check_vertical_layout: warning: {note}", file=sys.stderr)
    if name in ("auto", "tesseract"):
        if shutil.which("tesseract"):
            detect_tesseract(frames)
            return "tesseract", note
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

SPEC_KEYS = {"canvas", "elements", "shots"}
SPEC_ROLES = {"title", "caption", "watermark", "logo", "cta", "handle", "label", "other"}
SPEC_ELEMENT_KEYS = {"role", "label", "box", "stroke", "background"}
SPEC_SHOT_KEYS = {"eye_y", "face_box"}
BACKGROUNDS = {"busy", "calm"}


def _spec_box(v, where: str) -> Box:
    if not isinstance(v, list) or len(v) != 4 or not all(_is_num(c) for c in v):
        raise ToolError(f"spec {where} needs a box of 4 numbers [x0, y0, x1, y1] in pixels")
    b = Box(*(float(c) for c in v))
    if not (b.x0 < b.x1 and b.y0 < b.y1):
        raise ToolError(f"spec {where} box needs x0 < x1 and y0 < y1, got {v}")
    return b


def frames_from_spec(spec) -> tuple[int, int, list[Frame]]:
    """Validate a declared-overlay spec and turn it into frames. Anything malformed
    is a ToolError (exit 2): an exception escaping here would exit 1, which reads as
    a FAIL verdict, and an unknown key (a typo) would otherwise check nothing."""
    if not isinstance(spec, dict):
        raise ToolError("spec must be a JSON object")
    unknown = set(spec) - SPEC_KEYS
    if unknown:
        raise ToolError(f"spec has unknown key(s) {sorted(unknown)}; allowed: {sorted(SPEC_KEYS)}")
    canvas = spec.get("canvas")
    if not (isinstance(canvas, list) and len(canvas) == 2
            and all(_is_num(v) and v >= 1 and float(v).is_integer() for v in canvas)):
        raise ToolError('spec needs "canvas": [width, height] as whole numbers of pixels')
    W, H = int(canvas[0]), int(canvas[1])
    elements, shots = spec.get("elements", []), spec.get("shots", [])
    if not isinstance(elements, list) or not isinstance(shots, list):
        raise ToolError('spec "elements" and "shots" must be lists')
    if not elements and not shots:
        raise ToolError("spec declares no elements and no shots: there is nothing to check")
    texts = []
    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            raise ToolError(f"spec element {i} must be an object")
        bad_keys = set(el) - SPEC_ELEMENT_KEYS
        if bad_keys:
            raise ToolError(f"spec element {i} has unknown key(s) {sorted(bad_keys)}")
        box = _spec_box(el.get("box"), f"element {i}")
        role = str(el.get("role") or "other").strip().lower()
        if role not in SPEC_ROLES:
            raise ToolError(f"spec element {i} role {el.get('role')!r} is not one of {sorted(SPEC_ROLES)}")
        background = el.get("background")
        if background is not None:
            background = str(background).strip().lower()
            if background not in BACKGROUNDS:
                raise ToolError(f"spec element {i} background must be one of {sorted(BACKGROUNDS)}")
        stroke = el.get("stroke")
        if stroke is not None and not isinstance(stroke, bool):
            raise ToolError(f"spec element {i} stroke must be true or false")
        texts.append(Text(str(el.get("label") or role or f"element {i}"), box, role=role,
                          stroke=stroke, background=background))
    frames = [Frame(label="overlays", texts=texts, faces=None)]
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict) or set(shot) - SPEC_SHOT_KEYS:
            raise ToolError(f"spec shot {i} must be an object with {sorted(SPEC_SHOT_KEYS)}")
        if "face_box" not in shot:
            raise ToolError(f"spec shot {i} needs a face_box (eye_y alone places no face)")
        eye = shot.get("eye_y")
        if eye is not None and not _is_num(eye):
            raise ToolError(f"spec shot {i} eye_y must be a number")
        face = Face(_spec_box(shot["face_box"], f"shot {i} face_box"), float(eye) if eye is not None else None)
        frames.append(Frame(label=f"shot {i + 1}", faces=[face], shot=i))
    if not shots:
        frames[0].faces = []  # nothing declared: the face rules SKIP, they are not unmeasurable
    return W, H, frames


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def load_waivers(path: str | None) -> tuple[list[dict], str | None]:
    """Read an owner's waiver file and return its waivers and its sha256.

    The file is {"waivers": [{"rule", "input_sha256", "reason", "granted_by"}, ...]}.
    Whatever the policy forbids is a usage error (exit 2), never a silent skip: a
    never-waivable rule, an empty reason or grantor, a malformed sha256, an unknown
    key. The sha256 is of the bytes parsed here, so the report names the exact file."""
    if path is None:
        return [], None
    try:
        raw = Path(path).read_bytes()
        doc = json.loads(raw)
    except (OSError, ValueError, RecursionError) as exc:
        raise ToolError(f"cannot read the waiver file {path}: {exc!r}") from exc
    if not isinstance(doc, dict) or set(doc) != {"waivers"} or not isinstance(doc["waivers"], list):
        raise ToolError(f'{path}: a waiver file is {{"waivers": [...]}} and nothing else')
    known = {rule for rule, _ in RULES}
    seen: set[tuple[str, str]] = set()
    for i, w in enumerate(doc["waivers"]):
        where = f"{path}: waivers[{i}]"
        if not isinstance(w, dict) or set(w) != WAIVER_KEYS or not all(isinstance(v, str) for v in w.values()):
            raise ToolError(f"{where} needs exactly {sorted(WAIVER_KEYS)}, all strings")
        if w["rule"] not in known:
            raise ToolError(f"{where}: unknown rule {w['rule']!r}")
        if w["rule"] in NEVER_WAIVABLE:
            raise ToolError(f"{where}: {w['rule']} cannot be waived ({NEVER_WAIVABLE[w['rule']]})")
        if not SHA256_HEX.fullmatch(w["input_sha256"]):
            raise ToolError(f"{where}: input_sha256 must be the lowercase 64-hex sha256 of the waived file")
        if not w["reason"].strip() or not w["granted_by"].strip():
            raise ToolError(f"{where}: reason and granted_by must not be empty")
        if (w["rule"], w["input_sha256"]) in seen:
            raise ToolError(f"{where}: a second waiver for {w['rule']} on the same file")
        seen.add((w["rule"], w["input_sha256"]))
    return doc["waivers"], hashlib.sha256(raw).hexdigest()


WAIVER_OUTCOMES = {
    "applied": "turned this file's FAIL into WAIVED",
    "refused": "not applied: this FAIL is never waivable (declared text not found)",
    "no-fail": "not applied: the rule did not FAIL on this file",
    "other-input": "not applied: bound to another file's sha256",
}


def apply_waivers(results: list[Result], waivers: list[dict], input_sha: str | None) -> list[dict]:
    """Apply the waivers bound to this input's sha256; return each with its outcome
    (a key of WAIVER_OUTCOMES). A waiver covers its rule's FAIL on that one file."""
    log = []
    for w in waivers:
        outcome = "other-input"
        if w["input_sha256"] == input_sha:
            r = next((r for r in results if r.rule == w["rule"] and r.status == "FAIL"), None)
            if r is None:
                outcome = "no-fail"
            elif not r.waivable:
                outcome = "refused"
            else:
                outcome = "applied"
                r.status, r.waiver = "WAIVED", {"reason": w["reason"], "granted_by": w["granted_by"]}
                r.detail = f"waived by {w['granted_by']} ({w['reason']}): {r.detail}"
        log.append({**w, "outcome": outcome})
    return log


def verdict(results: list[Result], strict: bool) -> tuple[str, dict]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    failed = counts.get("FAIL", 0) or (strict and counts.get("UNCHECKED", 0))
    return ("FAIL" if failed else "PASS"), counts


def render_table(meta: dict, results: list[Result], v: str, counts: dict) -> str:
    declared = meta.get("declared")
    lines = [f"vertical layout check: {meta['input']}  (profile {meta['profile']}, "
             f"detector {meta.get('detector', '-')}, {meta.get('samples', 0)} sample(s))"]
    if declared is not None:
        # The verdict means little without this: undeclared captions are not checked.
        lines.append(f"  declared: {', '.join(declared) if declared else 'none (captions and title not checked for presence)'}")
    if meta.get("detector_note"):
        lines.append(f"  note: {meta['detector_note']}")
    for r in results:
        lines.append(f"  {r.rule}  {r.name:<26} {r.status:<9} {r.detail}")
        for e in r.evidence:
            lines.append(f"        - {json.dumps(e, ensure_ascii=False)}")
    tally = ", ".join(f"{counts[k]} {k}" for k in ("PASS", "FAIL", "WAIVED", "WARN", "SKIP", "N/A", "UNCHECKED")
                      if counts.get(k))
    if meta.get("waiver_file"):
        lines.append(f"  waivers: {meta['waiver_file']['path']} (sha256 {meta['waiver_file']['sha256']})")
    for w in meta.get("waivers") or []:
        if w["outcome"] != "applied":
            lines.append(f"  note: waiver {w['rule']} from {w['granted_by']} {WAIVER_OUTCOMES[w['outcome']]}")
    for key in ("report", "guide"):
        if meta.get(key):
            lines.append(f"{key}: {meta[key]}")
    lines.append(f"VERDICT: {v}  ({tally})")  # last line, always: `tail -1` reads the verdict
    return "\n".join(lines)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError as exc:
        raise ToolError(f"cannot read {path} to fingerprint it: {exc}") from exc
    return h.hexdigest()


def emit(args, meta: dict, results: list[Result], waivers: tuple[list[dict], str | None],
         input_sha: str | None) -> int:
    entries, waiver_sha = waivers
    meta = {**meta, "waivers": apply_waivers(results, entries, input_sha),
            "waiver_file": {"path": args.waive, "sha256": waiver_sha} if args.waive else None}
    v, counts = verdict(results, args.strict)
    payload = {**meta, "verdict": v, "counts": counts,
               "results": [r.__dict__ for r in results]}
    if args.report:
        try:
            Path(args.report).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise ToolError(f"cannot write the report {args.report}: {exc}") from exc
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
    waivers = load_waivers(args.waive)  # a bad waiver file is exit 2 before any work
    if args.waive and len(inputs) != 1:
        raise ToolError("a waiver binds to one file's sha256; check waived stills one at a time")
    if args.waive and args.no_report:
        raise ToolError("--waive needs the report: the report is where waivers are logged")
    # Hashed before and again after every read (sampling, detection, guide): a file
    # replaced mid-run is an error, not a verdict on a mix of two files. A file swapped
    # and put back between the two hashes is not seen.
    input_sha = {i: sha256_of(Path(i)) for i in inputs}
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
        detector, detector_note = run_detector(args.detector, frames)
        cls = layout["classification"]
        leg = profile.get("legibility") or {}
        measure_legibility(frames, leg.get("contrast_ratio", 3.0), cls["overlay_min_text_height"] * H)
        expect = frozenset(k for k, on in (("title", args.expect_title), ("caption", args.expect_captions)) if on)
        results = evaluate(W, H, frames, profile, cls, layout["canvas"], expect)
        guide = None
        if not args.no_guide:
            guide = args.guide or _default_out(inputs[0], "layout-guide.png")
            write_guide(inputs[0], W, H, info.get("duration"), profile, Path(guide), is_image=not is_video)
    if {i: sha256_of(Path(i)) for i in inputs} != input_sha:
        raise ToolError("the input changed while it was being checked; re-run on the finished file")
    if args.report is None and not args.no_report:
        args.report = _default_out(inputs[0], "layout-report.json")
    meta = {"input": inputs[0] if is_video else inputs, "mode": "video" if is_video else "image",
            "profile": pname, "detector": detector, "canvas": [W, H], "samples": len(frames),
            "declared": sorted(expect), "report": args.report, "guide": guide,
            # Which bytes this verdict is about: a report beside a re-rendered file
            # describes the old render, and the sha says so.
            "input_sha256": input_sha,
            "contract_sha256": sha256_of(Path(args.layout or DEFAULT_LAYOUT))}
    if detector_note:
        meta["detector_note"] = detector_note
    return emit(args, meta, results, waivers, input_sha[inputs[0]] if len(inputs) == 1 else None)


def cmd_spec(args, layout: dict, pname: str, profile: dict) -> int:
    waivers = load_waivers(args.waive)
    if args.waive and args.report is None:  # waivers are logged in the report, so write one
        args.report = _default_out(args.input, "layout-report.json")
    try:
        raw = Path(args.input).read_bytes()  # hashed and parsed from the same bytes
        spec = json.loads(raw)
    except (OSError, ValueError, RecursionError) as exc:
        raise ToolError(f"cannot read spec {args.input}: {exc!r}") from exc
    input_sha = hashlib.sha256(raw).hexdigest()
    W, H, frames = frames_from_spec(spec)
    results = evaluate(W, H, frames, profile, layout["classification"], layout["canvas"])
    meta = {"input": args.input, "mode": "spec", "profile": pname, "detector": "declared",
            "canvas": [W, H], "samples": len(frames), "report": args.report,
            "input_sha256": {args.input: input_sha},
            "contract_sha256": sha256_of(Path(args.layout or DEFAULT_LAYOUT))}
    return emit(args, meta, results, waivers, input_sha)


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
        rows.append(("Title hook band", band(profile["title_band"], safe, W, H)))
    if profile.get("caption_band"):
        rows.append(("Caption band", band(profile["caption_band"], safe, W, H)))
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
        p.add_argument("--waive", action="append", metavar="WAIVERS.json",
                       help="the owner's waiver file: each entry binds one rule to one file's sha256, with "
                            "a reason and who granted it; see references/vertical-layout.md, 'Waivers'. "
                            "Implies a report")
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
        if getattr(args, "waive", None) is not None:
            if len(args.waive) > 1:
                raise ToolError("--waive takes one file; put every waiver in it")
            args.waive = args.waive[0]
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
            if W < 1 or H < 1:
                raise ToolError(f"--canvas needs positive sizes, got {args.canvas!r}")
            print(zones_table(profile, W, H))
            return 0
        return cmd_guide(args, layout, pname, profile)
    except ToolError as exc:
        print(f"check_vertical_layout: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
