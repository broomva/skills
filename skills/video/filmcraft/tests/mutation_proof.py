#!/usr/bin/env python3
"""Mutation proof for filmcraft: break each load-bearing predicate, assert pytest catches it.

Run with `python3 tests/mutation_proof.py`. Exits non-zero if any mutant survives.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]

# (description, rel_file, original_snippet, mutated_snippet, pytest -k selector)
MUTATIONS: list[tuple[str, str, str, str, str]] = [
    (
        "doctor ignores missing required tools",
        "scripts/filmcraft.py",
        "    ok = len(missing_required) == 0",
        "    ok = True",
        "test_doctor_missing_required_tool_fails",
    ),
    (
        "doctor never reports degraded when optional tools/skills missing",
        "scripts/filmcraft.py",
        '    elif missing_optional or missing_skills:' + chr(10) + '        status = "degraded"',
        '    elif False:' + chr(10) + '        status = "degraded"',
        "test_doctor_missing_optional_and_skills_reports_degraded",
    ),
    (
        "audio-only rejection disabled",
        "scripts/filmcraft.py",
        "    if has_audio_signal and not has_video_signal and not needs_ingest:",
        "    if False:",
        "test_route_audio_only_rejected_and_handed_to_soundcraft",
    ),
    (
        "raw footage routes to motion-lab instead of video-cut",
        "scripts/filmcraft.py",
        '    elif has_footage_signal:' + chr(10) + '        lane = "raw_footage"' + chr(10) + '        skills.append("video-cut")',
        '    elif has_footage_signal:' + chr(10) + '        lane = "code_first_motion"' + chr(10) + '        skills.append("motion-lab")',
        "test_route_raw_footage",
    ),
    (
        "liquid-midnight style omitted from routed skills",
        "scripts/filmcraft.py",
        "    if style_skill is not None:" + chr(10) + "        skills.append(style_skill)",
        "    if False:" + chr(10) + "        skills.append(style_skill)",
        "test_route_liquid_midnight_launch_film",
    ),
    (
        "explicit silent flag still attaches soundcraft",
        "scripts/filmcraft.py",
        "    include_audio = not explicit_silent",
        "    include_audio = True",
        "test_route_liquid_dawn_silent_loop",
    ),
    (
        "reference ingest flag ignored",
        "scripts/filmcraft.py",
        "    needs_ingest = bool(ref_hits)",
        "    needs_ingest = False",
        "test_route_reference_based_film",
    ),
    (
        "hybrid lane collapsed into raw_footage only",
        "scripts/filmcraft.py",
        '    if has_footage_signal and has_motion_specific:' + chr(10) + '        lane = "hybrid"' + chr(10) + '        skills.extend(["video-cut", "motion-lab"])',
        '    if False:' + chr(10) + '        lane = "hybrid"' + chr(10) + '        skills.extend(["video-cut", "motion-lab"])',
        "test_route_hybrid_footage_and_motion",
    ),
    (
        "verify fake-green when sibling gate is missing (prove-the-negative)",
        "scripts/filmcraft.py",
        '            "status": "skipped_missing_tool",' + chr(10) + '            "passed": False,',
        '            "status": "pass",' + chr(10) + '            "passed": True,',
        "test_verify_prove_the_negative_missing_video_gate_never_passes or test_verify_prove_the_negative_missing_audio_gate_never_passes",
    ),
    (
        "verify exit code returns 0 even when missing tools",
        "scripts/filmcraft.py",
        "    elif missing_tools or errored_gates:" + chr(10) + "        exit_code = 2",
        "    elif missing_tools or errored_gates:" + chr(10) + "        exit_code = 0",
        "test_verify_prove_the_negative_both_gates_missing",
    ),
    (
        "verify ignores failed sibling gate exit code",
        "scripts/filmcraft.py",
        '    else:' + chr(10) + '        status = "fail" if verdict is False else "error"' + chr(10) + '        passed = False',
        '    else:' + chr(10) + '        status = "pass"' + chr(10) + '        passed = True',
        "test_verify_visual_gate_failure_returns_exit_1 or test_verify_audio_gate_failure_returns_exit_1",
    ),
    (
        "verify accepts empty stdout exit 0 without explicit JSON verdict",
        "scripts/filmcraft.py",
        '        if verdict is True:' + chr(10) + '            status = "pass"' + chr(10) + '            passed = True' + chr(10) + '        else:' + chr(10) + '            status = "error"' + chr(10) + '            passed = False',
        '        status = "pass"' + chr(10) + '        passed = True',
        "test_p20_empty_stdout_exit_zero_never_passes",
    ),
    (
        "verify skips expected-dur check when ffprobe is absent",
        "scripts/filmcraft.py",
        '                "ok": False,' + chr(10) + '                "status": "unverified_duration",',
        '                "ok": True,' + chr(10) + '                "status": "unverified_duration",',
        "test_verify_expected_dur_unverified_without_ffprobe_fails",
    ),
    (
        "find_skill_dir ignores category-bucketed layout",
        "scripts/filmcraft.py",
        (
            "    for child in sorted(root.iterdir(), key=lambda p: p.name):" + chr(10)
            + '        if child.name.startswith(".") or not child.is_dir():' + chr(10)
            + "            continue" + chr(10)
            + "        candidate = child / skill_name" + chr(10)
            + "        if _looks_like_skill_dir(candidate):" + chr(10)
            + "            return candidate"
        ),
        "    pass",
        "test_doctor_resolves_bucketed_skill_layout",
    ),
]


def main() -> int:
    # Verify unmutated baseline passes before running mutants.
    base = subprocess.run(
        [sys.executable, "-m", "pytest", str(SRC / "tests"), "-q"],
        cwd=SRC,
        capture_output=True,
        text=True,
        check=False,
    )
    if base.returncode != 0:
        print(f"ERROR: baseline pytest failed (exit {base.returncode}):" + chr(10) + base.stdout + base.stderr, file=sys.stderr)
        return 2

    survivors: list[str] = []
    killed = 0
    for desc, rel_file, original, mutated, selector in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="filmcraft-mut-") as tmp:
            copy_root = Path(tmp) / "filmcraft"
            shutil.copytree(
                SRC,
                copy_root,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
            )
            target = copy_root / rel_file
            text = target.read_text(encoding="utf-8")
            if original not in text:
                print(f"ERROR: mutation pattern not found for: {desc}", file=sys.stderr)
                return 2
            if text.count(original) != 1:
                print(f"ERROR: mutation pattern ambiguous ({text.count(original)} hits) for: {desc}", file=sys.stderr)
                return 2
            target.write_text(text.replace(original, mutated, 1), encoding="utf-8")

            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(copy_root / "tests"), "-k", selector, "-q"],
                cwd=copy_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                survivors.append(desc)
                print(f"SURVIVED: {desc}")
            elif proc.returncode == 1:
                killed += 1
                print(f"KILLED:   {desc}")
            else:
                print(
                    f"ERROR: pytest exited {proc.returncode} (infrastructure/collection error, not test failure) for: {desc}"
                    + chr(10) + proc.stdout + proc.stderr,
                    file=sys.stderr,
                )
                return 2

    print(chr(10) + f"Mutation proof: {killed}/{len(MUTATIONS)} killed, {len(survivors)} survived")
    if survivors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
