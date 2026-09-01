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
// The response always carries a mandatory envelope (exit line, state warning). A cap
// smaller than that envelope cannot be honoured -- the trim loop runs out of stream to
// cut and the "never exceeds MAX_OUTPUT" invariant becomes false. Reject such caps at
// startup rather than silently violating the contract at runtime.
const MIN_OUTPUT = 512;
const MAX_OUTPUT = Number(process.env.JB_MAX_OUTPUT ?? 20000);
if (!Number.isInteger(MAX_OUTPUT) || MAX_OUTPUT < MIN_OUTPUT) {
  console.error(
    `forkable-shell: JB_MAX_OUTPUT must be an integer >= ${MIN_OUTPUT} ` +
    `(got ${JSON.stringify(process.env.JB_MAX_OUTPUT)}); the response envelope does not fit below that.`);
  process.exit(1);
}
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

  let out = res.stdout;
  let err = res.stderr ? `[stderr]\n${res.stderr}` : "";
  let truncated = false;
  const build = () =>
    [out, err, truncated ? NOTE : "", ...reserved].filter(Boolean).join("\n") || "(no output)";

  // Fit by MEASURING rather than by arithmetic over separator counts -- the arithmetic
  // version was off by one when both streams were present. Trim the longer stream
  // each pass so neither can starve the other, and stop if only the small reserved
  // metadata is left (it is bounded and must survive).
  while (build().length > MAX_OUTPUT) {
    truncated = true;
    const over = build().length - MAX_OUTPUT;
    if (out.length === 0 && err.length === 0) break;
    if (out.length >= err.length) out = out.slice(0, Math.max(0, out.length - over));
    else err = err.slice(0, Math.max(0, err.length - over));
  }
  const body = build();
  return { content: [{ type: "text", text: body }] };
});

await server.connect(new StdioServerTransport());
