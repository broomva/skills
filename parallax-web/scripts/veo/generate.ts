/**
 * Storyboard -> Veo 3.1 -> the clips /scroll-cinema plays.
 *
 * This exists as a committed script rather than as six files somebody once
 * produced by hand, for the same reason `bun run video` exists: footage that
 * only one laptop knows how to regenerate is footage nobody can re-cut after a
 * copy change. Re-run it and the page's ground layer comes back.
 *
 *   bun run scripts/veo/generate.ts            # generate whatever is missing
 *   bun run scripts/veo/generate.ts --only 01  # one scene, by id prefix
 *   bun run scripts/veo/generate.ts --force    # regenerate everything
 *   bun run scripts/veo/generate.ts --encode   # re-encode from raw, no API calls
 *
 * Raw Veo output lands in cinema/assets/veo-raw/ (gitignored by the repository
 * root .gitignore, which covers parallax-web/cinema/assets/) and is re-encoded
 * into public/scroll-cinema/. The raw file is kept so a re-encode never costs
 * another generation -- which is also why it must never live under out/, the
 * Next export directory the build deletes and rewrites.
 */

import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const KEY = process.env.GEMINI_API_KEY;
if (!KEY) {
  console.error("GEMINI_API_KEY is not set. Veo is reached through the Gemini API.");
  process.exit(2);
}

const ROOT = join(import.meta.dir, "..", "..");
const BOARD = join(ROOT, "scroll-cinema", "storyboard.json");
// NOT `out/`. `out/` is the Next static export directory, which the build
// deletes and rewrites wholesale -- raw Veo footage parked there is destroyed by
// the next `bun run build`, silently and after it has been paid for.
//
// Before the move this collision did not exist: ROOT was the old repository root,
// so raw lived at `<repo>/out/veo-raw` while the export went to `web/out/`. ROOT
// is now this package, and the two paths became the same one.
//
// `cinema/assets/` is the regenerable-intermediates directory and is already
// gitignored, which is the property this needs.
const RAW = join(ROOT, "cinema", "assets", "veo-raw");
const OUT = join(ROOT, "public", "scroll-cinema");
const API = "https://generativelanguage.googleapis.com/v1beta";

/** Only the fields this script reads. The rest of the payload is ignored. */
interface StartBody {
  name?: unknown;
  error?: unknown;
}
interface PollBody {
  done?: unknown;
  error?: unknown;
  response?: { error?: unknown } & Record<string, unknown>;
}

interface Scene {
  id: string;
  beat: string;
  prompt: string;
}
interface Board {
  model: string;
  aspectRatio: string;
  resolution: string;
  /**
   * Declared in the storyboard but NOT sent: veo-3.1-fast rejects the field
   * outright ("`generateAudio` isn't supported by this model", HTTP 400). The
   * audio is removed at encode time with -an instead, which is what the page
   * needs anyway since it autoplays muted.
   */
  generateAudio: boolean;
  negativePrompt: string;
  style: string;
  scenes: Scene[];
}

const argv = process.argv.slice(2);
const flag = (name: string) => argv.includes(`--${name}`);
const value = (name: string) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 ? argv[i + 1] : undefined;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function run(cmd: string[]): Promise<void> {
  const p = Bun.spawn(cmd, { stdout: "pipe", stderr: "pipe" });
  const code = await p.exited;
  if (code !== 0) {
    const err = await new Response(p.stderr).text();
    throw new Error(`${cmd[0]} exited ${code}\n${err.slice(-1200)}`);
  }
}

