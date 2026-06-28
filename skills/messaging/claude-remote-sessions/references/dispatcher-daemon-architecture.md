# Discord Dispatcher Daemon — Architecture

> Replaces the bash watchdog + per-channel gateway pattern with a single-gateway
> dispatcher that routes messages to per-channel Claude Code sessions on demand.

## Problem Statement

The current system spawns one full Claude Code instance per Discord channel, each
with its own Discord gateway connection and MCP servers. This creates:

- **N gateway connections** for N channels (wasteful, rate-limited)
- **~350 MB per channel** (Claude Code + Discord MCP + Telegram MCP)
- **No wake-on-message** — suspended sessions silently drop messages
- **Orphan processes** from crash loops that leak memory
- **Aggressive idle suspension** that kills sessions before users can interact

## Architecture

```
               Discord Gateway (1 WebSocket)
                        │
               ┌────────┴────────┐
               │   DISPATCHER    │  (~120 MB Bun, ~40 MB Rust)
               │                 │
               │  - discord.js   │
               │  - channel router│
               │  - session FSM  │
               │  - message queue│
               │  - slash cmds   │
               └────────┬────────┘
                        │ Unix socket (NDJSON)
            ┌───────────┼───────────┐
            │           │           │
      ┌─────┴─────┐ ┌──┴──┐  ┌────┴────┐
      │ Proxy MCP │ │ ... │  │ (none)  │
      │  ~20 MB   │ │     │  │SUSPENDED│
      └─────┬─────┘ └──┬──┘  └─────────┘
         stdio       stdio
            │           │
      ┌─────┴─────┐ ┌──┴──────┐
      │Claude Code│ │Claude   │
      │  ~365 MB  │ │Code     │
      └───────────┘ └─────────┘
```

### Key Insight: MCP Notification Interface

The Discord MCP plugin delivers messages to Claude Code via **MCP notifications
over stdio**:

```typescript
mcp.notification({
  method: 'notifications/claude/channel',
  params: { content, meta: { chat_id, message_id, user, user_id, ts } },
})
```

Outbound calls (reply, react, edit_message) use **MCP tool calls** over the same
stdio pipe. Claude Code doesn't know or care where the MCP server gets its data —
the proxy is indistinguishable from the real plugin.

## Components

### Dispatcher Daemon (single process)

- Maintains ONE `discord.js` `Client` with the gateway connection
- Receives all `messageCreate` events across all channels
- Routes inbound messages to the correct session based on channel ID
- Queues messages for suspended/spawning sessions (bounded, 50 max)
- Manages session lifecycle via the state machine
- Exposes Unix domain socket at `~/.claude/discord-dispatcher/dispatch.sock`
- Handles outbound API calls on behalf of proxy servers
- Subsumes slash daemon functionality

### Proxy MCP Server (one per active session)

- Speaks the exact same MCP stdio protocol as the official `server.ts`
- Claude Code sees it as a normal Discord channel plugin (same tools, same notifications)
- Connects to dispatcher via IPC (Unix socket) instead of Discord gateway
- Inbound: dispatcher → IPC → proxy writes MCP notification to Claude's stdin
- Outbound: Claude calls MCP tool → proxy forwards to dispatcher → Discord API → result returned
- Estimated memory: **~20 MB** (vs ~110 MB for full gateway server)

## Session State Machine

```
 IDLE ──message──▶ SPAWNING ──mcp connected──▶ ACTIVE ──idle timeout──▶ SUSPENDED
                      ▲                                                      │
                      └──────────────── message arrives ─────────────────────┘
```

| State | Processes | Memory | Behavior |
|-------|-----------|--------|----------|
| IDLE | None | 0 MB | Channel registered, no session. First message triggers spawn. |
| SPAWNING | tmux starting | 0 MB (growing) | Messages queued. Proxy connects when ready. |
| ACTIVE | Claude Code + Proxy MCP | ~385 MB | Processing messages normally. |
| SUSPENDED | None | 0 MB | Dispatcher still listening. Message triggers wake. |
| DEAD | None | 0 MB | Channel deleted/archived. Cleaned up. |

**Critical difference from current system**: a message arriving for a SUSPENDED
session triggers **wake-on-message**. The dispatcher is always listening, always
connected to the gateway.

## IPC Protocol

Unix domain socket at `~/.claude/discord-dispatcher/dispatch.sock`.
Protocol: newline-delimited JSON (NDJSON).

```typescript
// Proxy → Dispatcher: Register session
{ "type": "register", "session_id": "...", "channel_id": "..." }

// Dispatcher → Proxy: Inbound message
{ "type": "inbound", "channel_id": "...", "content": "...", "meta": { ... } }

// Proxy → Dispatcher: Outbound tool call
{ "type": "tool_call", "request_id": "...", "name": "reply", "args": { ... } }

// Dispatcher → Proxy: Tool call result
{ "type": "tool_result", "request_id": "...", "result": { ... } }

// Dispatcher → Proxy: Permission request relay
{ "type": "permission_request", "request_id": "...", ... }

// Proxy → Dispatcher: Permission response relay
{ "type": "permission_response", "request_id": "...", "behavior": "allow" }
```

