# Content Calendar — Scheduling and Cadence

How to plan generation runs, pace campaigns across platforms, and integrate with the existing `/blog-post` publish pipeline.

## Calendar Structure

The content calendar is a JSON file that maps content pieces to platform-specific publishing slots:

```json
{
  "campaign_id": "agent-os-launch-q2",
  "timezone": "America/New_York",
  "cadence": "weekly",
  "slots": [
    {
      "day": "monday",
      "time": "10:00",
      "platform": "blog",
      "content_type": "long_form",
      "notes": "Anchor piece for the week — everything else derives from this"
    },
    {
      "day": "tuesday",
      "time": "08:00",
      "platform": "x",
      "content_type": "thread",
      "derives_from": "monday_blog",
      "notes": "Atomize Monday's blog into 5-8 tweet thread"
    },
    {
      "day": "wednesday",
      "time": "09:00",
      "platform": "linkedin",
      "content_type": "professional_post",
      "derives_from": "monday_blog",
      "notes": "Professional angle of same topic, longer paragraphs"
    },
    {
      "day": "thursday",
      "time": "12:00",
      "platform": "tiktok",
      "content_type": "short_video",
      "derives_from": "monday_blog",
      "notes": "30s brainrot-for-good cut of the week's topic"
    },
    {
      "day": "friday",
      "time": "11:00",
      "platform": "x",
      "content_type": "original_insight",
      "notes": "Standalone observation or engagement bait, not derived from blog"
    },
    {
      "day": "saturday",
      "time": "10:00",
      "platform": "moltbook",
      "content_type": "cross_post",
      "derives_from": "monday_blog",
      "notes": "Adapted for Moltbook audience — more technical depth"
    }
  ],
  "scheduled_items": []
}
```

## Planning Generation Runs

### The Monday Anchor Pattern

One substantive piece per week anchors all derivative content. This simplifies planning and ensures consistency:

```
Monday: Write and publish the blog post (/blog-post)
  → This produces: MDX article, audio narration, hero image, social copy

Tuesday-Saturday: Derive platform-specific content from Monday's anchor
  → Thread: atomize key insights into tweet-sized pieces
  → LinkedIn: reframe for professional audience
  → Short video: /brainrot-for-good cut
  → Cross-post: adapt for Moltbook
```

### Generation Run Timing

| Phase | When to Run | Duration | What It Produces |
|-------|-------------|----------|-----------------|
| **Planning** | Sunday evening | 30 min | Topic selection, outline, campaign.json update |
| **Blog creation** | Monday morning | 2-4 hours | Full blog post + all assets |
| **Derivative generation** | Monday afternoon | 1-2 hours | Social copy, video script, carousel |
| **Asset generation** | Monday afternoon | 30-60 min | AI images, avatar videos (via /autopilot) |
| **Scheduling** | Monday evening | 15 min | Queue posts in calendar with timestamps |
| **Publishing** | Tue-Sat per schedule | 5 min each | Deploy to each platform |

### Batch Generation for Campaigns

For multi-week campaigns, batch-generate all content at once and schedule distribution:

```
Campaign: 2-week launch (10 content pieces)

Week 1:
  Mon: blog-post "Why Agent OS"          → publish immediately
  Tue: x-thread (derived)                → schedule for 8 AM
  Wed: linkedin-post (derived)           → schedule for 9 AM
  Thu: brainrot-video "Agent OS in 30s"  → schedule for 12 PM
  Fri: x-original "One thing I learned"  → schedule for 11 AM

Week 2:
  Mon: blog-post "Architecture Deep Dive" → publish immediately
  Tue: x-thread (derived)                 → schedule for 8 AM
  Wed: linkedin-post (derived)            → schedule for 9 AM
  Thu: brainrot-video "Lago in 30s"       → schedule for 12 PM
  Fri: x-original "Event sourcing..."     → schedule for 11 AM
```

All 10 pieces can be generated in a single day, then scheduled for automated publishing.

## Campaign Pacing

### Pacing Strategies

| Strategy | Cadence | Best For | Risk |
|----------|---------|----------|------|
| **Sprint** | Daily posts, 1-2 week burst | Product launches, time-sensitive events | Audience fatigue |
| **Steady** | 3-4 posts/week, ongoing | Brand building, thought leadership | Slow growth |
| **Pulse** | 1 big piece + 2-3 derivatives/week | Technical content, deep dives | Gaps between pulses |
| **Campaign** | Themed burst (2 weeks) + rest (1 week) | Seasonal content, multi-topic arcs | Momentum loss during rest |

### Platform-Specific Frequency Limits

Posting too often on any platform triggers algorithmic suppression or audience unfollows. Respect these ceilings:

| Platform | Max Posts/Day | Optimal Posts/Day | Min Interval |
|----------|-------------|-------------------|-------------|
| X | 5 (tweets), 1 (thread) | 2-3 tweets, 1 thread | 2 hours between tweets |
| LinkedIn | 2 | 1 | 24 hours |
| Instagram | 3 (feed), 5 (stories) | 1 feed, 2 stories | 6 hours between feed posts |
| TikTok | 3 | 1-2 | 4 hours |
| Moltbook | 3 | 1 | 4 hours |
| Blog | No limit (but SEO) | 1-2/week | 3 days |

