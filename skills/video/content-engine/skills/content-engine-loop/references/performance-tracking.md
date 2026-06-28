# Performance Tracking — Per-Asset Metrics

What to track, how to store it, and how to aggregate performance data across content pieces, platforms, and campaigns.

## What to Track

### Core Metrics

Every published asset is tracked across these universal engagement metrics:

| Metric | Description | Platforms | Weight in Composite |
|--------|-------------|-----------|-------------------|
| **Views / Impressions** | How many times the content was displayed | All | 0.1 |
| **Likes / Reactions** | Positive engagement signal | X, LinkedIn, Instagram, Moltbook, TikTok | 1.0 |
| **Shares / Retweets / Reposts** | Amplification signal (strongest quality indicator) | X, LinkedIn, TikTok | 3.0 |
| **Saves / Bookmarks** | High-intent "I want to return to this" signal | X, Instagram, TikTok | 2.0 |
| **Comments / Replies** | Conversation trigger signal | All | 2.0 |
| **Click-throughs** | Traffic driven to blog or product | X, LinkedIn, Instagram (link in bio) | 2.5 |
| **Follower delta** | Net new followers attributed to this content | All | 5.0 |

### Platform-Specific Metrics

| Platform | Extra Metrics | How to Pull |
|----------|--------------|-------------|
| **X** | Quote tweets, profile visits, detail expands | X Analytics API or manual export |
| **LinkedIn** | Unique impressions, company page follows | LinkedIn Analytics API |
| **Instagram** | Reach, profile visits, website clicks, story exits | Instagram Insights API |
| **TikTok** | Average watch time, completion rate, for-you % | TikTok Analytics |
| **YouTube** | Watch time, CTR, audience retention curve | YouTube Studio API |
| **Blog** | Page views, time on page, scroll depth, bounce rate | Vercel Analytics / Plausible |
| **Moltbook** | Karma earned, thread engagement | Manual or API |

### Content-Level Metrics

Beyond platform metrics, track content-production metadata:

| Metric | Purpose |
|--------|---------|
| **Generation tool** | Which tool produced the asset (Higgsfield, Veo, Nano Banana, etc.) |
| **Visual style** | Which compiled identity style preset was used |
| **Topic category** | What the content is about (technical, lifestyle, product, opinion) |
| **Content format** | Blog, thread, short video, carousel, single image |
| **Production time** | How long the content took to produce (from brief to publish) |
| **Cost** | API credits, subscription pro-rata, human time |

## Storage Format

### Per-Asset Metrics File

Each published asset gets a `metrics.json` entry that is updated over time:

```json
{
  "asset_id": "intro-post",
  "campaign_id": "agent-os-launch-q2",
  "content_type": "blog_post",
  "topic": "Why we built an Agent OS in Rust",
  "identity": {
    "brand": "broomva",
    "style": "cinematic-glass",
    "character": "founder"
  },
  "production": {
    "tools_used": ["blog-post", "nano-banana", "kokoro-tts"],
    "generation_tool": "nano-banana",
    "production_time_hours": 3.5,
    "cost_usd": 0.12
  },
  "platforms": {
    "blog": {
      "url": "https://broomva.tech/writing/why-agent-os-rust",
      "published_at": "2026-04-14T14:00:00Z",
      "snapshots": [
        {
          "captured_at": "2026-04-15T14:00:00Z",
          "age_hours": 24,
          "views": 342,
          "time_on_page_seconds": 187,
          "scroll_depth_pct": 72,
          "bounce_rate": 0.34
        },
        {
          "captured_at": "2026-04-21T14:00:00Z",
          "age_hours": 168,
          "views": 1203,
          "time_on_page_seconds": 165,
          "scroll_depth_pct": 68,
          "bounce_rate": 0.38
        }
      ]
    },
    "x": {
      "post_ids": ["1901234567890123456"],
      "published_at": "2026-04-15T12:00:00Z",
      "snapshots": [
        {
          "captured_at": "2026-04-16T12:00:00Z",
          "age_hours": 24,
          "impressions": 4521,
          "likes": 87,
          "retweets": 12,
          "quotes": 3,
          "replies": 8,
          "bookmarks": 23,
          "profile_clicks": 45,
          "link_clicks": 156
        },
        {
          "captured_at": "2026-04-22T12:00:00Z",
          "age_hours": 168,
          "impressions": 12340,
          "likes": 234,
          "retweets": 41,
          "quotes": 9,
          "replies": 22,
          "bookmarks": 67,
          "profile_clicks": 112,
          "link_clicks": 389
        }
      ]
    },
    "linkedin": {
      "post_id": "urn:li:share:7054321098765432100",
      "published_at": "2026-04-16T13:00:00Z",
      "snapshots": [
        {
          "captured_at": "2026-04-17T13:00:00Z",
          "age_hours": 24,
          "impressions": 2100,
          "unique_impressions": 1830,
          "likes": 45,
          "comments": 6,
          "shares": 4,
          "clicks": 89
        }
      ]
    }
  },
  "composite_score": null,
  "computed_at": null
}
```

