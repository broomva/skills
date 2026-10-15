"""Mutation proof: break each load-bearing line, assert its test fails.

Run with `python3 tests/mutation_proof.py` (pytest importable; set
MOTION_LAB_NODE_DIR for the render mutations, which are skipped otherwise).
Exits non-zero if any mutation survives.

A green suite says the assertions ran, not that they discriminate. Each entry
below applies one mutation to a COPY of the skill and runs only the test that
claims to cover it. A survivor is a test that cannot tell the mechanism from
its absence.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]

# (description, file, original text, mutated text, pytest -k selector, needs render)
MUTATIONS = [
    ("pin check always passes", "scripts/motion_lint.py",
     "    return bool(_PIN.search(url))", "    return True", "test_unpinned_urls_fail", False),
    ("Math.random rule removed", "scripts/motion_lint.py",
     r"\bMath\.random\s*\(|", "", "test_timers_and_random or test_module_mode", False),
    ("comment stripping disabled", "scripts/motion_lint.py",
     "            wipe(keep, i, j)\n            wipe(blank, i, j)\n            i = j\n        elif c == \"/\" and nxt == \"*\":",
     "            i = j\n        elif c == \"/\" and nxt == \"*\":", "test_comments_and_strings", False),
    ("preview guard ignored (every clock is an error)", "scripts/motion_lint.py",
     "    preview_ok = has_render_at and has_guard", "    preview_ok = False",
     "test_clock_with_renderat_and_guard or test_good_fixture", False),
    ("WAAPI treated as needing renderAt", "scripts/motion_lint.py",
     '|WebGLRenderer")', '|WebGLRenderer|\\.animate\\s*\\(")', "test_waapi_only", False),
    ("transition: none flagged", "scripts/motion_lint.py",
     'if value in ("none", "0s", "0", "initial", "unset") or value.startswith("none"):', "if False:",
     "test_css_transition", False),
    ("beats accumulate a rounded step", "scripts/motion_math.py",
     "    return [round_half_up(offset + n * fpb) for n in range(count)]",
     "    return [round_half_up(offset) + n * round_half_up(fpb) for n in range(count)]",
     "test_drift_free_grid", False),
    ("banker's rounding", "scripts/motion_math.py",
     "    return math.floor(x + 0.5)", "    return round(x)", "test_half_rounds_up", False),
    ("GIF delays rounded per frame", "scripts/motion_math.py",
     "    return [round_half_up(100 * (i + 1) / fps) - round_half_up(100 * i / fps) for i in range(frames)]",
     "    return [round_half_up(100 / fps) for _ in range(frames)]",
     "test_cumulative_time or test_24fps_six_second", False),
    ("GIF reader ignores the local colour table", "scripts/motion_math.py",
     "            if lpacked & 0x80:\n                pos += 3 * (2 ** ((lpacked & 0x07) + 1))",
     "            pass", "test_reads_every_delay", False),
    ("text hold rounds down", "scripts/motion_math.py",
     "math.ceil(secs * fps - 1e-9)", "math.floor(secs * fps)", "test_text_hold", False),
    ("renderer renders frame N too", "scripts/render.mjs",
     "for (let i = 0; i < N; i++) {", "for (let i = 0; i <= N; i++) {", "test_renders_frames_0_to_n", True),
    ("verify never compares", "scripts/render.mjs",
     "if (!again.equals(first)) mismatches.push(i);", "", "test_verify_catches", True),
    ("renderAt not called", "scripts/render.mjs",
     "if (typeof window.renderAt === 'function') { await window.renderAt(tt); drew = true; }", "",
     "test_frames_actually_change or test_renders_frames_0_to_n", True),
]


def main() -> int:
    render_ok = bool(os.environ.get("MOTION_LAB_NODE_DIR"))
    survivors, ran = [], 0
    for desc, rel, old, new, sel, needs_render in MUTATIONS:
        if needs_render and not render_ok:
            print(f"SKIP  {desc} (set MOTION_LAB_NODE_DIR)")
            continue
        work = Path(tempfile.mkdtemp(prefix="mut_motionlab_"))
        try:
            shutil.copytree(SRC, work / "s", ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
            target = work / "s" / rel
            text = target.read_text()
            if text.count(old) != 1:
                print(f"ERROR {desc}: anchor not found exactly once in {rel}")
                return 2
            target.write_text(text.replace(old, new))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x",
                                "tests/", "-k", sel], cwd=work / "s", capture_output=True, text=True)
            ran += 1
            if r.returncode == 0:
                survivors.append(desc)
                print(f"SURVIVED {desc}  (-k {sel})")
            elif r.returncode == 5:
                print(f"ERROR {desc}: selector matched no tests: {sel}")
                return 2
            else:
                print(f"KILLED   {desc}")
        finally:
            shutil.rmtree(work, ignore_errors=True)
    print(f"\n{ran - len(survivors)}/{ran} mutations killed")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
