---
name: content-engine-opencaptions
slug: opencaptions
hook: post-production
version: "0.1.0"
description: "OpenCaptions extension for Content Engine — adds intent-driven CWI (Caption With Intent) captions to the post-production pipeline. Hooks into the grade → caption → final stage. Generates captions that understand video intent (pitch, volume, emotion, emphasis) and style themselves accordingly with variable font weight, size, and color. Uses the OpenCaptions CLI or MCP server. Triggers on: 'add captions', 'opencaptions', 'CWI captions', 'intent captions'."
inputs:
  - "graded video asset from post-production pipeline"
  - "compiled/brands/{brand_slug}.md (optional)"
  - "scene brief (passed at runtime)"
outputs:
  - "extensions/opencaptions/output/{asset_id}.cwi.json"
  - "extensions/opencaptions/output/{asset_id}.vtt"
  - "extensions/opencaptions/output/{asset_id}-report.json"
  - "extensions/opencaptions/output/{asset_id}-captioned.mp4 (Remotion render)"
dependencies: []
---

# OpenCaptions Extension

Hook CWI (Caption With Intent) captions into the Content Engine post-production pipeline. Instead of flat, static subtitles, CWI encodes the *felt experience* of speech — pitch drives font weight, volume drives font size, emphasis triggers glow animations, and speaker identity maps to WCAG AA colors. The result is captions that communicate how something was said, not just what was said.

CWI is the Oscar-winning (2025) captioning standard by FCB Chicago and Chicago Hearing Society. OpenCaptions is the first open-source programmatic toolchain for it.

## Pipeline Hook Point

**Stage:** Post-Production (Stage 3)
**Position:** After upscale and color grade, before final export.

```
Post-Production Chain:
  1. Upscale (Real-ESRGAN / Topaz)   --> Higher resolution
  2. Color Grade (Brand LUT / ffmpeg) --> On-brand color
  3. OpenCaptions (CWI)               --> Intent-driven captions
  4. Final Export (ffmpeg)             --> Production-ready file
```

The extension receives a graded video file and produces:
1. A CWI document (`.cwi.json`) with word-level intent annotations
2. A WebVTT fallback (`.vtt`) for platforms that need standard subtitles
3. A validation report (JSON) with pillar scores
4. A captioned video (`.mp4`) rendered via Remotion or ffmpeg burn-in

## How It Works

```
Graded Video + Scene Brief
  |
  ├── [1] Transcribe (faster-whisper) --> word-level timestamps
  ├── [2] Diarize (pyannote-audio)    --> speaker attribution
  ├── [3] Extract Intent              --> pitch, volume, emotion, emphasis per utterance
  |       V1: parselmouth + FER (audio+vision)
  |       V2: V-JEPA2 world model
  |       V3: TRIBE v2 neural prediction
  ├── [4] Map Intent --> CWI          --> weight, size, emphasis, animation per word
  |       V1: RulesMapper (pitch-->weight, volume-->size)
  |       V2: LearnedMapper (trained on correction data)
  |       V3: NeuralMapper (brain-region activations drive styling)
  ├── [5] Validate (12 rules)         --> Attribution + Synchronization + Intonation scores
  └── [6] Render                      --> Remotion overlay OR ffmpeg burn-in
```

### Step 1-2: Transcription + Diarization

The pipeline calls the OpenCaptions CLI or MCP server, which runs faster-whisper for word-level timestamps and pyannote-audio for speaker detection. These stages produce a `DiarizedTranscript` with each word tagged to a speaker.

### Step 3: Intent Extraction

The intent extractor analyzes audio and video to determine the *felt register* of each utterance:
- **Vocal signals**: Pitch (Hz), volume (dB), speech rate (WPM), pause timing
- **Affect signals**: Valence (-1 to 1), arousal (0 to 1), dominant emotion
- **Semantic signals**: Sarcasm probability, emphasis words, rhetorical devices

These signals form an `IntentFrame` for each utterance. Individual words that deviate from the utterance baseline receive `WordIntent` overrides.

### Step 4: Intent Mapping

The mapper converts intent signals to CWI visual parameters:

