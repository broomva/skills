# Cinematic Prompting

How to write prompts that produce intentional, film-quality AI content instead of generic "cinematic" slop.

## The Start-Frame Doctrine

Origin: ohneis652's production workflow, validated across Kling, Wan, Veo, Sora, and Seedance models.

**The rule:** Video quality is only as good as your initial image. Never go straight from text to video. Always generate or select a start frame first, then animate it.

Why this works:
- Text-to-video models have to solve two problems simultaneously: what to show and how to move it. Splitting these into two steps lets each model focus on what it does best.
- The start frame locks composition, lighting, color, character appearance, and camera position. The video model only needs to add motion.
- You can iterate on the start frame cheaply (image generation is fast and cheap) before committing to expensive video generation.
- A mediocre motion model with a perfect start frame beats a perfect motion model with a text-only prompt.

### Start-Frame Workflow

```
1. Write a detailed image prompt (see below)
2. Generate 4-8 candidate frames
3. Select the best one (composition, lighting, character accuracy)
4. Optionally upscale the selected frame
5. Feed the frame + a motion prompt into the video model
6. The motion prompt should describe ONLY movement, not scene content
```

### Writing the Image Prompt

The image prompt has five components, in order of importance:

1. **Subject** -- who/what is in the frame, with specific details (not "a person" but "a woman in her 30s with short dark hair, wearing a charcoal wool coat")
2. **Composition** -- camera angle, framing, depth of field ("medium close-up, shallow depth of field, subject positioned at left-third rule intersection")
3. **Lighting** -- source, quality, direction, color temperature ("warm golden hour sidelight from camera-left, soft fill from a bounce board camera-right, deep shadows on the far side of the face")
4. **Environment** -- setting, atmosphere, background treatment ("standing in a rain-wet Tokyo alley, neon signs reflected in puddles, background bokeh from distant traffic")
5. **Technical** -- film stock, lens, format ("shot on Kodak Vision3 500T, 85mm f/1.4 lens, anamorphic lens flare, 2.39:1 aspect ratio, subtle film grain")

### Writing the Motion Prompt

Once the start frame is locked, the motion prompt should describe ONLY:
- Camera movement: "slow dolly forward", "steady left-to-right pan", "gentle crane up"
- Subject movement: "turns head to face camera", "walks forward two steps", "reaches for the object"
- Environmental motion: "rain falling", "neon signs flickering", "leaves drifting"
- Pacing: "slow, contemplative pace" or "fast, energetic movement"

**Do not** re-describe the scene content, lighting, or composition in the motion prompt. The start frame already contains that information.

## Soul Cinema vs General Models

"Soul Cinema" is the approach of treating AI generation as filmmaking rather than illustration. The distinction:

| General AI Content | Soul Cinema |
|-------------------|-------------|
| "Make it look cinematic" | Specific director vocabulary + technical camera language |
| Random composition | Intentional framing using rule of thirds, leading lines, negative space |
| "Good lighting" | Named lighting setups (Rembrandt, butterfly, split, practical motivated) |
| Default color palette | Color grading with specific references (teal-orange, bleach bypass, cross-processed) |
| Single static shot | Planned camera movement with purpose (reveal, track, establish) |
| No film reference | Explicit film stock, lens, and format specification |

## Intentional Lighting

Lighting is the most impactful prompt element after subject. Named lighting setups produce dramatically better results than vague descriptions.

### Lighting Vocabulary

