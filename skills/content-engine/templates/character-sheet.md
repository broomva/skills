---
name: "{character_name}"
type: character-sheet
compiled: "{date}"
compiler_version: "0.1.0"
brand_ref: "compiled/brands/{brand_slug}.md"
nano_banana_ref: "{nano_banana_face_id}"
consistency_model: "{consistency_method}"
sources:
  - path: "raw/character-refs/{character_slug}/{source_file}"
    sha256: "{sha256}"
    modified: "{modified_date}"
tools:
  - nano-banana-pro
  - soul-cinema
  - comfyui
template: "templates/character-sheet.md"
template_version: "1.0.0"
---

# {character_name} -- Character Sheet

> Compiled character identity for {character_name}. This file ensures visual
> consistency across all generation tools and sessions. Every tool should
> produce a recognizable version of this character.

## Identity

**Full name:** {full_name}

**Role:** {role_description -- e.g., "Founder/CEO avatar for brand communications.
Appears in blog hero images, social media, presentation slides, and video
thumbnails."}

**Age range:** {age_range -- e.g., "Late 20s to early 30s"}

**Build:** {body_type -- e.g., "Medium build, athletic posture"}

**Ethnicity/Heritage:** {ethnicity -- e.g., "Latin American (Colombian)"}

**Distinguishing features:**
- {feature_1 -- e.g., "Strong jawline, defined cheekbones"}
- {feature_2 -- e.g., "Dark brown eyes, direct gaze"}
- {feature_3 -- e.g., "Short-cropped dark hair, clean fade"}
- {feature_4 -- e.g., "Light stubble (2-3 day growth)"}
- {feature_5 -- e.g., "Slight asymmetry in smile (left side higher)"}

**Personality in frame:** {personality_description -- e.g., "Projects calm
confidence. Slightly reserved but warm. Never performative -- the camera
catches them in a natural moment, not posing for it."}

---

## Consistency Anchors

These are the technical artifacts that ensure this character looks the same
across tools and sessions. They are the ground truth for "is this the right
person?"

### Nano Banana Pro ID

**Face ID:** `{nano_banana_face_id}`

**Source images used for embedding:**
1. `raw/character-refs/{character_slug}/{ref_image_1}` -- {description_1 -- e.g., "Front-facing, neutral expression, even lighting"}
2. `raw/character-refs/{character_slug}/{ref_image_2}` -- {description_2 -- e.g., "Three-quarter turn, slight smile"}
3. `raw/character-refs/{character_slug}/{ref_image_3}` -- {description_3 -- e.g., "Profile view, dramatic lighting"}
4. `raw/character-refs/{character_slug}/{ref_image_4}` -- {description_4 -- e.g., "Full body, casual standing pose"}

**Embedding quality notes:** {embedding_notes -- e.g., "Embedding trained on 4
high-resolution reference photos. Best consistency at face_id_weight 0.85.
Above 0.9 starts to override lighting/expression. Below 0.75 face becomes
inconsistent."}

### LoRA Weights

**LoRA file:** `{lora_filename -- e.g., "carlos_v3.safetensors"}`

**Training details:**
- Training images: {training_count -- e.g., "24 images"}
- Resolution: {training_resolution -- e.g., "512x512, center-cropped"}
- Steps: {training_steps -- e.g., "1500"}
- Learning rate: {training_lr -- e.g., "1e-4"}
- Trigger word: `{trigger_word -- e.g., "cescob_person"}`
- Recommended weight: {lora_weight -- e.g., "0.7-0.85"}

**LoRA compatibility:**
- SDXL base: {sdxl_compat -- e.g., "Yes (primary target)"}
- SD 1.5: {sd15_compat -- e.g., "No"}
- Flux: {flux_compat -- e.g., "Separate LoRA required (not yet trained)"}

### Face Embedding Hash

**Embedding method:** {embedding_method -- e.g., "InsightFace buffalo_l"}

**Embedding hash:** `{face_embedding_sha256}`

**Similarity threshold:** {similarity_threshold -- e.g., "cosine > 0.72 for
positive match. Below 0.65 is definitely wrong. Between 0.65-0.72 requires
manual review."}

**Verification images:** {verification_count -- e.g., "8 test generations
verified against embedding, all > 0.78 cosine similarity"}

---

## Scene Defaults

Default values for scene briefs involving this character. These can be
overridden per-scene but provide a consistent baseline.

### Wardrobe

**Default outfit:**
- **Top:** {default_top -- e.g., "Fitted black crewneck t-shirt, premium cotton"}
- **Bottom:** {default_bottom -- e.g., "Dark indigo slim jeans, no distressing"}
- **Footwear:** {default_footwear -- e.g., "White minimalist sneakers (Common Projects style)"}
- **Accessories:** {default_accessories -- e.g., "Simple silver watch, left wrist. No rings, no chains."}

**Alternate outfits:**

| Outfit Name | Context | Description |
|---|---|---|
| {outfit_1_name -- e.g., "Tech Keynote"} | {outfit_1_context -- e.g., "Presentations, product launches"} | {outfit_1_desc -- e.g., "Dark navy blazer over black tee, no tie. Rolled sleeves permitted."} |
| {outfit_2_name -- e.g., "Studio Session"} | {outfit_2_context -- e.g., "Behind-the-scenes, coding, building"} | {outfit_2_desc -- e.g., "Henley or plain tee, sleeves pushed up. Comfortable but intentional."} |
| {outfit_3_name -- e.g., "Editorial"} | {outfit_3_context -- e.g., "Magazine-style portraits, formal content"} | {outfit_3_desc -- e.g., "Black turtleneck or mandarin collar shirt. Minimalist, Steve Jobs energy."} |

**Wardrobe anti-patterns:**
- {wardrobe_anti_1 -- e.g., "No logos, brand names, or text on clothing"}
- {wardrobe_anti_2 -- e.g., "No bright colors (nothing above 40% saturation)"}
- {wardrobe_anti_3 -- e.g., "No ties, bowties, or formal neckwear"}

### Environments

**Primary environments:**

| Environment | Description | Lighting | Mood |
|---|---|---|---|
| {env_1_name -- e.g., "Command Center"} | {env_1_desc -- e.g., "Dark room with multiple glowing screens, terminal text visible. Desk with mechanical keyboard."} | {env_1_light -- e.g., "Screen glow as key light, ambient blue-purple fill"} | {env_1_mood -- e.g., "Focused, in the zone"} |
| {env_2_name -- e.g., "Glass Office"} | {env_2_desc -- e.g., "Floor-to-ceiling windows, city skyline at night. Minimal furniture, dark surfaces."} | {env_2_light -- e.g., "City lights as backlight, warm desk lamp as fill"} | {env_2_mood -- e.g., "Strategic, visionary"} |
| {env_3_name -- e.g., "Workshop"} | {env_3_desc -- e.g., "Open workspace with exposed brick, wooden surfaces, prototype hardware visible."} | {env_3_light -- e.g., "Overhead industrial pendants, warm spots"} | {env_3_mood -- e.g., "Hands-on, building"} |
| {env_4_name -- e.g., "Nature Escape"} | {env_4_desc -- e.g., "Forest trail, mountain overlook, or coastal path. Character in context, not posed."} | {env_4_light -- e.g., "Golden hour natural light, dappled shadows"} | {env_4_mood -- e.g., "Reflective, grounded"} |

**Environment rules:**
- {env_rule_1 -- e.g., "Indoor environments always have at least one visible light source (practical lighting)"}
- {env_rule_2 -- e.g., "Outdoor environments are golden hour or blue hour only -- never harsh midday"}
- {env_rule_3 -- e.g., "Background complexity inversely proportional to character close-up level"}

### Lighting for This Character

**Flattering angles:** {flattering_light -- e.g., "Key light from camera-left at
45 degrees, 30 degrees elevation. This illuminates the stronger side of the
jawline and creates a natural shadow that defines the cheekbones."}

**Skin tone rendering:** {skin_tone_notes -- e.g., "Warm olive undertone. Avoid
cool white balance which makes skin look gray. Aim for 4200-4800K. In
post-processing, keep skin luminance between 45-60% (never blown out, never
muddy)."}

**Eye lighting:** {eye_light -- e.g., "Always ensure catchlights in both eyes.
Single catchlight per eye preferred (reads as one key light). Dual
catchlights acceptable only with rim/backlight justification."}

---

## Tool-Specific Character Prompts

### Nano Banana Pro

**Character prompt fragment:**
{nbp_character_prompt -- e.g., "[face_id:{nano_banana_face_id}] a man in his
late 20s, strong jawline, short dark hair, light stubble, olive skin,
wearing {default_outfit_summary}, {scene_context}"}

**Consistency settings:**
- face_id_weight: {nbp_face_weight -- e.g., "0.85"}
- ip_adapter_weight: {nbp_ip_weight -- e.g., "0.0 (disabled when using face_id)"}
- pose_reference: {nbp_pose_ref -- e.g., "Optional. Use raw/character-refs/{character_slug}/pose_*.jpg"}

### Soul Cinema

**Character prompt fragment:**
{sc_character_prompt -- e.g., "a confident man in his late 20s with short dark
hair and light stubble, {outfit_description}, {action_description},
cinematic framing, shallow depth of field"}

**Motion directives:**
- {sc_motion_1 -- e.g., "Subtle breathing motion, never perfectly still"}
- {sc_motion_2 -- e.g., "Head turns: slow, deliberate, max 20 degrees per second"}
- {sc_motion_3 -- e.g., "Hand gestures: minimal, purposeful, never frantic"}

### ComfyUI

**Character prompt fragment:**
{comfyui_character_prompt -- e.g., "(cescob_person:1.1), masterpiece, best
quality, a man in late 20s, strong jawline, (short dark hair:1.2), light
stubble, olive skin tone, {outfit_description}, {scene_context}"}

**Workflow additions:**
- LoRA loader: `{lora_filename}` at weight {lora_weight}
- IP-Adapter: {ip_adapter_config -- e.g., "ip-adapter-faceid-plusv2 with
  raw/character-refs/{character_slug}/front_neutral.jpg at weight 0.8"}
- ControlNet: {controlnet_config -- e.g., "Optional openpose for specific
  body positioning. Use raw/character-refs/{character_slug}/pose_*.json"}

---

## Versioning

**Current version:** {character_version -- e.g., "v3"}

**Version history:**
| Version | Date | Changes |
|---|---|---|
| {v1_date} | {v1_changes -- e.g., "Initial character sheet. 4 reference images."} |
| {v2_date} | {v2_changes -- e.g., "Retrained LoRA with 24 images (was 12). Better hair consistency."} |
| {v3_date} | {v3_changes -- e.g., "Added Nano Banana Pro face embedding. Updated wardrobe."} |

**Drift detection:** If generated images consistently score below the similarity
threshold ({similarity_threshold}), the character anchors need updating. Common
causes: tool model updates, LoRA incompatibility with new checkpoints, or
accumulated prompt drift.
