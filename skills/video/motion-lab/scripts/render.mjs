#!/usr/bin/env node
// render.mjs — freeze a code-first animation at every frame and save PNGs.
//
//   node render.mjs anim.html --seconds 6 --fps 24 [--width 1080 --height 1080]
//        [--scale 1] [--out out] [--every 12] [--verify | --verify-all] [--mp4] [--no-sheet] [--allow-static]
//
// Frames are 0..N-1 (N = seconds * fps): frame N is frame 0 again, and rendering
// it is the hiccup at a loop seam. Each frame is the page frozen at t = i / fps: the
// renderer seeks its document.getAnimations() entries (CSS animations, transitions,
// WAAPI) and every SVG SMIL timeline (<animate>, <animateTransform>, <set>, which
// getAnimations() does not list), then calls window.renderAt(t) LAST so renderAt
// wins. Animations the warm-up probe finds renderAt driving are left to the page.
// The result is exact however slow the machine.
//
// The page is loaded with ?t=0 so its own preview loop never starts (the render
// contract: "with ?t= never start requestAnimationFrame"); a running preview loop
// would redraw between our seek and the screenshot. If the page sets
// window.__ready, rendering waits for it (fonts, texture bakes).
//
// Outputs in --out: frames/0000.png..., contact.png (every --every-th frame with
// its frame number, laid out in the browser so the labels need no ffmpeg fonts),
// manifest.json, and anim.mp4 with --mp4 (needs ffmpeg on PATH).
//
// --verify reloads the page and re-renders the first, middle and last frames;
// any byte difference means a frame is not a pure function of t. It samples
// three frames on one machine: a pass is evidence, not proof, of purity, and the
// manifest says so (verify.scope). --verify-all re-renders every frame.
//
// Exit codes: 0 ok; 2 usage or runtime error; 3 --verify found an impure frame,
// or the ownership probe saw renderAt create an Animation;
// 4 --mp4 failed; 5 the page threw, or a renderAt call timed out (the render stops
// there and the manifest is still written; page_errors lists it); 6 nothing drives
// motion (no renderAt, no animations, no SMIL) and every frame is the same image
// (pass --allow-static when a still is what you want); 7 a frozen frame keeps
// changing on its own: something on the page still draws while it is frozen at a
// t (a preview loop its ?t= guard does not stop, a setTimeout chain, a worker).
// If nothing the renderer seeks drives the page but the frames still change, the
// motion runs on its own clock: exit 3, the same as an impure frame.
//
// Exit 7 is a DRIFT check: the renderer seeks a frame, screenshots it, waits
// 250 ms, and screenshots again. Static analysis cannot prove a guard wraps a loop
// (P20 rounds 1-3 kept finding shapes that fooled it), and counting
// requestAnimationFrame calls flagged a correct paused GSAP timeline, whose ticker
// keeps scheduling frames while drawing nothing (round 4). A pixel that changes
// while frozen is the thing that actually corrupts a render. The call counts are
// still recorded in manifest.loop_probe as a diagnostic.
//
// Untrusted input: the page is loaded from file://, and file:// requests outside
// the input file's directory are blocked (an <iframe src="file:///..."> could
// otherwise put a local file into a frame).
//
// Playwright is resolved from the CURRENT directory first, so the skill can live
// anywhere: run it from a project that has `npm i -D playwright` (or bun add -d).

