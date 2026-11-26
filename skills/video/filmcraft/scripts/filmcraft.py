#!/usr/bin/env python3
"""filmcraft — thin terminal-first video production router and delivery gate runner.

Unites Broomva's modular video skills without duplicating them:
  - Reference dissection : workspace `scripts/video_ingest.py` + `ffprobe`
  - Raw recorded footage : `video-cut` (Whisper + unheard.py + editPlan.json)
  - Code-first motion    : `motion-lab` (render.mjs + video_qa.py)
  - Visual style systems : `liquid-midnight` | `liquid-dawn`
  - Sound & delivery QA  : `soundcraft` (audio_qa.py check/sheet/pad-sidechain)

Pure Python stdlib only. Zero third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

REQUIRED_TOOLS: tuple[str, ...] = ("ffmpeg", "ffprobe", "node", "python3")
OPTIONAL_TOOLS: tuple[str, ...] = ("yt-dlp", "whisper-cli", "playwright", "earshot")
SIBLING_SKILLS: tuple[str, ...] = (
    "video-cut",
    "motion-lab",
    "liquid-midnight",
    "liquid-dawn",
    "soundcraft",
)

SKILL_KEY_SCRIPTS: dict[str, tuple[str, ...]] = {
    "video-cut": ("scripts/transcribe_local.py", "scripts/unheard.py", "scripts/render.py"),
    "motion-lab": ("scripts/motion_lint.py", "scripts/render.mjs", "scripts/video_qa.py"),
    "liquid-midnight": ("scripts/materialize.mjs",),
    "liquid-dawn": (),
    "soundcraft": ("scripts/audio_qa.py",),
}

TOOL_HINTS: dict[str, str] = {
    "ffmpeg": "Install ffmpeg (macOS: `brew install ffmpeg`; Ubuntu: `sudo apt-get install ffmpeg`).",
    "ffprobe": "Install ffprobe (bundled with ffmpeg).",
    "node": "Install Node.js >= 20 (macOS: `brew install node` or nvm).",
    "python3": "Install Python >= 3.11.",
    "yt-dlp": "Optional (for URL reference ingest): `brew install yt-dlp` or `pip install yt-dlp`.",
    "whisper-cli": "Optional (for local raw-footage ASR): `brew install whisper-cpp` or use faster_whisper in video-cut.",
    "playwright": "Optional (for motion-lab browser rendering): `npm i -D playwright && npx playwright install chromium`.",
    "earshot": "Optional (for soundcraft MIT audio craft tooling): install earshot CLI or use soundcraft/scripts/audio_qa.py.",
}

DEFAULT_DUR_TOLERANCE_SEC = 0.5
GATE_TIMEOUT_SEC = 300

# --- Routing signal patterns (deterministic, word-boundary safe) ---

_REF_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("url", re.compile(r"https?://\S+", re.IGNORECASE)),
    ("reference", re.compile(r"\b(?:reference|ref\s+video|ref\s+clip)\b", re.IGNORECASE)),
    ("dissect", re.compile(r"\b(?:dissect|breakdown|reverse[- ]engineer|analyze\s+this\s+video|mimic|recreate)\b", re.IGNORECASE)),
    ("video_host", re.compile(r"\b(?:youtube|youtu\.be|vimeo|tiktok)\b", re.IGNORECASE)),
)

_FOOTAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("footage", re.compile(r"\b(?:raw\s+footage|footage|raw\s+clips?|recorded\s+clips?|clips)\b", re.IGNORECASE)),
    ("talking_head", re.compile(r"\b(?:talking[- ]head|interview|webcam|screen\s+recording|vlog|camera\s+roll)\b", re.IGNORECASE)),
    ("editorial_cut", re.compile(r"\b(?:retakes?|filler\s+words?|dead[- ]air|trim\s+(?:this|the|my)?\s*(?:recording|video|clip|footage)|cut\s+these|unheard|editplan|edl|video-cut)\b", re.IGNORECASE)),
    ("video_recording", re.compile(r"\b(?:video\s+recordings?|screen\s+recordings?|camera\s+recordings?)\b", re.IGNORECASE)),
)

_MOTION_SPECIFIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("launch_film", re.compile(r"\b(?:launch\s+film|launch\s+video|product\s+launch|keynote\s+video|keynote)\b", re.IGNORECASE)),
    ("animation", re.compile(r"\b(?:motion[- ]lab|motion\s+design|animat(?:e|ed|ion|ions)|kinetic|title\s+card|logo\s+reveal|explainer|animated\s+loop|loop)\b", re.IGNORECASE)),
    ("code_render", re.compile(r"\b(?:code[- ]first|webgl|shader|canvas|remotion|renderat|three\.?js|gsap|svg\s+animation|overlay|overlays)\b", re.IGNORECASE)),
    ("short_form_motion", re.compile(r"\b(?:reel|teaser|promo|product\s+demo|demo\s+video)\b", re.IGNORECASE)),
)

_GENERIC_VIDEO_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("film", re.compile(r"\b(?:film|movie|trailer|spot|commercial)\b", re.IGNORECASE)),
    ("video", re.compile(r"\b(?:video|mp4|edit\s+video)\b", re.IGNORECASE)),
)

_STYLE_MIDNIGHT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("liquid-midnight", re.compile(r"\b(?:liquid[- ]midnight|midnight\s+blue|chrome\s+rim|metal\s+rim|plasma\s+orb|orbloom|agent\s+workspaces)\b", re.IGNORECASE)),
)

_STYLE_DAWN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("liquid-dawn", re.compile(r"\b(?:liquid[- ]dawn|warm\s+paper|pearl\s+rim|daylight\s+glass|light\s+liquid\s+glass)\b", re.IGNORECASE)),
)

_AUDIO_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sound", re.compile(r"\b(?:sound|soundcraft|soundtrack|sfx|foley|earshot)\b", re.IGNORECASE)),
    ("audio_mix", re.compile(r"\b(?:audio|music|score|voiceover|voice[- ]over|\bvo\b|narration|narrate|dialogue|lufs|sidechain|pad[- ]sidechain|mix|master|podcast|wav)\b", re.IGNORECASE)),
    ("rhythm", re.compile(r"\b(?:bpm|beat[- ]synced?|on\s+the\s+beat)\b", re.IGNORECASE)),
)

_NEGATED_AUDIO_RX = re.compile(r"\b(?:no|without)\s+(?:audio|sound|soundtrack|music)\b", re.IGNORECASE)
_NUM_PHRASE = r"(?:\d+(?:\.\d+)?|(?:a\s+few|a\s+couple(?:\s+of)?|half\s+a|several|[a-z]+(?:[- ][a-z]+)?))"
_DUR_UNIT = r"(?:s|sec|secs|second|seconds|m|min|mins|minute|minutes)"
_DUR_TAIL = rf"(?:\s+(?:for|during|of))?(?:\s+(?:the|about|around))?\s+{_NUM_PHRASE}\s*{_DUR_UNIT}"
_SECTION_NOUN = r"(?:intro|outro|opening|ending|beginning|start|end|section|segment|part|beat|pause|moment|cut|cuts|gap|gaps|first|last|final)"
_SECTION_SILENT_RX = re.compile(
    rf"\b(?:"
    rf"(?:silent|muted?)\s+(?:the\s+)?{_SECTION_NOUN}(?:{_DUR_TAIL})?\b"
    rf"|(?:no|without)\s+(?:audio|sound|soundtrack|music)\s+(?:in|on|during|for|at)\s+(?:the\s+)?(?:{_SECTION_NOUN}(?:{_DUR_TAIL})?|{_NUM_PHRASE}\s*{_DUR_UNIT})\b"
    rf")",
    re.IGNORECASE,
)
_SILENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("no_audio", _NEGATED_AUDIO_RX),
    ("muted", re.compile(r"\b(?:muted|mute)\b", re.IGNORECASE)),
    ("silent_deliverable", re.compile(r"\bsilent\b", re.IGNORECASE)),
)

_PRODUCE_VERBS = re.compile(
    r"\b(?:make|build|create|produce|recreate|render|generate|shoot|cut|edit|ship|turn)\b",
    re.IGNORECASE,
)

_DURATION_SEC_RX = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b", re.IGNORECASE)
_DURATION_MIN_RX = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes)\b", re.IGNORECASE)


def _match_patterns(text: str, patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> list[str]:
    hits: list[str] = []
    for label, rx in patterns:
        if rx.search(text):
            hits.append(label)
    return hits


def _extract_duration_sec(text: str) -> float | None:
    m = _DURATION_SEC_RX.search(text)
    if m:
        return float(m.group(1))
    m_min = _DURATION_MIN_RX.search(text)
    if m_min:
        return float(m_min.group(1)) * 60.0
    return None


def _default_skill_roots() -> list[Path]:
    """Return candidate skill roots when `--skills-root` is not explicitly given."""
    roots: list[Path] = []
    env_root = os.environ.get("FILMCRAFT_SKILLS_ROOT")
    if env_root:
        roots.append(Path(env_root).expanduser())
    home_skills = Path.home() / ".agents" / "skills"
    roots.append(home_skills)
    here = Path(__file__).resolve()
    if len(here.parents) >= 4 and here.parents[3].name == "skills":
        repo_skills = here.parents[3]
        if repo_skills not in roots:
            roots.append(repo_skills)
    return roots


def _looks_like_skill_dir(path: Path) -> bool:
    return path.is_dir() and ((path / "SKILL.md").is_file() or (path / "scripts").is_dir())


def _search_skill_in_root(skill_name: str, root: Path) -> Path | None:
    """Search one root for `<root>/<skill>`, `<root>/<cat>/<skill>`, or `<root>/skills/<cat>/<skill>`."""
    if not root.is_dir():
        return None
    direct = root / skill_name
    if _looks_like_skill_dir(direct):
        return direct
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if child.name.startswith(".") or not child.is_dir():
            continue
        candidate = child / skill_name
        if _looks_like_skill_dir(candidate):
            return candidate
    nested_skills = root / "skills"
    if nested_skills.is_dir():
        for cat in sorted(nested_skills.iterdir(), key=lambda p: p.name):
            if cat.name.startswith(".") or not cat.is_dir():
                continue
            candidate = cat / skill_name
            if _looks_like_skill_dir(candidate):
                return candidate
    return None


def find_skill_dir(skill_name: str, skills_root: Path | None = None) -> Path | None:
    """Locate a sibling skill directory.

    When `skills_root` is explicitly supplied, ONLY that root is searched so
    callers and tests stay isolated from `~/.agents/skills`.
    """
    if skills_root is not None:
        return _search_skill_in_root(skill_name, skills_root)
    for root in _default_skill_roots():
        found = _search_skill_in_root(skill_name, root)
        if found is not None:
            return found
    return None


def find_sibling_script(
    skill_name: str,
    rel_script: str,
    skills_root: Path | None = None,
) -> Path | None:
    """Locate a specific script inside a sibling skill; returns None if absent."""
    skill_dir = find_skill_dir(skill_name, skills_root)
    if skill_dir is None:
        return None
    script_path = skill_dir / rel_script
    if script_path.is_file():
        return script_path
    return None


def _probe_playwright(which_fn: Callable[[str], str | None]) -> dict[str, Any]:
    """Probe Playwright CLI, MOTION_LAB_NODE_DIR, or Node resolution."""
    cli = which_fn("playwright")
    if cli:
        return {"found": True, "path": cli, "source": "PATH"}
    node_dir = os.environ.get("MOTION_LAB_NODE_DIR")
    if node_dir:
        pkg = Path(node_dir) / "node_modules" / "playwright" / "package.json"
        if pkg.is_file():
            return {"found": True, "path": str(pkg.parent), "source": "MOTION_LAB_NODE_DIR"}
    node_bin = which_fn("node")
    if node_bin:
        try:
            proc = subprocess.run(
                [node_bin, "-e", "console.log(require.resolve('playwright'))"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return {"found": True, "path": proc.stdout.strip(), "source": "node"}
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"found": False, "path": None, "source": None}


def run_doctor(
    skills_root: Path | None = None,
    which_fn: Callable[[str], str | None] = shutil.which,
    playwright_probe: Callable[[Callable[[str], str | None]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Probe local binaries and sibling skills and report actionable hints."""
    required_tools: dict[str, dict[str, Any]] = {}
    optional_tools: dict[str, dict[str, Any]] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []
    hints: list[str] = []

    for tool in REQUIRED_TOOLS:
        path = which_fn(tool)
        found = path is not None
        required_tools[tool] = {"found": found, "path": path}
        if not found:
            missing_required.append(tool)
            hints.append(f"[required:{tool}] {TOOL_HINTS[tool]}")

    pw_probe = playwright_probe or _probe_playwright
    for tool in OPTIONAL_TOOLS:
        if tool == "playwright":
            info = pw_probe(which_fn)
        else:
            path = which_fn(tool)
            info = {"found": path is not None, "path": path}
        optional_tools[tool] = info
        if not info["found"]:
            missing_optional.append(tool)
            hints.append(f"[optional:{tool}] {TOOL_HINTS[tool]}")

    skills_report: dict[str, dict[str, Any]] = {}
    missing_skills: list[str] = []
    for skill in SIBLING_SKILLS:
        sdir = find_skill_dir(skill, skills_root)
        scripts_status: dict[str, bool] = {}
        for rel in SKILL_KEY_SCRIPTS.get(skill, ()):
            scripts_status[rel] = bool(sdir is not None and (sdir / rel).is_file())
        present = sdir is not None
        skills_report[skill] = {
            "found": present,
            "path": str(sdir) if sdir is not None else None,
            "scripts": scripts_status,
        }
        if not present:
            missing_skills.append(skill)
            hints.append(
                f"[skill:{skill}] Sibling skill `{skill}` not found under "
                f"{skills_root if skills_root is not None else '~/.agents/skills'}; "
                f"install it or pass `--skills-root <dir>`."
            )
        else:
            missing_scripts = [rel for rel, ok in scripts_status.items() if not ok]
            if missing_scripts:
                hints.append(
                    f"[skill:{skill}] Found at {sdir} but missing expected script(s): "
                    f"{', '.join(missing_scripts)}."
                )

    ok = len(missing_required) == 0
    if not ok:
        status = "missing_required"
    elif missing_optional or missing_skills:
        status = "degraded"
    else:
        status = "ready"

    return {
        "ok": ok,
        "status": status,
        "skills_root": str(skills_root) if skills_root is not None else str(Path.home() / ".agents" / "skills"),
        "required_tools": required_tools,
        "optional_tools": optional_tools,
        "skills": skills_report,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "missing_skills": missing_skills,
        "hints": hints,
    }


