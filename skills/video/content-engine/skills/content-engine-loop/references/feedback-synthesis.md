# Feedback Synthesis — Closing the Loop

How performance data feeds back into compiled identity refinement, promoting high-performing styles, flagging anti-patterns, and driving the visual knowledge evolution cycle.

## The Feedback Loop

The content engine loop is only complete when performance data changes future behavior. Without this step, you are publishing blind. With it, every campaign makes the next one better.

```
PUBLISH → MEASURE → ANALYZE → DECIDE → UPDATE → PUBLISH (refined)
                                  │
                                  └─ This document covers everything
                                     from ANALYZE through UPDATE
```

### Feedback Cadence

| Trigger | When | What It Does |
|---------|------|-------------|
| **Weekly review** | Sunday | Analyze the past week's metrics, flag top/bottom performers |
| **Campaign close** | End of campaign | Full analysis, identity update, campaign report |
| **Anomaly detection** | Anytime | Something went viral or completely flopped — investigate immediately |
| **Quarterly synthesis** | Every 3 months | Deep pattern review across all campaigns, major identity revision |

## Analysis Protocol

### Step 1: Collect

Pull all metrics for the analysis window. Use the composite engagement score from `performance-tracking.md`:

```
composite = impressions * 0.1
          + likes * 1.0
          + shares * 3.0
          + saves * 2.0
          + comments * 2.0
          + clicks * 2.5
          + follower_delta * 5.0
```

### Step 2: Rank

Sort all assets by composite score and identify the distribution:

```
All assets in window, sorted by composite:

P90 (top 10%):   "Agent OS 30s" (TikTok, brainrot, 892)
P80 (top 20%):   "Standing desk avatar" (X, cinematic, 567)
                  ...
P50 (median):    "Lago architecture" (Blog, editorial, 289)
                  ...
P20 (bottom 20%): "Event sourcing intro" (LinkedIn, editorial, 112)
P10 (bottom 10%): "Setup tutorial" (X, editorial, 67)
```

### Step 3: Correlate

For each asset in the top 20% and bottom 20%, identify what distinguishes them across dimensions:

| Dimension | Top 20% Pattern | Bottom 20% Pattern |
|-----------|----------------|-------------------|
| **Style** | cinematic-glass, brainrot-high-energy | editorial-clean |
| **Tool** | Higgsfield (avatar), Veo 3.1 (cinematic B-roll) | Nano Banana (static image only) |
| **Format** | Short video, visual-heavy thread | Text-only, long-form without media |
| **Platform** | TikTok, X | LinkedIn (for this audience) |
| **Topic** | Product demos, "why we built X" | Pure technical architecture |
| **Time** | Thu 12 PM, Tue 8 AM | Mon 10 AM, Sat 10 AM |
| **Hook type** | Contrarian claim, surprising stat | Descriptive summary |

### Step 4: Hypothesize

Turn correlations into testable hypotheses:

```
H1: Avatar videos (Higgsfield) outperform static images by >2x on social
    Evidence: 6 avatar posts avg 423 composite vs 12 static posts avg 198
    Confidence: High (sufficient sample size, consistent pattern)

H2: Brainrot-for-good format drives highest saves (return intent)
    Evidence: 4 brainrot posts avg 67 saves vs 15 other posts avg 18 saves
    Confidence: Medium (small sample, but 3.7x difference)

H3: Thursday 12 PM is the optimal posting time
    Evidence: 5 Thursday posts avg 478 vs 7 Tuesday posts avg 356
    Confidence: Low (confounded by format — Thursdays are always video)
```

### Step 5: Decide

Each hypothesis leads to an identity or calendar action:

| Hypothesis | Confidence | Action |
|------------|-----------|--------|
| High confidence, positive | **Promote**: Increase weight in compiled identity |
| High confidence, negative | **Demote**: Decrease weight or remove from rotation |
| Medium confidence, positive | **Test**: Increase frequency to gather more data |
| Medium confidence, negative | **Monitor**: Keep current allocation, watch for confirmation |
| Low confidence | **No action**: Insufficient data, note for future analysis |

## Promoting High-Performing Styles

When a style, tool, or format consistently appears in the top 20%, promote it in the compiled identity.

### Promotion Rules

