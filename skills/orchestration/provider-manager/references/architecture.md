# Provider Manager Architecture Reference

## Overview

`provider-manager` orchestrates multi-account credentials between two layers:
1. **Orca Application**: Desktop app multi-account profile manager.
2. **Claude Code CLI**: Terminal agent environment (`claude`).
3. **Claude Web / Browser Sessions**: Arc & Chrome session extraction for zero-touch re-authentication.

```
                  ┌───────────────────────────────────────────┐
                  │          Arc / Chrome Browser             │
                  │   Profile 3 (Stimulus) / Default / etc.   │
                  │   sessionKeyV3 (Cookie in SQLite DB)      │
                  └─────────────────────┬─────────────────────┘
                                        │ Keychain Decryption
                                        ▼ (Arc Safe Storage)
┌───────────────────────┐      ┌──────────────────────────────┐
│  Orca Desktop App     │◄────►│     provider-manager         │
│  orca-data.json       │      │   Autonomous Orchestrator    │
│  Keychain Credentials │      └──────────────┬───────────────┘
└───────────────────────┘                     │
                                              ▼
                               ┌──────────────────────────────┐
                               │       Claude Code CLI        │
                               │  ~/.claude.json              │
                               │  Keychain (Scoped & Fallback)│
                               └──────────────────────────────┘
```

---

## 1. Storage & Credential Layout

### A. Orca Configuration
* **Catalog File**:
  `~/Library/Application Support/orca/profiles/local-default/orca-data.json`
* **Schema**:
  ```json
  {
    "settings": {
      "activeClaudeManagedAccountId": "5f5c518b-5edb-48a0-b2cd-8bce8a72f346",
      "claudeManagedAccounts": [
        {
          "id": "82259891-9233-4751-a0e5-68887399f4c4",
          "email": "dev@example.com",
          "organizationUuid": "65def83d-0861-4043-9e38-06b9c58fcd08",
          "organizationName": "dev@example.com's Organization",
          "lastAuthenticatedAt": 1784821057205
        },
        {
          "id": "5f5c518b-5edb-48a0-b2cd-8bce8a72f346",
          "email": "team@example.com",
          "organizationUuid": "4e16b260-4551-4cf0-a415-e9f9e1876c4e",
          "organizationName": "team@example.com's Organization",
          "lastAuthenticatedAt": 1790440188000
        }
      ]
    }
  }
  ```
* **Orca Keychain Entry**:
  * **Service**: `Orca Claude Code Managed Credentials`
  * **Account**: `<account-id-uuid>`
  * **Value**: JSON string containing `{ "claudeAiOauth": { "accessToken": "...", "refreshToken": "...", "expiresAt": ... } }`

---

### B. Claude Code Runtime State
* **Config File**: `~/.claude.json`. Its `oauthAccount` block (`emailAddress`, `organizationUuid`, ...) is
  last-writer-wins across processes: a display hint, never the truth about which account is active.
