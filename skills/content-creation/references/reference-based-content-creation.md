# Reference-Based Content Creation

Using social media posts as creative references to inform, style-match, and generate new content.

---

## 1. How Creators Use Reference Posts

Content creators use reference posts/videos in three modes:

**Style Transfer** — Matching the visual aesthetic (color grading, typography, motion style, aspect ratio) of a reference while creating original content. A creator sees a Reel with kinetic text, moody blue grading, and 2-second cuts, then recreates that style with their own subject matter.

**Format Matching** — Replicating the structural format of high-performing content. A LinkedIn post that opens with a contrarian hook, uses numbered insights, and closes with a question CTA becomes a template that any topic can fill.

**Content Repurposing** — Taking an existing piece (blog post, podcast, long-form video) and reshaping it to match the format and style of reference content that performs well on a specific platform.

### Practical Workflow

```
1. Collect references (save/bookmark high-performing posts)
2. Analyze what makes them work:
   - Visual: colors, fonts, pacing, transitions, aspect ratio
   - Structural: hook type, section count, CTA pattern
   - Tonal: formal/casual, first-person/third-person, data-heavy/story-heavy
3. Build a "style brief" from the analysis
4. Create new content using the brief as creative constraints
5. Iterate based on performance of the output vs. the reference
```

---

## 2. Tools for Generating a "Style Brief" from Video

A structured style brief captures the reproducible elements of a reference video.

### Style Brief Schema

```typescript
interface StyleBrief {
  // Visual
  aspectRatio: "16:9" | "9:16" | "1:1" | "4:5";
  resolution: string; // "1080x1920"
  dominantColors: string[]; // hex codes
  colorMood: string; // "warm", "cool", "neon", "muted"
  typography: {
    style: string; // "kinetic", "static overlay", "handwritten"
    position: "center" | "bottom-third" | "top";
    animation: string; // "word-by-word", "fade-in", "typewriter"
  };

  // Temporal
  durationSeconds: number;
  averageCutLength: number; // seconds between transitions
  pacing: "fast" | "medium" | "slow";
  transitions: string[]; // "hard cut", "fade", "swipe", "zoom"

  // Structure
  hook: {
    type: string; // "question", "stat", "contrarian", "before-after"
    durationSeconds: number;
  };
  sections: { name: string; durationSeconds: number }[];
  cta: {
    type: string; // "follow", "link", "save", "comment"
    placement: "end" | "overlay" | "pinned-comment";
  };

  // Audio
  hasVoiceover: boolean;
  hasBGMusic: boolean;
  musicMood: string; // "upbeat", "ambient", "dramatic"
  hasSFX: boolean;
}
```

### Tools That Can Produce Style Briefs

| Tool | Approach | Output |
|------|----------|--------|
| **Gemini 2.5 Pro** (via API) | Upload full video (up to 1hr), prompt for structured JSON analysis | JSON style brief |
| **Claude** (via API) | Send sampled frames (up to 600 images per request), prompt for analysis | JSON style brief |
| **Twelve Labs** | Video understanding API — indexes video for semantic search, scene detection, text extraction | Structured metadata, timestamps, visual descriptions |
| **OpusClip** | Analyzes videos against social/marketing trends, identifies highlight moments | Clip suggestions with engagement scoring |
| **Manual + FFmpeg** | Extract keyframes, analyze with LLM | Frames + LLM-generated brief |

### Gemini Video Analysis (Recommended for Full Videos)

Gemini processes both audio and visual streams natively. Key specs:
- 1M context window: up to 1 hour at default resolution, 3 hours at low resolution
- Sampling: ~1 frame/second (300 tokens/sec default, 100 tokens/sec low-res)
- Supports YouTube URLs (public), File API (up to 20GB paid), inline data (<100MB)
- Timestamp queries: "What happens at 00:05?"

