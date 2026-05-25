---
name: "{campaign_name}"
type: campaign-plan
created: "{date}"
brand_ref: "compiled/brands/{brand_slug}.md"
character_refs:
  - "compiled/characters/{character_slug_1}.md"
  - "compiled/characters/{character_slug_2}.md"
scene_count: {scene_count}
status: "{status}"
format_targets:
  - reels
  - carousels
  - posts
---

# Campaign: {campaign_name}

> Multi-scene content campaign. Orchestrates brand identity, character
> consistency, and scene sequencing across multiple generated assets for
> a coordinated content release.

## Campaign Overview

**Objective:** {campaign_objective -- e.g., "Launch the Arcan agent runtime
with a cohesive visual narrative across social, blog, and video. Position
the founder as a builder who ships real infrastructure, not a thought
leader who talks about it."}

**Theme:** {campaign_theme -- e.g., "Building in the dark -- the private
intensity of creating something new before anyone else sees it."}

**Narrative arc:** {narrative_arc -- e.g., "From solitary builder (scenes 1-3)
to the first user discovering the tool (scene 4) to community forming
around it (scene 5). Individual to collective."}

**Duration:** {campaign_duration -- e.g., "7 days, April 7-13, 2026"}

**Success metrics:**
- {metric_1 -- e.g., "Blog post views > 500 in first 48 hours"}
- {metric_2 -- e.g., "Reel engagement rate > 5%"}
- {metric_3 -- e.g., "At least 3 quote-tweets or repost threads"}
- {metric_4 -- e.g., "GitHub stars +50 within launch week"}

---

## Brand & Characters

### Brand Reference

**Brand:** {brand_name} (see `{brand_ref}`)

**Brand-specific campaign notes:** {brand_campaign_notes -- e.g., "This campaign
leans into the 'dark glass' aesthetic. All scenes should feel like they
exist in the same physical universe -- consistent color grading, lighting
temperature, and surface materials across every asset."}

### Characters

| Character | Role in Campaign | Scenes | Notes |
|---|---|---|---|
| {character_1_name} | {character_1_role -- e.g., "Primary protagonist. Appears in all scenes."} | {character_1_scenes -- e.g., "1, 2, 3, 4, 5"} | {character_1_notes -- e.g., "Uses 'Default' and 'Tech Keynote' outfits."} |
| {character_2_name} | {character_2_role -- e.g., "Secondary. First user/community member."} | {character_2_scenes -- e.g., "4, 5"} | {character_2_notes -- e.g., "Introduced in scene 4 as a new presence."} |

---

## Scene Sequence

### Scene 1: {scene_1_name}

**Brief:** {scene_1_brief -- e.g., "Founder alone at workstation. Code on
screens. Coffee going cold. The deep work shot."}

**Format:** {scene_1_format -- e.g., "Still (blog hero, 16:9)"}
**Tool:** {scene_1_tool -- e.g., "nano-banana-pro"}
**Character:** {scene_1_character -- e.g., "Carlos (Default outfit)"}
**Mood:** {scene_1_mood -- e.g., "Focused solitude"}
**Placement:** {scene_1_placement -- e.g., "Blog hero image, X post image"}

**Scene brief file:** `{scene_1_brief_path -- e.g., "knowledge/raw/scene-briefs/arcan-launch/scene-01-deep-work.md"}`

---

### Scene 2: {scene_2_name}

**Brief:** {scene_2_brief -- e.g., "Close-up of hands on keyboard, screen
reflections on skin. Terminal showing compilation output."}

**Format:** {scene_2_format -- e.g., "Still (carousel frame 1, 1:1)"}
**Tool:** {scene_2_tool -- e.g., "nano-banana-pro"}
**Character:** {scene_2_character -- e.g., "Carlos (Default outfit, hands only)"}
**Mood:** {scene_2_mood -- e.g., "Craftsmanship, precision"}
**Placement:** {scene_2_placement -- e.g., "Carousel frame 1 of 5"}

**Scene brief file:** `{scene_2_brief_path}`

---

### Scene 3: {scene_3_name}

**Brief:** {scene_3_brief -- e.g., "Wide shot of the workspace from doorway.
Subject silhouetted against screen glow. Establishing the environment."}

**Format:** {scene_3_format -- e.g., "Video (Reel, 9:16, 4s)"}
**Tool:** {scene_3_tool -- e.g., "soul-cinema"}
**Character:** {scene_3_character -- e.g., "Carlos (Default outfit, silhouette)"}
**Mood:** {scene_3_mood -- e.g., "Mystery, atmosphere"}
**Placement:** {scene_3_placement -- e.g., "Reel opening clip, X video"}

**Scene brief file:** `{scene_3_brief_path}`

---

### Scene 4: {scene_4_name}

**Brief:** {scene_4_brief}
**Format:** {scene_4_format}
**Tool:** {scene_4_tool}
**Character:** {scene_4_character}
**Mood:** {scene_4_mood}
**Placement:** {scene_4_placement}

**Scene brief file:** `{scene_4_brief_path}`

---

### Scene 5: {scene_5_name}

**Brief:** {scene_5_brief}
**Format:** {scene_5_format}
**Tool:** {scene_5_tool}
**Character:** {scene_5_character}
**Mood:** {scene_5_mood}
**Placement:** {scene_5_placement}

**Scene brief file:** `{scene_5_brief_path}`

---

> Add more scenes as needed. Copy the scene block above and increment the
> scene number. Update `scene_count` in frontmatter.

---

## Format Targets

### Reels (9:16)

**Count:** {reel_count -- e.g., "2"}
**Duration:** {reel_duration -- e.g., "15-30 seconds each"}
**Structure:** {reel_structure -- e.g., "Scene 3 (atmosphere) as opening hook
→ Scene 1 (hero) as middle → Scene 5 (community) as resolution. Add
word-by-word captions via Remotion. Background audio: ambient synth."}

**Technical specs:**
- Resolution: 1080x1920
- FPS: 30
- Codec: H.265 (CRF 18)
- Audio: Gemini TTS narration + ambient music mix
- Captions: Top-center (Instagram safe zone, 12% from top)
- Export: `ffmpeg -movflags +faststart`

### Carousels (1:1)

**Count:** {carousel_count -- e.g., "1 carousel, 5 frames"}
**Frame sequence:** {carousel_sequence -- e.g., "
  Frame 1: Scene 2 (hands/keyboard close-up) -- hook
  Frame 2: Text overlay on brand background -- problem statement
  Frame 3: Scene 1 (hero at desk) -- the solution being built
  Frame 4: Architecture diagram or code screenshot -- credibility
  Frame 5: Scene 5 (community) + CTA -- resolution"}

**Technical specs:**
- Resolution: 1080x1080
- Format: PNG (each frame)
- Text: Brand typography, {primary_hex} on {bg_hex}
- Export: Individual PNGs named `{campaign_slug}-carousel-{nn}.png`

### Posts (16:9 or 1:1)

**Count:** {post_count -- e.g., "3"}
**Distribution:**
- {post_1_target -- e.g., "Blog hero (16:9) -- Scene 1"}
- {post_2_target -- e.g., "X post (16:9) -- Scene 1 with text overlay"}
- {post_3_target -- e.g., "LinkedIn post (1:1) -- Scene 4"}

**Technical specs:**
- Blog hero: 1920x1080, PNG
- Social cards: 1200x630 (OG), PNG
- X/LinkedIn: 1080x1080 or 1920x1080, PNG or JPEG (quality 95)

---

## Content Calendar

| Day | Date | Platform | Content | Scene | Format | Time |
|-----|------|----------|---------|-------|--------|------|
| {day_1} | {date_1} | {platform_1 -- e.g., "broomva.tech"} | {content_1 -- e.g., "Blog post: 'Building Arcan'"} | {scene_1_ref -- e.g., "Scene 1 (hero)"} | {format_1 -- e.g., "Post (16:9)"} | {time_1 -- e.g., "10:00 UTC"} |
| {day_1} | {date_1} | {platform_2 -- e.g., "X (@broomva_tech)"} | {content_2 -- e.g., "Launch thread (5 tweets)"} | {scene_2_ref -- e.g., "Scene 1 + Scene 2"} | {format_2 -- e.g., "Post (16:9) + Carousel"} | {time_2 -- e.g., "14:00 UTC"} |
| {day_2} | {date_2} | {platform_3 -- e.g., "Instagram"} | {content_3 -- e.g., "Reel: 'The Build'"} | {scene_3_ref -- e.g., "Scene 3 + Scene 1"} | {format_3 -- e.g., "Reel (9:16)"} | {time_3 -- e.g., "18:00 UTC"} |
| {day_3} | {date_3} | {platform_4 -- e.g., "LinkedIn"} | {content_4 -- e.g., "Long-form post + image"} | {scene_4_ref -- e.g., "Scene 4"} | {format_4 -- e.g., "Post (1:1)"} | {time_4 -- e.g., "12:00 UTC"} |
| {day_4} | {date_4} | {platform_5 -- e.g., "Moltbook"} | {content_5 -- e.g., "Cross-post (truncated)"} | {scene_5_ref -- e.g., "N/A"} | {format_5 -- e.g., "Text only"} | {time_5 -- e.g., "10:00 UTC"} |
| {day_5} | {date_5} | {platform_6 -- e.g., "X"} | {content_6 -- e.g., "Carousel: build process"} | {scene_6_ref -- e.g., "Scenes 2-5"} | {format_6 -- e.g., "Carousel (1:1)"} | {time_6 -- e.g., "14:00 UTC"} |
| {day_7} | {date_7} | {platform_7 -- e.g., "Instagram"} | {content_7 -- e.g., "Reel: community response"} | {scene_7_ref -- e.g., "Scene 5"} | {format_7 -- e.g., "Reel (9:16)"} | {time_7 -- e.g., "18:00 UTC"} |

---

## Distribution Plan

### Platform-Specific Adaptations

**broomva.tech (Blog):**
- Full long-form post with hero image (Scene 1)
- Audio narration via Gemini TTS (Kore voice)
- Inline images from campaign scenes
- Auto-deploy via Vercel on PR merge

**X (@broomva_tech):**
- Launch thread: {thread_structure -- e.g., "5 tweets. Tweet 1 = hook + hero image. Tweets 2-4 = key points. Tweet 5 = CTA + link."}
- Image uploads: `xurl --media-type image/png --category tweet_image`
- Schedule via `xurl` or manual post at peak engagement time

**Instagram (@broomva.tech):**
- Reels with word-by-word captions (Remotion composition)
- Carousel posts with swipe-through narrative
- Stories: behind-the-scenes of generation process (meta-content)
- Caption positioning: top 12% (Instagram safe zone)

**LinkedIn:**
- Professional framing of the same content
- Single image post with long-form text
- No video (LinkedIn video reach is lower)

**Moltbook (s/agents):**
- Cross-post blog content (truncated to 5500 chars)
- Strip MDX tags and frontmatter
- Append link back to broomva.tech

### Cross-Platform Consistency Rules

- {consistency_1 -- e.g., "Same color grade applied to all exported assets (use brand LUT)"}
- {consistency_2 -- e.g., "Character must be recognizable across all formats (face similarity > 0.72)"}
- {consistency_3 -- e.g., "Text overlays use the same typography and placement rules everywhere"}
- {consistency_4 -- e.g., "Post timing staggered by 4 hours minimum to avoid audience fatigue"}

---

## Production Checklist

### Pre-Production
- [ ] All compiled files (brand + characters) are fresh (lint passes)
- [ ] Scene briefs written for all {scene_count} scenes
- [ ] Content calendar reviewed and times locked
- [ ] Platform tokens valid (X, Instagram, LinkedIn -- check expiry)

### Production
- [ ] Scene 1 generated and approved
- [ ] Scene 2 generated and approved
- [ ] Scene 3 generated and approved
- [ ] Scene 4 generated and approved
- [ ] Scene 5 generated and approved
- [ ] Reels composed in Remotion (captions, audio, transitions)
- [ ] Carousels assembled (all frames consistent)
- [ ] Blog post drafted with inline images

### Post-Production
- [ ] All assets color-graded with brand LUT
- [ ] All assets exported at correct resolution/format
- [ ] Captions added to video assets (OpenCaptions pipeline, when available)
- [ ] Upscale pass completed (Real-ESRGAN for any sub-native assets)
- [ ] Final quality review (run acceptance criteria on each scene)

### Distribution
- [ ] Blog post published to broomva.tech
- [ ] X thread posted
- [ ] Instagram reel(s) published
- [ ] LinkedIn post published
- [ ] Moltbook cross-post queued
- [ ] Analytics tracking configured (UTM params, link shortener)

### Post-Launch
- [ ] 24-hour engagement check (respond to comments, track metrics)
- [ ] 48-hour metrics snapshot (compare against success metrics)
- [ ] Retrospective: what worked, what to change for next campaign
- [ ] Archive campaign assets to `knowledge/raw/campaigns/{campaign_slug}/`
