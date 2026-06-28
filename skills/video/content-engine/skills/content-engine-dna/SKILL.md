---
name: content-engine-dna
description: "Visual DNA Compiler -- compiles raw brand assets, character references, and style inspiration into persistent, structured identity files. Uses Gemini multimodal analysis to extract color palettes, composition rules, lighting patterns, and texture preferences. Generates tool-specific prompt fragments for Nano Banana Pro, Soul Cinema, Weavy, and ComfyUI. Inspired by Karpathy's LLM Wiki (compile-then-query) and MemPalace spatial hierarchy. Triggers on: 'compile brand', 'extract DNA', 'character sheet', 'style guide', 'compile identity', 'brand analysis'."
version: 1.0.0
author: broomva
tags:
  - visual-identity
  - brand-dna
  - character-consistency
  - style-locking
  - gemini-multimodal
  - content-engine
compounding:
  - content-engine-cinema
  - content-engine-autopilot
  - content-engine-loop
  - blog-post
  - content-creation
---

# content-engine-dna -- Visual DNA Compiler

The Visual DNA Compiler transforms raw visual assets (photos, mood boards, reference videos, brand guidelines, character references) into persistent, structured identity files. Every downstream generation session references these compiled files instead of re-deriving visual intent from scratch.

The core insight comes from two convergent patterns:

1. **Karpathy's LLM Wiki** -- treat visual identity like source code. Raw assets are the source. The LLM is the compiler. Compiled identity files are the executable. Schema rules enforce consistency. Active linting catches drift.

2. **MemPalace spatial hierarchy** -- organize compiled knowledge in a navigable structure (brands as wings, characters as rooms, styles as closets). The AAAK 30x compression pattern means a 200-image mood board becomes a 2-page brand DNA file that any tool can consume in a single context load.

The compiler is not a one-shot process. It is iterative: new raw assets trigger recompilation, performance feedback refines compiled prompts, and lint passes catch inconsistencies before they propagate to generated content.

---

## When to Invoke

- User drops reference images, mood boards, or brand assets into `knowledge/raw/`
- User says "compile brand", "extract DNA", "character sheet", "style guide"
- User says "compile identity" or "brand analysis"
- Before any generation session that needs character consistency or brand alignment
- When compiled files are stale (raw assets modified after last compilation timestamp)
- When `/content-engine lint` reports provenance errors or orphaned references

---

## Commands

### `/content-engine compile`

Full compilation pipeline. Scans `knowledge/raw/` for uncompiled or modified assets, analyzes them via Gemini multimodal, and writes structured identity files to `knowledge/compiled/`.

**Options:**

```bash
/content-engine compile                        # Full compile (all raw assets)
/content-engine compile --brand {slug}         # Compile specific brand only
/content-engine compile --character {slug}     # Compile specific character only
/content-engine compile --style {slug}         # Compile specific style only
/content-engine compile --incremental          # Only recompile changed raw assets
/content-engine compile --dry-run              # Preview what would be compiled
/content-engine compile --force                # Recompile everything, ignore timestamps
```

### `/content-engine lint`

Health-check compiled knowledge. Validates provenance, consistency, cross-linking, and tool-specific prompt freshness.

**Options:**

```bash
/content-engine lint                           # Lint all compiled files
/content-engine lint --brand {slug}            # Lint specific brand
/content-engine lint --fix                     # Auto-fix what can be fixed
/content-engine lint --strict                  # Fail on warnings (not just errors)
```

---

## Compilation Pipeline (6 Steps)

Each step is idempotent. The pipeline can be interrupted and resumed. All intermediate state is written to disk so crashes do not lose work.

### Step 1 -- Scan Raw Assets

Traverse `knowledge/raw/` and build a manifest of all source files:

```
knowledge/raw/
├── brand-assets/       # Campaign photos, logos, style guides, mood boards
├── character-refs/     # Face photos, pose references, body type refs
├── style-inspiration/  # Reference reels, screenshots, mood boards
└── scene-briefs/       # Scene descriptions, location photos
```

For each file, record:
- **Path**: relative to `knowledge/raw/`
- **Type**: image (png/jpg/webp), video (mp4/mov), document (md/pdf), directory
- **Hash**: SHA-256 of file contents (for change detection)
- **Last compiled**: timestamp from previous compilation run (if any)

**Change detection**: Compare current hash against hash stored in the compiled file's `sources` frontmatter. If different, mark for recompilation. If raw file is new (no corresponding compiled file), mark for initial compilation.

