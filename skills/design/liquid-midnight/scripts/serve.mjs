#!/usr/bin/env node
// Minimal static server for Liquid Midnight pages (ES modules need http). Loopback only; refuses dotfiles, `..` and
// malformed escapes. Works on Node >= 18 and Bun.
//   node serve.mjs <root-dir> [port]      → http://127.0.0.1:<port>/
import { readFile, realpath, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

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

export function startServer(root, port = 0) {
  const realRoot = realpath(root);
  const server = createServer(async (req, res) => {
    const file = resolveSafe(root, req.url || "/");
    try {
      if (req.method !== "GET" && req.method !== "HEAD") throw new Error("method");
      const host = (req.headers.host || "").replace(/:\d+$/, "");
      if (host !== "127.0.0.1" && host !== "localhost") throw new Error("host"); // DNS rebinding
      if (!file) throw new Error("refused");
      const st = await stat(file);
      const target = await realpath(st.isDirectory() ? join(file, "index.html") : file);
      const r = await realRoot;
      if (target !== r && !target.startsWith(r + sep)) throw new Error("symlink escape");
      const body = await readFile(target);
      res.writeHead(200, { "content-type": TYPES[extname(target)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404, { "content-type": "text/plain" });
      res.end("not found");
    }
  });
  return new Promise((ok) =>
    server.listen(port, "127.0.0.1", () => ok({ port: server.address().port, stop: () => server.close(), server })),
  );
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = resolve(process.argv[2] || ".");
  const s = await startServer(root, Number(process.argv[3]) || 4317);
  console.log(`serving ${root} at http://127.0.0.1:${s.port}/`);
}