```typescript
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

// Upload video via File API
const file = await ai.files.upload({ file: videoBuffer, config: { mimeType: "video/mp4" } });

// Analyze for style brief
const response = await ai.models.generateContent({
  model: "gemini-2.5-pro",
  contents: [
    { fileData: { fileUri: file.uri, mimeType: "video/mp4" } },
    { text: `Analyze this video and return a JSON style brief with these fields:
      - aspectRatio, resolution, dominantColors (hex), colorMood
      - typography style, position, animation type
      - durationSeconds, averageCutLength, pacing, transitions used
      - hook type and duration, section breakdown with timestamps
      - CTA type and placement
      - audio characteristics (voiceover, music mood, SFX)
      Return ONLY valid JSON.` },
  ],
  config: { responseMimeType: "application/json" },
});
```

### Claude Frame-Based Analysis

Claude cannot process video directly but handles up to 600 images per API request (100 for 200k context models). Sample frames at key intervals.

```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

// Extract frames with ffmpeg first:
// ffmpeg -i reference.mp4 -vf "fps=1" -q:v 2 frame_%04d.jpg

// Send sampled frames to Claude
const message = await client.messages.create({
  model: "claude-opus-4-6",
  max_tokens: 4096,
  messages: [{
    role: "user",
    content: [
      // Include 10-20 evenly-spaced frames
      ...frames.map((frame, i) => ([
        { type: "text", text: `Frame ${i + 1} (${timestamps[i]}):` },
        { type: "image", source: { type: "base64", media_type: "image/jpeg", data: frame } },
      ])).flat(),
      { type: "text", text: `Analyze these frames from a social media video.
        Extract a structured style brief as JSON covering:
        visual style, color palette, typography, pacing, transitions,
        hook structure, content sections, and CTA pattern.` },
    ],
  }],
});
```

**Claude vision limits:**
- Max image size: 5MB per image (API), 10MB (claude.ai)
- Max dimensions: 8000x8000px (rejected above this)
- Optimal: resize to max 1568px on long edge before sending
- Supports JPEG, PNG, GIF, WebP
- Cost: ~$0.004 per 1000x1000px image at current pricing

---

## 3. Extracting Content Templates from Reference Posts

A content template captures the structural skeleton of a reference post — the hook pattern, information architecture, and CTA — independent of subject matter.

### Template Schema

```typescript
interface ContentTemplate {
  platform: "x" | "instagram" | "linkedin" | "tiktok" | "youtube-shorts";
  format: "thread" | "carousel" | "reel" | "story" | "post" | "short-video";

  hook: {
    pattern: string; // "contrarian_claim", "surprising_stat", "before_after", "question"
    formula: string; // "Most [role]s think [belief]. The data says otherwise:"
    wordCount: number;
  };

  body: {
    sectionCount: number;
    sectionsPattern: string[]; // ["context", "insight", "insight", "proof", "insight"]
    wordsPerSection: number;
    mediaPlacement: string; // "every_2_sections", "hero_only", "none"
  };

  cta: {
    type: string; // "question", "follow", "link", "save_share"
    formula: string; // "What's your experience with [topic]? Drop it below."
  };

  stylistic: {
    tone: string; // "authoritative", "conversational", "data-driven"
    personPOV: "first" | "second" | "third";
    useEmoji: boolean;
    useHashtags: boolean;
    hashtagCount: number;
  };
}
```

### Extraction Workflow

**For text posts (X, LinkedIn):**
```
1. Copy post text
2. Send to Claude/Gemini with extraction prompt:
   "Analyze this social media post and extract a reusable content template.
    Identify: hook pattern (what formula does the opening use?),
    body structure (how many sections, what role does each serve?),
    CTA pattern, tone, and any formatting conventions."
3. Store template in library for reuse
```

**For visual posts (Instagram carousels, Reels):**
```
1. Download media (yt-dlp for video, scraper API for images)
2. For carousels: OCR each slide, then analyze text structure
3. For video: extract frames + transcribe audio
4. Send combined text + frames to LLM for template extraction
5. Capture both textual and visual template elements
```

### Hook Pattern Library (from research)