### Metric Snapshots

Metrics are captured at regular intervals to track decay and growth curves:

| Interval | When | Purpose |
|----------|------|---------|
| T+1h | 1 hour after publish | Early signal — is the hook working? |
| T+24h | 1 day after publish | First-day performance (primary evaluation point) |
| T+72h | 3 days after publish | Sustained engagement indicator |
| T+168h | 1 week after publish | Final evaluation for weekly campaigns |
| T+720h | 30 days after publish | Long-tail performance (for evergreen content) |

### Storage Location

```
~/.content-engine/metrics/
├── by-campaign/
│   ├── agent-os-launch-q2/
│   │   ├── intro-post.json
│   │   ├── demo-video.json
│   │   └── deep-dive.json
│   └── weekly-ongoing/
│       ├── 2026-w15-rust-patterns.json
│       └── 2026-w16-event-sourcing.json
├── aggregated/
│   ├── by-style.json
│   ├── by-tool.json
│   ├── by-platform.json
│   ├── by-topic.json
│   ├── by-format.json
│   └── by-time.json
└── history.jsonl          # Append-only log of all metric pulls
```

## Composite Engagement Score

The composite score normalizes across platforms and enables apples-to-apples comparison:

```
composite = (impressions * 0.1)
           + (likes * 1.0)
           + (shares * 3.0)
           + (saves * 2.0)
           + (comments * 2.0)
           + (clicks * 2.5)
           + (follower_delta * 5.0)
```

### Normalization

Raw scores vary wildly by platform (X impressions in thousands, LinkedIn in hundreds). Normalize per-platform to a 0-100 scale using the user's historical data:

```
normalized_score(metric, platform) = 
  (metric_value - user_min[platform][metric]) /
  (user_max[platform][metric] - user_min[platform][metric]) * 100
```

Until there is sufficient historical data (at least 10 posts per platform), use raw composite scores without normalization.

## Aggregation

### By Style

Which visual style drives the most engagement?

```json
{
  "aggregation": "by_style",
  "computed_at": "2026-04-28T10:00:00Z",
  "data": [
    {
      "style": "cinematic-glass",
      "asset_count": 8,
      "avg_composite": 342,
      "median_composite": 298,
      "best_asset": "intro-post",
      "best_platform": "x",
      "trend": "rising"
    },
    {
      "style": "editorial-clean",
      "asset_count": 5,
      "avg_composite": 189,
      "median_composite": 167,
      "best_asset": "architecture-deep-dive",
      "best_platform": "linkedin",
      "trend": "stable"
    },
    {
      "style": "brainrot-high-energy",
      "asset_count": 4,
      "avg_composite": 567,
      "median_composite": 512,
      "best_asset": "agent-os-30s",
      "best_platform": "tiktok",
      "trend": "rising"
    }
  ]
}
```

### By Tool

Which generation tool produces assets that perform best?

```json
{
  "aggregation": "by_tool",
  "data": [
    {
      "tool": "higgsfield",
      "asset_count": 6,
      "avg_composite": 423,
      "avg_saves": 34,
      "notes": "Avatar videos drive highest save rate — people bookmark to rewatch"
    },
    {
      "tool": "veo-3.1",
      "asset_count": 4,
      "avg_composite": 389,
      "avg_shares": 28,
      "notes": "Cinematic clips drive shares — people want to show others"
    },
    {
      "tool": "nano-banana",
      "asset_count": 12,
      "avg_composite": 198,
      "notes": "Good for hero images but not a standalone engagement driver"
    }
  ]
}
```

