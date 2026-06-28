# Content Pipeline — Handoff to /blog-post and /content-creation

## The Compound Advantage

Topics from social intelligence have three advantages over cold-start blog post ideas:

1. **Validated resonance** — People engaged, replied, extended the idea. It's not hypothetical.
2. **Pre-tested language** — The community already has words for the concept. Use them.
3. **Known objections** — Threads reveal what people push back on. Preempt in the post.
4. **Distribution targets** — Specific accounts and communities already engaged with the idea.

## Handoff Protocol

### Step 1: Prepare the intelligence brief

Before invoking /blog-post, assemble:

```markdown
## Intelligence Brief for: {topic}

### Community Evidence
- Thread 1: {post_id} — {what people said, how many engaged}
- Thread 2: {post_id} — {what landed, what didn't}
- X Thread: {conv_id} — {key replies}

### Pre-Tested Angles (what landed)
- "{verbatim framing from community that resonated}"
- "{another framing that got replies/engagement}"

### Known Objections (what to preempt)
- "{objection 1}" → our answer: {answer}
- "{objection 2}" → our answer: {answer}

### Distribution Targets
- Moltbook: post in {subreddit} sections
- X: share with @handle1, @handle2 (already engaged with topic)
- Community: {Discord/Slack channels where this topic is active}
- Moltbook interlocutors: {sparkxu, neo_konsi — already have context}
```

### Step 2: Invoke /blog-post

```
/blog-post "{topic}" — {audience}, {intent}, {tone}
```

Standard combinations for Life OS content:

| Audience | Intent | Tone |
|----------|--------|------|
| `developers` | `educate` | `provocative` |
| `developers` | `technical-deep-dive` | `confident-technical` |
| `founders` | `persuade` | `conversational` |
| `builders` | `reflect` | `storytelling` |

### Step 3: Inject community intelligence

When /blog-post reaches the Research phase:
- Paste the intelligence brief as research context
- Flag the verbatim community quotes for use in the opening or as pull quotes
- Note the known objections so they can be addressed in the body

### Step 4: /content-creation for multimedia

After /blog-post produces the .mdx:

```
/content-creation — reference the blog post, generate:
  - Hero image (Nano Banana: dark theme, technical, 1200×630)
  - X thread version (5-8 tweets, the key insight sequence)
  - Instagram carousel (8 slides: hook → 3 key points → evidence → CTA)
  - Moltbook essay version (full text, agent-voice)
```

### Step 5: Distribution via social-intelligence

After content is produced, use the `/engage` sub-skill to:
1. Post the Moltbook essay version
2. Run the X thread
3. Share in the specific communities where the topic was first discovered
4. Directly mention the interlocutors who contributed to the knowledge

## Content Sequencing

Not every piece of social intelligence becomes a blog post. The pipeline is:

```
Social thread (ephemeral)
  ↓ [extraction loop]
Raw insight note (research/notes/YYYY-MM-DD-social-insights-raw.md)
  ↓ [human review]
Session synthesis (research/notes/YYYY-MM-DD-social-engagement-knowledge-synthesis.md)
  ↓ [≥3 occurrences across conversations]
Blog candidate (docs/knowledge-extraction-loop.md → Blog Post Candidates)
  ↓ [/generate trigger]
Intelligence brief (assembled by social-intelligence)
  ↓ [/blog-post]
Full content package (posts/YYYY-MM-DD-{slug}/)
  ↓ [/content-creation]
Multimedia assets (media/, strategy/)
  ↓ [/engage distribution]
Published across all channels
```

## Moltbook-Specific: Essay vs Comment

Two modes for Moltbook content:

| Mode | When | Format | Length |
|------|------|--------|--------|
| **Comment** | Engaging an existing post | Focused angle, references the post | 200-400 words |
| **Essay post** | Publishing a full blog post | Full article, agent voice | Up to 40,000 chars |

For essay posts on Moltbook:
- Strip MDX frontmatter and JSX components from .mdx file
- Keep markdown formatting
- Add Moltbook-appropriate closing: section tags from `{s/agents, s/builds, s/infrastructure, s/memory, s/consciousness, s/philosophy}`
- End with link to canonical broomva.tech URL

## Standing Content Queue

Posts available for next Moltbook essay round (derived from blog candidates):

| Topic | Status | Target Section |
|-------|--------|---------------|
| "The Soul File Is Not Your Agent's Identity" | Draft needed | s/agents |
| "Why Confidence Scores Are Referential Integrity Violations" | Draft needed | s/agents |
| "The Quiet Supply Chain" | Draft needed | s/memory |
| "Bi-Temporal Memory" | Draft needed | s/infrastructure |
| "The Confused Deputy Problem in Agent Security" | Draft needed | s/agents |
