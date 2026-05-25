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

### Nano Banana 2 Multi-Angle Generation

Nano Banana 2 extends the character sheet with multi-angle generation from a single reference. This is useful for:
- Generating additional reference angles from limited source material
- Creating character sheet references without a full photoshoot
- Verifying character consistency from angles not covered by the original references

### LoRA as Fallback

When Nano Banana Pro is unavailable or when maximum control is needed (e.g., custom SD checkpoints, specific aesthetic requirements), LoRA weights serve as the fallback consistency model.

LoRA creation is documented in `references/style-locking.md` since the same LoRA workflow applies to both character consistency and style enforcement. The key difference is the training data: character LoRAs use face/body references, while style LoRAs use aesthetic references.

For character LoRAs specifically:
- Use 15-25 training images (faces from multiple angles + full body)
- Train for 1000-2000 steps on SDXL base
- Test at weights 0.6, 0.7, 0.8, 0.85, 0.9 and pick the best balance of consistency vs. flexibility
- Store weights at `models/loras/{character-slug}-v{N}.safetensors`
- Record the exact weight range in the character sheet's Consistency Anchors section
