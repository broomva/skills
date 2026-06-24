# AI Video Prompt Packs + Prompt-Craft Laws

> Distilled from the AI Video Creators course (BRO-1525) — see broomva/workspace docs/reference/ai-video-creators-course/.

A copy-paste prompt library plus the transferable laws of prompt craft for AI image and video generation. Pull exact prompts from §3–§8; pull the reasoning from §1–§2. Every prompt is reproduced VERBATIM in fenced code blocks so an agent can lift it without re-deriving it.

**Version note:** Model names in this file (Kling 1.6→3.0, Nano Banana Pro, Seedance 2.0, Veo 3.1, Minimax Hailuo 2, Avatar 3/4/5) were current late-2025/early-2026. They rotate fast — the course itself says model leadership "rotates quarterly." The **prompt structure and craft laws are durable**; treat the exact version strings as swap-in slots, not load-bearing.

---

## 1. The prompt-craft laws (the transferable core)

> **Self-contained quick reference.** These laws are restated tersely here so you can pull prompts and rules from this one file. The *canonical deep treatment* (full reasoning + tables) lives in [`cinematic-prompting.md`](./cinematic-prompting.md) and [`motion-animation.md`](./motion-animation.md) (their AVCC sections). This file owns the **verbatim packs** (§3+); those files own the depth.

These are the rules that survive model churn. A prompt is a **technical brief**, not a wish — you are the director, DP, gaffer, and stylist at once. Think like a creative director, not a casual user.

### 1.1 The image master formula

```
SHOT + LENS + LIGHT + TEXTURE + COMPOSITION + STYLE REFERENCE  (+ EMOTIONAL VISION)
```

Use it as a checklist every time. A professional prompt is **layered, not short** — each layer adds precision. The seven brief blocks, expanded:

| Block | What it controls | Anti-pattern it fixes |
|---|---|---|
| Subject & action | exactly who is in frame + what they do (write it like a character in a book) | "a happy person" |
| Camera & shot type | emotion + storytelling | unspecified framing |
| Lens & focal length | perspective, space compression, subject isolation | flat/random depth |
| Lighting | source + direction + quality + color temperature | the "default flat AI light" |
| Material & texture | defeats the "plastic AI look" | waxy skin, plastic surfaces |
| Composition | guides the viewer's eye | centered-by-default mush |
| Style reference | anchors the image in a known visual universe | "make it cinematic" |

**Why this works:** the models were trained on photography and film, so they respond to the actual vocabulary of those crafts. Each block maps to a real production decision the model already has training signal for.

### 1.2 Use technical language, not feelings

> **AI understands parameters, not feelings.**

Do this:
```
85mm portrait, f/1.4, soft side lighting, warm 3200k tones
```
Not this: "moody portrait." Translate every emotion into a parameter — the emotion is *yours*, the parameter is the model's.

### 1.3 Nano Banana Pro prompt order

```
1. Object   (most important element)
2. Context / Environment
3. Technical settings   (lens, lighting, mood)
```

**Why this works:** Nano Banana Pro does "reasoning-based generation" / Spatial Intelligence — it builds a 3D understanding of the scene before drawing. Leading with the object anchors that reasoning on the hero, so context and physics resolve around it instead of competing with it.

### 1.4 The Kling video formula

```
Subject + Action + Context + Style
```

- **Subject** = what actually appears.
- **Action** = what moves and how.
- **Context** = where and when.
- **Style** = how it's filmed and how it feels.

Remove any part → the model fills the gap on its own → randomness begins. Kling doesn't guess; it follows instructions. "Random" failures are almost always a missing part of this formula.

**Short-prompt priority (under ~50 words):** Subject + Action (never skip) → camera behavior → minimal context → optional style. "Short prompts don't remove structure — they compress it."

### 1.5 The motion law (image-to-video)

Answer three things in ~20–40 words:

```
WHAT moves  +  HOW it moves  +  HOW the camera behaves
```

Hard rules:
- **Do NOT re-describe the image.** Text-to-video (TTV) builds the world from scratch; image-to-video (I2V) animates what already exists. Re-describing the uploaded image is the #1 cause of bad I2V output.
- **Every motion needs an endpoint.** Open-ended motion is the infamous **99% hang** — Kling doesn't know when to stop. Every motion must start, progress, and stop.
- **One shot = one camera move.** Mixing moves in one prompt breaks spatial consistency → split into separate shots.
- **The more the camera moves, the shorter the shot.** Static ≈ longest; tracking ≈ ~2× shorter; complex moves = very short or broken.
- **Count nouns, not adjectives.** Overload (too many objects) is the top failure — compress objects into categories; Kling understands categories, don't micromanage every object.

### 1.6 The five universal control levers

True across image *and* video, across every model:

