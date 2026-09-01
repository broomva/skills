---
name: forkable-shell
category: compute
tier: D
description: >
  Gives an agent session a disposable, sandboxed bash shell whose entire filesystem is
  a single JSON file — so the workspace can be snapshotted, forked, branched and resumed
  at ~0.24ms per fork instead of seconds per container. Backed by just-bash (in-process,
  no VM, no container, no host access). Use when you want to run agent-generated shell
  commands without giving them a real machine, checkpoint an agent workspace, fork one
  workspace into N parallel branches to try competing approaches, resume a workspace in a
  later session or process, or hand a Claude Code subprocess a throwaway shell. Triggers on
  "forkable shell", "virtual shell", "sandboxed shell", "disposable shell", "fork the
  workspace", "branch the agent state", "checkpoint this workspace", "snapshot the
  filesystem", "vbash", "just-bash", "sandbox without a container". NOT FOR running real
  binaries (git, node, npm, compilers), long-running daemons, listening sockets, or
  untrusted human adversaries — use a real VM or Vercel Sandbox for those.
---

# forkable-shell

A **world** is one JSON file holding an entire agent workspace: the virtual filesystem
plus shell state. Because a world is a single value, **forking is a file copy**.

```
world.json ──fork──> A.json   (branch A works here)
           └─fork──> B.json   (branch B works here)
           trunk is never opened, so it cannot be mutated
```

## Setup

```bash
cd skills/compute/forkable-shell && npm install     # just-bash + MCP SDK
```

Requires **Node ≥ 20.18.1**. Run it under `node`, not `bun` — see Constraints.

## CLI (`scripts/vbash.mjs`)

```bash
node scripts/vbash.mjs init  <world> [--seed <hostfile>:<guestpath>]...
node scripts/vbash.mjs fork  <src> <dst>
node scripts/vbash.mjs exec  <world> <command...>
node scripts/vbash.mjs cat   <world> <guestpath>
node scripts/vbash.mjs info  <world>
node scripts/vbash.mjs mcp-config <world> [--log <path>]
node scripts/vbash.mjs drive <world> <prompt> [--log <p>] [--model m] [--max-turns n]
```

## Giving a Claude Code session a throwaway shell

`drive` runs one Claude Code turn whose **only** filesystem is the world:

```bash
node scripts/vbash.mjs init /tmp/w.json --seed ./data.csv:/work/data.csv
node scripts/vbash.mjs drive /tmp/w.json "Summarise /work/data.csv into /work/out.json"
node scripts/vbash.mjs cat /tmp/w.json /work/out.json
```

It passes `--allowed-tools mcp__vbash__vbash` and denies `Bash,Read,Write,Edit,Glob,Grep,
WebFetch,WebSearch,Task,NotebookEdit`, so the agent has no host-touching tool at all.
To wire it into a session you drive yourself, use `mcp-config` and pass the file to
`claude --mcp-config`.

## The fork workflow

1. `init` a trunk and seed it with inputs.
2. `fork` the trunk once per approach you want to try.
3. `drive` each branch with a different prompt (they are independent files, so run them
   in parallel).
4. Score each branch by reading artifacts out with `cat`.
5. Promote the winner (`cp` it over your working world). The trunk is untouched, so you
   can re-fork and try again.

**Always fork before branching.** Opening a world mutates it; `fork` never opens the
source. `tests/unit/world.test.mjs` asserts a branch cannot change its trunk's bytes,
turn count, or file list.

## Constraints worth knowing before you trust it

Measured. The first five have regression tests in this skill; the Bun, turn-budget
and custom-backend notes are findings from the session that produced it, recorded here
because they will bite you, and are **not** covered by these tests:

- **Shell state does not persist by itself.** just-bash resets env, cwd and functions
  between `exec()` calls; only the filesystem is shared. `scripts/persistent-shell.mjs`
  replays state host-side.
- **Functions cannot be recovered from the guest.** `declare -f` returns a stub with the
  body elided, so register them host-side via `addRc()`.
- **Shell state must be restored paired with its filesystem.** Loading state onto a fresh
  filesystem silently drops the cwd back to the default.
- **Snapshots are prefix-scoped.** An unscoped walk captures ~180 synthetic `/bin`,
  `/usr/bin`, `/dev`, `/proc` entries — the whole virtual distro instead of the workspace.
- **Bun is not supported by default.** just-bash 3.4.2 throws
  `DefenseInDepthBox: critical patches failed: Module._resolveFilename` on the first
  `exec()` under Bun. `defenseInDepth: false` fixes the core shell but not `sqlite3`
  (a separate worker guard). Use Node.
- **Budget turns generously when driving.** A `--max-turns` cap that is too low produces
  an empty result that looks like a capability failure. The default here is 60.
- **A custom filesystem backend boots empty.** just-bash seeds `/bin`, `/tmp`, `/dev`,
  `/proc` only for filesystems exposing synchronous `mkdirSync`/`writeFileSync`.

## Not a security boundary against humans

just-bash runs without VM isolation and is beta. Containment is verified against the
tool (`tests/integration/containment.test.mjs`: 8 host probes plus a positive control
proving the probe can detect a leak), and it holds for agent-generated commands. It is
not a bounty-grade jail. For arbitrary binaries or hostile input, use a real VM.

## Files

| Path | Role |
|---|---|
| `scripts/world.mjs` | the world abstraction: open, save, exec, fork, info |
| `scripts/fs-snapshot.mjs` | filesystem serialize/rehydrate (dirs, symlinks, hardlink groups, modes, mtimes) |
| `scripts/persistent-shell.mjs` | replays env/cwd/functions across `exec()` calls |
| `scripts/vbash-server.mjs` | MCP stdio server exposing the `vbash` tool |
| `scripts/vbash.mjs` | CLI |

## Tests

```bash
npm test          # node --test tests/unit/*.test.mjs tests/integration/*.test.mjs
```

Unit tests cover snapshot fidelity (binary, UTF-8, empty dirs, symlinks, hardlink
groups, file modes and mtimes, odd filenames), shell-state replay, and fork isolation
— including forking onto a destination that is a hardlink to the trunk.

Integration tests are two separate suites: `mcp.test.mjs` drives the MCP server over
real stdio (tool listing, restart persistence, fork divergence, error reporting), and
`containment.test.mjs` asserts host isolation through that same server.

**Symlink modes and mtimes are not restored** — `symlink()` takes neither, and the
snapshot records them for information only. File modes and mtimes are restored.