| Setup | Description | Prompt Pattern | Mood |
|-------|-------------|---------------|------|
| **Rembrandt** | Key light at 45 degrees, triangle of light on shadow side of face | `Rembrandt lighting, triangle of light on the cheek, warm key light at 45 degrees` | Classic portraiture, drama |
| **Butterfly** | Key light directly above and in front of the face, butterfly shadow under nose | `butterfly lighting from directly above, glamour lighting, soft shadow under the nose` | Beauty, fashion, glamour |
| **Split** | Key light at 90 degrees, half the face in shadow | `split lighting, half the face in deep shadow, dramatic side light` | Mystery, conflict, noir |
| **Rim/Edge** | Strong backlight creating a bright outline around the subject | `strong rim light, bright edge light outlining the subject against dark background` | Separation, ethereal, sci-fi |
| **Practical** | Motivated by visible light sources in the scene (lamps, screens, candles) | `lit only by the glow of computer screens, practical lighting from desk lamp, motivated light sources` | Naturalism, intimacy |
| **Chiaroscuro** | Extreme contrast between light and dark, Caravaggio-inspired | `chiaroscuro lighting, deep black shadows, single strong directional light source, Caravaggio-inspired` | High drama, fine art |
| **Ambient/Flat** | Even, soft light from all directions, minimal shadows | `soft ambient light, overcast sky, even illumination, minimal shadows` | Documentation, product |
| **Golden Hour** | Warm, low-angle sunlight with long shadows | `golden hour sunlight, warm orange glow, long shadows, magic hour, backlit` | Romance, nostalgia, beauty |
| **Neon** | Colored artificial light sources, typically urban night | `lit by neon signs, pink and blue neon glow, urban night lighting, colored light spill` | Urban, cyberpunk, nightlife |

### Depth and Composition

Depth cues make AI-generated images feel three-dimensional rather than flat:

**Foreground elements:** Include objects in the near plane to create depth. "Shot through a rain-streaked window", "foreground flowers out of focus", "steam rising in the foreground."

**Atmospheric perspective:** Objects farther from camera should be hazier and less saturated. "Atmospheric haze in the background", "distant mountains fading into blue", "fog rolling through the valley."

**Focus plane:** Specifying what is in focus and what is not creates the most natural depth. "Sharp focus on the subject's eyes, background in soft bokeh", "rack focus from foreground object to distant figure."

**Leading lines:** Use environmental geometry to direct the eye. "Railway tracks converging to vanishing point", "corridor walls creating perspective lines toward the subject."

## Camera Movement Vocabulary by Director Style

### Wes Anderson Moves
```
Static, locked-off frame. No movement. 
Occasional slow lateral dolly (always perfectly horizontal).
Quick whip pans between subjects (180 degrees, sharp).
Zoom-in to detail (not dolly — actual zoom, slightly artificial).

Prompt patterns:
"static centered frame, no camera movement"
"slow lateral dolly, perfectly level, tracking left to right"
"quick whip pan to the right, sharp stop"
```

### David Fincher Moves
```
Slow, deliberate dolly. Millimeter precision.
Overhead shots looking straight down.
Impossible camera moves (through walls, into objects) — CG-enhanced.
Push-in during dialogue (almost imperceptible).

Prompt patterns:
"slow deliberate dolly forward, barely perceptible movement"
"bird's eye view, camera looking straight down, overhead shot"
"very slow push-in on the subject's face, clinical precision"
```

### Christopher Nolan Moves
```
Sweeping crane shots over landscapes.
Handheld close-ups during action (controlled chaos).
IMAX-scale establishing shots with slow tilt.
Rotating/spinning shots for disorientation (Inception, Interstellar).

Prompt patterns:
"sweeping crane shot rising over the landscape, epic IMAX wide angle"
"handheld close-up, slight shake, urgent, documentary feel"
"slow upward tilt revealing the full scale of the structure, IMAX 65mm"
```

### Denis Villeneuve Moves
```
Extremely slow push-in from wide to medium (takes 10+ seconds).
Static wide shots held for uncomfortable duration.
Drone/aerial establishing shots, slow glide.
Minimal camera movement — the frame breathes, barely moves.

Prompt patterns:
"extremely slow push-in from wide establishing shot, contemplative pace"
"static wide shot, vast negative space, held for a long beat"
"slow aerial glide over geometric architecture, drone perspective"
```

### Stanley Kubrick Moves
```
Steadicam following subject from behind through corridors.
One-point perspective tracking shots (The Shining hallways).
Slow zoom-in on a static subject (Barry Lyndon, 2001).
Symmetrical framing maintained throughout movement.

Prompt patterns:
"steadicam tracking shot following from behind through a long corridor"
"one-point perspective, camera moving forward through symmetrical hallway"
"very slow zoom-in on a static subject, centered in frame, unsettling"
```

