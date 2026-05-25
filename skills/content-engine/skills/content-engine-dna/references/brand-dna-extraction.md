# Brand DNA Extraction via Gemini Multimodal

This document specifies how to analyze raw brand assets using Gemini's multimodal capabilities to produce structured visual identity data. It covers what to analyze, how to structure the analysis prompt, how to generate tool-specific prompt fragments, and how to track provenance.

---

## What to Analyze

Every image or video frame is analyzed across five visual dimensions. These dimensions are not arbitrary -- they are the axes along which AI generation tools differentiate output. Getting these right means the difference between "generic AI content" and "content that looks like it belongs to a specific brand."

### 1. Color Palette

**What to extract:**
- **Dominant colors** (3-5): The colors that occupy the most visual area. Extract as hex values.
- **Accent colors** (1-3): Colors used for emphasis, contrast, or focal points. Extract as hex values.
- **Overall temperature**: Warm (reds, oranges, yellows dominate), cool (blues, greens, purples dominate), or neutral (balanced or desaturated).
- **Saturation level**: High (vivid, punchy), medium (natural, balanced), low (muted, desaturated, pastel).
- **Contrast profile**: High (deep blacks, bright whites), medium (natural range), low (compressed, hazy, lifted shadows).
- **Mood mapping**: What emotional associations does this palette carry? (e.g., "#2D3436 grounds the image, creating authority; #E17055 injects warmth without undermining the seriousness").

**Why it matters:** Color palette is the single most recognizable element of brand consistency. Humans detect palette shifts before they notice any other inconsistency. Generation tools respond strongly to explicit hex values and temperature instructions.

### 2. Composition

**What to extract:**
- **Primary composition rule**: Rule of thirds, centered/symmetrical, golden ratio, dynamic diagonal, negative space dominant.
- **Subject placement**: Where the main subject sits in the frame (left third, centered, right third, lower third, etc.).
- **Leading lines**: Are there lines in the image that guide the eye? What direction do they lead? (converging, diverging, parallel, curved).
- **Negative space ratio**: Approximate percentage of frame that is "empty" (background, sky, wall, blur). This is critical -- many brands are defined by how much space they leave.
- **Depth layering**: How many distinct depth planes exist? (foreground element + subject + background is three layers. Subject only is one layer.)
- **Aspect ratio tendency**: Does the brand favor wide/cinematic (16:9, 2.39:1), square (1:1), or vertical (9:16)?

**Why it matters:** Composition drives the "feel" of an image before any content is processed. A brand that always uses centered symmetry (Wes Anderson) feels radically different from one that uses dynamic rule-of-thirds with negative space (Apple). AI tools default to centered composition unless explicitly instructed otherwise.

### 3. Lighting

**What to extract:**
- **Key light direction**: Front, 45-degree (Rembrandt), side, rim, overhead, under (dramatic), mixed.
- **Key light quality**: Hard (sharp shadows, direct sun or small source), soft (diffused shadows, overcast or large source), mixed.
- **Fill level**: How much shadow detail is visible? High fill = low contrast (editorial). Low fill = high contrast (dramatic).
- **Color temperature**: Estimated in Kelvin. 3200K = warm tungsten. 5500K = daylight. 6500K = overcast cool. 7500K+ = blue hour/shade.
- **Contrast ratio**: Estimated key-to-fill ratio. 2:1 = flat/editorial. 4:1 = natural. 8:1+ = dramatic/moody.
- **Rim/backlight**: Present or absent? Warm or cool? Subtle or prominent?
- **Practicals**: Are there visible light sources in frame (lamps, windows, neon)? These define the lighting "story."

**Why it matters:** Lighting is the technical backbone of visual mood. It is also the dimension most often botched by AI generation. Explicit lighting instructions (direction, quality, temperature, contrast ratio) dramatically improve generation consistency. Without them, tools default to flat, front-lit, daylight -- which looks generic.

### 4. Texture

**What to extract:**
- **Surface quality**: Matte (non-reflective, organic feel), glossy (reflective, commercial feel), mixed.
- **Film grain**: Present or absent? If present: fine (ISO 100-200 feel), medium (ISO 400-800), heavy (ISO 1600+, documentary/vintage).
- **Digital processing**: Clean/modern, film emulation, HDR-processed, analog with halation/light leaks.
- **Depth of field**: Deep (everything sharp, landscape/architectural), shallow (subject sharp, background blurred), very shallow (razor-thin focus plane, f/1.4 look).
- **Bokeh character**: If shallow DOF -- smooth circles (modern lens), hexagonal (vintage lens), swirly (vintage portrait lens). This matters because it is instantly recognizable and hard to fake.
- **Sharpness profile**: Clinical/razor (product photography), natural (editorial), soft/dreamy (fashion/fine art).

**Why it matters:** Texture is what separates "AI-looking" from "photographed-looking" content. Film grain alone can make generated content feel 50% more authentic. Most AI tools produce texture-free images by default. Explicit grain, DOF, and bokeh instructions are required for photorealistic output.

