---
name: content-engine-loop
description: "Content Loop + Distribution — compounds existing broomva skills into a unified content lifecycle. Orchestrates /blog-post, /content-creation, /social-intelligence, /brainrot-for-good, and /brand-icons for multi-platform distribution. Adds performance tracking, feedback-driven identity refinement, content calendar, and campaign management. Triggers on: 'distribute content', 'content loop', 'publish campaign', 'content calendar', 'track performance'."
---

# Content Engine Loop — Content Lifecycle + Distribution

Compounds five existing Broomva skills into a closed-loop content lifecycle: generate, distribute, measure, refine, repeat. Every asset flows from creation through multi-platform distribution to performance tracking, and the metrics feed back into identity refinement.

## Compounding Table

The loop does not replace existing skills. It orchestrates them into a coordinated pipeline where each skill handles its domain and the loop handles sequencing, tracking, and feedback.

| Skill | What It Does in the Loop | Trigger Phase |
|-------|--------------------------|---------------|
| `/blog-post` | Full blog post production: topic to published MDX + audio + deploy | Create |
| `/content-creation` | Multimedia asset pipeline: AI images, video, TTS, social copy | Create |
| `/social-intelligence` | Social engagement loop: post, engage, extract insights | Distribute + Listen |
| `/brainrot-for-good` | High-retention video production: brainrot pacing + substance | Create |
| `/brand-icons` | Visual identity consistency: OG images, social avatars, favicons | Create |
| `/content-engine-autopilot` | Browser-based batch generation: Higgsfield, Weavy, etc. | Create |
| `/content-engine-dna` | Compiled identity: brand style, character, visual language | All phases |

### How They Compound

```
LISTEN
  ├─ INSIGHT (from /social-intelligence)          — post-engagement signals
  └─ SALES-SUBSTRATE (CRM + transcripts + perf)   — customer-doubt grounded
  │
  ▼
PLAN (content calendar picks topic + format + platform)
  │
  ▼
CREATE
  ├─ /blog-post         → MDX article + audio narration
  ├─ /content-creation   → Hero image, AI video clips, social copy
  ├─ /brainrot-for-good  → 30s TikTok/Reels cut
  ├─ /brand-icons        → OG image, social card
  └─ /content-engine-autopilot → Avatar video (Higgsfield), motion card (Weavy)
  │
  ▼
DISTRIBUTE
  ├─ Blog: broomva.tech via PR merge + Vercel deploy
  ├─ X: thread via xurl or X MCP
  ├─ LinkedIn: post via LinkedIn MCP
  ├─ Instagram: carousel via ig-mcp
  ├─ TikTok/Reels: short video upload (manual or API)
  └─ Moltbook: cross-post via /social-intelligence
  │
  ▼
MEASURE
  ├─ Pull metrics per asset per platform (views, likes, shares, saves, comments)
  ├─ Store in ~/.content-engine/metrics/{campaign-id}/metrics.json
  └─ Aggregate: best style, best tool, best scene type, best posting time
  │
  ▼
REFINE
  ├─ Promote high-performing styles to compiled identity
  ├─ Flag anti-patterns (styles that consistently underperform)
  ├─ Update content calendar pacing based on audience engagement patterns
  └─ Feed refined identity back to next CREATE cycle
```

### LISTEN Sources

The LISTEN phase pulls from two complementary inputs. Either source alone can drive content; together they cover the full customer-attention surface.

**INSIGHT — post-engagement signals.** Handled by `/social-intelligence`. Tracks what existing followers respond to: comment themes, repost networks, profile-view bursts, save patterns. Best for refining tone, format, and posting cadence on accounts that already have audience.

**SALES-SUBSTRATE — customer-doubt grounding.** CRM lead lists (segmented by country / sector / size / doubts), sales-call transcripts (Fireflies / Granola / Otter), prospecting notes, per-post performance metrics. Loaded as a single LLM context window — the *"cerebro de la empresa"* — that proposes posts grounded in the doubts customers actually raised on calls, not the doubts the founder imagines. Best for B2B accounts where prospect intent is captured in conversations the audience never sees.

The substrate has one precondition: recording discipline. *"Si no quedó grabado, no pasó."* Whatever isn't transcribed disappears from the substrate, and the model cannot propose posts about it. See the full pattern (mechanism, failure modes, rule-of-three ledger — currently N=1 from Alan Arguello, LinkedIn, 2026-05-22) at `research/entities/pattern/sales-substrate-as-content-fuel.md` in the broomva workspace.

