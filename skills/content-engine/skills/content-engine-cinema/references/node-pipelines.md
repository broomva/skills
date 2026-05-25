# Node Pipeline Architecture

ComfyUI node-based generation pipelines from ohneis652's production workflow. Each node is a design decision -- the pipeline is an explicit encoding of your creative process.

## Philosophy: Nodes as Design Decisions

In a traditional creative workflow, every step is a conscious choice: the photographer selects a lens, the colorist chooses a LUT, the retoucher decides the skin texture. A node pipeline makes these decisions explicit and reproducible.

The key insight: **do not use a monolithic model for everything.** Break the pipeline into specialized nodes where each one handles a single transformation. This gives you:

- **Modularity** -- swap any node without rebuilding the whole pipeline
- **Reproducibility** -- the same inputs produce the same outputs every time
- **Debuggability** -- when output is wrong, you can identify which node caused it
- **Scalability** -- batch-process by feeding different inputs through the same pipeline

## The Six-Node Pipeline

```
[1. SD Base]  →  [2. LoRA Style Lock]  →  [3. Multi-Angle]  →  [4. Motion]  →  [5. Upscale]  →  [6. Grade]
```

### Node 1: Base Generation (SD / Flux / Nano Banana)

**Purpose:** Generate the raw creative output from a text or image prompt.

**Models by use case:**

| Model | Strength | Resolution | Speed |
|-------|----------|------------|-------|
| **SD 3.5 Large** | Photorealism, fine detail | 1024x1024 native | Medium |
| **Flux.1 [dev]** | Text rendering, composition accuracy | 1024x1024 native | Fast |
| **Flux.1 [schnell]** | Speed, good-enough quality for drafts | 1024x1024 native | Very fast |
| **Nano Banana 2** (Gemini) | API convenience, multimodal editing | Up to 2048x2048 | Fast (API) |

**ComfyUI setup:**
```
[CLIPTextEncode (positive)] → [KSampler] → [VAEDecode] → [SaveImage]
[CLIPTextEncode (negative)] ↗
[EmptyLatentImage] ↗
[CheckpointLoader] → model/clip/vae connections
```

**Design decisions at this node:**
- **Model selection** determines the aesthetic baseline (SD3.5 for photorealism, Flux for graphic design)
- **Sampler/scheduler** (DPM++ 2M Karras for detail, Euler for speed, DPM++ SDE for painterly)
- **CFG scale** (7-9 for photorealism, 3-5 for more creative/loose output, 12+ for strict prompt adherence)
- **Steps** (20-30 for production, 8-12 for drafts, 50+ for maximum detail with diminishing returns)
- **Resolution** (always generate at model native resolution, upscale later)

### Node 2: LoRA Style Lock

**Purpose:** Constrain the output to a specific visual language -- a brand, an era, a film stock, a design style.

A LoRA (Low-Rank Adaptation) is a small model trained on a specific aesthetic. When applied, it biases the base model toward that aesthetic without replacing it entirely.

**Common LoRA categories:**

| Category | Example LoRAs | Effect |
|----------|---------------|--------|
| **Film stock** | Kodak Portra 400, Fuji Velvia, CineStill 800T | Color response, grain texture, highlight roll-off |
| **Era** | 1970s print, 80s VHS, 90s Kodachrome | Period-accurate color science and texture |
| **Brand** | Custom-trained on brand assets | Color palette, composition patterns, typography style |
| **Character** | Trained on character sheet | Facial features, body proportions, clothing details |
| **Technique** | Long exposure, tilt-shift, IR photography | Specific photographic techniques |

**ComfyUI setup:**
```
[CheckpointLoader] → [LoRALoader] → model/clip to KSampler
                      ↑
              lora_name: "film_stock_portra.safetensors"
              strength_model: 0.7
              strength_clip: 0.7
```

**Design decisions at this node:**
- **LoRA selection** -- which aesthetic to apply
- **Strength** (0.0-1.0) -- how much the LoRA overrides the base model
  - 0.3-0.5: subtle influence, base model character preserved
  - 0.6-0.8: strong style lock, recommended for most production use
  - 0.9-1.0: dominant, can cause artifacts if the LoRA is low quality
- **Multiple LoRAs** -- chain them (film stock + era + character) but reduce individual strengths to avoid conflict

### Node 3: Multi-Angle / Multi-Pose Expansion

**Purpose:** Generate multiple views of the subject from a single reference, creating a character turnaround or scene variation set.

**Methods:**

**Nano Banana multi-view (API):**
```
Input: single reference image + prompt describing desired angles
Output: front, 3/4, side, back views with consistent character
```

**ComfyUI multi-view:**
```
[LoadImage (reference)] → [IPAdapter] → [KSampler with angle-modified prompt] → [VAEDecode]
                                         ↑
                                prompt: "3/4 view of the same character..."
```

