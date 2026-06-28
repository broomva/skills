# Visual Content Strategy

## Image Placement

- **One image per ~300 words** as baseline
- Articles with visuals every 75-100 words get **2x more social shares**
- Place images immediately after the point they illustrate, never before
- Featured/hero image is essential — becomes the social media thumbnail

## Image Types and When to Use Each

| Type | When | Notes |
|------|------|-------|
| Screenshots | Process walkthroughs, UI demos, evidence | Crop to relevant area |
| Custom diagrams | Architecture, workflows, system design | Strongest brand differentiation |
| Data visualizations | Metrics, comparisons, trends | Bar for categories, line for time |
| Infographics | Summary of complex processes, statistics | Best for shareable/saveable |

## GIF vs Video Decision

- **Prefer MP4 over GIF** — many platforms convert GIFs to video anyway
- **Maximum one GIF per post** to avoid page speed degradation
- **Keep GIFs short** with minimal frames
- **Use video for:** tutorials, demos > 5 seconds, anything needing audio
- **Use GIFs only for:** micro-interactions, quick UI animations, flow previews

## Image Optimization Specs

| Spec | Value |
|------|-------|
| Width | 1200px (display), 1500-2500px source |
| Max file size | 500KB per image |
| Format | PNG for screenshots/sharp edges, JPG for photos |
| Alt text | Descriptive, keyword-natural, functions as caption |

## Optimization Commands

```bash
# Optimize single image
magick input.png -resize 1200x -quality 85 output-opt.png

# Create animated GIF from sequence (2s per frame)
magick f1.png f2.png f3.png -resize 1200x675! -set delay 200 -loop 0 flow.gif

# Convert video to GIF fallback
ffmpeg -y -i video.mp4 -vf "fps=12,scale=960:-1:flags=lanczos" -c:v gif output.gif

# Full-page screenshot via agent-browser
agent-browser open <url> && agent-browser wait --load networkidle && agent-browser screenshot --full output.png
```

## Data Visualization in Narrative

- Add 2-3 lines of introduction before every chart
- Use descriptive titles that tell the story ("Revenue doubled after Q3 launch" not "Revenue by Quarter")
- One chart = one point. Remove clutter.
- Bar/column for category comparison; line for trends over time
- Sequence charts: beginning (baseline), middle (change), end (outcome)

## Asset Naming Convention

```
{subject}-{descriptor}-opt.png
```

Examples: `nynj-landing-opt.png`, `agent-chat-response-opt.png`, `metrics-dashboard-overview.png`

## Pencil MCP for Design Assets

Use Pencil for custom graphics, social cards, diagrams, and carousel slides:

```
get_guidelines(topic="slides")      — slide design rules
get_style_guide(tags=[...])         — visual consistency
batch_design(operations=[...])      — create multi-element compositions
get_screenshot(nodeId)              — export designed frames
```

**Topics available:** `design-system`, `landing-page`, `slides`, `mobile-app`, `web-app`, `table`, `tailwind`, `code`
