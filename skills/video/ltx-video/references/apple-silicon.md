# LTX-2 on Apple Silicon (MLX / MPS)

## MLX Native Options

Three community projects bring LTX-2 to Apple Silicon via MLX:

### mlx-video (by Prince Canuma / Blaizzy)

MLX-native video generation framework. Supports LTX-Video and other diffusion models.

```bash
pip install git+https://github.com/Blaizzy/mlx-video.git

# Basic usage
from mlx_video import generate
generate(prompt="A cat playing piano", model="ltx-video", steps=20)
```

- GitHub: https://github.com/Blaizzy/mlx-video
- Quantized model support (Q4, Q8)
- Optimized for Apple Neural Engine + GPU

### LTX-2-MLX (by Acelogic)

Direct MLX port of LTX-2 with quantization support.

```bash
git clone https://github.com/Acelogic/LTX-2-MLX.git
cd LTX-2-MLX
pip install -r requirements.txt

python generate.py \
  --prompt "A golden retriever running through a park" \
  --quantize q4 \
  --num_frames 33 \
  --output output.mp4
```

- GitHub: https://github.com/Acelogic/LTX-2-MLX
- Q4 quantized model fits ~19 GB (runs on 24 GB machines)
- Full-precision model requires 64 GB+ unified memory

### LTX Video Mac GUI (by James See)

Native macOS GUI app wrapping LTX-Video for point-and-click usage.

- GitHub: https://github.com/james-see/ltx-video-mac
- No terminal required
- Drag-and-drop image-to-video
- Built with SwiftUI

## MPS Backend (PyTorch on Metal)

If using the upstream LTX-2 repo directly with `device="mps"`:

### PyTorch Version Pinning

MPS support is fragile across PyTorch releases. Known-good versions:

| PyTorch Version | MPS Status | Notes |
|-----------------|------------|-------|
| 2.3.0 | Works | Stable for LTX-2 |
| 2.4.1 | Works | Stable for LTX-2 |
| 2.5.0+ | Broken | Conv3d regression, NaN outputs |

```bash
# Pin to a known-good version
pip install torch==2.4.1 torchvision==0.19.1 torchaudio==0.24.1
```

### Known Limitations

- **No FP8 quantization.** FP8 is CUDA-only (requires H100/Ada Lovelace hardware). Use Q4/Q8 MLX quantization instead.
- **float64 unsupported.** MPS does not support float64 tensors. Patches needed to cast `torch.float64` to `torch.float32` throughout the pipeline.
- **Audio decode broken.** Audio extraction/synchronization fails at most frame counts on MPS. Generate video-only and add audio in post.
- **Conv3d regression.** PyTorch 2.5+ introduced a Conv3d bug on MPS that produces NaN outputs. Pin to 2.4.1 or use community patches.
- **Slower than CUDA.** Expect 3-5x slower generation compared to an RTX 4090. MLX-native paths are generally faster than MPS.

### Community Patches

Two patch sets fix the worst MPS issues:

**ltx2-mps** (Pocket-science):
```bash
git clone https://github.com/Pocket-science/ltx2-mps.git
# Patches Conv3d, float64, and scheduler issues for MPS
# Apply to upstream LTX-2 repo
```
- GitHub: https://github.com/Pocket-science/ltx2-mps

**mps-conv3d** (mpsops):
```bash
git clone https://github.com/mpsops/mps-conv3d.git
# Standalone Conv3d fix for PyTorch MPS backend
```
- GitHub: https://github.com/mpsops/mps-conv3d

## Memory Requirements

| Configuration | Unified Memory Needed | Notes |
|---------------|----------------------|-------|
| Q4 quantized (MLX) | ~19 GB | Fits 24 GB M2/M3/M4 Pro |
| Q8 quantized (MLX) | ~30 GB | Needs 32 GB+ machine |
| Full precision (MLX) | ~64 GB | M2/M3/M4 Max or Ultra |
| MPS (float32) | ~48 GB+ | Unquantized PyTorch |

### Recommended Hardware

- **24 GB** (M2/M3/M4 Pro): Q4 quantized only, short clips (33 frames)
- **36-48 GB** (M3/M4 Pro max config): Q8 quantized, medium clips
- **64 GB+** (M2/M3/M4 Max): Full precision, longer clips
- **128 GB+** (M2/M4 Ultra): Full precision, high resolution, long clips

## Recommended Path

For Apple Silicon users, the priority order is:

1. **MLX-native** (mlx-video or LTX-2-MLX) with Q4 quantization -- best performance/memory ratio
2. **MPS with patches** (ltx2-mps) pinned to PyTorch 2.4.1 -- if you need upstream compatibility
3. **Cloud API** -- if local generation is too slow or memory-constrained (see `references/cloud-api.md`)