| Pattern | Formula | Best For |
|---------|---------|----------|
| Scale Proof | "[Number] [things] in [timeframe]. Here's what happened:" | X threads |
| Contrarian | "Most [role]s think [belief]. The data says otherwise:" | LinkedIn, X |
| Transformation | "We replaced [old] with [new]. The results:" | Case studies |
| Earned Insight | "I spent X hours doing Y. Here's what I learned:" | Personal brand |
| Data Hook | "[Surprising stat]. Here's why that matters:" | B2B content |
| Question | "What if [surprising premise]?" | Instagram, TikTok |

---

## 4. AI Tools That Can Generate Remotion Compositions from Style Analysis

No current tool directly watches a video and outputs a ready-to-render Remotion composition. However, the workflow is achievable by chaining tools.

### LLM-to-Remotion Pipeline

```
Reference Video
      ↓
[Gemini/Claude] → Style Brief (JSON)
      ↓
[Claude/Gemini] → Remotion TSX Code Generation
      ↓
[Remotion] → Rendered Video
```

**Step 1: Analyze reference (see Section 2)**

**Step 2: Generate Remotion composition from brief**

```typescript
// Prompt Claude to generate Remotion code from a style brief
const composition = await client.messages.create({
  model: "claude-opus-4-6",
  max_tokens: 8192,
  system: `You are a Remotion expert. Generate valid Remotion compositions.
    Rules:
    - Use <Img> + staticFile() never <img>
    - Use spring() for organic motion
    - Use <Sequence> with premountFor for preloading
    - Use <OffthreadVideo> for video files
    - Use <TransitionSeries> from @remotion/transitions
    - No CSS transitions or Tailwind animation classes
    - All durations in frames (fps=30)`,
  messages: [{
    role: "user",
    content: `Generate a Remotion composition that matches this style brief:
      ${JSON.stringify(styleBrief)}

      The composition should:
      1. Match the aspect ratio, pacing, and transition style
      2. Use the color palette from the brief
      3. Follow the section structure with appropriate timing
      4. Include placeholder props for content injection
      5. Use TypeScript with proper Remotion imports`,
  }],
});
```

### Remotion Template Architecture

Remotion templates are React components with parameterized props. Structure for reusability:

```
remotion-project/
├── src/
│   ├── compositions/
│   │   ├── templates/           # Style-matched templates
│   │   │   ├── KineticText.tsx  # Fast-paced word-by-word
│   │   │   ├── CarouselSlide.tsx # Instagram-style slides
│   │   │   └── CinematicB-Roll.tsx # AI video + overlays
│   │   └── Root.tsx
│   ├── styles/
│   │   └── themes.ts            # Color palettes from style briefs
│   └── data/
│       └── content.json         # Injected content per render
├── public/
│   └── assets/                  # AI-generated images/clips
└── package.json
```

### Existing Remotion Templates to Build On

| Template | Description | Use Case |
|----------|-------------|----------|
| TikTok template | Animated word-by-word captions | Short-form captioned video |
| Next.js SaaS template | Server-rendered video generation | API-driven video creation |
| Audiogram | Audio waveform visualization | Podcast clips |
| Render Server (Express) | On-demand rendering API | Automated batch rendering |

### Programmatic Video APIs (Alternative to Remotion)

| Tool | Approach | Best For |
|------|----------|----------|
| **Creatomate** | JSON template + REST API rendering | Batch social content, simple templates |
| **Shotstack** | JSON template + cloud rendering at scale | High-volume, template-driven |
| **Remotion** | React components + local/Lambda render | Full creative control, complex compositions |

---

## 5. End-to-End Workflow: Link to Content

User provides a social media URL. System extracts content, analyzes style, generates matching content.

### Architecture