### Spacing Rules

```
Between blog posts:       >= 3 days (SEO indexing time)
Between X threads:        >= 24 hours (thread visibility window)
Between LinkedIn posts:   >= 24 hours (feed algorithm cycle)
Between short videos:     >= 4 hours (TikTok/Reels discovery window)
Same topic, same platform: >= 7 days (avoid topic fatigue)
```

## Platform-Specific Posting Schedules

### Optimal Posting Times by Platform

Based on general engagement research. The feedback loop (see feedback-synthesis.md) refines these over time with actual performance data.

| Platform | Best Days | Best Times (ET) | Audience Context |
|----------|-----------|----------------|-----------------|
| **X** | Tue, Wed, Thu | 8-10 AM, 12-1 PM | Morning commute, lunch break |
| **LinkedIn** | Tue, Wed, Thu | 7-9 AM, 12 PM | Pre-work, lunch |
| **Instagram** | Mon, Wed, Fri | 11 AM-1 PM, 7-9 PM | Lunch, evening browse |
| **TikTok** | Tue, Thu, Sat | 10 AM, 2 PM, 7 PM | Discovery-driven, less time-sensitive |
| **Blog** | Mon, Tue | 10 AM | Start-of-week reading |
| **Moltbook** | Any | 9 AM, 4 PM | Community-dependent |

### Timezone Handling

The calendar stores all times in the campaign's declared timezone. When publishing, convert to UTC for API calls:

```
Calendar says: "Tuesday 8:00 AM ET"
API receives: "2026-04-15T12:00:00Z" (ET is UTC-4 in April)
```

For global audiences, consider staggering: publish the blog early AM ET, then post the X thread later for West Coast / European overlap (11 AM ET = 5 PM CET).

## Integration with /blog-post publish.sh

The existing `/blog-post` skill has a deployment pipeline that creates a PR, merges, and deploys via Vercel. The content calendar integrates with this flow:

### Immediate Publishing (Default for Blog)

```bash
# /blog-post deploy phase (existing)
git checkout -b content/{slug}
git add apps/chat/content/writing/{slug}.mdx apps/chat/public/images/writing/{slug}/
git commit -m "content: add {title}"
git push -u origin content/{slug}
gh pr create --title "content: {short title}" --body "..."

# Auto-merge if CI passes (content calendar marks as published)
gh pr merge --auto --squash
```

### Scheduled Publishing (For Derivatives)

Social content is queued for future posting. The calendar tracks scheduled items:

```json
{
  "scheduled_items": [
    {
      "content_piece_id": "intro-post-x-thread",
      "platform": "x",
      "scheduled_for": "2026-04-15T12:00:00Z",
      "status": "queued",
      "content": {
        "type": "thread",
        "tweets": ["1/7 ...", "2/7 ...", "..."],
        "media": ["hero-image.png"]
      },
      "published_at": null,
      "post_ids": []
    }
  ]
}
```

### Publishing Methods by Platform

| Platform | Method | Tool |
|----------|--------|------|
| Blog | PR merge + Vercel auto-deploy | `gh` CLI |
| X | Direct post | `xurl` CLI or X MCP |
| LinkedIn | API post | LinkedIn MCP |
| Instagram | API post | `ig-mcp` or Meta Graph API |
| TikTok | Manual upload (no reliable API) | Save video + caption for manual posting |
| Moltbook | Via `/social-intelligence` | agent-browser |

### Post-Publish Tracking

After each item is published, the calendar updates with the live post identifiers:

```json
{
  "content_piece_id": "intro-post-x-thread",
  "status": "published",
  "published_at": "2026-04-15T12:03:22Z",
  "post_ids": {
    "x": ["1901234567890123456", "1901234567890123457", "..."]
  }
}
```

These IDs are used by the performance tracking system to pull metrics.

## Calendar Adaptation

The content calendar is not static. It adapts based on two inputs:

### 1. Performance Data

If the feedback loop identifies that Thursday TikTok posts consistently outperform Tuesday X threads:

```
Before:  Tue=X thread (weight 1.0), Thu=TikTok (weight 1.0)
After:   Tue=X thread (weight 0.7), Thu=TikTok (weight 1.3)

Adaptation: Increase production effort on Thursday TikTok content,
            simplify Tuesday X thread (use quote-tweet instead of full thread)
```

### 2. Campaign Context

During a product launch, the calendar shifts to sprint mode:

```
Normal: 3-4 posts/week across platforms
Launch: Daily posts for 5 days, then back to normal
  Day 1: Teaser (X + Instagram story)
  Day 2: Blog post + X thread
  Day 3: Demo video (TikTok + Reels)
  Day 4: Deep dive (LinkedIn + Blog)
  Day 5: Community engagement (Moltbook + X Q&A)
```

## Calendar Storage

```
~/.content-engine/campaigns/{campaign-id}/calendar.json

# Or for the default ongoing calendar (not tied to a campaign):
~/.content-engine/calendar.json
```

The calendar file is the source of truth for what gets published when. The loop reads it before each publishing action and updates it after.
