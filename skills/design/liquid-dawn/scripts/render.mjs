#!/usr/bin/env node
// Render Liquid Dawn pages to PNG at chosen times and modes, so the work can be LOOKED AT (DESIGN.md §11).
//   node scripts/render.mjs <root-dir> <page.html> [--t 0,4,9] [--mode dawn,dusk] [--width 1440] [--shots all|full|hero,fields]
//                           [--out renders]
// Serves <root-dir> on 127.0.0.1, opens <page>?t=..&mode=.., waits for window.__ready (set after renderAt), then
// screenshots the full page ("full") and/or every [data-shot] element. Needs Playwright with Chromium:
//   npm i -D playwright && npx playwright install chromium     (or set LD_PLAYWRIGHT_DIR to a dir that has it)
import { mkdirSync, realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { startServer } from "./serve.mjs";

export function loadPlaywright() {
  for (const b of [process.env.LD_PLAYWRIGHT_DIR, process.cwd()].filter(Boolean)) {
    try {
      return createRequire(join(resolve(b), "noop.js"))("playwright");
    } catch {}
  }
  return null;
}

export function parseArgs(argv) {
  const [root, page, ...rest] = argv;
  if (!root || !page) throw new Error("usage: render.mjs <root-dir> <page.html> [--t 0,4] [--mode dawn,dusk] [--width 1440] [--shots all] [--out dir]");
  const o = { root, page, t: ["0", "4", "9"], mode: ["dawn", "dusk"], width: "1440", shots: "all", out: "renders" };
  for (let i = 0; i < rest.length; i++) {
    const k = rest[i].replace(/^--/, "");
    if (!["t", "mode", "width", "shots", "out"].includes(k)) throw new Error(`unknown option ${rest[i]}`);
    const v = rest[++i];
    if (v === undefined || v.startsWith("--")) throw new Error(`--${k} needs a value`);
    o[k] = k === "t" || k === "mode" ? v.split(",").filter(Boolean) : v;
  }
  for (const t of o.t) if (!(Number(t) >= 0)) throw new Error(`--t: not a time: ${t}`);
  for (const m of o.mode) if (!["dawn", "dusk"].includes(m)) throw new Error(`--mode: dawn or dusk, got ${m}`);
  return o;
}

export async function render(o) {
  const pw = loadPlaywright();
  if (!pw) {
    console.error("render.mjs needs Playwright: `npm i -D playwright && npx playwright install chromium` (or set LD_PLAYWRIGHT_DIR)");
    process.exit(3);
  }
  const rootDir = resolve(o.root);
  const rel = relative(rootDir, resolve(rootDir, o.page)).split("\\").join("/");
  const { server, url } = await startServer(rootDir);
  const browser = await pw.chromium.launch();
  const written = [];
  try {
    mkdirSync(o.out, { recursive: true });
    for (const mode of o.mode)
      for (const t of o.t) {
        const page = await browser.newPage({ viewport: { width: Number(o.width), height: 900 }, deviceScaleFactor: 1 });
        const errors = [];
        page.on("pageerror", (e) => errors.push(e.message));
        const res = await page.goto(`${url}/${rel}?t=${t}&mode=${mode}`);
        if (!res?.ok()) throw new Error(`HTTP ${res?.status()} for ${rel}`);
        try {
          await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 });
        } catch {
          throw new Error(`page never set window.__ready${errors.length ? `: ${errors.join(" | ")}` : ""}`);
        }
        if (errors.length) throw new Error(`page errors: ${errors.join(" | ")}`);
        const tag = `${mode}-t${t}`;
        if (o.shots === "all" || o.shots === "full") {
          const f = join(o.out, `${tag}-full.png`);
          await page.screenshot({ path: f, fullPage: true });
          written.push(f);
        }
        if (o.shots !== "full") {
          const want = o.shots === "all" ? null : o.shots.split(",");
          for (const el of await page.$$("[data-shot]")) {
            const name = await el.getAttribute("data-shot");
            if (want && !want.includes(name)) continue;
            const f = join(o.out, `${tag}-${name}.png`);
            await el.screenshot({ path: f });
            written.push(f);
          }
        }
        await page.close();
      }
  } finally {
    await browser.close();
    server.close();
  }
  return written;
}

const isMain = (() => {
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
})();
if (isMain) {
  try {
    const files = await render(parseArgs(process.argv.slice(2)));
    for (const f of files) console.log(f);
  } catch (e) {
    console.error(`render: ${e.message}`);
    process.exit(2);
  }
}