1. **Camera language = realism.** Naming real bodies/lenses/apertures (Sony A7R V, Hasselblad H6D, ARRI ALEXA 35, RED KOMODO 6K) deterministically shifts lighting, depth, and grade — because the models were trained on photography. (See the cheat sheet in §2.)
2. **References > prompts.** Control comes from reference images (OmniReference / Kling Elements / a collage), not "the perfect words." In Seedance, references give ~80% of control.
3. **Negative constraints.** State what must NOT happen ("no tongue flicking, mouth closed", "NO UI, no plastic skin"). As important as the positive instructions — for motion control AND for realism.
4. **Physics must be explicit.** For integration: weight, gravity, contact shadows, indentation, reflections — or objects float.
5. **Deliberate imperfection = realism** (UGC). "Shot on iPhone," uneven exposure, sensor noise, horizon tilt, natural blink/breath. Perfection reads as fake.

### 1.7 The universal generator model

```
PROMPT → MODEL → CONTROLS → RESULT
```

If the output is wrong, adjust **one of the three layers** — don't ask "why did it give me a weird result?" Ask "which model is best for this task, and which controls do I adjust?" Every new tool just hides the same four building blocks somewhere different; find them, don't relearn from scratch.

**Save-for-repeatability:** `SAVE = prompt + model + settings + seed`. This single habit converts a lucky result into a client-grade repeatable system. Lock a seed for a consistent campaign look; nudge it slightly for variations on the same scene.

### 1.8 JSON support by model

| Model | JSON prompting | Notes |
|---|---|---|
| **Nano Banana Pro** | Yes | Best for structured/illustration/3D-toon/repeatable variations |
| **Kling** | Yes | Modern model, understands JSON well |
| **Veo** | Yes | JSON-friendly |
| **Sora** | Yes | JSON-friendly |
| **Midjourney** | **No** | Plain text only — works via OmniReference + a few params |

JSON works best for structured images (illustration, toon shading, 3D-inspired art) and for repeatable variations within one visual system. Build it fast by pasting the template (§3.6) into ChatGPT and using voice input to fill each block.

### 1.9 The control hierarchy for making video

```
Text → Video           (least control — random character; avoid for brand work)
Image + Text → Video   (RECOMMENDED — full control over character/style)
Image → Image transition (most powerful — for time/age/emotional change between two frames)
```

Image fidelity caps video fidelity: "if the image isn't real, the video never will be." Invest the realism budget at the image stage; upscale before animating.

---

## 2. Camera-model → look cheat sheet

Drop one of these strings into any image prompt to deterministically set the look. This is lever #1 (§1.6) made concrete.

| Prompt text to include | Visual result |
|---|---|
| **ARRI ALEXA 35** | Cinematic, soft depth, natural color grading |
| **Hasselblad H6D** | Premium high-end close-ups, rich macro detail |
| **RED KOMODO 6K** | True cinematic, film-like look |
| **Sony A7R IV** (or A7R V) | Ultra-realistic, high-detail |

Companion lens/body anchors seen in the verbatim packs: `Zeiss Supreme Prime lens, 85mm, f1.8` (beauty portrait) · `Hasselblad H6D-100c, 100mm macro lens, f/8, ISO 100, 1/125` (luxury product) · `Sony A1, 85mm f1.4 lens, at f1.6, ISO 100, 1/200` (the upscale recipe) · `35mm anamorphic lens, shot on Arri Alexa` (anamorphic cinema look) · `85mm prime lens, f/1.8, shot on Sony A7R IV` (National Geographic macro).

### Lens / focal-length psychology

| Focal length | Character |
|---|---|
| 14–24mm (ultra-wide) | Dramatic, distorted, exaggerated space, more environment |
| 24–35mm (wide) | Lots of environment, natural dynamism |
| 35–50mm (standard) | Human-eye perspective |
| 85–135mm (portrait) | Flattering compression, subject isolation |
| 200mm+ (telephoto) | Extreme compression, flattened backgrounds |

Short lenses exaggerate space + include more environment; long lenses compress space + isolate the subject.

---

## 3. Image prompt packs (VERBATIM)

### 3.1 Director-level "good prompt" (the reference standard)

```
Motocross rider mid-lean on a dirt track, captured in gritty 90s analog style,
vertical black and white frame with strong motion blur,
shot handheld with a 35mm lens at f/2.8, 1/33 of a second, ISO 400,
flat overcast daylight, diffused shadows, helmet highlights softly blown out,
granular dirt with lateral dust streaks, styled like vintage Marlboro campaigns,
evoking raw speed and unpolished realism.
```

**Why this works:** every block of the master formula (§1.1) is present — subject+action, style era, format, lens+aperture+shutter+ISO, light quality, texture, style reference, emotional vision. Nothing is left for the model to invent.

### 3.2 Style-decision prompt (vs "cinematic lighting")

```
muted blue-gray palette, matte textures, soft haze, asymmetrical composition, gritty editorial mood, 35mm lens
```

### 3.3 Composition-directed example

```
A wide shot of a sports car parked under neon signs at night,
framed with leading lines that guide the eye into the distance.
```

