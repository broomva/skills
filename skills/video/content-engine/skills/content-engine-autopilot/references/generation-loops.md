# Generation Loops — Batch Generation Patterns

How the content engine autopilot executes batch generation across browser-based tools, with API-first fallback logic, prompt injection patterns, completion detection, and manifest tracking.

## API-First with Browser Fallback

The autopilot always prefers API access over browser automation. APIs are faster, more reliable, and easier to batch. Browser automation is reserved for tools that lack APIs or where API access is restricted.

### Decision Tree

```
For each generation task:
  1. Does this tool have a usable API?
     ├─ YES → Use API directly (skip browser entirely)
     │   └─ API call fails?
     │       ├─ Rate limited → back off and retry via API
     │       ├─ Auth error → refresh API token, retry
     │       └─ API down → fall back to browser
     └─ NO → Use browser automation
         └─ Session valid?
             ├─ YES → headless batch
             └─ NO → headed setup → save session → headless batch
```

### API-First Tools

These tools should **never** use browser automation under normal conditions:

| Tool | API | SDK / Client |
|------|-----|-------------|
| **Gemini / Nano Banana** | `generativelanguage.googleapis.com` | `@google/genai` — `gemini-3.1-flash-image` for images |
| **Veo 3.1** | `generativelanguage.googleapis.com` | `@google/genai` — `veo-3.1-generate-preview` for video |
| **fal.ai** | `queue.fal.run/{model}` | `@fal-ai/client` — 600+ models via one API |
| **ElevenLabs** | `api.elevenlabs.io/v1` | `elevenlabs` npm — TTS and voice cloning |
| **Replicate** | `api.replicate.com/v1` | `replicate` npm — open-source model hosting |

```typescript
// Example: API-first generation with Veo 3.1
import { GoogleGenAI } from "@google/genai";
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

const response = await ai.models.generateVideos({
  model: "veo-3.1-generate-preview",
  prompt: compiledPrompt,
  config: {
    aspectRatio: "16:9",
    numberOfVideos: 1,
    durationSeconds: 8,
    personGeneration: "allow_adult",
    includeAudio: true,
  },
});

// Poll for completion
let operation = response;
while (!operation.done) {
  await new Promise(r => setTimeout(r, 10_000));
  operation = await ai.operations.get({ operationName: operation.name });
}

// Download result
const videoData = operation.response.generatedVideos[0].video.data;
fs.writeFileSync(outputPath, Buffer.from(videoData, 'base64'));
```

### Browser-Only Tools

These tools have no usable API and require browser automation:

| Tool | Why No API | Browser Strategy |
|------|-----------|-----------------|
| **Higgsfield** | No public API | Full browser automation with session persistence |
| **Weavy** | No public API | Full browser automation |
| **Pika** | No public API | Full browser automation |
| **Udio** | No public API | Full browser automation |
| **Canva** | API exists but limited to templates | Browser for creative generation |

### Hybrid Tools

Some tools have partial API coverage:

| Tool | API Coverage | Hybrid Strategy |
|------|-------------|----------------|
| **Artlist** | Search API, no download API | API for finding assets, browser for downloading |
| **Runway** | API exists (Gen-3 Turbo) but waitlisted | API when available, browser fallback |

## Compiled Identity Injection

Every generation prompt is assembled from the compiled identity before injection into the tool. This ensures brand consistency across all generated assets.

### Identity Assembly Pipeline

```
1. LOAD identity components:
   brand   ← knowledge/compiled/brands/{brand}.json
   char    ← knowledge/compiled/characters/{character}.json
   style   ← knowledge/compiled/styles/{style}.json

2. MERGE into prompt context:
   style_prefix  = style.prompt_prefix    # "Cinematic 4K, shallow DOF, ..."
   char_context  = char.visual_description # "Dark-haired engineer, glasses, ..."
   brand_suffix  = brand.visual_language   # "Deep navy (#0a0a12) accents, ..."

3. ASSEMBLE final prompt:
   "{style_prefix}. {scene_brief}. Character: {char_context}. {brand_suffix}"

4. ADAPT for tool:
   - Higgsfield: prompt + face_reference_url (character image)
   - Weavy: prompt + color_palette (brand hex values)
   - Artlist: search_query (derived from scene_brief keywords)
```

### Example Assembly

Given:
- **Brand**: `broomva` — deep navy, glass effects, clean typography
- **Character**: `founder` — dark hair, glasses, casual-professional
- **Style**: `cinematic-glass` — 4K, shallow DOF, warm lighting
- **Scene brief**: "presenting at a standing desk with dual monitors"

