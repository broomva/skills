# LoRA Style-Locking Patterns

Style locking is the practice of enforcing a specific visual aesthetic across all generated content using LoRA (Low-Rank Adaptation) weights, tool-specific prompt engineering, and pipeline configuration. The term comes from the ohneis652 workflow: instead of hoping a prompt produces the right style, you lock the style at the model level so every generation inherits it automatically.

This document covers the mechanics of style locking, the ComfyUI node setup that implements it, tool-specific prompt fragment generation, and documented anti-patterns that break consistency.

---

## How LoRAs Enforce Visual Styles

A LoRA is a small set of weight adjustments applied on top of a base model (Stable Diffusion XL, Flux, etc.) that biases generation toward a specific aesthetic. Unlike full fine-tuning (which modifies all model weights), LoRAs modify only a low-rank subspace -- typically 1-10% of the parameters -- making them fast to train, small to store, and stackable.

### The Style Locking Principle

From ohneis652's node pipeline philosophy:

> "You're not just prompting, you're directing. Each node is a design decision. Each LoRA is a creative constraint that eliminates the bad outputs before they're generated."

The principle: instead of writing elaborate prompts that describe a style (and hoping the model interprets them correctly), you train or select a LoRA that embodies the style and apply it at generation time. The LoRA constrains the latent space so that only outputs matching the style are reachable.

**Without LoRA**: "Wes Anderson style, pastel colors, symmetrical framing, centered composition" -- the model tries to interpret these words and produces variable results. Sometimes it works, sometimes it generates something that looks vaguely colorful but not Wes Anderson at all.

**With LoRA**: A Wes Anderson LoRA trained on actual Wes Anderson film stills constrains the model to only produce outputs in that visual space. The prompt can focus on scene content, and the style is handled by the weights.

### Style Categories and Example LoRAs

| Style | LoRA Reference | Effect | Typical Weight |
|-------|---------------|--------|---------------|
| Wes Anderson Pastels | `wes-anderson-pastel-v2.safetensors` | Centered symmetry, muted pastels, flat lighting, miniature-like depth | 0.7-0.8 |
| Fincher Desaturation | `fincher-dark-v1.safetensors` | Push-in framing, desaturated greens/blues, crushed blacks, overhead key | 0.6-0.75 |
| Nolan IMAX | `nolan-imax-v1.safetensors` | Wide-angle scale, practical lighting, blue-teal/orange palette, deep focus | 0.65-0.8 |
| Villeneuve Architectural | `villeneuve-desolation-v1.safetensors` | Negative space, warm/cold contrast, monolithic scale, haze | 0.6-0.7 |
| Kubrick Precision | `kubrick-symmetry-v1.safetensors` | One-point perspective, cold blue-white, clinical precision, geometric | 0.7-0.85 |
| 90s Editorial | `90s-editorial-v2.safetensors` | High contrast B&W or muted warm, flash photography, candid energy | 0.5-0.65 |
| Y2K Digital | `y2k-digital-v1.safetensors` | Oversaturated, chrome, lens flare, early digital camera look | 0.5-0.6 |
| Film Noir | `film-noir-v2.safetensors` | Hard shadows, venetian-blind patterns, high contrast B&W, low key | 0.7-0.8 |
| Cottagecore | `cottagecore-warmth-v1.safetensors` | Warm diffused light, florals, soft focus, golden tones, organic textures | 0.6-0.75 |
| Brutalism | `brutalist-concrete-v1.safetensors` | Raw concrete, geometric shadows, minimal color, hard edges | 0.65-0.8 |

### Weight as a Dial

LoRA weight (0.0 to 1.0) controls how strongly the style is enforced:

| Weight Range | Effect |
|-------------|--------|
| 0.0 - 0.3 | Subtle influence. Base model dominates. Style appears as a hint. |
| 0.3 - 0.5 | Moderate influence. Style visible but base model still contributes significantly. Good for blending. |
| 0.5 - 0.7 | Strong influence. Style clearly dominates. Base model provides structure. Sweet spot for most uses. |
| 0.7 - 0.85 | Very strong. Style fully locked. Some loss of prompt responsiveness. Use for strict consistency. |
| 0.85 - 1.0 | Maximum. Style overwhelms everything. Prompts beyond the LoRA's training distribution may be ignored. Risk of artifacts. |

