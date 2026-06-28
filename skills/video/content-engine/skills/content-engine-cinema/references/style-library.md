# Design Style Library

25+ codified design styles with visual characteristics, use cases, and exact prompt fragments. Each style is a reusable aesthetic recipe -- apply it to any subject matter to produce visually coherent content.

Sourced from ohneis652's style taxonomy and production experience.

## How to Use This Library

1. **Choose a style** based on the content's audience and purpose
2. **Copy the prompt fragment** and append it to your subject/scene prompt
3. **Combine with a director vocabulary** from [cinematic-prompting.md](cinematic-prompting.md) for video
4. **Apply a matching LoRA** if available in the local pipeline (see [node-pipelines.md](node-pipelines.md))

### Prompt Assembly

```
[Your subject and scene description],
[Style prompt fragment from this library],
[Director vocabulary keywords if making video],
[Technical specs: resolution, aspect ratio]
```

---

## 1. Flat Illustration

**Visual characteristics:** Bold geometric shapes, minimal to no shadows, limited color palette (4-6 colors), thick outlines optional, clean vector aesthetic, no gradients or textures.

**When to use:** Explainer content, social media cards, infographics, app onboarding, brand illustrations, blog headers.

**Prompt fragment:**
```
flat illustration style, bold geometric shapes, minimal shadows, clean vector art, 
limited color palette, solid fills, no gradients, simple composition, 
2D design, graphic poster style
```

---

## 2. Psychedelic

**Visual characteristics:** Saturated swirling colors, organic flowing shapes, kaleidoscopic patterns, rainbow gradients, melting/distorted forms, op-art influence, fractal repetition.

**When to use:** Music events, festival branding, counter-culture content, creative/art-focused campaigns, attention-grabbing social media.

**Prompt fragment:**
```
psychedelic art style, swirling saturated colors, organic flowing patterns, 
kaleidoscopic symmetry, rainbow gradient, melting forms, op-art influence, 
vibrant neon colors, fractal repetition, trippy visual distortion
```

---

## 3. Minimalism

**Visual characteristics:** Extreme negative space (60%+ empty), single focal point, monochrome or 2-3 colors maximum, thin lines if any, geometric simplicity, intentional asymmetry.

**When to use:** Luxury brands, tech products, editorial layouts, architecture content, premium apps, investor-facing materials.

**Prompt fragment:**
```
minimalist design, extreme negative space, single focal point, monochrome palette, 
clean lines, geometric simplicity, intentional whitespace, refined composition, 
less is more, sophisticated restraint
```

---

## 4. Japanese (Japandi / Ukiyo-e inspired)

**Visual characteristics:** Wabi-sabi imperfection, natural materials (wood, paper, stone), muted earth tones with selective red/indigo accents, brushstroke textures, asymmetric balance, ma (negative space).

**When to use:** Wellness brands, tea/food content, mindfulness apps, interior design, craft/artisan products, nature-focused content.

**Prompt fragment:**
```
Japanese aesthetic, wabi-sabi, natural materials texture, muted earth tones, 
selective red accent, brushstroke texture, asymmetric balance, ma negative space, 
paper texture background, zen composition, subtle imperfection
```

---

## 5. Poster Collage

**Visual characteristics:** Layered cut-out elements, visible paper texture and torn edges, mixed typography sizes, overlapping images at angles, tape/pin marks, zine aesthetic, deliberate imperfection.

**When to use:** Event promotion, editorial features, music/culture content, indie brands, social justice campaigns, youth-targeted content.

**Prompt fragment:**
```
poster collage style, layered cut-out elements, torn paper edges, mixed typography, 
overlapping images at angles, visible tape marks, zine aesthetic, 
analog collage on textured paper, raw and authentic, mixed media
```

---

## 6. Indie Groovy

**Visual characteristics:** Hand-drawn wobbly lines, warm retro palette (mustard, burnt orange, olive, cream), rounded organic shapes, playful typography, slight misregistration like risograph printing.

**When to use:** Independent brands, coffee shops, record stores, sustainable products, community events, food/lifestyle blogs.

**Prompt fragment:**
```
indie groovy style, hand-drawn wobbly lines, warm retro color palette, 
mustard yellow and burnt orange and olive green, rounded organic shapes, 
playful hand-lettered typography, risograph texture, retro warmth, 
lo-fi charm, imperfect registration
```

---

## 7. Vintage 80s

**Visual characteristics:** Neon pink/cyan/purple on dark backgrounds, chrome reflections, grid perspective floors, VHS scan lines, synthwave sunset gradients, geometric wireframes, lens flare.

