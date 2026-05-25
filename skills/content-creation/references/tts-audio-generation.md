# TTS Audio Generation for Blog Posts

Generate high-quality audio narration for blog posts using local TTS engines. Audio files are pre-generated and served as static assets — zero runtime cost, instant playback.

## Strategy: Batched Pre-Generation

Pre-generate MP3 files for each post as part of the content pipeline, not on-demand. This avoids runtime API costs, serverless timeouts, and external dependencies at serve time.

**Math for a typical blog:**
- 2000-word post → ~12K characters → ~8-10 min audio → ~8-10 MB MP3 (128kbps)
- 50 posts → ~500 MB total → well within Cloudflare R2 free tier (10 GB, zero egress)

## TTS Engine Options (ranked by quality)

### Tier 1: Voicebox (best quality, self-hosted)

[voicebox.sh](https://voicebox.sh/) — "Ollama for audio." Free, MIT-licensed, runs locally.

**Engines:** Qwen3-TTS (8-9/10), Chatterbox (8/10), LuxTTS (7/10, CPU-fast)

**Setup:**
```bash
# Option A: Desktop app (GUI + server)
# Download from https://voicebox.sh/

# Option B: Docker headless (no GUI)
git clone https://github.com/jamiepine/voicebox.git
cd voicebox && docker compose up

# Option C: Backend only (requires Python env)
just dev-backend
```

**REST API (runs on localhost:17493):**
```bash
# Health check
curl http://localhost:17493/health

# List available voice profiles
curl http://localhost:17493/profiles

# Generate speech
curl -X POST http://localhost:17493/generate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your blog post content here...",
    "profile_id": "PROFILE_ID",
    "language": "en"
  }'

# Download the generated audio
curl http://localhost:17493/audio/{generation_id} -o output.wav

# Convert to MP3
ffmpeg -i output.wav -codec:a libmp3lame -b:a 128k output.mp3
```

**Voice cloning:** Upload 3+ seconds of reference audio (WAV/MP3/FLAC) via `POST /profiles/{id}/samples` to create a custom voice profile.

**Limits:** 50,000 characters per generation with automatic sentence splitting and crossfading.

### Tier 2: kokoro-tts-cli (fast batch, CLI-first)

Best for rapid batch generation without GPU. 82M parameter model, surprisingly natural.

**Setup:**
```bash
# Install
pip install kokoro-tts  # nazdridoy version — file-oriented, EPUB/PDF support
# OR
pip install git+https://github.com/cheuerde/kokoro-tts-cli.git  # server mode

# Server mode (recommended for batch — avoids model reload per file)
kokoro-tts-server &  # start once
kokoro-tts-client --text "Hello" --save output.wav  # fast repeated calls
```

**Batch generation:**
```bash
# Single file
kokoro-tts input.txt output.wav --voice af_sarah --speed 1.0

# From stdin (pipe markdown content)
cat post.mdx | sed '1,/^---$/d' | sed '/^---$/,+0d' | kokoro-tts - output.wav --voice af_sarah

# Available voices: af_sarah, af_bella, bf_emma, am_adam, bm_george (40+ total)
# Voice blending: --voice "af_bella:0.7,bf_emma:0.3"
```

### Tier 3: mlx-audio (Apple Silicon native)

Leverages Apple MLX framework for M-series chip optimization.

```bash
pip install mlx-audio

# Generate with Kokoro model
mlx_audio.tts.generate \
  --model mlx-community/Kokoro-82M-bf16 \
  --text "Your text here" \
  --voice af_heart \
  --speed 1.0 \
  --lang_code a
```

### Tier 4: Edge TTS (cloud, free, unofficial)

Microsoft Azure Neural voices via unofficial API. No API key needed. Risk: Microsoft could block it.

```bash
pip install edge-tts

# Generate audio
edge-tts --text "Your text here" --voice en-US-AndrewNeural --write-media output.mp3

# Best voices: en-US-AndrewNeural (warm), en-US-RogerNeural (authoritative)
```

**npm packages for Node.js API routes:**
- `msedge-tts` (MIT, streaming support, SSML)
- `node-edge-tts` (proxy support, subtitle generation)

### Tier 5: Cloud APIs (paid, highest quality)

| Service | Quality | Free Tier | Best Voice |
|---------|---------|-----------|------------|
| ElevenLabs | 9-10/10 | ~10 min/mo | Custom clone |
| Google Cloud TTS | 8/10 | 1M chars/mo WaveNet | en-US-Neural2-D |
| OpenAI TTS | 8/10 | None | alloy, nova |
| Amazon Polly | 7/10 | 1M chars/mo (12 mo) | Matthew (Neural) |

## Batch Generation Script Pattern

For the content pipeline, generate audio for all posts that don't have it yet:

```bash
#!/bin/bash
# generate-audio.sh — batch TTS for all blog posts
# Requires: kokoro-tts (or voicebox running on :17493)

CONTENT_DIR="apps/chat/content/writing"
AUDIO_DIR="apps/chat/public/audio/writing"
mkdir -p "$AUDIO_DIR"

for file in "$CONTENT_DIR"/*.mdx; do
  slug=$(basename "$file" .mdx)
  output="$AUDIO_DIR/$slug.mp3"

  # Skip if audio already exists
  [ -f "$output" ] && echo "skip: $slug" && continue

  echo "generating: $slug"

  # Strip frontmatter, then generate
  body=$(sed '1{/^---$/!q;};1,/^---$/d' "$file")

  # Option A: kokoro-tts
  echo "$body" | kokoro-tts - "/tmp/$slug.wav" --voice af_sarah --speed 1.0
  ffmpeg -i "/tmp/$slug.wav" -codec:a libmp3lame -b:a 128k -y "$output"

  # Option B: Voicebox (requires server running)
  # GEN_ID=$(curl -s -X POST http://localhost:17493/generate \
  #   -H "Content-Type: application/json" \
  #   -d "{\"text\": \"$body\", \"profile_id\": \"default\", \"language\": \"en\"}" \
  #   | jq -r '.id')
  # curl -s "http://localhost:17493/audio/$GEN_ID" -o "$output"

  # Option C: Edge TTS
  # edge-tts --text "$body" --voice en-US-AndrewNeural --write-media "$output"
done

echo "done — generated audio in $AUDIO_DIR"
```

## Integration with broomva.tech

### Frontmatter: `audio` field

Add an `audio` field to post frontmatter pointing to the generated file:

```yaml
---
title: "My Post Title"
summary: "Post summary"
date: 2026-03-20
published: true
tags: [topic]
audio: /audio/writing/my-post-title.mp3
---
```

### Player Component

The site's `ContentArticle` component checks for the `audio` field and renders a native `<audio>` player with full controls (play/pause, seek, skip ±10s, progress bar) instead of the Web Speech API fallback.

### Storage Options

| Storage | Free Tier | Egress | Best For |
|---------|-----------|--------|----------|
| **Repo (`public/audio/`)** | Unlimited | CDN via Vercel | < 50 posts, < 500 MB |
| **Cloudflare R2** | 10 GB storage, zero egress | $0 | Any scale |
| **Vercel Blob** | 1 GB (Hobby) | $0.15/GB over | Small sites |
| **S3 + CloudFront** | 5 GB (12 mo) | $0.085/GB | AWS shops |

For a personal blog with < 50 posts, committing audio to `public/audio/` is simplest — Vercel's CDN handles the rest.

## Pipeline Integration

In the content creation pipeline, audio generation fits between VISUAL ASSETS and SOCIAL:

```
REFERENCE → RESEARCH → NARRATIVE → VISUAL ASSETS → AUDIO → VIDEO → SOCIAL → DEPLOY
```

After the MDX file is written:
1. Generate audio via Voicebox or kokoro-tts
2. Place MP3 in `public/audio/writing/{slug}.mp3`
3. Add `audio: /audio/writing/{slug}.mp3` to frontmatter
4. The ContentArticle component picks it up automatically

## Quality Comparison

| Engine | Quality | Speed | Cost | Voice Clone | Offline |
|--------|---------|-------|------|-------------|---------|
| Voicebox (Qwen3-TTS) | 8-9/10 | ~1x realtime (GPU) | Free | Yes | Yes |
| Voicebox (LuxTTS) | 7/10 | 150x realtime (CPU) | Free | No | Yes |
| kokoro-tts | 7-8/10 | ~2x realtime (CPU) | Free | No | Yes |
| Edge TTS | 7-8/10 | ~0.5x realtime (stream) | Free* | No | No |
| ElevenLabs | 9-10/10 | ~1x realtime | $5+/mo | Yes | No |

*Edge TTS is unofficial and could be blocked by Microsoft.