### 3.4 Style-reference example

```
Cinematography inspired by Roger Deakins in Blade Runner 2049, teal and amber palette, haze, hard rim lights.
```

### 3.5 Reusable templates with [variables]

Homework master-prompt structure (a fill-in scaffold):
```
"Medium shot of [subject] doing [action], shot on [lens] at [aperture], [camera angle].
[Lighting description: source + direction + quality + temperature].
Detailed textures on [key materials]. [Composition choice] with [note about negative space or depth].
Styled like [described visual reference], evoking [emotional intention]."
```

Expert-portrait template (Advanced Option A — a sellable "Prompt System" you hand a client):
```
"Centered close-up portrait of [type of expert] in [environment], shot on [lens] at [aperture],
[lighting description], [composition note], with [style reference], evoking [emotion]."
```

Lens & Lighting Test Grid — 4 controlled variants (Advanced Option B):
```
Version 1: 35mm, soft daylight, side-lit
Version 2: 85mm, warm tungsten, Rembrandt lighting
Version 3: 24mm wide, hard neon light
Version 4: 50mm, backlit, rim light halo
```

### 3.6 JSON prompt template (Nano Banana Pro / ChatGPT / Kling / Veo / Sora — NOT Midjourney)

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

### 3.7 Camera-settings looks (drop-in style blocks)

Anamorphic cinema-lens style:
```
Shot on 35mm anamorphic lens, f/2.8, cinematic bokeh, subtle motion blur,
slight film grain, chromatic aberration, warm color grading, shot on Arri Alexa
```

National Geographic / macro style:
```
Macro photography, 85mm prime lens, f/1.8 aperture, sharp focus on skin
textures and condensation droplets, global illumination, high dynamic range (HDR),
incredibly detailed pores, shot on Sony A7R IV.
```

---

## 4. Base-character identity-lock pack (VERBATIM)

The hero portrait is the visual anchor — generate it FIRST, then reuse it as a reference everywhere. This is THE character-consistency mechanism. Target: Nano Banana Pro, 9:16, 2K.

```
Ultra-realistic beauty portrait, chest-up framing, frontal eye-level view, centered composition for identity lock.
Young woman with very light porcelain skin, soft warm-neutral undertone, natural skin texture with subtle micro-details.
Facial structure: high cheekbones, symmetrical face, narrow straight nose, soft defined jawline.
Eyes: light grey-green eyes, sharp focus, clean natural eyelashes.
Eyebrows: very light blonde, almost invisible, minimal definition.
Hair: platinum blonde, slicked back tightly, center part, clean styling, no loose strands.
Lips: natural nude soft pink lips, slightly glossy, medium fullness.
Expression: neutral, calm, confident, direct eye contact.
Lighting: soft studio beauty lighting, large diffused key light from front, subtle fill to remove harsh shadows, clean commercial skin rendering.
Background: pure white seamless studio background, no texture, no gradients.
Camera: shot on Sony A7R V, Zeiss Supreme Prime lens, 85mm, f1.8 cinematic depth of field.
Focus: ultra sharp focus on eyes and facial features, background slightly soft.
Color: clean neutral tones, natural skin color, no stylization.
Composition: centered framing, minimal negative space, no distractions.
```

**Why this works:** it splits Fixed DNA (face structure, eye color, skin) from the technical/lighting block, so the DNA section can be copy-pasted verbatim on every future generation while only outfit/location/pose change. "Frontal eye-level, centered, for identity lock" gives the model the cleanest possible anchor to reproduce.

### Character Master Prompt structure (the "digital passport")

```
Fixed DNA (never changes)  +  Variable Context (changes every post)
```
- **Fixed DNA:** face description · age / ethnicity / skin type · identifying details (moles, scars, texture). Copy-paste verbatim every time.
- **Variable Context:** outfit · location · lighting · pose. Edit per post.

Rule: **1 account = 1 character.** Change everything except the DNA. Download/store your hero images locally — tools change, local files keep the character forever.

### UGC base identity — blend two faces into a new fictional person (VERBATIM)

For synthetic influencers where you must NOT resemble any real source. Use only as "genetic inspiration."