**MVDream / Zero123++ (ComfyUI nodes):**
```
[LoadImage] → [Zero123PlusLoader] → [Zero123PlusSampler] → [SaveImage]
                                     ↑
                         elevation: 0, azimuth: [0, 45, 90, 180]
```

**Design decisions at this node:**
- **Which angles to generate** -- front/3/4/side/back for character sheets; same angle with different poses for scene variations
- **Consistency method** -- IPAdapter (preserves style + appearance), Zero123 (precise geometry rotation), LoRA (trained identity)
- **Number of outputs** -- 4 views minimum for a character sheet, 8-12 for a comprehensive reference package

### Node 4: Motion / Video Synthesis

**Purpose:** Add temporal motion to a static frame, turning the start image into video.

This is where the start-frame doctrine (see [cinematic-prompting.md](cinematic-prompting.md)) pays off. The motion node receives a high-quality, carefully composed frame and only needs to animate it.

**Models by capability:**

| Model | Strength | Duration | Input |
|-------|----------|----------|-------|
| **Wan 2.1** | Natural motion, camera control | 2-5s | Image + text |
| **Kling 2.0/3.0** | Motion transfer, character animation | 5-10s | Image + reference video |
| **Seedance 2.0** | Multi-shot storytelling, consistency | 4-8s | Image + text + character reference |
| **AnimateDiff** | ComfyUI-native, fast iteration | 2-4s | Latent + motion LoRA |
| **Veo 3.1** | Highest quality, native audio | 4-8s | Image + text (API only) |

**ComfyUI setup (AnimateDiff):**
```
[LoadImage] → [VAEEncode] → [AnimateDiffLoader] → [KSampler] → [VAEDecode] → [SaveAnimatedImages]
                              ↑
                   motion_module: "mm_sd15_v3.safetensors"
                   motion_scale: 1.0
```

**ComfyUI setup (Wan via API node):**
```
[LoadImage] → [WanImageToVideo node] → [SaveVideo]
               ↑
   prompt: "slow dolly forward, subtle camera movement"
   negative: "fast motion, sudden movements, jittery"
```

**Design decisions at this node:**
- **Model selection** -- Wan for natural subtle motion, Kling for motion transfer, AnimateDiff for fast local iteration
- **Motion scale** -- how much movement to add (lower is usually better; too much motion looks artificial)
- **Duration** -- shorter clips are more controllable (2-4s), extend via chaining
- **Camera vs subject motion** -- decide whether the camera moves, the subject moves, or both

### Node 5: Upscaling

**Purpose:** Increase resolution without introducing artifacts, blurriness, or hallucinated detail.

**Tools by priority:**

| Tool | Method | Best For | Output |
|------|--------|----------|--------|
| **Topaz Gigapixel AI** | Neural network, proprietary | Final delivery, maximum quality | 2x-6x upscale |
| **Real-ESRGAN** | Open-source neural upscaler | Local pipeline, good quality | 2x-4x upscale |
| **SD Upscale** (ComfyUI) | Tiled re-diffusion at higher res | Adding detail during upscale | 2x with detail enhancement |
| **Lanczos** (ffmpeg/ImageMagick) | Algorithmic interpolation | Fast previews, no GPU needed | Any scale, no detail addition |

**ComfyUI setup (Real-ESRGAN):**
```
[LoadImage] → [UpscaleModelLoader] → [ImageUpscaleWithModel] → [SaveImage]
               ↑
       model_name: "RealESRGAN_x4plus.pth"
```

**ComfyUI setup (SD Upscale / tiled):**
```
[LoadImage] → [VAEEncode] → [UpscaleTiled] → [KSampler] → [VAEDecode] → [SaveImage]
                              ↑
                   tile_size: 512
                   denoise: 0.35  # Low denoise preserves original, high adds detail
```

**Design decisions at this node:**
- **Upscale factor** -- 2x for web delivery, 4x for print, 6x rarely needed
- **Denoise level** (for SD Upscale) -- 0.2-0.4 preserves the original closely, 0.5-0.7 adds detail but may change character
- **Sharpening** -- apply after upscale, not before (prevents artifact amplification)

See [upscaling-grading.md](upscaling-grading.md) for the full upscaling pipeline including CLI commands.

### Node 6: Color Grading

**Purpose:** Apply the final color science -- the "look" that ties all outputs together into a cohesive visual package.

**Methods:**

**LUT-based (ffmpeg):**
```bash
ffmpeg -i input.png -vf "lut3d=cinematic_teal_orange.cube" output.png
```

**ComfyUI color correction:**
```
[LoadImage] → [ColorCorrect] → [SaveImage]
               ↑
   temperature: -5     # Cooler
   tint: 0
   brightness: -0.05   # Slightly darker
   contrast: 1.15      # Punch up
   saturation: 0.9     # Slightly desaturated
   gamma: 1.0
```

