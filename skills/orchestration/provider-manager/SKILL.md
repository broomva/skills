---
name: provider-manager
category: orchestration
description: >
  Subscription account manager for macOS (Claude Code CLI, OpenAI Codex CLI, Antigravity ACP, Orca, Keychain): account
  discovery, usage telemetry (Grok too, read-only), machine-wide balancer that fails over without killing running sessions,
  safe switching, and browser-session re-login. Use when: inspecting quotas or which account is active,
  switching or rotating Claude or Codex accounts, re-authorizing an account, listing sessions stalled
  by a rate limit, or balancing multi-account quotas across providers. Triggers: "switch claude account",
  "switch codex account", "provider usage", "codex usage", "rate limit reached", "login headless",
  "orca credentials", "provider-manager", "stalled sessions", "subscription limit", "grok usage".
license: MIT
---

# Provider Manager

Claude, OpenAI Codex and Antigravity ACP subscription accounts on one Mac: telemetry, balancing, and safe switching
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
waits, and a StopFailure report still fails over once the probe confirms it. When a backoff ends,
exactly one process gets the retry (a 60-second claim taken under the state lock), and a login clears
that account's backoff.

The endpoint can refuse the **active** account for hours: every Claude Code session on that account
calls it too, so the budget is gone before the one retry per window lands (BRO-3405: 429 with
`Retry-After: 3600` six hours running). The probe's own response carries the same two windows, so
while the endpoint refuses the active account, the balancer refreshes its numbers from one probe each
time they reach half of `staleNumbersMinutes`: `OK (via probe, numbers 3m old, endpoint throttled,
next try in 41m)`. Probe numbers are never held past `staleNumbersMinutes`, never taken for a standby,
and dropped if the store changed hands while the probe ran. An expired token means
`auth_expired`. A dead grant means `needs_login`: its refresh token is spent once, then skipped until
a login, a switch or Orca writes new tokens. None of these switches anything, and a standby with any
of them is not a candidate. Tool output (a GitHub API limit, a site's 429) is never read as a Claude
limit.

## Codex accounts (BRO-3346)

Codex uses **a concrete home per account generation**. `switch --provider codex` changes the
selection for new sessions; it never replaces an existing home's `auth.json`. Existing sessions
keep their account, including across workspaces. A late refresh writes only its original home.

- `codex login` first logs out and revokes the account its `CODEX_HOME` holds
  (`clear_existing_auth_before_login` → `logout_with_revoke`, Codex 0.163.0). The former
  "one live seat" limit was this login behavior, not an OpenAI account limit. Every managed login
  runs in an empty scratch home with the file store forced. Its email is checked before publication.
- Homes and the private atomic registry live under `~/.local/share/broomva/codex/` (override:
  `PROVIDER_MANAGER_CODEX_ROOT`). Reauthorizing an account creates a **new generation**, preserving
  its prior home for existing sessions. Reauthorizing the selected account selects its new generation.
  Logging in a new email registers it, so it remains selectable after another account is selected.
- The existing `~/.codex` home (`CODEX_AUTH_PATH` override) is adopted **in place**. Its grant is
  never copied into another live home. Existing sessions keep using it; nothing restarts them.
- Managed homes are the authoritative credentials. Telemetry reads each home's latest access token;
  provider-manager never refreshes a managed grant, including an inactive account's. Its Codex
  sessions own refresh. An expired access token may make telemetry unreadable until Codex renews it;
  unreadable numbers never justify automatic switching. Keychain copies are bootstrap/backup data.
- Switching to an account without a home first refreshes its saved standby copy (never a grant owned
  by a home) or re-logs it in if proven dead, then publishes a home and selects it. All outcomes are
  `codex.balance.decision` events. Usage thresholds, cooldown, Arc chooser and telemetry guards apply.
- devteam@ and carlos@ share one Team workspace; changing user cannot restore exhausted workspace
  credits. team@ is a Pro account in another workspace and can help in that case.

### Session launchers

Install the separate launcher, preserving the real vendor executable:

```bash
python3 "$PM" codex-launcher --binary /absolute/path/to/real/codex
python3 "$PM" codex-home                  # selected concrete home
```

Set T3's Codex **Binary path** and Paseo's `agents.providers.codex.command` to the printed launcher.
Do not replace the vendor executable or set `CODEX_HOME` to a mutable `current` symlink.
The wrapper pins direct sessions, forces file credentials, and rejects credential-changing login/logout
(read-only login status remains available);
use `login-headless` for reauthorization. New homes copy config/instructions and share skills/rules;
auth, databases and native session history are separate. Existing homes are retained.

Paseo pins `PASEO_AGENT_ID` to its first home. The app-server proxy records native thread IDs and
routes thread/turn RPCs to their original account child; new thread/start requests use current selection.
It supports T3 sharing one server across threads; the provider account/usage display follows selection,
while every thread continues receiving its own account's events. native threads predating installation resume in the
legacy home. Multiple account children stay alive concurrently; server-originated permission IDs are namespaced. This prevents
an app-server restart from silently moving an existing thread to the latest selection.

A retained generation with a revoked grant can be recovered without moving its thread IDs:

```bash
python3 "$PM" login-headless --provider codex --email EMAIL --repair-home /absolute/retained/home
```

Repair requires the usage endpoint to confirm `token_revoked` for that exact home before login;
expiry, an unreadable endpoint, or a grant that changed during the browser flow refuses repair.
The fresh login grant is written **only** into the confirmed-dead home, preserving native history.
Ordinary reauthorization publishes a new generation and leaves healthy old sessions alone.

`scripts/pm_codex_integrations.py paseo --config PATH --launcher PATH` emits a candidate Paseo
config preserving other settings; apply privately, then `paseo daemon reload --json`.
The `t3 --binary REAL` command alternatively emits create-only per-generation provider-instance
requests for T3's native settings client. Those fixed instances are useful for an explicit account
picker; the selection launcher handles automatic selection. Existing provider defaults are preserved.

Configuration: `~/.config/broomva/provider-manager.json` (keys: `autoBalance`, `threshold`,
`weeklyThreshold`, `standbyMax`, `margin`, `cooldownMinutes`, `failoverMinGapMinutes`,
`evalIntervalSeconds`, `probeTtlSeconds`, `probeModel`, `versionGate`, `verifiedClaudeVersions`,
`staleNumbersMinutes`, `codexAccounts`). Set `"autoBalance": false` to log `would_switch` and never
switch automatically. `codexAccounts` names the Arc space each Codex account re-logs in from:
`{"codexAccounts": {"carlos@getstimulus.ai": {"arcSpace": "Carlos"}}}`.

## Commands

All commands accept `--provider {claude,codex,antigravity,grok,all}` (default: `claude`; `grok` takes only `list`, `status` and `usage`):

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
python3 $PM list --provider codex                    # Codex accounts (devteam, carlos, team) & active store
python3 $PM status --provider codex                  # active Codex auth mode, email, plan, token freshness
python3 $PM usage --provider codex [--force]         # 5h/7d Codex utilization, status, why a standby is not a candidate
python3 $PM switch --provider codex devteam@...      # Codex selection: new sessions use this account; existing sessions retain theirs
python3 $PM balance --provider codex [--dry-run]     # evaluate Codex balance (5h threshold / credits depleted)
python3 $PM login-headless --provider codex [--email X] [--space S] # Codex login via Arc into X's saved copy; the CLI stays put

# Multi-provider aggregate commands
python3 $PM usage --provider grok [--force] [--json] # Grok: weekly window %, reset, tier, status (read-only)
python3 $PM usage --provider all       # Claude Code, OpenAI Codex, Antigravity and Grok telemetry
python3 $PM status --provider all      # inspect authentication across both providers
python3 $PM list --provider all        # list managed accounts across both providers
python3 $PM balance --provider all     # evaluate and balance both Claude and Codex accounts
```

`login-headless` for Claude accounts renews via browser cookies in Arc/Chrome without GUI interaction.
For OpenAI Codex, `switch` and `login-headless` drive `codex login` through an Arc space, in an empty
scratch `CODEX_HOME` (file credential store forced): the account chooser (forced with `prompt=login`)
and the consent page are clicked through, and the scratch auth.json is saved as the account's copy,
then deleted. `~/.codex` is never touched by a login, so nothing is revoked. `login-headless` leaves the
selected account unchanged unless it is being reauthorized or none is selected; `switch` selects a home. The target must be signed in to that
space's OpenAI web session.

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

## Antigravity accounts (BRO-3349)

Antigravity **ACP** accounts use separate concrete file profiles. This is distinct from Gemini CLI
and the native Antigravity desktop/Go CLI's shared Keychain login. Those global logins are not swapped.

1. Sign in each account through a fresh native T3 Antigravity instance. Its private profile is
   `~/.t3/userdata/providers/antigravity/<sha256(instance-id)>`. Register that profile **in place**:
   `python3 "$PM" antigravity-register --email EMAIL --profile ABSOLUTE_PROFILE --binary ABSOLUTE_ACP_BINARY`.
   Identity and quota must verify before registration; no grants are copied. Fresh official ACP
   `initialize` + `authenticate(methodId=oauth-personal)` is also supported for a new concrete profile.
2. `python3 "$PM" antigravity-launcher` installs a separate launcher. Create a **new local ACP**
   T3 provider instance using its printed path, `authMethodId: oauth-personal`, and explicit custom
   model IDs from the native Antigravity provider. Preserve existing native instances as overrides.
3. Select this new provider for managed threads. Native Antigravity instances keep their fixed
   account; existing native conversations are not migrated. The launcher obtains the host thread
   identity through T3's supported MCP bootstrap, atomically pins its first account, then execs the
   official ACP binary unchanged. Resume uses the saved pin. Missing context, imported/history-bearing
   conversations without a pin, and forks fail closed. Discovery probes lack thread context and show
   a warning; configured custom models remain available. The launcher intentionally refuses direct
   non-T3 use without a stable supported host context.

Commands: `list`, `status`, `usage`, `balance [--dry-run]`, and `switch EMAIL` accept
`--provider antigravity`. Aggregate `--provider all` includes Antigravity. These commands currently
emit sanitized JSON for this provider. `balance --auto` and new-session selection honor the shared
`autoBalance` setting. A manual switch without `--model` updates every family selection; `--model gemini-4-argon-high`
or `--model claude` targets one family. Balance accepts the same option; omitted, it evaluates
the conservative all-family route used for unknown models. Use `balance --provider antigravity
--model gemini` or `--model claude` to explicitly update a known-model family selection.
Model-specific new threads automatically evaluate their own independent Gemini /
shared-third-party selections.

Each launch refreshes telemetry at most once per five minutes. Readings older than 30 minutes,
identity errors, missing applicable quotas and unknown amounts are ineligible. Disabled buckets are
inapplicable, rather than zero usage. Both official quota endpoints merge conservatively. Selection
changes when current use is at least 90%, a standby is at most 70% and 25 points lower, with a
30-minute cooldown. Unknown models require both families. A bucket's actual reset/cadence is retained.
Provider quota summaries are telemetry, not a guarantee that an inference request will succeed;
a runtime rejection may differ from the displayed quota. There is no automatic runtime-error replay
or migration of an existing conversation to another account.

Only the verified **ACP 1.3.0 darwin-arm64** executable and matching harness hashes are accepted.
Its initialize response supports load/resume and does not advertise fork. An upgrade requires a new
contract check before adding hashes. Registry/pins live privately under
`~/.local/share/broomva/antigravity` (`PROVIDER_MANAGER_ANTIGRAVITY_ROOT` override).
The fingerprint binds the native grant and project, ignoring access-token/serialization metadata.
Native ACP refresh owns its profile; telemetry uses Google's documented refresh exchange, never
writes native credentials, and permanently refuses a grant if unexpected refresh-token rotation
is returned. Reauthorization must use a new profile; registered profiles are immutable. Sign in through a
**fresh native T3 instance ID**, then run `antigravity-register` with the same email and new profile.
This publishes an immutable account generation and makes it the latest for new sessions. Existing
pins retain their original generation, including across subsequent registrations. Re-registering
a retained profile is idempotent and does not roll the latest generation backward. Never sign in
over a registered profile. V1 registries migrate atomically, preserving selections and pin ownership.
Existing pins refuse altered grants/runtimes instead of silently changing identity.

## Grok usage (BRO-3466)

There is one xAI account (`~/.grok/auth.json`, written only by the grok CLI), so Grok has **no
balancing, switching or login** here: `list`, `status` and `usage` with `--provider grok` are
read-only, and `--provider all` includes it. Anything else with `--provider grok` is refused.

The numbers come from the endpoint behind grok 1.0.70's own billing pane, found in the binary and
measured on 2026-10-24: `GET https://cli-chat-proxy.grok.com/v1/billing?format=credits` (the plan's
`currentPeriod` and `creditUsagePercent`, which was weekly at the time, plus per-product percents) and `/user?include=subscription`
(the email, which must match auth.json, and `subscriptionTier`). Both use the CLI's OIDC access token as a
bearer, with redirects refused. Status is `OK`, `LIMITED` (the window or any product in it is at 100% or more, or the account is blocked),
`NEEDS_LOGIN` (no login, or the token was rejected) or `UNAVAILABLE`. A status other than OK or LIMITED prints
`telemetry unavailable: <reason>`. An expired access token is reported, not refreshed. Any grok run, for example
`grok models`, refreshes it. Readings are cached for 60 s in `~/.cache/broomva-provider-grok/usage.json`
(`--force` re-reads). After a failed read the last good numbers appear only as `lastKnown`, with their age,
and never as current. An unreadable percent is never a zero, and a response the parser does not understand is
`invalid_response`, so it never takes down `--provider all`.