**The ohneis652 rule of thumb**: Start at 0.65 and adjust. If the style is not visible enough, increase by 0.05. If the prompt is being ignored, decrease by 0.05. The sweet spot is different for every LoRA and depends on the complexity of the scene being generated.

---

## ComfyUI Node Setup for Style Locking

ComfyUI is a node-based visual programming environment for Stable Diffusion. Each node in the graph represents a processing step. Style locking is implemented by inserting LoRA loader nodes between the checkpoint loader and the sampler.

### Basic Style-Locked Pipeline

```
[CheckpointLoaderSimple]
    └── model ──► [LoRALoader] ──► model ──► [KSampler]
    └── clip ──► [LoRALoader] ──► clip ──► [CLIPTextEncode (positive)]
                                       ──► [CLIPTextEncode (negative)]
    └── vae ────────────────────────────► [VAEDecode]
```

### Node Configuration

#### CheckpointLoaderSimple
```yaml
node: CheckpointLoaderSimple
params:
  ckpt_name: "sdxl_base_1.0.safetensors"  # or flux1-dev, etc.
```

The base checkpoint provides the foundation. Choose based on desired output quality:
- SDXL 1.0: Best for photorealistic content, widest LoRA compatibility
- Flux.1 Dev: Higher detail, better prompt following, fewer LoRAs available
- Pony Diffusion: Better for stylized/illustration content

#### LoRALoader
```yaml
node: LoRALoader
params:
  lora_name: "wes-anderson-pastel-v2.safetensors"
  strength_model: 0.7    # How strongly the LoRA affects the diffusion model
  strength_clip: 0.7     # How strongly the LoRA affects text encoding
```

**Critical detail**: `strength_model` and `strength_clip` can be set independently. For style LoRAs, they should usually be equal. For character LoRAs, `strength_model` can be slightly higher than `strength_clip` to enforce visual consistency without restricting prompt interpretation.

#### Stacking Multiple LoRAs

Multiple LoRAs can be chained for compound effects (e.g., style + character):

```
[CheckpointLoader]
    └── model ──► [LoRALoader: style] ──► model ──► [LoRALoader: character] ──► model ──► [KSampler]
```

**Stacking rules:**
- Total combined weight should not exceed 1.2 (sum of all LoRA weights). Beyond this, artifacts appear.
- Load style LoRA first, character LoRA second. Order matters because each LoRA modifies the weights seen by the next.
- If stacking 3+ LoRAs, reduce individual weights proportionally. Three LoRAs at 0.4 each is usually better than three at 0.7 each.

#### CLIPTextEncode (Positive Prompt)

```yaml
node: CLIPTextEncode
params:
  text: >
    cinematic photograph, centered composition, symmetrical framing,
    pastel color palette, soft diffused lighting, shallow depth of field,
    film grain, muted tones, {scene_specific_content}
```

For ComfyUI, positive prompts use comma-separated tag format rather than natural language. The style-specific tags complement the LoRA -- they reinforce the style direction without relying solely on the weights.

#### CLIPTextEncode (Negative Prompt)

```yaml
node: CLIPTextEncode
params:
  text: >
    ugly, blurry, low quality, oversaturated, harsh shadows,
    text, watermark, logo, {style_specific_negatives}
```

Style-specific negatives are critical. For a Wes Anderson LoRA:
```
dutch angle, tilted, harsh contrast, neon colors, desaturated, gritty, handheld shake
```

For a Fincher LoRA:
```
bright, cheerful, pastel, saturated, warm tones, symmetrical centered, flat lighting
```

The negative prompt eliminates the outputs that would contradict the locked style.

#### KSampler

```yaml
node: KSampler
params:
  seed: -1                 # Random seed (-1) or fixed for reproducibility
  steps: 30                # 20-40 for SDXL, 20-28 for Flux
  cfg: 7.0                 # 5-8 for SDXL, 3-5 for Flux (lower = more creative)
  sampler_name: "euler_a"  # euler_a for speed, dpmpp_2m_sde for quality
  scheduler: "karras"      # karras for SDXL, normal for Flux
  denoise: 1.0             # 1.0 for txt2img, 0.4-0.7 for img2img
```

