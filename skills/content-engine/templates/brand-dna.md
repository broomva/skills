---
name: "{brand_name}"
type: brand-dna
compiled: "{date}"
compiler_version: "0.1.0"
sources:
  - path: "raw/brand-assets/{brand_slug}/{source_file}"
    sha256: "{sha256}"
    modified: "{modified_date}"
tools:
  - nano-banana-pro
  - soul-cinema
  - weavy
  - comfyui
template: "templates/brand-dna.md"
template_version: "1.0.0"
---

# {brand_name} -- Brand DNA

> Compiled identity file for {brand_name}. This document is machine-readable:
> generation tools consume it directly to produce on-brand content.

## Brand Essence

**Tagline:** {one_line_tagline}

**Brand voice:** {voice_description -- e.g., "Authoritative but approachable.
Technical precision with human warmth. Never corporate, never casual."}

**Core values:**
1. {value_1} -- {brief_description}
2. {value_2} -- {brief_description}
3. {value_3} -- {brief_description}

**Target audience:** {audience_description -- demographics, psychographics,
what they care about, what they're trying to accomplish}

**Competitive positioning:** {how_this_brand_differs_from_alternatives}

---

## Visual Identity

### Color Palette

| Role | Hex | RGB | Usage |
|------|-----|-----|-------|
| Primary | {primary_hex} | {primary_rgb} | Headlines, CTAs, brand marks |
| Secondary | {secondary_hex} | {secondary_rgb} | Accents, supporting elements |
| Background | {bg_hex} | {bg_rgb} | Canvas, negative space |
| Surface | {surface_hex} | {surface_rgb} | Cards, panels, elevated surfaces |
| Text Primary | {text_primary_hex} | {text_primary_rgb} | Body text, headings |
| Text Secondary | {text_secondary_hex} | {text_secondary_rgb} | Captions, metadata |
| Accent Warm | {accent_warm_hex} | {accent_warm_rgb} | Highlights, notifications |
| Accent Cool | {accent_cool_hex} | {accent_cool_rgb} | Links, interactive elements |

**Color rules:**
- {color_rule_1 -- e.g., "Never place primary on secondary without a separator"}
- {color_rule_2 -- e.g., "Background must always be dark (< 20% lightness)"}
- {color_rule_3 -- e.g., "Accent colors used sparingly -- max 10% of any composition"}

### Lighting

**Primary lighting style:** {lighting_style -- e.g., "Cinematic rim lighting
with deep shadows. Single key light at 45 degrees, warm fill at 15% opacity."}

**Mood lighting:**
- **Hero shots:** {hero_lighting -- e.g., "Dramatic backlight, lens flare permitted"}
- **Product shots:** {product_lighting -- e.g., "Clean studio, even diffusion"}
- **Atmospheric:** {atmospheric_lighting -- e.g., "Volumetric fog, god rays,
  practical light sources (screens, neon, fire)"}

**Light temperature:** {color_temp -- e.g., "4500K neutral with warm 3200K
accents. Never cool/blue unless depicting technology."}

### Composition

**Aspect ratios:**
- Social feed: 1:1 (1080x1080)
- Stories/Reels: 9:16 (1080x1920)
- Blog hero: 16:9 (1920x1080)
- OG/social card: 1.91:1 (1200x630)

**Grid system:** {grid_description -- e.g., "Rule of thirds with subject placed
at left or right intersection. Generous negative space (min 30% of frame)."}

**Depth of field:** {dof_preference -- e.g., "Shallow (f/1.4-2.8 equivalent)
for portraits. Deep (f/8-11) for architectural/environment shots."}

**Camera angles:**
- **Default:** {default_angle -- e.g., "Eye level, slight upward tilt (5-10 degrees)"}
- **Power shots:** {power_angle -- e.g., "Low angle, looking up. Hero framing."}
- **Intimate:** {intimate_angle -- e.g., "Slightly above eye level, close crop"}

### Texture

**Surface qualities:**
- {texture_1 -- e.g., "Glass: frosted, with subtle refraction and depth blur"}
- {texture_2 -- e.g., "Metal: brushed titanium, not chrome. Matte, not mirror."}
- {texture_3 -- e.g., "Fabric: linen or raw cotton. Never synthetic sheen."}
- {texture_4 -- e.g., "Digital: subtle noise grain (ISO 800 equivalent). Anti-smooth."}

**Material palette:** {material_description -- e.g., "Dark glass, oxidized
metal, raw concrete, backlit panels. Industrial-luxe."}

### Pose Language

**Character posture:**
- **Confident:** {confident_pose -- e.g., "Shoulders back, chin slightly raised,
  hands visible. Direct gaze or three-quarter turn."}
- **Thoughtful:** {thoughtful_pose -- e.g., "Hand near chin or temple, gaze
  slightly off-camera. Weight shifted to one side."}
- **Active:** {active_pose -- e.g., "Mid-gesture, hands in motion. Captured at
  peak of movement. Slight motion blur permitted."}

**Forbidden poses:**
- {forbidden_1 -- e.g., "Arms crossed (reads as defensive)"}
- {forbidden_2 -- e.g., "Hands in pockets (reads as disengaged)"}
- {forbidden_3 -- e.g., "Stock photo pointing (reads as generic)"}

**Group dynamics:** {group_description -- e.g., "Characters interact naturally.
No one looks at camera in group shots. Triangular composition."}

---

## Tool-Specific Prompts

### Nano Banana Pro

**Positive prompt:**
{nano_banana_positive -- Full prompt text optimized for Nano Banana Pro's
prompt format. Include style keywords the model responds to, reference any
face IDs or consistency tokens, specify composition and lighting in NBP's
vocabulary. Example: "cinematic portrait, {brand_name} brand aesthetic,
dramatic rim lighting, shallow depth of field, [face_id:{character_ref}],
dark moody background with glass reflections, 8k, film grain"}

**Negative prompt:**
{nano_banana_negative -- e.g., "cartoon, anime, illustration, watermark, text,
logo, blurry, low quality, overexposed, flat lighting, stock photo, generic
corporate, plastic skin, uncanny valley"}

**Parameters:**
- resolution: {nbp_resolution -- e.g., "1024x1024 (square) or 768x1344 (portrait)"}
- guidance_scale: {nbp_guidance -- e.g., "7.5"}
- steps: {nbp_steps -- e.g., "30"}
- face_id_weight: {nbp_face_weight -- e.g., "0.85"}
- style_strength: {nbp_style_strength -- e.g., "0.7"}

**Notes:**
{nbp_notes -- e.g., "Nano Banana Pro excels at character consistency via face
embeddings. Always reference the character's face_id. For multi-character
scenes, use separate face_id slots. The model tends to over-saturate warm
tones -- pull guidance down to 6.5 if reds look blown out."}

### Soul Cinema

**Positive prompt:**
{soul_cinema_positive -- Full prompt optimized for Soul Cinema's cinematic
video generation. Include motion descriptors, camera movements, atmospheric
elements. Example: "cinematic establishing shot, slow dolly forward through
fog, {brand_name} dark glass aesthetic, volumetric lighting, anamorphic
lens flare, 24fps film cadence, color graded teal-orange"}

**Negative prompt:**
{soul_cinema_negative -- e.g., "static, flat, digital, clean, stock footage,
handheld shake, fast motion, text overlay, watermark"}

**Parameters:**
- resolution: {sc_resolution -- e.g., "1280x720"}
- duration: {sc_duration -- e.g., "4 seconds"}
- fps: {sc_fps -- e.g., "24"}
- camera_motion: {sc_camera -- e.g., "slow_dolly | orbit | static"}
- mood_preset: {sc_mood -- e.g., "cinematic_dark"}

**Notes:**
{sc_notes -- e.g., "Soul Cinema responds well to film terminology (dolly, crane,
steadicam). Describe camera movement explicitly. Keep prompts under 200
tokens for best results. The model struggles with rapid character motion --
prefer slow, deliberate movement."}

### Weavy

**Positive prompt:**
{weavy_positive -- Full prompt optimized for Weavy's stylized image generation.
Example: "editorial illustration, {brand_name} brand palette, minimalist
composition, bold geometric shapes, limited color palette [{primary_hex},
{secondary_hex}, {bg_hex}], clean lines, negative space, modern design"}

**Negative prompt:**
{weavy_negative -- e.g., "photorealistic, noisy, cluttered, gradients,
drop shadows, 3D render, ornate, decorative, busy background"}

**Parameters:**
- resolution: {weavy_resolution -- e.g., "1080x1080"}
- style_preset: {weavy_preset -- e.g., "editorial | minimal | bold"}
- color_mode: {weavy_color -- e.g., "brand_palette_locked"}

**Notes:**
{weavy_notes -- e.g., "Weavy works best for social media graphics and
illustrations, not photorealistic content. Feed it the exact hex codes from
the color palette. Keep compositions simple -- the model shines with
negative space and geometric shapes."}

### ComfyUI

**Positive prompt:**
{comfyui_positive -- Full prompt for the main KSampler node in a ComfyUI
workflow. Example: "masterpiece, best quality, {brand_name} brand style,
cinematic lighting, film grain, (dark background:1.3), (glass reflections:0.8),
professional photography, 8k uhd"}

**Negative prompt:**
{comfyui_negative -- e.g., "(worst quality:1.4), (low quality:1.4), normal
quality, lowres, watermark, text, blurry, jpeg artifacts, deformed,
mutated, disfigured, bad anatomy"}

**Parameters:**
- checkpoint: {comfyui_checkpoint -- e.g., "sdxl_base_1.0.safetensors"}
- lora: {comfyui_lora -- e.g., "{brand_slug}_style_v2.safetensors @ 0.7"}
- sampler: {comfyui_sampler -- e.g., "dpmpp_2m_sde_karras"}
- steps: {comfyui_steps -- e.g., "35"}
- cfg_scale: {comfyui_cfg -- e.g., "7.0"}
- resolution: {comfyui_resolution -- e.g., "1024x1024 (SDXL native)"}
- vae: {comfyui_vae -- e.g., "sdxl_vae.safetensors"}

**Workflow notes:**
{comfyui_workflow -- e.g., "Recommended workflow: txt2img → upscale (4x
UltraSharp) → img2img refinement at 0.3 denoise. For character consistency,
add IP-Adapter node with face reference image at weight 0.85. For brand
style, use the LoRA trained on brand assets."}

---

## Anti-Patterns

Things this brand is NOT. Use these to catch off-brand generations early.

| Anti-Pattern | Why It Fails | What To Do Instead |
|---|---|---|
| {anti_1_name} | {anti_1_reason -- e.g., "Bright, saturated pastels read as playful/consumer, not technical/premium"} | {anti_1_fix -- e.g., "Use dark palette with selective accent pops"} |
| {anti_2_name} | {anti_2_reason -- e.g., "Stock photo compositions signal generic corporate"} | {anti_2_fix -- e.g., "Asymmetric framing, environmental context"} |
| {anti_3_name} | {anti_3_reason -- e.g., "Over-polished renders feel synthetic and untrustworthy"} | {anti_3_fix -- e.g., "Add film grain, chromatic aberration, subtle imperfections"} |
| {anti_4_name} | {anti_4_reason} | {anti_4_fix} |
| {anti_5_name} | {anti_5_reason} | {anti_5_fix} |

**Brand red lines** (immediate rejection):
- {red_line_1 -- e.g., "Any image that could be mistaken for a competitor's brand"}
- {red_line_2 -- e.g., "Watermarks, visible AI artifacts, extra fingers/limbs"}
- {red_line_3 -- e.g., "Content that misrepresents the product's capabilities"}

---

## Quality Checklist

Before approving any generated asset, verify:

- [ ] Colors match palette (sample check: pick 3 dominant colors, compare to hex table)
- [ ] Lighting follows the defined style (key light direction, temperature, shadows)
- [ ] Composition uses brand grid rules (aspect ratio, negative space, subject placement)
- [ ] No anti-pattern violations present
- [ ] Tool-specific parameters were used (check generation metadata)
- [ ] Character consistency maintained (if applicable -- cross-reference character sheet)
- [ ] No brand red line violations
