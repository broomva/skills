# X Blog Post — Long-Form Articles on X

## What It Is

X supports full long-form articles (formerly "Twitter Articles") with rich formatting, inline images, videos, GIFs, and no character limit. This is the X equivalent of a blog post — not a thread, not a tweet, but a complete article published natively on the platform.

## Why It Matters

- **Algorithm boost**: Long-form content keeps users on-platform, which X's algorithm rewards with distribution
- **Multimedia-native**: Inline images, GIFs, and video clips play natively — no external links needed
- **Engagement surface**: Users can reply, quote, repost, and bookmark — driving all engagement signals
- **SEO**: X articles are indexed by search engines
- **Distribution**: Appears in feeds, search results, and follower timelines

## How It Differs from broomva.tech Post

| Aspect | broomva.tech | X Blog Post |
|--------|-------------|-------------|
| **Tone** | Technical, structured, evergreen | Conversational, opinionated, timely |
| **Media density** | 1 image per ~300 words | 1 media asset per section (every ~150-200 words) |
| **Structure** | Formal sections with headers | Shorter sections, more visual breaks |
| **Length** | 800-2500 words | Flexible — as long or short as needed |
| **Hook** | Informational, SEO-friendly | Provocative, curiosity-driven, personal |
| **CTA** | "Install X" or "Read more" | Embedded — engagement IS the CTA |
| **Formatting** | Markdown/MDX with code blocks | Rich text with inline media |

## Content Strategy

### The Multimedia-First Rule

Every section of an X blog post should be accompanied by at least one visual asset:

| Section Type | Best Media | Generation Tool |
|-------------|-----------|----------------|
| Hook / intro | Hero image (striking, thumbnail-worthy) | Imagen 4.0 |
| Architecture / system | Diagram or flowchart | Imagen 4.0 or `/pencil` |
| Demo / walkthrough | GIF (terminal recording or UI flow) | ffmpeg from screen recording or Veo clip |
| Data / metrics | Data visualization or stat card | Imagen 4.0 |
| Code / technical | Syntax-highlighted code screenshot | Carbon or silicon.sh |
| Concept / abstract | AI-generated conceptual illustration | Imagen 4.0 |
| Video demo | Short inline clip (8-15s) | Veo 3.1 |

### Media Generation Checklist

For each X blog post, generate:
1. **Hero image** — The thumbnail. Must be striking enough to stop scrolling. Use Imagen 4.0.
2. **1 supporting image per major section** — Diagrams, screenshots, or AI illustrations
3. **At least 1 GIF** — Animated demo, terminal recording, or visual flow
4. **Optional video clip** — 8-15s Veo 3.1 clip for the most impactful section
5. **Code screenshots** — If showing code, use syntax-highlighted images (not raw text)

### Writing for X's Audience

- **Lead with the most provocative claim** — X rewards strong opinions
- **Use short paragraphs** — 2-3 sentences max per paragraph
- **Include personal experience** — "I built this" > "One could build this"
- **Be specific** — Numbers, timelines, concrete results > vague claims
- **End sections with a visual** — Breaks up text, increases scroll depth
- **Conversational tone** — Write like you're explaining to a smart friend, not writing docs

### Hook Formula for X Blog Posts

The hero image + first sentence determine whether anyone reads past the fold.

**Hero image**: Dark, technical, visually striking. Must communicate the topic at a glance without text.

**First sentence patterns**:
- "I [did something concrete]. Here's everything I learned." (earned insight)
- "This [artifact/system] was built by the thing it describes." (meta-proof)
- "[Surprising stat or claim]. And I can prove it." (data hook + confidence)
- "Everyone is doing [X]. We did [Y] instead. The results:" (contrarian)
- "In [timeframe], [outcome]. No [expected tool]. Here's the stack:" (constraint-driven)

## Structure Template

```markdown
# Title (clear, benefit-driven or curiosity-driven)

[Hero image — full width]

[Hook paragraph — 1-2 sentences, provocative or surprising]

## Section 1: The Setup
[Context in 2-3 short paragraphs]
[Supporting image or diagram]

## Section 2: The Core Insight
[Main teaching or argument]
[Code screenshot or architecture diagram]
[GIF demo if applicable]

## Section 3: The Evidence
[Data, metrics, before/after]
[Stat card or data visualization]

## Section 4: The How
[Implementation details or walkthrough]
[Video clip or terminal GIF]
[Code examples as images]

## Section 5: The Takeaway
[One memorable conclusion — single paragraph]
[CTA woven naturally into the narrative]
```

## Publishing

X blog posts can be published via `xurl` as a regular post with the article content, or composed directly in the X web interface. For long-form with rich media:

1. **Compose in X's editor** — Upload images and video natively for best display
2. **Or use the API** — Post with `xurl post` including media attachments

For multimedia-rich articles, composing in the X web editor is recommended since it handles inline media positioning better than the API.

### Media Upload via xurl

```bash
# Upload image, get media ID
MEDIA_ID=$(xurl media upload hero.png 2>&1 | jq -r '.media_id_string')

# Post with media
xurl post "Article text..." --media hero.png
```

## Growth Integration

X blog posts are the long-form anchor that threads and posts can reference. For maximum growth impact:

1. **Publish the X thread FIRST** — it drives initial engagement and visibility
2. **The blog post lives in the self-reply** of the thread's final tweet — not in the thread body
3. **Share terminal screenshots and demos as standalone X posts** in the days following — each references back to the article
4. **Tag relevant accounts** in the thread tweet 1, not in the blog post itself
5. **Embed the article link in your X bio** or pinned post during its promotion window

See [x-growth-strategy.md](x-growth-strategy.md) for the full growth playbook.

## Quality Gates (X Blog Post Specific)

- [ ] Hero image is striking enough to stop scrolling (not generic AI art)
- [ ] Hero image shows something REAL — running code, architecture, data — not stock/AI filler
- [ ] Every section has at least one visual (image, GIF, or video)
- [ ] Opening sentence is provocative or surprising (not descriptive)
- [ ] Paragraphs are 2-3 sentences max
- [ ] At least 1 GIF showing something in action
- [ ] Tone is conversational, not documentation-style
- [ ] Personal experience or first-hand evidence included ("I built" not "one could build")
- [ ] No section longer than 200 words without a visual break
- [ ] Companion X thread drafted (article is promoted via thread, not posted in isolation)
