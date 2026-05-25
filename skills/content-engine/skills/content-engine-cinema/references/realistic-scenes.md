# Realistic Scene Generation

Photorealistic scene generation using the viznfr method for character-consistent, brand-aligned content production.

## The Scene Generation Formula

The viznfr method breaks photorealistic generation into five sequential steps. Each step constrains the next, eliminating the randomness that makes AI output feel generic.

```
Persona Definition → Character Sheet → Scene Description → Face Swap → Generate
```

Skipping steps produces inconsistency. Running them in order produces characters that look the same across dozens of scenes.

## Step 1: Persona Definition

A persona is not just appearance -- it encodes the entire character context that influences visual output.

### Persona Template

```yaml
name: "Maya Chen"
demographics:
  age_range: "28-32"
  ethnicity: "East Asian"
  build: "athletic, lean"
  height: "5'7\""

appearance:
  hair: "black, shoulder-length, straight with slight wave at ends"
  eyes: "dark brown, almond-shaped"
  skin: "warm olive undertone, clear complexion"
  distinguishing: "small mole above left lip, defined jawline"

wardrobe:
  default: "charcoal wool coat, dark jeans, white sneakers"
  professional: "navy blazer, white oxford shirt, tailored trousers"
  casual: "oversized vintage band tee, high-waisted jeans"
  
personality_cues:
  posture: "confident, shoulders back, direct eye contact"
  expressions: "thoughtful, slight asymmetric smile, focused gaze"
  energy: "calm intensity, deliberate movements"

environment_affinity:
  - "modern urban architecture"
  - "coffee shops with natural light"
  - "minimalist workspaces"
  - "rainy city streets"
```

The persona drives every downstream decision. Wardrobe affects lighting (dark clothes need different key-to-fill ratios). Personality cues affect pose direction. Environment affinity narrows scene options.

## Step 2: Character Sheet Generation

The character sheet is a multi-angle reference image that locks visual identity. This is the anchor for all subsequent scenes.

### Generating a Character Sheet

**Method 1: Nano Banana multi-view (API-first)**
```
Prompt: "Character reference sheet of [persona description], 
front view, 3/4 view, side profile, back view, 
neutral grey background, even studio lighting, 
full body and face detail, consistent proportions across all views,
clean white background, character turnaround sheet"
```

Generate at the highest resolution available. The character sheet is the most important asset in the pipeline.

**Method 2: ComfyUI with multi-view LoRA**
Use a multi-view LoRA (e.g., CharTurner, MVDream) to generate consistent turnarounds from a single reference. See [node-pipelines.md](node-pipelines.md) for the ComfyUI setup.

**Method 3: Photo reference + style transfer**
Start from a real photo (stock or custom), then use style transfer to match the desired aesthetic while preserving facial features.

### Character Sheet Quality Checklist

- [ ] Face is clearly visible and consistent across all views
- [ ] Skin tone and texture are uniform (no random color shifts)
- [ ] Hair style and color match exactly across views
- [ ] Body proportions are consistent (no stretched limbs, changing heights)
- [ ] Clothing details match across all angles
- [ ] Lighting is neutral and even (no dramatic shadows that hide features)
- [ ] Resolution is high enough for face-swap extraction (minimum 512px on face)

## Step 3: Scene Description

The scene description combines character action with environment, lighting, and camera specifics. It references the persona but adds the narrative context.

### Scene Description Template

```
[Character name] [action/pose], [wardrobe from persona],
[environment with specific details],
[lighting setup from cinematic-prompting.md],
[camera angle and framing],
[mood/atmosphere],
[technical specifications]
```

### Example Scenes for Maya Chen

**Scene A: Morning workspace**
```
Maya Chen sitting at a minimalist desk reviewing code on a large monitor,
wearing her charcoal wool coat draped over the chair back, white oxford shirt 
with sleeves rolled to the elbows,
modern co-working space with floor-to-ceiling windows, morning light streaming in,
soft window light from camera-left as key, cool ambient fill from overhead LEDs,
medium shot from slightly above, shallow depth of field on her face and hands,
focused and absorbed, calm productivity,
shot on Sony A7IV, 35mm f/1.4, natural light, subtle warm grade
```

**Scene B: Evening street**
```
Maya Chen walking through a rain-wet city street at dusk, hands in coat pockets,
wearing the charcoal wool coat buttoned up, dark jeans, white sneakers,
Tokyo side street with small restaurants and warm-lit signs, wet asphalt reflections,
neon signs providing colored rim light, warm incandescent spill from shop windows,
medium-wide tracking shot, subject at left third, shallow depth of field,
contemplative, solitary, urban intimacy,
shot on Canon C70, 50mm f/1.2, anamorphic adapter, teal-orange grade
```

