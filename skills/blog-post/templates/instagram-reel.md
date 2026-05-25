# Instagram Reel

## Script ({N} seconds, 9:16 vertical, 1080×1920px)

### [0-3s] — HOOK
**Visual**: {Pattern interrupt — surprising visual, text overlay, or action}
**Audio/VO**: "{Opening line — 'Here's something nobody tells you about...'}"
**Captions**: {On-screen text for muted viewing}

### [3-8s] — PROBLEM
**Visual**: {Quick setup of the tension — relatable scenario}
**Audio/VO**: "{Problem statement}"
**Captions**: {Key phrase on screen}

### [8-25s] — INSIGHT
**Visual**: {Core value — screen recording, diagram, demo, talking head}
**Audio/VO**: "{Main teaching content}"
**Captions**: {Key points appear as text overlays}
**B-roll**: {AI clip concept or screen recording plan}

### [25-40s] — EVIDENCE
**Visual**: {Proof — metric, before/after, demo result}
**Audio/VO**: "{Data or demonstration narrative}"
**Captions**: {Stat or result on screen in large text}

### [40-55s] — TAKEAWAY
**Visual**: {Summary frame or talking head}
**Audio/VO**: "{One clear lesson}"
**Captions**: {Takeaway text}

### [55-60s] — CTA
**Visual**: {Profile card or subscribe prompt}
**Audio/VO**: "Follow for more" / "Link in bio"
**Captions**: {CTA text}

## Production Notes

- **Total duration**: {N}s
- **Aspect ratio**: 9:16 (1080×1920)
- **Captions**: Required (80% watch muted)
- **Audio**: {Original VO / AI narration / trending audio}
- **Production tool**: {Remotion / Veo 3.1 / screen recording + ffmpeg}
- **Transitions**: {Cut / spring animation / zoom}

## Vertical Crop Command (if converting from 16:9)

```bash
ffmpeg -i horizontal.mp4 -vf "crop=608:1080" -c:a copy vertical.mp4
```
