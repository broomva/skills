// Drives the MCP server over real stdio, the same path Claude Code uses.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as nfs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const SERVER = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "scripts", "vbash-server.mjs");
const tmp = () => nfs.mkdtempSync(path.join(os.tmpdir(), "mcp-"));

const OPEN = new Set();
async function connect(world) {
  const c = new Client({ name: "test", version: "1.0.0" });
  await c.connect(new StdioClientTransport({
    command: process.execPath, args: [SERVER], env: { ...process.env, JB_WORLD: world },
  }));
  OPEN.add(c);
  return c;
}
async function shut(c) { OPEN.delete(c); try { await c.close(); } catch { /* already gone */ } }
// Every test body ends in `finally { reap() }`. Without it a failing or
// timed-out test leaves a live server child and `node --test` never exits --
// CI would hang instead of reporting a failure.
// NB: do NOT reap from a `beforeExit` hook. Async work scheduled there re-arms
// the event loop, so the hook fires forever and the runner hangs anyway.
const call = async (c, command) =>
  (await c.callTool({ name: "vbash", arguments: { command } })).content[0].text;

test("server exposes exactly the vbash tool", { timeout: 30000 }, async () => {
  try {
    const c = await connect(path.join(tmp(), "w.json"));
    const names = (await c.listTools()).tools.map((t) => t.name);
    assert.deepEqual(names, ["vbash"]);
    await shut(c);
  } finally { for (const c of [...OPEN]) await shut(c); }
});

test("filesystem state persists across tool calls and a server RESTART", { timeout: 30000 }, async () => {
  try {
    const world = path.join(tmp(), "w.json");
    let c = await connect(world);
    await call(c, "echo hello > /work/a.txt");
    await call(c, "mkdir -p /work/sub && cd /work/sub");
    assert.match(await call(c, "pwd"), /\/work\/sub/);
    await shut(c);
  
    c = await connect(world);                    // new OS process, world reloaded from JSON
    assert.match(await call(c, "cat /work/a.txt"), /hello/);
    assert.match(await call(c, "pwd"), /\/work\/sub/, "shell state lost across restart");
    await shut(c);
  } finally { for (const c of [...OPEN]) await shut(c); }
});

test("a forked world diverges from its trunk under the server", { timeout: 30000 }, async () => {
  try {
    const d = tmp(), trunk = path.join(d, "t.json"), branch = path.join(d, "b.json");
    let c = await connect(trunk);
    await call(c, "echo base > /work/base.txt");
    await shut(c);
  
    nfs.copyFileSync(trunk, branch);             // the fork
    c = await connect(branch);
    await call(c, "echo only-branch > /work/branch.txt");
    await shut(c);
  
    c = await connect(trunk);
    const ls = await call(c, "ls /work");
    assert.match(ls, /base\.txt/);
    assert.ok(!ls.includes("branch.txt"), "branch file appeared in the trunk");
    await shut(c);
  } finally { for (const c of [...OPEN]) await shut(c); }
});

test("nonzero exit codes and stderr are reported to the caller", { timeout: 30000 }, async () => {
  try {
    const c = await connect(path.join(tmp(), "w.json"));
    const out = await call(c, "cat /work/does-not-exist");
    assert.match(out, /No such file|exit 1/);
    await shut(c);
  } finally { for (const c of [...OPEN]) await shut(c); }
});

test("the MCP tool reports when shell state was not captured", { timeout: 30000 }, async () => {
  const c = await connect(path.join(tmp(), "w.json"));
  try {
    await call(c, "mkdir -p /work/s");
    const bailed = await call(c, "cd /work/s; set -e; false");
    assert.match(bailed, /shell state \(cwd, env\) was NOT captured/,
      "the agent is not told its cd/export was discarded");
    const fine = await call(c, "cd /work/s");
    assert.ok(!/NOT captured/.test(fine), "a normal command must not warn");
  } finally { for (const x of [...OPEN]) await shut(x); }
});
