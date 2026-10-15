#!/usr/bin/env node
// render.mjs — freeze a code-first animation at every frame and save PNGs.
//
//   node render.mjs anim.html --seconds 6 --fps 24 [--width 1080 --height 1080]
//        [--scale 1] [--out out] [--every 12] [--verify | --verify-all] [--mp4] [--no-sheet] [--allow-static]
//
// Frames are 0..N-1 (N = seconds * fps): frame N is frame 0 again, and rendering
// it is the hiccup at a loop seam. Each frame is the page frozen at t = i / fps by
// calling window.renderAt(t) (when the page defines it), seeking every
// document.getAnimations() entry (CSS animations, transitions, WAAPI) and seeking
// every SVG SMIL timeline (<animate>, <animateTransform>, <set>, which
// getAnimations() does not list), so the result is exact however slow the machine.
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
// Exit codes: 0 ok; 2 usage or runtime error; 3 --verify found an impure frame;
// 4 --mp4 failed; 5 the page threw (page_errors in the manifest); 6 nothing drives
// motion (no renderAt, no animations, no SMIL) and every frame is the same image:
// pass --allow-static when a still is what you want. If nothing the renderer seeks
// drives the page but the frames still change, the motion runs on its own clock:
// exit 3, the same as an impure frame.
//
// Playwright is resolved from the CURRENT directory first, so the skill can live
// anywhere: run it from a project that has `npm i -D playwright` (or bun add -d).

import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { mkdirSync, writeFileSync, rmSync, existsSync } from 'node:fs';
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
    else if (a === '--every') o.every = Number(val());
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

async function openAt(browser, o, url) {
  const page = await browser.newPage({ viewport: { width: o.width, height: o.height }, deviceScaleFactor: o.scale });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(url, { waitUntil: 'load' });
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    if ('__ready' in window) {
      const t0 = Date.now(); // renderer-side wait, not page animation time
      while (!window.__ready && Date.now() - t0 < 30000) await new Promise((r) => setTimeout(r, 50));
    }
  });
  // Warm-up. Let CSS/WAAPI animations actually START before anything pauses them:
  // pausing one the compositor has not picked up yet leaves the element rastered on
  // the main thread, so the first frame comes out with different edge pixels than
  // every later frame (measured: a cold first run differed only at frame 0, only on
  // an animated element's antialiased edge). Then draw frame 0 once and discard it.
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().map((a) => a.ready.catch(() => {})));
    for (let k = 0; k < 2; k++) await new Promise((r) => requestAnimationFrame(() => r()));
  });
  await frameAt(page, 0);
  await page.screenshot();
  return { page, errors };
}