**CFG (Classifier-Free Guidance)** interacts with LoRA weight. Higher CFG = stricter prompt adherence. With a strong LoRA (weight > 0.7), lower CFG (5-6) produces better results because the LoRA already constrains the style and high CFG can cause over-cooking.

---

## Tool-Specific Prompt Fragment Generation

Each generation tool has its own prompt grammar. Style locking requires adapting the same visual intent to each tool's native language.

### Nano Banana Pro Fragments

Nano Banana Pro uses natural language descriptions. Style locking is achieved through descriptive consistency, not weights.

**Format:**
```
{scene_description}.
Style: {style_name} aesthetic. {2-3 specific style markers}.
Lighting: {lighting_description}.
Color: {color_palette_description}.
Camera: {shot_type}, {focal_length_impression}.
```

**Example (Wes Anderson style):**
```
A woman sits at a perfectly organized desk in a pastel pink office.
Style: Wes Anderson aesthetic. Symmetrical framing, centered composition, miniature-like depth.
Lighting: Soft, flat, even illumination with no harsh shadows.
Color: Muted pastels -- powder blue walls, butter yellow desk accessories, sage green plant.
Camera: Medium wide shot, centered, 50mm lens feel.
```

**Anti-patterns for Nano Banana Pro:**
- Do not use ComfyUI-style comma-separated tags (the model interprets them poorly)
- Do not reference LoRA names (Nano Banana has no LoRA system)
- Do not use negative prompts (Nano Banana does not support them; rephrase as positives)

### Soul Cinema / Higgsfield Fragments

Soul Cinema uses cinematic terminology. This is the tool where film-school vocabulary pays off.

**Format:**
```
Cinematic {shot_type} of {subject}.
{camera_movement} shot. {lens_spec}.
{lighting_setup}.
{color_grade_reference}.
{composition_rule}.
{atmosphere/mood}.
```

**Example (Fincher style):**
```
Cinematic medium close-up of a woman at a rain-streaked window.
Slow push-in shot. 85mm lens, shallow depth of field.
Single overhead key light, no fill, deep shadows on face.
Desaturated green-blue grade, crushed blacks, lifted midtones.
Off-center composition, subject in right third.
Tense, contemplative atmosphere. Urban night exterior visible through glass.
```

**Anti-patterns for Soul Cinema:**
- Do not use casual/conversational description ("a cool picture of someone")
- Do not specify resolution or aspect ratio in the prompt (use tool settings)
- Do not reference other AI tools in the prompt ("like Midjourney style")

### Weavy Fragments

Weavy focuses on environmental scene generation with character insertion. The prompt should lead with environment, not character.

**Format:**
```
Environment: {detailed_environment_description}
Mood: {mood_keywords}
Lighting: {lighting_description}
Time: {time_of_day}
Camera: {angle}, {distance}, {focal_length}
Character: [reference character sheet {slug}]
Action: {what_the_character_is_doing}
```

**Example (Villeneuve style):**
```
Environment: Vast concrete interior, cathedral-like proportions, raw walls with water stains,
single shaft of warm light from high window cutting through dust-filled air.
Mood: Solitary, monumental, contemplative
Lighting: Single warm beam from upper left, rest in deep shadow, visible dust motes
Time: Late afternoon, interior
Camera: Low angle, full body, 24mm wide lens
Character: [reference character sheet luna]
Action: Standing still, looking up at the light source, arms at sides
```

**Anti-patterns for Weavy:**
- Do not describe the character's physical appearance (the character sheet handles this)
- Do not use vague environment descriptions ("a nice room")
- Do not stack conflicting moods ("peaceful yet tense and energetic")

### ComfyUI Configuration Fragments

ComfyUI fragments are YAML node configurations, not natural language. They encode the exact technical setup for reproducible generation.

