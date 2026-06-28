# Playwright Setup for Content Engine Autopilot

How to install, configure, and operate Playwright-based browser automation from Claude Code for content generation workflows.

## Installation

### Option 1: agent-browser (Recommended)

The `agent-browser` CLI wraps Playwright with agent-friendly commands and handles session management natively.

```bash
# Install globally
npm install -g @anthropic-ai/agent-browser

# Verify installation
agent-browser --version

# Install browser binaries (Chromium by default)
agent-browser install
```

### Option 2: Playwright Direct

For cases where you need finer control or `agent-browser` is unavailable.

```bash
# Install Playwright as a project dependency
bun add playwright
# or
npm install playwright

# Install browser binaries
npx playwright install chromium

# Verify
npx playwright --version
```

### Option 3: Playwright MCP Server

For Claude Code MCP integration (read-only inspection, not recommended for generation loops).

```bash
npx @anthropic-ai/mcp-server-playwright
```

## Headed vs Headless Mode

### Headed Mode (Setup + Debugging)

Headed mode opens a visible browser window. **Required** for initial tool authentication because the user needs to interact with OAuth flows, CAPTCHAs, and 2FA prompts.

```bash
# agent-browser
agent-browser open "https://higgsfield.ai" --headed

# Playwright direct
const browser = await chromium.launch({ headless: false });
```

**When to use headed mode:**
- First-time tool setup (user must log in)
- Debugging selector failures (see what the page looks like)
- Tools with CAPTCHA challenges (Cloudflare, reCAPTCHA)
- OAuth flows that require user consent clicks

### Headless Mode (Production Batches)

Headless mode runs without a visible window. Faster startup, lower resource usage, suitable for unattended batch runs after authentication is saved.

```bash
# agent-browser (default is headless)
agent-browser open "https://higgsfield.ai"

# Playwright direct
const browser = await chromium.launch({ headless: true });
```

**When to use headless mode:**
- Batch generation with saved sessions
- Downloading completed assets
- Any automation that does not require user interaction

### Mode Selection Logic

```
Is the session saved and valid?
  ├─ YES → headless mode (batch generation)
  └─ NO  → headed mode (user authenticates)
           └─ After auth → save session → switch to headless for remaining work
```

## Session Management

### Saving a Session

After the user authenticates in headed mode, save the browser state (cookies, localStorage, sessionStorage) to a JSON file.

```bash
# agent-browser
agent-browser save-session ~/.content-engine/sessions/higgsfield.json

# Playwright direct (Node.js)
const context = await browser.newContext();
// ... user authenticates ...
await context.storageState({ path: '~/.content-engine/sessions/higgsfield.json' });
```

### Loading a Session

Restore the saved session to skip authentication on subsequent runs.

```bash
# agent-browser
agent-browser open "https://higgsfield.ai" --session ~/.content-engine/sessions/higgsfield.json

# Playwright direct
const context = await browser.newContext({
  storageState: '~/.content-engine/sessions/higgsfield.json'
});
```

### Session File Structure

The session file is a Playwright `storageState` JSON containing:

```json
{
  "cookies": [
    {
      "name": "session_token",
      "value": "abc123...",
      "domain": ".higgsfield.ai",
      "path": "/",
      "expires": 1743984000,
      "httpOnly": true,
      "secure": true,
      "sameSite": "Lax"
    }
  ],
  "origins": [
    {
      "origin": "https://higgsfield.ai",
      "localStorage": [
        { "name": "auth_token", "value": "..." },
        { "name": "user_prefs", "value": "..." }
      ]
    }
  ]
}
```

### Session Directory Layout

```
~/.content-engine/sessions/
├── higgsfield.json      # Higgsfield session state
├── weavy.json           # Weavy session state
├── artlist.json          # Artlist session state
├── runway.json           # Runway session state
├── pika.json             # Pika session state
├── udio.json             # Udio session state
└── .last-check.json     # Timestamps of last session validity check
```

## Timeout Configuration

Different operations need different timeout windows. Generation tools can take minutes to produce output.

### Recommended Timeouts