* **Credential store (keychain)**, as Claude Code 2.1.280 names it:
  * `Claude Code-credentials` when `CLAUDE_CONFIG_DIR` is unset. **This is the item every live session
    reads.** Verified 2026-10-02: no running `claude` process sets `CLAUDE_CONFIG_DIR`, and this item's
    mdat follows the sessions' refreshes.
  * `Claude Code-credentials-<sha256(config dir)[:8]>` when `CLAUDE_CONFIG_DIR` is set (`d098dafb` for
    `~/.claude`). Old provider-manager versions also wrote this item (the "mirror"); this version never
    writes it.
  * `CLAUDE_SECURESTORAGE_CONFIG_DIR` overrides both. Account: `$USER`.
  * Value: JSON (hex when written with `-X`) holding `claudeAiOauth` (Claude's access/refresh tokens,
    `expiresAt`, scopes) and `mcpOAuth` (MCP servers' OAuth: Linear, Slack, Sentry...).
* **Write invariant**: a switch replaces `claudeAiOauth` in the primary item only, and writes the
  item's other keys back exactly as it read them (read twice, written only if both reads agree, under
  Claude Code's refresh lock). MCP tokens are never copied between items or from an Orca copy. The
  old cross-item merge let the stale mirror's Linear tokens overwrite the live ones (D28).

### D. OpenAI Codex Storage & Credentials
* **Homes and selection**: `~/.local/share/broomva/codex/accounts.json` maps email → immutable
  generation home and contains the selected email. Registry writes are atomic and mode 0600;
  directories and generation homes are mode 0700. `PROVIDER_MANAGER_CODEX_ROOT` overrides the root.
* **Legacy adoption**: `~/.codex/auth.json` (or `CODEX_AUTH_PATH`) remains in its existing home,
  registered in place. Never duplicate the running CLI's grant into another home.
* **Credential ownership**: each generation's `auth.json` belongs to its Codex sessions. Registry
  selection never writes an auth file. Explicit repair is restricted to an authority-confirmed revoked
  grant and writes its fresh independent login grant to that one dead home only. Telemetry reads home credentials before Keychain copies,
  and never refreshes a managed grant. A standalone saved copy can be refreshed only before its
  first home is published. Keychain service remains `Orca Codex Managed Credentials`.
* **Login**: `codex login` revokes whatever its home holds, so every browser login runs in an empty
  scratch home with `cli_auth_credentials_store="file"`. Check returned email, persist a Keychain
  backup, publish a new generation home, register it, and clean up the scratch directory.
  Reauthorizing the selected account selects the new generation. Ordinary login never overwrites old homes. Explicit confirmed-revoked-home repair retains its history and pins.
* **Race eliminated**: Codex 0.163's token refresh can finish after a file swap and overwrite the
  target, or rotate between snapshot and backup. A re-read/CAS in provider-manager cannot serialize
  with the CLI's private semaphore. Separate homes remove the shared auth-file write instead.
* **Launcher**: resolves a concrete home once; overrides `CODEX_HOME`, forces file credentials and
  execs the explicit real executable. Paseo agent IDs and native app-server thread IDs retain home
  pins on resume. The proxy routes each thread/turn to an account child, including read/archive RPCs;
  thread/start resolves current selection even in T3's shared provider session. Server-originated request
  IDs are namespaced so approval replies reach the originating child. Unmapped legacy threads resume
  in the legacy home. Credential-changing login/logout through the launcher are refused; reauthorization must publish a new generation.
* **Shared files**: new homes copy config.toml (root file-store setting forced), managed config and
  AGENTS.md, and symlink skills/rules/prompts directories. Auth, databases, logs, and session state
  stay local to the generation. Nothing deletes retained generations automatically.
* **Workspace credits**: devteam@ and carlos@ share Team credits; team@ is in another workspace.
  The balancer skips same/unknown-workspace candidates when the selected workspace is exhausted.
* **Health**: per-grant fingerprints retain revoked/needs_login marks; fresh login generations clear
  them. Transient network or telemetry failures never start browser login.
* **OAuth Refresh**:
  * Endpoint: `https://auth.openai.com/oauth/token`
  * Client ID: `app_EMoamEEZ73f0CkXaXp7hrann`
  * Body: `{"grant_type": "refresh_token", "client_id": "...", "refresh_token": "..."}`
* **Telemetry**:
  * Endpoint: `https://chatgpt.com/backend-api/wham/usage`
  * Header: `ChatGPT-Account-ID: <account_id>`, `Authorization: Bearer <access_token>`
  * Returns: 5-hour primary window, 7-day secondary window, credits balance, and rate limit reset credits.

---

## 2. Autonomous Headless OAuth Flow

When an account's refresh token has expired or credentials need initial setup without a physical display:

1. **Session Cookie Extraction**:
   * Reads SQLite cookie database from Arc (`~/Library/Application Support/Arc/User Data/Profile 3/Cookies`) or Google Chrome.
   * Retrieves the browser master password from macOS Keychain (`Arc Safe Storage` or `Chrome Safe Storage`).
   * Decrypts cookies using `PBKDF2-SHA1` (1003 iterations, 16-byte key) + `AES-128-CBC`.
   * Verifies valid `sessionKeyV3` or `sessionKey` against `https://claude.ai/api/bootstrap`.

2. **PKCE Flow Registration**:
   * `claude auth login --claudeai --email <target>` generates a standard PKCE authorization URL:
     `https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c250a-e61b-44d9-88ed-5944d1962f5e&...&state=<state>&code_challenge=<challenge>`
   * The script performs a GET request following 307 redirects to register the session on Claude's auth backend.

3. **Autonomous Approval API**:
   * Sends an authenticated POST request to:
     `https://claude.ai/v1/oauth/${organization_uuid}/authorize`
   * Headers: Includes extracted cookies + `Origin: https://claude.ai` + `Referer: https://claude.ai/oauth/authorize`.
   * Body:
     ```json
     {
       "response_type": "code",
       "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
       "organization_uuid": "<target-org-uuid>",
       "redirect_uri": "https://platform.claude.com/oauth/code/callback",
       "scope": "user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload user:plugins",
       "state": "<state>",
       "code_challenge": "<code_challenge>",
       "code_challenge_method": "S256"
     }
     ```
   * *Critical Scope Rule*: `org:create_api_key` must be stripped when authorizing against chat organizations; Claude's API returns 400 if included.

4. **Code Exchange & Injection**:
   * The response returns `{ "redirect_uri": "https://platform.claude.com/oauth/code/callback?code=...&state=..." }`.
   * The script formats `<code-value>#<state>` and injects it into standard input of `claude auth login`.
   * Claude Code automatically calls `https://platform.claude.com/v1/oauth/token` with `grant_type: authorization_code`, receives access & refresh tokens, and persists them into the Keychain.
   * `provider-manager` copies the new tokens into that account's Orca item (`Orca Claude Code Managed Credentials`).
   * For an account the store does not hold, `claude auth login` runs with `CLAUDE_CONFIG_DIR` set to a
     throwaway directory, so its tokens land in that directory's scoped item (deleted afterwards). The live
     store is never written, and nothing switches. Before BRO-2713, every re-login was a hidden switch
     that skipped the outgoing write-back.

---

## 3. What Claude Code does with the store (measured)

Read from Claude Code 2.1.280's bundled source, then checked against the real binary with
`tests/drill/drill.py`:

| Behaviour | Source | Consequence |
|---|---|---|
| With no `<configDir>/.credentials.json` (none exists on this host), each request clears the token memo and re-reads the store, through a 30 s keychain read cache (`WNn=30000`). | `gD`/`zy`, keychain store class | A write to the store becomes every running session's credential within about 30 s. |
| A token within 5 min of `expiresAt` is refreshed under `<configDir>/.oauth_refresh.lock` + `<realpath(configDir)>.lock` (proper-lockfile, stale 60 s). Inside the lock the store is re-read; a changed access token is adopted. | `ed`, `rdo`, `wSr` | Refreshes force a real read, so a session never refreshes the outgoing account after a switch. A switch that holds this lock cannot race a refresh. |
| `invalid_grant` marks the refresh token dead; with no usable access token the turn fails "OAuth session expired and could not be refreshed". | `ed` catch, `i6`, `Rwt` | A switch that writes a consumed refresh token kills every running session at its next refresh. |
| The refresh response names the account (`account.email_address`); `GET /api/oauth/profile` returns `account.email` and `organization.uuid`. | `eHe`, `DLn` | Identity checks without spending anything. |
| `StopFailure` fires when an API error ends a turn; matcher on `error` (`rate_limit`, `authentication_failed`, ...); fire-and-forget. | hook schema `iN`, `mRe` | The real in-session rate-limit signal. A hook cannot resume the turn; it can only record it. |

Drill results (real binary, sandboxed scratch HOME, stubbed endpoints) are in the BRO-2713 PR.

## 4. The switch protocol

1. Balancer lock (`~/.cache/broomva-provider-balancer.lock`, flock; reentrant within one process).
2. Read everything: roster, every Orca copy, both store items. An unreadable store aborts.
3. Identify the store's account: its refresh token equals an Orca copy's (`orca_copy_match`); a cached
   profile check for the same token fingerprint (`profile_cached`); or a live profile check of its
   access token (`profile`). Otherwise it is `orca_setting_unverified`, and a switch that would
   discard that credential is refused unless `--force`.
4. Validate the target, still outside Claude Code's lock: refresh it through its own Orca copy
   (proving its refresh token unspent; the rotated pair is persisted and read back first). The new
   access token must then pass a profile check naming that account: the email must match exactly one
   roster account, and its org must agree.
5. Under Claude Code's refresh lock (no network inside, each keychain call bounded at 8 s, the whole
   hold far under the 60 s stale age): re-read the store and abort if it changed; write the outgoing
   account's live tokens to its Orca copy (read back) if they differ from it; write the target's
   `claudeAiOauth` to the primary item only; read back and verify. A failed read-back after the write
   records `switch.unverified` and keeps the cooldown.