def route_intent(
    intent: str,
    *,
    has_footage: bool = False,
    has_reference: bool = False,
    needs_audio: bool = False,
) -> dict[str, Any]:
    """Deterministically route a natural-language video intent to an ordered skill chain."""
    text = intent.strip()
    ref_hits = _match_patterns(text, _REF_PATTERNS)
    if has_reference and "flag:--has-reference" not in ref_hits:
        ref_hits.append("flag:--has-reference")

    footage_hits = _match_patterns(text, _FOOTAGE_PATTERNS)
    if has_footage and "flag:--has-footage" not in footage_hits:
        footage_hits.append("flag:--has-footage")

    motion_specific_hits = _match_patterns(text, _MOTION_SPECIFIC_PATTERNS)
    generic_video_hits = _match_patterns(text, _GENERIC_VIDEO_PATTERNS)
    midnight_hits = _match_patterns(text, _STYLE_MIDNIGHT_PATTERNS)
    dawn_hits = _match_patterns(text, _STYLE_DAWN_PATTERNS)
    text_no_section_silent = _SECTION_SILENT_RX.sub(" ", text)
    text_no_neg_audio = _NEGATED_AUDIO_RX.sub(" ", text_no_section_silent)
    audio_hits = _match_patterns(text_no_neg_audio, _AUDIO_PATTERNS)
    if needs_audio and "flag:--needs-audio" not in audio_hits:
        audio_hits.append("flag:--needs-audio")
    silent_hits = _match_patterns(text_no_section_silent, _SILENT_PATTERNS)

    duration_sec = _extract_duration_sec(text_no_section_silent)
    warnings: list[str] = []

    # Resolve mutually exclusive visual style system.
    style_skill: str | None = None
    style_hits: list[str] = []
    if midnight_hits and dawn_hits:
        m_pos = _STYLE_MIDNIGHT_PATTERNS[0][1].search(text)
        d_pos = _STYLE_DAWN_PATTERNS[0][1].search(text)
        if m_pos and d_pos and d_pos.start() < m_pos.start():
            style_skill = "liquid-dawn"
        else:
            style_skill = "liquid-midnight"
        style_hits = [*midnight_hits, *dawn_hits]
        warnings.append(
            f"Both liquid-midnight and liquid-dawn signals matched; selected `{style_skill}`. "
            "Never mix their tokens on one surface."
        )
    elif midnight_hits:
        style_skill = "liquid-midnight"
        style_hits = list(midnight_hits)
    elif dawn_hits:
        style_skill = "liquid-dawn"
        style_hits = list(dawn_hits)

    needs_ingest = bool(ref_hits)
    has_footage_signal = bool(footage_hits)
    has_motion_specific = bool(motion_specific_hits) or style_skill is not None
    has_video_signal = has_footage_signal or has_motion_specific or bool(generic_video_hits)
    has_audio_signal = bool(audio_hits)
    explicit_silent = bool(silent_hits) and not has_audio_signal and not needs_audio

    matched_signals = {
        "reference": ref_hits,
        "footage": footage_hits,
        "motion": [*motion_specific_hits, *generic_video_hits],
        "style": style_hits,
        "audio": audio_hits,
        "silent": silent_hits,
    }

    # Case 1: Audio-only request with no video/footage/reference deliverable.
    if has_audio_signal and not has_video_signal and not needs_ingest:
        next_commands = [
            "python3 <skills-root>/soundcraft/scripts/audio_qa.py check <audio_file> --json",
            "python3 <skills-root>/soundcraft/scripts/audio_qa.py sheet <audio_file> --out out/audio-qa-sheet.png",
        ]
        return {
            "intent": text,
            "in_scope": False,
            "rejected": True,
            "rejection_reason": (
                "Audio-only request with no video/visual deliverable; route directly to "
                "`soundcraft` instead of `filmcraft`."
            ),
            "lane": "audio_only",
            "needs_ingest": False,
            "extracted_duration_sec": duration_sec,
            "skills": ["soundcraft"],
            "matched_signals": matched_signals,
            "stages": [
                {
                    "stage": 1,
                    "name": "direct_handoff",
                    "active": True,
                    "owner": "soundcraft",
                    "commands": next_commands,
                }
            ],
            "next_commands": next_commands,
            "warnings": warnings,
        }

    # Case 2: Reference dissection only (no production lane requested).
    wants_production = (
        has_footage_signal
        or has_motion_specific
        or (bool(generic_video_hits) and bool(_PRODUCE_VERBS.search(text)))
    )
    if needs_ingest and not wants_production:
        ingest_cmds = [
            "python3 scripts/video_ingest.py <reference_url_or_path> --outdir work/ingest --keep-video",
            "ffprobe -v error -show_format -show_streams <video_path_from_work/ingest/manifest.json>",
        ]
        return {
            "intent": text,
            "in_scope": True,
            "rejected": False,
            "rejection_reason": None,
            "lane": "reference_dissection",
            "needs_ingest": True,
            "extracted_duration_sec": duration_sec,
            "skills": [],
            "matched_signals": matched_signals,
            "stages": [
                {
                    "stage": 1,
                    "name": "ingest_dissect",
                    "active": True,
                    "owner": "scripts/video_ingest.py + ffprobe",
                    "commands": ingest_cmds,
                },
                {
                    "stage": 2,
                    "name": "spec_route",
                    "active": True,
                    "owner": "filmcraft",
                    "commands": [
                        'python3 scripts/filmcraft.py route "<production intent after reviewing work/ingest/contact_sheet.jpg>" --json'
                    ],
                },
            ],
            "next_commands": ingest_cmds,
            "warnings": warnings,
        }

    # Case 3: Unrecognized / non-video request with no signals.
    if not has_video_signal and not needs_ingest:
        return {
            "intent": text,
            "in_scope": False,
            "rejected": True,
            "rejection_reason": (
                "No video, footage, motion, or reference signals detected; clarify the "
                "deliverable or pass --has-footage / --has-reference."
            ),
            "lane": "out_of_scope",
            "needs_ingest": False,
            "extracted_duration_sec": duration_sec,
            "skills": [],
            "matched_signals": matched_signals,
            "stages": [],
            "next_commands": [],
            "warnings": warnings,
        }

    # Case 4: Video production lanes (raw_footage | code_first_motion | hybrid).
    skills: list[str] = []
    if has_footage_signal and has_motion_specific:
        lane = "hybrid"
        skills.extend(["video-cut", "motion-lab"])
    elif has_footage_signal:
        lane = "raw_footage"
        skills.append("video-cut")
    else:
        lane = "code_first_motion"
        skills.append("motion-lab")

    if style_skill is not None:
        skills.append(style_skill)

    # Include soundcraft unless the user explicitly requested a silent/muted deliverable.
    include_audio = not explicit_silent
    if include_audio:
        skills.append("soundcraft")

    # Build 4-stage pipeline commands.
    stage1_cmds: list[str] = []
    if needs_ingest:
        stage1_cmds = [
            "python3 scripts/video_ingest.py <reference_url_or_path> --outdir work/ingest --keep-video",
            "ffprobe -v error -show_format -show_streams <video_path_from_work/ingest/manifest.json>",
        ]

    stage2_cmds: list[str] = ["python3 scripts/filmcraft.py doctor --json"]
    if style_skill == "liquid-midnight":
        stage2_cmds.append("node <skills-root>/liquid-midnight/scripts/materialize.mjs install work/scene --with templates")
    elif style_skill == "liquid-dawn":
        stage2_cmds.append("cp -R <skills-root>/liquid-dawn/assets work/scene/assets")

    stage3_cmds: list[str] = []
    target_mp4 = "out/final.mp4"
    if lane == "hybrid":
        dur_flag = f" --seconds {int(duration_sec) if duration_sec and duration_sec.is_integer() else duration_sec}" if duration_sec else ""
        stage3_cmds.extend([
            "python3 <skills-root>/video-cut/scripts/transcribe_local.py <raw_clip.mp4> --edit-dir edit",
            "python3 <skills-root>/video-cut/scripts/unheard.py detect <raw_clip.mp4> --transcript edit/transcripts/<clip>.json --json --annotate-out edit/annotated.txt",
            "python3 <skills-root>/video-cut/scripts/edit_plan.py validate edit/editPlan.json --check-files",
            "python3 <skills-root>/video-cut/scripts/edit_plan.py render edit/editPlan.json -o work/footage-cut.mp4",
            "python3 <skills-root>/motion-lab/scripts/motion_lint.py work/scene/index.html",
            f"node <skills-root>/motion-lab/scripts/render.mjs work/scene/index.html{dur_flag} --serve --workers 4 --webgl --transparent --verify --out work/overlay",
            (
                "mkdir -p out && ffmpeg -y -i work/footage-cut.mp4 -framerate 24 -i work/overlay/frames/%04d.png -filter_complex '[0:v][1:v]overlay=0:0:eof_action=pass[v]' -map '[v]' -an -c:v libx264 -pix_fmt yuv420p out/final.mp4"
                if explicit_silent
                else "mkdir -p out && ffmpeg -y -i work/footage-cut.mp4 -framerate 24 -i work/overlay/frames/%04d.png -filter_complex '[0:v][1:v]overlay=0:0:eof_action=pass[v]' -map '[v]' -map 0:a? -c:v libx264 -pix_fmt yuv420p -c:a copy out/final.mp4"
            ),
        ])
    elif "video-cut" in skills:
        stage3_cmds.extend([
            "python3 <skills-root>/video-cut/scripts/transcribe_local.py <raw_clip.mp4> --edit-dir edit",
            "python3 <skills-root>/video-cut/scripts/unheard.py detect <raw_clip.mp4> --transcript edit/transcripts/<clip>.json --json --annotate-out edit/annotated.txt",
            "python3 <skills-root>/video-cut/scripts/edit_plan.py validate edit/editPlan.json --check-files",
            "python3 <skills-root>/video-cut/scripts/edit_plan.py render edit/editPlan.json -o out/final.mp4",
        ])
    elif "motion-lab" in skills:
        dur_flag = f" --seconds {int(duration_sec) if duration_sec and duration_sec.is_integer() else duration_sec}" if duration_sec else ""
        stage3_cmds.extend([
            "python3 <skills-root>/motion-lab/scripts/motion_lint.py work/scene/index.html",
            f"node <skills-root>/motion-lab/scripts/render.mjs work/scene/index.html{dur_flag} --serve --workers 4 --webgl --verify --out out --mp4",
        ])
        if "soundcraft" in skills:
            stage3_cmds.append(
                "ffmpeg -y -i out/anim.mp4 -i work/audio/master.wav -c:v copy -c:a aac -b:a 192k -movflags +faststart -shortest out/final.mp4"
            )
            target_mp4 = "out/final.mp4"
        else:
            target_mp4 = "out/anim.mp4"
    if "soundcraft" in skills:
        stage3_cmds.append(
            f"python3 <skills-root>/soundcraft/scripts/audio_qa.py sheet {target_mp4} --out out/audio-qa-sheet.png"
        )

    verify_cmd = f"python3 scripts/filmcraft.py verify {target_mp4}"
    if duration_sec is not None:
        dur_str = str(int(duration_sec)) if duration_sec.is_integer() else str(duration_sec)
        verify_cmd += f" --expected-dur {dur_str}"
    if explicit_silent:
        verify_cmd += " --skip-audio"
    verify_cmd += " --json"
    stage4_cmds = [verify_cmd]

    stages = [
        {
            "stage": 1,
            "name": "ingest_dissect",
            "active": needs_ingest,
            "owner": "scripts/video_ingest.py + ffprobe",
            "commands": stage1_cmds,
        },
        {
            "stage": 2,
            "name": "spec_route",
            "active": True,
            "owner": "filmcraft" + (f" + {style_skill}" if style_skill else ""),
            "commands": stage2_cmds,
        },
        {
            "stage": 3,
            "name": "render_compile",
            "active": True,
            "owner": " -> ".join(skills),
            "commands": stage3_cmds,
        },
        {
            "stage": 4,
            "name": "delivery_gates",
            "active": True,
            "owner": "filmcraft verify",
            "commands": stage4_cmds,
        },
    ]

    next_commands = [*stage1_cmds, *stage2_cmds, *stage3_cmds, *stage4_cmds]

    return {
        "intent": text,
        "in_scope": True,
        "rejected": False,
        "rejection_reason": None,
        "lane": lane,
        "needs_ingest": needs_ingest,
        "extracted_duration_sec": duration_sec,
        "skills": skills,
        "matched_signals": matched_signals,
        "stages": stages,
        "next_commands": next_commands,
        "warnings": warnings,
    }


