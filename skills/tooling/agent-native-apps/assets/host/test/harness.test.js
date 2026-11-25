import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { test } from "node:test";
import {
  HARNESSES,
  harnessEnv,
  lastJsonObject,
  lineParser,
  parseLoginPath,
  runHarness,
} from "../src/harness.js";

test("the prompt never appears in argv for any harness", () => {
  const secret = "--dangerously-skip-permissions do the thing";
  for (const [name, h] of Object.entries(HARNESSES)) {
    const args = h.args({
      prompt: secret,
      edit: false,
      model: "m",
      provider: "p",
      cwd: "/app",
      threadId: undefined,
    });
    assert.ok(!args.includes(secret), `${name} must read the prompt from stdin`);
    assert.ok(!args.some((a) => a.includes("dangerously")), name);
  }
});

test("claude: no settings from anywhere, no MCP servers; tools follow edit", () => {
  const ro = HARNESSES.claude.args({ edit: false, model: "haiku" });
  assert.equal(ro[ro.indexOf("--setting-sources") + 1], "", "neither user nor app-folder settings (hooks)");
  assert.equal(ro[ro.indexOf("--mcp-config") + 1], '{"mcpServers":{}}');
  assert.ok(ro.includes("--strict-mcp-config"));
  assert.equal(ro[ro.indexOf("--tools") + 1], "Read,Glob,Grep");
  const rw = HARNESSES.claude.args({ edit: true, model: "haiku" });
  assert.equal(rw[rw.indexOf("--tools") + 1], "Read,Glob,Grep,Edit,Write");
  assert.equal(rw[rw.indexOf("--permission-mode") + 1], "acceptEdits");
});

test("codex: sandbox follows edit, pinned to the app folder, prompt from stdin", () => {
  const ro = HARNESSES.codex.args({ edit: false, cwd: "/app" });
  assert.equal(ro[ro.indexOf("-s") + 1], "read-only");
  assert.equal(ro[ro.indexOf("-C") + 1], "/app");
  assert.equal(ro.at(-1), "-");
  assert.ok(!ro.includes("-m"), "no model flag unless one is given");
  const rw = HARNESSES.codex.args({ edit: true, model: "gpt-x", cwd: "/app" });
  assert.equal(rw[rw.indexOf("-s") + 1], "workspace-write");
  assert.equal(rw[rw.indexOf("-m") + 1], "gpt-x");
});

test("t3: start in the app's project, continue the app's thread, provider only with a model", () => {
  const start = HARNESSES.t3.args({
    cwd: "/app",
    title: "Pad agent",
    provider: "claudeAgent",
    model: "claude-haiku-5-5",
  });
  assert.deepEqual(start.slice(0, 4), ["thread", "start", "/app", "-"]);
  assert.equal(start[start.indexOf("--provider") + 1], "claudeAgent");
  assert.ok(start.includes("--wait") && start.includes("--json"));
  assert.ok(!HARNESSES.t3.args({ cwd: "/app", provider: "claudeAgent" }).includes("--provider"));
  assert.deepEqual(HARNESSES.t3.args({ cwd: "/app", threadId: "mcp:1" }), [
    "thread",
    "send",
    "mcp:1",
    "-",
    "--wait",
    "--json",
  ]);
  assert.equal(HARNESSES.t3.alwaysEdits, true);
});

test("t3 result maps to thread, text and done", () => {
  const p = HARNESSES.t3.parse;
  assert.deepEqual(p({ threadId: "mcp:1", runId: "r", status: "completed", reply: "pong", error: null }), [
    { type: "thread", threadId: "mcp:1" },
    { type: "text", text: "pong" },
    { type: "done", ok: true, summary: "" },
  ]);
  assert.equal(p({ threadId: "mcp:1", status: "failed", reply: null, error: "boom" }).at(-1).ok, false);
  assert.deepEqual(p({ unrelated: true }), []);
  assert.match(HARNESSES.t3.exitSummary(2), /waiting for an answer/);
});

test("claude stream-json maps to text, tool and done events", () => {
  const p = HARNESSES.claude.parse;
  assert.deepEqual(
    p({
      type: "assistant",
      message: {
        content: [
          { type: "text", text: "pong" },
          { type: "tool_use", name: "Edit", input: { a: 1 } },
        ],
      },
    }),
    [
      { type: "text", text: "pong" },
      { type: "tool", name: "Edit", input: { a: 1 } },
    ],
  );
  assert.deepEqual(p({ type: "result", subtype: "success", is_error: false, result: "pong" }), [
    { type: "done", ok: true, summary: "pong" },
  ]);
  assert.equal(p({ type: "result", subtype: "error_max_turns", is_error: true })[0].ok, false);
  assert.deepEqual(p({ type: "system", subtype: "hook_started" }), []);
});

test("codex jsonl: warnings and top-level errors are not the outcome; turn events are", () => {
  const p = HARNESSES.codex.parse;
  assert.deepEqual(p({ type: "item.completed", item: { type: "error", message: "deprecated flag" } }), []);
  assert.deepEqual(p({ type: "error", message: "stream dropped; retrying" }), [
    { type: "error", message: "stream dropped; retrying" },
  ]);
  assert.deepEqual(p({ type: "item.completed", item: { type: "agent_message", text: "pong" } }), [
    { type: "text", text: "pong" },
  ]);
  assert.deepEqual(p({ type: "turn.completed", usage: {} }), [{ type: "done", ok: true, summary: "" }]);
  assert.equal(p({ type: "turn.failed", error: { message: "out of credits" } })[0].summary, "out of credits");
});

