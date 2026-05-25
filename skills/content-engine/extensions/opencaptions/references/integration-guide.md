# OpenCaptions Integration Guide

Step-by-step guide for setting up the OpenCaptions extension in the Content Engine pipeline. Covers prerequisites, installation, pipeline wiring, standalone usage, and validation.

## Prerequisites

### Required

**OpenCaptions CLI** (Bun/Node.js package):

```bash
# Verify installation
npx opencaptions doctor
```

If `doctor` reports missing components, install:

```bash
cd ~/broomva/apps/opencaptions
bun install
turbo build
```

After building, the CLI is available via:
- Direct: `bun run ~/broomva/apps/opencaptions/packages/cli/src/index.ts`
- npx (after publishing): `npx opencaptions`
- Linked: `bun link` in the CLI package, then `opencaptions` globally

**ffmpeg** (for audio extraction and video rendering):

```bash
# macOS
brew install ffmpeg

# Verify
ffmpeg -version
```

### Optional: Python Dependencies (V1 Audio+Vision Backend)

The OpenCaptions pipeline works with zero Python dependencies using mock backends. Each Python package adds a capability layer. Install progressively based on what you need:

```bash
# Level 1: Word-level transcription (most important)
pip install faster-whisper

# Level 2: Real pitch and volume analysis
pip install praat-parselmouth

# Level 3: Energy-based diarization fallback + speech rate
pip install librosa

# Level 4: Multi-speaker detection (requires HuggingFace token)
pip install pyannote-audio
# Then set: export HF_TOKEN="your-huggingface-token"
# Accept the model license at https://huggingface.co/pyannote/speaker-diarization

# Level 5: Facial emotion detection from video frames
pip install fer opencv-python-headless

# Level 6: Semantic emphasis and sarcasm detection
# Install Ollama from https://ollama.com
# Then: ollama pull llama3.2
```

Run `npx opencaptions doctor` after each installation to verify what the pipeline can now access.

**Degradation behavior by level:**

| Level | What Works | What is Missing |
|---|---|---|
| None (mock) | Placeholder timestamps, single speaker, neutral intent | Everything real |
| 1 (whisper) | Real word-level timestamps, language detection | Speaker separation, pitch/volume, emotion |
| 1+2 (whisper+parselmouth) | Real timestamps + real pitch/volume per utterance | Speaker separation, emotion |
| 1+2+3 (whisper+parselmouth+librosa) | Above + speech rate, energy-based speaker hints | True speaker diarization, visual emotion |
| 1+2+3+4 (all audio) | Full audio pipeline: timestamps, speakers, pitch, volume, rate | Visual emotion, semantic emphasis |
| 1+2+3+4+5+6 (full V1) | Complete V1 pipeline: audio + vision + semantic analysis | Neural prediction (V3 only) |

### Optional: TRIBE v2 (V3 Neural Backend)

The TRIBE v2 backend predicts how a viewer's brain would respond to each moment of the video, then maps those predicted neural activations to CWI styling. This is research-grade and requires GPU.

```bash
cd ~/broomva/apps/opencaptions/packages/backend-tribe
bun install

# TRIBE v2 model requires:
# - Python 3.10+
# - PyTorch 2.0+
# - ~4GB GPU VRAM (RTX 3060 minimum)
# - Model weights from Meta (research license)
pip install torch torchvision torchaudio
pip install nilearn nibabel scipy

# Verify
npx opencaptions generate video.mp4 --backend tribe
```

See `~/broomva/apps/opencaptions/packages/backend-tribe/README.md` for full TRIBE v2 setup.

## compose-video.py Integration

The Content Engine's video composer supports OpenCaptions via the `--captions` flag.

### Basic Usage

```bash
# Generate a multi-shot video with CWI captions
python3 scripts/compose-video.py storyboard.md --brand arcan-studio --captions

# Generate from concept with captions
python3 scripts/compose-video.py --concept "Tech product reveal" --shots 4 --captions

# Full pipeline: generate + captions + Remotion render
python3 scripts/compose-video.py storyboard.md --brand arcan-studio --captions --remotion
```