**When to use:** Retro campaigns, nostalgia marketing, music/entertainment, gaming content, neon-lit product shots, nightclub/party promotion.

**Prompt fragment:**
```
vintage 80s synthwave, neon pink and cyan glow on dark background, 
chrome reflections, perspective grid floor, VHS scan lines, 
synthwave sunset gradient, geometric wireframe, lens flare, 
retro futurism, outrun aesthetic, hot pink and electric blue neon
```

---

## 8. 90s Editorial

**Visual characteristics:** High contrast B&W with selective warm tones, editorial grid layouts, serif headlines with sans-serif body, film grain, contact sheet borders, matte paper texture.

**When to use:** Fashion content, editorial features, long-form storytelling, biography/profile pieces, magazine-style layouts, photography-centric content.

**Prompt fragment:**
```
90s editorial style, high contrast black and white with warm tones, 
film grain texture, editorial grid layout, classic serif typography, 
matte paper texture, contact sheet aesthetic, fashion magazine look, 
Helmut Newton inspired, elegant restraint
```

---

## 9. Neo 3D

**Visual characteristics:** Glossy materials with soft shadows, floating/levitating objects, pastel or saturated solid backgrounds, rounded forms, clay/plastic material feel, soft global illumination.

**When to use:** App marketing, product showcases, SaaS landing pages, tech announcements, playful brand content, icon design, UI mockups.

**Prompt fragment:**
```
neo 3D render, glossy smooth materials, soft shadows, floating objects, 
solid pastel background, rounded forms, clay material feel, 
soft global illumination, subtle reflections, playful 3D illustration, 
isometric perspective, candy-like surfaces
```

---

## 10. Y2K

**Visual characteristics:** Chrome and holographic surfaces, transparent/translucent materials, bubble letters, gradient meshes, star shapes, low-poly 3D, butterfly/angel motifs, baby blue/pink/silver palette.

**When to use:** Gen-Z targeted content, nostalgia campaigns, fashion/beauty, social media trends, pop culture content, merchandise design.

**Prompt fragment:**
```
Y2K aesthetic, chrome and holographic surfaces, translucent materials, 
bubble letter typography, gradient mesh background, star and butterfly motifs, 
baby blue and pink and silver palette, low-poly 3D elements, 
glossy transparent overlays, early 2000s digital aesthetic
```

---

## 11. Liquid Retro

**Visual characteristics:** Fluid organic shapes with retro palettes (avocado, rust, cream, teal), lava lamp curves, smooth gradients, 60s/70s color theory, flowing typography, groovy movement feel.

**When to use:** Music branding, vinyl/audio products, cocktail/bar content, retro-modern brands, creative agency portfolios, festival lineups.

**Prompt fragment:**
```
liquid retro style, fluid organic shapes, retro color palette of avocado green 
and rust orange and cream and teal, lava lamp curves, smooth gradients, 
1970s color theory, flowing psychedelic typography, groovy movement, 
warm analog feeling, mid-century modern influence
```

---

## 12. Metallic Typography

**Visual characteristics:** Chrome/gold/silver 3D letterforms, reflective surfaces, industrial feel, dark backgrounds with metallic shine, embossed or extruded text, dramatic lighting on type.

**When to use:** Luxury branding, music album covers, fashion campaigns, award shows, high-end product launches, title cards, hero sections.

**Prompt fragment:**
```
metallic 3D typography, chrome silver letterforms with reflective surfaces, 
embossed extruded text, dark background, dramatic directional lighting 
highlighting metallic shine, industrial premium feel, 
liquid metal reflections, bold display type
```

---

## 13. Neu Brutalism (Neubrutalism)

**Visual characteristics:** Thick black borders (3-5px), bold solid colors (yellow, pink, blue), visible drop shadows offset to bottom-right, raw unpolished UI feel, monospace or chunky sans-serif type, no gradients.

**When to use:** Developer tools, indie SaaS, creative platforms, portfolio sites, landing pages that need to feel different, design tool marketing.

**Prompt fragment:**
```
neubrutalism style, thick black borders, bold solid colors of yellow and pink 
and blue, visible offset drop shadows, raw unpolished feel, 
chunky sans-serif typography, no gradients, high contrast, 
anti-corporate design, brutalist web aesthetic
```

---

## 14. Rubberhose

**Visual characteristics:** Characters with flexible tube-like limbs (no joints), 1930s cartoon aesthetic, simple oval bodies, pie-cut eyes, white gloves, bouncy posing, thick outlines, limited palette.

