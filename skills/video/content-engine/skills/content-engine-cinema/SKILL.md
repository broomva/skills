---
name: content-engine-cinema
description: "Cinematic Generation Layer — the taste and technique library for premium AI content. Codifies start-frame doctrine, camera style vocabulary (Anderson/Fincher/Nolan/Villeneuve/Kubrick), node pipeline architecture, scene generation formulas, and 25+ design styles with exact prompts. Tier-1 generation via Higgsfield CLI (30+ models — Soul V2, Nano Banana 2, Veo 3.1, Kling 3.0, Seedance 2.0, Flux 2, Marketing Studio). Triggers on: 'generate content', 'cinematic', 'create scene', 'start frame', 'style library', 'generate campaign', 'AI filmmaking', 'higgsfield generate', 'soul cinema', 'marketing studio'."
---

# Cinematic Generation Layer

The taste and technique library that turns AI generation tools into a coherent filmmaking system. This skill codifies the principles, workflows, and prompt engineering patterns that separate generic AI output from intentional, cinematic content.

## Core Doctrine: Start-Frame First

The single most important principle in AI video generation: **video quality is only as good as your initial image**. This comes from ohneis652's production experience and is validated across every major video model (Kling, Wan, Sora, Veo, Seedance).

The workflow is never "generate video from text." It is always:

```
Concept → Start Frame (image) → Motion (video) → Post-Production
```

A mediocre prompt with a perfect start frame produces better output than a perfect prompt with no image guidance. The start frame locks composition, lighting, color palette, character appearance, and camera position. The video model's job is reduced to adding motion to an already-excellent frame.

See [references/cinematic-prompting.md](references/cinematic-prompting.md) for the full start-frame doctrine.

## Camera Style Vocabulary

Every director has a visual signature. Encoding that signature into prompts produces results that feel intentional rather than random. The vocabulary below maps director aesthetics to prompt-level decisions.

| Director | Signature Look | Camera | Lighting | Color | Prompt Keywords |
|----------|---------------|--------|----------|-------|-----------------|
| **Wes Anderson** | Symmetrical compositions, pastel palettes, flat staging | Static, centered, planimetric | Soft, even, warm tungsten | Pastel yellows, pinks, teals, cream | `symmetrical composition, centered framing, pastel color palette, whimsical, flat staging, warm tungsten lighting` |
| **David Fincher** | Dark precision, clinical framing, desaturated | Slow dolly, locked tripod, overhead | Low-key, practical sources, sodium vapor | Desaturated, green-amber, cold | `desaturated color grade, dark shadows, clinical precision, cold blue-green tones, low-key lighting, overhead shot` |
| **Christopher Nolan** | IMAX scale, practical effects, blue-orange grade | Sweeping crane, handheld verité, IMAX wide | Natural + practical, golden hour | Blue-orange complementary, deep blacks | `IMAX wide angle, sweeping crane shot, blue-orange color grade, epic scale, natural lighting, deep blacks` |
| **Denis Villeneuve** | Vast negative space, geometric architecture, silence | Slow push-in, wide establishing, drone | Diffused overcast, hazy atmosphere | Muted earth tones, amber, grey | `vast negative space, geometric architecture, diffused atmospheric haze, muted earth tones, slow push-in, contemplative` |
| **Stanley Kubrick** | One-point perspective, symmetry, uncanny | Steadicam tracking, one-point corridors | Harsh top-light, candlelight | High contrast, selective saturation | `one-point perspective, symmetrical corridor, steadicam tracking shot, harsh overhead lighting, unsettling, high contrast` |
| **Wong Kar-wai** | Motion blur, neon reflections, step-printed | Handheld, canted angles, slow-motion | Neon, fluorescent, saturated practicals | Deep reds, greens, blues, warm skin | `neon reflections, motion blur, step-printed slow motion, saturated colors, handheld camera, intimate framing` |
| **Ridley Scott** | Smoke, volumetric light, tactile textures | Slow dolly, low angle, aerial | Volumetric beams, industrial haze | Cool steel, warm amber accents | `volumetric light beams, atmospheric smoke, industrial textures, slow dolly, low angle, cinematic anamorphic` |
| **Terrence Malick** | Magic hour, natural world, ethereal | Steadicam floating, wide nature | Golden hour exclusively, backlit | Warm golden, green, earth | `magic hour golden light, backlit silhouette, steadicam floating through nature, ethereal, natural world, wide angle` |

### Using the Vocabulary

Combine director keywords with subject and scene description. The director style replaces vague aesthetic instructions:

```
# Weak prompt
"A person walking down a hallway, cinematic"

# Strong prompt (Kubrick vocabulary)
"A person walking down a long symmetrical corridor, one-point perspective, 
steadicam tracking shot following from behind, harsh overhead fluorescent lighting, 
high contrast, institutional green walls, unsettling atmosphere, 35mm film grain"
```

