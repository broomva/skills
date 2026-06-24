# Character Sheets -- Format and Creation Process

Character sheets are the compiled identity files that ensure a specific person (real or fictional) looks consistent across every generation session, every tool, and every scene. They are the content engine's answer to the oldest problem in AI image generation: "How do I make the same character appear in different scenes without them looking like a different person every time?"

---

## Why Character Sheets Exist

The viznfr workflow demonstrated that character consistency is a solved problem IF you treat identity as compiled data rather than ad-hoc prompting:

1. **Define the persona** once (age, ethnicity, build, distinguishing features, default energy)
2. **Lock the identity** into a tool-native consistency system (Nano Banana Pro character sheet, or a LoRA fine-tuned on reference images)
3. **Reference the locked identity** in every subsequent generation (character sheet ID, not re-described prompts)

The character sheet `.md` file is the human-readable, tool-agnostic representation of this locked identity. It contains everything a generation tool needs to reproduce the character, plus metadata that enables verification and drift detection.

---

## Character Sheet Format

### Frontmatter

```yaml
---
name: Luna Reyes
type: character-sheet
compiled: 2026-04-07T14:30:00Z
sources:
  - path: raw/character-refs/luna/face-front.jpg
    sha256: m3n4o5p6...
  - path: raw/character-refs/luna/face-3quarter.jpg
    sha256: q7r8s9t0...
  - path: raw/character-refs/luna/full-body-standing.jpg
    sha256: a1b2c3d4...
nano_banana_ref: "nb-char-id-12345"
consistency_model: nano-banana-pro
lora_weights: null
face_embedding_hash: "sha256:u1v2w3x4..."
related:
  - "[[brands/broomva-lifestyle]]"
  - "[[styles/editorial-warm]]"
  - "[[styles/cinematic-golden]]"
status: active
---
```

**Required fields:**
- `name`: Human-readable character name
- `type`: Always `character-sheet`
- `compiled`: ISO-8601 timestamp of last compilation
- `sources`: Array of raw reference files with SHA-256 hashes
- `consistency_model`: Which system maintains identity (`nano-banana-pro`, `lora:{name}`, `sd-reference-only`)
- `status`: One of `active`, `draft`, `archived`, `stale`

**Optional fields:**
- `nano_banana_ref`: Character sheet ID from Nano Banana Pro (if using that system)
- `lora_weights`: Path to LoRA weights file (if using LoRA-based consistency)
- `face_embedding_hash`: SHA-256 of the face embedding vector (for verification)
- `related`: Wikilinks to associated brands and styles

### Body Sections

#### Identity

The core physical description. Every trait listed here is a consistency anchor -- if a generated image deviates from any of these traits, it is a consistency failure.

```markdown
## Identity

- **Age**: 28
- **Ethnicity**: Mixed (Southeast Asian / European)
- **Build**: Athletic-slim
- **Height impression**: Average-tall (5'7" / 170cm feel)
- **Hair**: Dark brown, shoulder-length, natural wave. Parts left. No bangs.
- **Eyes**: Dark brown, almond-shaped, slight upward tilt at outer corners
- **Skin tone**: Medium olive, warm undertone (Fitzpatrick Type IV)
- **Face shape**: Oval with defined cheekbones, tapered chin
- **Nose**: Straight bridge, medium width, slightly rounded tip
- **Lips**: Full, natural color, defined cupid's bow
- **Distinguishing features**: Subtle freckles across nose bridge, defined jawline, small beauty mark left of chin
- **Default expression**: Relaxed confidence, slight asymmetric smile (left corner higher)
- **Energy/vibe**: Approachable professional, warm intelligence, grounded
```

**Specificity matters.** "Brown hair" is not specific enough. "Dark brown, shoulder-length, natural wave, parts left, no bangs" is. Every adjective should eliminate an ambiguity that a generation tool might otherwise resolve randomly.

#### Consistency Anchors

The technical mechanisms that enforce consistency across sessions.

