# Content Engine

Full-stack AI content studio — compile visual identity once, generate premium content at scale, distribute everywhere.

## What It Does

Content Engine treats visual identity (brand DNA, character sheets, style guides) as **compiled knowledge** — analyzed once from raw assets via Gemini multimodal, persisted as structured Markdown with tool-specific prompt fragments, and referenced by every generation session.

```
COMPILE → GENERATE → POST-PRODUCE → DISTRIBUTE → MEASURE → REFINE
```

## Architecture

Four skills, each handling one layer:

| Skill | Purpose |
|-------|---------|
| **content-engine-dna** | Visual DNA Compiler — raw assets → compiled identity files |
| **content-engine-cinema** | Cinematic Generation — start-frame doctrine, camera vocabulary, 25+ styles |
| **content-engine-autopilot** | Browser Orchestration — Playwright-driven batch generation |
| **content-engine-loop** | Content Loop — compounds existing distribution skills |

## Quick Start

### 1. Prerequisites

```bash
pip install google-genai    # Gemini multimodal analysis
brew install ffmpeg          # Video keyframe extraction
export GEMINI_API_KEY="..."  # Required
export FAL_KEY="..."         # For Nano Banana 2, Kling via fal.ai
```

### 2. Add Raw Assets

```
knowledge/raw/
├── brand-assets/{brand-name}/     ← Campaign photos, logos
├── character-refs/{char-name}/    ← Face photos, pose refs
└── style-inspiration/{style}/     ← Mood boards, references
```

### 3. Compile

```bash
python3 scripts/compile-dna.py              # Incremental
python3 scripts/compile-dna.py --force      # Full recompilation
python3 scripts/compile-dna.py --dry-run    # Preview
python3 scripts/compile-dna.py lint         # Health check
```

### 4. Generate (via Claude Code)

```
/content-engine generate --brand acme --character luna --scenes 5 --format reels
/content-engine campaign "Mediterranean lifestyle, 10 summer scenes, golden hour"
```

## Knowledge Architecture

Inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and [MemPalace](https://github.com/milla-jovovich/mempalace):

```
knowledge/
├── raw/        # Immutable source material (never modified by LLM)
├── compiled/   # LLM-compiled identity files (the "executable")
└── schema.md   # Compilation rules
```

**raw/** is source code. **compiled/** is executable. The LLM is the compiler.

## Tool Priority Matrix

| Task | Best Tool | Fallback |
|------|-----------|----------|
| Cinematic start frame | Soul Cinema (Higgsfield) | Nano Banana Pro |
| Character consistency | Nano Banana Pro | SD + LoRA |
| Scene variation | Weavy | Nano Banana + prompt |
| Video from keyframe | Veo 3.1 / Seedance 2.0 | Kling |
| Motion transfer | Kling | Wan |
| Upscaling | Topaz Gigapixel | Real-ESRGAN |

## Extension Points

Extensions hook into the pipeline at defined stages: pre-generation, post-generation, post-production, distribution. See [`extensions/README.md`](extensions/README.md).

Planned: **OpenCaptions** (intent-driven captions), **ComfyUI MCP**, **LoRA Training**.

## Research Sources

Built from analysis of industry creators and knowledge management frameworks:
- **viznfr** — Claude Code + Playwright autopilot, character consistency
- **ohneis652** — ComfyUI node pipelines, LoRA style-locking, Soul Cinema
- **Vidis AI** — Structured curriculum, ReelEngine/PromptEngine
- **Karpathy LLM Wiki** — Compile-then-query, active linting
- **MemPalace** — Spatial hierarchy, AAAK compression

## License

MIT — see [LICENSE](LICENSE).