1. **Minimum sample size**: At least 5 assets using this style/tool before promoting
2. **Consistency**: Must appear in top 20% in at least 3 of last 5 uses
3. **Cross-platform**: Must perform well on at least 2 platforms (not a platform-specific fluke)
4. **Recency**: Recent performance (last 30 days) weighted 2x vs older data

### How Promotion Works

The compiled identity in `knowledge/compiled/` has weighted style presets. Promotion increases the weight:

**Before promotion:**
```json
{
  "styles": {
    "cinematic-glass": { "weight": 1.0, "status": "active" },
    "editorial-clean": { "weight": 1.0, "status": "active" },
    "brainrot-high-energy": { "weight": 1.0, "status": "active" }
  }
}
```

**After feedback synthesis (week 4):**
```json
{
  "styles": {
    "cinematic-glass": { "weight": 1.3, "status": "promoted", "promoted_at": "2026-04-28", "reason": "2x engagement vs average" },
    "editorial-clean": { "weight": 0.6, "status": "demoted", "demoted_at": "2026-04-28", "reason": "consistently bottom 20% on social" },
    "brainrot-high-energy": { "weight": 1.5, "status": "promoted", "promoted_at": "2026-04-28", "reason": "3.7x saves, highest retention" }
  }
}
```

### What Promotion Changes

| Aspect | Effect of Promotion |
|--------|-------------------|
| **Campaign planning** | Promoted styles get more slots in the content calendar |
| **Prompt assembly** | Promoted style prefixes appear more often in compiled prompts |
| **Asset generation** | Batch runs prioritize promoted styles when resources are limited |
| **Quality review** | Promoted styles set the quality benchmark for review |

### Prompt Template Promotion

When a specific prompt text (not just style) drives exceptional results, save it to the prompt library:

```json
{
  "id": "proven-avatar-hook",
  "source_asset": "agent-os-30s",
  "composite_score": 892,
  "prompt_text": "Confident engineer walks toward camera in modern office, natural lighting, slight smile, 4K cinematic...",
  "style": "cinematic-glass",
  "tool": "higgsfield",
  "notes": "This exact prompt structure drove 45K views on TikTok. Reuse for similar demo intros.",
  "promoted_at": "2026-04-28"
}
```

Saved to `~/.content-engine/proven-prompts/` and available to all future generation loops.

## Flagging Anti-Patterns

When a style, tool, or approach consistently appears in the bottom 20%, flag it as an anti-pattern.

### Anti-Pattern Detection Rules

1. **Consistent underperformance**: Bottom 20% in at least 3 of last 5 uses
2. **No confounding factors**: Poor performance is not explained by bad timing, platform issues, or topic mismatch
3. **Below baseline**: Composite score below 50% of the user's average

### Anti-Pattern Registry

```json
{
  "anti_patterns": [
    {
      "id": "text-only-linkedin",
      "type": "format",
      "description": "Text-only LinkedIn posts without images or video consistently underperform by 60%",
      "detected_at": "2026-04-28",
      "evidence": [
        { "asset": "event-sourcing-intro", "composite": 112, "avg": 289 },
        { "asset": "rust-patterns-summary", "composite": 98, "avg": 289 },
        { "asset": "concurrency-thoughts", "composite": 134, "avg": 289 }
      ],
      "recommendation": "Always include at least one image or carousel in LinkedIn posts",
      "status": "active"
    },
    {
      "id": "saturday-moltbook-crosspost",
      "type": "timing",
      "description": "Saturday Moltbook cross-posts get 40% less engagement than weekday originals",
      "detected_at": "2026-04-28",
      "evidence": [],
      "recommendation": "Move Moltbook posts to Tuesday or Wednesday. Post original content, not cross-posts.",
      "status": "active"
    }
  ]
}
```

### How Anti-Patterns Affect the Loop

1. **Calendar**: Anti-pattern combinations (e.g., text-only + LinkedIn) are flagged during planning. The agent warns: "This combination has been flagged as an anti-pattern. Add media or choose a different format."
2. **Generation**: If a batch prompt would produce an anti-pattern output, the agent suggests modifications.
3. **Review**: Anti-pattern checklist is added to quality review for flagged combinations.

## Visual Knowledge Evolution Cycle

The compiled identity is a living document that evolves through the feedback loop. Over time, it converges on what works for your specific audience.

### Evolution Stages