import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { mkdirSync, writeFileSync, rmSync, existsSync, statSync, lstatSync, readdirSync, realpathSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';

function parseArgs(argv) {
  const o = { seconds: 6, fps: 24, width: 1080, height: 1080, scale: 1, out: 'out', every: 0, verify: false, verifyAll: false, mp4: false, sheet: true, allowStatic: false };
  const pos = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const val = () => { if (i + 1 >= argv.length) throw new Error(`${a} needs a value`); return argv[++i]; };
    if (a === '--seconds') o.seconds = Number(val());
    else if (a === '--fps') o.fps = Number(val());
    else if (a === '--width') o.width = Number(val());
    else if (a === '--height') o.height = Number(val());
    else if (a === '--scale') o.scale = Number(val());
    else if (a === '--out') o.out = val();
    else if (a === '--every') {
      o.every = Number(val());
      if (!Number.isInteger(o.every) || o.every < 1) throw new Error('--every must be a positive integer');
    }
    else if (a === '--verify') o.verify = true;
    else if (a === '--verify-all') { o.verify = true; o.verifyAll = true; }
    else if (a === '--mp4') o.mp4 = true;
    else if (a === '--no-sheet') o.sheet = false;
    else if (a === '--allow-static') o.allowStatic = true;
    else if (a.startsWith('--')) throw new Error(`unknown flag ${a}`);
    else pos.push(a);
  }
  if (pos.length !== 1) throw new Error('usage: node render.mjs <file.html> [--seconds 6 --fps 24 ...]');
  o.file = pos[0];
  for (const k of ['seconds', 'fps', 'width', 'height', 'scale']) {
    if (!(o[k] > 0) || !Number.isFinite(o[k])) throw new Error(`--${k} must be a positive number`);
  }
  if (Math.round(o.seconds * o.fps) < 1) throw new Error('--seconds x --fps rounds to zero frames');
  return o;
}

async function loadPlaywright() {
  const bases = [pathToFileURL(path.join(process.cwd(), 'noop.js')).href, import.meta.url];
  for (const base of bases) {
    for (const name of ['playwright', 'playwright-core']) {
      try {
        return createRequire(base)(name); // playwright is CommonJS: require() exposes chromium directly
      } catch { /* try the next base */ }
    }
  }
  throw new Error('playwright not found. In your project: npm i -D playwright && npx playwright install chromium');
}

// Injected before any page script. Counts the page's own frame scheduling and
// keeps an unwrapped requestAnimationFrame for the renderer's waits, so the
// renderer's own rAF calls are never counted against the page.
const LOOP_PROBE = `(() => {
  const raf = window.requestAnimationFrame.bind(window);
  const si = window.setInterval.bind(window);
  window.__mlRAF = raf;
  window.__mlCounts = { raf: 0, interval: 0 };
  window.requestAnimationFrame = function (cb) { window.__mlCounts.raf++; return raf(cb); };
  // document.getAnimations() does not include animations inside shadow roots
  // (P20 round 7): walk every open shadow root too.
  const roots = () => {
    const out = [document];
    for (let i = 0; i < out.length; i++)
      for (const el of out[i].querySelectorAll('*')) if (el.shadowRoot) out.push(el.shadowRoot);
    return out;
  };
  window.__mlAllAnims = () => roots().flatMap((r) => r.getAnimations());
  window.__mlAllSvgs = () => roots().flatMap((r) => [...r.querySelectorAll('svg')]);
  window.__mlSmilCount = () => roots().reduce((n, r) => n + r.querySelectorAll('animate, animateTransform, animateMotion, set').length, 0);
  window.setInterval = function (...a) { window.__mlCounts.interval++; return si(...a); };
})();`;

const FRAME_TIMEOUT_MS = Number(process.env.MOTION_LAB_FRAME_TIMEOUT_MS) > 0
  ? Number(process.env.MOTION_LAB_FRAME_TIMEOUT_MS) : 30000; // per renderAt call
const DRIFT_WAIT_MS = 250;