### Wong Kar-wai Moves
```
Handheld, slightly unsteady, intimate.
Step-printed slow motion (lower frame rate, jerky).
Canted/dutch angles during emotional moments.
Quick snap-zooms.

Prompt patterns:
"handheld camera, intimate close-up, slightly unsteady, step-printed slow motion"
"canted angle, tilted frame, swaying handheld movement"
"quick snap zoom to close-up, neon-lit background blurred"
```

## Prompt Assembly Template

Use this template to assemble complete generation prompts:

```
[Subject with specific details],
[Composition: camera angle + framing + depth of field],
[Lighting: named setup + direction + color temperature],
[Environment: setting + atmosphere + background],
[Director vocabulary: 3-5 specific keywords from the style table],
[Technical: film stock + lens + format + grain/texture],
[Mood: 1-2 emotional descriptors]
```

### Example: Fincher-style tech noir

```
A software engineer in her late 20s with glasses and a dark hoodie,
medium close-up, shallow depth of field, subject off-center right,
lit only by the glow of three monitors, cold blue light on her face with 
deep shadows on the far side, desaturated practical lighting,
seated in a dark server room with blinking LED indicators in the background,
desaturated color grade, clinical precision, cold blue-green tones, 
low-key lighting, very slow push-in,
shot on RED Monstro 8K, 50mm f/1.2 lens, subtle digital noise,
tense, focused, isolated
```

### Example: Villeneuve-style landscape

```
A solitary figure in a sand-colored environment suit standing at the edge 
of a vast desert basin, tiny in the frame,
extreme wide shot, deep depth of field, figure positioned at bottom-third,
diffused overcast light filtering through atmospheric haze, warm amber tones,
endless geometric rock formations extending to the horizon, heat shimmer,
vast negative space, geometric architecture, muted earth tones, 
contemplative silence, slow push-in,
shot on ARRI Alexa 65, 21mm wide angle lens, 2.39:1 anamorphic,
awe, solitude, insignificance
```

## Validated Composition Strategies (April 2026)

Findings from hands-on production sessions using Google's Imagen 4.0 + Veo 3.0 pipeline.

### Start-Frame Doctrine: PROVEN

The Start-Frame Doctrine (described above) has been validated end-to-end with the Imagen 4.0 keyframe + Veo 3.0 image-to-video pipeline. The results are dramatically better than text-to-video alone. Text-to-video produces generic, flat output; image-to-video with a crafted keyframe locks composition, lighting, and identity from the first frame.

The workflow is:

```
1. Generate keyframe via Imagen 4.0 (imagen-4.0-generate-001)
   → Returns high-resolution PNG, fast and cheap
2. Analyze keyframe via Gemini (gemini-2.5-flash, not preview models)
   → Confirms composition, lighting, subject fidelity
3. Feed keyframe + motion prompt into Veo 3.0 (image-to-video)
   → Veo animates the frame; motion prompt describes ONLY camera movement
```

### Image Prompt: 5-Component Priority Order

The image prompt (for keyframe generation) must contain five components in strict priority order. This order is load-bearing — dropping lower-priority components is acceptable, but reordering or omitting higher-priority ones produces poor results:

1. **Subject** — who/what, with specific physical details
2. **Composition** — camera angle, framing, depth of field, rule-of-thirds placement
3. **Lighting** — named setup, direction, color temperature, shadow behavior
4. **Environment** — setting, atmosphere, background treatment, depth cues
5. **Technical** — film stock, lens focal length + aperture, aspect ratio, grain/texture

### Motion Prompt: Camera Movement ONLY

When feeding a keyframe into Veo 3.0 image-to-video, the motion prompt must describe ONLY camera movement. Never re-describe the scene content, lighting, composition, or subject appearance. The keyframe already contains all of that information. Re-describing it confuses the model and degrades output quality.

Good motion prompts:
- `"Slow dolly forward, gentle drift left"`
- `"Steady crane up revealing the horizon"`
- `"Subtle handheld micro-movements, breathing camera"`

Bad motion prompts:
- `"A woman in a charcoal coat walks through a neon-lit Tokyo alley with rain..."` (re-describing the scene)

