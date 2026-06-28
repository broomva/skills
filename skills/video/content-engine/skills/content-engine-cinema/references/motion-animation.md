# Motion and Animation

Techniques for adding motion to static frames, transferring motion between subjects, and building multi-shot animated narratives.

## Kling Motion Transfer

Kling's motion transfer is the single most powerful animation technique available today. It takes a reference video as a driving motion source and applies that motion to your character -- zero rigging, zero skeleton setup, zero manual keyframing.

### How It Works

```
Reference Video (driving motion) + Start Frame (your character) → Output Video (your character performing the motion)
```

The model extracts motion information from the reference video (body movement, facial expressions, camera motion) and applies it to the subject in your start frame while preserving the start frame's appearance, lighting, and environment.

### Workflow

1. **Find or record a reference video** -- this is the "motion template"
   - Can be a real person performing the action you want
   - Can be existing footage from any source
   - Duration should be 2-10 seconds (longer clips lose coherence)
   - Clear, well-lit footage works best (the model needs to see the motion clearly)

2. **Prepare your start frame** (see [cinematic-prompting.md](cinematic-prompting.md) for the start-frame doctrine)
   - The character should be in a pose that can plausibly transition into the reference motion
   - If the reference starts with arms at sides, your start frame should show arms at sides
   - Mismatched starting poses produce glitchy transitions

3. **Submit to Kling motion transfer**

**Via fal.ai API:**
```typescript
import { fal } from "@fal-ai/client";

const result = await fal.subscribe("fal-ai/kling-video/v2/master/image-to-video", {
  input: {
    prompt: "natural movement, smooth motion",
    image_url: "https://your-start-frame.png",
    // Reference video for motion transfer
    reference_video_url: "https://your-reference-motion.mp4",
    duration: "5",
    aspect_ratio: "16:9",
  },
});
// result.data.video.url → output video
```

**Via Kling web UI (browser-automated):**
```
1. Upload start frame as "Reference Image"
2. Upload motion video as "Motion Reference"  
3. Set duration and aspect ratio
4. Generate
```

### Motion Reference Library

Build a library of reusable motion references organized by action type:

```
knowledge/raw/motion-refs/
  walking/           # Walking gaits, speeds, styles
  gesturing/         # Hand gestures, pointing, presenting
  turning/           # Head turns, body rotations
  sitting-standing/  # Sit-to-stand, stand-to-sit transitions
  reactions/         # Surprise, laughter, thinking, nodding
  camera-moves/      # Recorded camera movements (dolly, pan, crane)
```

You can record these yourself with a phone -- they do not need to be high production quality. The motion extraction is robust to different resolutions, lighting conditions, and subjects.

### Common Pitfalls

- **Occluded limbs**: If a limb is hidden in the reference video, the model guesses its motion and often gets it wrong. Use reference videos where all relevant body parts are visible.
- **Extreme motion**: Very fast or very large movements (jumping, spinning) can break coherence. Prefer moderate, controlled motion.
- **Background contamination**: If the reference video has a busy background, the model may transfer background motion to your output. Use references with clean or static backgrounds.
- **Scale mismatch**: If the reference subject is much larger or smaller in frame than your start frame subject, the motion may not map correctly. Match framing roughly.

## Wan Image-to-Video Animation

Wan 2.1 is the best model for subtle, natural animation from a start frame. Its strength is environmental motion and gentle camera movement -- the kind of animation that makes a still image feel alive without dramatic action.

### Best Use Cases

- **Environmental animation**: leaves moving, water flowing, clouds drifting, smoke curling
- **Subtle character motion**: breathing, slight head movement, blinking, hair movement in wind
- **Camera moves**: slow dolly, gentle pan, subtle crane up/down
- **Atmospheric effects**: rain, snow, fog movement, light flicker

### Prompt Engineering for Wan

Wan responds well to motion-specific language. The prompt should describe ONLY the motion, not the scene content (the start frame already defines the scene).

**Effective motion prompts:**
```
"slow, gentle camera dolly forward, subtle environmental motion, leaves rustling"
"subject slowly turns head to the left, natural movement, slight breeze moving hair"
"camera slowly pans right, revealing more of the environment, ambient motion"
"rain beginning to fall, droplets hitting surfaces, reflections forming in puddles"
```

**Ineffective motion prompts (re-describing the scene):**
```
"a woman in a coat standing in a rainy street with neon lights"  # This describes the scene, not motion
"cinematic, 4K, professional"  # These are quality tags, not motion descriptions
```

### Via API