Output: `compile-manifest.json` (ephemeral, written to `.cache/content-engine/`).

### Step 2 -- Analyze via Gemini Multimodal

For each raw asset marked for compilation, send to Gemini for structured multimodal analysis. The analysis prompt extracts specific visual dimensions (full prompt spec in `references/brand-dna-extraction.md`).

**For images**, extract:
- **Color palette**: Dominant colors (hex values), accent colors, overall temperature (warm/cool/neutral), saturation level
- **Composition**: Rule of thirds / centered / golden ratio / negative space, subject placement, leading lines
- **Lighting**: Direction (front/side/rim/overhead), quality (hard/soft/diffused), temperature (kelvin estimate), contrast ratio
- **Texture**: Surface qualities (matte/glossy/film-grain/digital-clean), depth of field, bokeh character
- **Pose language**: Subject posture, gesture vocabulary, energy level (candid/editorial/lifestyle/cinematic)

**For videos**, first extract keyframes via ffmpeg:
```bash
ffmpeg -i input.mp4 -vf "select=eq(pict_type\,I)" -vsync vfill -q:v 2 keyframe_%04d.jpg
```
Then analyze keyframes as images plus:
- **Pacing**: Cut frequency, shot duration distribution
- **Camera movement**: Static / dolly / crane / handheld / tracking
- **Transitions**: Cut / dissolve / whip pan / match cut

**API call pattern** (using @google/genai):
```typescript
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: [
    { role: "user", parts: [
      { inlineData: { mimeType: "image/jpeg", data: base64Image } },
      { text: BRAND_DNA_EXTRACTION_PROMPT }
    ]}
  ]
});
```

The extraction prompt is defined in `references/brand-dna-extraction.md`. It produces structured JSON that maps directly to the compiled file sections.

### Step 3 -- Cross-Reference

Compare new analysis results against existing compiled files:

1. **Brand collision detection**: If a new brand analysis overlaps >70% with an existing brand DNA (by color palette and composition), flag for merge review rather than creating a duplicate.
2. **Character consistency check**: If a character reference produces identity traits that conflict with an existing character sheet (e.g., different eye color, different build), flag the conflict and ask the user to resolve.
3. **Style deduplication**: If a new style analysis matches an existing style guide (by camera language and color grammar), update the existing guide rather than creating a new one.
4. **Cross-linking**: Identify which characters belong to which brands, which styles apply to which brands, and set up `related` wikilinks in the compiled files.

### Step 4 -- Generate Tool-Specific Prompt Fragments

For each compiled identity, generate exact prompt text that reproduces the identity in each supported tool. This is the critical step that makes compiled knowledge actionable.

**Nano Banana Pro prompt fragment:**
```
[Character]: {name}, {age}, {ethnicity}, {build}. {distinguishing features}.
{default expression}. {energy/vibe}.
Wearing: {wardrobe defaults}.
Setting: {environment}.
Lighting: {lighting setup}.
```

**Soul Cinema / Higgsfield prompt fragment:**
```
Cinematic {shot_type} of {subject_description}.
{camera_movement}.
{lighting_direction} {lighting_quality} lighting, {color_temperature}.
{composition_rule}. {depth_of_field}.
Style reference: {director_style}.
```

**Weavy scene prompt fragment:**
```
{scene_description}
Character: {character_sheet_ref}
Environment: {environment_description}
Mood: {mood_keywords}
Lighting: {lighting_description}
Camera: {camera_angle}, {focal_length}
```

**ComfyUI node configuration fragment:**
```yaml
checkpoint: {base_model}
lora:
  name: {lora_name}
  weight: {lora_weight}
sampler: {sampler}
steps: {steps}
cfg: {cfg_scale}
positive: "{positive_prompt}"
negative: "{negative_prompt}"
```

Each fragment is tested mentally against the tool's known prompt grammar before being written. Anti-patterns (prompts that produce inconsistent results) are documented in the compiled file's Anti-Patterns section.

### Step 5 -- Write Compiled Files

Write structured Markdown files to `knowledge/compiled/`:

```
knowledge/compiled/
├── brands/{slug}.md          # Brand DNA files
├── characters/{slug}.md      # Character sheets
└── styles/{slug}.md          # Style guides
```

