# Multimedia Production

## Philosophy

Media is not decoration — it is content. Each asset must advance the narrative, not just break up text. If an image doesn't make the post better without its caption, it's the wrong image.

## Asset Production Matrix

| Asset | Primary Tool | Fallback | Dimensions | Format |
|-------|-------------|----------|-----------|--------|
| Hero / social card | Nano Banana (`gemini-3.1-flash-image`) | `/pencil` MCP | 1200×675 (blog), 1200×628 (OG) | PNG |
| Supporting images | Nano Banana or `/agent-browser` screenshots | Stock + optimization | 1200px wide | PNG/JPG |
| Custom diagrams | `/pencil` MCP | Mermaid in post | Variable | PNG |
| Instagram carousel | `/pencil` MCP | Canva manual | 1080×1350 | PNG |
| Instagram reel | Remotion (9:16) or Veo 3.1 | Manual screen recording | 1080×1920 | MP4 |
| Blog video | Remotion (16:9) + AI clips (Veo 3.1) | ffmpeg assembly | 1920×1080 | MP4 |
| GIF preview | ffmpeg from video | ImageMagick from frames | 960px wide | GIF |
| Audio narration | kokoro-tts / Edge TTS | ElevenLabs (premium) | — | MP3 (128kbps) |
| X post image | Nano Banana | Cropped hero | 1200×675 | PNG |
| LinkedIn image | Same as hero | — | 1200×628 | PNG |

## Hero Image Generation

Every post needs a hero image. It becomes the social card thumbnail, blog header, and visual anchor.

**Nano Banana (Gemini Images) prompt pattern**:
```
A [style] technical illustration for a blog post about [topic].
[Visual concept tied to the post's core metaphor].
Dark background, [accent color] highlights, clean composition.
Professional, modern, minimal text. 1200x675 pixels.
```

**Style directions by post type**:
- Technical deep dive → architectural diagram aesthetic, circuit-board patterns
- Personal reflection → abstract, organic, soft gradients
- Case study → data visualization aesthetic, charts, metrics
- Launch/announcement → product showcase, hero shot, bold typography
- Opinion/contrarian → visual tension, contrast, unexpected juxtaposition

**API call** (using @google/genai):
```javascript
import { GoogleGenAI } from "@google/genai";
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
const response = await ai.models.generateContent({
  model: "gemini-3.1-flash-image",
  contents: "[prompt]",
  config: { responseModalities: ["TEXT", "IMAGE"] },
});
// Save inline data as PNG
```

## Supporting Images

**Placement rule**: One image per ~300 words. Articles with images every 75-100 words get 2× more social shares.

**Types and when to use**:
- **Screenshots** — Process walkthroughs, UI evidence. Crop to relevant area.
- **Diagrams** — Architecture, workflows, system design. Strongest brand differentiation.
- **Data viz** — Metrics, comparisons, trends. Bar for categories, line for time series.
- **AI-generated** — Conceptual illustrations, mood images. Never for evidence.

**Optimization**:
```bash
# Resize and optimize
magick input.png -resize 1200x -quality 85 output-opt.png

# Naming convention
{subject}-{descriptor}-opt.png
```

## Video Production

### Remotion Composition (15-30s blog video)

**Scene structure**:
```
Title (3-4s) → Key Stat (3s) → Screenshots/Evidence (2-3s each) → Workflow (3-4s) → Closing CTA (3-4s)
```

**Key rules**:
- Use `Img` + `staticFile()` (never `<img>` tag)
- Use `spring()` for organic motion (never CSS transitions)
- Use `<Sequence>` with `premountFor` for preloading
- Include `-movflags +faststart` in any ffmpeg preprocessing for AI clips

### Veo 3.1 AI Video Clips

For cinematic B-roll, product demos, abstract visuals:
- 720p/1080p/4K, 4/6/8 seconds per clip
- Native audio at 48kHz
- Chain up to 20 clips (~148s total)
- Aspect ratios: 16:9 (blog) or 9:16 (reels)

### GIF Creation

```bash
# From video
ffmpeg -y -i video.mp4 -vf "fps=12,scale=960:-1:flags=lanczos" -c:v gif output.gif

# From image sequence (2s per frame)
magick f1.png f2.png f3.png -resize 1200x675! -set delay 200 -loop 0 flow.gif
```

**When to use GIF**: Micro-interactions, quick UI flows, loop-worthy moments. Max one per post.

## Audio Narration

### Script Preparation

1. Extract post body text (strip frontmatter and markdown formatting)
2. Add natural pause markers: `[pause]` between sections, `[beat]` for emphasis
3. Spell out abbreviations on first use: "AI (artificial intelligence)"
4. Note pronunciation: "Lago (LAH-go)", "Arcan (AR-kan)"

### Generation

```bash
# kokoro-tts (fast, good quality, local)
kokoro-tts post-body.txt /tmp/narration.wav --voice af_sarah

# Convert to MP3
ffmpeg -i /tmp/narration.wav -codec:a libmp3lame -b:a 128k narration.mp3

# Edge TTS (free, Microsoft Neural voices)
edge-tts --text "$(cat post-body.txt)" --write-media narration.mp3 --voice en-US-AriaNeural
```

### Integration with broomva.tech

1. Place MP3 at `public/audio/writing/{slug}.mp3`
2. Add `audio: /audio/writing/{slug}.mp3` to post frontmatter
3. The `ContentArticle` component renders a native `<audio>` player automatically

## Media Prompt File Format

In `media/image-prompts.md`, structure prompts as:

```markdown
## Hero Image
**Concept**: [What the image represents conceptually]
**Prompt**: [Full AI generation prompt]
**Dimensions**: 1200×675
**Style**: [dark-technical / organic-soft / data-viz / product-hero]
**Usage**: Blog header, X thread image 1, LinkedIn post image, OG card

## Supporting Image 1 — [Section Name]
**Concept**: [Tied to specific content in that section]
**Prompt**: [Full prompt]
**Dimensions**: 1200×auto
**Usage**: Blog inline after paragraph X

## Instagram Carousel Slides
**Concept**: [Overall carousel narrative]
**Slides**: [Number of slides, what each contains]
**Dimensions**: 1080×1350
**Tool**: /pencil MCP or manual design
```

## Asset Naming Convention

```
{slug}/media/png/hero-social-card-opt.png
{slug}/media/png/section-1-architecture-opt.png
{slug}/media/png/section-3-metrics-opt.png
{slug}/media/gif/ui-flow-demo.gif
{slug}/media/mp4/blog-video-30s.mp4
{slug}/media/mp4/reel-vertical.mp4
{slug}/media/mp3/narration.mp3
{slug}/media/thumbnails/x-card.png
{slug}/media/thumbnails/linkedin-card.png
{slug}/media/thumbnails/ig-cover.png
```