Assembled prompt for Higgsfield:
```
Cinematic 4K, shallow depth of field, warm golden hour lighting through floor-to-ceiling
windows. A confident software engineer (dark hair, glasses, casual-professional attire)
presenting at a standing desk with dual monitors showing colorful code. Camera: medium
close-up, slight push-in. Color grade: deep navy (#0a0a12) shadows, warm highlights,
subtle lens flare. Clean, minimal environment.
```

### Tool-Specific Prompt Adaptation

Each tool has different prompt conventions and limits:

| Tool | Max Prompt Length | Prompt Style |
|------|------------------|-------------|
| Higgsfield | ~500 chars | Descriptive, visual, include character details |
| Weavy | ~300 chars | Concise, keyword-heavy, style-focused |
| Artlist | ~100 chars (search) | Search keywords, genre tags |
| Runway | ~500 chars | Cinematic language, camera movement verbs |
| Pika | ~500 chars | Action-oriented, style modifiers |
| Udio | ~200 chars | Musical genre, mood, tempo, instrumentation |

The assembly pipeline truncates or reformats the prompt to match each tool's expectations.

## Generation Loop Architecture

### Single-Tool Loop

```
INIT:
  session = loadSession(tool)
  identity = loadIdentity(campaign.identity)
  manifest = createManifest(campaign)
  context = launchBrowser(session)

LOOP (for each prompt in campaign.prompts):
  page = context.newPage()
  page.goto(tool.create_url)
  
  // Inject compiled prompt
  prompt = assemblePrompt(identity, prompt.text)
  page.fill(tool.prompt_selector, prompt)
  
  // Configure settings
  for (setting, value) in campaign.settings:
    page.click(tool.settings_map[setting].replace('{value}', value))
  
  // Submit generation
  page.click(tool.submit_selector)
  
  // Wait for completion (with timeout)
  page.waitForSelector(tool.result_selector, { timeout: tool.typical_wait * 2 })
  
  // Download result
  download = page.waitForEvent('download')
  page.click(tool.download_selector)
  outputPath = saveDownload(download, campaign.output_dir, tool.name, prompt.id)
  
  // Update manifest
  manifest.addAsset({
    id: prompt.id,
    tool: tool.name,
    prompt: prompt.text,
    compiled_prompt: prompt,
    file: outputPath,
    status: 'completed'
  })
  
  page.close()
  
  // Rate limit pause
  sleep(tool.rate_limit * 1000)

FINALIZE:
  manifest.computeStats()
  manifest.save(campaign.output_dir + '/manifest.json')
  context.close()
```

### Multi-Tool Loop

When a campaign uses multiple tools, run them sequentially (not in parallel) to avoid session conflicts:

```
for each tool in campaign.tools:
  runSingleToolLoop(tool, campaign.prompts.filter(p => p.tool === tool.name))
```

**Exception**: API-based and browser-based tools can run in parallel because they do not share browser state.

```
parallel:
  - API loop: Veo 3.1 (video clips)
  - API loop: Nano Banana (hero images)
sequential after APIs:
  - Browser loop: Higgsfield (avatar videos)
  - Browser loop: Weavy (motion graphics)
```

## Completion Detection Patterns

### Pattern 1: Element Appearance

Wait for a result element to appear in the DOM.

```typescript
await page.waitForSelector('div.generation-result video', { 
  state: 'attached',
  timeout: 300_000 
});
```

**Used by**: Higgsfield (video player), Pika (result card)

### Pattern 2: Progress Bar

Poll a progress indicator until it reaches 100%.

```typescript
let progress = 0;
while (progress < 100) {
  const progressText = await page.textContent('.progress-bar-text');
  progress = parseInt(progressText.replace('%', ''));
  await page.waitForTimeout(5000);
}
```

**Used by**: Runway (progress percentage)

### Pattern 3: Button State Change

Wait for a download button to become enabled (transitions from disabled/loading to clickable).

```typescript
await page.waitForSelector('button.download:not([disabled])', { 
  timeout: 300_000 
});
```

**Used by**: Weavy (download button), Artlist (download button)

### Pattern 4: URL Change

The tool redirects to a results page when generation is complete.

```typescript
await page.waitForURL('**/results/**', { timeout: 300_000 });
```

**Used by**: Some tools redirect from `/create` to `/results/{id}`

### Pattern 5: Network Idle

Wait for all network requests to settle (generation backend has finished).

```typescript
await page.waitForLoadState('networkidle', { timeout: 300_000 });
```

**Caution**: This is a weak signal. Background analytics and websocket connections may prevent network idle. Use as a secondary check combined with element appearance.

## Retry Strategy

### Per-Generation Retry

