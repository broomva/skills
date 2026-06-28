# Media Generation Prompts

## Hero Image

**Concept**: {What the image represents — tied to post's core metaphor}
**Prompt**: A sleek {style} technical illustration for a blog post about {topic}. {Visual concept}. Dark background, {accent color} highlights, clean composition. Professional, modern, minimal text. 1200×675 pixels.
**Dimensions**: 1200×675 (blog header, OG card)
**Model**: gemini-3.1-flash-image (Nano Banana)
**Usage**: Blog header, X thread image 1, LinkedIn post image, OG social card

## Supporting Image 1 — {Section Name}

**Concept**: {Tied to specific content in section}
**Prompt**: {Full AI generation prompt}
**Dimensions**: 1200×auto
**Usage**: Blog inline after {section}

## Supporting Image 2 — {Section Name}

**Concept**: {Tied to specific content in section}
**Prompt**: {Full AI generation prompt}
**Dimensions**: 1200×auto
**Usage**: Blog inline, X thread image 2

## Instagram Carousel

**Overall concept**: {Carousel narrative arc}
**Tool**: /pencil MCP or manual design
**Dimensions**: 1080×1350 per slide
**Slide count**: {N}
**Style**: {Design direction — colors, typography, layout}

## Social Card Variants

### X Card
**Dimensions**: 1200×675
**Source**: Crop from hero or generate variant

### LinkedIn Card
**Dimensions**: 1200×628
**Source**: Crop from hero or generate variant

### Instagram Cover
**Dimensions**: 1080×1350
**Source**: Carousel slide 1

## Generation Commands

```bash
# Hero image via Nano Banana
# (requires GEMINI_API_KEY)
# Use the script in /content-creation or inline:

node -e "
const { GoogleGenAI } = require('@google/genai');
const fs = require('fs');
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
(async () => {
  const r = await ai.models.generateContent({
    model: 'gemini-3.1-flash-image',
    contents: '[PROMPT]',
    config: { responseModalities: ['TEXT', 'IMAGE'] },
  });
  for (const p of r.candidates[0].content.parts) {
    if (p.inlineData) {
      fs.writeFileSync('hero.png', Buffer.from(p.inlineData.data, 'base64'));
    }
  }
})();
"

# Optimize images
magick hero.png -resize 1200x -quality 85 media/png/hero-social-card-opt.png

# Crop for platforms
magick hero.png -resize 1200x675! media/thumbnails/x-card.png
magick hero.png -resize 1200x628! media/thumbnails/linkedin-card.png
```