```
┌─ INPUT ────────────────────────────────────────────────┐
│  User provides: URL (X/LinkedIn/Instagram/TikTok)       │
│  + topic/subject for new content                        │
│  + target platform(s)                                   │
└─────────────────────────────────────────────────────────┘
           ↓
┌─ PHASE 1: EXTRACT ─────────────────────────────────────┐
│  yt-dlp → download video/images                         │
│  Scraper API → captions, metadata, engagement metrics   │
│  ffmpeg → extract keyframes, audio                      │
│  Whisper/Gemini → transcribe audio                      │
└─────────────────────────────────────────────────────────┘
           ↓
┌─ PHASE 2: ANALYZE ─────────────────────────────────────┐
│  Gemini (full video) or Claude (frames) →               │
│    → Style Brief (visual: colors, fonts, pacing)        │
│    → Content Template (hook, structure, CTA)             │
│    → Engagement Analysis (what made it work?)            │
└─────────────────────────────────────────────────────────┘
           ↓
┌─ PHASE 3: GENERATE ────────────────────────────────────┐
│  Claude/Gemini → new content matching template           │
│  Nano Banana → hero images matching color palette        │
│  Veo 3.1 → B-roll clips matching visual style            │
│  Kling v3 → motion-transferred clips (optional)          │
│  ElevenLabs → voiceover matching audio style              │
└─────────────────────────────────────────────────────────┘
           ↓
┌─ PHASE 4: COMPOSE ─────────────────────────────────────┐
│  Remotion → assemble into video composition              │
│  Pencil → design carousel slides                         │
│  Claude → write social copy matching tone                │
│  ffmpeg → format for target platforms                    │
└─────────────────────────────────────────────────────────┘
           ↓
┌─ PHASE 5: PUBLISH ─────────────────────────────────────┐
│  xurl / twitter-mcp → post to X                         │
│  ig-mcp → post to Instagram                              │
│  linkedin-mcp → post to LinkedIn                         │
│  Ayrshare MCP → multi-platform                           │
└─────────────────────────────────────────────────────────┘
```

### Content Extraction Tools

**yt-dlp** (video download — supports thousands of sites):
```bash
# Download video + metadata from any supported platform
yt-dlp -f "best[height<=1080]" --write-info-json --write-thumbnail \
  "https://x.com/user/status/123456"

# Extract audio only (for transcription)
yt-dlp -x --audio-format wav "https://instagram.com/reel/ABC123"

# Download with subtitles
yt-dlp --write-auto-sub --sub-lang en "https://tiktok.com/@user/video/123"
```

**Apify scrapers** (metadata + engagement):
- Instagram Scraper — posts, captions, hashtags, engagement metrics, comments
- TikTok Scraper — video metadata, sounds, engagement
- Twitter/X Scraper — tweet text, media, engagement counts
- LinkedIn Scraper — post content, reactions, comments

**FFmpeg keyframe extraction:**
```bash
# Extract 1 frame per second
ffmpeg -i reference.mp4 -vf "fps=1" -q:v 2 frames/frame_%04d.jpg

# Extract only scene-change keyframes
ffmpeg -i reference.mp4 -vf "select=gt(scene\,0.3)" -vsync vfr keyframes/kf_%04d.jpg

# Extract first and last frames
ffmpeg -i reference.mp4 -vf "select=eq(n\,0)" -vframes 1 first.jpg
ffmpeg -sseof -0.1 -i reference.mp4 -vframes 1 last.jpg
```

### Implementation Script (TypeScript)