def _probe_media_ffprobe(
    mp4_path: Path,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Run ffprobe to gather stream & duration metadata without failing silently."""
    ffprobe_bin = which_fn("ffprobe")
    if not ffprobe_bin:
        return {"status": "skipped_missing_tool", "duration_sec": None, "streams": []}
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(mp4_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc), "duration_sec": None, "streams": []}
    if proc.returncode != 0:
        return {
            "status": "fail",
            "exit_code": proc.returncode,
            "stderr": proc.stderr.strip(),
            "duration_sec": None,
            "streams": [],
        }
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "error", "error": f"invalid ffprobe json: {exc}", "duration_sec": None, "streams": []}

    fmt = data.get("format") or {}
    raw_dur = fmt.get("duration")
    duration_sec = None
    if raw_dur is not None:
        try:
            parsed_dur = float(raw_dur)
            if math.isfinite(parsed_dur) and parsed_dur >= 0.0:
                duration_sec = parsed_dur
        except (TypeError, ValueError):
            duration_sec = None
    streams = data.get("streams") or []
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return {
        "status": "ok",
        "duration_sec": duration_sec,
        "has_video": has_video,
        "has_audio": has_audio,
        "stream_count": len(streams),
    }


def _run_gate_subprocess(
    *,
    gate_name: str,
    skill_name: str,
    rel_script: str,
    args: list[str],
    skills_root: Path | None,
    timeout_sec: int = GATE_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Locate and run one sibling gate script; never report pass if absent."""
    script_path = find_sibling_script(skill_name, rel_script, skills_root)
    if script_path is None:
        return {
            "gate": gate_name,
            "skill": skill_name,
            "script": rel_script,
            "script_path": None,
            "required": True,
            "status": "skipped_missing_tool",
            "passed": False,
            "exit_code": None,
            "command": None,
            "hint": (
                f"Required sibling gate `{skill_name}/{rel_script}` not found under "
                f"{skills_root if skills_root is not None else '~/.agents/skills'}. "
                "Install the sibling skill or pass `--skills-root <dir>`."
            ),
        }

    cmd = [sys.executable, str(script_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "gate": gate_name,
            "skill": skill_name,
            "script": rel_script,
            "script_path": str(script_path),
            "required": True,
            "status": "error",
            "passed": False,
            "exit_code": None,
            "command": cmd,
            "stderr": f"Timed out after {timeout_sec}s",
        }
    except OSError as exc:
        return {
            "gate": gate_name,
            "skill": skill_name,
            "script": rel_script,
            "script_path": str(script_path),
            "required": True,
            "status": "error",
            "passed": False,
            "exit_code": None,
            "command": cmd,
            "stderr": str(exc),
        }

    parsed_json: Any = None
    stdout_text = proc.stdout.strip()
    if stdout_text:
        try:
            parsed_json = json.loads(stdout_text)
        except json.JSONDecodeError:
            parsed_json = None

    verdict: bool | None = None
    if isinstance(parsed_json, dict):
        if isinstance(parsed_json.get("passed"), bool):
            verdict = parsed_json["passed"]
        elif isinstance(parsed_json.get("pass"), bool):
            verdict = parsed_json["pass"]

    if proc.returncode not in (0, 1):
        status = "error"
        passed = False
    elif proc.returncode == 0:
        if verdict is True:
            status = "pass"
            passed = True
        else:
            status = "error"
            passed = False
    else:
        status = "fail" if verdict is False else "error"
        passed = False

    return {
        "gate": gate_name,
        "skill": skill_name,
        "script": rel_script,
        "script_path": str(script_path),
        "required": True,
        "status": status,
        "passed": passed,
        "exit_code": proc.returncode,
        "command": cmd,
        "stdout": stdout_text,
        "stderr": proc.stderr.strip(),
        "parsed_output": parsed_json,
    }


def run_verify(
    mp4_path: Path,
    *,
    expected_dur: float | None = None,
    dur_tolerance: float = DEFAULT_DUR_TOLERANCE_SEC,
    beats: str | None = None,
    skills_root: Path | None = None,
    skip_audio: bool = False,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> tuple[dict[str, Any], int]:
    """Run unified visual + audio delivery gates on `mp4_path`.

    Exit 0 ONLY when every required gate actually ran and passed (and duration
    matched when `--expected-dur` is supplied). Never reports fake-green when a
    sibling gate script is missing.
    """
    if not mp4_path.is_file():
        receipt = {
            "ok": False,
            "exit_code": 2,
            "mp4": str(mp4_path),
            "error": f"Target video file not found: {mp4_path}",
            "probe": None,
            "duration_check": None,
            "gates": {},
            "missing_tools": [],
            "failed_gates": [],
        }
        return receipt, 2

    probe = _probe_media_ffprobe(mp4_path.resolve(), which_fn=which_fn)

    duration_check: dict[str, Any] | None = None
    if expected_dur is not None:
        actual = probe.get("duration_sec")
        if actual is None:
            duration_check = {
                "ok": False,
                "status": "unverified_duration",
                "expected_sec": expected_dur,
                "actual_sec": None,
                "tolerance_sec": dur_tolerance,
            }
        else:
            delta = abs(actual - expected_dur)
            dur_ok = delta <= dur_tolerance
            duration_check = {
                "ok": dur_ok,
                "status": "pass" if dur_ok else "fail",
                "expected_sec": expected_dur,
                "actual_sec": actual,
                "delta_sec": round(delta, 4),
                "tolerance_sec": dur_tolerance,
            }

    abs_mp4 = mp4_path.resolve()
    video_args = ["grade", str(abs_mp4), "--json"]
    if beats:
        video_args.extend(["--beats", beats])
    video_gate = _run_gate_subprocess(
        gate_name="video_qa",
        skill_name="motion-lab",
        rel_script="scripts/video_qa.py",
        args=video_args,
        skills_root=skills_root,
    )

    if skip_audio:
        audio_gate: dict[str, Any] = {
            "gate": "audio_qa",
            "skill": "soundcraft",
            "script": "scripts/audio_qa.py",
            "script_path": None,
            "required": False,
            "status": "skipped_by_flag",
            "passed": True,
            "exit_code": None,
            "command": None,
        }
    else:
        audio_args = ["check", str(abs_mp4), "--json"]
        if expected_dur is not None:
            audio_args.extend(["--expected-dur", str(expected_dur)])
        audio_gate = _run_gate_subprocess(
            gate_name="audio_qa",
            skill_name="soundcraft",
            rel_script="scripts/audio_qa.py",
            args=audio_args,
            skills_root=skills_root,
        )

    gates = {
        "video_qa": video_gate,
        "audio_qa": audio_gate,
    }

    missing_tools = [
        name
        for name, gate in gates.items()
        if gate["required"] and gate["status"] == "skipped_missing_tool"
    ]
    errored_gates = [
        name
        for name, gate in gates.items()
        if gate["required"] and gate["status"] == "error"
    ]
    failed_gates = [
        name
        for name, gate in gates.items()
        if gate["required"] and gate["status"] == "fail"
    ]
    all_required_passed = all(
        gate["status"] == "pass"
        for gate in gates.values()
        if gate["required"]
    )
    duration_ok = duration_check["ok"] if duration_check is not None else True

    ok = all_required_passed and duration_ok and not missing_tools and not errored_gates
    if ok:
        exit_code = 0
    elif missing_tools or errored_gates:
        exit_code = 2
    else:
        exit_code = 1

    receipt = {
        "ok": ok,
        "exit_code": exit_code,
        "mp4": str(mp4_path),
        "probe": probe,
        "duration_check": duration_check,
        "gates": gates,
        "missing_tools": missing_tools,
        "failed_gates": failed_gates,
        "errored_gates": errored_gates,
    }
    return receipt, exit_code


def _format_doctor_text(report: dict[str, Any]) -> str:
    lines = [f"filmcraft doctor: {report['status']} (ok={report['ok']})"]
    lines.append("Required tools:")
    for name, info in report["required_tools"].items():
        mark = "OK" if info["found"] else "MISSING"
        lines.append(f"  - {name}: {mark}" + (f" ({info['path']})" if info["path"] else ""))
    lines.append("Optional tools:")
    for name, info in report["optional_tools"].items():
        mark = "OK" if info["found"] else "absent"
        lines.append(f"  - {name}: {mark}" + (f" ({info['path']})" if info["path"] else ""))
    lines.append(f"Sibling skills (root={report['skills_root']}):")
    for name, info in report["skills"].items():
        mark = "OK" if info["found"] else "MISSING"
        lines.append(f"  - {name}: {mark}" + (f" ({info['path']})" if info["path"] else ""))
    if report["hints"]:
        lines.append("Hints:")
        for hint in report["hints"]:
            lines.append(f"  * {hint}")
    return chr(10).join(lines)


def _format_route_text(result: dict[str, Any]) -> str:
    lines = [
        f"lane: {result['lane']} (in_scope={result['in_scope']}, needs_ingest={result['needs_ingest']})",
        f"skills: {', '.join(result['skills']) if result['skills'] else '(none)'}",
    ]
    if result.get("rejection_reason"):
        lines.append(f"reason: {result['rejection_reason']}")
    if result.get("warnings"):
        for w in result["warnings"]:
            lines.append(f"warning: {w}")
    if result["next_commands"]:
        lines.append("next commands:")
        for cmd in result["next_commands"]:
            lines.append(f"  $ {cmd}")
    return chr(10).join(lines)


def _format_verify_text(receipt: dict[str, Any]) -> str:
    lines = [f"filmcraft verify: {'PASS' if receipt['ok'] else 'FAIL'} (exit={receipt['exit_code']}) — {receipt['mp4']}"]
    if receipt.get("error"):
        lines.append(f"error: {receipt['error']}")
    if receipt.get("duration_check"):
        dc = receipt["duration_check"]
        lines.append(
            f"duration: {dc['status']} (expected={dc['expected_sec']}s, actual={dc['actual_sec']}s)"
        )
    for name, gate in receipt.get("gates", {}).items():
        lines.append(f"  - {name} ({gate['skill']}/{gate['script']}): {gate['status']}")
        if gate.get("hint"):
            lines.append(f"    hint: {gate['hint']}")
    return chr(10).join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="filmcraft",
        description="Thin terminal-first video production router and unified delivery gate runner.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser("doctor", help="Probe local video/audio toolchain and sibling skills.")
    p_doc.add_argument("--skills-root", type=Path, default=None, help="Directory containing sibling skills.")
    p_doc.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    p_route = sub.add_parser("route", help="Deterministically route a video intent to an ordered skill chain.")
    p_route.add_argument("intent_text", help="Natural-language description of the video task.")
    p_route.add_argument("--has-footage", action="store_true", help="Caller has raw recorded footage clips.")
    p_route.add_argument("--has-reference", action="store_true", help="Caller has a reference video/URL to dissect.")
    p_route.add_argument("--needs-audio", action="store_true", help="Deliverable requires sound design / audio QA.")
    p_route.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    p_ver = sub.add_parser("verify", help="Run unified visual (video_qa.py) + audio (audio_qa.py) delivery gates.")
    p_ver.add_argument("mp4_path", type=Path, help="Path to rendered MP4 deliverable.")
    p_ver.add_argument("--expected-dur", type=float, default=None, help="Expected duration in seconds.")
    p_ver.add_argument("--dur-tolerance", type=float, default=DEFAULT_DUR_TOLERANCE_SEC, help="Duration tolerance in seconds (default: 0.5).")
    p_ver.add_argument("--beats", type=str, default=None, help="Comma-separated beat frame indices forwarded to motion-lab video_qa.py grade.")
    p_ver.add_argument("--skills-root", type=Path, default=None, help="Directory containing sibling skills.")
    p_ver.add_argument("--skip-audio", action="store_true", help="Explicitly skip audio_qa gate for silent deliverables.")
    p_ver.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        report = run_doctor(skills_root=args.skills_root)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(_format_doctor_text(report))
        return 0 if report["ok"] else 1

    if args.command == "route":
        if not args.intent_text.strip():
            print("error: intent_text must be non-empty", file=sys.stderr)
            return 2
        result = route_intent(
            args.intent_text,
            has_footage=args.has_footage,
            has_reference=args.has_reference,
            needs_audio=args.needs_audio,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(_format_route_text(result))
        return 0

    if args.command == "verify":
        receipt, exit_code = run_verify(
            args.mp4_path,
            expected_dur=args.expected_dur,
            dur_tolerance=args.dur_tolerance,
            beats=args.beats,
            skills_root=args.skills_root,
            skip_audio=args.skip_audio,
        )
        if args.json:
            print(json.dumps(receipt, indent=2))
        else:
            print(_format_verify_text(receipt))
        return exit_code

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
