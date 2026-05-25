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