**Format:**
```yaml
checkpoint: sdxl_base_1.0.safetensors
lora:
  - name: wes-anderson-pastel-v2.safetensors
    model_weight: 0.7
    clip_weight: 0.7
sampler: euler_a
scheduler: karras
steps: 30
cfg: 6.5
width: 1216
height: 832
positive: >
  cinematic photograph, centered composition, symmetrical framing,
  pastel color palette, powder blue, butter yellow, sage green,
  soft diffused lighting, film grain, shallow depth of field,
  {scene_specific_tags}
negative: >
  ugly, blurry, low quality, harsh shadows, dutch angle,
  neon colors, desaturated, gritty, handheld, {style_specific_negatives}
```

**Anti-patterns for ComfyUI:**
- Do not use natural language sentences in the positive prompt (use comma-separated tags)
- Do not set CFG > 10 with LoRA weight > 0.7 (produces artifacts)
- Do not omit the negative prompt (without it, the LoRA has less constraint space to work with)
- Do not use a scheduler mismatched with the sampler (karras with euler_a is fine; normal with dpmpp_2m_sde is fine; mixing others requires testing)

---

## The ohneis652 Node Pipeline

ohneis652's core contribution is the node pipeline architecture -- a modular, branching generation process where each stage has a specific purpose and produces inspectable intermediate output.

### Full Pipeline

```
[Stage 1: Base Generation]
    Checkpoint + LoRA (style lock) → KSampler → Base Image
                                                    ↓
[Stage 2: Character Injection]
    Base Image + Character Reference → Nano Banana / IP-Adapter → Character Image
                                                    ↓
[Stage 3: Multi-Angle]
    Character Image → Nano Banana 2 / SV3D → Multiple Angles
                                                    ↓
[Stage 4: Motion]
    Selected Angle → Wan / Kling / Veo → Video Clip
                                                    ↓
[Stage 5: Upscale]
    Video Frames → Topaz Gigapixel / Real-ESRGAN → Upscaled Frames
                                                    ↓
[Stage 6: Grade]
    Upscaled Frames → LUT / Lightroom → Final Output
```

### Design Principles

1. **Each stage is independently inspectable.** You can stop after Stage 1 and examine the base image before investing compute in later stages. This prevents cascading failures -- if the base image is wrong, you fix it before generating 100 angles of the wrong image.

2. **Style lock happens once, at Stage 1.** The LoRA is applied at generation time, not in post-processing. Every subsequent stage inherits the style from the base image. This is why ohneis652 calls it "locking" -- once the style is baked into the base, it cannot drift in later stages.

3. **Character injection is Stage 2, not Stage 1.** Separating style from character prevents the two from competing. The LoRA handles style, the character reference handles identity. If they were combined in Stage 1 (character LoRA + style LoRA), the total weight budget would be split and both would suffer.

4. **Upscaling is not optional.** AI generation at native resolution (1024x1024) looks acceptable on a phone screen but falls apart on desktop or print. Topaz Gigapixel adds genuine detail (not just sharpening). This is a quality gate, not a luxury.

5. **Color grading is the final creative decision.** It is the only stage where the creator applies subjective taste after all technical generation is complete. LUTs (Look-Up Tables) provide reproducible grading. A single LUT can transform a warm image into a cold one or a modern one into a vintage one.

### Start-Frame Doctrine

The start-frame doctrine is ohneis652's most important contribution to the content engine:

> "Video quality is only as good as the initial generated image. Use cinematic-first models, not general-purpose."

This means:
- The image generated at Stage 1 (the "start frame") determines the quality ceiling for everything downstream
- Investing extra time and compute at Stage 1 (more steps, better LoRA, refined prompt) pays dividends at every subsequent stage
- A mediocre start frame cannot be rescued by good upscaling or grading
- Use cinematic-focused tools (Soul Cinema, Cinema Studio 2.5) for start frames, not general-purpose generators

---

## Anti-Pattern Documentation

Collected anti-patterns from ohneis652 workflows, community experience, and internal testing. Each anti-pattern describes what goes wrong and why.

### LoRA Anti-Patterns

