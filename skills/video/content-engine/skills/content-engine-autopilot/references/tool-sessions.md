# Tool Sessions — Per-Tool Authentication Persistence

How the content engine autopilot saves, loads, validates, and refreshes authentication sessions for each supported browser-based generation tool.

## Session Storage Location

All sessions live under a single directory:

```
~/.content-engine/sessions/
├── higgsfield.json      # Playwright storageState for Higgsfield
├── weavy.json           # Playwright storageState for Weavy
├── artlist.json         # Playwright storageState for Artlist
├── runway.json          # Playwright storageState for Runway
├── pika.json            # Playwright storageState for Pika
├── udio.json            # Playwright storageState for Udio
├── canva.json           # Playwright storageState for Canva
└── .session-meta.json   # Metadata about session health and expiry
```

The `.session-meta.json` file tracks session validity without requiring a browser launch:

```json
{
  "higgsfield": {
    "saved_at": "2026-04-07T14:30:00Z",
    "last_validated": "2026-04-07T16:00:00Z",
    "expires_estimate": "2026-04-14T14:30:00Z",
    "auth_method": "google_oauth",
    "status": "valid"
  },
  "weavy": {
    "saved_at": "2026-04-06T10:00:00Z",
    "last_validated": "2026-04-07T09:00:00Z",
    "expires_estimate": "2026-04-13T10:00:00Z",
    "auth_method": "email_password",
    "status": "valid"
  }
}
```

## Saving Sessions

### When to Save

Save a session immediately after the user completes authentication. The agent detects successful auth by checking for a redirect to the tool's dashboard or the presence of auth-related cookies.

### Save Procedure

```
1. User completes login in headed browser
2. Agent verifies auth:
   - Navigate to dashboard URL
   - Confirm no redirect back to login
   - Check for auth cookies in browser state
3. Agent saves storageState:
   agent-browser save-session ~/.content-engine/sessions/{tool}.json
4. Agent updates .session-meta.json with save timestamp and auth method
5. Agent confirms save to user: "Session saved for {tool}. Valid for ~7 days."
```

### What Gets Saved

The Playwright `storageState` captures:

| Data | Purpose | Example |
|------|---------|---------|
| **Cookies** | Session tokens, auth cookies, CSRF tokens | `session_token`, `__cf_bm`, `_ga` |
| **localStorage** | JWT tokens, user preferences, feature flags | `auth_token`, `user_id`, `theme` |
| **sessionStorage** | Not persisted by Playwright (ephemeral by design) | Re-created on page load |

**Security note**: Session files contain sensitive authentication tokens. The `~/.content-engine/sessions/` directory should have `700` permissions (owner-only access). Never commit session files to git.

```bash
chmod 700 ~/.content-engine/sessions/
```

## Loading Sessions

### Load Procedure

```
1. Check .session-meta.json for session status
2. If status is "expired" or "unknown" → skip to re-authentication
3. Load storageState into browser context
4. Navigate to dashboard URL as validation
5. If dashboard loads → session valid, proceed
6. If redirected to login → session expired:
   a. Update .session-meta.json status to "expired"
   b. Switch to headed mode
   c. Prompt user to re-authenticate
   d. Save new session
```

### Validation Check (Lightweight)

Before launching a full batch, quickly validate the session without generating anything:

```bash
# agent-browser approach
agent-browser open "{dashboard_url}" --session ~/.content-engine/sessions/{tool}.json --headless
agent-browser wait --url-contains "{dashboard_path}" --timeout 10000
# If this succeeds, session is valid
# If it times out or URL contains "login", session is expired
```

## Per-Tool Session Details

### Higgsfield

| Property | Value |
|----------|-------|
| Auth method | Google OAuth (primary), Email (secondary) |
| Login URL | `https://higgsfield.ai` (redirects to login if not authed) |
| Dashboard URL | `https://higgsfield.ai/dashboard` or `https://higgsfield.ai/create` |
| Auth cookie | `next-auth.session-token` (HttpOnly, Secure) |
| Session lifetime | ~7 days (Google OAuth refresh extends this) |
| Refresh pattern | Re-authenticate when token expires; no silent refresh |