```markdown
## Consistency Anchors

### Nano Banana Pro
- **Character sheet ID**: nb-char-id-12345
- **Upload date**: 2026-04-05
- **Reference images used**: 5 (front, 3/4 left, 3/4 right, profile left, full body)
- **Consistency score**: 0.92 (tool-reported)
- **Known drift scenarios**: Extreme close-ups sometimes alter nose shape. Full-body shots in complex environments may lose freckle detail.

### LoRA (if applicable)
- **Weights file**: models/loras/luna-reyes-v2.safetensors
- **Training images**: 20 (curated from raw/character-refs/luna/)
- **Training steps**: 1500
- **Base model**: SDXL 1.0
- **Recommended weight**: 0.7-0.85 (higher = more consistent but less flexible)
- **Known drift scenarios**: Weight > 0.9 produces face rigidity. Weight < 0.6 loses identity.

### Face Embedding
- **Embedding hash**: sha256:u1v2w3x4...
- **Embedding model**: InsightFace antelopev2
- **Reference image**: raw/character-refs/luna/face-front.jpg
- **Verification threshold**: cosine similarity >= 0.85
```

#### Scene Defaults

Pre-configured defaults that define how the character looks "normally." These can be overridden per scene, but they serve as the baseline that maintains brand coherence.

```markdown
## Scene Defaults

### Wardrobe Palette
- **Core colors**: Earth tones (olive #556B2F, rust #B7410E, cream #FFFDD0, slate #708090)
- **Accent**: Warm metallics (gold #FFD700, bronze #CD7F32) — jewelry, buttons, small details
- **Textures**: Natural fabrics (cotton, linen, light wool). No synthetic sheen.
- **Style range**: Smart casual to editorial. Structured blazers, quality basics, minimal branding.
- **Avoid**: Neon/fluorescent colors, heavy graphic prints, visible logos, athleisure

### Environments That Work
- Urban architecture with natural light (cafes with large windows, rooftop terraces, tree-lined streets)
- Workspace with warm ambient lighting (wooden desks, bookshelves, warm practicals)
- Outdoor golden hour (parks, coastal walks, garden terraces)
- Minimalist interiors with texture (concrete, wood, plants, natural textiles)

### Environments to Avoid
- Corporate sterile (fluorescent-lit offices, conference rooms, white cubicles)
- Pure black or pure white seamless backgrounds (studio look breaks lifestyle feel)
- Heavily cluttered or maximalist spaces (compete with subject for attention)
- Themed/decorated sets (holiday, party — unless specifically scripted)

### Lighting That Flatters
- **Best**: 45-degree soft key, warm fill, subtle warm rim (emphasizes cheekbone structure, reduces under-eye shadows)
- **Good**: Window light (large, diffused), golden hour direct, overcast ambient
- **Acceptable**: Top-down with bounce fill, ring light (for social content only)
- **Avoid**: Direct overhead without fill (harsh nose/eye socket shadows), direct front (flattens facial structure), colored gels on face (distorts skin tone), under-lighting (unflattering shadows)
```

---

## Creation Process

### Step 1 -- Collect Reference Images

Minimum 5 reference images, ideally 8-12, covering:

| Angle | Purpose | Requirements |
|-------|---------|-------------|
| Front face (neutral) | Identity baseline | Even lighting, neutral expression, no accessories blocking face |
| 3/4 left | Nose shape, cheekbone | Same lighting as front |
| 3/4 right | Symmetry verification | Same lighting as front |
| Profile (left or right) | Jawline, nose bridge | Side lighting acceptable |
| Full body (standing) | Build, proportions, posture | Full figure visible, neutral clothing |
| Expression range (2-3) | Smile, serious, candid | Natural expressions, not exaggerated |
| Environment context (2-3) | Character in situ | Natural settings, varied lighting |

**Quality requirements:**
- Minimum 1024x1024 resolution
- Face clearly visible (no heavy shadows, no heavy accessories blocking features)
- Consistent identity across all reference images (same person, same approximate age)
- No heavy filters or processing (the raw visual data is what the compiler needs)

Place all reference images in `knowledge/raw/character-refs/{slug}/`.

### Step 2 -- Nano Banana Pro Character Sheet Upload

If using Nano Banana Pro as the consistency model:

1. Select 5 best reference images (front, 3/4 left, 3/4 right, profile, full body)
2. Upload to Nano Banana Pro character sheet creator
3. Wait for processing (typically 2-5 minutes)
4. Record the character sheet ID (visible in the tool's character library)
5. Test with 3 basic scene prompts to verify consistency
6. If consistency score is below 0.85, revisit reference image selection

The character sheet ID is the key anchor. All subsequent Nano Banana Pro generations reference this ID rather than re-describing the character.

### Step 3 -- Gemini Analysis

Run the character reference images through the brand DNA extraction prompt (see `references/brand-dna-extraction.md`) with a character-specific modifier:

```
In addition to standard visual analysis, extract the following character-specific traits:

{
  "identity": {
    "age_apparent": 28,
    "ethnicity_apparent": "Mixed Southeast Asian / European",
    "build": "athletic-slim",
    "height_impression": "average-tall",
    "hair": {
      "color": "dark brown",
      "length": "shoulder-length",
      "texture": "natural wave",
      "part": "left",
      "bangs": false
    },
    "eyes": {
      "color": "dark brown",
      "shape": "almond",
      "detail": "slight upward tilt at outer corners"
    },
    "skin": {
      "tone": "medium olive",
      "undertone": "warm",
      "fitzpatrick": "IV"
    },
    "face_shape": "oval with defined cheekbones",
    "distinguishing": ["freckles across nose bridge", "defined jawline", "beauty mark left of chin"],
    "default_expression": "relaxed confidence, asymmetric smile",
    "energy": "approachable professional, warm intelligence"
  }
}

Be specific. Extract traits that differentiate this person from a generic description. "Brown eyes" is insufficient -- "dark brown, almond-shaped, slight upward tilt" is the level of specificity needed.
```

### Step 4 -- Compile Character Sheet

Using the Gemini analysis output plus the Nano Banana character sheet ID (if applicable), write the compiled character sheet to `knowledge/compiled/characters/{slug}.md` following the format specified above.

### Step 5 -- Cross-Reference

- Link the character to any brands they appear in (`related` field)
- Link to default styles that define their visual context
- Verify no conflicting character sheet exists (name collision, appearance overlap)
- If the character belongs to a brand, verify the character's wardrobe palette does not conflict with the brand's color palette

### Step 6 -- Consistency Verification

Generate 5 test images using the character sheet across different scenarios:

1. Indoor, warm lighting, close-up
2. Outdoor, natural light, medium shot
3. Urban environment, full body
4. Different wardrobe, same character
5. Different expression, same lighting

For each generated image, verify against the identity section:
- Hair color, length, style match?
- Eye color, shape match?
- Skin tone consistent?
- Distinguishing features preserved?
- Overall energy/vibe maintained?

If more than 1 of 5 tests show significant deviation, the character sheet needs refinement (better reference images, adjusted LoRA weights, or updated Nano Banana character sheet).

---

## Face Embedding Consistency Verification

For programmatic consistency checking (beyond visual inspection), face embeddings provide a numerical verification layer.

### Computing the Reference Embedding

```python
import insightface
from insightface.app import FaceAnalysis

app = FaceAnalysis(name='antelopev2', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=0)

# Load reference image
img = cv2.imread('raw/character-refs/luna/face-front.jpg')
faces = app.get(img)

if len(faces) == 1:
    reference_embedding = faces[0].normed_embedding
    embedding_hash = hashlib.sha256(reference_embedding.tobytes()).hexdigest()
    # Store embedding_hash in character sheet frontmatter
```

### Verifying Generated Images

```python
# Load generated image
generated_img = cv2.imread('output/scene-01.jpg')
generated_faces = app.get(generated_img)

if len(generated_faces) == 1:
    similarity = np.dot(reference_embedding, generated_faces[0].normed_embedding)
    if similarity >= 0.85:
        print(f"PASS: cosine similarity {similarity:.3f}")
    else:
        print(f"FAIL: cosine similarity {similarity:.3f} (threshold: 0.85)")
```

### Thresholds

| Similarity | Verdict | Action |
|-----------|---------|--------|
| >= 0.90 | Excellent | Character is strongly consistent |
| 0.85 - 0.89 | Good | Acceptable for most use cases |
| 0.80 - 0.84 | Marginal | Review manually; may pass for non-close-up shots |
| < 0.80 | Fail | Character has drifted; regenerate or adjust consistency model |

---

## Maintaining Consistency Across Sessions

Character drift is the gradual degradation of identity consistency over time. It happens for several reasons:

### Drift Sources

1. **Prompt evolution**: As scene descriptions change, character traits can be overridden by environmental context (e.g., a "beach scene" prompt might lighten hair color).
2. **Tool updates**: When Nano Banana Pro or ComfyUI update their models, the same prompt may produce slightly different results.
3. **LoRA weight decay**: If LoRA weights are combined with other LoRAs or used at different strengths, the identity signal weakens.
4. **Seed variation**: Different random seeds produce different interpretations of the same prompt. Some seeds are more faithful than others.

### Anti-Drift Protocol

1. **Always reference the character sheet ID** (Nano Banana) or LoRA name (ComfyUI) explicitly. Never rely on text description alone.
2. **Include consistency anchors in every prompt**: "Character: Luna Reyes [nb-char-id-12345]" even when the prompt is primarily about the scene.
3. **Batch-verify periodically**: Every 10 generations, run face embedding verification against the reference. If average similarity drops below 0.85, investigate.
4. **Pin tool versions**: Record which tool version produced good results. When tools update, test before batch-generating.
5. **Maintain a "golden set"**: Keep 3-5 generated images that perfectly match the character sheet. Use these as visual references when evaluating new generations.

### Handling Multi-Character Scenes

When multiple characters appear in the same scene:

- Generate each character separately, then composite (highest consistency)
- If generating together, lead with the character who needs highest consistency
- Use explicit character differentiation in the prompt: do not rely on "two people" -- specify each character by name and reference
- Verify both characters' embeddings independently against their respective sheets

---

## Nano Banana Pro Integration

Nano Banana Pro is the primary consistency model for the content engine. Its character sheet system provides the highest-fidelity identity locking available through a browser-accessible tool.

### Character Sheet ID Workflow

```
1. Upload reference images → Nano Banana Pro character creator
2. Tool processes images → generates internal character model
3. Character sheet ID assigned (e.g., nb-char-id-12345)
4. Record ID in compiled character sheet frontmatter
5. All subsequent generations: "Use character sheet nb-char-id-12345"
```

### Multi-Angle Character Set (Nano Banana Pro → Kling Elements)

Nano Banana **Pro** (not Nano Banana 2) builds a multi-angle character set — e.g. a 5-frame set of the same character from different angles — which is then saved as a Kling **Element** and recalled by name in later generations. Assemble it from your curated angle references; it is built from multiple angle shots, **not** auto-generated from a single image. Useful for:
- Building a reusable, named character Element so appearance stays consistent as the camera moves
- Combining Elements (character + environment + style) into one controlled composite

### LoRA as Fallback

When Nano Banana Pro is unavailable or when maximum control is needed (e.g., custom SD checkpoints, specific aesthetic requirements), LoRA weights serve as the fallback consistency model.

LoRA creation is documented in `references/style-locking.md` since the same LoRA workflow applies to both character consistency and style enforcement. The key difference is the training data: character LoRAs use face/body references, while style LoRAs use aesthetic references.

For character LoRAs specifically:
- Use 15-25 training images (faces from multiple angles + full body)
- Train for 1000-2000 steps on SDXL base
- Test at weights 0.6, 0.7, 0.8, 0.85, 0.9 and pick the best balance of consistency vs. flexibility
- Store weights at `models/loras/{character-slug}-v{N}.safetensors`
- Record the exact weight range in the character sheet's Consistency Anchors section

---

## AI Video Creators distillation (AVCC additions)

> Distilled from the AI Video Creators course (BRO-1525) — see broomva/workspace docs/reference/ai-video-creators-course/.

The AVCC course arrives at the same destination as the viznfr workflow above (a locked identity reused across every scene) by a different, lower-tooling road: instead of a tool-native consistency model (Nano Banana character sheet ID, LoRA) compiled once, it treats the **prompt text itself** as the portable identity file. The two approaches are complementary — compile the identity into a tool-native anchor when you have one (see [Consistency Anchors](#consistency-anchors) and [Nano Banana Pro Integration](#nano-banana-pro-integration) above), and *additionally* carry the Fixed-DNA text block so the character survives a tool change. Everything below is the text-block discipline and the cross-model reuse mechanism the AVCC teaches; it does not restate the embedding/LoRA/anchor machinery already covered.

### Character DNA = Master Prompt (the "digital passport")

The AVCC frames the character sheet not as a metadata file but as a single reusable prompt split into two parts. The split is the entire discipline:

| Part | Contents | Edit cadence |
|---|---|---|
| **A. Fixed DNA** (never changes) | Face description · age / ethnicity / skin type · identifying details (moles, scars, skin texture) | **Copy-pasted verbatim into every generation, forever.** Treat as immutable. |
| **B. Variable Context** (changes every post) | Outfit · location · lighting · pose | Rewritten per post — this is the *only* part you touch. |

**Why this works:** the model regenerates the face from the same exact tokens every time, so identity drift has no entry point — drift only enters through *changed* tokens, and the Fixed DNA block is never changed. It is the [Anti-Drift Protocol](#anti-drift-protocol) rule "include consistency anchors in every prompt" reduced to its most portable form: when you have no tool-native anchor (new model, new platform, no LoRA), the verbatim text block *is* the anchor. The Fixed/Variable split also makes batching trivial — a content calendar becomes "one Fixed DNA + N Variable Contexts."

The course ships ready-made Master Prompts in its Aesthetic Library (a Drive file of viral character aesthetics + filled-in DNA blocks). Store your own Fixed DNA block at the top of the compiled character sheet so it can be copied in one motion.

A worked example of the level of specificity the Fixed DNA block demands — this is a base **identity-lock portrait** prompt (Nano Banana Pro, 9:16, 2K), where the entire body of the prompt becomes the Fixed DNA from then on:

```text
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

Note "centered composition for identity lock" / "frontal eye-level view" — the portrait is deliberately neutral so it makes the strongest possible reference frame (see the reuse mechanism below). Everything from "Facial structure:" through "Lips:" is what becomes the **Fixed DNA**; "Lighting / Background / Camera / Focus / Color / Composition" are scene-level and migrate into **Variable Context** for later posts.

### 1 account = 1 character, never change the DNA

The hardest rule and the most-repeated one in the course:

> **1 Account = 1 Character. Same face, same skin aesthetic, same DNA. Never change the DNA.**

You may change camera, story, world, outfit, era, mood freely — those are Variable Context. You may **never** change the Fixed DNA, and you may **never** run two characters on one account. The rationale is distribution, not aesthetics: *"You're not looking for content — you're building an asset."* Visual identity is the single strongest signal both the human brain and the recommendation algorithm recognize, so a consistent face compounds recognition the way a logo does. A second character on the same account splits that signal and resets the compounding. This is the business-layer reason the [Maintaining Consistency Across Sessions](#maintaining-consistency-across-sessions) machinery exists: drift is not a quality bug, it is an asset-destruction event.

### Hero-portrait-first + reuse-as-reference (the universal mechanism)

The single mechanism that works across *every* model — Midjourney, Kling, Nano Banana Pro, Seedance — is:

1. **Generate the hero portrait once** (the identity-lock prompt above). This is the anchor frame.
2. **Reuse that one image as a reference everywhere**, regardless of how each tool names the feature.

The feature has a different name in every tool, but it is the same operation — this table is the model-agnostic Rosetta for the "reference reuse" anchor:

| Tool | Reference-reuse feature | Notes |
|---|---|---|
| **Midjourney** | OmniReference | Plain-text prompts only — no JSON |
| **Kling** | Elements | Save the hero (or a 5-frame multi-angle set) as a named Element; call it by name later |
| **Nano Banana Pro** | reference image / face-swap | Feed the hero as REF 1; or replace only the face on another image |
| **Seedance 2.0** | reference collage (up to 9 images) | References give ~80% of control; build the collage in Photojoiner |

**Why this works:** image fidelity caps video fidelity ("if the image isn't real, the video never will be"), so the entire consistency problem collapses to *make one excellent anchor frame, then never re-describe the face — point at the frame instead.* This is the AVCC's version of the [Anti-Drift Protocol](#anti-drift-protocol) rule "always reference the character sheet ID … never rely on text description alone," generalized to any tool that accepts an image reference. The Fixed-DNA text block (above) is the fallback for tools/sessions where you can't attach the image; the reference image is the primary anchor when you can.

> Model/version note: Midjourney OmniReference, Kling Elements, Nano Banana Pro face-swap, and Seedance 2.0's 9-image collage are the named features at time of writing (Kling 3.0, Nano Banana Pro, Seedance 2.0 era). **These rotate quarterly.** The durable craft is "generate one anchor, reuse it as a reference"; the feature names are not durable — re-map them when a tool ships a new reference primitive or a new model supersedes these.

### Two paths to the start image (Full Generation vs Hybrid Reality)

Once the Fixed DNA exists, the per-post start image is made one of two ways:

| Path | How | When to use |
|---|---|---|
| **Full Generation** | Keep Fixed DNA untouched; rewrite only Variable Context (new world — Mars, beach, café). Pure text-to-image. | Fictional/impossible scenes; full creative control; no real footage needed. |
| **Hybrid Reality** | Screenshot a *real* video (yours), upload to Nano Banana Pro, ask it to **replace only the face** with your character. Real environment + real clothes + AI face. | Maximum believability; "easy believable integration" because lighting/physics/wardrobe are already real — only the identity is synthetic. |

**Why Hybrid Reality works:** the photorealism problem is hardest in the environment and the body physics, both of which a real screenshot already solves perfectly. By constraining the model to edit *only the face*, you spend the generation budget on the one region you actually need synthesized and inherit everything else from reality. It is the [Handling Multi-Character Scenes](#handling-multi-character-scenes) "composite for highest consistency" idea applied to a single character against a real backplate. (Nano Banana Pro's face-swap is the named tool here — same rotation caveat as above.)

### Kling Motion Control + the tripod rule ("stillness is the law")

To animate the locked character with realistic human motion, the AVCC uses **Kling Motion Control**, which separates *appearance* from *motion* across two input slots:

| Slot | Feed it | It contributes |
|---|---|---|
| **Start Frame** | the perfect hero image (locked DNA) | appearance / identity |
| **Motion Reference** | a phone video you recorded | movement + facial expressions |

The mapping is the whole point: **appearance comes from the photo, motion comes from your video.** You perform the action yourself on a phone; the AI wears your character's face over your movement.

**The non-negotiable constraint — "stillness is the law":**

> The camera recording the Motion Reference **MUST be absolutely static** — tripod, shelf, or table. Any handheld shake makes the AI face drift, float, or warp, and the illusion breaks.

**Why this works:** the model is solving an identity-transfer problem frame-by-frame; a static camera means the *only* thing changing between frames is the subject's motion, which is exactly the signal Motion Control is built to transfer. A moving camera adds a second source of inter-frame change (parallax, background shift) that the face-transfer solver mistakes for identity variation — and identity variation is drift. A tripod removes that confound entirely. This is the motion-side analogue of the [Drift Sources](#drift-sources) "seed variation" problem: an uncontrolled variable in the input becomes drift in the output, so you eliminate the variable at the source.

### Download and store hero images locally (tools change)

Operational rule that protects everything above:

> **Download and store your hero/anchor images on local disk.** Tools, accounts, and cloud libraries change, deprecate, rate-limit, or disappear; a local file keeps the character forever.

This is the same logic as the `sources` array with SHA-256 hashes in the [character sheet frontmatter](#frontmatter) — the raw visual anchor is the irreplaceable asset and must survive any single tool's lifecycle. In content-engine terms: the hero portrait belongs in `knowledge/raw/character-refs/{slug}/` alongside the other references, hashed and recorded, *before* it is ever uploaded to a generation tool. The Fixed-DNA text block, the local hero image, and (when available) the tool-native anchor are three redundant copies of the same identity — the more tool-independent the copy, the more durable it is.