test("lineParser handles split chunks and skips log lines", () => {
  const seen = [];
  const feed = lineParser((o) => seen.push(o));
  feed('{"a":');
  feed('1}\n2026 ERROR not json\n{"b":2}\n{"c"');
  assert.deepEqual(seen, [{ a: 1 }, { b: 2 }]);
});

test("lastJsonObject finds a pretty-printed result after log noise", () => {
  assert.deepEqual(lastJsonObject('log {x}\n{\n  "threadId": "t",\n  "nested": {"a": 1}\n}\n'), {
    threadId: "t",
    nested: { a: 1 },
  });
  assert.equal(lastJsonObject("no json here"), null);
});

test("parseLoginPath ignores rc-file noise around the marker", () => {
  const out = "welcome!\n__AGENT_NATIVE_APPS_PATH__/a:/b__AGENT_NATIVE_APPS_PATH__";
  assert.equal(parseLoginPath(out), "/a:/b");
  assert.equal(parseLoginPath("nothing"), null);
});

test("harnessEnv passes an allowlist, not the host's tokens", () => {
  const env = harnessEnv({
    HOME: "/h",
    PATH: "/bin",
    GITHUB_TOKEN: "x",
    ANTHROPIC_API_KEY: "y",
    AWS_SECRET: "z",
  });
  assert.deepEqual(env, { TERM: "dumb", NO_COLOR: "1", HOME: "/h", PATH: "/bin" });
});

function fakeChild() {
  const child = new EventEmitter();
  child.pid = 999999; // no such process group: cancel falls back to child.kill
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.stdinText = "";
  child.stdin = { on() {}, end: (text) => (child.stdinText = text) };
  child.killed = [];
  child.kill = (sig) => {
    child.killed.push(sig);
    child.emit("close", null, sig);
  };
  return child;
}

test("runHarness writes the prompt to stdin and holds done until the process exits", async () => {
  const child = fakeChild();
  const events = [];
  const opts = { harness: "claude", prompt: "--help hi", cwd: "/tmp" };
  let spawned;
  const { finished } = runHarness(
    opts,
    (e) => events.push(e),
    (bin, args, o) => {
      spawned = { bin, args, o };
      return child;
    },
  );
  assert.equal(child.stdinText, "--help hi");
  assert.equal(spawned.o.detached, true, "own process group, so cancel reaches subprocesses");
  assert.ok(!("GITHUB_TOKEN" in spawned.o.env));
  child.stdout.write('{"type":"assistant","message":{"content":[{"type":"text","text":"pong"}]}}\n');
  child.stdout.write('{"type":"result","subtype":"success","is_error":false,"result":"pong"}\n');
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(
    events.map((e) => e.type),
    ["text"],
    "the CLI's result is not done while it still runs",
  );
  child.emit("close", 0, null);
  await finished;
  assert.deepEqual(
    events.map((e) => e.type),
    ["text", "done"],
  );
  assert.deepEqual(events.at(-1), { type: "done", ok: true, summary: "pong" });
});

test("runHarness parses t3's whole output at exit", async () => {
  const child = fakeChild();
  const events = [];
  const { finished } = runHarness(
    { harness: "t3", prompt: "hi", cwd: "/app" },
    (e) => events.push(e),
    () => child,
  );
  child.stdout.write('{"threadId":"mcp:1","runId":"r","status":"comp');
  child.stdout.write('leted","reply":"pong","error":null}\n');
  await new Promise((r) => setImmediate(r));
  child.emit("close", 0, null);
  await finished;
  assert.deepEqual(
    events.map((e) => e.type),
    ["thread", "text", "done"],
  );
});

test("runHarness reports a CLI that dies without a result, and a waiting t3 thread", async () => {
  const child = fakeChild();
  const events = [];
  const { finished } = runHarness(
    { harness: "codex", prompt: "hi", cwd: "/tmp" },
    (e) => events.push(e),
    () => child,
  );
  child.stderr.write("boom");
  await new Promise((r) => setImmediate(r));
  child.emit("close", 2, null);
  await finished;
  assert.equal(events.at(-1).ok, false);
  assert.match(events.at(-1).summary, /exit 2: boom/);

  const waiting = fakeChild();
  const t3events = [];
  const t3 = runHarness(
    { harness: "t3", prompt: "hi", cwd: "/app" },
    (e) => t3events.push(e),
    () => waiting,
  );
  waiting.emit("close", 2, null);
  await t3.finished;
  assert.match(t3events.at(-1).summary, /waiting for an answer/);
});

test("cancel signals the run and the run ends once", async () => {
  const child = fakeChild();
  const events = [];
  const r = runHarness(
    { harness: "claude", prompt: "hi", cwd: "/tmp" },
    (e) => events.push(e),
    () => child,
  );
  r.cancel();
  await r.finished;
  assert.deepEqual(child.killed, ["SIGTERM"]);
  assert.equal(events.filter((e) => e.type === "done").length, 1);
  assert.match(events.at(-1).summary, /stopped \(SIGTERM\)/);
});

test("runHarness refuses an empty prompt and unknown or prototype harness names", () => {
  assert.throws(() => runHarness({ harness: "claude", prompt: " ", cwd: "/" }, () => {}));
  assert.throws(() => runHarness({ harness: "gpt", prompt: "x", cwd: "/" }, () => {}));
  assert.throws(
    () => runHarness({ harness: "toString", prompt: "x", cwd: "/" }, () => {}),
    /Unknown harness/,
  );
});
