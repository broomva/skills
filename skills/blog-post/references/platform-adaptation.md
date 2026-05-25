# Platform Adaptation

## Core Principle

The same *message* expressed in platform-*native* language. Never copy-paste and truncate. Each platform has its own attention economy, consumption pattern, and audience expectation.

## X Blog Post (Long-Form Article)

**Purpose**: Full long-form article published natively on X. Keeps users on-platform (algorithm rewards this). Rich inline media — images, GIFs, video clips play natively.

**How it differs from broomva.tech post**:
- More conversational and opinionated (less documentation-style)
- Higher media density — 1 visual per section (~150-200 words)
- Shorter paragraphs (2-3 sentences max)
- Personal voice ("I built this" not "one could build this")
- Provocative hook over informational hook

**Media-first rule**: Every section must have at least one visual asset:
- Hero image (Imagen 4.0 — striking, thumbnail-worthy)
- Architecture diagrams, flowcharts
- GIFs (terminal recordings, UI flows, demos)
- Short video clips (8-15s Veo 3.1)
- Code screenshots (syntax-highlighted, not raw text)
- Stat cards and data visualizations

**Structure**:
```
Hero image (full-width, stops scrolling)
Hook (1-2 sentences — provocative or meta)
---
Section 1: Setup (2-3 paragraphs + visual)
Section 2: Core insight (teaching + diagram/code + optional GIF)
Section 3: Evidence (data + stat card)
Section 4: How (walkthrough + video/GIF)
Closing (1 paragraph + natural CTA)
```

**Hook formulas**:
- "I [did something]. Here's everything I learned."
- "This [artifact] was built by the thing it describes."
- "[Surprising stat]. And I can prove it."
- "Everyone is doing [X]. We did [Y] instead."

**What works**: Strong opinions backed by evidence, multimedia-dense sections, personal narrative
**What fails**: Documentation tone, walls of text without visuals, vague claims, generic AI art

See [references/x-blog-post.md](x-blog-post.md) for the full guide.

## X Single Post (280 chars)

**Purpose**: Standalone insight that earns engagement (likes, replies, reposts). Also the primary format for building-in-public updates, contrarian takes, and moment surfing.

**Structure**:
- One surprising claim, stat, or reframe
- ALWAYS attach an image (text-only posts get 60% less reach)
- No external links in post body (X suppresses them) — put links in self-reply
- Include an engagement hook: question, contrarian frame, or invitation to reply

**What works**:
- Specific numbers: "We reduced build times from 47 minutes to 3.2 seconds"
- Contrarian takes: "The biggest lie in AI: you need more data"
- Concise frameworks: "3 rules for X: [rule]. [rule]. [rule]."
- Questions that provoke: "Why does every AI startup look the same?"
- Terminal screenshots showing real work running
- Before/after comparisons with visuals
- Tagging 1-2 accounts whose work you build on (genuine credit, not attention-seeking)

**What fails**:
- Generic motivational content
- External links in the post body (kills reach — use self-reply)
- Text-only posts without images
- Passive observations ("Interesting that...")
- Thread teasers in a single post ("A thread on why X is important")
- Tagging for attention without substance

**Growth patterns** (see [x-growth-strategy.md](x-growth-strategy.md)):
- **Build in public**: Terminal screenshot + 1-2 line insight (3-5x/week)
- **Contrarian take**: Strong opinion backed by your data/experience (1-2x/week)
- **Moment surfing**: React to breaking news with your running code (opportunistic)
- **Strategic reply**: Reply to big accounts with substance + your screenshot (3-5x/day)
- **Day N update**: "Day 47 of building X in Rust" + progress image (daily optional)

## X Thread (5-8 tweets)

**Purpose**: Develop an argument in tweet-sized beats. Each tweet stands alone while building momentum. Best format for "How I built X" stories, technical deep dives, and comparison posts.

**Structure** (7-tweet sweet spot):
```
1/7 — HOOK: The single most compelling claim or stat
      This tweet determines everything. Spend 50% of effort here.
      ALWAYS attach hero image (terminal, result, diagram)
      Tag 1-2 accounts if crediting their work (their engagement amplifies reach)
      Formula options:
        "[Number] [things] in [timeframe]. Here's what happened:"
        "Most [role]s think [belief]. The data says otherwise:"
        "We replaced [old] with [new]. The results:"

2/7 — CONTEXT: Set the scene (1-2 sentences, establish what was normal)

3/7 — INSIGHT 1: First key finding or argument
      [attach image — increases completion by 45%]

4/7 — INSIGHT 2: Second key finding, builds on the first

5/7 — INSIGHT 3: Third finding or the "but" moment
      [attach image — data viz, screenshot, or diagram]

6/7 — EVIDENCE: Strongest proof point, most surprising result

7/7 — CTA: Drive engagement, not just clicks
      "What's your experience with X? Reply below."
      or "We're going deeper in Discord: [invite]"
      [Put external links in self-reply, not here]
```

**Self-reply**: Post immediately after thread with external link + Discord invite. This is where links go — X doesn't suppress links in replies as aggressively.