Each file follows its type-specific format (see Compiled File Formats below). Every compiled file includes:
- YAML frontmatter with provenance metadata
- SHA-256 hashes of all source files in the `sources` field
- Compilation timestamp
- Tool-specific prompt fragments
- Anti-patterns section

### Step 6 -- Verify Provenance

Post-write verification pass:

1. **Source integrity**: Every `sources` entry in compiled files points to an existing raw file
2. **Hash verification**: SHA-256 of each source file matches the hash recorded at compilation time
3. **Completeness**: Every raw asset directory has at least one corresponding compiled file
4. **Cross-link integrity**: All `[[wikilink]]` references in compiled files resolve to existing compiled files
5. **Prompt fragment validation**: Each tool-specific prompt fragment is syntactically valid for its target tool

Verification failures are logged to `.cache/content-engine/compile-report.json` and printed to stdout.

---

## Compiled File Formats

### Brand DNA (`compiled/brands/{slug}.md`)

```yaml
---
name: Brand Name
type: brand-dna
compiled: 2026-04-07T14:30:00Z
sources:
  - path: raw/brand-assets/campaign-photos/hero-01.jpg
    sha256: a1b2c3d4...
  - path: raw/brand-assets/campaign-photos/hero-02.jpg
    sha256: e5f6g7h8...
  - path: raw/brand-assets/logo/primary.svg
    sha256: i9j0k1l2...
tools: [nano-banana-pro, weavy, soul-cinema, comfyui]
related:
  - "[[characters/luna]]"
  - "[[styles/cinematic-warm]]"
status: active
---

# {Brand Name} -- Visual DNA

## Visual Identity

### Color Palette
| Role | Hex | Mood |
|------|-----|------|
| Primary | #2D3436 | Grounding, authority |
| Secondary | #DFE6E9 | Clean, spacious |
| Accent | #E17055 | Warmth, energy |
| Highlight | #FFEAA7 | Optimism, attention |

Temperature: warm-neutral
Saturation: medium (40-60%)

### Composition
- Primary rule: rule of thirds with subject at left intersection
- Negative space: generous (40%+ of frame)
- Leading lines: architectural, converging toward subject
- Depth layering: foreground element (blurred) + subject (sharp) + background (soft)

### Lighting
- Direction: 45-degree key, subtle fill from opposite
- Quality: soft, diffused (overcast or large softbox)
- Temperature: 5200K (warm daylight)
- Contrast ratio: 3:1 (natural, not dramatic)
- Rim light: present but subtle, warm tone

### Texture
- Surface: matte with subtle film grain (ISO 400 emulation)
- Depth of field: shallow (f/2.0-2.8 equivalent)
- Bokeh: smooth, circular
- Digital artifacts: none (clean processing)

### Pose Language
- Energy: relaxed confidence (not stiff, not over-animated)
- Gesture vocabulary: open hands, natural movement
- Eye contact: direct but soft
- Context: lifestyle/editorial hybrid

## Tool-Specific Prompts

### Nano Banana Pro
{exact prompt prefix for this brand's look}

### Soul Cinema
{exact prompt prefix for this brand's look}

### Weavy
{exact prompt prefix for this brand's look}

### ComfyUI
{node configuration for this brand's look}

## Anti-Patterns
- Avoid: harsh direct flash, cool-toned environments, centered symmetrical framing
- Avoid: over-saturated colors (saturation > 70%)
- Avoid: Dutch angles, extreme close-ups without context
- Avoid: pure white backgrounds (use warm off-white #FAF9F6)
```

### Character Sheet (`compiled/characters/{slug}.md`)

