// just-bash resets env, cwd and functions between exec() calls -- only the
// filesystem is shared. This replays state host-side so a multi-turn agent sees
// one continuous shell.
//
// LIMIT: `declare -f` in just-bash returns a STUB with the body elided
// ("f ()\n{\n    # function body\n}"), so functions cannot be recovered from the
// guest. Register them host-side with addRc().
import { Bash } from "just-bash";

const sq = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`;
const STATE = "/tmp/.forkable-shell-state";   // under /tmp so a /work snapshot excludes it
const MARK = "__FS_SPLIT__";

export class PersistentShell {
  constructor(options = {}) {
    this.bash = new Bash(options);
    this.cwd = options.cwd ?? "/work";
    this.env = { ...(options.env ?? {}) };
    this.rc = "";
  }

  /** Text replayed before every command (function definitions, aliases). */
  addRc(text) { this.rc += (this.rc ? "\n" : "") + text; return this; }

  async exec(command) {
    const preamble = [
      `cd ${sq(this.cwd)} 2>/dev/null || true`,
      ...Object.entries(this.env).map(([k, v]) => `export ${k}=${sq(v)}`),
      this.rc,
    ].filter(Boolean).join("\n");

    const script = `${preamble}
{ ${command}
}
__fs_rc=$?
{ pwd; echo ${sq(MARK)}; export -p; } > ${STATE} 2>/dev/null
exit $__fs_rc`;

    const result = await this.bash.exec(script);
    try {
      const raw = await this.bash.readFile(STATE);
      const [pwd, exports] = raw.split(MARK + "\n");
      this.cwd = pwd.trim() || this.cwd;
      const next = {};
      for (const line of (exports ?? "").split("\n")) {
        const m = line.match(/^declare -x ([A-Za-z_][A-Za-z0-9_]*)="((?:[^"\\]|\\.)*)"$/);
        if (m) next[m[1]] = m[2].replace(/\\(.)/g, "$1");
      }
      if (Object.keys(next).length) this.env = next;
    } catch { /* capture failed; retain prior state rather than corrupting it */ }
    return result;
  }

  getState() { return { cwd: this.cwd, env: { ...this.env }, rc: this.rc }; }
  loadState(s) {
    this.cwd = s?.cwd ?? this.cwd;
    this.env = { ...(s?.env ?? {}) };
    this.rc = s?.rc ?? "";
    return this;
  }
}