### By Scene Type

Which scene compositions perform best? Correlates with `/brainrot-for-good` scene types and `/content-creation` visual assets.

```json
{
  "aggregation": "by_scene_type",
  "data": [
    { "scene": "talking_head_avatar", "avg_composite": 445, "best_platform": "tiktok" },
    { "scene": "terminal_demo", "avg_composite": 312, "best_platform": "x" },
    { "scene": "data_visualization", "avg_composite": 267, "best_platform": "linkedin" },
    { "scene": "before_after", "avg_composite": 534, "best_platform": "instagram" }
  ]
}
```

### By Time

What posting time and day produce best results?

```json
{
  "aggregation": "by_time",
  "data": [
    { "day": "tuesday", "time_bucket": "08-10", "avg_composite": 356, "sample_size": 7 },
    { "day": "thursday", "time_bucket": "12-14", "avg_composite": 478, "sample_size": 5 },
    { "day": "monday", "time_bucket": "10-12", "avg_composite": 289, "sample_size": 8 }
  ]
}
```

## Metric Pull Methods

### Automated (Preferred)

| Platform | Method | Setup |
|----------|--------|-------|
| X | X API v2 (`GET /tweets/:id`) | Bearer token via X Developer Portal |
| LinkedIn | LinkedIn Marketing API | OAuth 2.0 app via LinkedIn Developer |
| Instagram | Instagram Graph API | Meta Business Suite app |
| Blog | Vercel Analytics API or Plausible API | API token |
| TikTok | TikTok Content Posting API | Creator token |

### Semi-Automated

For platforms without easy API access, use browser automation via `/agent-browser`:

```bash
# Navigate to X Analytics for a specific tweet
agent-browser open "https://x.com/analytics" --session ~/.content-engine/sessions/x.json
agent-browser wait --selector "[data-testid='tweet-stats']"
agent-browser get text "[data-testid='tweet-stats']" > /tmp/x-metrics.txt
```

### Manual

For platforms that resist automation, the agent prompts the user:

```
"I need metrics for the TikTok video posted on Thursday.
 Please check TikTok analytics and tell me:
 - Views
 - Likes
 - Shares
 - Saves
 - Comments
 - Average watch time
 - Completion rate"
```

The agent records the manually provided numbers in the same `metrics.json` format.

## Metric Staleness

Metrics have a freshness window. Stale metrics trigger a refresh:

| Age of Content | Refresh Interval | Rationale |
|---------------|-----------------|-----------|
| 0-24 hours | Every 4 hours | Rapid growth phase |
| 1-3 days | Every 12 hours | Growth stabilizing |
| 3-7 days | Daily | Final evaluation window |
| 7-30 days | Weekly | Long-tail check |
| 30+ days | Monthly | Evergreen tracking only |

The tracking system stores `last_pulled_at` per platform per asset and triggers refresh when the interval has elapsed.

## Dashboard Summary

When `/loop measure` or `/loop status` is invoked, display a summary:

```
Campaign: Agent OS Launch Q2
Period: Apr 14 - Apr 28, 2026
Status: Active (Week 2 of 2)

Content Pieces: 5 published, 3 scheduled, 2 in draft

Top Performer:
  "Agent OS in 30 seconds" (TikTok)
  Composite: 892 | Views: 45.2K | Saves: 234 | Shares: 89

Worst Performer:
  "Architecture Deep Dive" (LinkedIn)
  Composite: 112 | Impressions: 890 | Likes: 12 | Comments: 1

Style Rankings:
  1. brainrot-high-energy  (avg 567)
  2. cinematic-glass        (avg 342)
  3. editorial-clean        (avg 189)

Recommendations:
  - Increase brainrot-for-good production (2x engagement vs editorial)
  - Shift LinkedIn effort to X (same content, 3x reach on X)
  - Thursday 12 PM TikTok slot is your best performing time
```