/** Start one generation and return the long-running operation name. */
async function start(board: Board, scene: Scene): Promise<string> {
  const res = await fetch(`${API}/models/${board.model}:predictLongRunning?key=${KEY}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      instances: [{ prompt: `${scene.prompt} ${board.style}` }],
      parameters: {
        aspectRatio: board.aspectRatio,
        resolution: board.resolution,
        negativePrompt: board.negativePrompt,
      },
    }),
  });
  const body = (await res.json()) as StartBody;
  if (!res.ok || body.error) {
    throw new Error(
      `start ${scene.id}: ${res.status} ${JSON.stringify(body.error ?? body).slice(0, 400)}`,
    );
  }
  if (typeof body.name !== "string") {
    throw new Error(
      `start ${scene.id}: no operation name in ${JSON.stringify(body).slice(0, 300)}`,
    );
  }
  return body.name;
}

/** Poll until done, then dig the file URI out of whichever shape came back. */
async function await_(op: string, id: string): Promise<string> {
  const deadline = Date.now() + 12 * 60_000;
  let waited = 0;
  while (Date.now() < deadline) {
    await sleep(10_000);
    waited += 10;
    const res = await fetch(`${API}/${op}?key=${KEY}`);
    const body = (await res.json()) as PollBody;
    if (body.error) throw new Error(`poll ${id}: ${JSON.stringify(body.error).slice(0, 400)}`);
    if (!body.done) {
      if (waited % 60 === 0) console.log(`    ${id}: ${waited}s`);
      continue;
    }
    if (body.response?.error) {
      throw new Error(`generate ${id}: ${JSON.stringify(body.response.error).slice(0, 400)}`);
    }
    // The response shape has moved between previews, so find the uri rather
    // than index a path that a version bump can silently empty.
    const found = findUri(body.response);
    if (!found) {
      throw new Error(
        `generate ${id}: done, but no video uri in ${JSON.stringify(body.response).slice(0, 600)}`,
      );
    }
    console.log(`    ${id}: done in ${waited}s`);
    return found;
  }
  throw new Error(`poll ${id}: still running after 12 minutes`);
}

function findUri(node: unknown): string | null {
  if (typeof node === "string") return node.startsWith("http") ? node : null;
  if (Array.isArray(node)) {
    for (const child of node) {
      const hit = findUri(child);
      if (hit) return hit;
    }
    return null;
  }
  if (node && typeof node === "object") {
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      if ((k === "uri" || k === "videoUri" || k === "fileUri") && typeof v === "string") return v;
      const hit = findUri(v);
      if (hit) return hit;
    }
  }
  return null;
}

async function download(uri: string, to: string): Promise<void> {
  const sep = uri.includes("?") ? "&" : "?";
  const res = await fetch(`${uri}${sep}key=${KEY}`);
  if (!res.ok) throw new Error(`download ${to}: ${res.status}`);
  await writeFile(to, Buffer.from(await res.arrayBuffer()));
}

/**
 * Re-encode for the web. Veo returns a large, audio-bearing master; this page
 * plays six of these behind a diagram, muted, as texture. Two orders of
 * magnitude of bytes buy nothing here, and a public repo pays for them forever.
 */
async function encode(rawPath: string, id: string, index: number, last: boolean): Promise<void> {
  const mp4 = join(OUT, `${id}.mp4`);
  await run([
    "ffmpeg",
    "-y",
    "-loglevel",
    "error",
    "-i",
    rawPath,
    "-an",
    "-vf",
    "scale=1280:-2,format=yuv420p",
    "-c:v",
    "libx264",
    "-preset",
    "slow",
    "-crf",
    "31",
    "-profile:v",
    "high",
    "-movflags",
    "+faststart",
    mp4,
  ]);
  // Posters are clip BOUNDARIES, not clips: the scrubber requires exactly
  // clips.length + 1 of them, one per seam, so the final clip contributes two
  // (its opening frame and its closing one).
  //
  // This ffmpeg build ships without a webp encoder ("Default encoder for
  // format webp (codec webp) is probably disabled"), so frames come out as PNG
  // and cwebp converts. Two steps, but it does not depend on how someone's
  // ffmpeg happened to be compiled.
  await poster(rawPath, id, "first", index);
  if (last) await poster(rawPath, id, "last", index + 1);
}

async function poster(
  rawPath: string,
  id: string,
  which: "first" | "last",
  index: number,
): Promise<void> {
  const frame = join(RAW, `${id}-${which}.png`);
  const out = join(OUT, `p${String(index).padStart(2, "0")}.webp`);
  const seek = which === "first" ? ["-ss", "0.2"] : ["-sseof", "-0.3"];
  await run([
    "ffmpeg",
    "-y",
    "-loglevel",
    "error",
    ...seek,
    "-i",
    rawPath,
    "-vframes",
    "1",
    "-vf",
    "scale=1280:-2",
    frame,
  ]);
  await run(["cwebp", "-quiet", "-q", "72", frame, "-o", out]);
}

const board: Board = JSON.parse(await readFile(BOARD, "utf8"));
await mkdir(RAW, { recursive: true });
await mkdir(OUT, { recursive: true });

const only = value("only");
const scenes = only ? board.scenes.filter((s) => s.id.startsWith(only)) : board.scenes;
if (scenes.length === 0) {
  console.error(`--only ${only} matched no scene`);
  process.exit(2);
}

console.log(
  `veo: ${board.model} · ${board.resolution} ${board.aspectRatio} · ${scenes.length} scene(s)`,
);

for (const scene of scenes) {
  const raw = join(RAW, `${scene.id}.mp4`);
  const done = join(OUT, `${scene.id}.mp4`);

  if (!flag("encode") && !flag("force") && existsSync(done)) {
    console.log(`  ${scene.id}: already built, skipping`);
    continue;
  }

  if (!existsSync(raw) || flag("force")) {
    if (flag("encode")) {
      console.log(`  ${scene.id}: no raw file, and --encode does not generate`);
      continue;
    }
    console.log(`  ${scene.id}: generating — "${scene.beat}"`);
    const op = await start(board, scene);
    const uri = await await_(op, scene.id);
    await download(uri, raw);
  } else {
    console.log(`  ${scene.id}: raw present, re-encoding only`);
  }

  await encode(
    raw,
    scene.id,
    board.scenes.indexOf(scene),
    scene === board.scenes[board.scenes.length - 1],
  );
  const size = Bun.file(join(OUT, `${scene.id}.mp4`)).size;
  console.log(`  ${scene.id}: ${(size / 1e6).toFixed(2)} MB`);
}

const manifest = {
  generatedFrom: "scroll-cinema/storyboard.json",
  model: board.model,
  clips: board.scenes.map((s) => `${s.id}.mp4`),
  // one per seam: clips.length + 1, which is what the scrubber asserts
  posters: board.scenes
    .map((_, i) => `p${String(i).padStart(2, "0")}.webp`)
    .concat(`p${String(board.scenes.length).padStart(2, "0")}.webp`),
  beats: board.scenes.map((s) => ({ id: s.id, beat: s.beat })),
};
await writeFile(join(OUT, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log("manifest written");
