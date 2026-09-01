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
  // Response assembly has two invariants that must BOTH hold, for every combination
  // of large/small stdout, large/small stderr, and warning present/absent:
  //   (1) the result never exceeds MAX_OUTPUT
  //   (2) the state warning is never dropped
  // Truncating the joined body satisfies (1) and breaks (2); protecting metadata
  // from truncation satisfies (2) and breaks (1). Both were shipped in turn. So:
  // reserve the small bounded metadata, then spend the remaining room on the two
  // streams, trimming stdout first and stderr second.
  const NOTE = "[output truncated]";
  const warn = res.stateCaptured === false
    ? "[warning] shell state (cwd, env) was NOT captured: the command exited before the state epilogue ran (exit/set -e). Files persist; cwd and exported variables do not."
    : "";
  const exitLine = res.exitCode !== 0 ? `[exit ${res.exitCode}]` : "";
  const reserved = [exitLine, warn].filter(Boolean);
  // +1 per joined line; NOTE is only added when something is actually trimmed.
  const reservedLen = reserved.reduce((n, x) => n + x.length + 1, 0) + NOTE.length + 1;

  let room = Math.max(0, MAX_OUTPUT - reservedLen);
  let truncated = false;
  let out = res.stdout;
  let err = res.stderr ? `[stderr]\n${res.stderr}` : "";
  // stderr is a stream like any other -- treating it as protected metadata is what
  // broke the cap. Give it at most half the room when both compete.
  if (out.length + err.length > room) {
    truncated = true;
    const errBudget = Math.min(err.length, Math.floor(room / 2));
    const outBudget = Math.max(0, room - errBudget);
    out = out.slice(0, outBudget);
    err = err.slice(0, errBudget);
  }

  // No second clamp here. A trailing slice() would be a weaker duplicate of the
  // budget above -- it enforces the cap while trimming SILENTLY, which breaks the
  // "say when you trimmed" invariant, and it made the budget arithmetic
  // unobservable (mutants M20 and M21 both survived while it was present).
  const body = [out, err, truncated ? NOTE : "", ...reserved]
    .filter(Boolean).join("\n") || "(no output)";
  return { content: [{ type: "text", text: body }] };
});

await server.connect(new StdioServerTransport());