### 5. Pose Language

**What to extract:**
- **Subject posture**: Formal/upright, relaxed/natural, dynamic/in-motion, contemplative/still.
- **Gesture vocabulary**: Hands visible/hidden? Open gestures (palms visible, arms uncrossed) or closed (hands in pockets, arms crossed)?
- **Eye contact**: Direct to camera (engaging, confrontational), averted (candid, editorial), mid-distance gaze (thoughtful).
- **Energy level**: High (jumping, laughing, moving), medium (walking, conversing, natural smile), low (seated, contemplative, serene).
- **Body-to-camera relationship**: Facing camera, three-quarter turn, profile, over-the-shoulder, back-to-camera.
- **Context style**: Lifestyle (in natural environment, doing something), editorial (posed but artistic), portrait (formal, face-focused), documentary (captured, not posed).

**Why it matters:** Pose language defines the human element of a brand. The same person photographed with candid gestures vs. editorial poses communicates completely different brand values. AI tools need explicit pose direction -- without it they default to stiff, symmetrical, forward-facing poses that look artificial.

---

## Analysis Prompt Structure

The Gemini analysis prompt is the compiler's core. It must extract all five dimensions in a single pass while producing structured, machine-parseable output.

### System Prompt

```
You are a visual identity analyst for a premium content creation pipeline. Your job is to extract the visual DNA from brand reference images -- the specific, measurable, reproducible characteristics that define how this brand looks.

You are NOT writing marketing copy. You are extracting technical specifications that an AI image generation tool can use to reproduce this brand's visual style. Be precise, use hex values for colors, use directional terms for lighting, use compositional terminology for framing.

Every observation must be specific enough that a different analyst looking at different images from the same brand would extract the same values. If a characteristic is ambiguous or inconsistent across images, say so explicitly rather than guessing.
```

### User Prompt (Single Image)

```
Analyze this image and extract the following visual characteristics. Output as JSON.

{
  "color_palette": {
    "dominant": [{"hex": "#XXXXXX", "name": "descriptive name", "area_pct": 30}],
    "accent": [{"hex": "#XXXXXX", "name": "descriptive name", "role": "what it does"}],
    "temperature": "warm | cool | neutral",
    "saturation": "high | medium | low",
    "contrast": "high | medium | low",
    "mood": "one sentence describing the emotional effect of the palette"
  },
  "composition": {
    "primary_rule": "rule-of-thirds | centered | golden-ratio | diagonal | negative-space",
    "subject_placement": "description of where the subject sits",
    "leading_lines": "description or null",
    "negative_space_pct": 35,
    "depth_layers": 3,
    "aspect_tendency": "wide | square | vertical"
  },
  "lighting": {
    "key_direction": "front | 45-degree | side | rim | overhead | under | mixed",
    "key_quality": "hard | soft | mixed",
    "fill_level": "high | medium | low",
    "temperature_k": 5200,
    "contrast_ratio": "2:1 | 3:1 | 4:1 | 8:1+",
    "rim_light": {"present": true, "tone": "warm | cool", "intensity": "subtle | prominent"},
    "practicals": "description of visible light sources or null"
  },
  "texture": {
    "surface": "matte | glossy | mixed",
    "film_grain": "none | fine | medium | heavy",
    "processing": "clean | film-emulation | hdr | analog",
    "dof": "deep | shallow | very-shallow",
    "bokeh": "smooth | hexagonal | swirly | n/a",
    "sharpness": "clinical | natural | soft"
  },
  "pose_language": {
    "posture": "formal | relaxed | dynamic | contemplative",
    "gestures": "description",
    "eye_contact": "direct | averted | mid-distance",
    "energy": "high | medium | low",
    "body_camera": "facing | three-quarter | profile | over-shoulder | back",
    "context": "lifestyle | editorial | portrait | documentary"
  },
  "overall_impression": "One sentence capturing the essence of the visual style",
  "anti_patterns": ["specific things that would break this style"]
}

Be precise. Use exact hex values from the image. Estimate lighting temperature in Kelvin. Quantify negative space as a percentage. If something is ambiguous, note the ambiguity explicitly.
```

### User Prompt (Multi-Image Batch)

When compiling a full brand from multiple images, use a batch analysis prompt:

```
You are analyzing {N} images from the same brand/campaign. Your job is to extract the CONSISTENT visual DNA -- the characteristics that are shared across all images, not the ones that vary.

For each dimension, report:
1. The CONSENSUS value (what is consistent across all images)
2. The VARIANCE (what differs between images -- this is also useful data)
3. The CONFIDENCE (how many of the N images support the consensus value)

Output the same JSON schema as single-image analysis, but add "confidence" (0.0-1.0) and "variance_notes" to each field.

If a characteristic is genuinely inconsistent across images (e.g., some images are warm-lit and others cool-lit), do NOT average them. Report the inconsistency explicitly. An inconsistency finding is more valuable than a false consensus.
```

