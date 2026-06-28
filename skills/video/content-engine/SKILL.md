---
name: content-engine
category: video
description: "Full-stack AI content studio — orchestrates visual DNA compilation, cinematic generation (via Higgsfield CLI or MCP), browser-automated tool execution, and multi-platform distribution into a unified content pipeline. Compiles brand identity, character sheets, and style guides into persistent knowledge (Karpathy compile-then-query pattern), then generates premium cinematic content using Higgsfield (30+ models including Soul V2, Nano Banana 2, Veo 3.1, Kling 3.0, Seedance 2.0, Flux 2), Soul Cinema, Weavy, and ComfyUI with consistent character identity and intentional visual direction. Triggers on: 'content engine', 'generate campaign', 'compile brand', 'cinematic content', 'AI content studio', 'batch generate', 'content pipeline', 'visual DNA', 'character consistency', 'higgsfield', 'marketing studio', 'product photoshoot', 'soul character'."
---

# Content Engine

Full-stack AI content studio: compile visual identity once, generate premium content at scale, distribute everywhere.

```
COMPILE → GENERATE → POST-PRODUCE → DISTRIBUTE → MEASURE → REFINE
```

## Commands

| Command | What it does |
|---------|-------------|
| `/content-engine compile` | Raw assets → compiled visual DNA (brand, character, style) |
| `/content-engine lint` | Health-check compiled knowledge for consistency |
| `/content-engine generate` | Create content using compiled identity + scene brief |
| `/content-engine autopilot setup {tool}` | Save browser session for a generation tool |
| `/content-engine autopilot run` | Batch generation via browser automation |
| `/content-engine campaign {brief}` | Full pipeline: compile → generate → distribute |
| `/content-engine loop` | Compound existing skills for distribution |

## Architecture

Four sub-skills, each handling one layer:

```
[content-engine-dna]       Visual DNA Compiler
        ↓                  raw/ → compiled/ (brand DNA, character sheets, style guides)
[content-engine-cinema]    Cinematic Generation Layer
        ↓                  compiled identity → tool-specific prompts → generation
[content-engine-autopilot] Browser Orchestration
        ↓                  Playwright drives tools OR API calls → organized output
[content-engine-loop]      Content Loop + Distribution
                           compounds /blog-post + /content-creation + /social-intelligence
```

## Quick Start

### 1. Compile Brand Identity

Drop reference assets into `knowledge/raw/`:
- Brand campaign photos → `knowledge/raw/brand-assets/`
- Character face references → `knowledge/raw/character-refs/`
- Style inspiration (mood boards, reference reels) → `knowledge/raw/style-inspiration/`

Then compile:
```
/content-engine compile
```

This analyzes all raw assets via Gemini multimodal and produces compiled identity files in `knowledge/compiled/` with tool-specific prompt fragments.

### 2. Generate Content

Write a scene brief or use a campaign plan:
```
/content-engine generate --brand acme --character luna --scenes 5 --format reels
```

The engine:
1. Reads compiled identity (brand DNA + character sheet + style guide)
2. Selects the best tool per the tool priority matrix
3. Injects compiled identity into tool-specific prompts
4. Generates via API (fal.ai, @google/genai) or browser automation
5. Runs post-production (upscale → grade)
6. Organizes output with manifest.json tracking

### 3. Run a Full Campaign

```
/content-engine campaign "Mediterranean lifestyle, 10 summer scenes, golden hour, reels + carousel"
```

Orchestrates all four skills end-to-end: compile (if needed) → generate scenes → post-produce → adapt for platforms → distribute.

### 4. Distribute

```
/content-engine loop
```

Compounds existing skills for multi-platform distribution:
- `/blog-post` — Writing + 6 platform adaptations
- `/content-creation` — TTS, Remotion video, media pipeline
- `/social-intelligence` — Distribution + engagement monitoring
- `/brainrot-for-good` — High-retention short-form video
- `/brand-icons` — OG images, social cards

## Setup & Prerequisites

### Required

