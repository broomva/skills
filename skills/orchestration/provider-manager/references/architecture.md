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
    `~/.claude`). provider-manager keeps it in step as a mirror, for any session launched that way.
  * `CLAUDE_SECURESTORAGE_CONFIG_DIR` overrides both. Account: `$USER`.
  * Value: JSON (hex when written with `-X`) holding `claudeAiOauth` (Claude's access/refresh tokens,
    `expiresAt`, scopes) and `mcpOAuth` (MCP servers' OAuth: Linear, Slack, Sentry...).
* **Per-item write invariant**: a switch replaces `claudeAiOauth` in each item and writes the item's
  other keys back exactly as it read them, immediately before (under Claude Code's refresh lock). MCP
  tokens are never copied between items or from an Orca copy. The old cross-item merge let the stale
  mirror's Linear tokens overwrite the live ones (D28).

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
immediately before the POST. It refuses: the account the store holds; any copy whose refresh token
equals the primary item's; one equal to the mirror's while a running Claude Code process was launched
with `CLAUDE_CONFIG_DIR` (from `ps axeww`); and, unless the store was proven dead or the operator
forced it, any refresh while the store's account cannot be identified. On `invalid_grant`, the copy is
re-read: if another writer changed it meanwhile, it is not marked `needs_login`. Telemetry for the
store's account uses the store's access token and never refreshes it.

**The mirror.** Old provider-manager versions wrote the scoped item too, so it can still hold a
chain an Orca copy also holds. This version never writes it.

## 5. Telemetry, balancer, probe

`fetch_account_usage` returns `telemetry`: `ok` (numbers), `throttled` (usage endpoint 429; backoff
2→4→...→30 min, or `Retry-After`; the last numbers are kept and marked stale), `auth_expired`,
`needs_login` (`invalid_grant` on the copy), `no_credentials`, or `unavailable`. Only `ok` numbers can
mark an account limited (`locked_reason`, 5h or 7d ≥ 100%, or an active limit at 100%).

Decision rules and defaults: SKILL.md "The balancer". The probe runs `claude -p "Reply with the single
word OK." --tools "" --strict-mcp-config --setting-sources project --no-session-persistence
--output-format json` (plus `--model <probeModel>` only if configured: by default it uses the same
default model as the sessions), from an empty temp dir. Its environment drops `CLAUDECODE`,
`CLAUDE_CODE_*`, `CLAUDE_PID` and `ANTHROPIC_*` auth overrides, keeps `CLAUDE_CONFIG_DIR` as the
sessions have it, and sets `PROVIDER_MANAGER_PROBE=1` (the hook no-ops on it).

The result is cached for `probeTtlSeconds`:
- `ok`;
- `limited` (`api_error_status: 429` in Claude Code's JSON result, else the limit phrases);
- `auth_dead` ("OAuth session expired and could not be refreshed");
- `unknown`.

`limited` permits a rate-limit failover; `auth_dead` permits the dead-grant failover. Measured against
the real 2.1.280 binary (`tests/drill`, `probe` scenario):
- a subscription-limit 429 (with the `anthropic-ratelimit-unified-status: rejected` / `-reset` headers)
  prints "You've hit your session limit · resets 10:47pm (…)" with `api_error_status: 429`;
- a dead grant prints the auth message.

**Version gate.** `claude --version` (cached per resolved binary, 1 h) must be in
`MEASURED_CLAUDE_VERSIONS` (2.1.280) or `verifiedClaudeVersions`. Otherwise automatic evaluations log
`version_unverified` and only `would_switch`. Operator commands are not gated.

## 6. Files and events

| Path | What |
|---|---|
| `~/.cache/broomva-provider-events.jsonl` | Events. Every line: `timestamp`, `iso`, `event`, `trace_id` (one evaluation or switch), `run_id` (one process), `pid`, `session_id` (the calling session). |
| `~/.cache/broomva-provider-state.json` | `lastEvalAt`, `lastKickAt`, `lastSwitch {at, from, to, source, unverified?}`, `holdUntil`, `pendingSignals`, `telemetry {id: backoff}`, `health {id: needsLogin}`, `probes`, `claudeVersion`, `storeIdentity` (token fingerprint, never a token). Mode 0600. |
| `~/.cache/broomva-provider-usage.json` | Usage cache (90 s TTL). |
| `~/.cache/broomva-provider-stalled.jsonl` | StopFailure reports: `sessionId`, `cwd`, `transcriptPath`, `error`, `paseoAgentId`. |
| `~/.cache/broomva-provider-balancer.lock` | The machine-wide lock; holds `{pid, since, holder}`. |

Events:
- `switch` (`fromAccount`, `toAccount`, `source`, `reason`, `wroteBack`, `outgoingIdentity`, utilisations, `probe`);
- `switch.refused` (`target`, `reason`), `switch.unverified` (`error`), `switch.discard_unverified`;
- `balance.decision` (`action`, `reason`, `telemetry`, `remainingSeconds`...);
- `probe` (`result`), `probe.disagrees` (a session reported a limit and the probe says ok), `version_unverified` (`claudeVersion`);
- `telemetry.throttled` (`backoffUntil`);
- `refresh`, `refresh.refused` (`reason`), `refresh.deferred`, `refresh.failed` (`needsLogin`), `refresh.persist_failed` (critical);
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
the 5-minute gap) is retried for up to 15 minutes, because stalled sessions send no prompts.
