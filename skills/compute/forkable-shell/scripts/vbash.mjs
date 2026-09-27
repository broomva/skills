#!/usr/bin/env node
// CLI for forkable virtual shells.
//   init <world> [--seed <hostfile>:<guestpath>]...   create a world
//   fork <src> <dst>                                  copy a world (this is the fork)
//   exec <world> <command...>                         run one command, persist
//   cat  <world> <guestpath>                          read a file out of a world
//   info <world>                                      turns, size, contents
//   mcp-config <world> [--log <path>]                 print MCP server config JSON
//   drive <world> <prompt> [--log <p>] [--model m] [--max-turns n]
//                                                     run one Claude Code turn against the world
import * as nfs from "node:fs";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { World } from "./world.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SERVER = path.join(HERE, "vbash-server.mjs");
const [cmd, ...rest] = process.argv.slice(2);
const die = (m) => { console.error(`vbash: ${m}`); process.exit(2); };
const takeFlag = (args, name) => {
  const i = args.indexOf(name);
  if (i === -1) return null;
  const v = args[i + 1]; args.splice(i, 2); return v;
};

function mcpConfig(world, log) {
  return {
    mcpServers: {
      vbash: {
        command: process.execPath,
        args: [SERVER],
        env: { JB_WORLD: path.resolve(world), ...(log ? { JB_LOG: path.resolve(log) } : {}) },
      },
    },
  };
}

switch (cmd) {
  case "init": {
    const args = [...rest];
    const seeds = [];
    for (let s; (s = takeFlag(args, "--seed")) !== null; ) seeds.push(s);
    const world = args[0] ?? die("usage: init <world> [--seed host:guest]");
    const files = {};
    for (const s of seeds) {
      const idx = s.lastIndexOf(":");
      if (idx === -1) die(`--seed needs host:guest, got ${s}`);
      const [host, guest] = [s.slice(0, idx), s.slice(idx + 1)];
      files[guest] = new Uint8Array(nfs.readFileSync(host));   // bytes, not utf8
    }
    await World.open(world, { files });
    console.log(`created ${world} (${nfs.statSync(world).size} bytes, ${Object.keys(files).length} seeded)`);
    break;
  }
  case "fork": {
    const [src, dst] = rest;
    if (!src || !dst) die("usage: fork <src> <dst>");
    World.fork(src, dst);
    console.log(`forked ${src} -> ${dst} (${nfs.statSync(dst).size} bytes)`);
    break;
  }
  case "exec": {
    const [world, ...c] = rest;
    if (!world || !c.length) die("usage: exec <world> <command...>");
    const w = await World.open(world);
    const r = await w.exec(c.join(" "));
    if (r.stdout) process.stdout.write(r.stdout);
    if (r.stderr) process.stderr.write(r.stderr);
    if (r.stateCaptured === false) {
      process.stderr.write("vbash: warning: shell state (cwd, env) was NOT captured — " +
        "the command exited before the state epilogue ran (exit/set -e).\n");
    }
    process.exit(r.exitCode);
  }
  case "cat": {
    const [world, p] = rest;
    if (!world || !p) die("usage: cat <world> <guestpath>");
    const w = await World.open(world);
    process.stdout.write(Buffer.from(await w.fs.readFileBuffer(p)));  // bytes, not utf8
    break;
  }
  case "info": {
    const world = rest[0] ?? die("usage: info <world>");
    const i = World.info(world);
    console.log(`${world}: ${i.turns} turns, ${i.bytes} bytes, cwd=${i.cwd}`);
    for (const d of i.dirs) console.log(`  dir   ${d}`);
    for (const f of i.files) console.log(`  file  ${f.path}${f.hardlinkTo ? ` -> ${f.hardlinkTo}` : ` (${f.bytes}B)`}`);
    for (const l of i.links) console.log(`  link  ${l}`);
    break;
  }
  case "mcp-config": {
    const args = [...rest];
    const log = takeFlag(args, "--log");
    const world = args[0] ?? die("usage: mcp-config <world> [--log <path>]");
    console.log(JSON.stringify(mcpConfig(world, log), null, 2));
    break;
  }
  case "drive": {
    const args = [...rest];
    const log = takeFlag(args, "--log");
    const model = takeFlag(args, "--model") ?? "sonnet";
    const maxTurns = takeFlag(args, "--max-turns") ?? "60";
    const world = args.shift() ?? die("usage: drive <world> <prompt> [--log p] [--model m] [--max-turns n]");
    const prompt = args.join(" ") || die("a prompt is required");
    await World.open(world);                       // ensure the world exists
    const cfg = path.join(nfs.mkdtempSync("/tmp/vbash-"), "mcp.json");
    nfs.writeFileSync(cfg, JSON.stringify(mcpConfig(world, log)));
    const r = spawnSync("claude", [
      "-p", prompt,
      "--mcp-config", cfg,
      "--allowed-tools", "mcp__vbash__vbash",
      // Deny every host-touching tool: the virtual FS must be the agent's only world.
      "--disallowed-tools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit",
      "--model", model, "--max-turns", maxTurns, "--output-format", "text",
    ], { stdio: ["ignore", "inherit", "inherit"] });
    nfs.rmSync(path.dirname(cfg), { recursive: true, force: true });
    process.exit(r.status ?? 1);
  }
  default:
    console.log(nfs.readFileSync(fileURLToPath(import.meta.url), "utf8")
      .split("\n").filter((l) => l.startsWith("//")).slice(1, 10).join("\n").replace(/^\/\/ ?/gm, ""));
    process.exit(cmd ? 2 : 0);
}