```yaml
---
name: Character Name
type: character-sheet
compiled: 2026-04-07T14:30:00Z
sources:
  - path: raw/character-refs/luna/face-front.jpg
    sha256: m3n4o5p6...
  - path: raw/character-refs/luna/face-3quarter.jpg
    sha256: q7r8s9t0...
nano_banana_ref: "nb-char-id-12345"
consistency_model: nano-banana-pro
lora_weights: null
face_embedding_hash: "sha256:u1v2w3x4..."
related:
  - "[[brands/acme]]"
  - "[[styles/editorial-warm]]"
status: active
---

# {Character Name} -- Character Sheet

## Identity
- **Age**: 28
- **Ethnicity**: Mixed (Southeast Asian / European)
- **Build**: Athletic-slim
- **Height impression**: Average-tall
- **Hair**: Dark brown, shoulder-length, natural wave
- **Eyes**: Dark brown, almond-shaped
- **Skin tone**: Medium olive (Fitzpatrick IV)
- **Distinguishing features**: Subtle freckles across nose bridge, defined jawline
- **Default expression**: Relaxed confidence, slight asymmetric smile
- **Energy/vibe**: Approachable professional, warm intelligence

## Consistency Anchors
- **Nano Banana Pro character sheet ID**: nb-char-id-12345
- **LoRA weights**: {path or null if using Nano Banana}
- **Face embedding hash**: sha256:u1v2w3x4... (for verification across sessions)
- **Consistency verification**: Compare generated face against reference embeddings; cosine similarity must exceed 0.85

## Scene Defaults

### Wardrobe Palette
- **Core**: Earth tones (olive, rust, cream, slate)
- **Accent**: Warm metallics (gold, bronze)
- **Avoid**: Neon colors, heavy patterns, logos
- **Style**: Smart casual to editorial (structured blazers, quality fabrics)

### Environments That Work
- Urban architecture with natural light
- Cafe/workspace with warm ambient
- Outdoor golden hour with greenery
- Minimalist interiors with texture

### Environments to Avoid
- Sterile office/corporate
- Pure black backgrounds
- Heavily cluttered spaces
- Over-designed sets

### Lighting That Flatters
- 45-degree soft key light (emphasizes cheekbone structure)
- Warm fill (reduces under-eye shadows)
- Subtle rim light (separates from background without halo)
- Avoid: direct overhead (harsh nose shadow), direct front (flattens features)
```

### Style Guide (`compiled/styles/{slug}.md`)

```yaml
---
name: Style Name
type: style-guide
compiled: 2026-04-07T14:30:00Z
sources:
  - path: raw/style-inspiration/wes-anderson-refs/
    sha256: y5z6a7b8...
category: cinematic
camera_ref: [wes-anderson]
lora_ref: "wes-anderson-pastel-v2.safetensors"
related:
  - "[[brands/acme]]"
  - "[[characters/luna]]"
status: active
---

# {Style Name} -- Style Guide

## Camera Language
- **Shot types**: Medium-wide (primary), centered close-up (accent), symmetrical wide (establishing)
- **Movement**: Static (primary), slow lateral dolly (accent), centered zoom-out reveal
- **Framing**: One-point perspective, perfect symmetry, centered subjects
- **Focal length**: 35mm-50mm equivalent (no wide-angle distortion, no telephoto compression)

## Color Grammar
- **Primary palette**: Pastel (muted pink, powder blue, butter yellow, sage green)
- **Secondary**: Warm neutrals (cream, camel, terracotta)
- **Grading**: Desaturated 15% from capture, raised shadows, compressed highlights
- **LUT reference**: Wes Anderson Pastel Pack #3 (or manual: lift shadows +10, lower highlights -5, desaturate 15%)

## Lighting Setup
- **Key**: Large diffused source, frontal to 30-degree offset
- **Fill**: Bounce from opposite side, 2:1 ratio (very low contrast)
- **Rim**: Warm practical lights in frame (lamps, windows)
- **Temperature**: 5600K overall, warm practicals at 3200K for depth
- **Quality**: Extremely soft, almost shadowless on face

## Exact Prompts

### Nano Banana Pro
{prompt fragment}

### Soul Cinema
{prompt fragment}

### Weavy
{prompt fragment}

### ComfyUI
{node configuration with LoRA reference}
```

---

## Linting Rules

The lint pass enforces the Karpathy active-maintenance pattern: compiled knowledge must stay consistent with its sources and with itself.

### Consistency Rules

| Rule | Check | Severity |
|------|-------|----------|
| `provenance-exists` | Every `sources` entry points to an existing file in `raw/` | error |
| `provenance-hash` | SHA-256 of source file matches hash in compiled frontmatter | warning (triggers recompile suggestion) |
| `frontmatter-required` | All required frontmatter fields present (`name`, `type`, `compiled`, `sources`, `status`) | error |
| `frontmatter-type` | `type` is one of: `brand-dna`, `character-sheet`, `style-guide` | error |
| `frontmatter-status` | `status` is one of: `active`, `draft`, `archived`, `stale` | error |
| `tool-prompts-present` | At least one tool-specific prompt fragment exists in compiled file | warning |
| `anti-patterns-present` | Anti-patterns section exists and is non-empty (brand DNA and style guides) | warning |

### Orphaned Reference Rules