**When to use:** Playful brand mascots, animation, children's content, retro gaming, whimsical explainers, merchandise, sticker packs.

**Prompt fragment:**
```
rubberhose cartoon style, flexible tube limbs without joints, 
1930s cartoon aesthetic, simple oval body, pie-cut eyes, white gloves, 
bouncy dynamic pose, thick outlines, limited color palette, 
vintage animation cel look, Fleischer Studios inspired
```

---

## 15. Romantasy

**Visual characteristics:** Soft diffused light, floral elements (peonies, roses, wildflowers), painterly brushwork, warm golden-pink palette, ethereal glow, delicate textures, vintage softness.

**When to use:** Lifestyle brands, wellness/beauty, wedding/event content, book covers, editorial fashion, seasonal campaigns (spring/summer), feminine-coded products.

**Prompt fragment:**
```
romantasy aesthetic, soft diffused golden light, floral elements with peonies 
and wildflowers, painterly brushwork, warm golden-pink palette, 
ethereal glow, delicate textures, vintage softness, dreamy atmosphere, 
Pre-Raphaelite influence, romantic and enchanting
```

---

## 16. Pixel Art

**Visual characteristics:** Visible pixel grid, limited color palette (8-32 colors), dithering for shading, NES/SNES era proportions, clean pixel placement, isometric or side-view perspective.

**When to use:** Gaming content, retro tech branding, developer community content, indie game marketing, nostalgia campaigns, social media avatars.

**Prompt fragment:**
```
pixel art style, visible pixel grid, limited 16-color palette, 
dithering for shading and gradients, NES-era proportions, 
clean deliberate pixel placement, retro gaming aesthetic, 
8-bit or 16-bit look, crisp edges, no anti-aliasing
```

---

## 17. Memphis Design

**Visual characteristics:** Geometric shapes (squiggles, triangles, circles), clashing bold colors, terrazzo-like patterns, asymmetric composition, playful irreverence, post-modern, mix of patterns.

**When to use:** Creative industry content, design conferences, trendy retail, social media graphics, packaging, youth-targeted campaigns, playful enterprise.

**Prompt fragment:**
```
Memphis design style, geometric shapes with squiggles and triangles, 
clashing bold primary and secondary colors, terrazzo-like scattered patterns, 
asymmetric composition, post-modern playfulness, mix of stripes dots 
and zigzags, 1980s Italian radical design, irreverent and energetic
```

---

## 18. Cottagecore

**Visual characteristics:** Pastoral countryside settings, soft natural light, floral prints and gingham, warm muted earth tones with sage and cream, handmade/artisan textures, nostalgic rural romanticism.

**When to use:** Lifestyle brands, food/baking content, sustainable products, home goods, gardening, seasonal autumn/spring content, slow living.

**Prompt fragment:**
```
cottagecore aesthetic, pastoral countryside setting, soft natural golden light, 
floral prints and gingham patterns, warm muted earth tones with sage green 
and cream, handmade artisan textures, nostalgic rural charm, 
wildflower meadow, vintage crockery, cozy and gentle atmosphere
```

---

## 19. Cybercore

**Visual characteristics:** Neon grid lines on dark backgrounds, holographic HUD elements, glitch distortion, matrix-style data streams, electric blue and magenta and green, circuitboard patterns, digital rain.

**When to use:** AI/ML products, cybersecurity, tech conferences, developer tools, sci-fi content, hacker culture, fintech, crypto/web3.

**Prompt fragment:**
```
cybercore aesthetic, neon grid lines on dark background, holographic HUD elements, 
glitch distortion artifacts, matrix-style data streams, electric blue and magenta 
and neon green, circuitboard patterns, digital rain overlay, 
dark futuristic interface, cyberpunk technology aesthetic
```

---

## 20. Brutalism

**Visual characteristics:** Raw concrete textures, exposed structural elements, heavy block forms, monochrome with occasional bold accent, utilitarian typography, grid-based rigid layouts, no decoration.

**When to use:** Architecture content, infrastructure branding, serious institutional content, academic publishing, art galleries, counter-luxury positioning.

**Prompt fragment:**
```
brutalist architecture style, raw concrete texture, exposed structural elements, 
heavy geometric block forms, monochrome with single bold color accent, 
utilitarian sans-serif typography, rigid grid layout, 
no ornamental decoration, honest materials, imposing scale, 
Le Corbusier and Tadao Ando influence
```

---

## 21. Bauhaus

**Visual characteristics:** Primary colors (red, blue, yellow) on white/black, geometric shapes (circle, triangle, square), grid-based composition, sans-serif typography (Futura, DIN), form follows function.

