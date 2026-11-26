// Agent harnesses wired into an app. Each adapter turns {prompt, edit, model, ...}
// into a CLI invocation scoped to the app's folder, and turns the CLI's output
// into one event shape the page sees:
//   {type:"text", text} | {type:"tool", name, input} | {type:"thread", threadId, link?}
//   | {type:"done", ok, summary} | {type:"error", message}
//
// claude and codex stream JSONL; t3 prints one JSON result when the turn ends.
// The prompt always goes to the CLI on stdin, never argv, so no prompt can be
// read as a flag. The child gets an allowlisted environment, not the host's.
// Scope: cwd is the app's own folder.
//   claude/codex: read-only runs get read tools only; edit runs may change files.
//   t3: the app folder is a T3 project and the agent is a T3 thread. T3 threads
//       run with their project's runtime mode (full access by default) and the
//       CLI has no read-only switch, so a t3 run is gated as an edit run.
//       `t3 thread` has no CLI interrupt subcommand, so cancelling a t3 run stops
//       the local waiting CLI client; stop any still-running turn in T3 Code.

import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const HARNESSES = {
  claude: {
    bin: "claude",
    defaultModel: "sonnet",
    alwaysEdits: false,
    args({ edit, model }) {
      return [
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--tools",
        edit ? "Read,Glob,Grep,Edit,Write" : "Read,Glob,Grep",
        "--permission-mode",
        edit ? "acceptEdits" : "default",
        // No settings from anywhere: not the user's (hooks, MCP servers) and not
        // the app folder's, which the app or its agent can write. No MCP servers.
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--no-session-persistence",
      ];
    },
    parse(obj) {
      if (obj.type === "assistant") {
        return (obj.message?.content ?? []).flatMap((c) =>
          c.type === "text"
            ? [{ type: "text", text: c.text }]
            : c.type === "tool_use"
              ? [{ type: "tool", name: c.name, input: c.input }]
              : [],
        );
      }
      if (obj.type === "result") {
        return [
          {
            type: "done",
            ok: obj.subtype === "success" && !obj.is_error,
            summary: typeof obj.result === "string" ? obj.result : "",
          },
        ];
      }
      return [];
    },
  },
  codex: {
    bin: "codex",
    defaultModel: undefined, // the user's Codex default; pass `model` to pin one
    alwaysEdits: false,
    args({ edit, model, cwd }) {
      return [
        "exec",
        "--json",
        "--skip-git-repo-check",
        "-C",
        cwd,
        ...(model ? ["-m", model] : []),
        "-s",
        edit ? "workspace-write" : "read-only",
        "-", // read the prompt from stdin
      ];
    },
    parse(obj) {
      if (obj.type === "item.completed" && obj.item?.type === "agent_message") {
        return [{ type: "text", text: obj.item.text }];
      }
      if (obj.type === "item.completed" && obj.item?.type === "command_execution") {
        return [{ type: "tool", name: "shell", input: obj.item.command }];
      }
      if (obj.type === "item.completed" && obj.item?.type === "file_change") {
        return [{ type: "tool", name: "edit", input: obj.item.changes }];
      }
      // Codex reports config warnings as `error` items and keeps going; they are
      // not the run's outcome. turn.completed / turn.failed are.
      // A top-level `error` (a dropped stream, a retry) is reported but does not
      // end the run: the process exit and turn.* events do.
      if (obj.type === "error") return [{ type: "error", message: String(obj.message ?? "codex error") }];
      if (obj.type === "turn.completed") return [{ type: "done", ok: true, summary: "" }];
      if (obj.type === "turn.failed") {
        return [{ type: "done", ok: false, summary: obj.error?.message ?? "turn failed" }];
      }
      return [];
    },
  },
  t3: {
    bin: "t3",
    defaultModel: undefined, // the T3 project's default model
    alwaysEdits: true,
    wholeOutput: true,
    // `t3 thread start` takes --provider and --model only together.
    args({ model, provider, cwd, threadId, title }) {
      if (threadId) return ["thread", "send", threadId, "-", "--wait", "--json"];
      return [
        "thread",
        "start",
        cwd,
        "-", // read the message from stdin
        "--title",
        title ?? "agent-native app",
        ...(provider && model ? ["--provider", provider, "--model", model] : []),
        "--wait",
        "--json",
      ];
    },
    parse(obj) {
      if (typeof obj.threadId !== "string" || typeof obj.status !== "string") return [];
      return [
        { type: "thread", threadId: obj.threadId },
        ...(obj.reply ? [{ type: "text", text: String(obj.reply) }] : []),
        {
          type: "done",
          ok: obj.status === "completed" && !obj.error,
          summary: obj.error
            ? String(obj.error?.message ?? obj.error)
            : obj.status === "completed"
              ? ""
              : obj.status,
        },
      ];
    },
    // t3 thread --wait: exit 1 = the run failed, exit 2 = it waits for an answer.
    exitSummary(code) {
      if (code === 2) return "The T3 thread is waiting for an answer; open it in T3 to reply.";
      return null;
    },
    cancelSummary(signal) {
      return `stopped local t3 waiter (${signal}); the T3 CLI cannot interrupt a running server turn, so stop it in T3 Code if still active.`;
    },
  },
};

