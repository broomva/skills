# Content Engine Extensions

Extensions add capabilities to the content engine pipeline at well-defined
hook points. Each extension is a self-contained module that reads from
`compiled/` and writes only to its own namespace.

## Pipeline Architecture

The content engine pipeline has four hook points where extensions can operate:

```
                    ┌─────────────────────────────────────────────────┐
                    │             Content Engine Pipeline             │
                    └─────────────────────────────────────────────────┘

  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │    STAGE 1   │     │    STAGE 2   │     │    STAGE 3   │     │    STAGE 4   │
  │              │     │              │     │              │     │              │
  │    Pre-      │────▶│    Post-     │────▶│    Post-     │────▶│              │
  │  Generation  │     │  Generation  │     │  Production  │     │ Distribution │
  │              │     │              │     │              │     │              │
  └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
        │                    │                    │                    │
  ┌─────┴─────┐        ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
  │ Extension │        │Extension│         │Extension│         │Extension│
  │  hooks    │        │ hooks   │         │ hooks   │         │ hooks   │
  └───────────┘        └─────────┘         └─────────┘         └─────────┘
```

### Stage 1: Pre-Generation

Extensions at this stage run BEFORE the generation tool is invoked. They
prepare, validate, or augment the inputs.

**Input:** Scene brief + compiled brand/character files
**Output:** Modified scene brief or generation parameters

**Use cases:**
- Prompt optimization (rewrite prompts for specific tool quirks)
- Staleness check (verify compiled files are fresh before spending GPU time)
- Parameter tuning (adjust guidance scale, steps based on scene complexity)
- A/B test setup (create variant prompts for testing)

### Stage 2: Post-Generation

Extensions at this stage run AFTER the generation tool produces raw output
but BEFORE any post-processing. They evaluate or filter the raw asset.

**Input:** Raw generated asset (image or video) + scene brief
**Output:** Pass/fail verdict + feedback for re-generation, or annotated asset

**Use cases:**
- Quality gate (reject obviously bad generations -- extra limbs, artifacts)
- Brand compliance check (verify colors match palette within tolerance)
- Character consistency check (face similarity against embedding)
- NSFW/safety filter

### Stage 3: Post-Production

Extensions at this stage run AFTER the raw asset passes quality checks. They
transform the approved asset into its final form.

**Input:** Approved raw asset
**Output:** Final production-ready asset

**Use cases:**
- Upscaling (Real-ESRGAN, Topaz)
- Color grading (brand LUT application)
- Captioning (OpenCaptions CWI pipeline)
- Audio mixing (narration + ambient music)
- Film grain / texture overlay
- Format conversion (PNG to WebP, MP4 to HLS)

### Stage 4: Distribution

Extensions at this stage handle publishing the final asset to platforms. They
do not modify the asset.

**Input:** Final production-ready asset + campaign plan metadata
**Output:** Published URLs / confirmation

**Use cases:**
- Platform publishing (X, Instagram, LinkedIn, Moltbook)
- Blog post assembly (insert images into MDX, generate audio)
- CDN upload (Lago asset sync, Vercel deploy)
- Analytics tagging (UTM parameters, link shortening)

---

## Extension Structure

Each extension lives in its own directory under `extensions/` with the
following structure:

```
extensions/
  {extension-slug}/
    SKILL.md              # Required: skill definition with hook point declaration
    references/           # Optional: reference docs, configs
    scripts/              # Optional: executable scripts
    output/               # Extension's write namespace (created at runtime)
```

### SKILL.md Format

Every extension MUST declare its hook point and data contract in `SKILL.md`:

```markdown
---
name: "{Extension Name}"
slug: "{extension-slug}"
hook: "{pre-generation | post-generation | post-production | distribution}"
version: "0.1.0"
inputs:
  - "compiled/brands/*.md"
  - "compiled/characters/*.md"
  - "scene-brief (passed at runtime)"
outputs:
  - "extensions/{extension-slug}/output/*"
dependencies: []
---

# {Extension Name}

{Description of what this extension does.}

## Trigger

{When this extension runs and what conditions activate it.}

## Data Contract

### Reads (immutable)
- `compiled/brands/{brand_slug}.md` -- brand identity
- `compiled/characters/{character_slug}.md` -- character sheet

### Writes (own namespace only)
- `extensions/{extension-slug}/output/{asset_id}.{ext}` -- processed output
- `extensions/{extension-slug}/output/report.json` -- processing report

## Configuration

{Any configuration the extension accepts, with defaults.}
```

### Data Contracts

Extensions operate under strict isolation rules:

1. **Read from compiled/**: Extensions CAN read any file in `knowledge/compiled/`
   and any `templates/` file. These are treated as immutable inputs.

2. **Write to own namespace**: Extensions MUST only write to
   `extensions/{extension-slug}/output/`. No extension writes to another
   extension's directory or to `compiled/`.

3. **Receive pipeline data**: Extensions receive the current pipeline state
   (scene brief, raw asset path, metadata) via function arguments or stdin,
   not by reading filesystem state.

4. **Return structured results**: Extensions return a JSON result object:
   ```json
   {
     "status": "pass | fail | skip",
     "output_path": "extensions/{slug}/output/{file}",
     "metadata": { ... },
     "feedback": "Human-readable note for logs"
   }
   ```

5. **No side effects**: Extensions MUST NOT modify files outside their
   namespace, make network requests without declaration, or alter pipeline
   state except through their return value.

### Registration

Extensions are registered by listing them in this README. The content engine
reads this file to discover available extensions and their hook points.

---

## Registered Extensions

| Extension | Hook Point | Status | Description |
|---|---|---|---|
| `opencaptions` | post-production | active | CWI intent-driven caption generation for video assets |
| | | | |

> Add new extensions to this table when they are created. The content engine
> uses this table to discover and load extensions at each pipeline stage.

---

## OpenCaptions Extension (Planned)

The OpenCaptions extension will integrate the
[OpenCaptions](https://github.com/broomva/opencaptions) CWI (Caption with
Intention) pipeline into the content engine's post-production stage.

### Hook Point

**Stage:** Post-Production (Stage 3)

**Position in chain:** After upscale, after color grade, before final export.

```
Post-Production Pipeline:
  1. Upscale (Real-ESRGAN)      ──▶ Higher resolution
  2. Color Grade (Brand LUT)    ──▶ On-brand color
  3. OpenCaptions (CWI)         ──▶ Intentional captions burned in
  4. Final Export (ffmpeg)       ──▶ Production-ready file
```

### What It Does

OpenCaptions takes a video asset and produces captions that communicate
**intention**, not just transcription. Instead of flat subtitles, CWI
captions encode emotional weight, emphasis, and timing through visual
styling (size, weight, color, position, animation).

The pipeline:
1. **Transcribe**: Whisper extracts word-level timestamps from audio
2. **Diarize**: Pyannote identifies speakers (if multi-speaker)
3. **Extract Intent**: LLM analyzes transcript for emotional beats,
   emphasis words, rhetorical structure
4. **Map to CWI**: Intent signals become visual caption properties
   (amygdala activation → larger text, Broca activation → emphasis styling)
5. **Validate**: 12-rule CWI spec validator ensures captions meet the
   standard (no simultaneous styling overload, readability minimums, etc.)
6. **Render**: Captions composited onto video frame (Remotion or ffmpeg)

### Data Contract

**Reads:**
- Video asset from prior post-production step (upscaled + graded)
- `compiled/brands/{brand_slug}.md` -- for caption color palette and typography
- Scene brief -- for context on intended emotional tone

**Writes:**
- `extensions/opencaptions/output/{asset_id}-captioned.mp4` -- final video
- `extensions/opencaptions/output/{asset_id}.vtt` -- WebVTT subtitle file
- `extensions/opencaptions/output/{asset_id}-report.json` -- validation report

### Configuration

```yaml
opencaptions:
  # Caption positioning (Instagram-safe zone)
  position: "top"            # top | center | bottom
  margin_top_pct: 12         # percentage from top edge

  # Visual style
  style_preset: "clean"      # clean | hormozi | fireship | brainrot
  font_family: "Inter"       # must match brand typography
  base_font_size: 48         # pixels at 1080p
  background: "pill"         # pill | shadow | none
  background_opacity: 0.6    # 0.0 - 1.0

  # CWI-specific
  intent_model: "gpt-4o"     # LLM for intent extraction
  emphasis_scale: 1.5        # how much larger emphasis words get
  emotion_color_map:         # map emotions to brand palette
    confident: "{primary_hex}"
    reflective: "{secondary_hex}"
    urgent: "{accent_warm_hex}"

  # TRIBE v2 integration (future)
  neural_mapping: false      # enable TRIBE v2 neural response mapping
  neural_model: "tribe-v2-visual"
```

### TRIBE v2 Neural Mapping (Future)

When `neural_mapping: true`, the OpenCaptions extension will use Meta's
TRIBE v2 brain encoder to predict how the viewer's brain responds to each
moment of the video. These predicted neural responses drive caption styling:

- **Amygdala activation** → text size increase (emotional emphasis)
- **Right temporal cortex** → text weight/boldness (narrative significance)
- **Broca's area** → text emphasis/italic (linguistic processing load)
- **Visual cortex V1** → reduced caption opacity (let visuals breathe)

This creates captions that represent what the viewer's brain WOULD FEEL,
not just what the speaker SAID. See the OpenCaptions project for details
on the NeuralMapper V3 implementation (BRO-543).

### Implementation Status

| Component | Status | Linear Ticket |
|---|---|---|
| Extension directory structure | Not started | -- |
| SKILL.md declaration | Not started | -- |
| Pipeline integration (hook wiring) | Not started | -- |
| Caption rendering (Remotion path) | Available (in OpenCaptions repo) | BRO-529 |
| Caption rendering (ffmpeg path) | Not started | -- |
| WebVTT export | Available (in OpenCaptions repo) | BRO-529 |
| CWI validation | Available (in OpenCaptions repo) | BRO-528 |
| TRIBE v2 neural mapping | Research phase | BRO-541-545 |

---

## Writing a New Extension

### Step 1: Create the directory

```bash
mkdir -p extensions/{your-extension}/references
mkdir -p extensions/{your-extension}/scripts
```

### Step 2: Write SKILL.md

Declare your hook point, inputs, outputs, and dependencies. Follow the
format above. Be specific about what you read and write.

### Step 3: Implement

Extensions can be implemented as:
- **Shell scripts** (`scripts/run.sh`) -- simplest, good for wrapping CLI tools
- **Python scripts** (`scripts/run.py`) -- for LLM-based processing
- **Node scripts** (`scripts/run.ts`) -- for Remotion-based rendering
- **Rust binaries** -- for performance-critical processing

The extension receives its input via command-line arguments or stdin (JSON).
It writes output to its namespace and returns a JSON result to stdout.

### Step 4: Register

Add your extension to the "Registered Extensions" table in this README.
Include the hook point, status, and a one-line description.

### Step 5: Test

```bash
/content-engine test-extension --extension {your-extension}
```

This runs the extension against sample inputs from `references/` and
validates that:
- Output appears only in the extension's namespace
- Return value matches the expected JSON schema
- No files outside the namespace were modified

---

## Extension Ordering

When multiple extensions occupy the same hook point, they execute in the
order listed in the Registered Extensions table. The output of one extension
becomes the input of the next in the chain.

To change execution order, reorder the rows in the table. The content engine
reads top-to-bottom.

Extensions can declare `dependencies` in their SKILL.md to enforce ordering
constraints. If extension B depends on extension A, A always runs first
regardless of table order.