## Message Flow

### Inbound (Discord → Claude)

1. Discord gateway delivers `messageCreate` to dispatcher's single `Client`
2. Dispatcher runs `gate()` logic (access control, mention check)
3. Looks up `channelId` in session registry
4. **ACTIVE**: Forward to connected proxy MCP via IPC
5. **SUSPENDED**: Enqueue message → transition to SPAWNING → spawn tmux → flush on connect
6. **IDLE**: Auto-discover if in configured guild → spawn → queue → flush
7. **SPAWNING**: Enqueue (bounded queue, oldest dropped with warning)

### Outbound (Claude → Discord)

1. Claude Code calls MCP tool (e.g., `reply`)
2. Proxy receives `CallToolRequest` via stdio
3. Proxy forwards to dispatcher via IPC
4. Dispatcher calls Discord API via its single `Client`
5. Result returned through IPC → proxy → Claude Code

## Memory Budget Comparison

| Scenario | Current | Proposed | Savings |
|----------|---------|----------|---------|
| 6 channels, all active | **3.4 GB** | **2.4 GB** | 30% (no Telegram sidecar) |
| 6 channels, 2 active, 4 suspended | **3.4 GB** | **0.9 GB** | 74% |
| 20 channels (with threads) | ~11.5 GB | **1.0 GB** (2 active) | 91% |

## Plugin Registration

The proxy MCP registers as a local plugin:

```
~/.claude/plugins/local/discord-proxy/
├── .claude-plugin/plugin.json
├── .mcp.json                    # Points to proxy script
├── package.json                 # @modelcontextprotocol/sdk only
└── server.ts                    # Proxy implementation
```

Sessions launch with `--channels plugin:discord-proxy@local` instead of the
official plugin. Claude Code sees the same MCP interface — no core changes needed.

## Terminal Chrome Filtering

The proxy MCP should strip Claude Code terminal chrome before posting to Discord:

- Lines entirely composed of box-drawing characters (`─`, `━`)
- Status line (matching `Sonnet|Opus|Haiku|Claude \d+\.\d+ |`)
- Bare prompt characters (`❯`, `>`)
- Collapse excessive blank lines

This filtering lives in the proxy's `reply` and `edit_message` handlers, not in
the official plugin (which gets overwritten on updates).

## Implementation Phases

| Phase | Scope | Effort | Language |
|-------|-------|--------|----------|
| **1. MVP** | Single gateway + proxy MCP + wake-on-message | 2-3 days | TypeScript/Bun |
| **2. Slash commands** | Absorb `discord-slash-daemon.ts` | 1 day | TS |
| **3. Message queue** | Bounded queue for SPAWNING, graceful shutdown | 1 day | TS |
| **4. Rust migration** | Rewrite dispatcher as `arcan-discord` crate | 1-2 weeks | Rust |
| **5. arcan-fleet** | Discord sessions as managed agent instances | Future | Rust |

### Phase 1 deliverables

```
skills/claude-remote-sessions/scripts/
├── discord-dispatcher.ts          # Main dispatcher daemon
├── discord-proxy-mcp.ts           # Proxy MCP server
├── discord-session-manager.sh     # Existing (minimal changes)
├── discord-watchdog.sh            # Replaced by dispatcher
├── discord-slash-daemon.ts        # Absorbed in Phase 2
```

### Phase 4 deliverables

```
core/life/arcan/crates/arcan-discord/
├── Cargo.toml
└── src/
    ├── dispatcher.rs              # Gateway + routing + session FSM
    ├── ipc.rs                     # Unix socket NDJSON protocol
    ├── session.rs                 # Session lifecycle management
    └── main.rs                    # CLI entry point
```

## Language Rationale

**Start TypeScript/Bun (Phase 1-3)**:
- Reuses `discord.js` + `@modelcontextprotocol/sdk` — identical protocol
- Same language as the official plugin = guaranteed compatibility
- 2-3 days to MVP

**Migrate to Rust (Phase 4)**:
- 3-5x lower memory (~40 MB vs ~120 MB)
- No GC pauses for a long-running daemon
- Fits the Agent OS stack (`core/life/`)
- `twilight-gateway` for low-level gateway control
- Integration with Lago/Arcan/Spaces infrastructure

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Proxy diverges from official plugin protocol | Pin `@modelcontextprotocol/sdk` version. E2E test: send → deliver → reply |
| Queue overflow during long spawn | Bounded queue (50 msgs). Oldest dropped. Typing indicator during spawn. |
| Dispatcher crash = all channels down | launchd watchdog restarts. Discord retains history; `fetch_messages` on reconnect |
| Race: two messages trigger spawn | Mutex on per-channel state. Only IDLE/SUSPENDED → SPAWNING allowed |
| Plugin system changes in Claude Code updates | Fallback: `DISCORD_STATE_DIR` override works regardless |

## Related

- Current bash scripts: `scripts/discord-session-manager.sh`, `scripts/discord-watchdog.sh`
- Official Discord plugin: `~/.claude/plugins/marketplaces/.../discord/server.ts`
- Slash daemon: `scripts/discord-slash-daemon.ts`
- Session config: `~/.claude/discord-sessions/config.env`
