// Serialize / rehydrate a just-bash InMemoryFs subtree.
//
// Scoped to a prefix on purpose: Bash auto-populates ~180 synthetic entries under
// /bin, /usr/bin, /dev and /proc, and an unscoped getAllPaths() walk captures the
// whole virtual distro instead of the workspace.
//
// InMemoryFs ships no serializer, and its constructor's `initialFiles` accepts only
// files -- so empty directories and symlinks are dropped unless replayed explicitly.
import { InMemoryFs } from "just-bash";

/** @returns {Promise<{version:1,prefix:string,dirs:Array,files:Array,links:Array}>} */
export async function snapshot(fs, prefix = "/work") {
  const dirs = [], files = [], links = [], byIdentity = new Map();
  const paths = fs.getAllPaths()
    .filter((p) => p === prefix || p.startsWith(prefix + "/"))
    .sort();
  for (const p of paths) {
    let st;
    try { st = await fs.lstat(p); } catch { continue; }
    if (st.isSymbolicLink) {
      links.push({ path: p, target: await fs.readlink(p), mode: st.mode });
      continue;
    }
    if (st.isDirectory) {
      dirs.push({ path: p, mode: st.mode, mtime: st.mtime.getTime() });
      continue;
    }
    // Hardlink group: one payload, later paths recorded as links to the first.
    const key = st.identity ?? (st.ino !== undefined ? `ino:${st.ino}` : null);
    if (key && byIdentity.has(key)) {
      files.push({ path: p, hardlinkTo: byIdentity.get(key) });
      continue;
    }
    if (key) byIdentity.set(key, p);
    const buf = Buffer.from(await fs.readFileBuffer(p));
    files.push({ path: p, b64: buf.toString("base64"), mode: st.mode, mtime: st.mtime.getTime() });
  }
  return { version: 1, prefix, dirs, files, links };
}

/** Rebuild an InMemoryFs from a snapshot. Order matters: files, dirs, hardlinks, symlinks. */
export async function restore(snap) {
  const initial = {};
  for (const f of snap.files ?? []) {
    if (f.hardlinkTo) continue;
    initial[f.path] = {
      content: new Uint8Array(Buffer.from(f.b64, "base64")),
      mode: f.mode,
      mtime: new Date(f.mtime),
    };
  }
  const fs = new InMemoryFs(initial);
  for (const d of [...(snap.dirs ?? [])].sort((a, b) => a.path.length - b.path.length)) {
    if (!(await fs.exists(d.path))) await fs.mkdir(d.path, { recursive: true });
    await fs.chmod(d.path, d.mode);
    await fs.utimes(d.path, new Date(d.mtime), new Date(d.mtime));
  }
  for (const f of snap.files ?? []) if (f.hardlinkTo) await fs.link(f.hardlinkTo, f.path);
  // Symlinks last: their targets need not exist yet, and a broken link is legal.
  for (const l of snap.links ?? []) await fs.symlink(l.target, l.path);
  return fs;
}
