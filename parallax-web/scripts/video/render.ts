/**
 * Render the recorded walkthrough video.
 *
 * `frame.html` draws frame(t) as a pure function of t, so this is a screenshot
 * loop rather than a screen recording: no clock, no dropped frames, and the
 * same bytes every run. One Chrome is held open and driven over CDP, because a
 * process launch per frame costs more than the frame does.
 *
 * Run with: bun run scripts/video/render.ts [--fps 15] [--scale 0.75]
 */
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const HERE = import.meta.dir;
const ROOT = join(HERE, "..", "..");
const CHROME =
  process.env.CHROME_PATH ??
  join(
    process.env.HOME ?? "",
    ".cache/puppeteer/chrome-headless-shell/mac_arm-151.0.7922.71",
    "chrome-headless-shell-mac-arm64/chrome-headless-shell",
  );

const arg = (flag: string, fallback: number): number => {
  const i = process.argv.indexOf(flag);
  if (i === -1) return fallback;
  const v = Number(process.argv[i + 1]);
  return Number.isFinite(v) && v > 0 ? v : fallback;
};
const FPS = arg("--fps", 15);
const SCALE = arg("--scale", 0.75); // 1920x1080 -> 1440x810, plenty at full screen
const WIDTH = 1920;
const HEIGHT = 1080;

if (!existsSync(CHROME)) {
  console.error(`no chrome-headless-shell at ${CHROME}\nset CHROME_PATH to override`);
  process.exit(1);
}

// ---------------------------------------------------------------- page source
const content = readFileSync(join(HERE, "content.json"), "utf8");
const html = readFileSync(join(HERE, "frame.html"), "utf8");
if (!html.includes("__CONTENT__")) {
  console.error("frame.html no longer has a __CONTENT__ placeholder");
  process.exit(1);
}
const WORK = join(ROOT, "out", ".video");
rmSync(WORK, { recursive: true, force: true });
mkdirSync(WORK, { recursive: true });
const pagePath = join(WORK, "page.html");
writeFileSync(pagePath, html.replace("__CONTENT__", content));

const END = Number(/end:\s*(\d+)/.exec(html)?.[1] ?? 41000);
const frames = Math.ceil((END / 1000) * FPS);

// ---------------------------------------------------------------- chrome + cdp
const chrome = Bun.spawn(
  [
    CHROME,
    "--headless",
    "--remote-debugging-port=0",
    "--hide-scrollbars",
    "--disable-gpu",
    "--no-sandbox",
    `--window-size=${WIDTH},${HEIGHT}`,
    "about:blank",
  ],
  // A bare spawn inherits a startup snapshot of the environment; pass it
  // explicitly so CHROME_PATH/HOME are the ones this process actually has.
  { env: process.env, stdout: "pipe", stderr: "pipe" },
);

async function browserEndpoint(): Promise<string> {
  const reader = (chrome.stderr as ReadableStream<Uint8Array>).getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const m = /ws:\/\/([^\s/]+)\//.exec(buf);
    if (m?.[1] !== undefined) return m[1];
  }
  throw new Error(`chrome did not report a debugger URL:\n${buf.slice(0, 400)}`);
}

/**
 * The URL chrome prints on stderr is the BROWSER endpoint, where Page.* and
 * Runtime.* do not exist -- calls against it resolve empty and the page never
 * navigates. The page target has to be looked up and connected to separately.
 */
async function pageEndpoint(hostPort: string): Promise<string> {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://${hostPort}/json/list`);
      const targets = (await res.json()) as Array<{ type: string; webSocketDebuggerUrl?: string }>;
      const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page?.webSocketDebuggerUrl !== undefined) return page.webSocketDebuggerUrl;
    } catch {
      // chrome is still coming up
    }
    await Bun.sleep(200);
  }
  throw new Error(`no page target on ${hostPort}`);
}

const ws = new WebSocket(await pageEndpoint(await browserEndpoint()));
await new Promise<void>((res, rej) => {
  ws.onopen = () => res();
  ws.onerror = () => rej(new Error("CDP socket failed"));
});

let nextId = 1;
const pending = new Map<number, (v: Record<string, unknown>) => void>();
ws.onmessage = (ev) => {
  const msg = JSON.parse(String(ev.data)) as { id?: number; result?: Record<string, unknown> };
  if (msg.id !== undefined && pending.has(msg.id)) {
    pending.get(msg.id)?.(msg.result ?? {});
    pending.delete(msg.id);
  }
};
const cdp = (method: string, params: Record<string, unknown> = {}) =>
  new Promise<Record<string, unknown>>((resolve) => {
    const id = nextId++;
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
  });

await cdp("Page.enable");
await cdp("Emulation.setDeviceMetricsOverride", {
  width: WIDTH,
  height: HEIGHT,
  deviceScaleFactor: 1,
  mobile: false,
});
await cdp("Page.navigate", { url: `file://${pagePath}` });
// The page is one file with no network of its own; a short settle is enough.
await Bun.sleep(1200);

const probe = await cdp("Runtime.evaluate", { expression: "typeof render", returnByValue: true });
if ((probe.result as { value?: unknown })?.value !== "function") {
  console.error("render() is not defined on the page -- frame.html failed to parse");
  process.exit(1);
}

// ---------------------------------------------------------------- frames
const pad = (n: number) => String(n).padStart(5, "0");
const started = Date.now();
for (let i = 0; i < frames; i++) {
  const t = Math.round((i / FPS) * 1000);
  await cdp("Runtime.evaluate", { expression: `render(${t})`, returnByValue: true });
  const shot = await cdp("Page.captureScreenshot", { format: "png" });
  const data = (shot as { data?: string }).data;
  if (typeof data !== "string") throw new Error(`no screenshot data at frame ${i}`);
  writeFileSync(join(WORK, `f${pad(i)}.png`), Buffer.from(data, "base64"));
  if (i % 60 === 0 || i === frames - 1) {
    const pct = Math.round(((i + 1) / frames) * 100);
    process.stdout.write(`\r  frames ${i + 1}/${frames} (${pct}%)   `);
  }
}
process.stdout.write(`\r  frames ${frames}/${frames} (100%)   \n`);
console.log(`  captured in ${((Date.now() - started) / 1000).toFixed(1)}s`);

ws.close();
chrome.kill();

// ---------------------------------------------------------------- encode
// docs/, not out/: out/ is gitignored (see parallax-web/.gitignore), so a video
// written there exists on exactly one laptop. This one is committed instead.
const outPath = join(ROOT, "docs", "walkthrough.mp4");
const w = Math.round((WIDTH * SCALE) / 2) * 2;
const h = Math.round((HEIGHT * SCALE) / 2) * 2;
const ff = Bun.spawnSync(
  [
    "ffmpeg",
    "-y",
    "-framerate",
    String(FPS),
    "-i",
    join(WORK, "f%05d.png"),
    "-vf",
    `scale=${w}:${h}`,
    "-c:v",
    "libx264",
    "-preset",
    "slow",
    "-crf",
    "20",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    outPath,
  ],
  { env: process.env, stdout: "pipe", stderr: "pipe" },
);
if (ff.exitCode !== 0) {
  console.error(new TextDecoder().decode(ff.stderr).split("\n").slice(-15).join("\n"));
  process.exit(1);
}
rmSync(WORK, { recursive: true, force: true });
const size = Bun.file(outPath).size;
console.log(`\n  ${outPath}`);
console.log(
  `  ${(size / 1_048_576).toFixed(1)} MB · ${w}x${h} · ${FPS} fps · ${(END / 1000).toFixed(0)}s`,
);