| Anti-Pattern | What Happens | Why |
|-------------|-------------|-----|
| **Weight > 0.9** | Face rigidity, loss of prompt responsiveness, repetitive compositions | The LoRA overwhelms the base model. The latent space collapses to a narrow region. |
| **Stacking > 3 LoRAs** | Artifacts, color banding, anatomical errors | Combined weight exceeds the model's capacity. Low-rank adjustments start contradicting each other. |
| **Style LoRA + Character LoRA at equal high weight** | Style and character fight. Neither is fully realized. | Each LoRA pushes in a different direction. The model compromises, producing neither. |
| **LoRA trained on < 10 images** | Overfitting. Outputs look like the training set, not like the style. | Insufficient diversity in training data. The model memorizes specific images rather than learning a style. |
| **Using a LoRA with the wrong base model** | Garbage output, color noise, structural artifacts | LoRAs are base-model-specific. An SDXL LoRA applied to a Flux checkpoint produces nonsense. |

### Prompt Anti-Patterns

| Anti-Pattern | What Happens | Why |
|-------------|-------------|-----|
| **Contradictory style terms** ("warm and cold tones simultaneously") | Model averages, producing muddy/gray output | The model cannot resolve the contradiction, so it finds a midpoint that satisfies neither. |
| **Over-long prompts (> 150 tokens)** | Early tokens dominate, later tokens ignored | CLIP has a 77-token context window (padded to 150 with SDXL). Tokens beyond this are progressively downweighted. |
| **Style terms in negative prompt** | Does not reliably exclude the style; can attract it | Negative prompts are unreliable for complex concepts. "no Wes Anderson" may produce more Wes Anderson. |
| **Mixing natural language and tags** | Inconsistent interpretation, prompt leakage | ComfyUI works best with tags. Nano Banana works best with sentences. Mixing confuses both. |
| **"High quality, 8K, masterpiece"** | Minimal effect, wasted tokens | These terms are so overused in training data that they carry almost no signal. |

### Pipeline Anti-Patterns

| Anti-Pattern | What Happens | Why |
|-------------|-------------|-----|
| **Skipping the start frame check** | Bad images get upscaled and graded, wasting time | Stage 1 is the quality gate. Everything downstream inherits its problems. |
| **Upscaling before grading** | Grading amplifies upscaling artifacts | Upscaling adds detail. Grading stretches tonal range. Detail artifacts become visible after grading. Grade first (at low res), then upscale. *Exception:* Topaz Gigapixel handles this well -- its AI upscaling is artifact-resistant. |
| **Using img2img at high denoise to "fix" a bad generation** | Destroys the original composition and style lock | Denoise > 0.7 in img2img effectively generates a new image. The LoRA style from the original is partially overwritten. |
| **Regenerating without changing the prompt** | Same bad output (if using fixed seed) or random walk (if random seed) | If the output is bad, the prompt needs adjustment. Re-rolling the dice without changing anything is not a strategy. |

---

## Style Library Management

Over time, a content engine accumulates many style guides. Managing them requires organization.

### Naming Convention

```
knowledge/compiled/styles/{category}-{descriptor}.md
```

Examples:
- `cinematic-wes-anderson.md`
- `cinematic-fincher-dark.md`
- `editorial-90s-flash.md`
- `social-y2k-digital.md`
- `product-clean-minimal.md`

### Style Metadata

Each compiled style guide includes machine-queryable metadata:

```yaml
---
name: Wes Anderson Pastels
type: style-guide
category: cinematic          # cinematic | editorial | social | product
era: contemporary            # vintage | retro | contemporary | futuristic
mood: whimsical              # primary emotional register
color_temp: warm-neutral     # warm | cool | neutral | warm-neutral | cool-neutral
contrast: low                # high | medium | low
camera_ref: [wes-anderson]   # director style references
lora_ref: "wes-anderson-pastel-v2.safetensors"
lora_weight: 0.7
compatible_checkpoints: [sdxl_base_1.0, sdxl_turbo]
---
```

This metadata enables programmatic style selection: "find me a cinematic style with warm tones and low contrast" can be resolved by querying the frontmatter without reading every style guide's full body.

### Style Versioning

When a style guide is updated (new LoRA version, refined prompts, adjusted weights):

1. Increment the LoRA version: `v2` becomes `v3`
2. Update the `compiled` timestamp
3. Keep the previous LoRA file (do not delete -- in case rollback is needed)
4. Note the change in the style guide body under a "Changelog" section
5. Re-test with 3 standard test scenes to verify the update does not break existing campaigns

Style guides, like code, should be versioned and testable. A style update that breaks an active campaign is a regression.
