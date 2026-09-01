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

async function connect(world) {
  const c = new Client({ name: "test", version: "1.0.0" });
  await c.connect(new StdioClientTransport({
    command: process.execPath, args: [SERVER], env: { ...process.env, JB_WORLD: world },
  }));
  return c;
}
const call = async (c, command) =>
  (await c.callTool({ name: "vbash", arguments: { command } })).content[0].text;

test("server exposes exactly the vbash tool", async () => {
  const c = await connect(path.join(tmp(), "w.json"));
  const names = (await c.listTools()).tools.map((t) => t.name);
  assert.deepEqual(names, ["vbash"]);
  await c.close();
});

test("filesystem state persists across tool calls and a server RESTART", async () => {
  const world = path.join(tmp(), "w.json");
  let c = await connect(world);
  await call(c, "echo hello > /work/a.txt");
  await call(c, "mkdir -p /work/sub && cd /work/sub");
  assert.match(await call(c, "pwd"), /\/work\/sub/);
  await c.close();

  c = await connect(world);                    // new OS process, world reloaded from JSON
  assert.match(await call(c, "cat /work/a.txt"), /hello/);
  assert.match(await call(c, "pwd"), /\/work\/sub/, "shell state lost across restart");
  await c.close();
});

test("a forked world diverges from its trunk under the server", async () => {
  const d = tmp(), trunk = path.join(d, "t.json"), branch = path.join(d, "b.json");
  let c = await connect(trunk);
  await call(c, "echo base > /work/base.txt");
  await c.close();

  nfs.copyFileSync(trunk, branch);             // the fork
  c = await connect(branch);
  await call(c, "echo only-branch > /work/branch.txt");
  await c.close();

  c = await connect(trunk);
  const ls = await call(c, "ls /work");
  assert.match(ls, /base\.txt/);
  assert.ok(!ls.includes("branch.txt"), "branch file appeared in the trunk");
  await c.close();
});

test("nonzero exit codes and stderr are reported to the caller", async () => {
  const c = await connect(path.join(tmp(), "w.json"));
  const out = await call(c, "cat /work/does-not-exist");
  assert.match(out, /No such file|exit 1/);
  await c.close();
});