## Campaign Management

A **campaign** is a coordinated set of content pieces around a theme, published across platforms over a defined time window.

### Campaign Structure

```json
{
  "id": "agent-os-launch-q2",
  "name": "Agent OS Launch Campaign",
  "theme": "Life Agent OS public release",
  "start_date": "2026-04-14",
  "end_date": "2026-04-28",
  "status": "active",
  "content_pieces": [
    {
      "id": "intro-post",
      "type": "blog_post",
      "topic": "Why we built an Agent OS in Rust",
      "skill": "/blog-post",
      "status": "published",
      "published_at": "2026-04-14T10:00:00Z",
      "platforms": ["blog", "x_thread", "linkedin"],
      "assets": {
        "blog": "content/writing/why-agent-os-rust.mdx",
        "x_thread": "7 tweets + 3 images",
        "linkedin": "long-form post"
      }
    },
    {
      "id": "demo-video",
      "type": "brainrot_video",
      "topic": "Agent OS in 30 seconds",
      "skill": "/brainrot-for-good",
      "status": "drafted",
      "scheduled_for": "2026-04-16T15:00:00Z",
      "platforms": ["tiktok", "reels", "x_video"]
    },
    {
      "id": "deep-dive",
      "type": "blog_post",
      "topic": "Architecture deep dive: event sourcing in Lago",
      "skill": "/blog-post",
      "status": "planned",
      "scheduled_for": "2026-04-21T10:00:00Z",
      "platforms": ["blog", "x_thread"]
    }
  ],
  "identity": {
    "brand": "broomva",
    "style": "cinematic-glass",
    "character": "founder"
  },
  "metrics_tracking": true
}
```

### Campaign Lifecycle

```
PLAN → DRAFT → REVIEW → PUBLISH → MEASURE → CLOSE

PLAN:    Define theme, content pieces, platform targets, schedule
DRAFT:   Generate all content using compounded skills
REVIEW:  Quality check each piece (human review or /creative-review)
PUBLISH: Deploy per the content calendar schedule
MEASURE: Track performance for 7-14 days post-publish
CLOSE:   Aggregate results, extract learnings, update identity
```

### Campaign Storage

```
~/.content-engine/campaigns/
├── agent-os-launch-q2/
│   ├── campaign.json           # Campaign definition
│   ├── calendar.json           # Publishing schedule
│   ├── metrics/
│   │   ├── intro-post.json     # Per-piece metrics
│   │   └── demo-video.json
│   ├── assets/                 # Generated assets (symlinks to output/)
│   └── report.json             # Post-campaign summary
```

## Content Calendar

The content calendar manages publishing cadence across platforms. It accounts for optimal posting times, platform-specific frequency limits, and campaign pacing.

See [references/content-calendar.md](references/content-calendar.md) for scheduling details.

### Weekly Cadence (Default)

