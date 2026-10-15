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
# The list is the claim: each entry is a mechanism with a test that fails without
# it. Lines not listed here (e.g. the contact-sheet labels) carry no such claim.
MUTATIONS = [
    ("pin check always passes", "scripts/motion_lint.py",
     "    return bool(_PIN.search(url))", "    return True", "test_unpinned_urls_fail", False),
    ("Math.random rule removed", "scripts/motion_lint.py",
     r'"MC03", re.compile(r"\bMath\.random\b|', r'"MC03", re.compile(r"', "test_timers_and_random or test_module_mode", False),
    ("comment stripping disabled", "scripts/motion_lint.py",
     "                wipe(keep, i, j)\n                wipe(blank, i, j)\n                i = j\n            elif c == \"/\" and nxt == \"*\":",
     "                i = j\n            elif c == \"/\" and nxt == \"*\":", "test_comments_and_strings", False),
    ("preview guard ignored (every clock is an error)", "scripts/motion_lint.py",
     "    preview_ok = has_render_at and has_guard", "    preview_ok = False",
     "test_clock_with_renderat_and_guard or test_good_fixture", False),
    ("WAAPI treated as needing renderAt", "scripts/motion_lint.py",
     '|\\bsetTimeout\\b")', '|\\bsetTimeout\\b|\\.animate\\s*\\(")', "test_waapi_only", False),
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
    # The mechanism is "wait for animation.ready before pausing", done twice: once
    # in the warm-up and once per frame. Round 4 showed removing only the warm-up
    # copy survives (the per-frame copy covers it), so the mutant removes both:
    # 5/5 cold runs then fail at frame 0 on macOS Chromium. The compositor race it
    # guards does NOT occur in Ubuntu CI's headless Chromium (the mutant survived
    # there), so this entry runs only on macOS: see PLATFORM_ONLY.
    ("ready-await before pausing removed (warm-up and per-frame)", "scripts/render.mjs",
     "    await Promise.all(document.getAnimations().map((a) => a.ready.catch(() => {})));\n    const tick = window.__mlRAF || window.requestAnimationFrame.bind(window);\n    for (let k = 0; k < 2; k++) await new Promise((r) => tick(() => r()));\n  });\n  await frameAt(page, 0, errors);",
     "  });\n  await frameAt(page, 0, errors);", "test_warm_up_keeps", True,
     ("    await Promise.all(anims.map((a) => a.ready.catch(() => {})));\n", "")),
    ("SMIL timelines not seeked", "scripts/render.mjs",
     "if (typeof svg.pauseAnimations === 'function') { svg.pauseAnimations(); svg.setCurrentTime(tt); }", "",
     "test_svg_smil", True),
    ("page errors do not change the exit code", "scripts/render.mjs",
     "    if (errors.length) exitCode = 5;", "", "test_a_page_that_throws", True),
    ("static pages exit 0", "scripts/render.mjs",
     "      if (!o.allowStatic && !exitCode) exitCode = 6;", "", "test_a_static_page", True),
    ("namespace URIs treated as loads", "scripts/motion_lint.py",
     '    if "www.w3.org/" in url:\n        return "text"', '    if False:\n        return "text"', "test_svg_namespace", False),
    ("load contexts ignored (extensionless loads only warn)", "scripts/motion_lint.py",
     "    if LOAD_EXT.search(url) or LOAD_CTX.search(keep[max(0, m.start() - 48):m.start()]):",
     "    if LOAD_EXT.search(url):", "test_extensionless_loads", False),
    ("a guard without else excuses the loop", "scripts/motion_lint.py",
     "                elif rule == \"MC01\" and preview_ok and guard_wraps(blank, keep, m.start()):",
     "                elif rule == \"MC01\" and preview_ok:", "test_guard_without_else", False),
    ("canvas context counted as motion", "scripts/motion_lint.py",
     'MOTION_JS = re.compile(r"\\bTHREE\\b|', 'MOTION_JS = re.compile(r"getContext\\s*\\(|\\bTHREE\\b|',
     "test_static_canvas_beside_css_motion", False),
    ("contact sheet stops before the seam frame", "scripts/render.mjs",
     "(k === 1 ? 0 : Math.round((j * (N - 1)) / (k - 1)))", "(j * Math.max(1, Math.round(N / 12)))",
     "test_contact_sheet_spans", True),
    ("--verify-all re-renders in the first pass's order", "scripts/render.mjs",
     "Array.from({ length: N }, (_, i) => N - 1 - i)", "Array.from({ length: N }, (_, i) => i)",
     "test_verify_reports_its_scope", True),
    ("undriven motion called static", "scripts/render.mjs",
     "      if (changes) {", "      if (false) {", "test_undriven_motion", True),
    ("clock inside renderAt downgraded by the guard", "scripts/motion_lint.py",
     "                if rule == \"MC01\" and in_render_at:", "                if False:",
     "test_a_clock_inside_renderat", False),
    ("any transition flagged regardless of duration", "scripts/motion_lint.py",
     "                if not transition_is_live(m.group(1), m.group(2)):\n                    continue",
     "                pass", "test_transitions_that_cannot_run", False),
    ("unseeked GSAP not reported", "scripts/motion_lint.py",
     "    if re.search(r\"\\bgsap\\b\", all_js_blank) and not GSAP_SEEKED.search(all_js_blank):",
     "    if False:", "test_unseeked_gsap", False),
    ("unreachable renderAt accepted", "scripts/motion_lint.py",
     "    if is_html and has_render_at and not exposed:", "    if False:", "test_unreachable_renderat", False),
    ("renderer counts its own rAF waits against the page", "scripts/render.mjs",
     "    const tick = window.__mlRAF || window.requestAnimationFrame.bind(window);\n    let drew = false;",
     "    const tick = window.requestAnimationFrame.bind(window);\n    let drew = false;",
     "test_a_guarded_preview_loop", True),
    ("a mid-render throw aborts the render", "scripts/render.mjs",
     "    return await Promise.race([frameAtUnsafe(page, t), timeout]);\n  } catch (e) {",
     "    return await Promise.race([frameAtUnsafe(page, t), timeout]);\n  } catch (e) { throw e;",
     "test_renderat_throwing_mid_render", True),
    ("the seam frame dropped with --every", "scripts/render.mjs",
     "        if (picks[picks.length - 1] !== N - 1) picks.push(N - 1);", "", "test_every_keeps_the_seam", True),
    ("engine frame loops not clocks", "scripts/motion_lint.py",
     '    r"|\\.setAnimationLoop\\s*\\(\\s*(?!null\\b)|\\bticker\\.add\\s*\\(")', '    r"")',
     "test_engine_frame_loops", False),
    ("style-attribute url() not scanned", "scripts/motion_lint.py",
     "                if _URL.match(m.group(1).strip()):\n                    check_url(m.group(1).strip(), line_of(text, sm.start()), findings)",
     "                pass", "test_html_load_paths", False),
    ("drift gate removed", "scripts/render.mjs",
     "    if (!exitCode && drifting.length) {", "    if (false) {",
     "test_a_preview_loop_running_under_t or test_a_timeout_loop", True),
    ("call-count gate instead of drift (flags an idle ticker)", "scripts/render.mjs",
     "    if (!exitCode && drifting.length) {", "    if (!exitCode && (after.raf - before.raf >= 2 || drifting.length)) {",
     "test_an_idle_ticker", True),
    ("renderAt timeout removed", "scripts/render.mjs",
     "    return await Promise.race([frameAtUnsafe(page, t), timeout]);", "    return await frameAtUnsafe(page, t);",
     "test_a_hung_renderat", True),
    ("file:// outside the input dir allowed", "scripts/render.mjs",
     "    if (u.startsWith(allowedDir)) return route.continue();", "    return route.continue();",
     "test_local_files_outside", True),
    ("output cleanup deletes every file", "scripts/render.mjs",
     "if (/^\\d{4,}\\.png$/.test(f)) rmSync", "rmSync", "test_cleanup_keeps", True),
    ("template ${} expressions blanked", "scripts/motion_lint.py",
     "                wipe(blank, text_start, i)\n                close = scan_code(i + 2, in_expr=True)",
     "                close = scan_code(i + 2, in_expr=True)\n                wipe(blank, text_start, close)", "test_template_interpolation", False),
    ("renderAt not called", "scripts/render.mjs",
     "if (typeof window.renderAt === 'function') { await window.renderAt(tt); drew = true; }", "",
     "test_frames_actually_change or test_renders_frames_0_to_n", True),
]