### Veo 3.0 API: Technical Details

**Image input format:** The keyframe must be passed as `types.Image(image_bytes=bytes, mime_type='image/png')`. Do not pass a PIL Image object or a `Part` wrapper — Veo expects the raw Image type with bytes.

**`person_generation` parameter:** This parameter must be OMITTED entirely for image-to-video calls. Including it (even set to `"allow_adult"`) causes the Veo API to reject the request. It is only valid for text-to-video.

**Rate limits (free tier):** Approximately 5-6 video generations per day. Plan shot lists accordingly — generate all keyframes first (unlimited), review and select, then spend the video budget on the best frames.

### Model Selection

| Task | Model | Notes |
|------|-------|-------|
| Keyframe generation | `imagen-4.0-generate-001` | High-res PNG, fast, cheap. Use for all start frames. |
| Keyframe analysis | `gemini-2.5-flash` | Use the stable release, not preview models. Analyzes composition/lighting fidelity. |
| Image-to-video | Veo 3.0 | Feed keyframe as `types.Image`. Omit `person_generation`. Motion prompt = camera only. |
| Text-to-video | Veo 3.0 | Fallback only. Always prefer image-to-video with a keyframe. |

### Production Implications

- **Budget your video generations.** At 5-6 per day on free tier, each Veo call is precious. Never send a keyframe you have not reviewed.
- **Keyframes are cheap.** Generate 4-8 candidate keyframes via Imagen, select the best, then animate. This is the core efficiency of the Start-Frame Doctrine.
- **Gemini analysis as quality gate.** Before spending a Veo generation, run the keyframe through `gemini-2.5-flash` to verify composition matches intent. This catches misaligned framing before it costs a video slot.

---

## AI Video Creators distillation (AVCC additions)

> Distilled from the AI Video Creators course (BRO-1525) — see broomva/workspace docs/reference/ai-video-creators-course/. Copy-paste **verbatim prompt packs** for this craft live in [`ai-video-prompt-packs.md`](./ai-video-prompt-packs.md).
>
> This section adds only material NOT already covered above. The Start-Frame Doctrine (above) is the same principle AVCC calls "image-first, then animate" — keyframes become video inputs; that overlap is not restated. AVCC's contribution is the explicit prompt *formula*, a model-specific ordering hierarchy, a named control-lever framework, the parameter-not-feeling rule, model JSON support, the seven aesthetics and their meta-messages, two camera-language reference tables, and a trainable visual-taste loop. Model versions cited (Kling 3.0, Nano Banana Pro, Seedance 2.0) are late-2025/early-2026 snapshots — the course itself says model leadership "rotates quarterly." Treat the *workflow logic and prompt structure* as durable; treat *version names, credit costs, and free-tier claims* as perishable.

### The master image-prompt formula (SHOT+LENS+LIGHT+TEXTURE+COMPOSITION+STYLE)

AVCC compresses the whole image brief into one ordered checklist run **every time** you write a prompt:

```
SHOT + LENS + LIGHT + TEXTURE + COMPOSITION + STYLE REFERENCE
```

The professional variant appends one more slot — **EMOTIONAL VISION**, a single phrase stating how the viewer should feel:

```
SHOT + LENS + LIGHT + TEXTURE + COMPOSITION + STYLE REFERENCE + EMOTIONAL VISION
```

Why this works: it maps the same craft the **5-Component Priority Order** (§ above) encodes, but adds **two slots that order misses** — an explicit **LENS/focal-length** slot (perspective, compression, isolation — see lens table below) and an explicit **TEXTURE** slot (the single most reliable cure for the "plastic AI look"). Where the 5-component order folds lens into "Technical," AVCC promotes it to a first-class, named decision so it never gets dropped. Use the 5-component order to *prioritize* (what to keep when you must trim); use this formula as the *completeness checklist* (did I make a deliberate decision in every slot).

The fully-assembled homework version of this formula, as a fill-in template:

```
"Medium shot of [subject] doing [action], shot on [lens] at [aperture], [camera angle].
[Lighting description: source + direction + quality + temperature].
Detailed textures on [key materials]. [Composition choice] with [note about negative space or depth].
Styled like [described visual reference], evoking [emotional intention]."
```

