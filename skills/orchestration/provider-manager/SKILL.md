---
name: provider-manager
category: orchestration
description: >
  Subscription account manager for macOS (Claude Code CLI & OpenAI Codex CLI, Orca, Keychain): account
  discovery, usage telemetry, machine-wide balancer that fails over without killing running sessions,
  safe switching, and browser-session re-login. Use when: inspecting quotas or which account is active,
  switching or rotating Claude or Codex accounts, re-authorizing an account, listing sessions stalled
  by a rate limit, or balancing multi-account quotas across providers. Triggers: "switch claude account",
  "switch codex account", "provider usage", "codex usage", "rate limit reached", "login headless",
  "orca credentials", "provider-manager", "stalled sessions", "subscription limit".
license: MIT
---

# Provider Manager

Claude and OpenAI Codex subscription accounts on one Mac: telemetry, balancing, and safe switching
that never kills running sessions.

## Agents: a rate limit is not yours to fix

If your turn ends on a rate limit or a usage limit, **do not run `rotate`, `switch` or
`login-headless`.** The active credential is machine-wide, and every session on the machine shares
it. The balancer gets the report through the StopFailure hook, confirms it with a probe, and, if a
healthy account exists, moves the machine to it. Your session adopts the new account in place,
within about 30 seconds and with no restart. Report it and stop:

```
ARC-STATUS: BLOCKED quota (rate limit on the active Claude account; provider-manager handles failover)
```

`rotate`, `switch` and `login-headless` are for the operator or the orchestrator. (The report reaches
the balancer only if the `StopFailure` hook is wired: see Hooks. Without it, failover waits for
readable usage numbers.)

## How a switch reaches running sessions (measured, Claude Code 2.1.280)

- Every session reads one keychain item, `Claude Code-credentials` (no live session sets
  `CLAUDE_CONFIG_DIR`). It re-reads that item before its requests, through a 30-second read cache.
  A credential written there becomes every running session's credential within about 30 s.
- A **live** credential is adopted in place: the real-binary drill shows a running session's next
  requests served by the new account, with no error. A **stale** one (a consumed refresh token) kills
  every session at its next refresh: "OAuth session expired and could not be refreshed". That was
  every observed kill (BRO-2713).

So `switch` (and every balance or failover, which go through it):

1. holds the machine-wide balancer lock (one provider-manager action at a time; every refresh this
   tool makes also needs that lock, and re-reads the store first);
2. refuses to write a target it cannot prove live: it refreshes the target through its own copy
   (proving the refresh token is unspent, and persisting the new pair first), then checks that the
   new access token's profile names that account (email and org must agree);
3. saves the outgoing account's live tokens to its Orca item first, and reads them back. Claude
   Code rotated them since the last switch, and without this, switching back later would be unsafe;
4. holds Claude Code's own refresh lock while it rewrites the store item (a lock left by a dead
   process is reclaimed after 60 s, as Claude Code does). It changes only `claudeAiOauth`; mcpOAuth,
   Linear's included, is written back as read. The other item name (the mirror) is never written:
   one refresh chain must not sit in two items;
5. fails closed: an unreadable store, a store that changed mid-switch, or an unidentifiable store
   credential stops the switch with the store unchanged. A write that cannot be read back is
   recorded as `switch.unverified`, and the cooldown still applies.

This tool never refreshes a refresh token that a store item holds. That refresh token belongs to
Claude Code, and spending it would kill every session. The unscoped item is always protected. A
scoped mirror is protected whenever a running Claude Code process is configured to read it.

## The balancer

The hooks (every session) only *kick*: they start `balance --auto` detached, at most once per
evaluation interval (120 s). That process takes the balancer lock, so one evaluation runs however
many sessions kick. It switches only when:

- **balance:** the active account's readable 5-hour use is at or over 90% (or 7-day ≥ 97%), a
  standby is at or under 70% and at least 25 points lower, and the last switch was over 30 minutes
  ago; or
- **failover:** the active account is limited by readable numbers, or a session reported a rate
  limit (StopFailure), **and** a real probe confirms it. The probe is one tiny `claude -p` on the live
  store and the sessions' model, with no hooks, tools or MCP. The minimum gap is 5 minutes. A report
  stays pending (up to 15 minutes) until an evaluation can act on it; every evaluation drops reports
  older than that from the state. A session that reported
  `authentication_failed` triggers the same failover when the probe shows Claude Code itself cannot
  refresh the store's credential.