```typescript
import { GoogleGenAI } from "@google/genai";
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

// Wan via fal.ai
import { fal } from "@fal-ai/client";
const result = await fal.subscribe("fal-ai/wan/v2.1/image-to-video", {
  input: {
    image_url: "https://your-start-frame.png",
    prompt: "slow dolly forward, subtle atmospheric motion, gentle breeze",
    negative_prompt: "fast motion, sudden movement, jittery, static",
    num_frames: 81,  // ~3.2s at 25fps
    fps: 25,
    guidance_scale: 5.0,
  },
});
```

### Wan Camera Control

Wan supports explicit camera control parameters for precise movement:

| Camera Move | Prompt Pattern | Notes |
|-------------|---------------|-------|
| Dolly in | `"camera slowly moves forward toward the subject"` | Works best with depth in the scene |
| Dolly out | `"camera slowly pulls back, revealing more of the environment"` | Good for establishing shots |
| Pan left/right | `"camera pans slowly to the right, horizontal movement"` | Keep speed slow for best results |
| Tilt up/down | `"camera tilts upward, revealing the sky/ceiling"` | Combine with architectural elements |
| Crane up | `"camera rises slowly, elevated perspective"` | Works well with outdoor scenes |
| Static + subject motion | `"camera is static, subject slowly [action]"` | Explicitly say camera is static |

## Seedance 2.0 Multi-Shot Storytelling

Seedance 2.0 is designed for narrative continuity across multiple video clips. Where other models produce isolated shots, Seedance maintains character identity and scene consistency across cuts.

### Multi-Shot Workflow

```
Shot 1 (establishing) → Shot 2 (medium) → Shot 3 (close-up) → Shot 4 (reaction) → ...
```

Each shot uses the same character reference but different camera angles, actions, and framing.

### Setting Up a Sequence

1. **Create a shot list** (like a traditional film storyboard):

```
Shot 1: Wide establishing - Maya walks into the office, morning light
Shot 2: Medium - She sits at her desk, opens laptop
Shot 3: Close-up - Her face lit by the screen, focused expression  
Shot 4: Over-shoulder - We see what's on her screen
Shot 5: Medium wide - She leans back, satisfied smile
```

2. **Generate start frames for each shot** using the character sheet and scene description method from [realistic-scenes.md](realistic-scenes.md)

3. **Generate each shot with Seedance**, providing:
   - The start frame for that shot
   - The character reference (same for all shots)
   - The motion/action description for that shot
   - The previous shot's output (for temporal consistency)

### Via API

```typescript
// Seedance via fal.ai
const shot1 = await fal.subscribe("fal-ai/seedance/v2/image-to-video", {
  input: {
    image_url: startFrame1Url,
    prompt: "wide shot, woman walks into modern office, morning light streaming through windows",
    character_reference_url: characterSheetUrl,
    duration: "4",
    aspect_ratio: "16:9",
  },
});

const shot2 = await fal.subscribe("fal-ai/seedance/v2/image-to-video", {
  input: {
    image_url: startFrame2Url,
    prompt: "medium shot, same woman sits at desk and opens laptop, natural gesture",
    character_reference_url: characterSheetUrl,
    previous_video_url: shot1.data.video.url,  // temporal consistency
    duration: "3",
    aspect_ratio: "16:9",
  },
});
```

### Continuity Rules for Multi-Shot

- **Character reference must be identical** across all shots. Use the same character sheet URL.
- **Lighting should be consistent** within a scene. If shot 1 has morning window light, shot 5 should too (unless the narrative includes a time change).
- **Wardrobe must match** across shots in the same scene. Generate all start frames with the same wardrobe description.
- **Props and set dressing** that appear in one shot must appear in subsequent shots if the camera angle would reveal them.

## Camera Control Techniques

### Encoding Camera Movement in Prompts

Most video models respond to camera language in prompts, but the specificity and format varies:

**Universal camera terms** (work across most models):
```
"camera moves forward"        → dolly in
"camera moves backward"       → dolly out  
"camera moves to the right"   → truck right / pan right
"camera moves upward"         → crane up / tilt up
"camera orbits around"        → orbital / arc shot
"camera is static"            → locked tripod
"handheld camera"             → slight natural shake
"first person perspective"    → POV
```

**Speed modifiers:**
```
"very slow" / "barely perceptible" → 1-2 degree/second movement
"slow" / "gentle"                  → standard cinematic pace
"moderate"                         → tracking/following pace  
"fast" / "quick"                   → action sequence pace
"whip" / "snap"                    → instantaneous movement
```

