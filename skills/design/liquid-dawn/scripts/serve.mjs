#!/usr/bin/env node
// A tiny static server for previewing and rendering (ES modules do not load over file://).
//   node scripts/serve.mjs [root=assets] [port=4318]      → http://127.0.0.1:4318/specimen/
// Loopback only, GET/HEAD only, no dotfiles, and every path must resolve inside root (symlinks included).
import { createReadStream, realpathSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".mp4": "video/mp4",
  ".svg": "image/svg+xml",
};

/** Resolve a URL path to a file inside root, or null. Pure apart from the filesystem lookups. */
export function resolveInside(root, urlPath) {
  let p;
  try {
    p = decodeURIComponent(urlPath.split("?")[0]);
  } catch {
    return null;
  }
  if (p.split("/").some((s) => s.startsWith("."))) return null;
  const base = realpathSync(root);
  let f = resolve(base, `.${p}`);
  try {
    if (statSync(f).isDirectory()) f = join(f, "index.html");
    f = realpathSync(f);
  } catch {
    return null;
  }
  return f === base || f.startsWith(base + sep) ? f : null;
}

export function startServer(root, port = 0) {
  const rootDir = resolve(root);
  if (!statSync(rootDir, { throwIfNoEntry: false })?.isDirectory()) throw new Error(`serve: not a directory: ${root}`);
  const server = createServer((req, res) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405).end();
      return;
    }
    const f = resolveInside(rootDir, req.url || "/");
    if (!f) {
      res.writeHead(404).end("not found");
      return;
    }
    let size;
    try { size = statSync(f).size; } catch { res.writeHead(500).end("read error"); return; }
    const headers = { "content-type": TYPES[extname(f)] || "application/octet-stream", "cache-control": "no-store", "accept-ranges": "bytes", "content-length": size };
    let status = 200, start = 0, end = size - 1;
    // Single byte ranges let media decoders seek without downloading the complete file again.
    if (req.method === "GET" && req.headers.range) {
      const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
      let valid = !!m && !!(m[1] || m[2]) && size > 0;
      if (valid) {
        if (!m[1]) {
          const suffix = Number(m[2]);
          valid = Number.isSafeInteger(suffix) && suffix > 0;
          start = Math.max(0, size - suffix);
        } else {
          start = Number(m[1]);
          end = m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
          valid = Number.isSafeInteger(start) && Number.isSafeInteger(end) && start < size && end >= start;
        }
      }
      if (!valid) { res.writeHead(416, { "content-range": `bytes */${size}`, "content-length": 0 }).end(); return; }
      status = 206;
      headers["content-range"] = `bytes ${start}-${end}/${size}`;
      headers["content-length"] = end - start + 1;
    }
    if (req.method === "HEAD") { res.writeHead(200, headers).end(); return; }
    // Open first, answer second: a missing file must not kill the preview server.
    const s = createReadStream(f, status === 206 ? { start, end } : undefined);
    s.once("open", () => {
      res.writeHead(status, headers);
      s.pipe(res);
    });
    s.once("error", () => {
      if (!res.headersSent) res.writeHead(500).end("read error");
      else res.destroy();
    });
  });
  return new Promise((ok) => server.listen(port, "127.0.0.1", () => ok({ server, url: `http://127.0.0.1:${server.address().port}` })));
}

if (realpathSync(process.argv[1] ?? ".") === realpathSync(fileURLToPath(import.meta.url))) {
  const here = fileURLToPath(new URL("..", import.meta.url));
  const root = process.argv[2] ?? join(here, "assets");
  try {
    const { url } = await startServer(root, Number(process.argv[3] ?? 4318));
    console.log(`${url}/specimen/   (?mode=dusk, ?t=6 for a deterministic frame)`);
  } catch (e) {
    console.error(e.message);
    process.exit(2);
  }
}
