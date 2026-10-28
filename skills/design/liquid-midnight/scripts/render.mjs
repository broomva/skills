#!/usr/bin/env node
// Render Liquid Midnight pages to PNG at chosen times, formats and modes, so the work can be LOOKED AT (DESIGN.md §13).
//   node render.mjs <root-dir> <page.html> [--t 0,2.5,6] [--format keynote,reel,feed] [--mode night,day] [--out dir]
// Serves <root-dir> on 127.0.0.1 (dotfiles refused), opens <page>?t=..&format=..&mode=.. and waits for window.__ready
// (pages built on kit/loop.js set it after renderAt). Needs Playwright with Chromium:
//   npm i -D playwright && npx playwright install chromium      (or set LM_PLAYWRIGHT_DIR to a dir that has it)
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { startServer } from "./serve.mjs";

function loadPlaywright() {
  const bases = [process.env.LM_PLAYWRIGHT_DIR, process.cwd()].filter(Boolean);
  for (const b of bases) {
    try {
      return createRequire(join(resolve(b), "noop.js"))("playwright");
    } catch {}
  }
  console.error("render.mjs needs Playwright: `npm i -D playwright && npx playwright install chromium` (or set LM_PLAYWRIGHT_DIR)");
  process.exit(3);
}

const list = (v, d) => (v ? v.split(",").filter(Boolean) : d);
export function parseArgs(argv) {
  const [root, page, ...rest] = argv;
  const o = { root, page, t: ["0", "2", "6"], format: ["keynote"], mode: ["night", "day"], out: "renders" };
  for (let i = 0; i < rest.length; i++) {
    const k = rest[i].replace(/^--/, "");
    if (!(k in o)) throw new Error(`unknown option ${rest[i]}`);
    o[k] = k === "out" ? rest[++i] : list(rest[++i], o[k]);
  }
  for (const t of o.t) if (!Number.isFinite(Number(t)) || Number(t) < 0 || Number(t) > 3600) throw new Error(`--t values must be seconds in [0, 3600], got ${t}`);
  return o;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  let o;
  try {
    o = parseArgs(process.argv.slice(2));
    if (!o.root || !o.page) throw new Error("usage: render.mjs <root-dir> <page.html> [--t 0,2,6] [--format keynote,reel,feed] [--mode night,day] [--out dir]");
  } catch (e) {
    console.error(e.message);
    process.exit(2);
  }
  const { chromium } = loadPlaywright();
  const server = await startServer(resolve(o.root), 0);
  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const errors = [];
  mkdirSync(o.out, { recursive: true });
  const SIZE = { keynote: [1920, 1080], reel: [1080, 1920], feed: [1080, 1350] };
  try {
    for (const format of o.format)
      for (const mode of o.mode) {
        const [w, h] = SIZE[format] ?? SIZE.keynote;
        const page = await browser.newPage({ viewport: { width: w, height: h } });
        page.on("pageerror", (e) => errors.push(`${format}/${mode}: ${e.message}`));
        for (const t of o.t) {
          await page.goto(`http://127.0.0.1:${server.port}/${o.page.replace(/^\//, "")}?t=${t}&format=${format}&mode=${mode}`);
          await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 });
          const file = join(o.out, `${o.page.replace(/[^a-z0-9]+/gi, "-").replace(/-html$/, "")}-${format}-${mode}-t${t}.png`);
          await page.screenshot({ path: file });
          console.log(`rendered ${file}`);
        }
        await page.close();
      }
  } finally {
    await browser.close();
    server.stop(true);
  }
  if (errors.length) {
    console.error(`page errors:\n${errors.join("\n")}`);
    process.exit(1);
  }
}