**Scene C: Presentation**
```
Maya Chen standing confidently at a podium, making eye contact with the audience,
navy blazer over white oxford, wireless lavalier microphone,
modern conference stage with large screen behind her showing a data visualization,
theatrical stage lighting with warm key and blue-purple LED wash on backdrop,
low-angle medium shot looking slightly up, deep depth of field,
commanding presence, quiet confidence,
shot on RED Komodo, 85mm f/1.8, controlled stage lighting
```

## Step 4: Face Swap for Identity Lock

After generating the scene, the face may not perfectly match the character sheet. Face swap corrects this.

### Face Swap Pipeline

```
Character Sheet (reference face) + Scene Render (target body/pose) → Face Swap → Blended Output
```

**Tools (by priority):**

1. **InsightFace / ReActor** (ComfyUI node) -- best for local pipeline, runs on GPU, good at preserving lighting on the swapped face
2. **FaceSwap API** (fal.ai / Replicate) -- API-first option, send reference + target, get result
3. **IP-Adapter Face** (ComfyUI) -- not a traditional swap; uses the face as a conditioning signal during generation. Better at matching the lighting naturally but less precise on features.

### Face Swap Quality Rules

- The reference face image should be well-lit, front-facing, at least 512x512 pixels
- After swapping, check that the lighting direction on the face matches the scene's key light
- Skin tone must match between face and neck/hands (adjust if needed)
- Hair at the face boundary should blend naturally (no hard edge from the swap mask)
- Expression should match the scene's mood (a smiling face swap onto a tense pose looks wrong)

## Step 5: Generate and Iterate

The final render combines all constraints. At this point, most of the creative decisions are already made -- generation is execution, not exploration.

### Iteration Protocol

1. Generate 4 candidates from the same scene description
2. Select the best based on: composition accuracy, lighting match, character consistency
3. If none are acceptable, diagnose the failure:
   - Wrong composition? Adjust the camera/framing language in the prompt
   - Wrong lighting? Make the lighting setup more explicit
   - Character looks different? Re-run face swap with a better mask
   - Environment wrong? Add more environmental detail to the prompt
4. Never iterate more than 3 rounds. If it is not working after 3, the scene description needs restructuring, not re-rolling.

## Brand DNA to Scene Workflow

When generating content for a brand, the persona and scene must align with brand identity.

### Brand DNA Extraction

From any brand, extract:

```yaml
brand_dna:
  color_primary: "#1a1a2e"        # From logo/website
  color_secondary: "#e94560"      # Accent color
  color_neutral: "#f5f5f5"        # Background/text
  typography_feel: "geometric sans-serif, clean, modern"
  visual_mood: "confident, innovative, approachable"
  environments: 
    - "modern tech offices with natural materials"
    - "outdoor urban spaces, clean architecture"
    - "abstract gradient backgrounds"
  lighting_preference: "bright, even, optimistic"
  avoid:
    - "dark, moody, gritty"
    - "cluttered, messy environments"
    - "overly formal/corporate"
```

### Applying Brand DNA to Scenes

The brand DNA modifies the scene description template:

1. **Color palette** -- environments and wardrobe should include or complement brand colors
2. **Lighting preference** -- brand "mood" translates to a lighting setup
3. **Environment** -- use the brand's environment affinity, not the character's
4. **Avoid list** -- explicitly exclude these in the negative prompt or by omission

## Weavy Integration for Infinite Variations

Once a scene template is validated (produces good results), create variations by systematically changing one dimension at a time.

### Variation Axes

| Axis | Example Changes |
|------|----------------|
| **Time of day** | Same scene at morning, noon, golden hour, night |
| **Weather** | Clear, overcast, rain, fog, snow |
| **Wardrobe** | Same pose and environment, different outfit |
| **Camera angle** | Wide, medium, close-up, overhead, low-angle |
| **Season** | Spring blooms, summer light, autumn leaves, winter frost |
| **Action** | Standing still, walking, sitting, gesturing, looking away |

### Batch Generation Pattern

```python
# Pseudocode for scene variation batch
base_scene = load_scene_template("maya-workspace")
variations = [
    {"time": "morning", "weather": "clear", "camera": "medium"},
    {"time": "morning", "weather": "rain", "camera": "medium"},
    {"time": "evening", "weather": "clear", "camera": "wide"},
    {"time": "evening", "weather": "rain", "camera": "close-up"},
]

for v in variations:
    prompt = base_scene.render(
        time_of_day=v["time"],
        weather=v["weather"],
        camera_angle=v["camera"]
    )
    results = generate(prompt, num_candidates=4)
    best = select_best(results, criteria=["composition", "lighting", "character"])
    face_swapped = face_swap(best, character_sheet="maya-chen-reference.png")
    save(face_swapped, path=f"assets/maya/{v['time']}-{v['weather']}-{v['camera']}.png")
```