```typescript
import { exec } from "child_process";
import { GoogleGenAI } from "@google/genai";
import Anthropic from "@anthropic-ai/sdk";
import { fal } from "@fal-ai/client";

interface ReferenceAnalysis {
  styleBrief: StyleBrief;
  contentTemplate: ContentTemplate;
  extractedText: string;
  keyframes: string[]; // base64 encoded
}

async function analyzeReference(url: string): Promise<ReferenceAnalysis> {
  // 1. Download with yt-dlp
  await exec(`yt-dlp -f "best[height<=1080]" --write-info-json -o "ref.mp4" "${url}"`);

  // 2. Extract keyframes
  await exec(`ffmpeg -i ref.mp4 -vf "fps=1" -q:v 2 frames/frame_%04d.jpg`);

  // 3. Analyze with Gemini (full video)
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  const file = await ai.files.upload({ file: "ref.mp4", config: { mimeType: "video/mp4" } });

  const analysis = await ai.models.generateContent({
    model: "gemini-2.5-pro",
    contents: [
      { fileData: { fileUri: file.uri, mimeType: "video/mp4" } },
      { text: "Return JSON with: styleBrief (visual style, pacing, transitions, colors, typography) and contentTemplate (hook pattern, section structure, CTA type, tone)." },
    ],
    config: { responseMimeType: "application/json" },
  });

  return JSON.parse(analysis.text);
}

async function generateMatchingContent(
  analysis: ReferenceAnalysis,
  topic: string,
  targetPlatform: string
) {
  const client = new Anthropic();

  // Generate text content matching the template
  const content = await client.messages.create({
    model: "claude-opus-4-6",
    max_tokens: 4096,
    messages: [{
      role: "user",
      content: `Create a ${targetPlatform} post about "${topic}" that matches this template:
        ${JSON.stringify(analysis.contentTemplate)}
        Use this style: ${JSON.stringify(analysis.styleBrief)}
        Match the hook pattern, section structure, and CTA style exactly.`,
    }],
  });

  // Generate matching visuals
  const heroImage = await ai.models.generateContent({
    model: "gemini-3.1-flash-image",
    contents: `Create an image matching this color palette: ${analysis.styleBrief.dominantColors.join(", ")}.
      Style: ${analysis.styleBrief.colorMood}. Subject: ${topic}`,
    config: { responseModalities: ["IMAGE", "TEXT"] },
  });

  return { textContent: content, heroImage };
}
```

---

## 6. fal.ai and Runway Style Reference Features

### fal.ai Style Reference Ecosystem

fal.ai provides a unified API across 600+ models. Key style-reference capabilities:

**Veo 3.1 Reference-to-Video** (`fal-ai/veo3.1/reference-to-video`):
- Provide multiple reference images via `image_urls` array
- Images guide "consistent subject appearance" throughout generation
- Duration: fixed 8 seconds
- Resolution: 720p, 1080p, or 4K
- Style control via prompt (action, style, camera motion, ambiance)
- Pricing: $0.20/sec (no audio) to $0.60/sec (4K + audio)

```typescript
import { fal } from "@fal-ai/client";

fal.config({ credentials: process.env.FAL_KEY });

const result = await fal.subscribe("fal-ai/veo3.1/reference-to-video", {
  input: {
    prompt: "Cinematic product reveal with glass reflections, slow camera orbit",
    image_urls: [
      "https://example.com/ref-frame-1.jpg",
      "https://example.com/ref-frame-2.jpg",
      "https://example.com/ref-style-guide.jpg",
    ],
    resolution: "1080p",
    aspect_ratio: "16:9",
    generate_audio: true,
  },
});
```

**Veo 3.1 First-Last Frame** (`fal-ai/veo3.1/first-last-frame-to-video`):
- Provide opening and closing images
- Model generates smooth interpolation between them
- Useful for recreating transition styles from reference videos

**Kling Video v3 Motion Control** (`fal-ai/kling-video/v3/pro/motion-control`):
- Transfers movements from a reference video to a character image
- Character in reference image performs same actions as reference video
- Character orientation: "video" mode (up to 30s) or "image" mode (up to 10s)
- Pricing: $0.168/sec
- Use cases: transferring dance moves, gestures, animations

```typescript
const result = await fal.subscribe("fal-ai/kling-video/v3/pro/motion-control", {
  input: {
    image_url: "https://example.com/my-character.jpg",
    video_url: "https://example.com/reference-motion.mp4",
    character_orientation: "video",
    prompt: "Professional presenter gesturing while explaining a concept",
  },
});
```

**Kling Video v3 Image-to-Video** (`fal-ai/kling-video/v3/pro/image-to-video`):
- Start image + optional end image
- Multi-prompt support: sequential prompts for different 5-second segments
- Custom element support via `@Element1` in prompts with `frontal_image_url`
- Reference image URLs for style/appearance guidance
- CFG Scale for guidance strength
- Pricing: $0.112/sec (no audio), $0.168/sec (with audio)