```
Create a photorealistic image of a completely new fictional adult human identity generated from ***TWO*** reference individuals, using the references only as subtle genetic inspiration rather than direct likeness: blend distinct but believable facial structure elements such as almond-influenced eye shape, balanced brow geometry, natural nose bridge with a softly defined tip, realistic lip proportions, gently placed cheekbones, an organic jawline contour, mild facial asymmetry, realistic skin undertone, natural pores, fine skin texture, tiny expression lines, and believable bone-structure transitions into one cohesive person who does not strongly resemble any single source. Frame the subject in a natural medium shot from mid-torso upward, standing or seated casually in a realistic modern living room, captured like an authentic creator-style smartphone photo, eye-level camera angle, relaxed posture, calm everyday expression, direct but unforced presence, minimal foreground obstructions, clean lived-in background with a sofa, soft textiles, a small side table, books, plants, and subtle household details, clear subject separation without artificial blur. Use natural daylight from a nearby window mixed with soft practical home lighting, true-to-life color response, neutral warm skin tones, gentle ambient shadows, no dramatic contrast, no stylized editorial lighting. Shot on a modern smartphone main camera, 26mm equivalent lens, realistic depth of field, slight lens imperfection, mild edge softness, subtle sensor noise, candid UGC realism, anatomically accurate face and body proportions, realistic hairline and neck anatomy, natural clothing in a simple casual outfit such as a soft cotton T-shirt or knit top in muted neutral tones. Avoid morphing artifacts, feature-averaging softness, uncanny symmetry, waxy skin, overly perfect beauty retouching, artificial compositing cues, cinematic staging, glam lighting, exaggerated bokeh, face-swap look, duplicate identity resemblance, distorted eyes, melted features, mismatched lighting, or plastic skin.
```
> If you attach more references, change the number word ("TWO") in the text to match.

**Why this works:** "genetic inspiration not direct likeness" + the long negative tail (no morphing/averaging/uncanny-symmetry/face-swap-look) steers away from the two failure modes of multi-reference blends — averaging into mush, or copying one source too closely.

---

## 5. Image-to-image product-integration pack (VERBATIM)

Merges a generated subject with REAL product photos. Target: Nano Banana Pro, image-to-image with 3 refs. The 1.5M-view white-snake-with-diamonds commercial used exactly this.

```
Base reference image 1 as the base subject: a realistic white snake, same pose, same composition, same lighting direction.
Apply jewelry from reference image 2 and reference image 3 onto the snake.
Jewelry integration: jewelry from reference 2 around the upper neck of the snake, naturally hanging with gravity; jewelry from reference 3 wrapped along the middle and lower coils, following the curvature.
The jewelry must naturally follow the anatomical curves precisely, no floating elements.
Physical realism: realistic weight distribution; natural gravity behavior; slight indentation of scales under jewelry; accurate contact shadows; reflections of diamonds and metal on snake skin.
Lighting: soft studio lighting, soft key light from front-left, subtle fill light, clean specular highlights on diamonds.
Camera: Hasselblad H6D-100c, 100mm macro lens, aperture f/8, ISO 100, shutter 1/125.
Focus: ultra sharp on jewelry and snake head, slight falloff toward background.
Style: luxury jewelry product photography, Cartier / Tiffany level, ultra clean, high contrast, dark elegant background. Ultra photorealistic, macro detail, sharp gemstones, no distortion, no extra objects.
```

