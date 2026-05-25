---
name: content-engine-autopilot
description: "Browser Orchestration — Playwright-driven generation at scale. Claude Code runs your entire content pipeline in the browser. Saves authentication sessions per tool, executes batch generation using compiled identity, and organizes output automatically. Supports Higgsfield, Weavy, Artlist, and extensible to any web-based generation tool. Triggers on: 'autopilot', 'browser automation', 'batch generate', 'setup tool', 'automated generation'."
---

# Content Engine Autopilot — Browser Orchestration for AI Generation Tools

Drive web-based AI generation tools from Claude Code using Playwright. Authenticate once, save sessions, inject compiled identity prompts, and batch-generate assets across Higgsfield, Weavy, Artlist, and any browser-accessible tool.

## Why Browser Orchestration

Most cutting-edge generation tools (video avatars, motion graphics, music, stock footage) live behind web UIs with no public API. Autopilot turns Claude Code into an operator that can:

1. **Launch a headed Chrome instance** and let you log in once
2. **Persist that session** so future runs skip authentication
3. **Load your compiled identity** (brand style, character descriptions, scene parameters) and inject it into each tool's prompt field
4. **Run batch generation** across dozens of prompts in a single unattended session
5. **Download and organize results** into a structured output directory with a tracking manifest

```
SETUP (once per tool)
  └─ Launch Chrome → Navigate to tool → User logs in → Save session

GENERATE (per campaign)
  └─ Load session → Load compiled identity → For each prompt:
       Inject prompt → Configure settings → Submit → Wait → Download → Next

ORGANIZE (automatic)
  └─ raw/ → upscaled/ → graded/ → manifest.json
```

## Supported Tools

| Tool | Category | What It Generates | Session Persistence |
|------|----------|-------------------|---------------------|
| **Higgsfield** | Video avatar | Talking-head videos from text + face reference | Cookie-based (Google OAuth) |
| **Weavy** | Motion design | Animated social cards, kinetic typography | Cookie-based (email login) |
| **Artlist** | Stock + music | Licensed stock footage, music tracks, SFX | Cookie-based (email login) |
| **Runway** | Video generation | Gen-3 Alpha video clips from text/image | Cookie-based (Google OAuth) |
| **Pika** | Video effects | Stylized video generation, lip sync | Cookie-based (Google OAuth) |
| **Udio** | Music generation | AI music tracks with vocals | Cookie-based (Google OAuth) |
| **Canva** | Design | Templates, social cards, presentations | Cookie-based (Google/email) |