This approach produces a content library from a single validated scene template.

## Character Consistency Across Scenes

The hardest problem in AI content production is making the same character look like the same person across different scenes. The combination of character sheet + face swap + LoRA provides three layers of consistency:

1. **Character sheet** -- defines the canonical appearance
2. **Face swap** -- enforces facial identity in each output
3. **LoRA** (optional) -- trained on the character sheet, biases the model toward generating the correct appearance even before face swap

### Consistency Checklist

- [ ] Same character sheet used as reference across all scenes
- [ ] Skin tone consistent (check against neutral lighting reference)
- [ ] Hair color and style match (same highlights, same length)
- [ ] Body proportions consistent (compare standing poses across scenes)
- [ ] Clothing details match the wardrobe spec (no random additions)
- [ ] Face swap applied with consistent masking (same feather radius, same blend mode)
- [ ] Final review: place all scene outputs in a grid and check for any character that "drifts"

## Multi-Shot Narrative Continuity

Producing a coherent multi-shot video sequence (e.g., a 30-second narrative with 4-6 shots) requires a deliberate production strategy. Naive approaches fail predictably.

### Proven Failure Mode: Text-to-Video Stitching

Generating individual shots via text-to-video and stitching them together produces visually disconnected clips. Each generation rolls its own interpretation of lighting, color grade, character appearance, and environment. Even with identical prompt language, text-to-video introduces enough variance that the cuts feel like different films spliced together.

### Working Method: Start-Frame Doctrine + Image-to-Video

The Start-Frame Doctrine (see [cinematic-prompting.md](cinematic-prompting.md)) solves multi-shot continuity. By generating a keyframe image for each shot first, you lock the visual identity, lighting, and color grade before animation. Image-to-video then animates each keyframe while preserving the locked visual properties.

This produces shots that share a coherent visual language because the keyframes were designed together, not independently hallucinated by a video model.

### Multi-Shot Production Workflow

```
Phase 1 — Storyboard
  Define both image_prompt (5-component) and motion_prompt (camera only) per shot.
  The compose-video.py --concept flag auto-generates storyboards via Gemini.

Phase 2 — Keyframe Generation (batch, cheap, fast)
  Generate ALL keyframes for the entire sequence first via Imagen 4.0.
  Generate 4-8 candidates per shot. Select the best.
  Review the full set of selected keyframes AS A SEQUENCE:
    - Consistent lighting direction across shots?
    - Consistent color palette?
    - Character appearance stable?
    - Environment details coherent?
  This review is critical. Fix keyframes before animating.

Phase 3 — Animation (sequential, expensive, slow)
  Feed each approved keyframe into Veo 3.0 image-to-video.
  Motion prompt = camera movement ONLY.
  Budget: ~5-6 Veo generations/day on free tier.

Phase 4 — Assembly
  Stitch shots via ffmpeg or Remotion.
  Apply consistent color grade across all clips.
  Add audio/sound design.
```

### Storyboard Shot Definition

Each shot in the storyboard should define:

```yaml
shot_number: 1
image_prompt: |
  [Subject], [Composition], [Lighting], [Environment], [Technical]
motion_prompt: |
  [Camera movement only — e.g., "slow dolly forward, gentle drift right"]
duration_seconds: 4
transition: "cut"  # or "dissolve", "match-cut"
audio_cue: "ambient rain, distant traffic"
```

### Continuity Techniques

**Keyframe-first review:** The cheapest and most effective continuity tool. Lay out all selected keyframes in sequence order and review them as a filmstrip before spending any video generation budget. Fix lighting, color, and character issues at the keyframe stage where iteration is free.

**Last-frame extraction:** You can extract the last frame of a generated video via ffmpeg (`ffmpeg -sseof -1 -i clip.mp4 -frames:v 1 last_frame.png`) and use it as a reference for the next shot's keyframe. However, image-to-video with a purpose-built keyframe produces better results than last-frame chaining, which compounds drift and artifacts.

**Consistent technical spec:** Use the same film stock, lens, and aspect ratio across all shots in the storyboard. Mixing technical specs (e.g., one shot on "Kodak Vision3 500T" and the next on "ARRI LogC") produces subtle but noticeable visual discontinuity.

**Color grade in post:** Even with consistent keyframes, minor color variations will exist between generated clips. Apply a unified color grade (LUT or manual) across all shots in the assembly phase to smooth these out.