A worked director-level example (note every slot is filled with a parameter, not an adjective):

```
Motocross rider mid-lean on a dirt track, captured in gritty 90s analog style,
vertical black and white frame with strong motion blur,
shot handheld with a 35mm lens at f/2.8, 1/33 of a second, ISO 400,
flat overcast daylight, diffused shadows, helmet highlights softly blown out,
granular dirt with lateral dust streaks, styled like vintage Marlboro campaigns,
evoking raw speed and unpolished realism.
```

### "AI understands parameters, not feelings"

The single most load-bearing rule in AVCC's prompt craft, and the reason the formula above is built from technical slots. Models were trained on captioned photography and cinematography, so they respond to the vocabulary that *describes* photographs — bodies, lenses, apertures, shutter speeds, color temperatures, named lighting setups — and respond poorly to mood words.

Do **not** write:

```
moody portrait, cinematic lighting
```

Write the parameters that *produce* that mood:

```
85mm portrait, f/1.4, soft side lighting, warm 3200k tones
```

Same rule applied to a style decision — instead of "cinematic lighting," name the decisions:

```
muted blue-gray palette, matte textures, soft haze, asymmetrical composition, gritty editorial mood, 35mm lens
```

Why this works: a mood word is a *result* the model has to guess a path to; a parameter is the *path itself*. Naming camera language is also the cheapest single realism lever (see "Camera language = realism" under the control levers below).

### Nano Banana Pro: the Object → Context → Technical hierarchy

Modern reasoning-based image models (Nano Banana Pro is the reference instance; versions rotate) read prompts best when written in a specific **order of importance**, distinct from the cinematic SHOT-first formula above. NBP's "Spatial Intelligence" resolves the scene as 3D before drawing, so it wants the *thing* first, then *where it lives*, then *how it's shot*:

```
1. Object       (the single most important element)
2. Context / Environment
3. Technical settings   (lens, lighting, mood)
```

Worked example (a product campaign base shot):

```
a bright matte ZUFA-ZUFA can inside a traditional Central Asian yurt
A low-angle view of the can, where we see it against a hole in the yurt's roof.
Light beams shine through with smoke and steam
```

Object = the matte can · Context = inside the yurt · Technical = low angle, light beams through the roof hole, smoke/steam diffusion.