Adding a new tool requires only a tool adapter (see [Adding New Tools](#adding-new-tools)).

## Setup Flow

### Prerequisites

```bash
# Check Playwright availability
which agent-browser && echo "agent-browser available" || echo "Install: npm install -g @anthropic-ai/agent-browser"
npx playwright --version 2>/dev/null && echo "Playwright available" || echo "Install: npx playwright install chromium"

# Ensure session directory exists
mkdir -p ~/.content-engine/sessions
mkdir -p ~/.content-engine/output
```

### First-Time Tool Setup

The setup flow launches a **headed** (visible) browser so the user can authenticate interactively. The agent navigates to the login page and waits for the user to complete authentication, then saves the session state.

```
1. Agent runs: agent-browser open "https://higgsfield.ai/login" --headed
2. User logs in manually (Google OAuth, email/password, etc.)
3. Agent detects successful auth (checks for dashboard URL or auth cookie)
4. Agent saves session: agent-browser save-session ~/.content-engine/sessions/higgsfield.json
5. Session persists across future runs until expiry
```

**Per-tool setup commands:**

```bash
# Higgsfield
agent-browser open "https://higgsfield.ai" --headed
# After login, save session
agent-browser save-session ~/.content-engine/sessions/higgsfield.json

# Weavy
agent-browser open "https://app.weavy.ai" --headed
agent-browser save-session ~/.content-engine/sessions/weavy.json

# Artlist
agent-browser open "https://artlist.io/login" --headed
agent-browser save-session ~/.content-engine/sessions/artlist.json
```

See [references/tool-sessions.md](references/tool-sessions.md) for session storage format, expiry patterns, and refresh logic.

## Generation Loop

### Step 1: Load Compiled Identity

Before generating, the loop loads the compiled identity from the content-engine knowledge base. This includes brand styles, character descriptions, and scene parameters that get injected into every prompt.

```
~/.content-engine/ or skills/content-engine/knowledge/compiled/
├── brands/          # Brand color palettes, typography, visual language
├── characters/      # Character descriptions, face references, voice profiles
├── styles/          # Visual style presets (cinematic, editorial, brainrot, etc.)
```

The compiled identity transforms a generic prompt like "make a video about productivity" into a brand-consistent prompt with specific visual style, character appearance, color grading, and motion parameters.

### Step 2: Inject Prompt + Configure

For each generation task, the loop:

1. **Navigates** to the tool's creation page
2. **Locates** the prompt input field (CSS selector per tool adapter)
3. **Clears** any existing content and **types** the compiled prompt
4. **Configures** tool-specific settings (resolution, duration, style preset, aspect ratio)
5. **Submits** the generation request

```
Prompt template assembly:
  [style_prefix] + [character_context] + [scene_brief] + [brand_suffix]

Example:
  "Cinematic 4K, warm golden hour lighting. A confident software engineer
   (dark hair, glasses, casual-professional) presents at a standing desk
   with dual monitors showing code. Camera: medium close-up, shallow DOF.
   Brand: deep navy (#0a0a12) accents, clean typography overlays."
```

### Step 3: Wait for Generation

Different tools have different generation times. The loop polls for completion:

| Tool | Typical Wait | Completion Signal |
|------|-------------|-------------------|
| Higgsfield | 30-90s | Video player appears in result div |
| Weavy | 10-30s | Download button becomes clickable |
| Artlist | 5-15s (search) | Results grid populates |
| Runway | 60-180s | Progress bar reaches 100%, video renders |
| Pika | 30-120s | Result card with video thumbnail |

The loop uses exponential backoff polling: check every 5s for the first 30s, then every 15s up to 5 minutes, then fail with timeout.

### Step 4: Download + Organize

Results are downloaded and organized into the output directory:

```
~/.content-engine/output/{campaign-id}/
├── raw/                    # Direct downloads from tools
│   ├── higgsfield-001.mp4
│   ├── higgsfield-002.mp4
│   └── weavy-001.mp4
├── upscaled/               # After enhancement pass (optional)
│   └── higgsfield-001-4k.mp4
├── graded/                 # After color grading (optional)
│   └── higgsfield-001-graded.mp4
└── manifest.json           # Tracking manifest (see below)
```

### Manifest Format

Every generation run produces a `manifest.json` that tracks provenance:

```json
{
  "campaign_id": "launch-video-2026-04",
  "created_at": "2026-04-07T14:30:00Z",
  "identity": {
    "brand": "broomva",
    "style": "cinematic-glass",
    "character": "founder-avatar"
  },
  "assets": [
    {
      "id": "hf-001",
      "tool": "higgsfield",
      "prompt": "Cinematic 4K, warm golden hour...",
      "settings": {
        "resolution": "1080p",
        "duration": "10s",
        "aspect_ratio": "16:9"
      },
      "status": "completed",
      "files": {
        "raw": "raw/higgsfield-001.mp4",
        "upscaled": "upscaled/higgsfield-001-4k.mp4",
        "graded": null
      },
      "generated_at": "2026-04-07T14:32:15Z",
      "generation_time_seconds": 67,
      "metadata": {
        "file_size_bytes": 8421376,
        "duration_seconds": 10.2,
        "resolution": "1920x1080"
      }
    }
  ],
  "stats": {
    "total_requested": 12,
    "completed": 11,
    "failed": 1,
    "total_generation_time_seconds": 742
  }
}
```

## Batch Mode

Batch mode processes a list of prompts from a JSONL file or a campaign brief. It handles retries, rate limiting, and session refresh automatically.

### Campaign Brief Format

```json
{
  "campaign": "product-launch-q2",
  "tool": "higgsfield",
  "identity": {
    "brand": "brands/broomva.json",
    "character": "characters/founder.json",
    "style": "styles/cinematic-glass.json"
  },
  "settings": {
    "resolution": "1080p",
    "aspect_ratio": "9:16",
    "duration": "8s"
  },
  "prompts": [
    { "id": "intro", "text": "Engineer walks toward camera with confident smile, office background" },
    { "id": "demo", "text": "Hands typing on mechanical keyboard, code on screen, close-up" },
    { "id": "cta", "text": "Looking directly at camera, gesturing toward viewer, warm expression" }
  ]
}
```

### Running a Batch

```bash
# From Claude Code, invoke the skill:
# "autopilot: batch generate from campaign brief product-launch-q2"

# The loop will:
# 1. Load session for the specified tool
# 2. Load compiled identity files
# 3. Assemble each prompt with identity context
# 4. Generate sequentially (respecting tool rate limits)
# 5. Download and organize all results
# 6. Write manifest.json
```

### Error Handling

| Error | Recovery |
|-------|----------|
| Session expired | Auto-reload session file; if still invalid, prompt user to re-authenticate |
| Generation timeout (>5 min) | Mark as failed in manifest, move to next prompt, retry failed at end |
| Rate limited | Back off for 60s, then retry with exponential increase up to 5 min |
| Download failed | Retry download 3x with 10s intervals; if still failing, save URL for manual download |
| Browser crashed | Relaunch browser, reload session, resume from last successful prompt |
| Network error | Wait 30s, check connectivity, retry; after 3 failures, pause and notify user |

## Adding New Tools

To add a new browser-based generation tool, create a tool adapter with these components:

```
Tool Adapter Interface:
  1. login_url        — URL to navigate for authentication
  2. dashboard_url    — URL that confirms successful auth
  3. create_url       — URL for the generation page
  4. prompt_selector  — CSS selector for the prompt input field
  5. submit_selector  — CSS selector for the generate/submit button
  6. result_selector  — CSS selector for the completed result element
  7. download_action  — How to download the result (click selector, or extract src URL)
  8. settings_map     — Map of setting names to CSS selectors (resolution, duration, etc.)
  9. rate_limit       — Minimum seconds between generations
  10. typical_wait    — Expected generation time for timeout calculation
```

Example adapter for a new tool:

```json
{
  "name": "ideogram",
  "login_url": "https://ideogram.ai/login",
  "dashboard_url": "https://ideogram.ai/t/explore",
  "create_url": "https://ideogram.ai/t/explore",
  "prompt_selector": "textarea[placeholder*='Describe']",
  "submit_selector": "button[data-testid='generate-button']",
  "result_selector": "div[data-testid='generation-result'] img",
  "download_action": "extract_src",
  "settings_map": {
    "aspect_ratio": "button[data-value='{value}']",
    "style": "button[data-style='{value}']"
  },
  "rate_limit": 15,
  "typical_wait": 30
}
```

## API-First Fallback

When a tool offers a public API, the autopilot **prefers the API** over browser automation. Browser automation is the fallback for tools without APIs or when API access is restricted.

| Tool | API Available? | Autopilot Strategy |
|------|---------------|-------------------|
| Higgsfield | No public API | Browser only |
| Weavy | No public API | Browser only |
| Artlist | Search API only | API for search, browser for download |
| Runway | API (waitlist) | API when available, browser fallback |
| Pika | No public API | Browser only |
| Gemini/Veo | Full API | API-first (via /content-creation) |
| fal.ai | Full API | API-first (via /content-creation) |

See [references/generation-loops.md](references/generation-loops.md) for detailed API-first patterns.

## Compounding Skills

| Skill | How Autopilot Uses It |
|-------|----------------------|
| `/content-creation` | Provides compiled prompts and style briefs; receives generated assets |
| `/content-engine-dna` | Supplies compiled identity (brands, characters, styles) |
| `/content-engine-loop` | Triggers batch generation runs as part of campaign execution |
| `/agent-browser` | Underlying browser automation primitives |
| `/brand-icons` | Brand assets for consistent visual identity in prompts |
| `/brainrot-for-good` | Scene specs that become generation prompts for avatar videos |

## Reference Files

- [references/playwright-setup.md](references/playwright-setup.md) — Playwright installation, headed/headless modes, session management, timeouts
- [references/tool-sessions.md](references/tool-sessions.md) — Per-tool authentication persistence, session storage, expiry, refresh
- [references/generation-loops.md](references/generation-loops.md) — Batch generation patterns, API-first logic, manifest format, retry strategies
