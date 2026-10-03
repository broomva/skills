---
name: provider-manager
category: orchestration
description: >
  Claude subscription account manager for macOS (Claude Code CLI, Orca, Keychain): account
  discovery, usage telemetry, one machine-wide balancer that fails over without killing running
  sessions, safe switching, and browser-session re-login. Use when: inspecting quotas or which
  account is active, an operator or orchestrator switching or rotating accounts, re-authorizing an
  account, listing sessions stalled by a rate limit, or pausing automatic switching. An agent that
  hits a rate limit does NOT rotate: the balancer handles it. Triggers: "switch claude account",
  "provider usage", "rate limit reached", "login headless", "orca credentials", "provider-manager",
  "stalled sessions", "subscription limit".
license: MIT
---

# Provider Manager

Claude subscription accounts on one Mac: telemetry, one balancer, and a switch that never kills a
running session.

## Agents: a rate limit is not yours to fix

If your turn ends on a rate limit or a usage limit, **do not run `rotate`, `switch` or
`login-headless`.** The active credential is machine-wide, and every session on the machine shares
it. The balancer gets the report through the StopFailure hook, confirms it with a probe, and, if a
healthy account exists, moves the machine to it. Your session adopts the new account in place,
within about 30 seconds and with no restart. Report it and stop:

```
ARC-STATUS: BLOCKED quota (rate limit on the active Claude account; provider-manager handles failover)
```

`rotate`, `switch` and `login-headless` are for the operator or the orchestrator.

## How a switch reaches running sessions (measured, Claude Code 2.1.280)

- Every session reads one keychain item, `Claude Code-credentials` (no live session sets
  `CLAUDE_CONFIG_DIR`). It re-reads that item before its requests, through a 30-second read cache.
  A credential written there becomes every running session's credential within about 30 s.
- A **live** credential is adopted in place: the real-binary drill shows a running session's next
  requests served by the new account, with no error. A **stale** one (a consumed refresh token) kills
  every session at its next refresh: "OAuth session expired and could not be refreshed". That was
  every observed kill (BRO-2713).

So `switch` (and every balance or failover, which go through it):

1. holds the machine-wide balancer lock (exactly one provider-manager action at a time);
2. refuses to write a target it cannot prove live: near expiry, it is refreshed through its own copy
   first, then its access token must pass a profile check that names that account;
3. saves the outgoing account's live tokens to its Orca item first (Claude Code rotated them since
   the last switch), so switching back later is safe;
4. holds Claude Code's own refresh lock while it rewrites the store, and changes only
   `claudeAiOauth` in each item (mcpOAuth, Linear's included, is never touched);
5. fails closed: an unreadable store, a store that changed mid-switch, or an unidentifiable store
   credential stops the switch with the store unchanged.

This tool never refreshes the credential the store holds. That refresh token belongs to Claude Code;
spending it would kill every session.

## The balancer

The hooks (every session) only *kick*: they start `balance --auto` detached, at most once per
evaluation interval (120 s). That process takes the balancer lock, so one evaluation runs however
many sessions kick. It switches only when:

- **balance:** the active account's readable 5-hour use is at or over 90% (or 7-day ≥ 97%), a
  standby is at or under 70% and at least 25 points lower, and the last switch was over 30 minutes
  ago; or
- **failover:** the active account is limited by readable numbers, or a session reported a rate
  limit (StopFailure), **and** a real probe confirms it. The probe is one tiny `claude -p` on the live
  store, with no hooks, tools or MCP. The minimum gap is 5 minutes.

Telemetry that cannot be read is never a rate limit. The usage endpoint answering 429 means
`throttled` (back off, keep the last numbers marked stale). An expired token means `auth_expired`. A
dead grant means `needs_login`. None of these switches anything, and a standby with any of them is
not a candidate. Tool output (a GitHub API limit, a site's 429) is never read as a Claude limit.

Configuration: `~/.config/broomva/provider-manager.json` (keys: `autoBalance`, `threshold`,
`weeklyThreshold`, `standbyMax`, `margin`, `cooldownMinutes`, `failoverMinGapMinutes`,
`evalIntervalSeconds`, `probeTtlSeconds`). Set `"autoBalance": false` to log `would_switch` and never
switch automatically.

## Commands

```bash
PM=~/.agents/skills/provider-manager/scripts/provider_manager.py
python3 $PM list                       # accounts; which one the store holds, and how we know
python3 $PM usage [--force]            # 5h/7d per account, with telemetry status (OK, THROTTLED, NEEDS_LOGIN...)
python3 $PM state                      # balancer lock, cooldown, hold, health, backoff
python3 $PM history [--all]            # switches (or every decision, refusal and probe)
python3 $PM stalled [--hours 24]       # sessions whose turn ended on a rate limit/auth error, for resume
python3 $PM hold --minutes 30          # pause automatic switching (--clear to resume)
python3 $PM balance [--dry-run]        # evaluate now (operator)
python3 $PM switch team@company.com    # safe switch (operator); --force discards an unidentifiable store credential
python3 $PM rotate [--force]           # failover now (orchestrator); probe-confirmed unless --force
python3 $PM login-headless --email X   # re-login X from a browser session (see below)
```

`login-headless` for an account the store does not hold runs `claude auth login` in a throwaway
config dir: only that account's Orca copy is renewed, and nothing switches. Follow it with `switch`
if you want that account active. For the account the store holds, it renews the live store, and
running sessions adopt the fresh grant.

## Hooks

`scripts/provider_manager_hook.py <event>`: `session-start` (one status line on stderr from the
cache, then a kick), `prompt-submit` (a kick), `stop-failure` (records the stalled session; on
`rate_limit`, queues a probe-confirmed failover), `post-tool-use` (does nothing, on purpose). It
writes nothing to stdout, does no network I/O, and always exits 0. The wiring, including the
`StopFailure` entry, is in [references/architecture.md](references/architecture.md#hook-wiring).

## Tests and proof

- `tests/test_kill_paths.py`: each observed kill or false rotation, end to end, with a running
  session modelled on the binary. Against origin/main (`PM_IMPL_DIR=...`) all 13 fail; here all pass.
- `tests/mutation_check.py`: each guard disabled in a scratch copy turns its tests red.
- `tests/drill/drill.py`: the real `claude` binary in a sandboxed scratch HOME (no keychain, network
  only to a local stub), with a switch made between two of its requests.

## References

* [references/architecture.md](references/architecture.md): storage layout, what Claude Code does with
  the store, the switch protocol, events, hook wiring.
* [references/rotation-playbook.md](references/rotation-playbook.md): what to do on a rate limit
  (agents, orchestrator, operator).