### Runway Gen-4 Turbo Style Reference

Runway's API uses reference images with an at-mention tagging system:

```typescript
import RunwayML from "@runwayml/sdk";

const client = new RunwayML();

const task = await client.imageToVideo.create({
  model: "gen4.5",
  promptImage: "https://example.com/start-frame.jpg",
  promptText: "Smooth camera push-in with @CinematicStyle lighting and @BrandColors palette",
  referenceImages: [
    { uri: "https://example.com/style-reference.jpg", tag: "CinematicStyle" },
    { uri: "https://example.com/brand-colors.jpg", tag: "BrandColors" },
  ],
  ratio: "1280:720",
  duration: 10,
});
```

Key features:
- Tagged reference images can be mentioned in prompts via `@TagName`
- Untagged images also influence output styling
- Supports base64 data URIs (no external upload needed)
- Available SDKs: Node.js (`@runwayml/sdk`), Python (`runwayml`)

---

## 7. Veo 3.1 Reference Images / Ingredients to Video

Google's Veo 3.1 offers the most comprehensive reference-based generation through multiple mechanisms.

### Style Reference

Provide a style reference image and Veo generates videos matching that visual style — from paintings to cinematic looks.

```typescript
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

// Style reference via direct API
const operation = await ai.models.generateVideos({
  model: "veo-3.1-generate-preview",
  prompt: "A person walking through a city at golden hour",
  referenceImages: [
    { image: { inlineData: { mimeType: "image/png", data: styleRefBase64 } } },
  ],
});
```

### Character Consistency

Provide reference images of a character to maintain appearance across different scenes and prompts.

### Ingredients to Video (Scene Composition)

Provide reference images of a scene, character, or object to guide generation. Now includes audio generation.

### First/Last Frame Control

Supply opening and closing images for smooth transitions between specific visual states. Directly applicable to recreating transitions observed in reference videos.

### Using Frames from a Reference Video

Yes, you can extract frames from a reference video and use them as inputs:

```bash
# Extract key style frames from reference video
ffmpeg -i reference.mp4 -vf "select=gt(scene\,0.3)" -vsync vfr style_frames/kf_%04d.jpg

# Use first and last frames for transition matching
ffmpeg -i reference.mp4 -vf "select=eq(n\,0)" -vframes 1 first.jpg
ffmpeg -sseof -0.1 -i reference.mp4 -vframes 1 last.jpg
```

Then feed these extracted frames into:
- **Reference-to-video**: for subject/style consistency
- **First-last-frame**: for transition matching
- **Image-to-video**: for animating a specific frame with new motion

### Additional Veo 3.1 Controls

| Control | Description |
|---------|-------------|
| Object insertion/removal | Add or remove objects maintaining scale, interactions, shadows |
| Camera controls | Precise framing and exact camera movement |
| Outpainting | Expand videos beyond original frame for different aspect ratios |
| Scene extension | Continue narrative from last second of previous shot |
| Video chaining | Up to 20 extensions (~148s total) |

---

## 8. Content Repurposing Tools

Tools that take a reference and generate variations across platforms.

### Full-Pipeline Repurposing

| Tool | Input | Analysis | Output | API |
|------|-------|----------|--------|-----|
| **OpusClip** | Long-form video URL | Big data trend analysis, visual/audio/sentiment cues | Short clips with captions, transitions, CTA optimization | Yes |
| **Quso.ai** (fka Vidyo.ai) | Video URL | AI scene detection (Cutmagic), engagement scoring (Intelliclips) | Platform-optimized clips, subtitles, social captions, hashtags | Limited |
| **Descript** | Video/audio file | Transcription-based editing, AI co-editor (Underlord) | Clips, regenerated sections, eye contact correction | Yes |
| **Kapwing** | Video/document/blog | Smart Cut AI segmentation | Resized/reformatted content per platform | Yes |

### What These Tools Extract

