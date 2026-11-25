// Installs and grants, persisted as one JSON file in the host's home.
// A grant records the app version it was given for; a different version has no
// grants (grantedFor returns an empty set), which is how an edit revokes them.
// A null version (an app whose folder cannot be hashed) has no grants either.

import { randomBytes } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export class RegistryError extends Error {}

const real = (p) => {
  try {
    return fs.realpathSync(p);
  } catch {
    return path.resolve(p);
  }
};

export class Registry {
  constructor(home) {
    this.file = path.join(home, "registry.json");
    this.data = { apps: {}, grants: {} };
    let text;
    try {
      text = fs.readFileSync(this.file, "utf8");
    } catch (e) {
      if (e.code === "ENOENT") return; // first run
      throw new RegistryError(`Cannot read ${this.file}: ${e.message}`);
    }
    try {
      const parsed = JSON.parse(text);
      this.data = { apps: parsed.apps ?? {}, grants: parsed.grants ?? {} };
    } catch (e) {
      // Never start empty over a corrupt file: that would erase every pinned
      // cdhash on the next save. Keep it aside and refuse to start.
      const aside = `${this.file}.corrupt-${Date.now()}`;
      fs.renameSync(this.file, aside);
      throw new RegistryError(`${this.file} is not valid JSON (${e.message}); moved to ${aside}.`);
    }
  }

  save() {
    fs.mkdirSync(path.dirname(this.file), { recursive: true, mode: 0o700 });
    const tmp = `${this.file}.${process.pid}.${randomBytes(4).toString("hex")}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this.data, null, 2), { mode: 0o600 });
    fs.renameSync(tmp, this.file);
  }

  apps() {
    return Object.values(this.data.apps);
  }

  get(id) {
    return Object.hasOwn(this.data.apps, id) ? this.data.apps[id] : undefined;
  }

  put(record) {
    this.data.apps[record.id] = record;
    this.save();
  }

  update(id, patch) {
    const record = this.get(id);
    if (!record) return;
    this.data.apps[id] = { ...record, ...patch };
    this.save();
  }

  remove(id) {
    delete this.data.apps[id];
    delete this.data.grants[id];
    this.save();
  }

  findByBundle(bundlePath) {
    const wanted = real(bundlePath);
    return this.apps().find((a) => real(a.bundlePath) === wanted);
  }

  /** Another installed app already using this bundle path, if any. */
  bundleOwner(bundlePath, exceptId) {
    const wanted = real(bundlePath);
    return this.apps().find((a) => a.id !== exceptId && real(a.bundlePath) === wanted);
  }

  grantedFor(id, version) {
    const grant = Object.hasOwn(this.data.grants, id) ? this.data.grants[id] : undefined;
    return new Set(version && grant && grant.version === version ? grant.permissions : []);
  }

  grant(id, version, permissions) {
    if (!version) throw new RegistryError("Cannot grant to an app with no valid version.");
    const current = this.grantedFor(id, version);
    for (const p of permissions) current.add(p);
    this.data.grants[id] = { version, permissions: [...current] };
    this.save();
  }

  revoke(id) {
    delete this.data.grants[id];
    this.save();
  }
}