**Why this works:** it makes the physics explicit (lever #4) — weight distribution, gravity, scale indentation, contact shadows, reflections — which is the difference between jewelry that *sits on* the subject and jewelry that floats. The "no floating elements / no extra objects" negatives kill the two most common integration glitches.

### Hero-into-scene integration (image-edit, Nano Banana Pro stage)

```
Add a textured bearded football player with tattoos, warming up on the field in a real Madrid kit. Add crowds of fans to the stadium with flags of different countries.
```

### Brand-ad hero portrait (Oakley example, Nano Banana Pro)

```
A rugged downhill rider, 50 plus gray beard, wearing a helmet and Oakley Juliet glasses. Sunrise in the mountains, a winding mountain road reflected in the lenses. Close up portrait, cinematic lighting.
```

### Hybrid-reality face swap (Nano Banana Pro)

Screenshot a real video → upload → instruct the model to replace only the face with your character. Real environment + clothes + AI face = the easiest believable integration. The course gives this as a spoken instruction, not a fixed prompt — **illustrative paraphrase (author-composed, not a verbatim course prompt):**
```
Replace only the face with the character from reference image 1, preserve identity and facial structure, keep the original environment, clothing, lighting and pose unchanged.
```

---

## 6. Motion / animation pack (VERBATIM, strict negatives)

Target: Kling 3.0, 1080p, 15s or 5s. The animation companion to the §5 integration.

```
Slow motion. Subject lock on the bracelet. The camera smoothly tracks the hand, following the jewelry.
The hand slowly lifts upward. The snake gently rises with the hand, following the bracelet.
The snake moves with its entire body, natural, continuous, elegant motion — not only the head.
No tongue movement. No tongue flicking. The snake does NOT stick out its tongue at any moment.
The mouth remains closed. No aggressive or animalistic behavior.
Calm, controlled, luxury motion. The snake behaves like a refined, symbolic form — elegant, smooth, cinematic.
```

**Why this works:** WHAT moves (hand + snake body) + HOW (slowly, with the whole body) + camera behavior (smooth tracking) — the motion law (§1.5) in three lines. Then the negative block ("no tongue, mouth closed, no aggression") locks down the model's most likely off-script behaviors. If motion breaks or morphs, simplify to **one camera move + one subject move** at a time.

### Camera line templates (one line = one movement = one shot)

```
Static wide shot, locked camera
Slow push-in toward the subject
Tracking shot following the subject from the side, smooth and steady
```

Stable move vocabulary: static/locked · slow push-in · pan · tracking · aerial/top-down. Use carefully: **orbit** (slow only — fast orbit warps) and **handheld** (specify "controlled/steady handheld"; don't combine with other moves or it becomes jitter). "Cinematic camera" is NOT an instruction.

### Constraint Sandwich (Kling o1 / advanced stability)

```
Anchor → Action → Constraints
```
Example: *"our football player (element one) scores a goal — preserve the lighting and do not change the stadium design."* Tells the model what must NOT change, which stabilizes edited/advanced generations.

### Text-to-video motion examples (VERBATIM)

```
Time-lapse video, a stadium filling with a massive crowd of fans with flags from different countries, a noisy and cheerful crowd taking all the seats.
```
```
A drone flight over shouting crowds of fans, just like at a real match.
```
```
Smooth zoom out from the football player warming up on the field to the stadium.
```
```
Time-lapse video of decades flying by. This football player plays football, slowly aging, running back and forth with his team, practicing, laughing, hugging fans, the stands empty and then fill up, showing the endless cycle of games and the years our hero has gone through.
```

---

## 7. Lip-sync recipes (VERBATIM)

Lip sync is no longer hard: Kling 3 / Grok do it with minimal prompting given a clean face + clear speech. **Input quality defines output quality** — clean face + clear speech beats clever prompting. The dialogue goes at the end after `says clearly:`.

### 7.1 Kling 3 — Selfie Vlog (bedroom, 3s)

```
Handheld selfie video, vertical framing, realistic social-media style, 3 seconds. A young woman matching the reference image, with long dark hair, natural skin texture, minimal makeup, wearing a gray long-sleeve knit sweater, sits in a sunlit bedroom with an unmade bed, pillows, a bedside table, and a casual lived-in home atmosphere. She holds the phone at arm's length in a casual selfie angle while facing the camera. Natural daylight, soft indoor brightness. Subtle handheld motion, gentle natural body movement, natural blinking, realistic breathing, accurate lip sync, authentic facial micro-expressions. Keep the framing close-up to medium close-up, realistic smartphone front-camera optics, clean natural realism, no text on screen, no cuts, no filters, no exaggerated beauty retouching. She looks toward the camera and says clearly: "Hi everyone. I heard that you had some questions regarding lip-syncing."
```

### 7.2 Kling 3 — Gym Locker Room (4s)

```
Handheld selfie video, vertical framing, realistic social-media style, 4 seconds. A young woman with long dark hair, natural skin texture, minimal makeup, wearing a dark gray sports bra and black high-waisted leggings, stands in a gym locker room with beige lockers, wooden benches, bright overhead lights, and a large mirror. She holds the phone at arm's length in a casual selfie angle. Bright indoor lighting, clean fitness-club atmosphere, slightly post-workout look. Subtle handheld motion, gentle natural body sway, natural blinking, realistic breathing, accurate lip sync, authentic facial micro-expressions. She keeps her eyes focused on the phone screen the entire time and does not look away from it. Keep the framing close-up to medium close-up, realistic smartphone front-camera optics, clean natural realism, no text on screen, no cuts, no filters, no exaggerated beauty retouching. She says clearly: "In fact, lip-sync works perfectly even with minimal prompting.."
```

### 7.3 Kling 3 — Minimal Studio, walking forward (3s)

```
Handheld selfie video, vertical framing, realistic social-media style, 3 seconds. A young woman with long dark hair, natural skin texture, minimal makeup, wearing a fitted gray sleeveless top and black high-waisted leggings, is in a clean minimal studio space with a plain light-gray background. She holds the phone at arm's length in a casual selfie angle while moving slowly forward. Soft indoor studio lighting, clean neutral brightness, no breeze. Subtle handheld motion, gentle walking bounce, natural blinking, realistic breathing, accurate lip sync, authentic facial micro-expressions. Keep the framing close-up to medium close-up, realistic smartphone front-camera optics, clean natural realism, no text on screen, no cuts, no filters, no exaggerated beauty retouching. She looks toward the camera and says clearly: "You can do this in Kling 3.."
```

### 7.4 Kling 3 — Themed Room, walking forward (7s)

```
Handheld selfie video, vertical framing, realistic social-media style, 7 seconds. A young woman with long dark hair, natural skin texture, minimal makeup, wearing a brown-and-beige Jedi-style robe costume, stands in a cozy Star Wars-themed room with shelves displaying sci-fi collectibles, a Stormtrooper helmet, warm practical lamps, and subtle fan-decor ambiance. She holds the phone at arm's length in a casual selfie angle while walking slowly forward. Warm indoor lighting, soft balanced brightness, slight natural movement in her hair. Subtle handheld motion, gentle walking bounce, natural blinking, realistic breathing, accurate lip sync, authentic facial micro-expressions. Keep the framing close-up to medium close-up, realistic smartphone front-camera optics, clean natural realism, no text on screen, no cuts, no filters, no exaggerated beauty retouching. She looks toward the camera and says clearly: "See? It works quite well. I'll leave all the prompts down below. And yes- while I'm at it- Happy Star Wars Day!"
```

### 7.5 Grok — Walking Vlog (backup / variation)

```
A young woman walks along, filming a vlog, and says, "But you can also give Grok a try."
```

### 7.6 Beat-timed lip sync (dictate exact word rhythm)

Extreme close-up, lower-half-of-face shot with explicit `(pause)` markers and articulation constraints:
```
Extreme close-up video, 3 seconds, realistic cinematic beauty-detail shot, designed as a seamless continuation of the previous clip. Frame only the lower half of a young woman's face, focusing tightly on her lips, part of her nose, and surrounding natural skin texture. Soft natural-looking light, visible pores, realistic lip texture, subtle skin detail, shallow depth of field, clean background blur. She speaks with accurate lip sync in this exact rhythm: "and" (pause) "so" (pause) "much" (pause) "more". Each word is spoken separately, with a short noticeable beat of silence after it. Her mouth does not open wide; lip movement stays controlled, subtle, and precise. The lips move slowly and expressively, with a soft, intimate, sensual articulation style, but still natural and realistic. Minimal movement besides the lips and slight natural breathing, tiny micro-movements around the mouth, no exaggerated jaw opening, no broad facial motion. Clean cinematic realism, no cuts, no text on screen, no filters, no exaggerated beauty retouching.
```

**Why these work:** the shared scaffold (handheld selfie · vertical · "X seconds" · subject + clothing + location · "phone at arm's length" · the micro-realism stack of blink/breath/micro-expressions · the negative tail of `no text/cuts/filters/beauty-retouching` · `says clearly: "..."`) is reusable across every line — swap location, outfit, duration, and dialogue. The micro-realism stack and negatives are what keep it from reading as AI.

### 7.7 "Seamless continuation" UGC (split one script across shots)

Bake the script across multiple scenes by matching framing/eyeline/lighting and writing each clip "as a seamless continuation of the previous clip." Example continuation line:
```
Vertical talking-head video, 3 seconds, realistic creator-studio style, designed as a seamless continuation of the previous clip. The same young woman with long dark wavy hair, natural skin texture, stands or sits centered in front of a modern shelf setup with soft teal and warm orange practical lighting, camera gear, books, and a glowing AVCC sign in the background. Keep the same camera framing, body position, eye line, lighting, and overall visual continuity as the previous shot so it feels like the next sentence in the same take. She continues speaking naturally, as if mid-thought, with smooth conversational timing and accurate lip sync, saying: "and make thousands of dollars online. Inside AI Video School, you get the full system to create influencers like me that brands actually pay for.". Natural hand gestures continue from the previous moment, with subtle finger movement, small head motion, realistic blinking, breathing, and authentic facial micro-expressions. Clean cinematic realism, realistic smartphone or mirrorless talking-head look, no cuts, no text on screen, no filters, no exaggerated beauty retouching.
```

### 7.8 POV selfie + negatives (Hogwarts hackathon — multi-reference identity lock)

```
dark wizard teacher entering a magical classroom full of students in hog Hogwarts , use the face from reference image 1 exactly, preserve identity and facial structure, use the full outfit from reference image 2 exactly, no changes to clothing, POV selfie perspective, camera is the viewer, the character is filming himself, close to medium selfie framing, students visible behind him, shot on iPhone 17 Pro Max, natural indoor lighting, slightly uneven exposure, realistic shadows, authentic classroom atmosphere, students slightly out of focus in background, NO visible phone, NO UI, NO overlays, NO recording interface, NO third person perspective, natural imperfect framing, realistic vlog feel
```

**Why this works:** "camera is the viewer / character is filming himself" + the `NO visible phone / NO UI / NO recording interface / NO third person perspective` block is what produces a real POV selfie instead of a third-person shot of someone holding a phone. "Use the face from reference image 1 exactly" + "use the outfit from reference image 2 exactly" locks identity across the multi-reference set.

---

## 8. The ChatGPT 3-step content engine (VERBATIM)

ChatGPT is the "AI co-director." Train it once, then use it for pillars → hooks → script → scene prompts.

### 8.1 Step 1 — Train ChatGPT once as a creative director (permanent instruction)

```
Tell ChatGPT every time I ask for a visual prompt, include details about the visual style, camera movement, main subject, background setting, and lighting mood. Even if I don't explicitly ask, add a creative rule. If your scene includes multiple characters, instruct ChatGPT to always choose a primary subject and describe them in detail.
```
Feed it the categories first: **visual style · camera angle · subject focus · background setting · lighting/mood.**

### 8.2 Step 2 — Hook → script generation (the viral ad)

The viral-script 4-part structure: **Hook → Pain + Promise → Value Delivery → Call to Action.** Hook in the first ~3 seconds or it's dead (80% decide in 3s). "Hook with surprise, not explanation" — the first 3s earn the next 3s.

Full script-generation prompt (VERBATIM):
```
write a bold, high converting ad script for a paid AI community that punches the viewer in the face with reality. The audience is creators and marketers who use tools like Mid-Journey, Cling, and Runway, but still make cheap, forgettable content. The tone should be confident, confrontational, and slightly cocky, like a mentor who's tired of excuses. The script must open with a powerful no BS hook, challenging the audience's failures, and calling out why they're broke. Hammer home, the idea that prompts aren't the problem. Their direction and taste are. Explain that everyone has access to the same tools, but only those with elite vision turn them into cash. Use a clear example comparing a basic, boring AI prompt with a cinematic money-making version. Pitch a private AI community where members flip prompts into videos, videos into followers, and followers into income. Promise they'll launch their first AI reel in seven days using the system's exact prompts, voice, stack, and edit map. Include the offer $5 a month, price locked for life for the first 1000 members, with only 500 spots left, and with a final line that hits hard, forcing them to decide. Write it like a high-converting viral ad script designed to make someone stop scrolling immediately.
```

**Why this works:** it specifies audience, tone, the exact 5-beat arc (hook → problem → solution → offer → decision line), the comparison device, the concrete offer with scarcity, and the output format — leaving ChatGPT only the wording to invent. Ad-script structure: **Hook (no-BS, challenges failures) → Problem → Solution (the system) → Offer (concrete, scarce) → Final line that forces a decision.** "The secret isn't complexity, it's clarity. Every line should pull the viewer to the next."

### 8.3 Step 3 — Scene-by-scene visual prompts (one script line = one visual)

Walk the script line by line; each line produces one copy-paste image prompt. Concept brief → resulting Midjourney prompt. Examples (VERBATIM):

Concept (opening hook):
```
Give me a high-fashion editorial concept of three individuals posing under harsh lighting at night. It should feel cyberpunk and confrontational for an opening hook, include lighting, angle, and accessories that read expensive. All three characters should appear serious, staring directly into the camera.
```
Resulting Midjourney prompt:
```
A dramatic close-up of three individuals posing under harsh lighting at night. The central figure is bald with freckled light skin, bold facial piercings, septum, nostril, and a dermal piercing on the forehead. Heavy lashes and wearing oversized rhinestone earrings and a layered crystal necklace. The person on the left has platinum blonde hair with bangs and facial piercings, while the person on the right has straight neon pink hair and intense eye makeup. All three appear serious, staring directly into the camera.
```

### 8.4 Line-refinement queries (iterate any single line)

```
Make this hook funnier. Five options.
Make this phrase more powerful and convincing.
Add emotion to this paragraph.
```

### 8.5 ReelEngine viral-script flow (alternative GPT)

Open ReelEngine → Start → it asks **why** you're creating (promote community / personal brand / business / story film) → choose genre → target audience → main-character traits (or auto-generate) → it produces **3 cinematic story options** → pick one → full script with hook + value reveal + psychological triggers → refine any line ("make this line even funnier" → 5 options) → request the complete script.

### 8.6 Memory-reset phrasings (when ChatGPT/ReelEngine drifts)

Stay in one chat thread for visual consistency; reuse the same character name. If it hallucinates/drifts:
```
forget memory
forget memory of image creation
```

---

## 9. Image-editing prompt set (VERBATIM)

Most client work is **editing, not generating** — refine an existing image, don't endlessly re-generate. Check lighting direction + perspective on every edit so composites look natural. Mask slightly larger than the object with soft edges for inpainting; clearly state what changes vs what stays.

The 4 types: **Global** (whole image — color/contrast/mood) · **Local** (specific parts) · **Structural** (crop/expand/outpaint/aspect) · **Hybrid** (AI + Canva/Figma/Photoshop).

### Outpaint / expand
```
extend the city street with soft neon signs and blurred traffic in the background, keep the same lighting and mood
```

### Background replace
```
replace the background with a soft, out-of-focus office interior, warm light, minimal distractions
```

### Remove object
```
remove the extra person in the background and fill with soft bokeh lights
```

### Add object
```
add a vintage camera   (on the table)
```

### Prompt-based global edits
```
same scene, but in cinematic teal and orange color grading.
Turn this into a night scene with neon reflections on the street.
Keep the same face and pose, change the outfit to a black leather jacket.
```

### Region-based edits (select a region, attach instruction)
```
Replace sky with dramatic storm clouds          (select the sky)
Turn the cup into a glass of red wine            (select the coffee cup)
```

### Inpaint / brush-mask
```
change the jacket to a white linen blazer, keep the same pose and lighting
```

### Plain-text targeted edit (Nano Banana Pro — change one part, keep the rest)
```
Replace the eagle, make it look older like the woman and make it look more dangerous.
```

### Homework examples
```
Turn this into a night scene with neon lights, keep the same pose and lighting direction.
Change the outfit to a black blazer, keep the same face and pose.
```

**Why these work:** every edit names what changes AND what to preserve ("keep the same face and pose," "keep the same lighting and mood"). The model defaults to redrawing more than you intended; the preservation clause is the leash.

---

## 10. The master upscale prompt (VERBATIM)

144p → 4K, identity-preserving, optimized for Nano Banana Pro. Works on Google Flow, Higgsfield, Freepik, Flora. This is NOT re-generation — the original is an immutable framework; face, scene, and composition stay identical. Run the result through 1–2 more times to refine detail.

```
Enhance the portrait while strictly preserving the subject's
identity with accurate facial geometry. Do not change their
expression or face shape. Only allow subtle feature cleanup without
altering who they are. Keep the exact same background from the
reference image. No replacements, no changes, no new objects, no
layout shifts. The environment must look identical. The image must
be recreated as if it was shot on a Sony A1, using an 85mm f1.4
lens, at f1.6, ISO 100, 1/200 shutter speed, cinematic shallow
depth of field, perfect facial focus, and an editorial-neutral
color profile. This Sony A1 + 85mm f1.4 setup is mandatory. The
final image must clearly look like premium full-frame
Sony A1 quality.
Lighting must match the exact direction, angle, and mood of the
reference photo. Upgrade the lighting into a cinematic,
subject-focused style: soft directional light, warm highlights,
cool shadows, deeper contrast, expanded dynamic range,
micro-contrast boost, smooth gradations, and zero harsh shadows.
Maintain neutral premium color tone, cinematic contrast curve,
natural saturation, real skin texture (not plastic), and subtle
film grain. No fake glow, no runway lighting, no over smoothing.
Render in 4K resolution, 10-bit color, cinematic editorial style,
premium clarity, portrait crop, and
keep the original environmental vibe untouched.
Re-render the subject with improved realism, depth, texture, and
lighting while keeping identity and background fully preserved.
```

NEGATIVE PROMPT (paste into the negative field):
```
No new background.
No background change.
No overly dramatic lighting.
No face morphing.
No fake glow.
No flat lighting.
No over-smooth skin.
```

**Why this works:** it repeatedly hammers identity/background preservation ("strictly preserving," "exact same background," "must look identical," "mandatory" camera) while specifying a real high-end camera package — so the model upgrades *fidelity* without inventing a new person or scene. The negative field forecloses the exact ways an upscale model tends to drift (morphing the face, swapping the background, plastic skin, fake glow).

---

## 11. Quick-reference: prompt anatomy by stage

| Stage | Formula | Length | Key levers |
|---|---|---|---|
| Image (any) | SHOT+LENS+LIGHT+TEXTURE+COMPOSITION+STYLE (+vision) | Layered, long | Camera language; technical not feelings |
| Image (Nano Banana Pro) | Object → Context → Technical | Layered | Spatial Intelligence; HEX/font/text control |
| Image integration (I2I) | base ref + product refs + explicit physics | Layered | Weight/gravity/contact-shadows; "no floating" |
| Video TTV | Subject + Action + Context + Style | Full | Describe everything; count nouns |
| Video I2V (motion) | WHAT moves + HOW + camera behavior | ~20–40 words | Don't re-describe image; motion endpoint; one move/shot |
| Lip sync | scaffold + micro-realism stack + `says clearly:"..."` | Full | Clean face/voice input; negative tail |
| Upscale | preserve identity+bg + real camera + 4K + negatives | Long | "Mandatory" camera; immutable framework |

---

## 12. Decision rules (durable, model-agnostic)

- **Random prompt → random image.** ~95% of AI output online is visual noise because the prompts are vague. Structure beats luck.
- **A prompt is a technical brief, not a wish.** Director + DP + gaffer + stylist at once.
- **Image-first, then animate.** Image fidelity caps video fidelity.
- **Generate the hero portrait FIRST**, reuse it as a reference everywhere — the universal consistency mechanism.
- **Choose the model BEFORE writing the prompt** — faster/cheaper models need simpler, tighter prompts (Kling o1 = complex/long; 2.6 = 5–7 elements; 2.5 Turbo Pro = 3–4 max; 1.6 = 1 subject/1 action).
- **One reference = one job** (style OR subject OR pose OR photo); use clean, high-res references.
- **Output too close to a reference** → reduce its influence / add text / add a contrasting ref. **Too far** → increase influence / simplify text / remove conflicting refs.
- **Negative constraints are half the craft** — say what must NOT happen.
- **Deliberate imperfection = realism** for UGC; perfection reads as fake.
- **Save prompt + model + settings + seed** — turns a lucky result into a repeatable system.
- **If a prompt doesn't work, just try again** — sometimes it's not the wording; AI isn't perfect yet. Across Kling and Seedance, run several and combine the best parts.
- **The tool is not the moat — taste and direction are.** Everyone has the same models; the structured creative system is the sellable IP.