```bash
# Check prerequisites
echo "=== Required ==="
which ffmpeg && echo "ok ffmpeg" || echo "MISSING: brew install ffmpeg"
echo ""
echo "=== API Keys ==="
[ -n "$GEMINI_API_KEY" ] && echo "ok GEMINI_API_KEY" || echo "MISSING: needed for Gemini analysis + Veo 3.1"
[ -n "$FAL_KEY" ] && echo "ok FAL_KEY" || echo "MISSING: needed for Nano Banana 2, Kling via fal.ai"
echo ""
echo "=== Higgsfield CLI (recommended for agent workflows) ==="
which higgsfield && echo "ok higgsfield $(higgsfield version 2>/dev/null | head -1)" || echo "MISSING: curl -fsSL https://raw.githubusercontent.com/higgsfield-ai/cli/main/install.sh | sh"
echo ""
echo "=== Browser Automation ==="
which agent-browser && echo "ok agent-browser" || echo "MISSING: needed for autopilot mode"
```

### Higgsfield: two integration paths

Higgsfield offers BOTH a CLI and an MCP. Pick based on your runtime:

| Runtime | Recommended path | Why |
|---------|------------------|-----|
| **Claude Code, Codex, agent-browser, scripts** | **higgsfield CLI** + the `higgsfield-*` skills | Per Higgsfield's own guidance: "If you are using Claude Code or Codex, it's better to use the CLI." Direct programmatic access, scriptable, integrates with the skill bundle. |
| **Claude Desktop, web Claude, IDE plugins** | **Higgsfield MCP** at `https://mcp.higgsfield.ai` | One-click connector; UI-native; no CLI install. Can't be scripted. |

**CLI path (recommended for content-engine):**
```bash
# Install
curl -fsSL https://raw.githubusercontent.com/higgsfield-ai/cli/main/install.sh | sh

# Auth (interactive, opens browser)
higgsfield auth login

# Verify
higgsfield account status

# Capabilities exposed via three skill-level wrappers:
#   higgsfield-generate         — 30+ models (Nano Banana 2, Soul V2, Veo 3.1, Kling 3.0, Seedance 2.0, Flux 2)
#   higgsfield-product-photoshoot — Brand-quality product images with mode-specific enhancement
#   higgsfield-soul-id          — Train Soul Character refs for consistent face/identity
```

**MCP path (for Claude Desktop):**
1. Open Claude settings → Connectors → Add custom connector
2. Name: `Higgsfield`
3. URL: `https://mcp.higgsfield.ai`
4. Click Add → Connect → authenticate via Higgsfield account

Both paths use the same Higgsfield credit pool. No API key needed for either; auth is via your Higgsfield account.

### Optional (enhance quality)

- **Topaz Gigapixel AI** — CLI upscaling (falls back to Real-ESRGAN)
- **ComfyUI** — Local node-based pipelines with LoRA style-locking
- **Weavy account** — Scene variation with character consistency
- **Artlist.io** — AI-powered music matching

### Tool Session Setup

For browser-automated tools (legacy path; prefer the CLI when available):
```
/content-engine autopilot setup higgsfield   # browser fallback if CLI not available
/content-engine autopilot setup weavy
```

This launches Chrome, you log in manually, and the session is saved for future automated use.

## Knowledge Architecture

### Karpathy Compile-Then-Query Pattern

```
knowledge/
├── raw/              # Immutable source material (never modified by LLM)
│   ├── brand-assets/     # Campaign photos, logos, style guides
│   ├── character-refs/   # Face photos, pose references
│   ├── style-inspiration/# Mood boards, reference reels
│   └── scene-briefs/     # Scene descriptions
├── compiled/         # LLM-compiled identity files (the "wiki")
│   ├── brands/           # Per-brand DNA (.md)
│   ├── characters/       # Per-character sheets (.md)
│   └── styles/           # Compiled style guides (.md)
└── schema.md         # Compilation rules + templates
```

