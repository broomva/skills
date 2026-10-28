#!/usr/bin/env node
// Install the Liquid Midnight assets into a target project, verify an install, or list what would be copied.
//   node materialize.mjs install <target> [--dir liquid-midnight] [--with specimen,shaders,templates] [--dry-run] [--force]
//   node materialize.mjs verify  <target> [--dir liquid-midnight]
//   node materialize.mjs list
// Core (always): tokens, css, kit, fonts. Optional: specimen, shaders (Pencil fills), templates (starter scene).
// Writes <target>/<dir>/LIQUID_MIDNIGHT.json (source commit + sha256 per file) so `verify` can detect edits or drift.
// Pure Node (>= 18), no dependencies.
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readManifest, writeManifest } from "./sync_from_repo.mjs";

const SKILL = join(dirname(fileURLToPath(import.meta.url)), "..");
const ASSETS = join(SKILL, "assets");
export const CORE = ["tokens/", "css/", "kit/", "fonts/"];
export const OPTIONAL = { specimen: "specimen/", shaders: "shaders/", templates: "templates/" };
const RECEIPT = "LIQUID_MIDNIGHT.json";

const sha256 = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");
export const manifest = () => readManifest(join(ASSETS, "manifest.json"));

export function selection(withList = []) {
  const unknown = withList.filter((w) => !(w in OPTIONAL));
  if (unknown.length) throw new Error(`unknown --with value(s): ${unknown.join(", ")}; choose from ${Object.keys(OPTIONAL).join(", ")}`);
  const prefixes = [...CORE, ...withList.map((w) => OPTIONAL[w])];
  return Object.keys(manifest().files).filter((f) => prefixes.some((p) => f.startsWith(p)));
}

/** Copy the selection into target/dir; refuses to overwrite locally edited files unless force. Returns a report. */
export function install(target, { dir = "liquid-midnight", withList = [], dryRun = false, force = false } = {}) {
  const m = manifest();
  const files = selection(withList);
  const dest = resolve(target, dir);
  const prev = existsSync(join(dest, RECEIPT)) ? readManifest(join(dest, RECEIPT)) : null;
  const edited = [];
  for (const f of files) {
    const p = join(dest, f);
    if (!existsSync(p)) continue;
    const known = prev?.files?.[f];
    const now = sha256(p);
    if (now !== m.files[f] && now !== known) edited.push(f);
  }
  if (edited.length && !force) return { ok: false, dest, edited, copied: [] };
  if (!dryRun) {
    for (const f of files) {
      mkdirSync(dirname(join(dest, f)), { recursive: true });
      copyFileSync(join(ASSETS, f), join(dest, f));
    }
    const receipt = { name: "liquid-midnight", source: m.source, with: withList, files: Object.fromEntries(files.map((f) => [f, m.files[f]])) };
    writeManifest(join(dest, RECEIPT), receipt);
  }
  return { ok: true, dest, edited, copied: files, dryRun };
}

/** Compare an install against its receipt: missing or modified files are reported. */
export function verify(target, { dir = "liquid-midnight" } = {}) {
  const dest = resolve(target, dir);
  const rp = join(dest, RECEIPT);
  if (!existsSync(rp)) return { ok: false, dest, error: `no ${RECEIPT} in ${dest}; run install first` };
  const r = readManifest(rp);
  const missing = [];
  const modified = [];
  for (const [f, h] of Object.entries(r.files)) {
    const p = join(dest, f);
    if (!existsSync(p)) missing.push(f);
    else if (sha256(p) !== h) modified.push(f);
  }
  const stale = r.source?.commit !== manifest().source?.commit;
  return { ok: !missing.length && !modified.length, dest, missing, modified, stale, installedFrom: r.source?.commit, skillAt: manifest().source?.commit };
}

function parse(argv) {
  const [cmd, target, ...rest] = argv;
  const o = { cmd, target, dir: "liquid-midnight", withList: [], dryRun: false, force: false };
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === "--dir") o.dir = rest[++i];
    else if (a === "--with") o.withList = rest[++i].split(",").filter(Boolean);
    else if (a === "--dry-run") o.dryRun = true;
    else if (a === "--force") o.force = true;
    else throw new Error(`unknown argument ${a}`);
  }
  return o;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const o = parse(process.argv.slice(2));
    if (o.cmd === "list") {
      const m = manifest();
      console.log(`liquid-midnight@${m.source.commit}\ncore: ${CORE.join(" ")}\noptional (--with): ${Object.keys(OPTIONAL).join(", ")}`);
      for (const f of Object.keys(m.files)) console.log(`  ${f}`);
    } else if (o.cmd === "install" && o.target) {
      const r = install(o.target, o);
      if (!r.ok) {
        console.error(`refusing: ${r.edited.length} file(s) in ${r.dest} were edited locally (pass --force to overwrite):\n  ${r.edited.join("\n  ")}`);
        process.exit(1);
      }
      console.log(`${r.dryRun ? "would copy" : "copied"} ${r.copied.length} files to ${r.dest}`);
    } else if (o.cmd === "verify" && o.target) {
      const r = verify(o.target, o);
      if (r.error) {
        console.error(r.error);
        process.exit(1);
      }
      for (const f of r.missing) console.log(`missing   ${f}`);
      for (const f of r.modified) console.log(`modified  ${f}`);
      if (r.stale) console.log(`note: installed from ${r.installedFrom}; the skill now ships ${r.skillAt} (re-run install to update)`);
      console.log(r.ok ? "verify: ok" : "verify: FAILED");
      process.exit(r.ok ? 0 : 1);
    } else {
      console.error("usage: materialize.mjs install <target> [--dir d] [--with specimen,shaders,templates] [--dry-run] [--force] | verify <target> [--dir d] | list");
      process.exit(2);
    }
  } catch (e) {
    console.error(e.message);
    process.exit(2);
  }
}