**OpusClip** is the most advanced for reference-based repurposing:
- Identifies "highlighting moments" using big data against social/marketing trends
- ClipAnything: works across all video genres using visual + audio + sentiment cues
- ReframeAnything: AI object tracking for platform-specific aspect ratios
- Generates: dynamic captions (97%+ accuracy), smooth transitions, CTA optimization
- AI B-Roll generation, audio enhancement, voice-over synthesis
- Brand template application for consistent styling
- Supports 20+ languages
- **API integration available** for automated pipelines

### Programmatic Repurposing Stack

For maximum control, build a custom pipeline:

```
Source Content (URL or file)
      ↓
[yt-dlp] → download
[Whisper/Gemini] → transcribe
[Gemini/Claude] → analyze structure, identify top moments
      ↓
[Claude] → rewrite for each platform (X thread, LinkedIn post, carousel text)
[Nano Banana] → generate platform-specific images (1080x1350 carousel, 1080x1080 square)
[Veo 3.1] → generate B-roll clips matching source style
[Remotion] → compose video clips with motion graphics
[ffmpeg] → resize/crop for each platform
      ↓
[Publishing tools] → distribute
```

---

## 9. Using LLMs for Video Analysis and Creative Brief Generation

### Gemini (Best for Full Video Analysis)

Gemini is the only major LLM that processes full video natively (audio + visual). This makes it the primary tool for video analysis.

**Capabilities:**
- Process videos up to 1 hour (1M context) or 3 hours (low-res)
- Analyze both audio and visual streams simultaneously
- Timestamp-aware queries ("What happens at 00:05?")
- Structured JSON output via `responseMimeType: "application/json"`

**Recommended prompt for creative brief generation:**

```
Analyze this video and generate a comprehensive creative brief as JSON:

{
  "overview": {
    "platform": "detected platform",
    "format": "reel/story/post/thread",
    "genre": "educational/entertainment/promotional/storytelling",
    "targetAudience": "description"
  },
  "visual": {
    "aspectRatio": "16:9 or 9:16 or 1:1",
    "dominantColors": ["#hex1", "#hex2", "#hex3"],
    "colorMood": "warm/cool/neon/muted/pastel",
    "lightingStyle": "natural/studio/dramatic/flat",
    "filterOrGrade": "description of any color grading",
    "graphicElements": ["text overlays", "icons", "borders", "stickers"]
  },
  "typography": {
    "hasTextOverlays": true,
    "style": "kinetic/static/handwritten/minimal",
    "fontCharacter": "bold sans-serif/thin serif/playful/corporate",
    "animationType": "word-by-word/fade/slide/typewriter/none",
    "position": "center/bottom-third/top/varies"
  },
  "pacing": {
    "totalDuration": "seconds",
    "averageShotLength": "seconds",
    "pacingStyle": "fast/medium/slow/building",
    "transitionTypes": ["hard cut", "fade", "swipe", "zoom"],
    "rhythmNotes": "description of visual rhythm"
  },
  "structure": {
    "hook": {
      "type": "question/stat/contrarian/visual-shock/before-after",
      "durationSeconds": 0,
      "description": "what the hook does"
    },
    "sections": [
      { "name": "section name", "startTime": "MM:SS", "endTime": "MM:SS", "purpose": "description" }
    ],
    "cta": {
      "type": "follow/link/save/comment/none",
      "placement": "end/overlay/verbal",
      "text": "exact CTA if visible"
    }
  },
  "audio": {
    "hasVoiceover": true,
    "voiceCharacter": "description",
    "hasBGMusic": true,
    "musicGenre": "description",
    "musicEnergy": "high/medium/low",
    "hasSFX": true,
    "sfxTypes": ["whoosh", "pop", "ding"]
  },
  "contentPattern": {
    "hookFormula": "reusable formula with [placeholders]",
    "bodyFormula": "reusable structure description",
    "ctaFormula": "reusable CTA formula with [placeholders]"
  }
}
```

### Claude (Best for Frame Analysis + Content Generation)

