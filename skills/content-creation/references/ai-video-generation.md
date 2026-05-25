# AI Video & Image Generation for Content Pipeline

## Overview

AI-generated assets (images, video clips, voiceovers) dramatically accelerate the visual phases of the content pipeline. This reference covers Nano Banana (Gemini image gen), Veo 3.1 (Google video gen), and how to integrate both with Remotion compositions.

## Nano Banana (Gemini Image Generation)

**What it is:** Google's codename for Gemini image generation/editing models.

| Model | ID | Best For |
|-------|----|----------|
| Nano Banana | `gemini-2.5-flash-preview-image-generation` | Original, fast |
| Nano Banana 2 | `gemini-3.1-flash-image` | Faster, cheaper, multi-scene video |
| Nano Banana Pro | `gemini-3-pro-image` | Highest quality |

### Setup

```bash
bun add @google/genai
export GEMINI_API_KEY="your-key"
```

### Generate Images

```typescript
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

// Text-to-image
const response = await ai.models.generateContent({
  model: "gemini-3.1-flash-image",
  contents: "A minimalist dark UI dashboard with frosted glass panels, AI Blue #0066FF accents",
  config: {
    responseModalities: ["IMAGE", "TEXT"],
    imageGenerationConfig: { outputImageFormat: "png" },
  },
});

// Extract image from response
for (const part of response.candidates[0].content.parts) {
  if (part.inlineData) {
    const buffer = Buffer.from(part.inlineData.data, "base64");
    await Bun.write("output.png", buffer);
  }
}
```

### Edit Images (Natural Language)

```typescript
// Pass existing image + edit instruction
const response = await ai.models.generateContent({
  model: "gemini-3.1-flash-image",
  contents: [
    { inlineData: { mimeType: "image/png", data: base64Image } },
    { text: "Remove the background and add a subtle gradient from #0A0A0F to #12121A" },
  ],
  config: { responseModalities: ["IMAGE", "TEXT"] },
});
```

### Pricing (Nano Banana 2)

| Resolution | Per Image | Batch (50% off) |
|------------|-----------|------------------|
| 512px | $0.045 | $0.023 |
| 1K | $0.067 | $0.034 |
| 4K | $0.151 | $0.076 |

Free tier: ~500 requests/day via Google AI Studio.

### CLI Tools

```bash
# Standalone CLI
npm install -g @the-focus-ai/nano-banana
nano-banana "A hero image for an Agent OS product launch, dark theme, glass effects"

# Gemini CLI extension
gemini extensions install https://github.com/gemini-cli-extensions/nanobanana
```

### MCP Servers

| Package | Install |
|---------|---------|
| `@aeven/nanobanana-mcp` | MCP server for Claude Code |
| `@ycse/nanobanana-mcp` | Flash + Pro models |
| `nano-banana-mcp` | Cross-platform |

---

## Veo 3.1 (Google Video Generation)

**What it is:** Google DeepMind's flagship text-to-video model. First mainstream AI model to support 4K + native audio.

### Capabilities

| Feature | Value |
|---------|-------|
| Resolution | 720p, 1080p, 4K |
| Duration | 4, 6, or 8 seconds per clip |
| Frame rate | 24 fps |
| Audio | Native (dialogue, SFX, ambient) at 48kHz |
| Aspect ratios | 16:9, 9:16 |
| Input modes | Text-to-video, image-to-video, first+last frame interpolation |
| Reference images | Up to 3-4 per generation |
| Extensions | Chain up to 20 clips (~148s total) |

### Setup

```bash
bun add @google/genai
export GEMINI_API_KEY="your-key"
```

### Generate Video

```typescript
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

// Text-to-video
const operation = await ai.models.generateVideos({
  model: "veo-3.1-generate-preview",
  prompt: "Cinematic aerial shot of a modern tech workspace, blue accent lighting, glass surfaces",
});

// Poll until done (typically 11s–6min)
let result = operation;
while (!result.done) {
  await new Promise((r) => setTimeout(r, 10_000));
  result = await ai.operations.get(result);
}

// Download
for (const video of result.result.generatedVideos) {
  await ai.files.download({ file: video.video, downloadPath: "clip.mp4" });
}
```

### Image-to-Video (animate a still)

```typescript
const operation = await ai.models.generateVideos({
  model: "veo-3.1-generate-preview",
  prompt: "Smooth camera push-in with parallax depth, subtle particle effects",
  image: { inlineData: { mimeType: "image/png", data: base64Image } },
});
```

### First + Last Frame Interpolation

```typescript
const operation = await ai.models.generateVideos({
  model: "veo-3.1-generate-preview",
  prompt: "Smooth transition between two UI states",
  image: firstFrame,
  config: { lastFrame: lastFrame },
});
```

### 4K Generation

```typescript
const operation = await ai.models.generateVideos({
  model: "veo-3.1-generate-preview",
  prompt: "...",
  config: { resolution: "4k" },
});
```

### Pricing (approximate)

| Model | Without Audio | With Audio |
|-------|---------------|------------|
| Veo 3.1 Fast | ~$0.10/sec | ~$0.15/sec |
| Veo 3.1 | ~$0.40/sec | ~$0.50–0.75/sec |

8-second clip ≈ $3–6. Always verify in GCP console.

### MCP Servers

```bash
# Python MCP server (best maintained)
uvx mcp-veo3 --output-dir ~/Videos/Generated
# or: pip install mcp-veo3
```

| Server | URL |
|--------|-----|
| mcp-veo3 | github.com/dayongd1/mcp-veo3 |
| veo-mcp-server | github.com/alohc/veo-mcp-server |
| veotools | github.com/frontboat/veotools |

### Alternative Providers (cheaper)