function withTimeout(promise, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label}: timed out after ${FRAME_TIMEOUT_MS} ms`)), FRAME_TIMEOUT_MS);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function openAt(browser, o, url, probeTimes = []) {
  const page = await browser.newPage({ viewport: { width: o.width, height: o.height }, deviceScaleFactor: o.scale });
  await page.addInitScript(LOOP_PROBE);
  // Allowed: regular files whose REAL path (symlinks resolved) lies under the real
  // directory of the real input file, with no dot-named segment (.env, .git) below
  // it. A string prefix on the URL let a symlink escape and showed sibling dotfiles
  // (round 5); resolving the input itself keeps a symlinked anim.html renderable
  // (round 6). Directory URLs are refused (they would list file names).
  const root = path.dirname(realpathSync(path.resolve(o.file)));
  const blocked = [];
  await page.route('file://**', (route) => {
    const u = route.request().url();
    let ok = false;
    try {
      const real = realpathSync(fileURLToPath(u));
      const rel = path.relative(root, real);
      ok = rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel)
        && !rel.split(path.sep).some((seg) => seg.startsWith('.')) && statSync(real).isFile();
    } catch { ok = false; } // missing file or unparsable URL: nothing to serve
    if (ok) return route.continue();
    blocked.push(u);
    return route.abort();
  });
  const errors = [];
  const createdAnimations = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(url, { waitUntil: 'load' });
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    if ('__ready' in window) {
      const t0 = Date.now(); // renderer-side wait, not page animation time
      while (!window.__ready && Date.now() - t0 < 30000) await new Promise((r) => setTimeout(r, 50));
    }
  });
  try {
    // Warm-up. Let CSS/WAAPI animations actually START before anything pauses them:
    // pausing one the compositor has not picked up yet leaves the element rastered
    // on the main thread, so the first frame comes out with different edge pixels
    // than every later frame (measured on macOS Chromium).
    //
    // Then decide who drives each animation, by TESTING rather than guessing: call
    // renderAt at two times and see which paused animations it changed. Those are
    // page-owned (a scrub through a negative animation-delay, a WAAPI animation
    // renderAt positions) and the renderer leaves them alone; every other animation
    // is the renderer's and is seeked to t. Guessing "paused by the page = the
    // page's" froze any page that paused its CSS under ?t= (P20 round 6).
    await withTimeout(page.evaluate(async () => {
      const anims = window.__mlAllAnims ? window.__mlAllAnims() : document.getAnimations();
      await Promise.all(anims.map((a) => a.ready.catch(() => {})));
      const tick = window.__mlRAF || window.requestAnimationFrame.bind(window);
      for (let k = 0; k < 2; k++) await new Promise((r) => tick(() => r()));
      window.__mlPageOwned = new WeakSet();
      window.__mlProbeSig = null;
      window.__mlRenderAtCreated = [];
    }), 'warm-up');
    // Ownership probe: call renderAt at EVERY frame time (no screenshots, so it is
    // cheap) and mark as page-owned any paused animation whose timing renderAt
    // changed between consecutive calls. An animation that first appears after a
    // call is a different finding: renderAt started it on the wall clock, so a
    // frame cannot be a pure function of t. Two sample times (t=0 and 0.37 x
    // duration) missed a scrub renderAt only drives later in the timeline (P20
    // round 7). Each call has its own timeout; a throw is recorded and the probe
    // goes on.
    const hasRenderAt = await page.evaluate(() => typeof window.renderAt === 'function');
    if (hasRenderAt) {
      for (let i = 0; i < probeTimes.length; i++) {
        const t = probeTimes[i];
        try {
          await withTimeout(page.evaluate(async (tt) => {
            const all = () => window.__mlAllAnims ? window.__mlAllAnims() : document.getAnimations();
            const sig = (a) => {
              const tm = a.effect && a.effect.getTiming ? a.effect.getTiming() : {};
              return [a.currentTime, tm.delay, tm.duration, tm.iterationStart].join('|');
            };
            const animationFinding = (a) => {
              const target = a.effect && a.effect.target;
              return {
                frame_time: tt,
                animationName: typeof a.animationName === 'string' && a.animationName ? a.animationName : null,
                id: typeof a.id === 'string' && a.id ? a.id : null,
                target: target && target.tagName
                  ? `${target.tagName.toLowerCase()}${target.id ? `#${target.id}` : ''}` : null,
              };
            };
            const before = new Set(all());
            await window.renderAt(tt);
            const cur = new Map(all().map((a) => [a, sig(a)]));
            // MUTATION_ANCHOR: a newly-created Animation begins from wall-clock
            // time; even if a later call cancels and recreates it, that new identity
            // is another finding.
            for (const a of cur.keys()) if (!before.has(a)) window.__mlRenderAtCreated.push(animationFinding(a));
            const prev = window.__mlProbeSig;
            // a running animation's clock moves by itself, so only a PAUSED one
            // whose timing changed was changed by renderAt
            if (prev) for (const [a, sg] of cur) if (a.playState === 'paused' && prev.has(a) && prev.get(a) !== sg) window.__mlPageOwned.add(a);
            window.__mlProbeSig = cur;
          }, t), `warm-up probe t=${t}`);
        } catch (e) {
          const msg = String(e.message || e).split('\n')[0];
          errors.push(msg.startsWith('warm-up probe') ? msg : `warm-up probe t=${t}: ${msg}`);
          if (msg.includes('timed out after')) return { page, errors, blocked, createdAnimations, aborted: true };
        }
      }
      await page.evaluate(() => {
        window.__mlProbeSig = null;
        // a delay-positioned scrub must not carry the time it ran before renderAt paused it
        for (const a of (window.__mlAllAnims ? window.__mlAllAnims() : document.getAnimations()))
          if (window.__mlPageOwned.has(a)) a.currentTime = 0;
      });
      createdAnimations.push(...await page.evaluate(() => window.__mlRenderAtCreated || []));
    }
    const first = await frameAt(page, 0, errors);
    if (first.timedOut) return { page, errors, blocked, createdAnimations, aborted: true };
    await page.screenshot({ timeout: FRAME_TIMEOUT_MS });
  } catch (e) {
    errors.push(String(e.message || e).split('\n')[0]);
    return { page, errors, blocked, createdAnimations, aborted: true };
  }
  return { page, errors, blocked, createdAnimations, aborted: false };
}

function describeCreatedAnimation(finding) {
  const identity = finding.animationName ? `CSS animation "${finding.animationName}"`
    : finding.id ? `animation id "${finding.id}"` : 'unnamed animation';
  return `${identity}${finding.target ? ` on ${finding.target}` : ''}`;
}

async function frameAt(page, t, errors = []) {
  try {
    return await withTimeout(frameAtUnsafe(page, t), 'renderAt');
  } catch (e) {
    // renderAt threw for this t: record it (exit 5) instead of aborting the render
    const msg = String(e.message || e).split('\n')[0];
    errors.push(`frame t=${t}: ${msg}`);
    return { drew: true, anims: 0, smil: 0, threw: true, timedOut: msg.includes('timed out after') };
  }
}

async function drifts(page, t, errors) {
  // Seek t, capture, wait, capture again: a frozen frame must not change.
  const info = await frameAt(page, t, errors);
  if (info.timedOut) return { drift: false, timedOut: true };
  try {
    const a = await page.screenshot({ timeout: FRAME_TIMEOUT_MS });
    await page.waitForTimeout(DRIFT_WAIT_MS);
    const b = await page.screenshot({ timeout: FRAME_TIMEOUT_MS });
    return { drift: !a.equals(b), timedOut: false };
  } catch (e) {
    errors.push(`drift capture t=${t}: ${String(e.message || e).split('\n')[0]}`);
    return { drift: false, timedOut: true };
  }
}

async function frameAtUnsafe(page, t) {
  return page.evaluate(async (tt) => {
    const tick = window.__mlRAF || window.requestAnimationFrame.bind(window);
    // Seek first and call renderAt LAST, so renderAt wins for anything it sets
    // itself (P20 round 5). Animations the warm-up probe found renderAt driving are
    // page-owned and left alone; the renderer seeks every other one.
    const pageOwned = window.__mlPageOwned || new WeakSet();
    const anims = window.__mlAllAnims ? window.__mlAllAnims() : document.getAnimations();
    let seeked = 0;
    for (const a of anims) {
      if (pageOwned.has(a)) continue;
      a.pause();
      a.currentTime = tt * 1000;
      seeked++;
    }
    // SVG SMIL is not in getAnimations(): seek each <svg> document timeline.
    for (const svg of (window.__mlAllSvgs ? window.__mlAllSvgs() : document.querySelectorAll('svg'))) {
      if (typeof svg.pauseAnimations === 'function') { svg.pauseAnimations(); svg.setCurrentTime(tt); }
    }
    const smil = window.__mlSmilCount ? window.__mlSmilCount()
      : document.querySelectorAll('animate, animateTransform, animateMotion, set').length;
    // A just-started CSS animation is still pending; seeking it and screenshotting
    // in the same frame can capture the pre-seek pose. Wait for every animation to
    // be ready before renderAt and the capture.
    await Promise.all(anims.map((a) => a.ready.catch(() => {})));
    let drew = false;
    if (typeof window.renderAt === 'function') { await window.renderAt(tt); drew = true; }
    for (let k = 0; k < 2; k++) await new Promise((r) => tick(() => r()));
    return { drew, anims: anims.length, smil, page_owned: anims.length - seeked };
  }, t);
}

function sheetHtml(picks) {
  const cells = picks.map((i) => `<figure><img src="frames/${String(i).padStart(4, '0')}.png"><figcaption>F ${String(i).padStart(3, '0')}</figcaption></figure>`).join('');
  return `<!doctype html><meta charset="utf-8"><style>
    body{margin:0;background:#fff;font:600 22px ui-monospace,Menlo,monospace}
    main{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:8px}
    figure{margin:0}img{width:100%;display:block;outline:1px solid #ddd}
    figcaption{padding:4px 0;color:#111}</style><main>${cells}</main>`;
}

async function main() {
  const o = parseArgs(process.argv.slice(2));
  if (!existsSync(o.file)) throw new Error(`no such file: ${o.file}`);
  if (statSync(o.file).isDirectory()) throw new Error(`not a file: ${o.file}`);
  const N = Math.round(o.seconds * o.fps);
  const outDir = path.resolve(o.out);
  const framesDir = path.join(outDir, 'frames');
  const framePath = (i) => path.join(framesDir, `${String(i).padStart(4, '0')}.png`);

  const url = new URL(pathToFileURL(realpathSync(path.resolve(o.file))).href); // a symlinked input loads its target
  url.searchParams.set('t', '0');

  const { chromium } = await loadPlaywright();
  // Only now touch the output: remove earlier frame PNGs (NNNN.png) and nothing else.
  // Never delete THROUGH a symlink: a pre-existing out/frames link would point the
  // cleanup at someone else's PNGs (P20 round 7).
  if (existsSync(framesDir) && lstatSync(framesDir).isSymbolicLink()) {
    throw new Error(`refusing to use ${framesDir}: it is a symlink`);
  }
  mkdirSync(framesDir, { recursive: true });
  for (const f of readdirSync(framesDir)) if (/^\d{4,}\.png$/.test(f)) rmSync(path.join(framesDir, f));
  // and this renderer's own earlier outputs, so an aborted or --no-sheet run never
  // leaves a previous run's contact sheet, MP4 or manifest looking current
  for (const f of ['contact.png', 'anim.mp4', 'manifest.json']) rmSync(path.join(outDir, f), { force: true });
  const browser = await chromium.launch();
  const manifest = { file: o.file, seconds: o.seconds, fps: o.fps, frames: N, render_range: [0, N - 1],
    ...(Math.abs(o.seconds * o.fps - N) > 1e-9 ? { note: `seconds x fps = ${o.seconds * o.fps}, rounded to ${N} frames` } : {}),
    width: o.width, height: o.height, scale: o.scale, frames_dir: framesDir };
  // Findings are collected first and turned into ONE exit code at the end, so an
  // error raised by a late pass (drift, verify) still counts.
  const flags = { impure: false, errors: false, drift: false, static: false, mp4: false };
  let aborted = false;
  try {
    const probeTimes = Array.from({ length: N }, (_, i) => i / o.fps);
    const opened = await openAt(browser, o, url.href, probeTimes);
    const { page, errors, blocked, createdAnimations } = opened;
    manifest.page_errors = errors;
    manifest.blocked_requests = blocked;
    if (createdAnimations.length) {
      manifest.renderat_created_animations = createdAnimations;
      manifest.warning = `renderAt created ${describeCreatedAnimation(createdAnimations[0])} after frame t=${createdAnimations[0].frame_time}; the animation depends on the wall clock`;
      flags.impure = true;
    }
    if (opened.aborted) { aborted = true; manifest.aborted_at_frame = 0; }
    // Early drift sample, before the frame loop: a one-shot intro that plays for a
    // while after load and then stops corrupts the first frames and is gone by the
    // time the post-render sample runs (P20 round 5).
    const early = aborted ? { drift: false, timedOut: false } : await drifts(page, 0, errors);
    if (early.timedOut) { aborted = true; manifest.aborted_at_frame = 0; }
    const before = aborted ? { raf: 0, interval: 0 }
      : await page.evaluate(() => ({ ...(window.__mlCounts || { raf: 0, interval: 0 }) }));
    let drive = null;
    for (let i = 0; i < N && !aborted; i++) {
      const info = await frameAt(page, i / o.fps, errors);
      if (info.timedOut) {
        // A hung renderAt hangs every later frame too (a never-settling promise, or
        // a synchronous loop that also blocks screenshots): stop instead of paying
        // the timeout N times, and still write the manifest.
        aborted = true;
        manifest.aborted_at_frame = i;
        break;
      }
      if (drive === null && !info.threw) drive = info;
      try {
        await page.screenshot({ path: framePath(i), timeout: FRAME_TIMEOUT_MS });
      } catch (e) {
        errors.push(`screenshot(${i}): ${String(e.message || e).split('\n')[0]}`);
        aborted = true;
        manifest.aborted_at_frame = i;
        break;
      }
    }
    manifest.driven_by = drive
      ? { renderAt: drive.drew, animations: drive.anims, smil: drive.smil, page_owned: drive.page_owned } : null;

    if (!aborted) {
      const after = await page.evaluate(() => ({ ...(window.__mlCounts || { raf: 0, interval: 0 }) }));
      // Diagnostic: a paused GSAP timeline keeps its ticker scheduling frames while
      // drawing nothing, so a count alone is not evidence of a live loop.
      manifest.loop_probe = { raf_during_render: after.raf - before.raf, intervals: after.interval };
      // page-owned animations are not driven by the renderer; with no renderAt
      // there are none (the probe only runs when renderAt exists)
      if (drive && !drive.drew && drive.anims - drive.page_owned === 0 && drive.smil === 0) {
        const { readFileSync } = await import('node:fs');
        const first = readFileSync(framePath(0));
        const changes = Array.from({ length: N - 1 }, (_, k) => k + 1).some((i) => !readFileSync(framePath(i)).equals(first));
        if (changes) {
          // e.g. SMIL inside an <img src="data:image/svg+xml...">, a <video>, a CSS
          // background the renderer cannot reach: motion that ignores t.
          manifest.warning = 'frames change but nothing the renderer seeks drives them: the motion runs on its own clock';
          flags.impure = true;
        } else {
          manifest.warning = 'no window.renderAt, no document animations and no SMIL: every frame is the same image';
          flags.static = !o.allowStatic;
        }
      }
      const driftPicks = [...new Set([0, Math.floor(N / 2), N - 1])];
      const drifting = [];
      for (const i of driftPicks) {
        const d = await drifts(page, i / o.fps, errors);
        if (d.drift) drifting.push(i);
        if (d.timedOut) { aborted = true; manifest.aborted_at_frame = i; break; }
      }
      manifest.drift = { early: early.drift, frames: driftPicks, drifting, wait_ms: DRIFT_WAIT_MS };
      if (early.drift || drifting.length) {
        const msg = 'a frozen frame keeps changing on its own: something still draws while the page is frozen '
          + '(a preview loop the ?t= guard does not stop, a timer chain, a worker, an intro that plays after load, '
          + 'or a CSS transition or animation that renderAt starts)';
        if (manifest.warning) (manifest.notes = manifest.notes || []).push(msg); // keep the more specific warning
        else manifest.warning = msg;
        flags.drift = true;
      } else if (!aborted && manifest.loop_probe.raf_during_render >= 2) {
        manifest.notes = ['the page scheduled frames under ?t= but nothing drifted at the sampled moments; '
          + 'if it has a one-shot intro or a loop slower than 250 ms, run --verify-all'];
      }
    }
    if (!aborted) await page.close();

    if (o.verify && !aborted) {
      // Re-render OUT of the first pass's order. A renderAt that depends on its
      // call history (a counter, an accumulator) replays identically when the
      // frames come in the same order, so an in-order --verify-all passed an
      // impure page with zero mismatches. Reverse order breaks that replay.
      const picks = o.verifyAll ? Array.from({ length: N }, (_, i) => N - 1 - i)
        : [...new Set([0, Math.floor(N / 2), N - 1])].filter((i) => i >= 0);
      const v = await openAt(browser, o, url.href, probeTimes);
      errors.push(...v.errors.map((e) => `verify: ${e}`));
      const { readFileSync } = await import('node:fs');
      const mismatches = [];
      let verifyAborted = v.aborted;
      for (const i of picks) {
        if (verifyAborted) break;
        const info = await frameAt(v.page, i / o.fps, errors);
        if (info.timedOut) { verifyAborted = true; break; }
        let again;
        try {
          again = await v.page.screenshot({ timeout: FRAME_TIMEOUT_MS });
        } catch (e) {
          errors.push(`verify screenshot(${i}): ${String(e.message || e).split('\n')[0]}`);
          verifyAborted = true;
          break;
        }
        if (!again.equals(readFileSync(framePath(i)))) mismatches.push(i);
      }
      if (!verifyAborted) await v.page.close();
      mismatches.sort((a, b) => a - b);
      // pure is unknown (null) when the check did not finish
      manifest.verify = { frames: [...picks].sort((a, b) => a - b), mismatches,
        pure: verifyAborted ? null : mismatches.length === 0,
        scope: o.verifyAll ? `all ${N} frames` : `sampled ${picks.length} of ${N} frames`,
        ...(verifyAborted ? { aborted: true } : {}) };
      // a timeout is a page error (exit 5), not evidence of impurity
      if (mismatches.length) flags.impure = true;
      if (verifyAborted) aborted = true;
    }
    flags.errors = errors.length > 0;

    if (o.sheet && N > 0 && !aborted) {
      // Up to 12 frames spread evenly from 0 to N-1, so the seam frame is always
      // on the sheet. --every N takes every Nth frame instead (still capped at 12).
      let picks;
      if (o.every > 0) {
        picks = [];
        for (let i = 0; i < N && picks.length < 11; i += o.every) picks.push(i);
        if (picks[picks.length - 1] !== N - 1) picks.push(N - 1); // the seam frame is always on the sheet
      } else {
        const k = Math.min(12, N);
        picks = [...new Set(Array.from({ length: k }, (_, j) => (k === 1 ? 0 : Math.round((j * (N - 1)) / (k - 1)))))];
      }
      const sheetFile = path.join(outDir, 'contact.html');
      writeFileSync(sheetFile, sheetHtml(picks));
      const sp = await browser.newPage({ viewport: { width: 1600, height: 900 } });
      await sp.goto(pathToFileURL(sheetFile).href, { waitUntil: 'load' });
      await sp.screenshot({ path: path.join(outDir, 'contact.png'), fullPage: true });
      await sp.close();
      rmSync(sheetFile, { force: true });
      manifest.contact_sheet = path.join(outDir, 'contact.png');
      manifest.contact_frames = picks;
    }
  } catch (e) {
    // Anything unexpected still produces a manifest (exit 2), never a bare traceback.
    manifest.fatal = String(e.message || e).split('\n')[0];
    aborted = true;
  } finally {
    // A page stuck in a synchronous loop can stall a graceful close; do not wait forever.
    // unref: the fallback timer must not keep Node alive after a normal close.
    await Promise.race([browser.close(), new Promise((r) => setTimeout(r, 5000).unref())]);
  }

  if (o.mp4 && !aborted) {
    const mp4 = path.join(outDir, 'anim.mp4');
    const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(o.fps), '-i', path.join(framesDir, '%04d.png'),
      '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart',
      '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', mp4], { stdio: 'inherit' });
    if (r.error || r.status !== 0) { manifest.mp4_error = String(r.error || `ffmpeg exit ${r.status}`); flags.mp4 = true; }
    else manifest.mp4 = mp4;
  }

  // One exit code, by precedence: impurity outranks a page error, which outranks
  // drift, a static page and a failed MP4.
  const exitCode = manifest.fatal ? 2
    : flags.impure ? 3 : flags.errors ? 5 : flags.drift ? 7 : flags.static ? 6 : flags.mp4 ? 4 : 0;
  manifest.exit_code = exitCode;
  writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  process.exitCode = exitCode;
  // After an abort, exit once stdout has flushed (a pipe is asynchronous): do not
  // linger on a hung browser, and do not cut the manifest line short.
  process.stdout.write(JSON.stringify(manifest) + '\n', () => { if (aborted) process.exit(exitCode); });
}

main().catch((e) => { process.stderr.write(`render.mjs: ${e.message}\n`); process.exitCode = 2; });