Claude excels at detailed frame analysis and generating matching content from briefs.

**Recommended workflow:**

```
1. Extract 10-20 keyframes from reference video (ffmpeg)
2. Send frames to Claude with analysis prompt
3. Claude returns style brief + content template
4. Send brief + new topic to Claude for content generation
5. Claude outputs: social copy, Remotion composition code, image prompts
```

**Key advantages of Claude for this workflow:**
- Up to 600 images per API request (more frames = better analysis)
- Strong at code generation (Remotion TSX, structured JSON)
- Excellent at matching tone and style in writing
- Can generate complete content packages (post copy + image prompts + video scripts)

### Combined Gemini + Claude Pipeline (Recommended)

```
Reference Video
      ↓
[Gemini] — Full video analysis (audio + visual + temporal)
      ↓ produces
Creative Brief (JSON)
      ↓
[Claude] — Content generation from brief
      ├── Social copy matching template
      ├── Remotion composition TSX
      ├── Image generation prompts (for Nano Banana)
      ├── Video generation prompts (for Veo 3.1)
      └── Audio direction (for ElevenLabs)
```

This leverages Gemini's native video understanding for analysis and Claude's superior code generation and writing for output.

---

## Tool Summary

### Content Extraction

| Tool | Purpose | Platforms |
|------|---------|-----------|
| yt-dlp | Download video + metadata | 1000+ sites including X, Instagram, TikTok |
| Apify scrapers | Structured metadata + engagement | Instagram, TikTok, X, LinkedIn |
| ffmpeg | Frame extraction, format conversion | Local processing |

### Content Analysis

| Tool | Best For | Input Limit |
|------|----------|-------------|
| Gemini 2.5 Pro | Full video analysis (audio + visual) | 1hr video (1M context) |
| Claude Opus | Frame analysis + code generation | 600 images per request |
| Twelve Labs | Video indexing + semantic search | Enterprise video libraries |

### Content Generation (Visual)

| Tool | Capability | Via |
|------|-----------|-----|
| Nano Banana 2 | Image generation matching style palettes | @google/genai |
| Veo 3.1 | Video from reference images/frames, style matching | @google/genai or fal.ai |
| Kling v3 Motion Control | Motion transfer from reference video to new character | fal.ai |
| Runway Gen-4 Turbo | Style-referenced video generation with tagged images | @runwayml/sdk |

### Composition + Rendering

| Tool | Approach | Best For |
|------|----------|----------|
| Remotion | React components, full creative control | Complex compositions |
| Creatomate | JSON templates + REST API | Batch social content |
| Shotstack | JSON templates + cloud rendering | High-volume production |

### Content Repurposing

| Tool | Strength | API |
|------|----------|-----|
| OpusClip | Best automated clip extraction + optimization | Yes |
| Quso.ai | Multi-platform reformatting + captions | Limited |
| Descript | Text-based editing + AI regeneration | Yes |
| Kapwing | Smart Cut + multi-format export | Yes |

### Publishing

| Tool | Platform |
|------|----------|
| xurl CLI | X/Twitter |
| twitter-mcp-server | X/Twitter (via MCP) |
| ig-mcp | Instagram |
| linkedin-mcp | LinkedIn |
| Ayrshare MCP | Multi-platform |

---

## Recommended Packages

```bash
# Core analysis
bun add @google/genai              # Gemini video analysis + Nano Banana + Veo 3.1
bun add @anthropic-ai/sdk          # Claude frame analysis + content generation

# Video generation (multi-provider)
bun add @fal-ai/client             # Veo 3.1, Kling, Sora — single API
bun add @runwayml/sdk              # Runway Gen-4 Turbo (style references)

# Composition
bun add remotion @remotion/cli     # Programmatic video composition
bun add @remotion/media-parser     # Parse AI clip metadata
bun add @remotion/transitions      # Scene transitions

# Audio
bun add elevenlabs                 # Voiceover generation

# Utilities (system-level)
# yt-dlp — brew install yt-dlp
# ffmpeg — brew install ffmpeg
```
