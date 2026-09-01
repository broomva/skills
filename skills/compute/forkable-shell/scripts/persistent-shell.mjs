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

const ANSI_C = { n: "\n", t: "\t", r: "\r", "\\": "\\", "'": "'", '"': '"', a: "\x07", b: "\b", f: "\f", v: "\v", e: "\x1b", 0: "\0" };
/** Decode bash ANSI-C quoting ($'...') well enough to round-trip exported values. */
function unescapeAnsiC(str) {
  return str.replace(/\\(x[0-9A-Fa-f]{2}|.)/g, (_, c) =>
    c[0] === "x" ? String.fromCharCode(parseInt(c.slice(1), 16)) : (ANSI_C[c] ?? c));
}

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
      // Only replay syntactically valid names. The name is interpolated unquoted,
      // so a crafted key could smuggle commands into the replayed preamble.
      ...Object.entries(this.env)
        .filter(([k]) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(k))
        .map(([k, v]) => `export ${k}=${sq(v)}`),
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
        // bash emits two forms: name="..." and, for values holding control
        // characters, ANSI-C quoting name=$'...'. Parsing only the first silently
        // DROPS every variable containing a newline or tab.
        const dq = line.match(/^declare -x ([A-Za-z_][A-Za-z0-9_]*)="((?:[^"\\]|\\.)*)"$/);
        if (dq) { next[dq[1]] = dq[2].replace(/\\(.)/g, "$1"); continue; }
        const ansi = line.match(/^declare -x ([A-Za-z_][A-Za-z0-9_]*)=\$'((?:[^'\\]|\\.)*)'$/);
        if (ansi) { next[ansi[1]] = unescapeAnsiC(ansi[2]); continue; }
        const bare = line.match(/^declare -x ([A-Za-z_][A-Za-z0-9_]*)$/);
        if (bare) next[bare[1]] = "";
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