| Operation | Timeout | Rationale |
|-----------|---------|-----------|
| Page navigation | 30s | Most pages load within 10s, 30s covers slow CDNs |
| Login page load | 15s | Login pages are lightweight |
| Element visibility | 10s | UI elements should appear quickly after page load |
| Prompt injection (type) | 5s | Input fields are immediately interactive |
| Generation submit | 10s | Button click + initial server response |
| Generation completion | 300s (5 min) | AI generation can take 1-3 minutes; 5 min is safe ceiling |
| Download initiation | 30s | Download button click + file transfer start |
| File download complete | 120s | Large video files may take time to download |
| Session restore | 10s | Loading cookies and localStorage |

### Setting Timeouts

```typescript
// Playwright direct
const page = await context.newPage();

// Global default
page.setDefaultTimeout(30_000); // 30 seconds

// Per-operation overrides
await page.goto('https://higgsfield.ai/create', { timeout: 30_000 });
await page.waitForSelector('.result-video', { timeout: 300_000 }); // 5 min for generation
await page.click('button.download', { timeout: 10_000 });
```

```bash
# agent-browser
agent-browser open "https://higgsfield.ai/create" --timeout 30000
agent-browser wait --selector ".result-video" --timeout 300000
agent-browser click "button.download" --timeout 10000
```

## Error Handling

### Common Failures and Recovery

**1. Session Expired**

The saved session is no longer valid (token expired, server-side session invalidated).

```
Detection: After loading session, navigate to dashboard URL.
  If redirected to login page → session expired.

Recovery:
  1. Delete stale session file
  2. Switch to headed mode
  3. Prompt user to re-authenticate
  4. Save new session
  5. Resume batch in headless mode
```

**2. Selector Not Found**

The tool's UI has changed (class names, element structure, new version deployed).

```
Detection: waitForSelector times out.

Recovery:
  1. Take a screenshot for debugging: agent-browser screenshot /tmp/debug-{tool}-{timestamp}.png
  2. Log the failure with the expected vs actual DOM structure
  3. Skip this generation, mark as "selector_failure" in manifest
  4. Notify user with screenshot so they can update the tool adapter
```

**3. CAPTCHA / Bot Detection**

Some tools detect automated browsers and present challenges.

```
Prevention:
  - Use realistic viewport size (1920x1080, not 800x600)
  - Set a real User-Agent string
  - Add small random delays between actions (200-500ms)
  - Use headed mode for first run to build a session with natural behavior

Recovery:
  1. Switch to headed mode
  2. Let user solve the CAPTCHA manually
  3. Save the new session (post-CAPTCHA cookies often include trust tokens)
```

**4. Browser Crash / Out of Memory**

Long batch runs with many tabs or large video downloads can exhaust memory.

```
Prevention:
  - Process one generation at a time (close page after download)
  - Clear browser cache between generations: await context.clearCookies() (selectively)
  - Set --max-old-space-size=4096 for Node.js if needed

Recovery:
  1. Read manifest.json to find last completed generation
  2. Relaunch browser with fresh context
  3. Reload session
  4. Resume from the next unprocessed prompt
```

## Browser Context Configuration

For generation workflows, configure the browser context to behave like a real user session:

```typescript
const context = await browser.newContext({
  storageState: sessionPath,
  viewport: { width: 1920, height: 1080 },
  userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  locale: 'en-US',
  timezoneId: 'America/New_York',
  permissions: ['clipboard-read', 'clipboard-write'],
  acceptDownloads: true,
  // Important: set downloads path for organized output
  // Downloads go here before being moved to campaign output directory
});
```

### Download Handling

```typescript
// Wait for download event after clicking download button
const [download] = await Promise.all([
  page.waitForEvent('download', { timeout: 120_000 }),
  page.click('button.download'),
]);

// Save to organized output directory
const suggestedFilename = download.suggestedFilename();
const outputPath = path.join(campaignDir, 'raw', `${toolName}-${promptId}${path.extname(suggestedFilename)}`);
await download.saveAs(outputPath);
```

## Performance Tips

1. **Reuse browser context** across generations for the same tool (avoid re-creating context per prompt)
2. **Close pages after download** to free memory (but keep the context alive)
3. **Parallelize across tools** but not within a tool (most tools rate-limit per session)
4. **Pre-warm the session** by navigating to the dashboard before starting generation (lets background resources load)
5. **Use network interception** to block analytics/tracking scripts that slow page loads:

```typescript
await context.route('**/{analytics,tracking,ads}**', route => route.abort());
await context.route('**/*.{woff,woff2}', route => route.abort()); // Skip web fonts if not needed
```