### Combining Camera and Subject Motion

When both camera and subject move, state them as separate clauses:

```
"The camera slowly dollies forward while the subject turns to face the camera"
"Static camera, wide shot, as the character walks from left to right across the frame"
"Camera tracks alongside the subject as they walk down the corridor at the same pace"
```

### Virtual Camera Rigs

For more complex camera movements, describe the rig:

```
"Steadicam following from behind, smooth floating movement, 3 feet behind the subject"
"Crane shot starting at ground level, rising 30 feet to reveal the cityscape"
"Dolly zoom (vertigo effect), camera pulls back while zoom pushes in, maintaining subject size"
"360 degree orbit around the subject at eye level, full revolution over 5 seconds"
```

## Chaining and Extending Clips

### Duration Extension

Most models produce 2-8 second clips. For longer sequences, chain clips:

1. Generate the first clip (4 seconds)
2. Extract the last frame of the first clip
3. Use that frame as the start frame for the next clip
4. Repeat until desired duration is reached

```bash
# Extract last frame from a clip
ffmpeg -sseof -0.04 -i clip_01.mp4 -frames:v 1 last_frame.png

# Use last_frame.png as start frame for next generation
```

### Transition Handling

When chaining clips, the cut point between clips may have a slight discontinuity. Smooth it with:

```bash
# Cross-dissolve between clips (0.5 second overlap)
ffmpeg -i clip_01.mp4 -i clip_02.mp4 \
  -filter_complex "[0][1]xfade=transition=fade:duration=0.5:offset=3.5" \
  -y combined.mp4
```

### Frame Interpolation

If the output feels choppy (common with AnimateDiff at low frame counts), add interpolated frames:

```bash
# RIFE frame interpolation (doubles frame rate)
python -m rife_ncnn_vulkan -i input.mp4 -o interpolated.mp4 -m rife-v4.6

# Or via ffmpeg with minterpolate (lower quality but no GPU needed)
ffmpeg -i input.mp4 -vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" output.mp4
```

## Output Specifications

### Format Requirements by Platform

| Platform | Format | Resolution | FPS | Duration | Codec |
|----------|--------|-----------|-----|----------|-------|
| Web (general) | MP4 | 1920x1080 | 30 | Any | H.264 |
| X / Twitter | MP4 | 1920x1080 | 30 | 0:02-2:20 | H.264 |
| Instagram Reels | MP4 | 1080x1920 | 30 | 0:03-1:30 | H.264 |
| TikTok | MP4 | 1080x1920 | 30 | 0:05-3:00 | H.264 |
| YouTube | MP4 | 3840x2160 | 30/60 | Any | H.265 |
| Remotion input | MP4 | Any | 30 | Any | H.264 |

### Preprocessing for Remotion

All AI-generated video clips must be preprocessed before use in Remotion compositions:

```bash
# Ensure compatible codec, frame rate, and container
ffmpeg -i ai_clip.mp4 -c:v libx264 -crf 18 -movflags +faststart -r 30 -pix_fmt yuv420p processed.mp4
```

This ensures:
- H.264 codec (universally compatible)
- CRF 18 (high quality, reasonable file size)
- faststart flag (enables streaming/seeking)
- 30fps (matches Remotion default)
- yuv420p pixel format (required for browser playback)

---

## AI Video Creators distillation (AVCC additions)

> Distilled from the AI Video Creators course (BRO-1525) — see broomva/workspace docs/reference/ai-video-creators-course/. Copy-paste **verbatim motion prompts** live in [`ai-video-prompt-packs.md`](./ai-video-prompt-packs.md).

