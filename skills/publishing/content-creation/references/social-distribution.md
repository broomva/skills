# Social Distribution

## Content Atomization

A single blog post becomes:
- X thread (5-8 tweets)
- Instagram carousel (8-12 slides)
- LinkedIn text post (hook + takeaways + CTA)
- Short video clip (15-30s Remotion render)
- Quote graphic (1-2 striking stats)

## X/Twitter Thread

### Structure (5-8 tweets, 7 is sweet spot)

```
1/N — Hook (determines everything — spend 50% of effort here)
2/N — Context: set the scene (1-2 sentences)
3-6/N — Key insights: one per tweet from blog sections
        Insert image every 2-3 tweets (increases completion by 45%)
7/N — Strongest evidence or most surprising finding
8/N — CTA: link to full post, follow, or question
```

### Hook Formulas

- `"[Number] [things] in [timeframe]. Here's what happened:"` — scale proof
- `"Most [role]s think [common belief]. The data says otherwise:"` — contrarian
- `"We replaced [old thing] with [new thing]. The results:"` — transformation
- `"I spent X hours doing Y. Here's what I learned:"` — earned insight
- `"[Surprising stat]. Here's why that matters:"` — data hook

### Formatting Rules

- Number tweets explicitly (1/7, 2/7...)
- Generous line breaks (1-2 between ideas)
- One idea per tweet, never walls of text
- 2-3 quality threads per week > daily mediocre ones

## Instagram Carousel

### Specs
- Aspect ratio: **4:5 (1080x1350px)** for maximum feed presence
- Slide count: **8-12 for educational/B2B**, up to 20 for deep guides
- Video slides: max 60s each, 4GB total
- Engagement: 10% avg (beats single-image 7% and Reels 6%)

### Slide Structure

```
1  — Cover: "Is this for me?" + "What will I get?" in ≤10 words
2  — The problem (bold key phrase, 1-2 sentences)
3-9 — One insight per slide, flashcard style (not paragraphs)
10 — Key metric or stat (large number, bold)
11 — Summary takeaway
12 — CTA: save, share, link to full post
```

### Design with Pencil

Use `/pencil` MCP to design carousel slides:
1. `open_document("new")` — create new .pen file
2. `get_guidelines(topic="slides")` — load slide design rules
3. `get_style_guide(tags=[...])` — pick visual style
4. `batch_design(operations=[...])` — create slide frames at 1080x1350
5. `get_screenshot(nodeId)` — export each slide as PNG

## LinkedIn Post

### Format
```
[Hook — first 210 chars determine "See More" clicks]

[2-3 short paragraphs with key insights]

[Bullet list of 3-5 takeaways]

[CTA + link]

#relevantHashtags (3-5 max)
```

### Document Carousel (alternative)
Upload PDF/PPTX for swipeable carousels (6.10% avg engagement).
- 5-15 slides optimal
- One idea per slide, minimal text
- Consistent branding
- End with CTA slide

## Video Clips

### From Remotion Render
The Phase 4 video (15-30s) works directly for:
- X video tweets (max 2:20, aim for 15-30s)
- LinkedIn video posts
- Instagram Reels (9:16 vertical for max reach, or 1:1 square)

### Repurposing
```bash
# Square crop for Instagram/LinkedIn
ffmpeg -i video.mp4 -vf "crop=1080:1080" -c:a copy square.mp4

# Vertical crop for Reels/TikTok
ffmpeg -i video.mp4 -vf "crop=608:1080" -c:a copy vertical.mp4
```

## Distribution Checklist

- [ ] X thread posted (5-8 tweets with images)
- [ ] Instagram carousel designed and posted
- [ ] LinkedIn post with hook + link
- [ ] Video clip attached to social posts
- [ ] Blog post URL shared in relevant communities
- [ ] Cross-link between platforms (thread links to blog, blog embeds video)