/** Split a byte stream into JSON objects, one per line; skips non-JSON. */
export function lineParser(onObject) {
  let buffer = "";
  return (chunk) => {
    buffer += chunk;
    let index = buffer.indexOf("\n");
    while (index !== -1) {
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (line.startsWith("{")) {
        try {
          onObject(JSON.parse(line));
        } catch {
          // A partial or non-JSON line (CLI log output): not an event.
        }
      }
      index = buffer.indexOf("\n");
    }
  };
}

/** The last JSON object in a whole CLI output (t3 may pretty-print it). Pure. */
export function lastJsonObject(text) {
  const end = text.lastIndexOf("}");
  if (end === -1) return null;
  let start = text.lastIndexOf("{", end);
  while (start !== -1) {
    try {
      return JSON.parse(text.slice(start, end + 1));
    } catch {
      // not yet the outermost brace; keep widening
    }
    if (start === 0) break;
    start = text.lastIndexOf("{", start - 1);
  }
  return null;
}

// --------------------------------------------------------------- finding the CLIs

const MARK = "__AGENT_NATIVE_APPS_PATH__";

/** Extract PATH from a login shell's output, which may include rc-file noise. Pure. */
export function parseLoginPath(output) {
  const m = new RegExp(`${MARK}(.*?)${MARK}`, "s").exec(output);
  return m ? m[1].trim() : null;
}

/**
 * A host the shim launches through LaunchServices gets PATH=/usr/bin:/bin:...,
 * which holds none of claude, codex or t3. Ask the user's login shell once.
 */
