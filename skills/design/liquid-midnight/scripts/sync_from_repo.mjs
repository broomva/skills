#!/usr/bin/env node
// Maintainer tool: vendor the Liquid Midnight assets from a checkout of broomva/liquid-midnight (the source of truth)
// into this skill, and rewrite assets/manifest.json with the source commit and a sha256 per file.
//   node scripts/sync_from_repo.mjs /path/to/liquid-midnight
//   node scripts/sync_from_repo.mjs --rehash      (after editing a skill-authored asset such as templates/)
// The skill's tests fail when a vendored file no longer matches the manifest, so edits go to the source repo first.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SKILL = join(dirname(fileURLToPath(import.meta.url)), "..");
const ASSETS = join(SKILL, "assets");

/** source path in the repo -> destination under assets/ (directories are copied whole, minus tests) */
export const MAP = [
  ["tokens/tokens.json", "tokens/tokens.json"],
  ["tokens/tokens.css", "tokens/tokens.css"],
  ["css/materials.css", "css/materials.css"],
  ["kit", "kit"],
  ["fonts", "fonts"],
  ["design/shaders", "shaders"],
  ["specimen/index.html", "specimen/index.html"],
];
const SKIP = (p) => /\.test\.js$/.test(p) || /(^|\/)\./.test(p);

export function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}
export const sha256 = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");
/* On disk, file hashes are a list of {path, sha256}: a `"tokens/x": "<hex>"` map trips secret scanners (gitleaks
   generic-api-key) in this repo and in every project that commits an install receipt. In memory they are a map. */
export const toList = (files) => Object.entries(files).map(([path, h]) => ({ path, sha256: h }));
export const fromList = (list) => (Array.isArray(list) ? Object.fromEntries(list.map((e) => [e.path, e.sha256])) : { ...list }); // also reads the 0.1.0-pre map form
export const writeManifest = (p, m) => writeFileSync(p, `${JSON.stringify({ ...m, files: toList(m.files) }, null, 2)}\n`);
export const readManifest = (p) => {
  const m = JSON.parse(readFileSync(p, "utf8"));
  return { ...m, files: fromList(m.files) };
};

/** manifest of every vendored asset (templates are authored in the skill and hashed too) */
export function buildManifest(source) {
  const files = {};
  for (const p of walk(ASSETS)) {
    const rel = relative(ASSETS, p).split("\\").join("/");
    if (rel === "manifest.json") continue;
    files[rel] = sha256(p);
  }
  return { name: "liquid-midnight", source, files };
}

if (process.argv[1] === fileURLToPath(import.meta.url) && process.argv[2] === "--rehash") {
  // re-pin after editing a skill-authored asset (e.g. templates/): keeps the recorded source commit
  const prev = readManifest(join(ASSETS, "manifest.json"));
  const manifest = buildManifest(prev.source);
  manifest.files["../DESIGN.md"] = sha256(join(SKILL, "DESIGN.md"));
  writeManifest(join(ASSETS, "manifest.json"), manifest);
  console.log(`rehashed ${Object.keys(manifest.files).length} files (source ${prev.source.commit})`);
} else if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const repo = process.argv[2];
  if (!repo || !existsSync(join(repo, "DESIGN.md")) || !existsSync(join(repo, "kit/index.js"))) {
    console.error("usage: node scripts/sync_from_repo.mjs /path/to/liquid-midnight");
    process.exit(2);
  }
  const commit = execFileSync("git", ["-C", repo, "rev-parse", "--short", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", repo, "status", "--porcelain", "--", ...MAP.map(([s]) => s), "DESIGN.md"], { encoding: "utf8" }).trim();
  if (dirty) {
    console.error(`refusing: the source has uncommitted changes in vendored paths:\n${dirty}`);
    process.exit(1);
  }
  for (const [, dst] of MAP) rmSync(join(ASSETS, dst), { recursive: true, force: true });
  for (const [src, dst] of MAP) {
    const from = join(repo, src);
    mkdirSync(dirname(join(ASSETS, dst)), { recursive: true });
    cpSync(from, join(ASSETS, dst), { recursive: true, filter: (p) => !SKIP(relative(repo, p)) });
  }
  // DESIGN.md: vendored at the skill root, with its image links pointed at the source repo (renders are not vendored)
  const design = readFileSync(join(repo, "DESIGN.md"), "utf8").replace(
    /\]\((docs\/renders\/[^)]+)\)/g,
    (_, p) => `](https://raw.githubusercontent.com/broomva/liquid-midnight/${commit}/${p})`,
  );
  writeFileSync(join(SKILL, "DESIGN.md"), design);
  const manifest = buildManifest({ repo: "https://github.com/broomva/liquid-midnight", commit });
  manifest.files["../DESIGN.md"] = sha256(join(SKILL, "DESIGN.md"));
  writeManifest(join(ASSETS, "manifest.json"), manifest);
  console.log(`synced ${Object.keys(manifest.files).length} files from liquid-midnight@${commit}`);
}