**raw/** is source code. **compiled/** is executable. The LLM is the compiler.

Every compiled file:
- Traces provenance to raw sources
- Contains tool-specific prompt fragments
- Is human-reviewable Markdown
- Gets actively maintained via lint

### Mapping to Existing Patterns

| Content Engine | Karpathy Wiki | MemPalace | Broomva Knowledge Graph |
|---------------|--------------|-----------|----------------------|
| `raw/` | `raw/` | — | Layer 2 (raw extracts) |
| `compiled/` | `wiki/` | Rooms/Closets | Layer 3 (entity pages) |
| `schema.md` | `CLAUDE.md` | Wings/Halls | CLAUDE.md |
| Feedback loop | Linting pass | Tunnels | Layer 4 (synthesis) |

## Tool Priority Matrix

| Task | Best Tool | Fallback | Path |
|------|-----------|----------|------|
| Cinematic start frame | Soul Cinema (`higgsfield-generate --model soul_v2`) | Nano Banana Pro | CLI |
| Character consistency | Nano Banana Pro | SD + LoRA | CLI / fal.ai |
| Custom face/identity training | `higgsfield-soul-id` (Soul Character training) | LoRA fine-tuning | CLI |
| Branded product photoshoot | `higgsfield-product-photoshoot` (mode-specific enhancement) | Nano Banana + manual prompt | CLI |
| Marketing Studio (avatar + product ad) | `higgsfield-generate --model marketing_studio_video` | Veo 3.1 with prompt engineering | CLI |
| Multi-angle generation | Nano Banana 2 | Weavy | CLI / fal.ai |
| Scene variation | Weavy | Nano Banana + scene prompt | Browser |
| Video from keyframe | Veo 3.1 / Seedance 2.0 (via `higgsfield-generate`) | Kling | CLI |
| Motion transfer | Kling | Wan | Browser + ComfyUI |
| Upscaling | Topaz Gigapixel | Real-ESRGAN | CLI |
| Color grading | Lightroom | ffmpeg LUT | CLI/Browser |
| AI music | Artlist.io | Suno | Browser |
| Intent captions | OpenCaptions | ffmpeg burn-in | CLI (future) |

## Generation Modes

**Mode 1: API-First** (fastest, programmatic — preferred for agent workflows)
- **higgsfield CLI** (via `higgsfield-generate`, `higgsfield-product-photoshoot`, `higgsfield-soul-id`) → 30+ models including Soul V2, Nano Banana 2, Veo 3.1, Kling 3.0, Seedance 2.0, Flux 2, GPT Image 2; plus Marketing Studio (avatar + product ad modes); plus Soul Character training
- fal.ai → Nano Banana 2, Kling, Veo (alternate provider when models overlap)
- @google/genai → Veo 3.1, Gemini image (Google-native path)
- All three callable directly from Claude Code, no browser needed

**Mode 2: MCP-driven** (for Claude Desktop / IDE plugins)
- Higgsfield MCP at `https://mcp.higgsfield.ai` — same models, GUI-native auth, can't be scripted from Claude Code
- ComfyUI MCP (planned extension)

**Mode 3: Browser-Automated** (tools without APIs or MCP)
- Playwright drives Weavy, Artlist, Soul Cinema (legacy — prefer CLI now)
- Auth persisted via saved session state
- Batch generation with organized output

**Mode 4: Local Pipeline** (maximum control)
- ComfyUI + Stable Diffusion + LoRA
- Full node-based control over every generation step
- Topaz CLI for upscaling

**Mode 3: Local Pipeline** (maximum control)
- ComfyUI + Stable Diffusion + LoRA
- Full node-based control over every generation step
- Topaz CLI for upscaling

## Output Organization

```
output/{campaign-slug}/
├── raw/          # Direct generation output
├── upscaled/     # After Topaz/Real-ESRGAN pass
├── graded/       # After color grading
└── manifest.json # Prompts, identity refs, tool used, timestamps
```

## Extension Points

Extensions live in `extensions/`. Each extension:
- Has its own SKILL.md declaring which pipeline stage it hooks into
- Hook points: pre-generation, post-generation, post-production, distribution
- Can read from `compiled/` but only writes to its own output namespace
- Registered in `extensions/README.md`

### Planned Extensions
- **OpenCaptions** — Intent-driven captions (post-production hook)
- **ComfyUI MCP** — Direct tool calls for node pipelines
- **LoRA Training** — Compiled DNA as training data for custom models

## Reference Library — distilled craft

Deep, copy-paste-ready craft references live alongside each sub-skill. The cluster below was distilled from the full **AI Video Creators** course (BRO-1525 — 12.7 h video + 54 lessons; source playbook in `broomva/workspace docs/reference/ai-video-creators-course/`). Load the one that matches the task; the **prompt structure and craft laws are durable** even as model versions rotate.

| Reference | Sub-skill | What it gives |
|-----------|-----------|---------------|
| `references/ai-video-prompt-packs.md` | cinema | The transferable prompt-craft laws (image/video/motion formulas, 5 universal control levers, JSON-by-model, camera→look cheat sheet) + verbatim copy-paste packs (identity-lock, image-to-image product integration, motion w/ strict negatives, master upscale, ChatGPT 3-step content engine, lip-sync, image-editing). |
| `references/audio-sound-design.md` | cinema | Audio + sound-design + edit craft — the trailer arc, 3–5 layer named-role stack, verbatim ElevenLabs SFX prompts, the A/B mute-test gate, rhythm-before-sound editing, CapCut export discipline. |
| `references/cinematic-prompting.md` → §AVCC | cinema | SHOT+LENS+LIGHT+TEXTURE+COMPOSITION+STYLE formula, NBP Object→Context→Technical, the 5 control levers, 7 aesthetics + meta-messages, shot/lens reference tables, the taste-training loop. |
| `references/motion-animation.md` → §AVCC | cinema | Kling model-tier element budgets + model-first rule, Subject+Action+Context+Style, TTV-vs-I2V, motion-endpoint/99% hang, count-nouns overload rule, negative constraints, the Constraint Sandwich, reverse-motion trick. |
| `references/visual-dna-framework.md` | dna | The art-direction layer: Meaning→Trust→Conversion, the Visual DNA Pyramid, Brand Core, the full Meaning Map dictionary, 5 amateur→premium rules, the verbatim "Act as an art director" prompt, the 15-item Legend template. |
| `references/character-sheets.md` → §AVCC | dna | Character DNA = Master Prompt (Fixed DNA + Variable Context), "1 account = 1 character", hero-portrait-first + reuse, Hybrid-Reality face-swap, Kling Motion Control tripod rule, **+ product / non-human identity lock** (REF 1/2/3 integration, cross-scene verification). |
| `references/monetization-playbook.md` | loop | Creator→revenue: the 4 paths, exact pricing tiers + brand-placement packages, the 60-sec lead-qual script, margin rules, the micro-funnel + viral loop, Skool referral math. Grounds the Kleos proof-driven-demand engine. |

## Compounding Skills

This skill compounds on the existing broomva content ecosystem:

| Skill | Role |
|-------|------|
| `/content-creation` | Media pipeline (Nano Banana, Veo 3.1, TTS, Remotion) |
| `/blog-post` | Writing + 6 platform adaptations + publish.sh |
| `/social-intelligence` | Engagement loop + knowledge extraction |
| `/brainrot-for-good` | High-retention short-form video |
| `/brand-icons` | OG images, social cards |
| `/higgsfield-generate` | 30+ Higgsfield models, Marketing Studio (avatar + product ads) |
| `/higgsfield-product-photoshoot` | Brand-quality product images with mode-specific enhancement |
| `/higgsfield-soul-id` | Train Soul Character refs for consistent face/identity |
| `/agent-browser` | Playwright browser automation |
| `/arcan-glass` | Brand styling tokens |

## Research Sources

Built from analysis of:
- **viznfr** — Claude Code + Playwright autopilot, Nano Banana character sheets, brand DNA extraction
- **ohneis652** — ComfyUI node pipelines, LoRA style-locking, Soul Cinema start-frame doctrine, 25 design styles
- **AI Video Creators (Skool)** — fully captured & distilled (BRO-1525): ReelEngine/PromptEngine prompt craft, image-first pipeline, Visual-DNA art direction, character consistency, motion control, audio/edit craft, and the monetization playbook. See the Reference Library above + `broomva/workspace docs/reference/ai-video-creators-course/`.
- **MemPalace** — Spatial hierarchy, AAAK compression, MCP-native memory
- **Karpathy LLM Wiki** — raw/wiki/schema 3-layer architecture, compile-then-query, active linting
