# Output Structure

## Directory Convention

Each invocation produces a self-contained package at:

```
/broomva/posts/{YYYY-MM-DD}-{slug}/
```

**Slug rules:**
- Kebab-case, lowercase
- 3-6 words maximum
- No dates in slug (date is the prefix)
- Descriptive but concise: `agent-os-rust`, `haima-payments-launch`, `control-theory-applied`

## Full Directory Tree

```
{YYYY-MM-DD}-{slug}/
│
├── README.md                    # Package manifest
├── brief.md                     # Content brief (input)
├── research.md                  # Research notes (may be empty for opinion pieces)
├── outline.md                   # Structural blueprint with angle + framework
│
├── broomva-tech-post.mdx        # Primary long-form (broomva.tech)
├── substack-post.md             # Alternative long-form (if requested)
│
├── x-blog-post.md               # X long-form article (multimedia-rich, freeform length)
├── x-post.md                    # X single post (280 chars)
├── x-thread.md                  # X thread (5-8 tweets)
├── linkedin-post.md             # LinkedIn post
├── instagram-post.md            # Instagram caption + carousel slide spec
├── instagram-reel.md            # Reel script with timing
│
├── media/
│   ├── image-prompts.md         # AI generation prompts for all images
│   ├── audio-script.md          # TTS-ready narration text
│   ├── video-script.md          # Remotion/video composition outline
│   ├── gif-concept.md           # GIF animation concept + creation command
│   │
│   ├── hero.png                 # Generated hero/social card
│   ├── thumbnails/
│   │   ├── x-card.png           # 1200×675
│   │   ├── linkedin-card.png    # 1200×628
│   │   └── ig-cover.png         # 1080×1350
│   ├── png/                     # Supporting static images
│   ├── gif/                     # Animated GIFs
│   ├── mp3/                     # Audio files
│   │   └── narration.mp3        # Blog narration
│   └── mp4/                     # Video files
│       ├── blog-video.mp4       # 16:9 blog/social video
│       └── reel-vertical.mp4    # 9:16 Instagram reel
│
└── strategy/
    ├── audience.md              # Who, where, what they care about
    ├── platform-strategy.md     # Per-platform approach + rationale
    ├── distribution-plan.md     # Publishing sequence + timing
    └── cta.md                   # Call-to-action strategy per channel
```

## README.md Format

```markdown
# {Post Title}

**Created**: {YYYY-MM-DD}
**Slug**: {slug}
**Status**: draft | ready | published

## Brief
{One-sentence summary from brief.md}

## Content Package

| File | Status | Platform |
|------|--------|----------|
| broomva-tech-post.mdx | ✅ ready | broomva.tech |
| x-post.md | ✅ ready | X |
| x-thread.md | ✅ ready | X |
| linkedin-post.md | ✅ ready | LinkedIn |
| instagram-post.md | ✅ ready | Instagram |
| instagram-reel.md | ✅ ready | Instagram |

## Media Assets

| Asset | Status | Notes |
|-------|--------|-------|
| hero.png | ⏳ prompt ready | Run Nano Banana with prompt from image-prompts.md |
| narration.mp3 | ⏳ script ready | Run kokoro-tts with audio-script.md |
| blog-video.mp4 | ⏳ script ready | Render Remotion composition |

## Publishing

See `strategy/distribution-plan.md` for recommended sequence.

## Deploy to broomva.tech

\```bash
cp broomva-tech-post.mdx ~/broomva/broomva.tech/apps/chat/content/writing/{slug}.mdx
cp -r media/png/ ~/broomva/broomva.tech/apps/chat/public/images/writing/{slug}/
cp media/mp3/narration.mp3 ~/broomva/broomva.tech/apps/chat/public/audio/writing/{slug}.mp3
\```
```

## File Status Indicators

| Icon | Meaning |
|------|---------|
| ✅ | Content complete, ready for use |
| ⏳ | Prompt/script ready, needs execution (tool unavailable or deferred) |
| ❌ | Skipped (not applicable or not requested) |
| 🔄 | In progress |

## Conditional Files

Not all files are always generated:

- `substack-post.md` — Only if `destination: substack` in brief
- `research.md` — May be minimal for personal/opinion posts
- `media/mp4/` — Only if `mp4` in media targets
- `media/mp3/` — Only if `mp3` in media targets
- `media/gif/` — Only if `gif` in media targets or a demo-oriented post

Always create the file but mark as "❌ Not targeted" if skipped, so the package structure remains predictable.