The sections above cover the *mechanics* of motion (Kling motion transfer, Wan animation, Seedance multi-shot, camera language, chaining). This section adds the AVCC *prompt-discipline* layer — the rules that decide whether a Kling image-to-video generation lands or hangs at 99%. These are model-prompt heuristics, not API mechanics, and they compose with the Kling Motion Transfer and Seedance Multi-Shot sections above (don't re-read them — this layer sits on top).

> **Version note.** Model names below (Kling 1.6 → 3.0, Kling o1, Nano Banana Pro, Seedance 2.0) are pinned to late-2025/early-2026 and **rotate quarterly** — the course itself says model leadership "rotates quarterly." Treat the *tiering logic* (cheaper/faster model ⇒ fewer elements ⇒ simpler prompt) as durable; treat the specific version numbers and credit costs as perishable. When a tier name is stale, map by capability (single-action / few-element / many-element / reasoning / multi-shot), not by number.

### Choose the model BEFORE writing the prompt (the element budget)

The course's load-bearing sequencing rule: **pick the Kling tier first, then write the prompt to fit that tier's element budget.** Prompt complexity is a function of model capacity, not the other way around. Writing a 7-element prompt and then sending it to a fast/cheap tier is the most common self-inflicted failure — the model silently drops or scrambles elements.

An **element** = one noun-bearing thing the model must track and animate: a subject, a distinct action, a key object, a camera move, a lighting condition. (See "Count nouns, not adjectives" below for what counts.)

| Kling tier (rotates) | Element budget | Use for | Prompt discipline |
|---|---|---|---|
| **1.6** (oldest/cheapest) | **1 subject + 1 action** | Single-subject, single-action scenes; minimal context | Keep prompts very simple — one thing moving, one way |
| **2.5 Turbo Pro** (speed-optimized) | **3–4 elements max** | Short streamlined shots where speed/cost matters | Tight, short prompts; compress aggressively |
| **2.6 / 2.6 Turbo** (everyday) | **5–7 elements** | Most scenes — cinematic realism, richer environments, "fast, relatively inexpensive, works for most scenes" | Standard 4-part structure; room for a couple of objects + a camera move |
| **o1** (reasoning model — "the nano banana of video") | **complex / layered / many** | Complex scene logic + physics; **in-video editing** (add/remove objects, change environment/season); Next/Previous Shot continuity | Long, layered descriptions OK; pair with the Constraint Sandwich (below) |
| **3.0** ("the full film studio") | **multi-shot — up to ~6 shots / 15s** | Highest-quality output, multi-shot sequences, talking characters; **Omni** (multi-reference) and `@element` tagging | Define each shot as its own one-camera-move unit; see Seedance Multi-Shot above for the storyboard mindset |

**Why this works:** the failure isn't randomness, it's a budget overrun. A cheaper tier has less capacity to hold elements in coherent relation; an over-budget prompt forces it to gamble on which elements to honor. Matching prompt complexity to tier capacity removes the gamble. (Capability mapping > version number — the *budgets* survive renames; the *names* don't.)

### The 4-part prompt structure: Subject + Action + Context + Style

Every Kling prompt decomposes into four parts. The discipline is that **removing any one part doesn't simplify the prompt — it hands that decision to the model**, which fills the gap with whatever it wants. That gap-filling *is* the "randomness" people blame on the tool.

| Part | What it specifies | Drop it and… |
|---|---|---|
| **Subject** | What actually appears in frame | …the model invents who/what is there |
| **Action** | What moves, and how it moves | …the model picks an arbitrary motion (or none) |
| **Context** | Where and when the scene happens | …the model picks a setting/time of day |
| **Style** | How it's filmed and how it feels | …the model picks a look/grade |

**Short-prompt hierarchy** (when under ~50 words, e.g. for a fast tier): compress, never amputate.

```text
Subject + Action  (never skip these two)
  → Camera behavior
    → minimal Context
      → (optional) Style
```

> "Short prompts don't remove structure — they compress it."

**Why this works:** the model is an executor, not a co-author. Every unspecified slot is a degree of freedom you've delegated. The 4-part structure is just an enumeration of the slots, so "be more specific" becomes a checklist instead of a vibe.

### TTV ≠ I2V: don't re-describe the image

Text-to-video (TTV) and image-to-video (I2V) are **different operations that need different prompts**, and conflating them is a primary cause of bad I2V output.

- **TTV** builds the world from scratch → you must describe *everything* (full Subject + Action + Context + Style).
- **I2V** animates a frame that already exists → the image already *is* the Subject, Context, and most of the Style. Describing them again **fights the image** and creates confusion (the text and the pixels disagree, and the model tries to satisfy both).

**The I2V rule — describe motion only, ~20–40 words.** Answer exactly three questions:

1. **What moves** (and how)
2. **What stays static** (often the camera — say so explicitly)
3. **The motion endpoint** (where the motion lands — see below)

```text
Slow push-in. The subject lifts the cup and brings it to their lips, then lowers it. The camera comes to rest. Everything else stays still.
```

```text
The hand slowly raises the bracelet into the light, turning it once so the gemstones catch the key light, then holds. Camera tracks the hand, then settles.
```

These prompts say nothing about who the subject is, what they're wearing, or the room — the frame already carries all of that. (Contrast with the Wan section above, which makes the same "describe ONLY the motion, not the scene content" point for environmental animation — same principle, applied to I2V character/object motion.)

**Why this works:** the uploaded image is a hard constraint the model honors at high weight. Text describing the same content is a *competing soft constraint*. Keeping the text to pure motion lets the image own appearance and the text own movement — no contradiction to resolve.

### Motion must have an endpoint (the 99% hang)

> **Every motion must start, progress, and stop.**

Open-ended motion is the single most-cited cause of the infamous **Kling 99% hang** — the generation stalls at 99% because "Kling doesn't know when to stop." If you tell it the camera "moves forward" or the subject "is dancing" with no terminus, the model has no defined end state and chokes trying to find one.

The fix is to give every motion a **landing point**:

```text
# Hangs — open-ended:
The camera pushes in toward the subject.

# Lands — has an endpoint:
The camera pushes in toward the subject, then comes to rest in a tight close-up.
```

```text
# Hangs:
She walks down the corridor.

# Lands:
She walks three steps down the corridor and stops at the door, hand on the handle.
```

**Why this works:** a diffusion-video model is interpolating toward a coherent final frame. "Motion with no endpoint" is an ill-posed target — there's no last frame to converge on. Naming the end state turns an open interval into a closed one the model can actually render.

### One shot = one camera move; more motion = shorter shot

Two coupled rules that govern shot construction (they extend the Camera Control Techniques section above, which catalogs the *vocabulary* — this is the *budget* on using it):

- **One shot = one camera move.** Mixing multiple camera movements in a single prompt breaks spatial consistency. If you need a push-in *and* a pan, that's **two shots**, generated separately and cut together. A camera line is "one line = one movement = one shot."

```text
# Breaks spatial consistency — two moves in one shot:
The camera pushes in while panning right and craning up over the crowd.

# Stable — split into single-move shots:
Shot 1: Slow push-in toward the player, locked otherwise.
Shot 2: Static wide, camera pans right across the crowd.
```

- **The more the camera moves, the shorter the shot must be.** Movement and duration trade off. Static/locked shots survive the longest (good for ~8s); a tracking shot is reliable for roughly half that; complex moves should be kept very short. Long + complex = broken generation.

| Camera behavior | Reliable max duration | Notes |
|---|---|---|
| Static / locked | longest (~8s) | Let the *subject* carry the motion |
| Slow push-in / pan | medium | Single axis, slow |
| Tracking / following | ~half of static | One subject, steady pace |
| Orbit | short — **slow only** | Fast orbit warps geometry |
| Handheld | short — specify "controlled/steady" | Don't combine with other moves; becomes jitter fast |
| Complex / combined | very short or split | Prefer splitting into single-move shots |

**Why this works:** every frame of camera motion compounds the model's prediction error (geometry, parallax, occlusion all have to stay consistent across more change). Duration multiplies that error budget. Static-camera + subject-motion concentrates the hard prediction into one moving thing instead of the whole frame.

> "Cinematic camera" is **not** an instruction — it specifies no move. Use a concrete move (push-in, pan, tracking) or the model picks for you. (Same point the universal camera-terms table above makes; the AVCC framing is that *vagueness is delegation*.)

### Count nouns, not adjectives (the overload rule)

The #1 video-prompt failure is **overload** — too many distinct things for the model to track. The diagnostic is precise:

> **Count nouns, not adjectives.** Adjectives are free; nouns cost budget.

A heavily-described single object ("a battered, rain-soaked, neon-lit vintage leather jacket") is *one* noun — cheap. Five plainly-named objects ("a jacket, a phone, a dog, a bicycle, a sign") is *five* nouns — expensive, and likely over budget for anything below the o1/3.0 tier.

**The fix when over budget: compress objects into categories.** Kling understands categories; don't micromanage every object.

```text
# Over budget — 6+ tracked nouns:
A man holding a phone, a coffee cup, a newspaper, and keys, next to a dog, a bicycle, and a parked car.

# Compressed into categories:
A man holding a phone, surrounded by everyday street clutter, a dog at his feet.
```

**Why this works:** each noun is an entity the model must instantiate, place, and keep coherent across frames. Adjectives modify an entity already in the budget — they add detail, not load. Categories ("street clutter", "a crowd of fans with flags") let the model fill a region stochastically instead of tracking N discrete objects, which is exactly what it's good at.

### The 5 predictable failure causes

The course's framing: **"These aren't bugs, they're predictable mistakes."** When a Kling generation comes back wrong, it is almost always one of these five — check them in order:

1. **Too many elements** — over the tier's element budget (→ pick a higher tier, or compress nouns into categories).
2. **Missing camera guidance** — no camera line, so the model chose the move for you (→ add one explicit, single move).
3. **Innocent words trigger filters** — an ordinary word reads as policy-sensitive and the gen is silently degraded or refused (→ rephrase the trigger word).
4. **Open-ended motion** — no endpoint → the 99% hang (→ give the motion a landing point).
5. **Vague spatial language** — "near", "around", "behind" without a clear anchor → the model guesses placement (→ name explicit spatial relationships).

**Why this works:** it converts "the AI is random" into a five-item triage list. Every failure maps to a specific, reversible prompt edit, so debugging is mechanical instead of superstitious.

### Explicit negative constraints

State what must **not** happen — negatives are as load-bearing as positive instructions. Kling will add objects, motions, or behaviors on its own; a negative prompt (or an inline negative clause) is how you suppress them. This is especially critical for the o1 reasoning model and any edited/integrated frame, where the model has more latitude to "improve" the scene.

```text
No tongue movement. No tongue flicking. The snake does NOT stick out its tongue at any moment. The mouth remains closed. No aggressive or animalistic behavior.
```

```text
negative: fast motion, sudden movement, jittery, camera shake, extra people, text on screen, warped hands
```

**Why this works:** generative models default to a learned prior (snakes flick tongues; crowds appear; hands gesture). The positive prompt can't always override a strong prior by omission — you have to name the prior and forbid it. Negatives are how you delete from the model's defaults. (This is the same lever the Master Synthesis calls one of the "five universal control levers" — it applies across both image and video.)

### The reverse-motion enter-frame trick

A workaround for a genuinely hard problem — getting a *specific* hero to **enter** an initially-empty frame (models are bad at materializing a controlled subject into a clean scene):

1. Generate a clip where the character **walks out of frame** (or prompt "exits walking backward").
2. **Reverse the clip in editing.**
3. The character now appears to **walk into** an initially-empty frame.

```text
# Generate this (easy for the model):
The football player walks out of frame to the left, leaving the empty stadium.

# Then reverse in CapCut/ffmpeg → he walks INTO the empty stadium.
```

```bash
# Reverse a clip with ffmpeg (video only; add areverse for audio):
ffmpeg -i exit_clip.mp4 -vf reverse -an enter_clip.mp4
```

**Why this works:** "subject exits a populated frame" is an easy, well-supported generation (the model starts from a fully-specified frame and removes the subject — a downhill task). "Subject enters an empty frame" is uphill (the model must invent and place a specific controlled subject mid-shot). Reversing the easy direction gives you the hard result for free. The course also frames this as a mindset: *"trains you to see video from end to beginning."*

### The Constraint Sandwich (Anchor → Action → Constraints)

The stabilizing structure for advanced/edited generations — especially **Kling o1** in-video editing, where the model is allowed to change the scene and will over-reach without guardrails:

> **Anchor → Action → Constraints**

- **Anchor** — name the hero element that must persist (the subject of the edit).
- **Action** — what happens / what changes.
- **Constraints** — what must **NOT** change (lighting, set design, wardrobe, background, etc.).

```text
Our football player (element one) scores a goal — preserve the lighting and do not change the stadium design.
```

```text
Anchor: the white snake wearing the diamond bracelet.
Action: the hand slowly lifts; the snake rises with the hand, moving with its whole body.
Constraints: do not change the lighting; keep the dark background; mouth stays closed; no extra objects.
```

**Why this works:** an editing/reasoning model treats the whole frame as mutable by default. The sandwich pins the two ends — *this stays (Anchor), this is fixed (Constraints)* — and confines change to the middle (Action). It's the negative-constraint lever applied at scene-composition scale: you're telling the model the boundaries of its edit, not just its content. (Composes with the element-budget rule: the Constraints clause adds elements, so keep the total within the chosen tier's budget.)

### Cross-reference map

| AVCC rule above | Builds on (existing section) |
|---|---|
| Element budget / model-first | Kling Motion Transfer; Seedance 2.0 Multi-Shot |
| Describe motion only (I2V) | Wan Image-to-Video ("describe ONLY the motion") |
| One shot = one camera move | Camera Control Techniques (the move vocabulary) |
| Multi-shot tier (3.0) | Seedance 2.0 Multi-Shot Storytelling (storyboard mindset) |
| Reverse-motion trick / endpoints | Chaining and Extending Clips (last-frame chaining) |
| Negative constraints | Wan `negative_prompt` usage; output discipline |