### User Prompt (Video Keyframe Analysis)

```
These are keyframes extracted from a video. In addition to the standard visual analysis, extract:

{
  "motion": {
    "pacing": "fast-cuts | medium | slow-contemplative",
    "avg_shot_duration_s": 3.5,
    "camera_movement": "static | dolly | crane | handheld | tracking | mixed",
    "transitions": ["cut", "dissolve", "whip-pan", "match-cut"],
    "energy_arc": "description of how energy changes over the video"
  }
}

Analyze the keyframes both individually (for visual DNA) and sequentially (for motion/pacing).
```

---

## Generating Tool-Specific Prompt Fragments

After raw analysis, the compiler transforms structured JSON into natural-language prompt fragments optimized for each generation tool. This is a second LLM pass -- the analysis pass extracts data, the generation pass produces tool-ready prompts.

### Transformation Prompt

```
You are a prompt engineer specializing in AI image and video generation tools. Given the following visual DNA analysis, generate exact prompt text that would reproduce this visual style in each of the following tools.

VISUAL DNA:
{analysis_json}

Generate prompt fragments for:

1. NANO BANANA PRO — focuses on character consistency. Prompt should describe the person and scene in natural language. Include character physical traits, wardrobe, setting, lighting, and mood. Do NOT include technical photography terms -- Nano Banana responds better to descriptive language.

2. SOUL CINEMA / HIGGSFIELD — focuses on cinematic quality. Prompt should use film terminology: shot type, camera movement, lighting direction, color grade reference. Include a director-style reference if the analysis suggests one. The start-frame prompt is everything -- it determines all downstream quality.

3. WEAVY — focuses on scene generation with character insertion. Prompt should describe the environment in detail, then reference a character sheet. Weavy needs rich environmental description and mood keywords.

4. COMFYUI — focuses on node-based generation with LoRA. Output should be a YAML configuration snippet with checkpoint, LoRA, sampler, CFG, and positive/negative prompts. The positive prompt should be a comma-separated tag list (ComfyUI-native format), not natural language.

For each tool, also list 2-3 ANTI-PATTERNS: specific prompt phrases or settings that would break the intended style in that tool.

Output as a structured document with clear headers for each tool.
```

### Fragment Quality Criteria

A prompt fragment is valid if:
- It is self-contained (can be pasted directly into the tool without modification)
- It reproduces the core visual identity dimensions (color, lighting, composition) when used
- It does not include conflicting instructions (e.g., "warm lighting" and "blue-toned cool environment")
- It is tool-appropriate (natural language for Nano Banana, film terminology for Soul Cinema, tags for ComfyUI)
- Anti-patterns are specific and actionable (not generic "avoid bad quality")

---

## Provenance Tracking Format

Every compiled file must trace its lineage back to raw sources. This is not optional decoration -- it is the mechanism that makes linting, recompilation, and change detection possible.

### Frontmatter Provenance Fields

```yaml
sources:
  - path: raw/brand-assets/campaign-photos/hero-01.jpg
    sha256: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
    analyzed: 2026-04-07T14:30:00Z
    dimensions_extracted: [color_palette, composition, lighting, texture, pose_language]
  - path: raw/brand-assets/campaign-photos/hero-02.jpg
    sha256: f7e8d9c0b1a2f7e8d9c0b1a2f7e8d9c0b1a2f7e8d9c0b1a2f7e8d9c0b1a2f7e8
    analyzed: 2026-04-07T14:30:15Z
    dimensions_extracted: [color_palette, composition, lighting, texture]
compiled: 2026-04-07T14:31:00Z
compiler_model: gemini-2.0-flash
compiler_prompt_version: v1.0
```

### Provenance Rules

1. **Immutable raw**: Files in `knowledge/raw/` are never modified by the compiler. They are source-of-truth reference material.
2. **Hash-based change detection**: SHA-256 hashes are computed at compilation time and stored in frontmatter. When `lint` runs, it recomputes hashes and flags any mismatches.
3. **Timestamp ordering**: `compiled` timestamp must be later than all `analyzed` timestamps. `analyzed` timestamps must be later than the file modification time of the raw asset at analysis time.
4. **Model attribution**: The `compiler_model` field records which Gemini model version was used. This allows recompilation when better models become available.
5. **Prompt versioning**: The `compiler_prompt_version` field tracks which version of the analysis prompt was used. When prompts are updated, stale compiled files can be identified and recompiled.

### Provenance Verification

During lint, the following checks run:

```
For each compiled file:
  For each source in sources:
    1. Does the file at `path` exist?                    → error if missing
    2. Does sha256(file) == recorded sha256?              → warning if mismatch
    3. Is file mtime < analyzed timestamp?                → warning if newer
  Is compiled timestamp > all analyzed timestamps?        → error if not
  Is compiler_prompt_version current?                     → info if outdated
```

This chain of verification ensures that compiled identity files are always traceable, always verifiable, and always current.