- **fal.ai**: `@fal-ai/client` — single API for Veo 3.1, Sora 2 Pro, Kling 3 Pro, 600+ models
- **Replicate**: replicate.com/google/veo-3.1

---

## Integrating AI Assets with Remotion

### Pipeline Architecture

```
1. Script/Storyboard (LLM)
        ↓
2. Generate Assets
   ├── Nano Banana → hero images, social cards, diagrams
   ├── Veo 3.1 → cinematic B-roll clips, product demos
   └── ElevenLabs → voiceover audio
        ↓
3. Preprocess (FFmpeg)
   ffmpeg -i ai_clip.mp4 -c:v libx264 -crf 18 -movflags +faststart -r 30 processed.mp4
        ↓
4. Place in public/assets/
        ↓
5. Remotion Composition
   ├── <OffthreadVideo> for AI video clips
   ├── <Img> + staticFile() for AI images
   ├── <Audio> for voiceovers
   └── Motion graphics overlays (titles, transitions)
        ↓
6. Render
   npx remotion render CompositionId out/final.mp4
```

### Using AI Video Clips in Remotion

```tsx
import { OffthreadVideo, staticFile, Sequence } from "remotion";

// AI-generated clip as background
export const AIBackgroundScene: React.FC = () => (
  <Sequence from={0} durationInFrames={240}>
    <OffthreadVideo
      src={staticFile("assets/veo-hero-clip.mp4")}
      style={{ width: "100%", height: "100%", objectFit: "cover" }}
    />
    {/* Overlay motion graphics on top */}
    <div style={{ position: "absolute", bottom: 80, left: 80 }}>
      <AnimatedTitle text="Agent OS" />
    </div>
  </Sequence>
);
```

### Using AI Images in Remotion

```tsx
import { Img, staticFile } from "remotion";

// Nano Banana generated hero image
<Img src={staticFile("assets/nano-banana-hero.png")} style={{ width: "100%" }} />
```

### Dynamic Duration from AI Clips

```tsx
import { parseMedia } from "@remotion/media-parser";

const calculateMetadata = async ({ props }) => {
  const { durationInSeconds, dimensions } = await parseMedia({
    src: props.aiVideoUrl,
    fields: { durationInSeconds: true, dimensions: true },
  });
  return {
    durationInFrames: Math.ceil(durationInSeconds * 30),
    width: dimensions.width,
    height: dimensions.height,
    fps: 30,
  };
};
```

### FFmpeg Preprocessing (Critical)

AI-generated videos often need preprocessing for Remotion compatibility:

```bash
# Re-encode to H.264 with fast-start (REQUIRED for parseMedia)
ffmpeg -i ai_clip.mp4 -c:v libx264 -crf 18 -preset medium -movflags +faststart -c:a aac -b:a 192k processed.mp4

# Normalize to target resolution and framerate
ffmpeg -i ai_clip.mp4 -vf "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2" -r 30 -c:v libx264 -crf 18 -movflags +faststart normalized.mp4

# Convert WebM to MP4
ffmpeg -i ai_clip.webm -c:v libx264 -crf 18 -movflags +faststart converted.mp4
```

The `-movflags +faststart` flag is **critical** — without it, `parseMedia()` may return `Infinity` for duration.

### Transitions Between AI Clips and Motion Graphics

```tsx
import { TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";

<TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={120}>
    <OffthreadVideo src={staticFile("assets/ai-clip-1.mp4")} />
  </TransitionSeries.Sequence>
  <TransitionSeries.Transition
    presentation={fade()}
    timing={linearTiming({ durationInFrames: 15 })}
  />
  <TransitionSeries.Sequence durationInFrames={90}>
    <MotionGraphicsScene />
  </TransitionSeries.Sequence>
</TransitionSeries>
```

---

## Content Type → AI Tool Matrix

| Content Need | Tool | Model | Output |
|-------------|------|-------|--------|
| Hero image | Nano Banana 2 | `gemini-3.1-flash-image` | PNG 1K–4K |
| Social card | Nano Banana 2 | `gemini-3.1-flash-image` | PNG 1080x1080 |
| Product screenshot edit | Nano Banana Pro | `gemini-3-pro-image` | PNG (edited) |
| Cinematic B-roll | Veo 3.1 | `veo-3.1-generate-preview` | MP4 1080p/4K 8s |
| Product demo clip | Veo 3.1 | `veo-3.1-generate-preview` | MP4 (image-to-video) |
| Animated transition | Veo 3.1 | `veo-3.1-generate-preview` | MP4 (frame interpolation) |
| Voiceover | ElevenLabs | TTS | MP3/WAV |
| Motion graphics | Remotion | React components | MP4 (rendered) |
| Final composition | Remotion | All above combined | MP4/GIF |

---

## Recommended Packages

```bash
# Core
bun add @google/genai                    # Nano Banana + Veo 3.1
bun add @remotion/media-parser           # Parse AI clip metadata
bun add @remotion/transitions            # Transitions between clips

# Optional: multi-provider (access Veo, Sora, Kling, Runway via one API)
bun add @fal-ai/client

# Optional: voiceover
bun add elevenlabs                       # ElevenLabs TTS
```

---

## fal.ai as Unified Provider

fal.ai provides a single API for 600+ models including Veo 3.1, Sora 2 Pro, Kling 3 Pro. Useful when you want to swap models without code changes:

```typescript
import { fal } from "@fal-ai/client";

fal.config({ credentials: process.env.FAL_KEY });

// Generate with any model by changing the endpoint string
const result = await fal.subscribe("fal-ai/veo3", {
  input: { prompt: "Cinematic shot of glass UI panels floating in space" },
});

// Download the video
const videoUrl = result.data.video.url;
```

Also ships a [video-starter-kit](https://github.com/fal-ai-community/video-starter-kit) that integrates directly with Remotion + Next.js.
