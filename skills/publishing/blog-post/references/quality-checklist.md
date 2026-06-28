# Quality Checklist

Run this checklist before marking a content package as complete. Each gate must pass or be explicitly waived with rationale.

## Content Quality

### Long-Form Post
- [ ] Title is specific and compelling (not generic "Thoughts on X")
- [ ] Opening hook creates curiosity or states a bold claim within 2 sentences
- [ ] Clear angle statement identifiable within first 3 paragraphs
- [ ] At least 3 evidence points (data, examples, screenshots, quotes)
- [ ] Closing has a memorable one-liner, not a summary rehash
- [ ] Reading time is appropriate (800-2500 words for most posts)
- [ ] No placeholder text or TODO markers remain

### Factual Accuracy
- [ ] All statistics are sourced or from first-hand experience
- [ ] Technical claims are verifiable
- [ ] Dates and version numbers are current
- [ ] No speculative claims presented as facts

## Platform Adaptation Quality

### Unique Hooks (Critical)
- [ ] X post hook ≠ X thread hook ≠ LinkedIn hook ≠ Instagram caption opener
- [ ] Each hook is optimized for its platform's attention pattern
- [ ] No hook is a truncated version of another

### X Post
- [ ] ≤ 280 characters
- [ ] Self-contained (understandable without clicking anything)
- [ ] Contains the single most surprising insight
- [ ] Image attached (REQUIRED — text-only gets 60% less reach)
- [ ] Image shows something real (terminal, diagram, data) — not generic AI art
- [ ] No external links in post body (links go in self-reply)
- [ ] Engagement hook present (question, contrarian frame, or reply invitation)
- [ ] Tags are genuine (1-2 max, only accounts whose work is referenced)

### X Thread
- [ ] 5-8 tweets (not 3, not 15)
- [ ] Tweet 1 is the strongest hook (50% of effort spent here)
- [ ] Tweet 1 has an image attached (REQUIRED)
- [ ] Each tweet stands alone while building momentum
- [ ] Image attached every 2-3 tweets
- [ ] Tweets numbered (1/N format)
- [ ] No external links in thread body (links in self-reply)
- [ ] Final tweet drives replies or conversation (not just "read more")
- [ ] Self-reply with link/Discord invite planned
- [ ] Thread adds value a single post couldn't — if not, use X post instead

### LinkedIn
- [ ] Hook ≤ 210 characters (before "See More" fold)
- [ ] Includes bullet list of 3-5 takeaways
- [ ] 3-5 relevant hashtags (not trending-chasing)
- [ ] Professional tone without corporate jargon
- [ ] Ends with a question or clear CTA

### Instagram Post
- [ ] Carousel cover has ≤ 10 words
- [ ] 8-12 slides specified
- [ ] One concept per slide (flashcard, not paragraph)
- [ ] Caption adds depth beyond carousel content
- [ ] CTA includes "save" or "share" (highest-value IG actions)

### Instagram Reel
- [ ] 3-second hook specified
- [ ] Script is 15-60 seconds
- [ ] Captions included (80% watch muted)
- [ ] 9:16 vertical format specified
- [ ] CTA at end

## Media Quality

### Images
- [ ] Hero image prompt is specific and tied to post concept
- [ ] Supporting image prompts are tied to specific content sections
- [ ] All dimensions specified correctly per platform
- [ ] Naming convention followed: `{subject}-{descriptor}-opt.{ext}`

### Video (if targeted)
- [ ] Scene breakdown with duration per scene
- [ ] Total duration 15-30 seconds (or justified if longer)
- [ ] ffmpeg preprocessing includes `-movflags +faststart`
- [ ] Both 16:9 and 9:16 versions planned (if IG reel targeted)

### Audio (if targeted)
- [ ] Script is narration-ready (no markdown, natural pauses)
- [ ] Pronunciation guides for technical terms included
- [ ] Target: MP3 128kbps

### GIF (if targeted)
- [ ] Max one per post
- [ ] Shows a micro-interaction or flow preview (not a random animation)
- [ ] Width ≤ 960px, fps ≤ 12

## Strategy Quality

### Audience
- [ ] Target audience is specific (not "everyone")
- [ ] Audience's existing knowledge level is noted
- [ ] Audience's primary platform is identified

### Distribution
- [ ] Publishing sequence specified (which platform first)
- [ ] Cross-linking strategy defined (blog ← social, social → blog)
- [ ] Timing gaps between platform posts noted

### CTA
- [ ] Primary action is clear and specific
- [ ] CTA adapted per platform (not identical copy)
- [ ] CTA aligns with stated intent in brief

## Package Completeness

- [ ] README.md lists all files and their status
- [ ] brief.md captures the input
- [ ] outline.md shows the structural decisions
- [ ] All targeted platform files exist
- [ ] media/ directory has prompt files for all planned assets
- [ ] strategy/ directory has all four files
- [ ] Any skipped items are explained (tool unavailable, not applicable, etc.)