async function frameAt(page, t) {
  return page.evaluate(async (tt) => {
    let drew = false;
    if (typeof window.renderAt === 'function') { await window.renderAt(tt); drew = true; }
    const anims = document.getAnimations();
    for (const a of anims) { a.pause(); a.currentTime = tt * 1000; }
    // SVG SMIL is not in getAnimations(): seek each <svg> document timeline.
    let smil = 0;
    for (const svg of document.querySelectorAll('svg')) {
      if (typeof svg.pauseAnimations === 'function') { svg.pauseAnimations(); svg.setCurrentTime(tt); }
    }
    smil = document.querySelectorAll('animate, animateTransform, animateMotion, set').length;
    // A just-started CSS animation is still pending; seeking it and screenshotting
    // in the same frame can capture the pre-seek pose. Wait for every animation to
    // be ready, then two frames so the compositor has committed the paused state.
    await Promise.all(anims.map((a) => a.ready.catch(() => {})));
    for (let k = 0; k < 2; k++) await new Promise((r) => requestAnimationFrame(() => r()));
    return { drew, anims: anims.length, smil };
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
  const N = Math.round(o.seconds * o.fps);
  const outDir = path.resolve(o.out);
  const framesDir = path.join(outDir, 'frames');
  rmSync(framesDir, { recursive: true, force: true });
  mkdirSync(framesDir, { recursive: true });

  const url = new URL(pathToFileURL(path.resolve(o.file)).href);
  url.searchParams.set('t', '0');

  const { chromium } = await loadPlaywright();
  const browser = await chromium.launch();
  const manifest = { file: o.file, seconds: o.seconds, fps: o.fps, frames: N, render_range: [0, N - 1],
    width: o.width, height: o.height, scale: o.scale, frames_dir: framesDir };
  let exitCode = 0;
  try {
    const { page, errors } = await openAt(browser, o, url.href);
    let drive = null;
    for (let i = 0; i < N; i++) {
      const info = await frameAt(page, i / o.fps);
      if (drive === null) drive = info;
      await page.screenshot({ path: path.join(framesDir, `${String(i).padStart(4, '0')}.png`) });
    }
    manifest.driven_by = drive ? { renderAt: drive.drew, animations: drive.anims, smil: drive.smil } : null;
    manifest.page_errors = errors;
    if (errors.length) exitCode = 5;
    if (drive && !drive.drew && drive.anims === 0 && drive.smil === 0) {
      const { readFileSync } = await import('node:fs');
      const frame = (i) => readFileSync(path.join(framesDir, `${String(i).padStart(4, '0')}.png`));
      const first = frame(0);
      const changes = Array.from({ length: N - 1 }, (_, k) => k + 1).some((i) => !frame(i).equals(first));
      if (changes) {
        // e.g. SMIL inside an <img src="data:image/svg+xml...">, a <video>, a CSS
        // background the renderer cannot reach: motion that ignores t.
        manifest.warning = 'frames change but nothing the renderer seeks drives them: the motion runs on its own clock';
        exitCode = exitCode || 3;
      } else {
        manifest.warning = 'no window.renderAt, no document animations and no SMIL: every frame is the same image';
        if (!o.allowStatic && !exitCode) exitCode = 6;
      }
    }
    await page.close();

    if (o.verify) {
      // Re-render OUT of the first pass's order. A renderAt that depends on its
      // call history (a counter, an accumulator) replays identically when the
      // frames come in the same order, so an in-order --verify-all passed an
      // impure page with zero mismatches. Reverse order breaks that replay.
      const picks = o.verifyAll ? Array.from({ length: N }, (_, i) => N - 1 - i)
        : [...new Set([0, Math.floor(N / 2), N - 1])].filter((i) => i >= 0);
      const { page: p2 } = await openAt(browser, o, url.href);
      const { readFileSync } = await import('node:fs');
      const mismatches = [];
      for (const i of picks) {
        await frameAt(p2, i / o.fps);
        const again = await p2.screenshot();
        const first = readFileSync(path.join(framesDir, `${String(i).padStart(4, '0')}.png`));
        if (!again.equals(first)) mismatches.push(i);
      }
      await p2.close();
      mismatches.sort((a, b) => a - b);
      manifest.verify = { frames: [...picks].sort((a, b) => a - b), mismatches, pure: mismatches.length === 0,
        scope: o.verifyAll ? `all ${N} frames` : `sampled ${picks.length} of ${N} frames` };
      if (mismatches.length) exitCode = 3; // impurity outranks the other findings
    }

    if (o.sheet && N > 0) {
      // Up to 12 frames spread evenly from 0 to N-1, so the seam frame is always
      // on the sheet. --every N takes every Nth frame instead (still capped at 12).
      let picks;
      if (o.every > 0) {
        picks = [];
        for (let i = 0; i < N && picks.length < 12; i += o.every) picks.push(i);
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
  } finally {
    await browser.close();
  }

  if (o.mp4) {
    const mp4 = path.join(outDir, 'anim.mp4');
    const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(o.fps), '-i', path.join(framesDir, '%04d.png'),
      '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart',
      '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', mp4], { stdio: 'inherit' });
    if (r.error || r.status !== 0) { manifest.mp4_error = String(r.error || `ffmpeg exit ${r.status}`); exitCode = exitCode || 4; }
    else manifest.mp4 = mp4;
  }

  writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  process.stdout.write(JSON.stringify(manifest) + '\n');
  process.exitCode = exitCode;
}

main().catch((e) => { process.stderr.write(`render.mjs: ${e.message}\n`); process.exitCode = 2; });
