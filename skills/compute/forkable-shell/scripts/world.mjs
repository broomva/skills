// A "world" is one JSON file holding an entire agent workspace: the filesystem
// plus the shell state. Because it is a single value, forking a world is a file
// copy -- measured at ~0.24ms for an 11KB world, versus seconds for a container.
import { randomUUID } from "node:crypto";
import * as nfs from "node:fs";
import { InMemoryFs } from "just-bash";
import { snapshot, restore } from "./fs-snapshot.mjs";
import { PersistentShell } from "./persistent-shell.mjs";

export const DEFAULT_PREFIX = "/work";

export class World {
  constructor(path, { fs, shell, turns = 0, prefix = DEFAULT_PREFIX }) {
    this.path = path; this.fs = fs; this.shell = shell;
    this.turns = turns; this.prefix = prefix;
    // Serializes exec() on this world. An MCP client may issue overlapping tool
    // calls; interleaved commands would corrupt the replayed shell state and
    // race two saves of the same file.
    this._chain = Promise.resolve();
  }

  /** Open an existing world, or create a fresh one at `path`. */
  static async open(path, { files = {}, prefix = DEFAULT_PREFIX } = {}) {
    if (nfs.existsSync(path)) {
      const raw = JSON.parse(nfs.readFileSync(path, "utf8"));
      const fs = await restore(raw.fs);
      const shell = new PersistentShell({ fs, cwd: raw.shell?.cwd ?? prefix });
      shell.loadState(raw.shell ?? { cwd: prefix, env: {}, rc: "" });
      return new World(path, { fs, shell, turns: raw.turns ?? 0, prefix: raw.fs?.prefix ?? prefix });
    }
    const fs = new InMemoryFs();
    await fs.mkdir(prefix, { recursive: true });
    for (const [guestPath, content] of Object.entries(files)) {
      const dir = guestPath.slice(0, guestPath.lastIndexOf("/"));
      if (dir) await fs.mkdir(dir, { recursive: true });
      await fs.writeFile(guestPath, content);
    }
    const world = new World(path, { fs, shell: new PersistentShell({ fs, cwd: prefix }), prefix });
    await world.save();
    return world;
  }

  async save() {
    const payload = JSON.stringify({
      version: 1,
      fs: await snapshot(this.fs, this.prefix),
      shell: this.shell.getState(),
      turns: this.turns,
    });
    // Write-then-rename: a truncating in-place write that is interrupted destroys
    // the only copy of the world and leaves invalid JSON behind.
    // A fresh, exclusively created temp name: a predictable name could be a
    // pre-placed symlink whose target the write would follow and truncate.
    const tmp = `${this.path}.tmp-${process.pid}-${randomUUID()}`;
    try {
      nfs.writeFileSync(tmp, payload, { flag: "wx" });
      nfs.renameSync(tmp, this.path);
    } catch (err) {
      try { nfs.unlinkSync(tmp); } catch { /* never created */ }
      throw err;
    }
  }

  /** Run one command and persist the resulting world. Calls are serialized. */
  exec(command) {
    const run = this._chain.then(async () => {
      const res = await this.shell.exec(command);   // carries stateCaptured
      this.turns += 1;
      await this.save();
      return res;
    });
    this._chain = run.catch(() => {});
    return run;
  }

  /** Fork == copy. The source is never opened, so it cannot be mutated. */
  static fork(srcPath, destPath) {
    if (!nfs.existsSync(srcPath)) throw new Error(`no such world: ${srcPath}`);
    // copyFileSync opens an EXISTING destination for writing, so a dest that is a
    // hardlink or symlink to the trunk shares its inode and the branch then mutates
    // the trunk. Refuse self-aliasing outright, and unlink any other existing dest
    // so the copy always lands on a fresh inode.
    // lstat, not existsSync: existsSync FOLLOWS symlinks and returns false for a
    // DANGLING one, after which copyFileSync would follow it and write to its target.
    let destEntry = null;
    try { destEntry = nfs.lstatSync(destPath); } catch { /* genuinely absent */ }
    if (destEntry) {
      const sameInode = (a, b) => { try { const x = nfs.statSync(a), y = nfs.statSync(b);
        return x.dev === y.dev && x.ino === y.ino; } catch { return false; } };
      if (sameInode(srcPath, destPath)) {
        throw new Error(`refusing to fork onto the same file as the trunk: ${destPath}`);
      }
      nfs.unlinkSync(destPath);       // removes the link itself, never its target
    }
    nfs.copyFileSync(srcPath, destPath);
    return destPath;
  }

  static info(path) {
    const raw = JSON.parse(nfs.readFileSync(path, "utf8"));
    return {
      turns: raw.turns ?? 0,
      bytes: nfs.statSync(path).size,
      cwd: raw.shell?.cwd ?? null,
      files: (raw.fs?.files ?? []).map((f) => ({
        path: f.path,
        bytes: f.hardlinkTo ? 0 : Buffer.from(f.b64 ?? "", "base64").length,
        hardlinkTo: f.hardlinkTo ?? null,
      })),
      dirs: (raw.fs?.dirs ?? []).map((d) => d.path),
      links: (raw.fs?.links ?? []).map((l) => `${l.path} -> ${l.target}`),
    };
  }
}