- **never on its own:** a store left empty (`/logout`) is not refilled. On a Claude Code version
  other than the measured ones (2.1.280, and 2.1.295 by the drill), automatic switching is observe-only (`would_switch`,
  `version_unverified`, shown in the session-start line and `usage`) until the drill is re-run and
  the version added (`verifiedClaudeVersions`). An account the probe confirmed limited is not a
  failover target for an hour.
- **Codex balancing:** see "Codex accounts" below.

Telemetry that cannot be read is never a rate limit. The usage endpoint answering 429 means
`throttled`: the last numbers are kept, marked stale, and the endpoint is not called again until the
backoff ends (`Retry-After`, at least 1 minute and at most 6 hours; without it 2, 4, 8, 16, then 30
minutes). The backoff is persisted, so no kick reaches the endpoint inside it. `usage` shows the age of
the last good numbers and when the next try is (`THROTTLED (numbers 139m old, next try in 41m)`); past
`staleNumbersMinutes` (30) the balancer says so in its decision (`telemetryNote`): balancing on numbers
waits, and a StopFailure report still fails over once the probe confirms it. An expired token means
`auth_expired`. A dead grant means `needs_login`: its refresh token is spent once, then skipped until
a login, a switch or Orca writes new tokens. None of these switches anything, and a standby with any
of them is not a candidate. Tool output (a GitHub API limit, a site's 429) is never read as a Claude
limit.

## Codex accounts (measured 2026-10-19)

Two limits shape everything here:

- **One live Codex CLI seat at a time.** Logging one account into the Codex CLI revoked the other
  account's saved copy within minutes (its usage call then answers 401 `token_revoked`). A saved
  standby is therefore usually dead, and moving the CLI to another account is a browser re-login,
  which in turn revokes the seat it replaces.
- **One shared workspace.** devteam@ and carlos@ are two users of one ChatGPT Team workspace (one
  `chatgpt_account_id`). "Workspace out of credits" is shared: switching seats cannot fix it. Only the
  per-user 5-hour window benefits from a switch.

What the balancer does with that:

- Every evaluation and every `usage` call snapshots `~/.codex/auth.json` into its account's keychain
  copy when the two differ, so a raw `codex login` (which writes only auth.json) leaves a saved copy.
  The snapshot never refreshes anything. No refresh ever spends a refresh token auth.json holds: it
  belongs to the running CLI, and OpenAI rotates refresh tokens on use.
- A copy answering `token_revoked` is marked `revoked` (a refresh refused with `invalid_grant` is
  `needs_login`). That grant is not sent to the usage or token endpoint again until new tokens replace it.
- It moves the CLI when the active account is limited (readable numbers only: a usage 429 is
  `throttled`, never a limit) or over the 5-hour/7-day thresholds, to a live standby that is under
  `standbyMax` and, for a balance, `margin` points lower. While the active seat is out of workspace
  credits, a standby in the same workspace, or of unknown workspace (no saved copy), is never a
  candidate and is never re-logged in; only one known to be in another workspace is.
- With no live standby (the usual case), it re-logs in a standby whose grant is proven dead
  (`revoked`, `needs_login`) or that has no copy. A transient failure (network, a busy lock, a copy
  that changed or could not be read, a 401 without a revocation code) never starts a re-login, because
  a re-login revokes the live seat. The re-login runs through Arc, with `prompt=login`
  forcing OpenAI's account chooser (without it, the Arc space's own web session is signed in, whoever
  that is) in the account's `arcSpace` (default `Stimulus`). A short AppleScript check runs first and
  reports "Arc not answering AppleScript" (a pending permission prompt hangs Arc) or "Arc is not
  running" instead of hanging. A failed re-login is not retried for `cooldownMinutes`.
- Every outcome, holds included, is a `codex.balance.decision` event with its reason, and
  `usage --provider codex` shows why each standby is not a candidate (the STANDBY column).

Configuration: `~/.config/broomva/provider-manager.json` (keys: `autoBalance`, `threshold`,
`weeklyThreshold`, `standbyMax`, `margin`, `cooldownMinutes`, `failoverMinGapMinutes`,
`evalIntervalSeconds`, `probeTtlSeconds`, `probeModel`, `versionGate`, `verifiedClaudeVersions`,
`staleNumbersMinutes`, `codexAccounts`). Set `"autoBalance": false` to log `would_switch` and never
switch automatically. `codexAccounts` names the Arc space each Codex account re-logs in from:
`{"codexAccounts": {"carlos@getstimulus.ai": {"arcSpace": "Carlos"}}}`.

