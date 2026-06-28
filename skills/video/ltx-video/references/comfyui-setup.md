# LTX-2 ComfyUI Integration

## Requirements

- ComfyUI (latest)
- CUDA-compatible GPU: 32GB+ VRAM recommended (16GB minimum with low-VRAM loaders)
- 100GB+ free disk space for models
- Python 3.12+

## Installation

### Via ComfyUI Manager (Recommended)

1. Launch ComfyUI
2. Press `Ctrl+M` to open Manager
3. Select "Install Custom Nodes"
4. Search "LTXVideo"
5. Click Install → Restart ComfyUI

### Manual Installation

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git
cd ComfyUI-LTXVideo
pip install -r requirements.txt
# Restart ComfyUI
```

## Model Placement

Download from https://huggingface.co/Lightricks/LTX-2.3 and place:

```
ComfyUI/
├── models/
│   ├── checkpoints/
│   │   ├── ltx-2.3-22b-dev.safetensors        # or distilled variant
│   │   ├── ltx-2.3-spatial-upscaler-x2-1.1.safetensors
│   │   └── ltx-2.3-temporal-upscaler-x2-1.0.safetensors
│   ├── text_encoders/
│   │   └── gemma-3-12b/                        # Gemma 3 text encoder
│   └── loras/
│       ├── ltx-2.3-22b-distilled-lora-384.safetensors
│       ├── ltx-2.3-ic-lora-union.safetensors
│       ├── ltx-2.3-lora-motion-track.safetensors
│       ├── ltx-2.3-lora-detailer.safetensors
│       ├── ltx-2.3-lora-pose.safetensors
│       └── ltx-2.3-lora-camera-*.safetensors
```

## Available Workflow Files

The ComfyUI-LTXVideo repo includes example workflows:

| Workflow | Description |
|----------|-------------|
| `ltxv-13b-i2v-base.json` | Basic image-to-video |
| `ltxv-13b-t2v-base.json` | Basic text-to-video |
| `ltxv-13b-i2v-mixed-multiscale.json` | Multi-scale rendering |
| `ltxv-13b-dist-i2v-base.json` | Distilled variant |

Load via ComfyUI: File → Load Workflow → select JSON file.

## Custom Node Categories

### Conditioning
- Load and apply text/image/audio conditions
- Keyframe placement at specific frame indices

### Sampling
- LTX-specific samplers with guidance parameters
- Tiled sampling for memory efficiency

### VAE
- LTX VAE encode/decode
- Tiled VAE for large resolutions

### LoRA
- IC-LoRA loader with control conditioning
- Union, motion, pose, camera control LoRAs

### Utilities
- Prompt enhancement node
- Mask manipulation
- Latent normalization
- Low-VRAM model loaders

## Low-VRAM Mode

For GPUs with <32GB VRAM:

1. Use low-VRAM loader nodes from `low_vram_loaders.py`
2. Start ComfyUI with `--reserve-vram 1.5` (reserves 1.5GB for system)
3. Use the distilled model (fewer steps = less peak memory)
4. Enable tiled VAE decoding for large resolutions

```bash
python main.py --reserve-vram 1.5
```

## Typical Workflow Structure

```
[Gemma3 Text Encoder] → [LTX Conditioning] → [LTX Sampler] → [LTX VAE Decode] → [Save Video]
                                ↑
                    [Image/Audio Input] (optional)
```

For two-stage (higher quality):
```
[Stage 1: Base Generation] → [Spatial Upscaler] → [Stage 2: Refinement] → [Save Video]
                                                          ↑
                                                  [Temporal Upscaler] (optional)
```