**Lightroom (batch via presets):**
Export a Lightroom preset as `.xmp`, apply via `exiftool` or Lightroom CLI to batch-process.

**Design decisions at this node:**
- **LUT selection** -- the LUT IS the look. It should match the director vocabulary chosen earlier.
- **Contrast curve** -- lifted blacks for a filmic look, crushed blacks for drama
- **Color temperature** -- cooler for clinical/tech, warmer for human/emotional
- **Saturation** -- almost always reduce slightly from default for a professional look

## Complete Pipeline Example

Here is a full ComfyUI pipeline for generating a Fincher-style tech scene:

```
Workflow: "fincher-tech-scene-v1"

1. CheckpointLoaderSimple
   → ckpt_name: "sd3.5_large.safetensors"

2. LoRALoader (chained)
   → lora_name: "cinestill_800t.safetensors", strength: 0.6
   → lora_name: "desaturated_clinical.safetensors", strength: 0.4

3. CLIPTextEncode (positive)
   → "A software engineer in a dark server room, lit by monitor glow,
      cold blue-green tones, desaturated, clinical precision, 
      medium close-up, shallow depth of field, 50mm f/1.2"

4. CLIPTextEncode (negative)
   → "warm colors, bright, cheerful, oversaturated, cartoon, 
      illustration, low quality, blurry"

5. EmptyLatentImage → 1024x1024

6. KSampler
   → sampler: dpm_2m, scheduler: karras
   → steps: 28, cfg: 8.0, denoise: 1.0

7. VAEDecode → base image

8. UpscaleModelLoader + ImageUpscaleWithModel
   → RealESRGAN_x4plus → 4096x4096

9. ColorCorrect
   → temperature: -8, contrast: 1.2, saturation: 0.8, brightness: -0.1

10. SaveImage → "fincher-tech-scene-001.png"
```

## Setting Up a Pipeline in ComfyUI

### Installation

```bash
# Clone ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# Install dependencies
pip install -r requirements.txt

# Install ComfyUI Manager (for easy node installation)
cd custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager.git
cd ..

# Start the server
python main.py --listen 0.0.0.0 --port 8188
```

### Installing Custom Nodes

Via ComfyUI Manager (recommended):
1. Open `http://localhost:8188`
2. Click "Manager" → "Install Custom Nodes"
3. Search for and install: AnimateDiff, IPAdapter, Reactor (face swap), Real-ESRGAN

Via git (manual):
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git
git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
git clone https://github.com/Gourieff/comfyui-reactor-node.git
```

### Model Placement

```
ComfyUI/
  models/
    checkpoints/     # SD 3.5, Flux, etc.
    loras/           # Style LoRAs, character LoRAs
    upscale_models/  # RealESRGAN, ESPCN
    ipadapter/       # IPAdapter models
    insightface/     # Face analysis models (for Reactor)
    animatediff/     # Motion modules
    clip/            # CLIP models
    vae/             # VAE models
```

### Saving and Loading Workflows

ComfyUI workflows are saved as JSON files. Export from the UI via "Save" and load via "Load" or drag-and-drop.

Store production workflows in the content-engine knowledge directory:
```
content-engine/
  knowledge/
    compiled/
      styles/            # LoRA + LUT pairings per visual style
    raw/
      scene-briefs/      # Scene description templates
      style-inspiration/ # Reference images organized by style
```

### API Mode

ComfyUI exposes a REST API for programmatic pipeline execution:

```bash
# Queue a workflow
curl -X POST http://localhost:8188/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": <workflow-json>, "client_id": "content-engine"}'

# Check queue status
curl http://localhost:8188/queue

# Get output images
curl http://localhost:8188/view?filename=<output-filename>&type=output
```

This enables the API-first generation mode: generate the ComfyUI workflow JSON programmatically, submit it via API, and collect results.

## Pipeline Customization

### Adding a Node

To add a new node to an existing pipeline, determine where it belongs in the chain:

1. **Before base generation** -- preprocessing (image enhancement, background removal)
2. **After base, before style** -- composition adjustment (crop, rotate, perspective correct)
3. **After style, before motion** -- character refinement (face swap, detail enhancement)
4. **After motion, before upscale** -- temporal processing (frame interpolation, stabilization)
5. **After upscale, before grade** -- sharpening, noise reduction
6. **After grade** -- format conversion, metadata embedding

### Removing a Node

Some nodes are optional depending on use case:

- **No LoRA needed** -- when the base model already matches the desired style
- **No multi-angle needed** -- when generating single scenes, not character sheets
- **No motion needed** -- for still image production
- **No upscale needed** -- when base resolution is sufficient for the delivery format
- **No grade needed** -- when using a LoRA that already encodes the desired color science

The minimum viable pipeline is: Base Generation → Save. Everything else is additive refinement.