```
attempt = 0
max_retries = 3

while attempt < max_retries:
  try:
    result = generate(prompt)
    manifest.addAsset(result, status='completed')
    break
  catch TimeoutError:
    attempt += 1
    log("Generation timed out, retry {attempt}/{max_retries}")
    page.reload()  // Reload page to reset state
  catch SelectorError:
    manifest.addAsset(prompt, status='selector_failure')
    screenshot(page, debug_dir)
    break  // Don't retry selector failures (needs adapter update)
  catch AuthError:
    refreshSession(tool)
    attempt += 1
  catch RateLimitError:
    sleep(60 * attempt)  // Linear backoff: 60s, 120s, 180s
    attempt += 1

if attempt >= max_retries:
  manifest.addAsset(prompt, status='failed')
```

### End-of-Batch Retry

After completing all prompts, retry any that failed with transient errors:

```
failed = manifest.assets.filter(a => a.status === 'failed' && a.error_type !== 'selector_failure')
if failed.length > 0:
  log("Retrying {failed.length} failed generations")
  for prompt in failed:
    retryGenerate(prompt)
```

## Manifest Tracking

### Manifest Lifecycle

```
1. CREATE manifest at batch start (campaign metadata, empty assets array)
2. UPDATE manifest after each generation (append asset with status)
3. COMPUTE stats at batch end (totals, success rate, timing)
4. SAVE manifest to campaign output directory
5. READ manifest for:
   - Resume interrupted batches
   - Performance tracking (which tool/style performed best)
   - Asset inventory for downstream skills (/content-engine-loop)
```

### Manifest Fields Reference

```json
{
  "campaign_id": "string — unique campaign identifier",
  "created_at": "ISO 8601 timestamp",
  "completed_at": "ISO 8601 timestamp (null if in progress)",
  "identity": {
    "brand": "string — brand identity file path",
    "style": "string — style preset file path",
    "character": "string — character identity file path"
  },
  "tools_used": ["array of tool names"],
  "assets": [
    {
      "id": "string — prompt ID from campaign brief",
      "tool": "string — generation tool name",
      "prompt": "string — original prompt text from brief",
      "compiled_prompt": "string — full prompt after identity assembly",
      "settings": { "object — tool-specific settings" },
      "status": "completed | failed | timeout | selector_failure | skipped",
      "error": "string — error message if failed (null if completed)",
      "error_type": "string — error classification (null if completed)",
      "retry_count": "number — how many retries were attempted",
      "files": {
        "raw": "string — relative path to raw download",
        "upscaled": "string | null — relative path to upscaled version",
        "graded": "string | null — relative path to color-graded version"
      },
      "generated_at": "ISO 8601 timestamp",
      "generation_time_seconds": "number — wall clock time",
      "metadata": {
        "file_size_bytes": "number",
        "duration_seconds": "number (for video/audio)",
        "resolution": "string (for images/video, e.g. '1920x1080')",
        "format": "string (e.g. 'mp4', 'png', 'wav')"
      }
    }
  ],
  "stats": {
    "total_requested": "number",
    "completed": "number",
    "failed": "number",
    "skipped": "number",
    "success_rate": "number (0-1)",
    "total_generation_time_seconds": "number",
    "average_generation_time_seconds": "number",
    "total_output_size_bytes": "number"
  }
}
```

### Using Manifests Downstream

The `/content-engine-loop` skill reads manifests to:
- **Track asset inventory**: Which assets are available for distribution
- **Measure tool performance**: Which tool produces the best results for which scene type
- **Feed performance data**: Correlate asset provenance with engagement metrics
- **Resume campaigns**: Pick up where an interrupted batch left off

```bash
# Find all manifests from recent campaigns
find ~/.content-engine/output/ -name "manifest.json" -mtime -7

# Count completed assets across campaigns
jq -s '[.[].stats.completed] | add' ~/.content-engine/output/*/manifest.json

# Find failed generations that need retry
jq '.assets[] | select(.status == "failed")' ~/.content-engine/output/*/manifest.json
```

## Rate Limiting

### Per-Tool Rate Limits

| Tool | Generations/Hour | Min Interval | Credits/Gen |
|------|-----------------|-------------|-------------|
| Higgsfield | ~20 (free tier) | 15s | 1 credit |
| Weavy | ~30 | 10s | Subscription-based |
| Artlist | Unlimited (search), ~100 downloads/day | 5s | Subscription-based |
| Runway | ~10 (depends on plan) | 30s | 10-40 credits |
| Pika | ~20 (free tier) | 15s | 1 credit |
| Udio | ~20 | 15s | 1 credit |
| Veo 3.1 (API) | ~60/min | 1s | Pay-per-use |
| Nano Banana (API) | ~500/day (free) | 0.5s | Free tier |

### Rate Limit Enforcement

The loop enforces minimum intervals between generations:

```
after each generation:
  elapsed = now() - generation_start_time
  remaining_wait = tool.rate_limit - elapsed
  if remaining_wait > 0:
    sleep(remaining_wait)
```

For API tools, respect HTTP `Retry-After` headers and implement exponential backoff on 429 responses.
