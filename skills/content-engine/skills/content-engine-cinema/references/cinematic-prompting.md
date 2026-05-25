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