## Node Pipeline Architecture

The pipeline is a chain of specialized tools, each handling one aspect of the generation process. This mirrors how a professional post-production pipeline works: each node does one thing well.

```
[SD/Flux Base] → [LoRA Style Lock] → [Multi-Angle/Pose] → [Motion/Video] → [Upscale] → [Color Grade]
     ↓                  ↓                    ↓                   ↓              ↓            ↓
  Raw image      Style-locked       Character turnaround     Animated      4K/8K res    Final look
  from prompt    to brand/era       or scene angles          sequence       output       film-ready
```

Each node is a discrete design decision. Removing or reordering nodes changes the output character. See [references/node-pipelines.md](references/node-pipelines.md) for the full ComfyUI implementation.

**Key nodes:**
1. **Base generation** (SD 3.5 / Flux / Nano Banana) -- raw creative output from prompt
2. **LoRA style lock** -- constrains output to a specific era, brand, or visual language
3. **Multi-angle expansion** (Nano Banana multi-view) -- generates turnarounds and alternate poses
4. **Motion synthesis** (Wan / Kling / Seedance) -- adds video motion from the locked frame
5. **Upscaling** (Topaz Gigapixel / Real-ESRGAN) -- resolution enhancement without artifact introduction
6. **Color grading** (ffmpeg LUT / Lightroom) -- final color science and look

## Scene Generation Formula

The viznfr method for photorealistic scene generation follows a strict four-step formula that ensures character consistency across scenes. See [references/realistic-scenes.md](references/realistic-scenes.md) for the full workflow.

```
Persona Definition → Character Sheet → Scene Description → Face Swap → Generate
```

1. **Persona**: demographic, personality, wardrobe style, environment
2. **Character sheet**: multi-angle reference with consistent features (generated via LoRA or multi-view)
3. **Scene description**: environment, action, lighting, camera angle, mood
4. **Face swap**: locks facial identity from character sheet onto scene output
5. **Generate**: final render with all constraints applied

## Tool Priority Matrix

Three tiers based on quality, speed, and cost. Always prefer the highest available tier.

| Priority | Image Gen | Video Gen | Upscaling | Color Grade |
|----------|-----------|-----------|-----------|-------------|
| **Tier 1: Higgsfield CLI** (default) | `higgsfield-generate --model soul_v2 / nano_banana_2 / flux_2` | `higgsfield-generate --model veo_3 / kling_3 / seedance_2` | Topaz Gigapixel CLI | Lightroom (preset batch) |
| **Tier 1 (alternates)** | Nano Banana 2 (`@google/genai`) | Veo 3.1 (`@google/genai`) | — | — |
| **Tier 2: Browser-automated** | Midjourney (via browser) | Kling 3 Pro (via fal.ai) | Topaz web UI | DaVinci Resolve |
| **Tier 3: Local pipeline** | ComfyUI + SD/Flux | ComfyUI + Wan/AnimateDiff | Real-ESRGAN CLI | ffmpeg + LUT files |

**Why Higgsfield CLI is the default Tier 1:** a single CLI auths once and exposes 30+ models (Soul V2, Nano Banana 2, Veo 3.1, Kling 3.0, Seedance 2.0, Flux 2, GPT Image 2, Marketing Studio). One credit pool, one auth flow, scriptable from Claude Code. Higgsfield's own guidance: "If you are using Claude Code or Codex, it's better to use the CLI" — confirmed by the bundled `higgsfield-generate`, `higgsfield-product-photoshoot`, `higgsfield-soul-id` skill wrappers.

### Generation Modes

**Mode 1: Higgsfield-first** (default — recommended for agent workflows):
- One CLI, 30+ models. Auth once via `higgsfield auth login`.
- **Image generation:**
  - Cinematic editorial / lifestyle: `higgsfield-generate --model soul_v2 --prompt "..."`
  - Character consistency / multi-angle: `higgsfield-generate --model nano_banana_2 --prompt "..."`
  - General photoreal: `higgsfield-generate --model flux_2 --prompt "..."`
  - Product photoshoot: invoke `higgsfield-product-photoshoot` skill (mode-specific brand-quality enhancement)
- **Video generation (start-frame first):**
  - Premium: `higgsfield-generate --model veo_3 --image <upload_id> --prompt "..."`
  - Cinematic motion: `higgsfield-generate --model kling_3 --image <upload_id>`
  - Multi-shot storytelling: `higgsfield-generate --model seedance_2 --image <upload_id>`
- **Soul Character training** for face/identity locking across a series: invoke `higgsfield-soul-id` skill.
- **Marketing Studio** for branded ads with avatar + product: `higgsfield-generate --model marketing_studio_video`.
- Best for: 90% of cinematic generation work. Skip the other modes unless you specifically need a model Higgsfield doesn't expose.

