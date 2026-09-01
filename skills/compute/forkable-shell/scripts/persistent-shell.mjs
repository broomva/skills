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
  // Order matters: octal (\nnn, \0nnn) and hex (\xHH) must be matched before the
  // single-character table, or $'a\001b' decodes as NUL followed by the text "01".
  return str.replace(/\\(x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|.)/g, (_, c) => {
    if (c[0] === "x") return String.fromCharCode(parseInt(c.slice(1), 16));
    if (/^[0-7]+$/.test(c)) return String.fromCharCode(parseInt(c, 8) & 0xff);
    return ANSI_C[c] ?? c;
  });
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

    // A per-call token proves the epilogue actually ran. just-bash implements no
    // `trap`, so `exit N` or a `set -e` failure abandons the script before capture.
    // Without the token a stale state file would be read back as if it were fresh.
    const token = `T${Date.now()}${Math.random().toString(36).slice(2, 10)}`;
    // The delimiter carries the per-call token, so a cwd or value containing the
    // literal marker cannot split the payload. `builtin pwd` bypasses a
    // command-local `pwd()` override.
    const mark = `${MARK}${token}`;
    const script = `${preamble}
{ ${command}
}
__fs_rc=$?
{ echo ${sq(token)}; builtin pwd; echo ${sq(mark)}; export -p; } > ${STATE} 2>/dev/null
exit $__fs_rc`;

    const result = await this.bash.exec(script);
    this.stateCaptured = false;
    try {
      const raw = await this.bash.readFile(STATE);
      const nl = raw.indexOf("\n");
      if (raw.slice(0, nl) !== token) throw new Error("epilogue did not run");
      const parts = raw.slice(nl + 1).split(mark + "\n");
      if (parts.length !== 2) throw new Error("state payload is not well formed");
      const [pwd, exports] = parts;
      // Structural validation BEFORE claiming capture succeeded: entering the
      // epilogue is not the same as recovering usable state.
      const cwd = pwd.replace(/\n$/, "");
      if (!cwd.startsWith("/")) throw new Error(`implausible cwd: ${JSON.stringify(cwd)}`);
      this.cwd = cwd;
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
      this.stateCaptured = true;   // only now is the state actually recovered
    } catch { /* capture skipped/invalid; retain prior state rather than corrupting it */ }
    // Surfaced so a caller can tell "state is unchanged because nothing changed it"
    // from "state is unchanged because the command exited before we could look".
    return Object.assign(result, { stateCaptured: this.stateCaptured });
  }

  getState() { return { cwd: this.cwd, env: { ...this.env }, rc: this.rc }; }
  loadState(s) {
    this.cwd = s?.cwd ?? this.cwd;
    this.env = { ...(s?.env ?? {}) };
    this.rc = s?.rc ?? "";
    return this;
  }
}