**Key cookies to watch:**
- `next-auth.session-token` — primary auth (JWT)
- `next-auth.csrf-token` — CSRF protection (required for form submissions)
- `__Secure-next-auth.callback-url` — OAuth callback state

**Notes:**
- Higgsfield uses Next.js with NextAuth. The session token is a JWT with a 7-day default expiry.
- Google OAuth tokens may refresh silently in headed mode but not in headless. Expect to re-authenticate weekly.

### Weavy

| Property | Value |
|----------|-------|
| Auth method | Email + password |
| Login URL | `https://app.weavy.ai/login` |
| Dashboard URL | `https://app.weavy.ai/projects` |
| Auth cookie | `weavy_session` (HttpOnly, Secure) |
| Session lifetime | ~14 days |
| Refresh pattern | Cookie refreshed on every authenticated request |

**Key cookies:**
- `weavy_session` — primary session cookie
- `weavy_csrf` — CSRF token for mutations

**Notes:**
- Weavy's session cookie has a sliding expiry — using it extends the lifetime. Active batch runs keep it fresh.
- If running batches less than weekly, the session may expire. Re-authenticate before each campaign.

### Artlist

| Property | Value |
|----------|-------|
| Auth method | Email + password or Google OAuth |
| Login URL | `https://artlist.io/login` |
| Dashboard URL | `https://artlist.io/royalty-free/music` |
| Auth cookie | `artlist_session` (HttpOnly, Secure) |
| Session lifetime | ~30 days |
| Refresh pattern | Long-lived session; refresh on re-login |

**Key cookies:**
- `artlist_session` — primary session
- `artlist_plan` — subscription tier (affects available downloads)

**Notes:**
- Artlist has generous session lifetimes because it is a subscription service. Less frequent re-authentication needed.
- Download limits apply per subscription tier. The autopilot should check remaining downloads before starting a batch.
- Some assets require explicit license acceptance via checkbox before download.

### Runway

| Property | Value |
|----------|-------|
| Auth method | Google OAuth |
| Login URL | `https://app.runwayml.com/login` |
| Dashboard URL | `https://app.runwayml.com/` |
| Auth cookie | `rw_session` (HttpOnly, Secure) |
| Session lifetime | ~7 days |
| Refresh pattern | Re-authenticate weekly |

**Key cookies:**
- `rw_session` — primary auth
- `rw_workspace` — workspace context

**Notes:**
- Runway enforces credit-based billing. Check credit balance before batch runs.
- Gen-3 Alpha generations can take 1-3 minutes. Set generation timeout accordingly.

### Pika

| Property | Value |
|----------|-------|
| Auth method | Google OAuth |
| Login URL | `https://pika.art/login` |
| Dashboard URL | `https://pika.art/home` |
| Auth cookie | Varies (SPA with JWT in localStorage) |
| Session lifetime | ~7 days |
| Refresh pattern | JWT refresh via localStorage |

**Notes:**
- Pika stores the auth token in localStorage rather than cookies. The Playwright storageState captures this correctly.
- Token refresh may happen client-side. If a batch run encounters 401 errors mid-session, the token may need manual refresh.

### Udio

| Property | Value |
|----------|-------|
| Auth method | Google OAuth or Discord OAuth |
| Login URL | `https://www.udio.com/sign-in` |
| Dashboard URL | `https://www.udio.com/my-creations` |
| Auth cookie | Firebase auth token in localStorage |
| Session lifetime | ~1 hour (Firebase), refreshed automatically |
| Refresh pattern | Firebase SDK auto-refreshes in active browser sessions |

**Notes:**
- Udio uses Firebase Authentication. The ID token expires every hour but auto-refreshes when the page is active.
- In headless batch mode, the auto-refresh may not trigger. If you get auth errors after ~1 hour, reload the page to trigger token refresh.

## Session Expiry Detection

### Proactive Checks

Before starting a batch, validate all required sessions:

```
for each tool in campaign.tools:
  1. Read .session-meta.json for tool
  2. If expires_estimate < now → mark as "likely_expired"
  3. If last_validated > 24h ago → mark as "needs_check"
  4. If status is "valid" and within estimate → proceed
```

### Reactive Detection During Batch

During generation, the loop watches for auth failures:

| Signal | Meaning | Recovery |
|--------|---------|----------|
| Redirect to login page | Session fully expired | Pause batch, re-auth in headed mode, save new session, resume |
| 401 or 403 HTTP response | Token invalid | Reload page to trigger refresh; if persists, re-auth |
| "Please sign in" text on page | Soft session expiry | Same as redirect — re-authenticate |
| Rate limit / billing error | Account issue, not session | Log warning, pause batch, notify user |

## Session Refresh Patterns

### Sliding Window (Weavy, Artlist)

These tools extend session lifetime on every authenticated request. Keep sessions alive by:
- Using the tool at least once within the session window
- Running a lightweight validation check (navigate to dashboard) weekly

### Fixed Expiry (Higgsfield, Runway, Pika)

These tools issue tokens with a hard expiry. No amount of usage extends them. Plan for:
- Re-authentication before each weekly campaign batch
- Saving a fresh session immediately after re-auth

### Auto-Refresh (Udio)

Firebase-based tools auto-refresh tokens in active browser sessions. For batch mode:
- Reload the page every 45 minutes to trigger refresh
- Monitor for 401 responses as the trigger to reload

## Security Considerations

1. **File permissions**: `chmod 600 ~/.content-engine/sessions/*.json` — only the owner should read session files
2. **Never commit**: Add `sessions/` to `.gitignore` in any project that references the session directory
3. **Rotation**: Delete session files for tools you no longer use
4. **Shared machines**: Never save sessions on shared or multi-user systems without encryption
5. **Audit**: The `.session-meta.json` provides a log of when sessions were created and last used

## Higgsfield via Arc CDP

Browser-based Playwright login to Higgsfield does not work reliably. Google OAuth is blocked in automated contexts, and Clerk (their auth provider) rate-limits email/password attempts from headless browsers. The Higgsfield API exists but requires separate top-up credits — subscription credits are web-only and cannot be used via API.

The working approach is to use Arc browser with Chrome DevTools Protocol (CDP) remote debugging, then connect the agent to the user's live browser session.

### Setup

The user must launch Arc with the remote debugging port enabled:

```bash
osascript -e 'quit app "Arc"' && sleep 2 && /Applications/Arc.app/Contents/MacOS/Arc --remote-debugging-port=9222 &
```

This kills any existing Arc instance and restarts it with CDP on port 9222. The user then logs into Higgsfield manually in Arc (Google OAuth works in a real browser).

### Agent Connection

Once the user is logged into Higgsfield in Arc, the agent connects via:

```bash
agent-browser --cdp 9222 open "https://higgsfield.ai/cinema-studio"
```

The `--cdp 9222` flag tells agent-browser to attach to the existing Arc session rather than launching a new browser. This inherits the user's authenticated cookies, bypassing the OAuth/Clerk issues entirely.

### Cinema Studio 2.5 Workflow

| Property | Value |
|----------|-------|
| URL | `https://higgsfield.ai/cinema-studio` |
| Credit cost | 8 credits per generation |
| Generation time | ~4-5 minutes |
| Input method | Text prompt in textbox, click GENERATE button |
| Completion detection | Poll page via snapshot until video thumbnail appears |

**Generation loop:**
1. Navigate to Cinema Studio
2. Enter prompt in the textbox
3. Click the GENERATE button
4. Poll for completion by taking periodic snapshots (~30s intervals)
5. When the video thumbnail or download link appears, generation is complete
6. Download or screenshot the result

### Limitations

- Arc must remain open during the entire generation session — closing it kills the CDP connection
- Only one agent can connect to port 9222 at a time
- If Arc crashes or the user navigates away from Cinema Studio, the agent loses context
- Credit balance is not exposed via API; the agent must read it from the page UI