export function resolveUserPath(env = process.env) {
  const shell = env.SHELL || "/bin/zsh";
  let login = null;
  try {
    const out = execFileSync(shell, ["-l", "-c", `printf '${MARK}%s${MARK}' "$PATH"`], {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["ignore", "pipe", "ignore"],
    });
    login = parseLoginPath(out);
  } catch {
    // fall through to the known install locations
  }
  const extra = [
    path.join(os.homedir(), ".local", "bin"),
    path.join(os.homedir(), ".t3", "bin"),
    path.join(os.homedir(), ".bun", "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
  ];
  const parts = [...(login ? login.split(":") : []), ...(env.PATH ?? "").split(":"), ...extra];
  return [...new Set(parts.filter(Boolean))].join(":");
}

/** Absolute path of `bin` on `searchPath`, or null. */
export function which(bin, searchPath = process.env.PATH ?? "") {
  for (const dir of searchPath.split(":")) {
    const candidate = path.join(dir, bin);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {
      // keep looking
    }
  }
  return null;
}

// --------------------------------------------------------------- running a harness

// What a harness child may see of the host's environment. Credentials live in
// the CLIs' own stores under HOME (Claude's keychain item, ~/.codex, T3's
// server), so tokens the host happens to carry in its env are not passed on.
const ENV_ALLOW = [
  "HOME",
  "USER",
  "LOGNAME",
  "SHELL",
  "PATH",
  "LANG",
  "LC_ALL",
  "LC_CTYPE",
  "TMPDIR",
  "CLAUDE_CONFIG_DIR",
  "CODEX_HOME",
  "T3CODE_HOME",
];

/** The allowlisted environment for a harness child. Pure. */
export function harnessEnv(env = process.env) {
  const out = { TERM: "dumb", NO_COLOR: "1" };
  for (const key of ENV_ALLOW) if (typeof env[key] === "string") out[key] = env[key];
  return out;
}

const KILL_GRACE_MS = 3000;

/**
 * Run a harness. Returns {cancel, finished}; events stream through onEvent.
 * Exactly one `done` event is emitted, and only once the child has exited:
 * a CLI's own "result"/"turn.completed" is held until the process is gone, so
 * the caller never treats a still-running child as finished.
 */
export function runHarness(
  {
    harness,
    prompt,
    edit = false,
    model,
    provider,
    cwd,
    threadId,
    title,
    env = harnessEnv(),
    killGraceMs = KILL_GRACE_MS,
  },
  onEvent,
  spawnImpl = spawn,
) {
  if (!Object.hasOwn(HARNESSES, harness)) throw new Error(`Unknown harness "${harness}".`);
  const adapter = HARNESSES[harness];
  if (typeof prompt !== "string" || !prompt.trim() || prompt.length > 20000) {
    throw new Error("prompt must be a non-empty string under 20,000 characters.");
  }
  const args = adapter.args({
    edit: edit || adapter.alwaysEdits,
    model: model ?? adapter.defaultModel,
    provider,
    cwd,
    threadId,
    title,
  });
  // Its own process group, so cancel reaches the shell commands it starts.
  const child = spawnImpl(adapter.bin, args, { cwd, stdio: ["pipe", "pipe", "pipe"], env, detached: true });
  child.stdin?.on?.("error", () => {}); // a CLI that exits early closes stdin
  child.stdin?.end?.(prompt);

  let finished_ = false;
  let reported = null; // the CLI's own outcome, emitted only at exit
  const emit = (event) => {
    if (finished_) return;
    if (event.type === "done") {
      reported ??= event;
      return;
    }
    onEvent(event);
  };
  const finish = (event) => {
    if (finished_) return;
    finished_ = true;
    onEvent(event);
  };
  let stdout = "";
  const feed = lineParser((obj) => {
    for (const event of adapter.parse(obj)) emit(event);
  });
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    if (adapter.wholeOutput) stdout = (stdout + chunk).slice(-200000);
    else feed(chunk);
  });
  let stderr = "";
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (d) => {
    stderr = (stderr + d).slice(-4000);
  });
  const groupAlive = () => {
    if (!Number.isInteger(child.pid) || child.pid <= 0) return false;
    try {
      process.kill(-child.pid, 0);
      return true;
    } catch {
      return false;
    }
  };
  const signalGroup = (sig) => {
    try {
      process.kill(-child.pid, sig);
    } catch {
      try {
        child.kill(sig);
      } catch {
        // already gone
      }
    }
  };
  let cancelled = false;
  let cleanupDone = Promise.resolve();
  let killTimer;
  let cleanupPoll;
  const stopEscalation = () => {
    clearTimeout(killTimer);
    clearInterval(cleanupPoll);
  };
  const finished = new Promise((resolve) => {
    child.on("error", (e) => {
      stopEscalation();
      emit({ type: "error", message: e.message });
      finish({ type: "done", ok: false, summary: e.message });
      resolve();
    });
    child.on("close", async (code, signal) => {
      if (!cancelled) stopEscalation();
      else await cleanupDone;
      if (adapter.wholeOutput) {
        const obj = lastJsonObject(stdout);
        if (obj) for (const event of adapter.parse(obj)) emit(event);
      }
      const exitedOk = code === 0;
      const failure = signal
        ? (adapter.cancelSummary?.(signal) ?? `stopped (${signal})`)
        : (adapter.exitSummary?.(code) ?? `exit ${code}: ${stderr.trim().slice(-500)}`);
      finish({
        type: "done",
        ok: exitedOk && (reported ? reported.ok : true),
        summary: exitedOk ? (reported?.summary ?? "") : failure,
      });
      resolve();
    });
  });
  const cancel = () => {
    if (cancelled || finished_) return;
    cancelled = true;
    signalGroup("SIGTERM");
    cleanupDone = new Promise((resolve) => {
      const done = () => {
        stopEscalation();
        resolve();
      };
      if (!groupAlive()) {
        done();
        return;
      }
      const pollMs = Math.min(50, Math.max(10, Math.floor(killGraceMs / 4)));
      cleanupPoll = setInterval(() => {
        if (!groupAlive()) done();
      }, pollMs);
      killTimer = setTimeout(() => {
        clearInterval(cleanupPoll);
        if (groupAlive()) signalGroup("SIGKILL");
        const settle = setInterval(() => {
          if (!groupAlive()) {
            clearInterval(settle);
            clearTimeout(giveUp);
            done();
          }
        }, 25);
        const giveUp = setTimeout(() => {
          clearInterval(settle);
          done();
        }, 500);
      }, killGraceMs);
    });
  };
  return { cancel, finished };
}

/**
 * Cancel every active run on app `before-quit`, preventing immediate shutdown
 * until process-group cleanup (including SIGKILL escalation) has completed.
 * Returns the cleanup promise when shutdown was deferred, or null if idle.
 */
export function cancelRunsOnQuit(runs, event, quit) {
  const active = [...runs];
  if (active.length === 0) return null;
  event.preventDefault();
  for (const r of active) r.cancel();
  return Promise.allSettled(active.map((r) => r.finished)).finally(() => quit());
}
