#!/usr/bin/env node
// Minimal static server for Liquid Midnight pages (ES modules need http). Loopback only; refuses dotfiles, `..` and
// malformed escapes. Works on Node >= 18 and Bun.
//   node serve.mjs <root-dir> [port]      → http://127.0.0.1:<port>/
import { realpathSync } from "node:fs";
import { readFile, realpath, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
/* entry-point check that survives symlinked paths (macOS /var -> /private/var, npm bin links) */
const isMain = (url) => {
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(url));
  } catch {
    return false;
  }
};

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".glsl": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
};

/** Map a URL path to a file under root, or null when it must not be served. */
export function resolveSafe(root, urlPath) {
  let p;
  try {
    p = decodeURIComponent(urlPath.split("?")[0]);
  } catch {
    return null;
  }
  const parts = p.split(/[/\\]+/).filter(Boolean);
  if (parts.some((s) => s === ".." || s.startsWith("."))) return null;
  const full = resolve(root, ...parts);
  if (full !== resolve(root) && !full.startsWith(resolve(root) + sep)) return null;
  return p.endsWith("/") || !parts.length ? join(full, "index.html") : full;
}

export async function startServer(root, port = 0) {
  let r;
  try {
    r = await realpath(root);
    if (!(await stat(r)).isDirectory()) throw new Error();
  } catch {
    throw new Error(`serve: root is not a readable directory: ${root}`);
  }
  const server = createServer(async (req, res) => {
    const file = resolveSafe(root, req.url || "/");
    try {
      if (req.method !== "GET" && req.method !== "HEAD") throw new Error("method");
      const host = (req.headers.host || "").replace(/:\d+$/, "");
      if (host !== "127.0.0.1" && host !== "localhost") throw new Error("host"); // DNS rebinding
      if (!file) throw new Error("refused");
      const st = await stat(file);
      const target = await realpath(st.isDirectory() ? join(file, "index.html") : file);
      if (target !== r && !target.startsWith(r + sep)) throw new Error("symlink escape");
      const body = await readFile(target);
      res.writeHead(200, { "content-type": TYPES[extname(target)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404, { "content-type": "text/plain" });
      res.end("not found");
    }
  });
  return new Promise((ok, bad) => {
    server.once("error", bad); // e.g. EADDRINUSE: reject instead of throwing out of the listener
    server.listen(port, "127.0.0.1", () => {
      server.off("error", bad); // after start, errors must surface, not vanish into a settled promise
      ok({ port: server.address().port, stop: () => server.close(), server });
    });
  });
}

if (isMain(import.meta.url)) {
  const root = resolve(process.argv[2] || ".");
  try {
    const s = await startServer(root, process.argv[3] !== undefined ? Number(process.argv[3]) : 4317); // explicit 0 = ephemeral
    console.log(`serving ${root} at http://127.0.0.1:${s.port}/`);
  } catch (e) {
    console.error(e.message);
    process.exit(2);
  }
}