**When to use:** Design education, typography-focused content, modernist brands, architecture, museum/gallery content, minimalist product marketing.

**Prompt fragment:**
```
Bauhaus design, primary colors of red blue and yellow on white background, 
geometric shapes of circle triangle and square, grid-based composition, 
clean sans-serif typography, form follows function, 
modernist graphic design, Kandinsky and Moholy-Nagy influence, 
rational geometry, visual harmony
```

---

## 22. Art Deco

**Visual characteristics:** Gold and black palette, geometric fan/sunburst patterns, symmetrical compositions, decorative line work, elongated proportions, Gatsby-era luxury, ornamental borders.

**When to use:** Luxury brands, event invitations, premium packaging, hotel/hospitality, financial services, awards ceremonies, cocktail/spirits branding.

**Prompt fragment:**
```
Art Deco style, gold and black color palette, geometric fan and sunburst patterns, 
symmetrical composition, decorative linear ornaments, elongated elegant proportions, 
1920s Gatsby-era luxury, ornamental borders and frames, 
chrome and gold metallic accents, opulent geometric elegance
```

---

## 23. Vaporwave

**Visual characteristics:** Pastel pink/purple/teal gradient skies, Greek/Roman statues, Windows 95 UI elements, Japanese text, checkerboard floors, palm trees, sunset grids, glitchy VHS texture.

**When to use:** Ironic/meta content, internet culture, music content, retro tech nostalgia, meme-adjacent branding, youth subculture, aesthetic accounts.

**Prompt fragment:**
```
vaporwave aesthetic, pastel pink and purple and teal gradient sky, 
Greek marble statue bust, Windows 95 UI elements, Japanese katakana text, 
checkerboard floor, palm tree silhouettes, sunset grid perspective, 
glitchy VHS texture, lo-fi digital nostalgia, Macintosh Plus era
```

---

## 24. Glassmorphism

**Visual characteristics:** Frosted glass panels with blur, translucent surfaces with visible backgrounds, subtle borders with white opacity, floating card layouts, vivid gradients behind glass, depth layering.

**When to use:** Modern app UI, SaaS dashboards, fintech products, iOS-style interfaces, product marketing, tech landing pages, notification designs.

**Prompt fragment:**
```
glassmorphism style, frosted glass panels with background blur effect, 
translucent surfaces showing blurred colors beneath, subtle white border, 
floating card layout with depth layering, vivid gradient background 
visible through frosted glass, soft shadows, modern UI aesthetic, 
Apple iOS design language
```

---

## 25. Risograph

**Visual characteristics:** Limited ink colors (2-4) with visible overlap/overprint, paper texture, slight misregistration between colors, halftone dot patterns, grain, soy-ink matte finish.

**When to use:** Independent publishing, zines, art prints, event posters, community organizations, eco-conscious brands, handmade/craft marketing, book covers.

**Prompt fragment:**
```
risograph print style, limited two-color or three-color palette, 
visible color overlap and overprint effects, natural paper texture, 
slight misregistration between color layers, halftone dot pattern, 
grain and noise texture, soy ink matte finish, 
independent press aesthetic, lo-fi print quality
```

---

## 26. Solarpunk

**Visual characteristics:** Lush vegetation integrated with technology, renewable energy elements (solar panels, wind turbines), Art Nouveau organic curves, optimistic green palette, community-scale architecture, bright daylight.

**When to use:** Sustainability content, clean energy brands, urban planning, community projects, optimistic futures content, environmental campaigns, green tech.

**Prompt fragment:**
```
solarpunk aesthetic, lush vegetation integrated with clean technology, 
solar panels and wind turbines, Art Nouveau organic curves in architecture, 
optimistic green and golden palette, community-scale sustainable buildings, 
bright warm daylight, utopian but grounded, nature and technology in harmony
```

---

## Style Combination Patterns

Styles can be combined for unique aesthetics. Some tested pairings:

| Combination | Result | Use Case |
|-------------|--------|----------|
| Minimalism + Brutalism | Raw, stark, powerful | Architecture portfolios |
| Neo 3D + Glassmorphism | Playful depth, modern | SaaS product pages |
| Cottagecore + Risograph | Artisan, handmade feel | Farmers market, crafts |
| Y2K + Cybercore | Retro-futuristic nostalgia | Gen-Z tech content |
| Bauhaus + Flat Illustration | Educational clarity | Design tool documentation |
| Romantasy + Art Deco | Luxurious fantasy | Premium editorial |

When combining, use one style at 70% strength and the other at 30%. Both at full strength usually produces visual confusion.
