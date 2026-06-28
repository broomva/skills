# LTX-2 Cloud APIs & GPU Rental

Use cloud APIs when local hardware is insufficient or when you need fast turnaround
without managing infrastructure.

## Managed APIs

### LTX API (Official by Lightricks)

The official hosted API from the model creators.

- **Pricing:** $0.04-$0.08 per second of generated video (1080p)
- **Docs:** https://docs.ltx.video
- **Features:** Text-to-video, image-to-video, all official models, upscalers

```python
import requests

response = requests.post(
    "https://api.ltx.video/v1/generate",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={
        "prompt": "A cinematic shot of ocean waves crashing on volcanic rocks at sunset",
        "width": 1216,
        "height": 704,
        "num_frames": 97,
        "model": "ltx-2.3-22b-dev",
    },
)
result = response.json()
video_url = result["video_url"]
```

### fal.ai

Serverless inference platform with LTX-2 support.

- **Pricing:** ~$0.20 per video (varies by resolution/length)
- **Endpoint:** https://fal.ai/models/fal-ai/ltx-2/text-to-video/fast
- **Features:** Queue-based async generation, webhooks, fast cold starts

```python
import fal_client

# pip install fal-client
result = fal_client.subscribe(
    "fal-ai/ltx-2/text-to-video/fast",
    arguments={
        "prompt": "A golden retriever running through autumn leaves in a park",
        "num_frames": 97,
        "width": 1216,
        "height": 704,
    },
)
video_url = result["video"]["url"]
print(f"Video: {video_url}")
```

### Replicate

Container-based model hosting with pay-per-run pricing.

- **Pricing:** ~$0.10 per run (varies by hardware/duration)
- **Model:** https://replicate.com/lightricks/ltx-2-fast
- **Features:** Webhooks, streaming, version pinning

```python
import replicate

# pip install replicate
# export REPLICATE_API_TOKEN=your_token
output = replicate.run(
    "lightricks/ltx-2-fast",
    input={
        "prompt": "A cinematic aerial shot of a mountain range at golden hour",
        "num_frames": 97,
        "width": 1216,
        "height": 704,
    },
)
# output is a FileOutput URL
print(f"Video: {output}")
```

## Cloud GPU Rental

For running the full LTX-2 pipeline yourself with maximum control.

### RunPod

- **H100 SXM:** ~$2.49/hr (80 GB VRAM)
- **A100 80GB:** ~$1.64/hr
- **RTX 4090:** ~$0.44/hr (24 GB -- needs FP8 + distilled)
- **URL:** https://www.runpod.io
- Pre-built PyTorch templates available
- Persistent storage for model weights

### Vast.ai

- **Starting from:** ~$0.50/hr (community GPUs)
- **A100 80GB:** ~$1.00-1.50/hr
- **H100:** ~$2.00-3.00/hr
- **URL:** https://vast.ai
- Spot pricing (cheaper but interruptible)
- Docker-based, bring your own image

### Lambda Labs

- **H100:** ~$2.49/hr
- **A100 80GB:** ~$1.29/hr
- **URL:** https://lambdalabs.com/service/gpu-cloud
- Pre-installed CUDA/PyTorch environments

### Setup on Cloud GPU

```bash
# Generic cloud GPU setup (RunPod, Vast.ai, Lambda)
git clone https://github.com/Lightricks/LTX-2.git
cd LTX-2
pip install uv && uv sync --frozen
source .venv/bin/activate

# Download models (one-time, save to persistent storage)
python -c "
from huggingface_hub import snapshot_download
snapshot_download('Lightricks/LTX-2.3', local_dir='./models')
"

# Generate
python -m ltx_pipelines.run \
  --config configs/ltx-2.3-22b-dev-2stage.yaml \
  --prompt "Your prompt here" \
  --output output.mp4
```

## ComfyUI Cloud

Run ComfyUI workflows in the cloud without local GPU:

### Comfy Cloud (Official)

- **URL:** https://comfy.org/cloud
- Managed ComfyUI with GPU backend
- Upload workflows, run on-demand
- Pay per compute minute

### RunComfy

- **URL:** https://www.runcomfy.com
- Pre-configured ComfyUI machines
- LTX-Video nodes pre-installed
- Hourly pricing

## Cost Comparison

| Option | Cost per 5s Video | Latency | Setup Effort |
|--------|-------------------|---------|--------------|
| LTX API | $0.20-0.40 | ~30s | None (API key) |
| fal.ai | ~$0.20 | ~45s | None (API key) |
| Replicate | ~$0.10 | ~60s | None (API key) |
| RunPod H100 | ~$0.03* | ~15s | Medium (setup env) |
| Vast.ai A100 | ~$0.02* | ~20s | Medium (Docker) |
| Local RTX 4090 | Electricity only | ~20s | High (buy hardware) |
| Local Apple M4 Max | Electricity only | ~90s | Medium (MLX setup) |

*Amortized cost assuming continuous generation; actual cost includes idle time.

## Recommendation

- **Prototyping / low volume:** Use fal.ai or Replicate (no setup, per-run billing)
- **Production / high volume:** LTX API (official support, SLA) or self-hosted on RunPod
- **Maximum control:** Cloud GPU rental with persistent storage for model weights
- **Budget-sensitive:** Vast.ai spot instances or self-hosted with distilled + FP8