6. Record: orca-data active id and the `~/.claude.json` hint (each rewritten only if nobody wrote the
   file since it was read, never if it does not parse, keeping its mode); state `lastSwitch` (the
   cooldown); event `switch`.

**Refresh interlock:** `refresh_account_token` runs only under the balancer lock (non-blocking: if
another provider-manager action holds it, nothing is refreshed), and re-reads every store item
immediately before the POST. It refuses:
- the account the store holds;
- any copy whose refresh token equals the primary item's, or the unscoped `Claude Code-credentials`
  item's even when that item is the mirror (every default session reads it);
- one equal to a scoped mirror's while a running Claude Code process has `CLAUDE_CONFIG_DIR` resolving
  to that config dir (from `ps axeww`: the command part must be Claude Code, the variable a real
  environment token; an unreadable process table counts as yes);
- unless the store was proven dead or the operator forced it, any refresh while the store's account
  cannot be identified. On `invalid_grant`, the copy is
re-read: if another writer changed it meanwhile, it is not marked `needs_login`. Telemetry for the
store's account uses the store's access token and never refreshes it.

**The mirror.** Old provider-manager versions wrote the scoped item too, so it can still hold a
chain an Orca copy also holds. This version never writes it.

## 5. Telemetry, balancer, probe

`fetch_account_usage` returns `telemetry`: `ok` (numbers), `throttled` (usage endpoint 429; the last
numbers are kept and marked stale), `auth_expired`, `needs_login` (`invalid_grant` on the copy),
`no_credentials`, or `unavailable`. Only `ok` numbers can mark an account limited (`locked_reason`, 5h or
7d ≥ 100%, or an active limit at 100%).