Why this works: a reasoning model anchors on the primary object, then places it spatially, then applies optics — feeding the prompt in that order matches its internal resolution sequence and produces stable, glitch-free results (objects don't float, shadows land correctly, light scatters on the matte surface). This is **not** a contradiction of the SHOT-first cinematic formula — it is the *model-specific* ordering for reasoning-class generators. Use SHOT-first for camera-driven cinematic stills (Midjourney, Imagen-class); use Object-first for reasoning-class generators doing product/integration/text work. When in doubt, AVCC's guidance is to **test both formats plus a JSON version and pick the winner** — they produce genuinely different outputs.

### The 5 universal control levers (named framework)

AVCC names exactly five levers that hold true across **both image and video** generation. When output is wrong, you are almost always failing to pull one of these — not failing to find "the perfect words":

| # | Lever | What it does | Concrete handle |
|---|-------|--------------|-----------------|
| 1 | **Camera language = realism** | Naming real camera bodies/lenses deterministically shifts lighting, depth, and grade because the training data was photography | `Sony A7R IV`, `Hasselblad H6D`, `ARRI ALEXA 35`, `RED KOMODO 6K`, `85mm f/1.4`, `35mm anamorphic` |
| 2 | **References > prompts** | Control comes from reference *images*, not better text — the dominant control surface | OmniReference (Midjourney) · Elements (Kling) · 9-image collage (Seedance ≈ 80% of control) · drag image into prompt window |
| 3 | **Negative constraints** | Stating what must NOT happen is as important as positive instruction | `no tongue, mouth closed` · `NO UI, no plastic skin` · negative-prompt field for upscale |
| 4 | **Physics must be explicit** | For object integration: weight, gravity, contact shadows, indentation, reflections — or objects float | `contact shadow under the can`, `the cushion indents under its weight`, `reflection on the wet floor` |
| 5 | **Deliberate imperfection = realism** | For UGC/authentic looks, perfection reads as fake; specify flaws | `shot on iPhone`, `uneven exposure`, `sensor noise`, `slight horizon tilt`, `natural blink and breath` |

Why this framework matters: it converts "why did it give me a weird result?" into a diagnostic — walk the five levers and find the one you under-specified. It composes with the universal generator model `PROMPT → MODEL → CONTROLS → RESULT`: the levers tell you *what* to change inside the PROMPT and CONTROLS layers. Levers 1 and 3 reinforce the [Soul Cinema](#soul-cinema-vs-general-models) and [motion-prompt](#motion-prompt-camera-movement-only) doctrines above; levers 2, 4, 5 are AVCC-distinct additions.

### JSON prompt support is a per-model property

Whether you can use structured JSON prompting is a **property of the model**, not a universal technique. Get this wrong and a JSON prompt degrades to garbage on a model that can't parse it.

| Model class | JSON support | Notes |
|-------------|--------------|-------|
| **Nano Banana Pro** | Yes | Reasoning-based; handles structured blocks well |
| **Kling** | Yes | JSON-friendly modern video model |
| **Veo** | Yes | JSON-friendly |
| **Sora** | Yes | JSON-friendly |
| **Midjourney** | **No** | Plain text only — JSON will not parse; use natural-language prompts |

A JSON prompt template for the models that support it:

```json
{
  "camera": {
    "angle": "front three-quarter view",
    "lens": "35mm",
    "movement": "static"
  },
  "lighting": {
    "type": "soft studio three-point",
    "key_light": "warm",
    "rim_light": "subtle",
    "shadow_style": "soft"
  },
  "color_palette": ["#HEX", "#HEX"],
  "subject": {
    "type": "...",
    "pose": "...",
    "expression": "..."
  },
  "render_style": "3D toon shading"
}
```

Why this works: JSON shines for **structured, repeatable** images — illustrations, toon shading, 3D-inspired art, and producing controlled variations within one visual system (lock everything, change one field). For photographic/cinematic stills, natural language still wins. Build JSON fast by pasting the template into ChatGPT and using **voice input** to fill each block.

### The 7 main aesthetics and their meta-messages

An aesthetic is a *communication choice*, not decoration — each one carries a meta-message the audience reads before they read any copy. Choosing the wrong aesthetic for the goal is a strategic error no amount of prompt polish fixes. Pick the aesthetic from the chain `Goal → Emotion → Aesthetic → Palette & Light → References`.

| # | Aesthetic | Meta-message | Hallmarks (prompt keywords) | Used for |
|---|-----------|--------------|------------------------------|----------|
| 1 | **Cinematic** | story, emotion, importance | dramatic lighting, depth & contrast, shallow DoF, film-like grading | storytelling, emotional ads, trailers, premium narratives |
| 2 | **Minimalist** | clarity, trust, premium | clean compositions, neutral palettes, soft diffused light, lots of negative space | brands, tech, skincare, luxury products |
| 3 | **Editorial / Fashion** | confidence, trend, luxury | bold posing, polished skin/textures, studio lighting, campaign styling | fashion, beauty, branding, high-end campaigns |
| 4 | **Dreamy / Soft** | emotion, nostalgia, calm | pastel/muted colors, glow & haze, gentle light, romantic/introspective | lifestyle, emotional storytelling, memory-driven content |
| 5 | **Retro / Vintage** | authenticity, memory, humanity | film grain, warm tones, analog imperfections, candid feel | heritage brands, storytelling, human-focused visuals |
| 6 | **Gritty / Dark** | power, intensity, rebellion | high contrast, deep shadows, rough textures, urban realism | sports, street culture, raw energy, masculine brands |
| 7 | **Futuristic / Tech** | innovation, speed, advancement | neon/rim lighting, chrome/glossy surfaces, clean geometry, digital precision | tech, AI, future-focused products/services |

Core elements that compose any aesthetic: **Color + Light + Composition + Texture + Mood (+ Shapes)** — changing **one element** can completely flip how an image feels. Color meta-meanings: **warm = emotional · cool = intelligent · dark = powerful · pastel = gentle.** Substyles (Y2K, Dark Academia, Indie Sleaze, Barbiecore, Cyberpunk, etc.) are a refinement vocabulary layered on top — not rigid categories. To apply an aesthetic: (1) name it, (2) add palette + light + texture + mood keywords, (3) keep the vocabulary *consistent* across variations, (4) generate multiple options and pick the strongest. The Soul Cinema doctrine above is the *Cinematic* row of this table taken to full director-vocabulary depth; the other six aesthetics are the AVCC-distinct additions.

### Shot type → emotion (reference table)

The shot type is the lens's first emotional decision — it sets how close the viewer stands to the subject before any lighting or grade applies.

| Shot | Emotional / storytelling effect |
|------|----------------------------------|
| Extreme close-up | Intimacy; forces attention onto small details |
| Close-up | Focuses on emotion |
| Medium shot | Balances emotion with surrounding context |
| Full shot | Shows the entire figure plus environment |
| Long shot | Atmosphere dominates the frame |
| Over-the-shoulder | Presence; puts the viewer inside the scene |
| Point-of-view (POV) | Full immersion from the character's perspective |
| Bird's-eye view | Abstraction plus sense of scale |
| Worm's-eye view | Power, dominance |

### Lens / focal length → psychology (reference table)

Focal length is the SHOT formula's LENS slot. Short lenses exaggerate space and pull in more environment; long lenses compress space and isolate the subject. Pick the focal length for the *psychological* effect, then it doubles as a realism cue (lever 1).

| Focal length | Character / psychology |
|--------------|------------------------|
| 14–24mm (ultra-wide) | Dramatic, distorted, dynamic; exaggerates space, more environment |
| 24–35mm (wide) | Lots of environment, natural dynamism |
| 35–50mm (standard) | Close to human-eye perspective |
| 85–135mm (portrait) | Flattering compression, subject isolation |
| 200mm+ (telephoto) | Extreme compression, flattened backgrounds |

These two tables are the substance behind the director-style camera-movement vocabulary above: the director sections tell you *how the camera moves*; these tables tell you *what the static frame's shot type and lens do to the viewer* before any movement is added.

### The visual-taste training system (Curate → Patterns → Prompts → Practice)

Taste is **trainable** — it is the set of visual decisions you repeat on purpose (color language, lighting style, composition habits, texture choices, mood), and it is what separates "random prompt → random image" from creative direction. The shift is from **Random** (decisions are arbitrary, output looks arbitrary) to **Curated** (repeat the same visual language deliberately, control the *why*). The four-step loop:

1. **CURATE** — collect like a director, not consume like entertainment. Build a board of premium/emotional/aligned references; target ~20–30 strong references to start, then +5/day. You are collecting *assets*, not chasing inspiration dopamine.
2. **FIND PATTERNS** — treat the board as a *dataset*, not a collage. Identify 2–4 repeating patterns (palette, lighting signature, texture choices, composition habits, recurring moods) — these become your aesthetic direction.
3. **TASTE → PROMPTS** — translate taste into *language*. This is the step that makes taste usable: "Woman on the street, cinematic lighting" is weak; "Muted blue-gray palette, matte textures, soft haze, asymmetrical composition, gritty editorial mood, 35mm lens" is direction. **Taste becomes usable only when it becomes language** (note this is the same "parameters not feelings" rule applied to your own style).
4. **PRACTICE (micro)** — repetition builds taste: recreate one reference exactly, generate 5 variations in the same aesthetic, change *lighting only*, then *angle only*, building a small "signature pack." The goal is **control, not variety.**

A fast shortcut: upload your moodboard to ChatGPT and ask it to extract palette, lighting, textures, composition, and mood, plus ready-to-use keywords *and* an aesthetic **"NO list"** (what breaks your style) — that becomes a repeatable style-guide system. Why this works: it makes the front-end of the SHOT formula (STYLE REFERENCE + EMOTIONAL VISION) a deliberate, owned input rather than a per-prompt guess — the same way the Start-Frame Doctrine makes composition a deliberate input to the video model.