**Mode 2: Direct provider APIs** (fallback when Higgsfield is missing a model):
- `@google/genai` SDK for Nano Banana, Veo 3.1, Imagen
- `@fal-ai/client` for Kling, Sora, alternative Flux variants
- Use when: a specific provider exposes a model Higgsfield hasn't bundled, or when you want provider-direct billing

**Mode 3: Higgsfield MCP** (for Claude Desktop / web Claude):
- Add `https://mcp.higgsfield.ai` as a custom connector in Claude settings → Connectors
- Same 30+ models, same auth, GUI-driven
- Use when: not running Claude Code or Codex; the CLI path is preferred for those

**Mode 4: Browser-automated** (rare, for tools without API/MCP):
- Use `/agent-browser` to drive Midjourney, Weavy, Artlist, or other web-only tools
- Best for: music selection, premium one-offs in tools without programmatic access
- Note: Higgsfield Studio is now CLI-accessible; do not use the browser path for Higgsfield models anymore

**Mode 5: Local pipeline** (maximum control):
- ComfyUI with custom node graphs for full pipeline control
- LoRA training and application for brand-locked output
- Best for: brand content where you need bit-exact reproducibility, R&D on custom styles

### Cinema → Higgsfield workflow integration

The compounded workflow when content-engine-cinema dispatches a scene:

```
Concept (cinema scene brief)
  ↓
Camera-style vocabulary picked (Fincher / Nolan / Villeneuve / etc.)
  ↓
Style fragment + scene description merged into final prompt
  ↓
START FRAME: invoke higgsfield-generate --model soul_v2 (or nano_banana_2)
             → upload_id captured from output
  ↓
[Optional: invoke higgsfield-soul-id if face/identity needs to be locked]
  ↓
MOTION: invoke higgsfield-generate --model veo_3 / kling_3 --image <upload_id>
        → wait for job, capture video_url
  ↓
POST-PRODUCE: Topaz Gigapixel for upscale, Lightroom or ffmpeg LUT for grade
  ↓
Output to /content-engine/output/{campaign-slug}/raw/
  ↓
manifest.json updated with: prompt, model, upload_id, job_id, timestamp, identity_refs
```

Every node above is a single CLI invocation; no manual browser steps.

## Design Style Library

25+ codified design styles with exact prompt fragments. Each style is a reusable aesthetic recipe. See [references/style-library.md](references/style-library.md) for the complete library with example prompts and use cases.

**Selected styles:**

| Style | Visual Signature | Best For |
|-------|-----------------|----------|
| Flat Illustration | Bold shapes, minimal shadows, geometric | Explainer content, social cards |
| Neo 3D | Glossy materials, soft shadows, floating objects | Product showcases, app marketing |
| Brutalism | Raw concrete, exposed structure, monospace | Developer tools, infrastructure |
| Y2K | Chrome, gradients, bubble letters, translucent | Gen-Z targeting, nostalgia |
| Romantasy | Soft light, floral, painterly, warm | Lifestyle, wellness, editorial |
| Cybercore | Neon grids, holographic, dark backgrounds | Tech products, AI content |
| Vintage 80s | VHS grain, neon, synthwave, chrome text | Retro campaigns, music |
| Bauhaus | Primary colors, geometric, grid, sans-serif | Design tools, education |

## Motion and Animation

See [references/motion-animation.md](references/motion-animation.md) for the full motion technique guide.

**Key capabilities:**
- **Kling motion transfer**: use a reference video as a motion driver -- zero rigging, the model extracts motion and applies it to your character
- **Wan image-to-video**: animate a start frame with natural motion, best for subtle camera moves and environmental animation
- **Seedance 2.0**: multi-shot storytelling with character consistency across cuts
- **Camera control**: encode specific camera movements (dolly, pan, crane) into generation prompts

## Post-Production

See [references/upscaling-grading.md](references/upscaling-grading.md) for the upscaling and color grading pipeline.

**Output organization:**
```
assets/
  raw/           # Direct model output (never delete)
  upscaled/      # After Topaz or Real-ESRGAN
  graded/        # After LUT or Lightroom
  final/         # Delivery-ready files
```

## Reference Files

- [references/cinematic-prompting.md](references/cinematic-prompting.md) -- start-frame doctrine, camera vocabulary, prompt engineering
- [references/realistic-scenes.md](references/realistic-scenes.md) -- photorealistic scene generation formula, character consistency
- [references/node-pipelines.md](references/node-pipelines.md) -- ComfyUI node architecture, pipeline design
- [references/motion-animation.md](references/motion-animation.md) -- Kling motion transfer, Wan animation, Seedance multi-shot
- [references/style-library.md](references/style-library.md) -- 25+ design styles with prompt patterns
- [references/upscaling-grading.md](references/upscaling-grading.md) -- Topaz, Real-ESRGAN, ffmpeg LUT grading, output organization