### What `--captions` Does

When the `--captions` flag is passed, after all clips are generated and stitched into a final video, the pipeline adds a caption step:

1. **Check availability**: Runs `npx opencaptions doctor` to verify the CLI is installed
2. **Generate CWI document**: Calls `npx opencaptions generate {final-video}.mp4 --output {output-dir}/captions.cwi.json`
3. **Validate**: Reads the validation report and logs pillar scores
4. **Generate WebVTT sidecar**: `npx opencaptions export captions.cwi.json --format webvtt`
5. **Update manifest**: Adds caption metadata to `manifest.json`

If `--remotion` is also passed, the CWI JSON is injected into the Remotion composition as props for the `<CaptionOverlay>` component, and the final rendered video includes animated captions.

### Fallback Behavior

If `npx opencaptions doctor` fails (CLI not installed):

```
  WARNING: OpenCaptions not available. Falling back to scene brief text overlay.
  Install: cd ~/broomva/apps/opencaptions && bun install && turbo build
```

The pipeline generates a simple `.vtt` file derived from the storyboard shot descriptions, with timing based on clip boundaries. No intent analysis, no speaker attribution, no variable styling.

## Remotion Integration

The `<CaptionOverlay>` component reads a CWI JSON document and renders animated captions on top of video content.

### Setup

1. Install the Roboto Flex variable font:

```bash
cd ~/broomva/skills/content-engine/remotion
bun add @fontsource-variable/roboto-flex
```

2. Import in the Remotion root:

```typescript
// remotion/src/Root.tsx
import "@fontsource-variable/roboto-flex";
```

3. Create the CaptionOverlay component at `remotion/src/components/CaptionOverlay.tsx`:

The full component implementation is specified in `cwi-remotion-bridge.md`. The component accepts:

```typescript
interface CaptionOverlayProps {
  cwiDocument: CWIDocument;           // The CWI JSON document
  style?: "word-by-word" | "narrative" | "minimal";
  baseFontSize?: number;              // Default: 48 (at 1080p)
  background?: "pill" | "shadow" | "gradient" | "none";
  backgroundOpacity?: number;         // Default: 0.6
  position?: "top" | "center" | "bottom";
}
```

4. Wire into the composition:

```typescript
// remotion/src/compositions/CaptionedVideo.tsx
import { AbsoluteFill, OffthreadVideo, staticFile } from "remotion";
import { CaptionOverlay } from "../components/CaptionOverlay";
import type { CWIDocument } from "@opencaptions/types";

export function CaptionedVideo({ videoSrc, cwiPath, style }) {
  // Load CWI document from static file or input props
  const cwiDocument: CWIDocument = require(cwiPath);

  return (
    <AbsoluteFill>
      <OffthreadVideo src={videoSrc} />
      <CaptionOverlay
        cwiDocument={cwiDocument}
        style={style ?? "narrative"}
        background="pill"
        position="bottom"
      />
    </AbsoluteFill>
  );
}
```

5. Register the composition:

```typescript
// remotion/src/Root.tsx
import { Composition } from "remotion";
import { CaptionedVideo } from "./compositions/CaptionedVideo";

export function Root() {
  return (
    <Composition
      id="CaptionedVideo"
      component={CaptionedVideo}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={300} // Overridden by calculateMetadata
      defaultProps={{
        videoSrc: "",
        cwiPath: "",
        style: "narrative",
      }}
    />
  );
}
```

6. Render:

```bash
# Render captioned video
npx remotion render CaptionedVideo \
  --props='{"videoSrc":"output/final.mp4","cwiPath":"output/captions.cwi.json","style":"narrative"}' \
  --output output/final-captioned.mp4
```

### Style Selection by Content Type

