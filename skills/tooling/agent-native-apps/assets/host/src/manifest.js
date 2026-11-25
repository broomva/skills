// An app is a folder: app.json + index.html + whatever it loads.
//
// Its version is a content hash of exactly the files the host will SERVE. The
// hashed set and the served set come from one predicate (`isServedSegment`), so
// no byte can run that the version does not cover. Any edit, including one made
// by the app's own agent, is a new version.

import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { PERMISSIONS } from "./capabilities.js";

export const HARNESS_NAMES = ["claude", "codex", "t3"];
const MAX_FILES = 2000;
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const MAX_TOTAL_BYTES = 200 * 1024 * 1024;
const MODEL_RE = /^[A-Za-z0-9][\w.:/-]{0,80}$/;
const PROVIDER_RE = /^[A-Za-z0-9][\w.-]{0,80}$/;

export class ManifestError extends Error {}

/**
 * A path segment the host serves and hashes. Dot-entries (.git, .claude,
 * .DS_Store, ...) and node_modules are neither served nor hashed. Pure.
 */
export function isServedSegment(name) {
  return name.length > 0 && !name.startsWith(".") && name !== "node_modules";
}

export const validModel = (m) => typeof m === "string" && MODEL_RE.test(m);
export const validProvider = (p) => typeof p === "string" && PROVIDER_RE.test(p);

/** Validate a parsed app.json. Pure. */
export function validateManifest(raw) {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new ManifestError("app.json must be a JSON object.");
  }
  const { name, permissions = [], icon, agent = {} } = raw;
  if (typeof name !== "string" || !/^[\p{L}\p{N} ._-]{1,40}$/u.test(name) || name.startsWith(".")) {
    throw new ManifestError("app.json name: 1-40 letters, digits, spaces, '.', '_' or '-'.");
  }
  if (!Array.isArray(permissions) || permissions.some((p) => !Object.hasOwn(PERMISSIONS, p))) {
    throw new ManifestError(
      `app.json permissions must be a list drawn from: ${Object.keys(PERMISSIONS).join(", ")}.`,
    );
  }
  if (icon !== undefined && (typeof icon !== "string" || icon.length > 4)) {
    throw new ManifestError("app.json icon: up to 4 characters (an emoji or initials).");
  }
  if (typeof agent !== "object" || agent === null || Array.isArray(agent)) {
    throw new ManifestError("app.json agent must be an object.");
  }
  const harness = agent.harness ?? "claude";
  if (!HARNESS_NAMES.includes(harness)) {
    throw new ManifestError(`app.json agent.harness: one of ${HARNESS_NAMES.join(", ")}.`);
  }
  // The page may pick another harness only from this list (default: just `harness`).
  const harnesses = agent.harnesses ?? [harness];
  if (!Array.isArray(harnesses) || harnesses.some((h) => !HARNESS_NAMES.includes(h))) {
    throw new ManifestError(`app.json agent.harnesses: a list drawn from ${HARNESS_NAMES.join(", ")}.`);
  }
  if (agent.model !== undefined && !validModel(agent.model)) {
    throw new ManifestError("app.json agent.model: a model id (letters, digits, . _ : / -).");
  }
  if (agent.provider !== undefined && !validProvider(agent.provider)) {
    throw new ManifestError("app.json agent.provider: a T3 provider instance id.");
  }
  if (harness === "t3" && agent.provider !== undefined && agent.model === undefined) {
    throw new ManifestError("app.json agent: a t3 provider needs a model too.");
  }
  return {
    name,
    permissions: [...new Set(permissions)],
    icon: icon ?? name.slice(0, 1).toUpperCase(),
    agent: {
      harness,
      harnesses: [...new Set([harness, ...harnesses])],
      model: agent.model,
      provider: agent.provider,
    },
  };
}

export function readManifest(appDir) {
  const file = path.join(appDir, "app.json");
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (e) {
    throw new ManifestError(`Cannot read ${file}: ${e.message}`);
  }
  if (!fs.existsSync(path.join(appDir, "index.html"))) {
    throw new ManifestError(`${appDir} has no index.html.`);
  }
  return validateManifest(raw);
}

/** Every served file in appDir (absolute paths, sorted). Refuses symlinks and limits. */
export function servedFiles(appDir) {
  const files = [];
  let total = 0;
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!isServedSegment(entry.name)) continue;
      const full = path.join(dir, entry.name);
      // A symlink could point outside the folder, and its target would not be
      // in the hash: an app folder holds real files only.
      if (entry.isSymbolicLink())
        throw new ManifestError(`${full} is a symlink; apps may not contain symlinks.`);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!entry.isFile()) continue;
      const size = fs.statSync(full).size;
      total += size;
      if (size > MAX_FILE_BYTES) throw new ManifestError(`${full} is over ${MAX_FILE_BYTES} bytes.`);
      if (total > MAX_TOTAL_BYTES) throw new ManifestError(`${appDir} is over ${MAX_TOTAL_BYTES} bytes.`);
      files.push(full);
      if (files.length > MAX_FILES) throw new ManifestError(`${appDir} has over ${MAX_FILES} files.`);
    }
  };
  walk(appDir);
  return files.sort();
}

function frame(hash, buffer) {
  const length = Buffer.alloc(8);
  length.writeBigUInt64BE(BigInt(buffer.length));
  hash.update(length);
  hash.update(buffer);
}

/**
 * sha256 over (length-prefixed POSIX relative path, sha256 of the file's bytes)
 * per served file, in sorted order; 32 hex chars (128 bits). Length prefixes
 * make the encoding unambiguous, so no two trees share a byte stream.
 */
export function versionOf(appDir) {
  const tree = createHash("sha256");
  for (const file of servedFiles(appDir)) {
    frame(tree, Buffer.from(path.relative(appDir, file).split(path.sep).join("/")));
    frame(tree, createHash("sha256").update(fs.readFileSync(file)).digest());
  }
  return tree.digest("hex").slice(0, 32);
}

const inside = (root, target) => target === root || target.startsWith(root + path.sep);

/** Resolve a request path inside appDir, or null if it escapes or is not served. Pure. */
export function resolveInside(appDir, requestPath) {
  let decoded;
  try {
    decoded = decodeURIComponent(requestPath).replace(/^\/+/, "");
  } catch {
    return null; // malformed %-escape
  }
  const relative = decoded || "index.html";
  if (relative.split(/[\\/]+/).some((s) => s !== "" && s !== ".." && !isServedSegment(s))) return null;
  const target = path.resolve(appDir, relative);
  return inside(path.resolve(appDir), target) ? target : null;
}

/**
 * The file to serve for a request: a served path inside appDir by path AND by
 * real path (no symlink, in the file or any parent, may lead out), and a
 * regular file. Returns null otherwise.
 */
export function servableFile(appDir, requestPath) {
  const target = resolveInside(appDir, requestPath);
  if (!target) return null;
  try {
    const real = fs.realpathSync(target);
    if (!inside(fs.realpathSync(appDir), real) || !fs.statSync(real).isFile()) return null;
    return real;
  } catch {
    return null;
  }
}