```
Stage 1: SEED (Week 0)
  Identity based on brand guidelines + artistic intuition
  No performance data yet
  All styles have equal weight (1.0)
  Calendar uses general best-practice timing

Stage 2: CALIBRATE (Weeks 1-4)
  First performance data arrives
  Obvious winners and losers emerge
  Initial promotions and demotions (high-confidence only)
  Calendar starts adapting posting times

Stage 3: REFINE (Weeks 5-12)
  Sufficient data for medium-confidence hypotheses
  Style weights diverge significantly (0.5 to 2.0 range)
  Proven prompts library grows
  Anti-pattern registry catches repeated mistakes
  Calendar reflects audience-specific timing

Stage 4: OPTIMIZE (Weeks 13+)
  Identity is performance-proven
  New styles are A/B tested against proven winners
  Diminishing returns — focus shifts to topic selection and audience expansion
  Calendar is fine-tuned per platform per day per format
```

### A/B Testing New Styles

Once the identity has a stable baseline (Stage 3+), test new styles against proven ones:

```
A/B Test Protocol:
  1. Take a proven prompt template (composite > P80)
  2. Generate two versions:
     A: Proven style (cinematic-glass, weight 1.3)
     B: New style (neon-editorial, weight 1.0)
  3. Publish both within 24 hours on the same platform
  4. Measure after 72 hours
  5. If B > A * 0.8 → add to rotation (it is competitive)
  6. If B > A * 1.2 → promote immediately (it outperforms proven)
  7. If B < A * 0.5 → reject (not worth further testing)
```

### Identity Version History

Every feedback-driven update creates a new version of the compiled identity:

```
~/.content-engine/identity-history/
├── v1-2026-04-07.json    # Initial seed identity
├── v2-2026-04-14.json    # After first week's feedback
├── v3-2026-04-21.json    # After second week
├── v4-2026-04-28.json    # Campaign close revision
└── changelog.jsonl       # Append-only log of all changes
```

The changelog records every promotion, demotion, and modification:

```jsonl
{"timestamp":"2026-04-14T10:00:00Z","action":"promote","target":"cinematic-glass","from_weight":1.0,"to_weight":1.2,"reason":"Top 20% in 4 of 5 uses","evidence":["intro-post","demo-video","hero-shot","product-demo"]}
{"timestamp":"2026-04-14T10:00:00Z","action":"demote","target":"editorial-clean","from_weight":1.0,"to_weight":0.8,"reason":"Bottom 20% in 3 of 4 social posts","evidence":["event-sourcing-intro","rust-patterns","concurrency-thoughts"]}
{"timestamp":"2026-04-21T10:00:00Z","action":"add_anti_pattern","id":"text-only-linkedin","description":"Text-only LinkedIn posts consistently underperform by 60%"}
{"timestamp":"2026-04-28T10:00:00Z","action":"promote","target":"brainrot-high-energy","from_weight":1.0,"to_weight":1.5,"reason":"3.7x saves vs average, highest TikTok retention"}
```

## Feedback Log

All feedback synthesis runs are logged to an append-only file for auditability:

```
~/.content-engine/feedback-log.jsonl
```

Each entry records:
- Timestamp of the synthesis run
- Analysis window (date range)
- Number of assets analyzed
- Promotions made
- Demotions made
- Anti-patterns detected
- Calendar changes
- Hypotheses generated (with confidence level)

This log feeds into the broader knowledge bookkeeping system (bstack P8) so that content performance insights can be promoted to entity pages in `research/entities/pattern/` when they cross the Nous gate threshold.

## Integration with Knowledge Bookkeeping

When a feedback synthesis produces a high-confidence insight (evidence from 5+ assets, consistent across 3+ campaigns), it qualifies for promotion to the knowledge graph:

```
Feedback insight:
  "Avatar videos with the 'walk toward camera' opening consistently drive
   3x saves vs static thumbnails across X and TikTok (n=12, p<0.05)"

Nous gate scoring:
  Novelty: 2/3 (not widely discussed, specific to our audience)
  Specificity: 3/3 (exact format, exact metric, exact platforms)
  Relevance: 2/3 (directly applicable to content strategy)
  Total: 7/9 → PROMOTE to Layer 3

Entity page created:
  research/entities/pattern/avatar-walk-toward-camera-hook.md
```

This ensures that hard-won content performance insights are not lost between campaigns but become permanent, searchable knowledge.
