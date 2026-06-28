# Media Generation Prompts — Agent OS Launch

## Hero Image

**Concept**: A layered operating system architecture rendered as a sleek dark technical diagram — 7 glowing layers stacked vertically, each representing a subsystem, with data flowing between them.
**Prompt**: A sleek dark-themed technical illustration for a blog post about building an Agent Operating System in Rust. Seven horizontal layers stacked vertically like geological strata, each glowing with a different accent color (blues, purples, cyans). Data streams flow between layers as luminous particles. Dark background (#0A0A0A), clean composition, no text. Professional, futuristic, minimal. 1200×675 pixels.
**Dimensions**: 1200×675
**Model**: gemini-3.1-flash-image
**Usage**: Blog header, X thread image 1, LinkedIn post image, OG social card

## Supporting Image 1 — Architecture Diagram

**Concept**: Clean technical diagram showing all 7 subsystems and their connections
**Prompt**: A technical architecture diagram on dark background showing 7 interconnected modules labeled: Arcan (runtime), Lago (persistence), Autonomic (homeostasis), Haima (finance), Praxis (tools), Vigil (observability), Spaces (networking). Modules connected by thin glowing lines. Minimal, professional, engineering blueprint style. Blue accent (#3B82F6). 1200×800 pixels.
**Dimensions**: 1200×auto
**Usage**: Blog inline after architecture section, X thread tweet 3

## Supporting Image 2 — Homeostasis Visualization

**Concept**: Three gauges representing operational, cognitive, and economic health — the autonomic regulation concept
**Prompt**: Three circular gauge meters on dark background, labeled Operational, Cognitive, Economic. Each gauge shows a needle in the green zone with subtle glow. Below each: small icons (gear, brain, dollar). Clean data-dashboard aesthetic, blue (#3B82F6) and green (#22C55E) accents. 1200×675 pixels.
**Dimensions**: 1200×auto
**Usage**: Blog inline after homeostasis section, X thread tweet 5

## Instagram Carousel

**Overall concept**: 9-slide educational carousel explaining the Agent OS architecture
**Tool**: /pencil MCP with Arcan Glass design tokens
**Dimensions**: 1080×1350 per slide
**Slide count**: 9
**Style**: Dark background (#0A0A0A), AI Blue (#3B82F6) accents, bold sans-serif typography, consistent branding

## Generation Commands

```bash
# Hero image
node -e "
const { GoogleGenAI } = require('@google/genai');
const fs = require('fs');
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
(async () => {
  const r = await ai.models.generateContent({
    model: 'gemini-3.1-flash-image',
    contents: 'A sleek dark-themed technical illustration for a blog post about building an Agent Operating System in Rust. Seven horizontal layers stacked vertically like geological strata, each glowing with a different accent color (blues, purples, cyans). Data streams flow between layers as luminous particles. Dark background, clean composition, no text. Professional, futuristic, minimal. 1200x675 pixels.',
    config: { responseModalities: ['TEXT', 'IMAGE'] },
  });
  for (const p of r.candidates[0].content.parts) {
    if (p.inlineData) {
      fs.writeFileSync('hero.png', Buffer.from(p.inlineData.data, 'base64'));
      console.log('Hero image saved');
    }
  }
})();
"

# Optimize and create platform variants
magick hero.png -resize 1200x675! media/png/hero-social-card-opt.png
magick hero.png -resize 1200x675! media/thumbnails/x-card.png
magick hero.png -resize 1200x628! media/thumbnails/linkedin-card.png
```