| Content Type | Recommended Style | Background | Position |
|---|---|---|---|
| TikTok / Reels | `word-by-word` | `none` | `center` |
| YouTube / Blog embed | `narrative` | `pill` | `bottom` |
| Interview / Podcast | `minimal` | `gradient` | `bottom` |
| Documentary | `narrative` | `shadow` | `bottom` |
| Brainrot edit | `word-by-word` | `none` | `center` |

## Standalone Usage

The OpenCaptions CLI works independently of the Content Engine.

### Generate Captions

```bash
# Basic generation (V1 audio+vision backend)
npx opencaptions generate interview.mp4

# Output: interview.cwi.json + interview.vtt (auto-named)

# Custom output path
npx opencaptions generate interview.mp4 --output my-captions.cwi.json

# TRIBE v2 neural backend (requires GPU)
npx opencaptions generate interview.mp4 --backend tribe
```

### Validate Captions

```bash
npx opencaptions validate captions.cwi.json
```

Output:

```
Validation Report

  Overall: PASSED  Score: 87/100

  Attribution:     95/100 ok
  Synchronization: 85/100 ok
  Intonation:      80/100 ok

  Findings:
    [WARN] [INT_003] Only 22.5% of words have non-default weight (minimum 20%)
    [WARN] [FCC_002] Caption "evt-12" is 45 chars (max 42)
```

Exit code: 0 if passed, 1 if failed. Use in CI/CD:

```bash
npx opencaptions validate captions.cwi.json || echo "CWI validation failed"
```

The validation score (0-100) is the average of three pillar scores. A CWI document passes if every pillar scores >= 80. Common failure modes:

- **Low Attribution score**: Missing speakers in cast, duplicate colors, poor contrast colors
- **Low Synchronization score**: Overlapping events, missing timestamps, non-monotonic timing
- **Low Intonation score**: All words have the same weight (flat captions with no vocal variation)

### Preview Captions

```bash
# Full document summary (metadata + cast + all events)
npx opencaptions preview captions.cwi.json

# Preview at a specific timestamp (ANSI-colored terminal output)
# (Note: time-based preview is available via the MCP server)
```

### Export Captions

```bash
# WebVTT (standard subtitle format)
npx opencaptions export captions.cwi.json --format webvtt
# Output: captions.vtt

# After Effects ExtendScript
npx opencaptions export captions.cwi.json --format ae-json
# Output: captions.jsx — run in AE via File > Scripts > Run Script File

# Premiere Pro XML (FCP XML v5)
npx opencaptions export captions.cwi.json --format premiere-xml
# Output: captions.xml — import in Premiere via File > Import
```

### System Health Check

```bash
npx opencaptions doctor
```

Reports the status of every dependency:

```
OpenCaptions Doctor

  Core:
    ok  Bun runtime (1.1.x)
    ok  @opencaptions/types
    ok  @opencaptions/spec
    ok  @opencaptions/pipeline

  Audio:
    ok  ffmpeg
    ok  faster-whisper
    ok  praat-parselmouth
    --  librosa (optional, not installed)

  Vision:
    --  fer (optional, not installed)
    --  opencv (optional, not installed)

  Diarization:
    ok  pyannote-audio
    ok  HF_TOKEN set

  Semantic:
    ok  ollama reachable
    ok  llama3.2 model available

  Neural (V3):
    --  TRIBE v2 (not configured)

  Summary: 10/14 components available
  Pipeline level: Full V1 (audio + semantic)
```

## MCP Server Integration

For agent-driven captioning (Claude Code, other AI agents), use the MCP server instead of the CLI.

### Configuration

Add to Claude Code settings (`.claude/settings.json` or global):

```json
{
  "mcpServers": {
    "opencaptions": {
      "command": "bun",
      "args": ["run", "/Users/broomva/broomva/apps/opencaptions/packages/mcp/src/index.ts"],
      "env": {}
    }
  }
}
```

Or after npm publishing:

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

### Available Tools

