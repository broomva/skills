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
* **Config File**:
  `~/.claude.json`
  * Block `oauthAccount`: contains `accountUuid`, `emailAddress`, `organizationUuid`, `organizationName`, `organizationType` (`claude_max`, `claude_pro`), etc.
* **Credentials in macOS Keychain**:
  * **Scoped Service**: `Claude Code-credentials-d098dafb` (hash represents `~/.claude`)
  * **Fallback Service**: `Claude Code-credentials`
  * **Account**: macOS username (e.g. `$(whoami)`)
  * **Format**: Hex-encoded JSON or raw JSON string.

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
   * `provider-manager` mirrors the new tokens into Orca's Keychain service (`Orca Claude Code Managed Credentials`).

---

## 3. Rate Limit & Rotation Mechanism

* **Quota Tracking**:
  * Claude Code returns HTTP 429 when the 5-hour rolling organization rate limit window is exhausted.
* **Auto-Rotation**:
  * When an agent detects a 429 or rate limit warning, it runs `provider_manager.py rotate`.
  * The tool selects the next alternate account with valid credentials, switches the active Keychain and config, and validates via `claude auth status`.
  * The agent retries its turn on the newly activated subscription.