## Commands

All commands accept `--provider {claude,codex,all}` (default: `claude`):

```bash
PM=~/.agents/skills/provider-manager/scripts/provider_manager.py

# Claude commands (default)
python3 $PM list                       # Claude accounts; active store vs Keychain copies
python3 $PM usage [--force]            # 5h/7d per Claude account, with status (OK, THROTTLED, NEEDS_LOGIN...)
python3 $PM state                      # balancer lock, cooldown, hold, health, backoff
python3 $PM history [--all]            # switches (or every decision, refusal and probe)
python3 $PM stalled [--hours 24]       # sessions whose turn ended on a rate limit/auth error, for resume
python3 $PM hold --minutes 30          # pause automatic switching (--clear to resume)
python3 $PM balance [--dry-run]        # evaluate Claude balance now
python3 $PM switch team@company.com    # safe Claude switch; --force discards unidentifiable credential
python3 $PM rotate [--force]           # failover now (orchestrator); probe-confirmed unless --force
python3 $PM login-headless --email X   # re-login X from browser session; --force: over unidentifiable credential

# OpenAI Codex commands
python3 $PM list --provider codex                    # Codex accounts (devteam, carlos) & active store
python3 $PM status --provider codex                  # active Codex auth mode, email, plan, token freshness
python3 $PM usage --provider codex [--force]         # 5h/7d Codex utilization, status, why a standby is not a candidate
python3 $PM switch --provider codex devteam@...      # Codex switch: saves the outgoing seat; a dead target is re-logged in via Arc
python3 $PM balance --provider codex [--dry-run]     # evaluate Codex balance (5h threshold / credits depleted)
python3 $PM login-headless --provider codex [--email X] [--space S] # Codex re-login via Arc (account chooser forced)

# Multi-provider aggregate commands
python3 $PM usage --provider all       # display both Claude Code and OpenAI Codex telemetry
python3 $PM status --provider all      # inspect authentication across both providers
python3 $PM list --provider all        # list managed accounts across both providers
python3 $PM balance --provider all     # evaluate and balance both Claude and Codex accounts
```

`login-headless` for Claude accounts renews via browser cookies in Arc/Chrome without GUI interaction.
For OpenAI Codex, `switch` and `login-headless` drive `codex login` through an Arc space: the account
chooser (forced with `prompt=login`) and the consent page are clicked through, and the new auth.json is
snapshotted. The target must be signed in to that space's OpenAI web session. Because only one CLI seat
is live, every such login revokes the other account's saved copy.

## Hooks

`scripts/provider_manager_hook.py <event>`: `session-start` (one status line on stderr from the
cache, then a kick), `prompt-submit` (a kick), `stop-failure` (records the stalled session; on
`rate_limit` or `authentication_failed`, queues a probe-confirmed failover), `post-tool-use` (does nothing, on purpose). It
writes nothing to stdout, does no network I/O, and always exits 0.

**The `StopFailure` entry is a prerequisite for report-driven failover.** Claude Code runs StopFailure
hooks only when they are configured. Without the entry, a rate limit reaches the balancer only through
readable usage numbers on a later prompt's evaluation. The wiring is in
[references/architecture.md](references/architecture.md#hook-wiring).

## Tests and proof

- `tests/test_kill_paths.py`: each observed kill or false rotation, end to end, with a running
  session modelled on the binary. K1–K15 fail against the code before BRO-2713 (`PM_IMPL_DIR=...`),
  K16 (the auth.json snapshot never spends the Codex CLI's refresh token) against the code before
  BRO-3192; here all pass.
- `tests/mutation_check.py`: each guard disabled in a scratch copy turns its tests red.
- `tests/drill/drill.py`: the real `claude` binary in a sandboxed scratch HOME (no keychain, network
  only to a local stub), with a switch made between two of its requests. Its `probe` scenario runs
  the probe through the real binary and checks how its output is classified.

## References

* [references/architecture.md](references/architecture.md): storage layout, what Claude Code does with
  the store, the switch protocol, events, hook wiring.
* [references/rotation-playbook.md](references/rotation-playbook.md): what to do on a rate limit
  (agents, orchestrator, operator).