| Rule | Check | Severity |
|------|-------|----------|
| `orphaned-compiled` | Compiled file exists but all its source files have been deleted | error |
| `orphaned-raw` | Raw asset exists with no corresponding compiled file | warning |
| `stale-compiled` | Source file modified after compiled file's `compiled` timestamp | warning |

### Cross-Linking Rules

| Rule | Check | Severity |
|------|-------|----------|
| `wikilink-valid` | All `[[wikilink]]` references in `related` resolve to existing compiled files | error |
| `character-brand-link` | Every character sheet references at least one brand DNA | warning |
| `style-brand-link` | Every style guide references at least one brand DNA | warning |
| `bidirectional-links` | If A references B, B should reference A | warning |

### Lint Output

```json
{
  "timestamp": "2026-04-07T14:30:00Z",
  "files_checked": 12,
  "errors": 0,
  "warnings": 3,
  "details": [
    {
      "file": "compiled/brands/acme.md",
      "rule": "stale-compiled",
      "severity": "warning",
      "message": "Source raw/brand-assets/campaign-photos/hero-03.jpg modified after last compilation"
    }
  ]
}
```

Errors block the pipeline (generation should not proceed with broken identity files). Warnings are informational and suggest corrective action.

---

## Dependencies

### Required

| Dependency | Purpose |
|------------|---------|
| `@google/genai` | Gemini multimodal analysis (brand DNA extraction, style analysis) |
| `ffmpeg` | Video keyframe extraction, format conversion |
| Node.js 20+ | Script runtime |

### Optional

| Dependency | Purpose |
|------------|---------|
| Nano Banana Pro account | Character sheet ID integration |
| ComfyUI local install | LoRA style-locking verification |
| fal.ai API key | Programmatic generation for prompt testing |

---

## File Locations

| File | Purpose |
|------|---------|
| `references/brand-dna-extraction.md` | Full Gemini analysis prompt spec and extraction methodology |
| `references/character-sheets.md` | Character sheet format, creation process, consistency verification |
| `references/style-locking.md` | LoRA style-locking patterns, ComfyUI node setup, anti-patterns |
| `knowledge/raw/` | Immutable source assets (never modified by the compiler) |
| `knowledge/compiled/` | LLM-compiled identity files (written by the compiler) |
| `knowledge/schema.md` | Compilation rules and validation schema |
| `.cache/content-engine/` | Ephemeral compilation state (manifests, reports) |

---

## Self-Maintenance Rules

These rules govern any agent that modifies files in this skill. They are enforced by reasoning, not by hooks.

**Rule 1 -- Pipeline step count consistency**
When adding or removing compilation steps: update the step count in BOTH this file's heading ("6 Steps") AND any references to the pipeline in sibling SKILL.md files. The pipeline step count must always match across all files.

**Rule 2 -- Compiled file format consistency**
When adding a new compiled file type or modifying frontmatter fields: update BOTH the format examples in this file AND the corresponding template in `templates/`. The template must always reflect the current schema.

**Rule 3 -- Linting rule consistency**
When adding a new lint rule: add it to the Linting Rules table in this file AND implement the check in `scripts/compile-dna.py`. Rules documented but not implemented are worse than no rules.

**Rule 4 -- Tool-specific prompt format consistency**
When adding a new supported tool: add prompt fragment format examples in this file, in `references/brand-dna-extraction.md` (extraction prompt), and in `references/style-locking.md` (if the tool uses LoRA or equivalent). All three files must agree on supported tools.

**Rule 5 -- SKILL.md is authoritative**
This SKILL.md is the single source of truth for compilation pipeline, compiled file formats, and linting rules. All reference files defer to it. If a conflict exists, this file wins.

---

## Integration Points

| Skill | Integration |
|-------|-------------|
| `content-engine-cinema` | Consumes compiled identity files. Reads brand DNA, character sheets, and style guides to construct generation prompts. |
| `content-engine-autopilot` | Loads compiled identity before driving browser tools. Injects tool-specific prompt fragments into generation sessions. |
| `content-engine-loop` | Feeds performance data back. High-performing styles/prompts get promoted in compiled knowledge. |
| `bookkeeping` | Compiled files follow the same provenance-tracked Markdown pattern as Layer 3 entity pages. Shares the compile-then-query philosophy. |
| `blog-post` / `content-creation` | Compiled visual identity informs image generation prompts within the blog post pipeline. |
