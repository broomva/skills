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
  // Metadata is assembled FIRST and its space reserved, then stdout is trimmed to
  // fit. Truncating the joined body instead would drop the trailing warning exactly
  // when a command produces a lot of output -- silently restoring the failure mode
  // the warning exists to prevent.
  const meta = [
    res.stderr ? `[stderr]\n${res.stderr}` : "",
    res.exitCode !== 0 ? `[exit ${res.exitCode}]` : "",
    // Without this the agent cannot tell that its `cd` and `export` were discarded
    // because the command exited before state capture.
    res.stateCaptured === false
      ? "[warning] shell state (cwd, env) was NOT captured: the command exited before the state epilogue ran (exit/set -e). Files persist; cwd and exported variables do not."
      : "",
  ].filter(Boolean).join("\n");

  const NOTE = "[output truncated]";
  const room = Math.max(0, MAX_OUTPUT - meta.length - NOTE.length - 2);
  const truncated = res.stdout.length > room;
  const body = [
    truncated ? res.stdout.slice(0, room) : res.stdout,
    truncated ? NOTE : "",
    meta,
  ].filter(Boolean).join("\n") || "(no output)";
  return { content: [{ type: "text", text: body }] };
});

await server.connect(new StdioServerTransport());