**Rules**:
- Number tweets explicitly (1/7, 2/7...)
- One idea per tweet — never wall of text
- Generous line breaks between ideas
- Image every 2-3 tweets (tweet 1 ALWAYS has an image)
- Post full chain immediately via self-reply (don't trickle)
- Native images/video only — never external media links

## LinkedIn Post (1300 chars)

**Purpose**: Professional credibility, thought leadership, drive traffic to long-form.

**Structure**:
```
[HOOK — first 210 characters, before "See More" fold]
This is the most important part. It must create curiosity or state a bold claim.

[2-3 short paragraphs with key insights]
Use concrete numbers and specific examples.
Avoid corporate jargon — write like a smart person talking to peers.

Key takeaways:
• [Takeaway 1 — specific and actionable]
• [Takeaway 2]
• [Takeaway 3]
• [Takeaway 4 — optional]

[CTA — clear ask]
Link to the full post, ask a question, or invite discussion.

#tag1 #tag2 #tag3 (3-5 max, relevant, not trending-chasing)
```

**What works**:
- Opening with a personal experience or confession
- Specific metrics and outcomes
- "Here's what I learned" framing
- Bullet lists (LinkedIn's algorithm favors them)
- Asking a genuine question at the end

**What fails**:
- "I'm thrilled to announce..." (engagement killer)
- Long unbroken paragraphs
- More than 5 hashtags
- Tagging people who aren't genuinely relevant
- Humble-bragging without substance

**Hook formulas**:
- "I [did something unexpected]. Here's why:"
- "[Surprising stat]. Most people don't realize..."
- "The hardest lesson I learned about [topic]:"
- "Stop doing [common practice]. Do this instead:"
- "3 years ago, I [situation]. Today, [outcome]."

## Instagram Post (Caption + Carousel)

**Purpose**: Visual-first education. The carousel teaches; the caption adds depth.

**Carousel specs**:
- Aspect ratio: 4:5 (1080×1350px) for maximum feed presence
- Slides: 8-12 for educational content
- Design tool: `/pencil` MCP for custom slides

**Slide structure**:
```
Slide 1  — COVER: "Is this for me?" + "What will I get?" in ≤10 words
           Bold title, clean design, branded colors
Slide 2  — PROBLEM: The pain point (bold key phrase, 1-2 sentences max)
Slide 3  — INSIGHT 1: One point per slide, flashcard style
Slide 4  — INSIGHT 2: Visual > text. Use icons, diagrams, code snippets
Slide 5  — INSIGHT 3
Slide 6  — INSIGHT 4
Slide 7  — STAT: Key metric in large typography
Slide 8  — SUMMARY: 3-4 bullet takeaways
Slide 9  — CTA: "Save this for later 🔖" / "Share with someone who needs this"
```

**Caption structure** (up to 2200 chars):
```
[Hook — first line visible in feed]

[Story or context that adds depth beyond the carousel]

[Key insight not in the carousel — reward for reading]

[CTA: Save, share, follow, or link in bio]

.
.
.
#hashtags (20-30, mix of broad and niche, hidden after dots)
```

**What works**:
- Swipeable education (Instagram users love learning in slide format)
- Clean, consistent design across slides
- One visual concept per slide (not cramming)
- Mixing text slides with image/screenshot slides

## Instagram Reel (15-60s script)

**Purpose**: Discoverability. Reels reach non-followers more than any other format.

**Script structure**:
```
[0-3s]  HOOK: Visual or verbal pattern interrupt
        "Here's something nobody tells you about [topic]"
        or: Start with the result, then rewind

[3-8s]  PROBLEM: Quick setup of the tension
        "Every developer faces [problem]"

[8-25s] INSIGHT: Core value of the post
        Show, don't just tell. Screen recordings, diagrams, demos.
        If talking head: fast cuts, no filler words

[25-40s] EVIDENCE: Proof point (metric, demo, before/after)

[40-55s] TAKEAWAY: One clear lesson

[55-60s] CTA: "Follow for more" / "Link in bio" / "Save this"
```

**Technical specs**:
- Aspect ratio: 9:16 (1080×1920px)
- Duration: 15-60s (30s sweet spot for educational)
- Captions required (80% watch without sound)
- Trending audio optional (helps discovery but not required for educational)

**Production options**:
- **Remotion** — Programmatic composition with `spring()` animations, `<Sequence>` timing
- **Veo 3.1** — AI-generated B-roll clips (9:16, up to 8s per clip, chain up to ~148s)
- **Screen recording** — Best for code demos and UI walkthroughs

## Cross-Platform Consistency

While each adaptation is unique, maintain:
1. **Same core message** — The one-sentence angle statement appears in every piece (adapted per platform)
2. **Visual identity** — Same color palette, font style, hero image across platforms
3. **CTA alignment** — All roads lead to the same action (even if phrased differently)
4. **Fact consistency** — Same numbers, same claims, same evidence everywhere
5. **Temporal coherence** — Distribution timing creates a coordinated narrative, not random noise