**429 backoff.** `Retry-After` (seconds or an HTTP date) is honoured, floored at 60 s and capped at 6 h;
without it the backoff is 2→4→8→16→30 min. It is persisted (`telemetry.<id>.backoffUntil`) and checked
before every usage call, so kicks inside it never reach the endpoint. Measured 2026-10-19: the endpoint
answered `Retry-After: 3600` to each hourly retry for the active account, so its numbers were over two
hours old with the backoff working as designed. `usage` shows the age of the last good numbers and the
time to the next try; `state` shows both under `claudeTelemetry`. Past `staleNumbersMinutes` the
balance decision carries `telemetryNote`: balancing on numbers waits, StopFailure reports still fail
over after the probe.

**One retry per window.** When `backoffUntil` has passed, `_claim_usage_call` takes the retry under the
state lock and pushes `backoffUntil` out by `USAGE_CLAIM_SECONDS` (60 s, with `claimedAt`/`claimedBy`),
so every other kick, from any session, still sees a backoff. A 429 replaces the claim with the new
window, a good read clears the entry, any other failure lets the claim lapse after a minute. A login
(`login-headless`) clears the account's entry: a new grant starts with one call.

**Probe readout (BRO-3405).** Measured 2026-10-22/23: after team@ was logged in again and made active,
the endpoint answered 429 with `Retry-After: 3600` to every retry (00:48, 01:52, 02:53, 03:54, 04:57,
05:57Z), one call per window, for six hours. The backoff was working; the budget is per account and
Claude Code 2.1.306 spends it (it calls `/api/oauth/usage` itself, on several paths). The probe runs
with `--output-format stream-json --verbose`, and 2.1.306 prints a `rate_limit_event` whose
`rate_limit_info.unifiedWindows.{five_hour,seven_day}` carry `utilization` (a 0-1 fraction: Claude
Code clamps the unified-ratelimit header to [0, 1]) and `resetsAt` (epoch seconds), taken from that
real response's headers. `readout_numbers` (in the balancer, under its lock) runs one probe when the
active account's endpoint is throttled and its numbers are at least half of `staleNumbersMinutes` old
(and the last probe at least that old). It writes an `ok` cache entry marked `numbersSource: probe`
and `endpoint: throttled` (`status: rejected` becomes a lock, so a limit fails over through the usual
probe-confirmed path). While the endpoint stays in backoff that entry is kept until
`staleNumbersMinutes`, then it degrades to `throttled` like any other old numbers. Never for a standby
(the probe only reaches the store), and discarded when `build_context` no longer identifies the store
as that account after the probe; only a probe record this path attributed (`readoutFor`) is ever reused,
and it records the five-hour `resetsAt`/`fiveHourAtProbe` so a limit it found ends with that window. A
malformed or missing event is no readout, and a probe that answered without one logs
`telemetry.readout_missing` (with `claudeVersion`). A dry run never probes. The result line is the last
`type: result` event (stream-json opens with `init`); with none, the raw text is classified as before.

