# LTX-2 Prompting Guide

## Core Principles

LTX-2 uses Gemma 3 (12B) as its text encoder. Prompts should be detailed, chronological,
and descriptive — think "screenplay direction" not "search query."

## Prompt Structure

Write a single flowing paragraph (~200 words) covering these elements in order:

1. **Scene establishment** — what the viewer sees first
2. **Main subject** — detailed appearance, clothing, features
3. **Action/motion** — specific movements, direction, speed
4. **Environment** — setting, background, surrounding elements
5. **Camera** — angle, movement (pan, dolly, tracking, static)
6. **Lighting** — time of day, light source, shadows, atmosphere
7. **Transitions** — changes that occur during the clip

## Prompt Enhancement

Set `enhance_prompt=True` to let Gemma 3 automatically expand short prompts into
detailed descriptions. Useful for quick iterations but may not capture specific intent.

## Examples by Category

### Cinematic Landscape
> "Aerial drone shot slowly descending over a misty mountain valley at dawn. The peaks
> are snow-capped, emerging from thick fog that fills the valley below. Pine forests
> cover the lower slopes, their dark green contrasting with the white snow. A river
> winds through the valley floor, catching golden light from the rising sun. The camera
> tilts downward as it descends, revealing a small village with stone buildings and
> smoke rising from chimneys. Birds fly across the frame in the middle distance.
> The overall mood is serene and majestic, with cool blue tones in shadows and warm
> golden highlights."

### Character Animation
> "A young woman with curly red hair and a green coat walks through a busy European
> city market. She carries a woven basket and pauses at a flower stall, picking up a
> bouquet of sunflowers. She smiles and smells the flowers. The market is bustling with
> vendors and shoppers. Colorful awnings and hanging lights decorate the stalls. The
> camera follows her at a medium shot from slightly above, tracking her movement through
> the crowd. Natural afternoon light filters through the awnings creating dappled shadows.
> The scene has a warm, nostalgic quality with rich earth tones."

### Abstract / Artistic
> "Macro close-up of oil paint being slowly poured onto a canvas. Thick, viscous streams
> of deep cobalt blue and cadmium red merge and swirl together, creating organic patterns.
> The paint catches studio light, revealing glossy highlights and deep shadows in the
> texture. As the colors mix, secondary purples and magentas emerge at the boundaries.
> The camera slowly pulls back, revealing more of the canvas and the abstract composition
> forming. The background is a clean white studio. The motion is deliberate and mesmerizing."

### Product / Commercial
> "A sleek smartphone rotates slowly on a reflective black surface. The device catches
> dramatic side lighting that highlights its metallic edges and glass back. The screen
> displays a vibrant gradient animation. The camera orbits the device at a low angle,
> transitioning from a three-quarter view to a straight profile shot. Lens flares appear
> as the light catches the camera lens. The background is a deep black gradient. The
> overall aesthetic is premium and minimalist with cool blue accent lighting."

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| "A cat" | Too vague, no detail | Describe breed, color, action, setting |
| "Make text that says Hello" | Cannot reliably render text | Avoid text-in-video requests |
| "A person flying without wings" | Physics violations degrade quality | Keep scenarios plausible |
| "4K ultra-HD cinematic" | Quality keywords don't help | Describe the actual scene |
| Multiple unrelated scenes | Single-clip model | One continuous scene per generation |
| "Generate a 2-minute video" | Limited to ~60s max | Keep under frame limits |

## Keyframe Conditioning Tips

When using `KeyframeInterpolationPipeline`:
- Provide start and end frames as images
- The prompt should describe the transition/motion between them
- Keep keyframe images visually consistent (same subject, similar lighting)

## Audio-Video Prompting

When using `A2VidPipelineTwoStage`:
- Audio conditioning strongly guides the visual output
- Match prompt descriptions to the audio content
- Speech in audio produces better sync than music alone
- Describe visual elements that complement the audio
