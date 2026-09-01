#!/usr/bin/env node
// MCP stdio server exposing a forkable virtual shell as the `vbash` tool.
//
// Every call write-throughs to JB_WORLD, so the world on disk is always current
// and can be forked between calls. The agent cannot reach the host filesystem:
// the only filesystem it is given is the in-memory one.
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import * as nfs from "node:fs";
import { World } from "./world.mjs";

const WORLD = process.env.JB_WORLD;
const LOG = process.env.JB_LOG;
const MAX_OUTPUT = Number(process.env.JB_MAX_OUTPUT ?? 20000);
if (!WORLD) {
  console.error("forkable-shell: JB_WORLD (path to the world JSON) is required");
  process.exit(1);
}

const world = await World.open(WORLD);

const server = new McpServer({ name: "vbash", version: "1.0.0" });
server.registerTool("vbash", {
  title: "Virtual bash",
  description:
    "Run a bash command inside an isolated virtual filesystem. This is the ONLY " +
    "filesystem you can see or modify; the host machine is not reachable. Your " +
    "workspace is /work. Standard unix tools are available (ls, cat, sed, awk, grep, " +
    "jq, sqlite3, find, sort, tar, wc). State persists across calls.",
  inputSchema: { command: z.string().describe("bash command to run") },
}, async ({ command }) => {
  const res = await world.exec(command);
  if (LOG) {
    nfs.appendFileSync(LOG, JSON.stringify({
      t: Date.now(), turn: world.turns, cmd: command,
      exit: res.exitCode, out: res.stdout.slice(0, 400), err: res.stderr.slice(0, 200),
    }) + "\n");
  }
  const body = [
    res.stdout,
    res.stderr ? `[stderr]\n${res.stderr}` : "",
    res.exitCode !== 0 ? `[exit ${res.exitCode}]` : "",
  ].filter(Boolean).join("\n") || "(no output)";
  return { content: [{ type: "text", text: body.slice(0, MAX_OUTPUT) }] };
});

await server.connect(new StdioServerTransport());