| Day | Platform | Content Type | Optimal Time (ET) |
|-----|----------|-------------|-------------------|
| Mon | Blog | Long-form post | 10:00 AM |
| Tue | X | Thread (from Monday's post) | 8:00 AM |
| Wed | LinkedIn | Professional adaptation | 9:00 AM |
| Thu | TikTok/Reels | Brainrot cut of the week's theme | 12:00 PM |
| Fri | X | Original insight or engagement | 11:00 AM |
| Sat | Moltbook | Cross-post or original | 10:00 AM |
| Sun | -- | Planning + measurement day | -- |

The calendar adapts based on performance data: if Tuesday X threads consistently outperform Friday posts, the calendar shifts allocation accordingly.

## Performance Tracking

Every published asset is tracked across all platforms. Metrics are pulled periodically (daily for the first week, weekly after) and stored in a structured format.

See [references/performance-tracking.md](references/performance-tracking.md) for metrics format and aggregation.

### What Gets Tracked

| Metric | Platforms | Pull Method |
|--------|-----------|-------------|
| Views / Impressions | All | Platform API or manual |
| Likes / Reactions | X, LinkedIn, Instagram, Moltbook | Platform API |
| Shares / Retweets / Reposts | X, LinkedIn | Platform API |
| Saves / Bookmarks | X, Instagram | Platform API |
| Comments / Replies | All | Platform API |
| Click-through rate | Blog (from social) | Analytics |
| Watch time / Retention | TikTok, Reels, YouTube | Platform API |
| Follower delta | All | Platform API |

### Aggregation Dimensions

Metrics are aggregated across multiple dimensions to find what works:

- **By style**: Which visual style (cinematic, brainrot, editorial) gets most engagement?
- **By tool**: Which generation tool (Higgsfield, Veo, Nano Banana) produces best-performing assets?
- **By topic**: Which content themes resonate most?
- **By platform**: Where does each content type perform best?
- **By time**: What posting time and day drive most engagement?
- **By format**: Blog posts vs threads vs short video vs carousel?

## Feedback Synthesis

The feedback loop closes the cycle by turning performance data into identity refinements.

See [references/feedback-synthesis.md](references/feedback-synthesis.md) for the full feedback protocol.

### The Refinement Cycle

```
COLLECT
  └─ Pull metrics for all assets published in the last 7 days

ANALYZE
  └─ Score each asset on composite engagement (views * 0.1 + likes * 1 + shares * 3 + saves * 2 + comments * 2)
  └─ Rank by style, tool, topic, platform, format

PROMOTE
  └─ Top 20% performing styles → increase weight in compiled identity
  └─ Top performing prompts → save to prompt library as proven templates
  └─ High-engagement topics → add to content calendar pipeline

FLAG
  └─ Bottom 20% → mark as anti-patterns in identity
  └─ Styles with <50% average engagement → demote or remove from rotation
  └─ Topics with consistently low engagement → reduce frequency

UPDATE
  └─ Write refined identity to knowledge/compiled/
  └─ Update content calendar weights
  └─ Log changes to ~/.content-engine/feedback-log.jsonl
```

### Visual Knowledge Evolution

The compiled identity evolves over time as the feedback loop runs:

```
Week 1: Initial identity (brand guidelines + artistic vision)
  ↓ publish + measure
Week 2: Learned that cinematic-glass style gets 2x engagement on X vs editorial
  ↓ promote cinematic-glass weight
Week 3: Learned that Higgsfield avatars get 3x saves vs static images
  ↓ increase avatar generation in campaigns
Week 4: Learned that 9:16 format outperforms 16:9 on all social except LinkedIn
  ↓ default to 9:16 for social, 16:9 for blog only
  ...
Week N: Identity is now a distilled, performance-proven visual language
```

## Sub-Commands

| Command | Trigger | What It Does |
|---------|---------|-------------|
| `/loop plan` | "plan a campaign", "content calendar" | Create or update a campaign with content pieces and schedule |
| `/loop create` | "create campaign content", "generate batch" | Run compounded skill pipeline for all planned pieces |
| `/loop distribute` | "publish campaign", "distribute content" | Deploy content per calendar schedule |
| `/loop measure` | "track performance", "check metrics" | Pull and aggregate metrics for active campaigns |
| `/loop refine` | "refine identity", "what worked" | Run feedback synthesis and update compiled identity |
| `/loop status` | "campaign status", "loop status" | Show active campaigns, scheduled posts, recent metrics |

## Integration with Existing Primitives

| Bstack Primitive | How the Loop Uses It |
|-----------------|---------------------|
| P1 (Conversation Bridge) | Campaign decisions logged to conversation history for context |
| P5 (Linear Tickets) | Each campaign is a Linear epic; content pieces are issues |
| P6 (PR Pipeline) | Blog posts deploy via PR merge |
| P8 (Knowledge Bookkeeping) | Performance learnings scored and promoted to entity pages |

## Quick Start

```
1. "content loop: plan a campaign for Agent OS launch, 2 weeks, blog + video + social"
   → Creates campaign.json with content pieces and calendar

2. "content loop: create the intro post"
   → Runs /blog-post for the first content piece, generates all assets

3. "content loop: distribute intro post"
   → Publishes to blog (PR), X (thread), LinkedIn (post)

4. "content loop: measure intro post after 3 days"
   → Pulls metrics from all platforms, stores in metrics.json

5. "content loop: refine identity based on this campaign"
   → Analyzes all metrics, updates compiled identity, logs changes
```

## Reference Files

- [references/content-calendar.md](references/content-calendar.md) — Scheduling cadence, platform timing, campaign pacing
- [references/performance-tracking.md](references/performance-tracking.md) — Per-asset metrics, storage format, aggregation dimensions
- [references/feedback-synthesis.md](references/feedback-synthesis.md) — Performance-to-identity feedback loop, promotion/demotion rules
