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
     "for (let i = 0; i < N && !aborted; i++) {", "for (let i = 0; i <= N && !aborted; i++) {", "test_renders_frames_0_to_n", True),
    ("verify never compares", "scripts/render.mjs",
     "if (!again.equals(readFileSync(framePath(i)))) mismatches.push(i);", "", "test_verify_catches", True),
    # The mechanism is "wait for animation.ready before pausing", done twice: once
    # in the warm-up and once per frame. Round 4 showed removing only the warm-up
    # copy survives (the per-frame copy covers it), so the mutant removes both:
    # 5/5 cold runs then fail at frame 0 on macOS Chromium. The compositor race it
    # guards does NOT occur in Ubuntu CI's headless Chromium (the mutant survived
    # there), so this entry runs only on macOS: see PLATFORM_ONLY.
    ("ready-await before pausing removed (warm-up and per-frame)", "scripts/render.mjs",
     "      await Promise.all(anims.map((a) => a.ready.catch(() => {})));\n      const tick = window.__mlRAF || window.requestAnimationFrame.bind(window);\n      for (let k = 0; k < 2; k++) await new Promise((r) => tick(() => r()));\n      window.__mlPageOwned",
     "      window.__mlPageOwned", "test_warm_up_keeps", True,
     ("    // be ready before renderAt and the capture.\n    await Promise.all(anims.map((a) => a.ready.catch(() => {})));\n",
      "    // be ready before renderAt and the capture.\n")),
    ("SMIL timelines not seeked", "scripts/render.mjs",
     "if (typeof svg.pauseAnimations === 'function') { svg.pauseAnimations(); svg.setCurrentTime(tt); }", "",
     "test_svg_smil", True),
    ("page errors do not change the exit code", "scripts/render.mjs",
     "    flags.errors = errors.length > 0;", "    flags.errors = false;", "test_a_page_that_throws", True),
    ("static pages exit 0", "scripts/render.mjs",
     "          flags.static = !o.allowStatic;", "          flags.static = false;", "test_a_static_page", True),
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
     "    const tick = window.__mlRAF || window.requestAnimationFrame.bind(window);\n    // Seek first",
     "    const tick = window.requestAnimationFrame.bind(window);\n    // Seek first",
     "test_a_guarded_preview_loop", True),
    ("a mid-render throw aborts the render", "scripts/render.mjs",
     "    return info;\n  } catch (e) {",
     "    return info;\n  } catch (e) { throw e;",
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
     "      if (early.drift || drifting.length) {", "      if (false) {",
     "test_a_preview_loop_running_under_t or test_a_timeout_loop", True),
    ("call-count gate instead of drift (flags an idle ticker)", "scripts/render.mjs",
     "      if (early.drift || drifting.length) {", "      if (early.drift || drifting.length || manifest.loop_probe.raf_during_render >= 2) {",
     "test_an_idle_ticker", True),
    ("renderAt timeout removed", "scripts/render.mjs",
     "    const info = await withTimeout(frameAtUnsafe(page, t), 'renderAt');", "    const info = await frameAtUnsafe(page, t);",
     "test_a_hung_renderat", True),
    ("file:// outside the input dir allowed", "scripts/render.mjs",
     "    if (ok) return route.continue();", "    return route.continue();",
     "test_local_files_outside", True),
    ("output cleanup deletes every file", "scripts/render.mjs",
     "if (/^\\d{4,}\\.png$/.test(f)) rmSync", "rmSync", "test_cleanup_keeps", True),
    ("template ${} expressions blanked", "scripts/motion_lint.py",
     "                wipe(blank, text_start, i)\n                close = scan_code(i + 2, in_expr=True)",
     "                close = scan_code(i + 2, in_expr=True)\n                wipe(blank, text_start, close)", "test_template_interpolation", False),
    ("animations seeked after renderAt (renderAt no longer wins)", "scripts/render.mjs",
     "    for (let k = 0; k < 2; k++) await new Promise((r) => tick(() => r()));\n    return { drew,",
     "    for (const a of anims) { a.pause(); a.currentTime = tt * 1000; }\n    for (let k = 0; k < 2; k++) await new Promise((r) => tick(() => r()));\n    return { drew,",
     "test_renderat_wins", True),
    ("page-paused animations seeked anyway", "scripts/render.mjs",
     "      if (pageOwned.has(a)) continue;", "", "test_renderat_wins", True),
    ("early drift sample removed", "scripts/render.mjs",
     "    const early = aborted ? { drift: false, timedOut: false } : await drifts(page, 0, errors);",
     "    const early = { drift: false, timedOut: false };", "test_a_one_shot_intro", True),
    ("a timed-out frame does not abort the render", "scripts/render.mjs",
     "      if (info.timedOut) {\n        // A hung renderAt", "      if (false) {\n        // A hung renderAt", "test_a_hung_renderat or test_a_synchronous_hang", True),
    ("dot-segments served", "scripts/render.mjs",
     "        && !rel.split(path.sep).some((seg) => seg.startsWith('.')) && statSync(real).isFile();",
     "        && statSync(real).isFile();", "test_symlinks_and_dotfiles", True),
    ("symlinks not resolved before the containment check", "scripts/render.mjs",
     "      const real = realpathSync(fileURLToPath(u));", "      const real = fileURLToPath(u);",
     "test_symlinks_and_dotfiles", True),
    # Two layers stop a match reaching into the next statement (the bracket-bounded
    # span and the exact property-key pattern); either alone suffices, so the mutant
    # removes both.
    ("Object.assign span and key both loosened", "scripts/motion_lint.py",
     "        args = keep[m.end():j - 1]", "        args = keep[m.end():]", "test_object_assign_does_not_reach", False,
     ('re.search(r"[{,]\\s*[\'\\"`]?renderAt[\'\\"`]?\\s*(?:[,}:]|$)", args[target.end():])',
      're.search(r"\\brenderAt\\b", args[target.end():])')),
    ("ownership guessed from 'paused' instead of probed", "scripts/render.mjs",
     "      if (pageOwned.has(a)) continue;", "      if (pageOwned.has(a) || a.playState === 'paused') continue;",
     "test_ownership_is_tested_not_guessed", True),
    ("ownership probe never marks page-owned", "scripts/render.mjs",
     "            if (prev) for (const [a, sg] of cur) if (a.playState === 'paused' && prev.has(a) && prev.get(a) !== sg) window.__mlPageOwned.add(a);", "",
     "test_ownership_is_tested_not_guessed or test_renderat_wins", True),
    ("renderAt-created animations not reported", "scripts/render.mjs",
     "            for (const a of cur.keys()) if (!before.has(a) && a.playState === 'running') fresh.push(",
     "            for (const a of cur.keys()) if (false) fresh.push(",
     # the capture-time check also catches the class-toggled page, so the probe's
     # own contribution is the finding on a render that aborts before any capture
     "test_renderat_that_creates_a_css_keyframe_fails_by_default or test_a_finding_survives_a_later_probe_timeout", True),
    ("probe reports new animations renderAt left paused", "scripts/render.mjs",
     "            for (const a of cur.keys()) if (!before.has(a) && a.playState === 'running') fresh.push(",
     "            for (const a of cur.keys()) if (!before.has(a)) fresh.push(",
     "test_an_animation_renderat_awaits_and_owns_is_not_reported or test_an_animation_renderat_creates_late or test_a_single_frame_async_owned", True),
    ("capture calls not checked for running animations", "scripts/render.mjs",
     "        if (a.playState !== 'running') continue;",
     "        continue;",
     "test_a_capture_call_that_creates_a_keyframe_fails or test_a_page_owned_animation_played_on_one_frame_fails", True),
    ("capture check skips page-owned animations", "scripts/render.mjs",
     "        if (a.playState !== 'running') continue;",
     "        if (a.playState !== 'running' || pageOwned.has(a)) continue;",
     "test_a_page_owned_animation_played_on_one_frame_fails", True),
    ("a probe timeout drops earlier findings", "scripts/render.mjs",
     "          if (msg.includes('timed out after')) return { page, errors, blocked, createdAnimations: candidates, aborted: true };",
     "          if (msg.includes('timed out after')) return { page, errors, blocked, createdAnimations, aborted: true };",
     "test_a_finding_survives_a_later_probe_timeout", True),
    ("page-owned scrub keeps its pre-pause run time", "scripts/render.mjs",
     "          if (window.__mlPageOwned.has(a)) a.currentTime = 0;", "", "test_ownership_is_tested_not_guessed", True),
    ("a probe timeout does not abort", "scripts/render.mjs",
     "          if (msg.includes('timed out after')) return { page, errors, blocked, createdAnimations: candidates, aborted: true };", "",
     "test_a_hang_at_t0", True),
    ("guard root from the link's directory, not the real input's", "scripts/render.mjs",
     "  const root = path.dirname(realpathSync(path.resolve(o.file)));",
     "  const root = realpathSync(path.dirname(path.resolve(o.file)));", "test_a_symlinked_input", True),
    ("stale outputs kept", "scripts/render.mjs",
     "  for (const f of ['contact.png', 'anim.mp4', 'manifest.json']) rmSync(path.join(outDir, f), { force: true });", "",
     "test_stale_outputs", True),
    ("directory URLs served", "scripts/render.mjs",
     " && statSync(real).isFile();", ";", "test_directory_urls", True),
    ("Object.assign exposure not recognised", "scripts/motion_lint.py",
     "            if RENDER_AT_EXPOSED.search(keep) or exposed_by_object_call(keep, blank) or",
     "            if RENDER_AT_EXPOSED.search(keep) or", "test_object_calls_that_expose or test_object_assign_exposes", False),
    ("inline negated guard not recognised", "scripts/motion_lint.py",
     ' or (cond and cond.group(1).lstrip().startswith("!"))', "", "test_an_inline_negated_guard", False),
    ("probe samples only two times", "scripts/render.mjs",
     "      for (let i = 0; i < probeTimes.length; i++) {", "      for (const i of [0, Math.floor(probeTimes.length * 0.37)]) {",
     "test_a_scrub_that_starts_late", True),
    ("shadow-root animations not seeked", "scripts/render.mjs",
     "  window.__mlAllAnims = () => roots().flatMap((r) => r.getAnimations());",
     "  window.__mlAllAnims = () => document.getAnimations();", "test_ownership_is_tested_not_guessed", True),
    ("verify ignores a timeout", "scripts/render.mjs",
     "        if (info.timedOut) { verifyAborted = true; break; }", "", "test_a_hang_inside_verify", True),
    ("cleanup follows a symlinked frames dir", "scripts/render.mjs",
     "  if (existsSync(framesDir) && lstatSync(framesDir).isSymbolicLink()) {", "  if (false) {",
     "test_a_symlinked_frames_dir", True),
    ("font host by substring", "scripts/motion_lint.py",
     "    return host.lower() in FONT_HOSTS", "    return any(h in url for h in FONT_HOSTS)", "test_a_lookalike_font_host", False),
    ("inline handlers not linted", "scripts/motion_lint.py",
     "        for m in ON_ATTR.finditer(outside):", "        for m in ():", "test_inline_event_handlers", False),
    ("srcdoc not linted", "scripts/motion_lint.py",
     "        for m in SRCDOC.finditer(outside):", "        for m in ():", "test_srcdoc_documents", False),
    ("named loop guard ignored", "scripts/motion_lint.py",
     "        return bool(refs) and all(positional_guard(blank, keep, r) for r in refs)", "        return False",
     "test_a_named_preview_loop", False),
    ("Object.assign onto any object starting with window", "scripts/motion_lint.py",
     '        target = re.match(r"\\s*(?:window|globalThis|self)\\s*,", args)  # exactly the global, then a comma',
     '        target = re.match(r"\\s*(?:window|globalThis|self)\\b", args)', "test_assigning_onto_a_different", False),
    ("renderAt not called", "scripts/render.mjs",
     "      await window.renderAt(tt);\n      drew = true;\n", "",
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
