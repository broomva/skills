import { realpathSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";

/**
 * Static serving for the hub's own front door, with one job it must not get
 * wrong: nothing outside the configured root is ever readable.
 *
 * The interesting case is not `../`. A URL parser normalises literal `..`
 * segments away before any handler sees them, so `GET /../package.json`
 * arrives as `/package.json` and is simply missing. The case that reaches the
 * filesystem is the ENCODED one -- `%2e%2e%2f` survives URL normalisation
 * untouched and only becomes `../` when the handler decodes it, which is the
 * moment a naive `join(root, pathname)` walks out of the directory.
 *
 * So the order here is: decode first, then resolve, then compare against the
 * root -- and compare again after `realpath`, because a symlink inside the
 * directory is a second way out that string comparison alone cannot see.
 */

export type StaticOutcome =
  | { readonly kind: "file"; readonly response: Response }
  | { readonly kind: "escape"; readonly detail: Record<string, unknown> }
  | { readonly kind: "missing" };

export interface StaticRoot {
  /** The directory served, after `realpath`. Every answer must resolve inside it. */
  readonly real: string;
}

/**
 * Resolved once, at startup, and deliberately not tolerant of a missing
 * directory. A hub that quietly answers 404 for every asset because the
 * landing directory was not shipped looks identical to a hub whose landing
 * page is simply broken, and the difference only becomes clear to whoever is
 * demoing it. Failing here names the cause while a log is still being read.
 */
export function staticRoot(dir: string): StaticRoot {
  const abs = resolve(dir);
  try {
    return { real: realpathSync(abs) };
  } catch (e) {
    throw new Error(
      `the hub cannot serve static files: ${abs} is not a readable directory (${e instanceof Error ? e.message : String(e)})`,
    );
  }
}

function contains(root: string, target: string): boolean {
  return target === root || target.startsWith(root + sep);
}

export function serveStatic(root: StaticRoot, req: Request, pathname: string): StaticOutcome {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    // A percent-sequence that is not valid UTF-8 is not a path we can reason
    // about, and guessing what it meant is how traversal filters get bypassed.
    return { kind: "escape", detail: { pathname, reason: "malformed percent-encoding" } };
  }
  if (decoded.includes("\0") || decoded.includes("\\")) {
    return {
      kind: "escape",
      detail: { pathname, reason: "path contains a null byte or backslash" },
    };
  }

  const rel = decoded.replace(/^\/+/, "");
  let target = rel === "" ? resolve(root.real, "index.html") : resolve(root.real, rel);
  if (!contains(root.real, target)) {
    return {
      kind: "escape",
      detail: { pathname, reason: "path resolves outside the served directory" },
    };
  }

  let st: ReturnType<typeof statSync>;
  try {
    st = statSync(target);
  } catch {
    return { kind: "missing" };
  }
  if (st.isDirectory()) {
    target = resolve(target, "index.html");
    if (!contains(root.real, target)) return { kind: "missing" };
    try {
      st = statSync(target);
    } catch {
      return { kind: "missing" };
    }
  }
  if (!st.isFile()) return { kind: "missing" };

  // Second gate: a symlink inside the directory pointing out of it passes the
  // string comparison above and fails here.
  let real: string;
  try {
    real = realpathSync(target);
  } catch {
    return { kind: "missing" };
  }
  if (!contains(root.real, real)) {
    return {
      kind: "escape",
      detail: { pathname, reason: "path resolves outside the served directory through a symlink" },
    };
  }

  return { kind: "file", response: fileResponse(real, req) };
}

/**
 * Serve the file, honouring a single byte range.
 *
 * Range support is not decoration: several browsers refuse to play a `<video>`
 * or `<audio>` element served from a source that answers a range request with
 * a whole-file 200. Nothing in `hub-static/` needs it today, but a static root
 * that silently breaks media the first time someone drops a file in it is a
 * trap, and the correct behaviour costs these twenty lines.
 */
function fileResponse(path: string, req: Request): Response {
  const file = Bun.file(path);
  const type = file.type;
  const size = file.size;
  const headers: Record<string, string> = {
    "content-type": type,
    "accept-ranges": "bytes",
    "cache-control": type.startsWith("text/html") ? "no-cache" : "public, max-age=3600",
  };

  const range = req.headers.get("range");
  const parsed = range === null ? null : parseRange(range, size);
  if (parsed === "unsatisfiable") {
    return new Response(null, {
      status: 416,
      headers: { ...headers, "content-range": `bytes */${String(size)}` },
    });
  }

  const head = req.method === "HEAD";
  if (parsed !== null) {
    const { start, end } = parsed;
    return new Response(head ? null : file.slice(start, end + 1), {
      status: 206,
      headers: {
        ...headers,
        "content-range": `bytes ${String(start)}-${String(end)}/${String(size)}`,
        "content-length": String(end - start + 1),
      },
    });
  }
  return new Response(head ? null : file, {
    status: 200,
    headers: { ...headers, "content-length": String(size) },
  });
}

function parseRange(
  header: string,
  size: number,
): { start: number; end: number } | "unsatisfiable" | null {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (m === null) return null;
  const rawStart = m[1] ?? "";
  const rawEnd = m[2] ?? "";
  if (rawStart === "" && rawEnd === "") return null;

  let start: number;
  let end: number;
  if (rawStart === "") {
    // suffix range: the last N bytes
    const n = Number.parseInt(rawEnd, 10);
    if (n <= 0) return "unsatisfiable";
    start = Math.max(0, size - n);
    end = size - 1;
  } else {
    start = Number.parseInt(rawStart, 10);
    end = rawEnd === "" ? size - 1 : Number.parseInt(rawEnd, 10);
  }
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  end = Math.min(end, size - 1);
  if (start > end || start >= size) return "unsatisfiable";
  return { start, end };
}