# Mutations whose race only reproduces on one platform. Elsewhere they print SKIP
# with the reason instead of being counted: a mutant no test can kill on this
# platform says nothing about the test, only about the platform.
PLATFORM_ONLY = {
    "ready-await before pausing removed (warm-up and per-frame)": (
        "darwin", "the compositor race reproduces on macOS Chromium (5/5), not on Linux headless Chromium"),
}


def main() -> int:
    render_ok = bool(os.environ.get("MOTION_LAB_NODE_DIR"))
    survivors, ran = [], 0
    for desc, rel, old, new, sel, needs_render, *extra in MUTATIONS:
        if needs_render and not render_ok:
            print(f"SKIP  {desc} (set MOTION_LAB_NODE_DIR)")
            continue
        if desc in PLATFORM_ONLY and not sys.platform.startswith(PLATFORM_ONLY[desc][0]):
            print(f"SKIP  {desc} ({PLATFORM_ONLY[desc][1]})")
            continue
        work = Path(tempfile.mkdtemp(prefix="mut_motionlab_"))
        try:
            shutil.copytree(SRC, work / "s", ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
            target = work / "s" / rel
            text = target.read_text()
            if text.count(old) != 1:
                print(f"ERROR {desc}: anchor not found exactly once in {rel}")
                return 2
            text = text.replace(old, new)
            for old2, new2 in extra:
                if text.count(old2) != 1:
                    print(f"ERROR {desc}: second anchor not found exactly once in {rel}")
                    return 2
                text = text.replace(old2, new2)
            target.write_text(text)
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x",
                                "tests/", "-k", sel], cwd=work / "s", capture_output=True, text=True)
            ran += 1
            if r.returncode == 0:
                survivors.append(desc)
                print(f"SURVIVED {desc}  (-k {sel})")
            elif r.returncode == 1:  # tests ran and at least one failed
                print(f"KILLED   {desc}")
            else:  # 2 interrupted, 3 internal, 4 usage, 5 no tests: not a kill
                print(f"ERROR {desc}: pytest exit {r.returncode} (-k {sel})\n{r.stdout[-800:]}")
                return 2
        finally:
            shutil.rmtree(work, ignore_errors=True)
    print(f"\n{ran - len(survivors)}/{ran} mutations killed")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