**Dead grants.** An `invalid_grant` marks the account `needsLogin` with a fingerprint of that refresh
token (`health.<id>.deadGrant`). Its refreshes are skipped while the copy still holds it, and the mark
clears when new tokens work. Before this, a dead copy was refreshed at every evaluation (205 times in a
day for one account).

Decision rules and defaults: SKILL.md "The balancer". The probe runs `claude -p "Reply with the single
word OK." --tools "" --strict-mcp-config --setting-sources project --no-session-persistence
--output-format stream-json --verbose` (plus `--model <probeModel>` only if configured: by default it uses the same
default model as the sessions), from an empty temp dir. Its environment drops `CLAUDECODE`,
`CLAUDE_CODE_*`, `CLAUDE_PID` and `ANTHROPIC_*` auth overrides, keeps `CLAUDE_CONFIG_DIR` as the
sessions have it, and sets `PROVIDER_MANAGER_PROBE=1` (the hook no-ops on it).

The result is cached for `probeTtlSeconds` (30 s for `unknown`), and a report newer than the cached
probe always gets a fresh one:
- `ok`;
- `limited` (`api_error_status: 429` in Claude Code's JSON result, else the limit phrases);
- `auth_dead` ("OAuth session expired and could not be refreshed");
- `unknown`.

`limited` permits a rate-limit failover; `auth_dead` permits the dead-grant failover. An account the
probe confirmed `limited` is not a failover target for an hour, whatever its numbers say: a per-model
cap need not show in the 5-hour/7-day totals. Per-model weekly buckets (`seven_day_opus`,
`seven_day_sonnet`, …) at 100% also count as limited. Measured against
the real 2.1.280 binary (`tests/drill`, `probe` scenario):
- a subscription-limit 429 (with the `anthropic-ratelimit-unified-status: rejected` / `-reset` headers)
  prints "You've hit your session limit · resets 10:47pm (…)" with `api_error_status: 429`;
- a dead grant prints the auth message.

**Version gate.** `claude --version` (the binary on PATH, else `~/.local/bin`; cached per resolved
binary for 1 h, a failed check for 1 min) must be in `MEASURED_CLAUDE_VERSIONS` (2.1.280; 2.1.295, whose drill passed every
scenario) or
`verifiedClaudeVersions`. Otherwise automatic evaluations log `version_unverified` and only
`would_switch`, and the pause shows in the session-start line, `usage` and `state`. Operator commands
(`switch`, `balance`, `rotate`) are not gated.

## 6. Files and events

| Path | What |
|---|---|
| `~/.cache/broomva-provider-events.jsonl` | Events. Every line: `timestamp`, `iso`, `event`, `trace_id` (one evaluation or switch), `run_id` (one process), `pid`, `session_id` (the calling session). |
| `~/.cache/broomva-provider-state.json` | `lastEvalAt`, `lastKickAt`, `lastSwitch {at, from, to, source, unverified?}`, `holdUntil`, `pendingSignals` (expired after 15 min at every evaluation), `telemetry {id: backoff}`, `health {id: needsLogin, deadGrant}`, `probes`, `claudeVersion`, `storeIdentity` (token fingerprint, never a token), `lastCodexSwitch`, `codexHealth {id: status, reason, grant}`, `codexLoginAttempts {email: at}`. Mode 0600. |
| `~/.cache/broomva-provider-usage.json` | Usage cache (90 s TTL). |
| `~/.cache/broomva-provider-stalled.jsonl` | StopFailure reports: `sessionId`, `cwd`, `transcriptPath`, `error`, `paseoAgentId`. |
| `~/.cache/broomva-provider-balancer.lock` | The machine-wide lock; holds `{pid, since, holder}`. |

Events:
- `switch` (`fromAccount`, `toAccount`, `source`, `reason`, `wroteBack`, `outgoingIdentity`, utilisations, `probe`);
- `switch.refused` (`target`, `reason`), `switch.unverified` (`error`), `switch.discard_unverified`;
- `balance.decision` (`action`, `reason`, `telemetry`, `remainingSeconds`...);
- `probe` (`result`), `probe.disagrees` (a session reported a limit and the probe says ok), `version_unverified` (`claudeVersion`);
- `balance.decision` also carries `numbersAgeSeconds` and `telemetryNote` when the active account's numbers are stale;
- `telemetry.throttled` (`backoffUntil`), `telemetry.readout` (`fiveHour`, `sevenDay`: the active account's numbers taken from a probe), `telemetry.readout_missing` (`claudeVersion`);
- `refresh`, `refresh.refused` (`reason`), `refresh.deferred`, `refresh.failed` (`needsLogin`), `refresh.persist_failed` (critical); Codex ones carry `provider: codex`;
- `codex.balance.decision` (`action`, `code`, `reason`, `active`, `target`, `standbys {email: why not a candidate}`, `source`, `dryRun`), one per evaluation, holds included;
- `codex.snapshot` (`reason`, `ok`), `codex.switch` (`method`), `codex.login`, `codex.login.failed` (`space`, `reason`);
- `writeback.failed`, `session.stalled`, `login`, `hold`.

Events and stalled-session logs are mode 0600.

## Hook wiring

The settings entries this version expects (`~/.claude/settings.json`). The UserPromptSubmit and
SessionStart entries are unchanged. **Add** the StopFailure entry. The two PostToolUse/PostToolUseFailure
entries are now no-ops and may be removed:

```json
"StopFailure": [
  { "hooks": [ { "type": "command", "timeout": 5,
                 "command": "python3 -I /Users/broomva/.agents/skills/provider-manager/scripts/provider_manager_hook.py stop-failure 2>/dev/null || true" } ] }
]
```

No matcher: the hook reads `error` itself. It records every stalled turn and starts a failover
evaluation for `rate_limit` and `authentication_failed`. The evaluation still needs the probe to agree
before it acts. In the detached process, a reported limit that cannot be acted on yet (lock busy, inside
the 5-minute gap, an inconclusive probe, a transient refusal) is retried for up to 15 minutes, because
stalled sessions send no prompts. One such loop runs per machine (`broomva-provider-settle.lock`), and
it stops once any switch has happened. A resolved evaluation clears only the reports it saw.

## Antigravity ACP isolation

`pm_antigravity.py` owns only an atomic, mode-0600 registry containing profile references, grant
fingerprints, sanitized quota readings, per-family selections/cooldowns and stable thread pins. Schema v2 keeps immutable generation
records, a latest-generation view per email and generation-owned pins. V1 migration preserves the
exact email-to-profile ownership of existing pins before any new registration is published.
Reauthorization into a fresh profile publishes a new generation without rewriting retained profiles;
idempotent registration of an older generation never replaces the latest one.
`pm_antigravity_quota.py` verifies Google userinfo identity before retrieving both official quota
summaries. Unknown/disabled data remains explicit; fallback model windows retain model families.
Google's refresh exchange is documented at
https://developers.google.com/identity/protocols/oauth2/native-app#offline.
The native profile is never rewritten by telemetry; unexpected refresh-token rotation places a
credential-free fingerprint refusal marker in `~/.cache/broomva-provider-antigravity/`.

`pm_antigravity_launch.py` uses the supported T3 `acp-mcp-call` bootstrap before native exec.
T3 registers its MCP thread scope before spawning the ACP runtime. Capabilities identify the caller;
thread inspection checks provider/model identity, run/item history and fork lineage. New pins are
committed before exec and retained across process restarts. File storage is forced and ambient
Google API credentials removed. Native ACP 1.3.0 and its harness are hash-pinned after an offline,
network-denied initialize probe established load/resume support and no fork support.

This integration routes only the newly configured generic ACP provider, not native T3 Antigravity
instances or desktop/Go CLI global authentication. No ACP protocol proxy, replay or server-ID rewrite
is involved. T3 discovery has no thread scope and intentionally fails closed; explicit custom models
allow the warning-state provider to be selected. Existing unpinned conversations require an explicit,
verified migration design rather than guessing an account. Quota summaries do not prove inference
availability, and runtime limit errors are surfaced without automatic request replay.