| Tool | Parameters | Returns |
|---|---|---|
| `generate_captions` | `video_path` (string), `language?` (string), `speakers?` (array) | CWI document JSON + validation report |
| `validate_captions` | `cwi_json` (string) | Validation report with pillar scores and findings |
| `preview_captions` | `cwi_json` (string), `time?` (number) | ANSI-formatted caption preview |
| `export_captions` | `cwi_json` (string), `format` ("webvtt") | Exported subtitle content |

### Agent Usage Patterns

**Generate and validate in one flow:**

```
"Generate CWI captions for /path/to/video.mp4"
→ Agent calls generate_captions → receives CWI JSON
→ Agent calls validate_captions → checks score >= 80
→ Agent writes CWI JSON to extensions/opencaptions/output/
```

**Iterative refinement:**

```
"Generate captions for the interview video, make sure the speaker colors are correct"
→ Agent calls generate_captions with speakers override
→ Agent calls validate_captions → checks ATT pillar
→ If ATT score < 80, agent adjusts colors and re-validates
```

## Output Structure

After running the OpenCaptions extension, the output directory contains:

```
extensions/opencaptions/output/
  {asset_id}.cwi.json          # CWI document (canonical output)
  {asset_id}.vtt               # WebVTT fallback subtitle file
  {asset_id}-report.json       # Validation report (pillar scores, findings)
  {asset_id}-captioned.mp4     # Rendered video with captions (Remotion path only)
```

The `manifest.json` in the campaign output directory is updated with caption metadata:

```json
{
  "captions": {
    "cwi_path": "extensions/opencaptions/output/final.cwi.json",
    "vtt_path": "extensions/opencaptions/output/final.vtt",
    "validation_score": 87,
    "validation_passed": true,
    "speakers_detected": 2,
    "backend": "av",
    "style": "narrative"
  }
}
```

## Troubleshooting

### "No audio track found"

The video has no audio. OpenCaptions requires an audio track for transcription. Solutions:
- Add a voiceover track before running captions
- Use scene brief text overlay (automatic fallback)

### Low Intonation score (INT_003 failing)

The intent mapper is not detecting enough vocal variation. Usually means:
- The speaker has a flat delivery (common in AI-generated voiceovers)
- Parselmouth is not installed (pitch/volume defaults to neutral)
- The audio quality is poor (compression artifacts confuse the pitch detector)

Fix: Install `praat-parselmouth` for real pitch analysis, or manually adjust the CWI document weights.

### Overlapping caption events (SYN_003 failing)

Two speakers are talking simultaneously and the diarizer produced overlapping segments. Solutions:
- Set `speakers` in config to limit to expected speaker count
- Post-process: trim overlapping events to the dominant speaker

### WCAG contrast failure (ATT_003 failing)

A speaker color does not meet 4.5:1 contrast against the #1a1a1a background. This only happens with custom color overrides (the default palette is pre-validated). Fix: use colors from the `SPEAKER_COLORS` constant or test custom colors at https://webaim.org/resources/contrastchecker/.

### Remotion render fails with "Roboto Flex not found"

The variable font is not loaded. Install it:

```bash
bun add @fontsource-variable/roboto-flex
```

And import it at the top of your Remotion root file.

### Pipeline timeout on long videos

faster-whisper transcription can be slow on CPU for videos > 10 minutes. Solutions:
- Use GPU: `CUDA_VISIBLE_DEVICES=0` (if available)
- Use the `--language` flag to skip language detection
- Process clips individually before stitching (compose-video.py generates per-clip, stitch after)

## Version Compatibility

| OpenCaptions Version | CWI Spec Version | Content Engine Compatibility |
|---|---|---|
| 0.1.x | 1.0 | Full (current) |

The CWI document schema is versioned (`version: "1.0"` in the document). The extension checks the version field and refuses to process documents from unsupported schema versions. The `$schema` field points to `https://opencaptions.tools/schema/cwi/1.0.json`.
