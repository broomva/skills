#!/usr/bin/env node
// Install the Liquid Midnight assets into a target project, verify an install, or list what would be copied.
//   node materialize.mjs install <target> [--dir liquid-midnight] [--with specimen,shaders,templates] [--without …] [--dry-run] [--force]
//   (optional sets installed earlier are kept on update; --without removes one; its files stay on disk, untracked)
//   node materialize.mjs verify  <target> [--dir liquid-midnight]
//   node materialize.mjs list
// Core (always): tokens, css, kit, fonts. Optional: specimen, shaders (Pencil fills), templates (starter scene).
// Writes <target>/<dir>/LIQUID_MIDNIGHT.json (source commit + sha256 per file) so `verify` can detect edits or drift.
// templates/ are STARTERS: copied once and meant to be edited in place. They are not hash-tracked, `verify` ignores
// them, and `install` keeps an existing starter unless --force.
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
export const STARTERS = ["templates/"];
const isStarter = (f) => STARTERS.some((p) => f.startsWith(p));
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
export function install(target, { dir = "liquid-midnight", withList, without = [], dryRun = false, force = false } = {}) {
  const badWithout = without.filter((w) => !(w in OPTIONAL));
  if (badWithout.length) throw new Error(`unknown --without value(s): ${badWithout.join(", ")}; choose from ${Object.keys(OPTIONAL).join(", ")}`);
  const m = manifest();
  const dest = resolve(target, dir);
  const prev = existsSync(join(dest, RECEIPT)) ? readManifest(join(dest, RECEIPT)) : null;
  // an update keeps the optional sets installed earlier: --with adds to them, it never silently drops them
  // (entries a newer skill no longer ships are dropped; --without removes a set from the install)
  withList = [...new Set([...(prev?.with ?? []).filter((w) => w in OPTIONAL), ...(withList ?? [])])].filter((w) => !without.includes(w));
  const files = selection(withList);
  const edited = [];
  const kept = [];
  for (const f of files) {
    const p = join(dest, f);
    if (!existsSync(p)) continue;
    if (isStarter(f)) {
      if (!force) kept.push(f);
      continue;
    }
    const known = prev?.files?.[f];
    const now = sha256(p);
    if (now !== m.files[f] && now !== known) edited.push(f);
  }
  if (edited.length && !force) return { ok: false, dest, edited, kept, copied: [] };
  const copied = files.filter((f) => !kept.includes(f));
  if (!dryRun) {
    for (const f of copied) {
      mkdirSync(dirname(join(dest, f)), { recursive: true });
      copyFileSync(join(ASSETS, f), join(dest, f));
    }
    const tracked = files.filter((f) => !isStarter(f));
    const starters = [...new Set([...(prev?.starters ?? []), ...files.filter(isStarter)])];
    const receipt = { name: "liquid-midnight", source: m.source, with: withList, starters, files: Object.fromEntries(tracked.map((f) => [f, m.files[f]])) };
    writeManifest(join(dest, RECEIPT), receipt);
  }
  return { ok: true, dest, edited, kept, copied, dryRun };
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
  const o = { cmd, target, dir: "liquid-midnight", withList: undefined, without: [], dryRun: false, force: false };
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === "--with") {
      const v = rest[++i];
      if (!v || v.startsWith("--")) throw new Error("--with needs a value: specimen,shaders,templates");
      o.withList = v.split(",").filter(Boolean);
    } else if (a === "--without") {
      const v = rest[++i];
      if (!v || v.startsWith("--")) throw new Error("--without needs a value: specimen,shaders,templates");
      o.without = v.split(",").filter(Boolean);
    } else if (a === "--dir") {
      const v = rest[++i];
      if (!v || v.startsWith("--")) throw new Error("--dir needs a value");
      o.dir = v;
    }
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
      for (const f of Object.keys(m.files)) if (!f.startsWith("../")) console.log(`  ${f}${isStarter(f) ? "  (starter: copied once, edit freely)" : ""}`);
    } else if (o.cmd === "install" && o.target) {
      const r = install(o.target, o);
      if (!r.ok) {
        console.error(`refusing: ${r.edited.length} file(s) in ${r.dest} were edited locally (pass --force to overwrite):\n  ${r.edited.join("\n  ")}`);
        process.exit(1);
      }
      console.log(`${r.dryRun ? "would copy" : "copied"} ${r.copied.length} files to ${r.dest}`);
      if (r.kept.length) console.log(`kept existing starter(s): ${r.kept.join(", ")} (pass --force to replace them)`);
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
      console.error("usage: materialize.mjs install <target> [--dir d] [--with specimen,shaders,templates] [--without …] [--dry-run] [--force] | verify <target> [--dir d] | list");
      process.exit(2);
    }
  } catch (e) {
    console.error(e.message);
    process.exit(2);
  }
}