| Intent Signal | CWI Property | Mapping (V1 RulesMapper) |
|---|---|---|
| Pitch (normalized 0-1) | `weight` (100-900) | Linear interpolation: `100 + pitch_norm * 800` |
| Volume (normalized 0-1) | `size` (0.7-1.5) | Linear interpolation: `0.8 + volume_norm * 0.55` |
| Semantic emphasis + high volume | `emphasis` (boolean) | Word in `emphasis_words` OR volume > p90 |
| Speaker identity | Speaker `color` | Assigned from 12-color WCAG AA palette |
| Whisper (low volume) | `weight` < 300 | Override: weight clamped to 100-250 |
| Shout (high volume) | `size` > 1.3 + emphasis | Override: size 1.35-1.5, emphasis true |

### Step 5: Validation

The `@opencaptions/spec` validator checks the CWI document against 12 rules across three pillars:

**Attribution (3 rules):**
- ATT_001: Every caption has a speaker in the cast
- ATT_002: Speakers have unique colors
- ATT_003: Colors meet WCAG AA contrast (4.5:1 against #1a1a1a)

**Synchronization (5 rules):**
- SYN_001: All words have timestamps
- SYN_002: Timestamps monotonically increasing
- SYN_003: Caption events do not overlap
- SYN_004: Animation duration 600ms per spec
- FCC_001: No gaps > 3s during speech
- FCC_002: Max 42 chars per line (FCC compliant)

**Intonation (3 rules):**
- INT_001: Weight in valid range (100-900)
- INT_002: Size in valid range (0.7-1.5)
- INT_003: > 20% of words have non-default weight (captions actually vary)

Each pillar scores 0-100. A CWI document passes if all three pillars score >= 80.

### Step 6: Rendering

Two rendering paths:

**Remotion path** (preferred for Content Engine): CWI words become React components in a `<CaptionOverlay>` composition. Each word appears at its timestamp with spring() entrance animation, speaker color, variable font weight, and emphasis glow. See `references/cwi-remotion-bridge.md` for the full mapping.

**ffmpeg burn-in** (fallback): Generate an ASS subtitle file from the CWI document and burn it into the video via `ffmpeg -vf ass=captions.ass`. Loses per-word animation but preserves speaker colors and font weight variation.

## CLI Usage

```bash
# Generate CWI captions from a video
npx opencaptions generate video.mp4 --output captions.cwi.json

# Generate with TRIBE v2 neural backend
npx opencaptions generate video.mp4 --backend tribe --output captions.cwi.json

# Validate a CWI document
npx opencaptions validate captions.cwi.json

# Preview captions in the terminal (ANSI-colored)
npx opencaptions preview captions.cwi.json

# Export to WebVTT
npx opencaptions export captions.cwi.json --format webvtt

# Export to After Effects ExtendScript
npx opencaptions export captions.cwi.json --format ae-json

# Export to Premiere Pro XML
npx opencaptions export captions.cwi.json --format premiere-xml

# Check system dependencies
npx opencaptions doctor

# Install Python dependencies
npx opencaptions setup
```

## MCP Server Usage

The OpenCaptions MCP server exposes four tools for agent integration:

| Tool | Description |
|---|---|
| `generate_captions` | Run the full pipeline on a video file |
| `validate_captions` | Validate a CWI document against 12 rules |
| `preview_captions` | Terminal-formatted preview at a given time |
| `export_captions` | Export to WebVTT format |

To use via Claude Code, add the MCP server to your settings:

```json
{
  "mcpServers": {
    "opencaptions": {
      "command": "npx",
      "args": ["@opencaptions/mcp"]
    }
  }
}
```

Then invoke in conversation: "Generate CWI captions for video.mp4" triggers `generate_captions`.

## compose-video.py Integration

The Content Engine's `compose-video.py` accepts a `--captions` flag:

```bash
python3 scripts/compose-video.py storyboard.md --brand arcan-studio --captions
```

When `--captions` is passed, after all clips are generated and stitched, the pipeline:

1. Runs `npx opencaptions generate {final-video}.mp4 --output {output-dir}/captions.cwi.json`
2. Validates the CWI document (warns if score < 80 but does not block)
3. If `--remotion` is also passed, injects the CWI JSON into the Remotion composition as `<CaptionOverlay>` props
4. Otherwise, generates WebVTT as a sidecar file alongside the final video

If OpenCaptions is not installed (`npx opencaptions doctor` fails), the pipeline degrades gracefully:
- Falls back to scene brief text overlay (static text from the storyboard `## Shot` descriptions)
- Logs a warning: "OpenCaptions not available, using scene brief text overlay"
- Still produces a `.vtt` file with timing derived from clip boundaries

## Caption Styles

Three built-in caption style presets, selectable via configuration:

### 1. Word-by-Word (brainrot)

High-retention style: each word appears individually, centered, maximum size variation. Used for social/TikTok/Reels content optimized for dopamine hooks.

- One word visible at a time
- Large base size (64px at 1080p)
- Extreme weight variation (100-900 full range)
- Emphasis words scale to 1.5x with glow
- Background: none (words float over video)
- Font: Roboto Flex variable

### 2. Narrative (editorial)

Full-sentence display with per-word styling. Used for long-form content, documentaries, blog video embeds.

- Full caption event visible, words styled inline
- Medium base size (48px at 1080p)
- Moderate weight variation (300-700)
- Emphasis words get subtle size bump (1.15x)
- Background: semi-transparent pill (rgba(0,0,0,0.6))
- Font: Roboto Flex variable

### 3. Minimal (lower-third)

Clean lower-third presentation. Speaker name + text. Minimal visual distraction. Used for interviews, talking heads, conference recordings.

- Speaker name label in speaker color, caption text in white
- Small base size (36px at 1080p)
- Weight variation only for emphasis (400 default, 700 emphasis)
- No size variation
- Background: gradient bar (bottom 15% of frame)
- Font: system sans-serif

## Data Contract

### Reads (immutable)

- Graded video asset from prior post-production step
- `knowledge/compiled/brands/{brand_slug}.md` -- for caption color palette and typography preferences
- Scene brief (runtime parameter) -- for context on intended emotional tone

### Writes (own namespace only)

- `extensions/opencaptions/output/{asset_id}.cwi.json` -- CWI document
- `extensions/opencaptions/output/{asset_id}.vtt` -- WebVTT fallback
- `extensions/opencaptions/output/{asset_id}-report.json` -- validation report
- `extensions/opencaptions/output/{asset_id}-captioned.mp4` -- rendered video (Remotion path only)

## Configuration

```yaml
opencaptions:
  # Caption style preset
  style: "narrative"              # word-by-word | narrative | minimal

  # Visual parameters
  font_family: "Roboto Flex"      # Variable font for weight axis
  base_font_size: 48              # Pixels at 1080p
  position: "bottom"              # top | center | bottom
  max_chars_per_line: 42          # FCC compliance
  background: "pill"              # pill | shadow | gradient | none
  background_opacity: 0.6         # 0.0 - 1.0

  # Pipeline backend
  backend: "av"                   # av (V1) | jepa (V2) | tribe (V3)
  language: "en"                  # ISO 639-1 hint for transcription

  # Speaker overrides (optional, auto-detected by default)
  speakers:
    - name: "Narrator"
      color: "#6B8AFF"
    - name: "Guest"
      color: "#FF6B6B"

  # Rendering
  render_mode: "remotion"         # remotion | ffmpeg | sidecar-only
  output_format: "mp4"            # mp4 | webm
  fps: 30                         # Match source video

  # Validation
  min_score: 80                   # Minimum overall score to proceed
  fail_on_low_score: false        # If true, block pipeline on low score

  # TRIBE v2 neural mapping (V3 backend only)
  neural_mapping: false           # Enable predicted neural response styling
```

## Graceful Degradation

The extension never blocks the Content Engine pipeline. Degradation ladder:

| Condition | Behavior |
|---|---|
| OpenCaptions CLI installed + all Python deps | Full CWI pipeline (transcription, diarization, intent, mapping) |
| OpenCaptions CLI installed, no Python deps | Mock backends with placeholder captions + validation |
| OpenCaptions CLI not installed | Scene brief text overlay as static captions at clip boundaries |
| Video has no audio track | Skip caption generation, log info message |
| Validation score < 80 | Warn but proceed (unless `fail_on_low_score: true`) |
| Remotion not available | Fall back to ffmpeg ASS burn-in |
| ffmpeg not available | Output CWI JSON + WebVTT as sidecar only (no rendered video) |

## Related

- **OpenCaptions project**: `~/broomva/apps/opencaptions/`
- **CWI-Remotion bridge**: `references/cwi-remotion-bridge.md`
- **Integration guide**: `references/integration-guide.md`
- **Content Engine SKILL.md**: `../../SKILL.md`
- **Extension framework**: `../README.md`
