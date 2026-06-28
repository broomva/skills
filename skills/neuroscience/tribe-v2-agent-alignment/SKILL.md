---
name: tribe-v2-agent-alignment
category: neuroscience
description: >
  Use Meta's TRIBE v2 brain encoder to validate cortical alignment of AI model representations
  (LLaMA, V-JEPA2, Wav2Vec, or any encoder) and inform model selection in the Life/Arcan agent OS stack.
  Use when: (1) Benchmarking whether a new model encoder aligns with human cortical processing,
  (2) Comparing text encoders by language cortex alignment score, (3) Comparing video encoders
  by visual cortex alignment score, (4) Integrating neuro-alignment scores into Arcan model routing,
  (5) Validating that a fine-tuned model has not lost biological plausibility, (6) Selecting the
  most brain-aligned encoder for a given modality in the agent OS, (7) Any task involving
  neuroscience-informed AI model evaluation, cortical alignment benchmarking, or biologically-inspired model selection.
---

# TRIBE v2 Agent Alignment

Validate whether your AI encoders — text, video, or audio — represent information the way human brains do, using Meta's TRIBE v2 cortical predictor. Use the resulting alignment scores to drive neuro-informed model routing in Life/Arcan.

## Concept

Cortical alignment measures how well an AI encoder's hidden states predict actual fMRI brain activity in response to the same stimulus. TRIBE v2 (TRansformer for In-silico Brain Experiments) was trained on thousands of hours of naturalistic fMRI data and can predict activity across the full cortical surface (~20k vertices on the fsaverage5 mesh) for any text, video, or audio input. A high alignment score (R² > 0.25) means the encoder has learned representations that are geometrically similar to what the human language, visual, or auditory cortex computes — without any explicit neuroscience objective. This matters for model selection in an agent OS: a text encoder with higher language cortex alignment tends to generalize better to novel linguistic contexts, is more robust to distribution shift, and exhibits better zero-shot transfer. TRIBE v2 proved that LLaMA 3.2-3B spontaneously developed such alignment, validating its representations neurologically. The same benchmark can be applied to any candidate encoder before committing it to Arcan's routing stack.

## Quick Start

Run a full alignment score for any encoder in 5 commands:

```bash
# 1. Install dependencies
pip install tribev2 transformers torch scikit-learn numpy

# 2. Prepare a stimulus directory (video files for video, text files for text, wav for audio)
mkdir -p ~/stimuli/text && echo "The model routed the task to the visual cortex." > ~/stimuli/text/s1.txt

# 3. Run alignment against LLaMA 3.2-3B (text encoder baseline)
python scripts/align_encoder.py \
  --encoder-type text \
  --encoder-model meta-llama/Llama-3.2-3B \
  --stimulus-dir ~/stimuli/text \
  --output ~/results/llama_alignment.json

# 4. Run alignment against a competing encoder
python scripts/align_encoder.py \
  --encoder-type text \
  --encoder-model bert-base-uncased \
  --stimulus-dir ~/stimuli/text \
  --output ~/results/bert_alignment.json

# 5. Compare scores
python -c "
import json
llama = json.load(open('~/results/llama_alignment.json'))['alignment_score']
bert  = json.load(open('~/results/bert_alignment.json'))['alignment_score']
winner = 'LLaMA 3.2' if llama > bert else 'BERT'
print(f'LLaMA 3.2: {llama:.3f}  |  BERT: {bert:.3f}  |  Winner: {winner}')
"
```

## Workflow A: Text Encoder Alignment

Compare any two text encoders by their language cortex alignment score. Language cortex vertices cover Broca's area (~vertex 15000-18000, left hemisphere) and Wernicke's area (~vertex 12000-15000, left hemisphere) on the fsaverage5 mesh.

### Step 1 — Prepare Text Stimuli

Text stimuli should be naturalistic sentences or paragraphs (not short keywords). TRIBE v2 was trained on narrative speech transcripts; similar inputs yield the most reliable alignment estimates.

```bash
mkdir -p ~/stimuli/text
cat > ~/stimuli/text/naturalistic_en.txt << 'EOF'
The surgeon carefully examined the patient before the procedure.
Language emerges from a distributed network spanning frontal and temporal lobes.
The model predicted activation in Broca's area when processing syntactically complex sentences.
EOF
```

### Step 2 — Run Alignment for Each Encoder

```bash
# Baseline: TRIBE v2's own text encoder (LLaMA 3.2-3B) — expect ~0.40 R²
python scripts/align_encoder.py \
  --encoder-type text \
  --encoder-model meta-llama/Llama-3.2-3B \
  --stimulus-dir ~/stimuli/text \
  --output ~/results/llama32_align.json

# Candidate A: Mistral 7B
python scripts/align_encoder.py \
  --encoder-type text \
  --encoder-model mistralai/Mistral-7B-v0.1 \
  --stimulus-dir ~/stimuli/text \
  --output ~/results/mistral7b_align.json

# Candidate B: sentence-transformers (smaller, faster)
python scripts/align_encoder.py \
  --encoder-type text \
  --encoder-model sentence-transformers/all-mpnet-base-v2 \
  --stimulus-dir ~/stimuli/text \
  --output ~/results/mpnet_align.json
```

### Step 3 — Interpret and Route

```python
import json, pathlib

results = {}
for p in pathlib.Path("~/results").expanduser().glob("*_align.json"):
    d = json.loads(p.read_text())
    results[d["encoder"]] = d["alignment_score"]

best = max(results, key=results.get)
print("Alignment scores (language cortex R²):")
for enc, score in sorted(results.items(), key=lambda x: -x[1]):
    flag = " <-- route here" if enc == best else ""
    print(f"  {enc:55s} {score:.3f}{flag}")
```

### Text Encoder Comparison Table

| Encoder | Type | Expected R² | Language Cortex Fit |
|---------|------|-------------|---------------------|
| LLaMA 3.2-3B | Autoregressive LM | ~0.40 | Excellent |
| Mistral 7B | Autoregressive LM | ~0.35-0.40 | Excellent |
| GPT-2 (medium) | Autoregressive LM | ~0.25-0.30 | Good |
| BERT-base | Masked LM | ~0.15-0.22 | Moderate |
| all-mpnet-base-v2 | Sentence encoder | ~0.10-0.18 | Moderate |
| Random linear encoder | Baseline | ~0.00-0.03 | Poor |

## Workflow B: Video Encoder Alignment

Compare video encoders by their visual cortex alignment. Visual cortex vertices cover V1-V4 (~vertex 1000-5000) and motion-selective areas MT/MST (~vertex 5000-8000) on fsaverage5.

### Step 1 — Prepare Video Stimuli

Use naturalistic video clips (not slideshows). MP4 format, 1-5 minutes each. TRIBE v2 segments at 5-second windows internally.

```bash
mkdir -p ~/stimuli/video
# Download a CC-licensed short clip, or use any .mp4 you have:
# ffmpeg -i source.mp4 -t 120 -c copy ~/stimuli/video/clip01.mp4
```

### Step 2 — Run Alignment

```bash
# Baseline: TRIBE v2's own video encoder (V-JEPA2 ViT-G) — expect high visual cortex alignment
python scripts/align_encoder.py \
  --encoder-type video \
  --encoder-model facebook/vjepa2-vitg-fpc64-256 \
  --stimulus-dir ~/stimuli/video \
  --output ~/results/vjepa2_align.json

# Candidate: CLIP ViT-L/14
python scripts/align_encoder.py \
  --encoder-type video \
  --encoder-model openai/clip-vit-large-patch14 \
  --stimulus-dir ~/stimuli/video \
  --output ~/results/clip_vitl_align.json

# Candidate: VideoMAE-v2 (ViT-G, action recognition)
python scripts/align_encoder.py \
  --encoder-type video \
  --encoder-model MCG-NJU/videomae-huge \
  --stimulus-dir ~/stimuli/video \
  --output ~/results/videomae_align.json
```

### Step 3 — Check Emergent Networks

TRIBE v2 spontaneously recovers 5 functional brain networks. Verify the visual encoder activates the correct one:

```python
import json
result = json.load(open("~/results/vjepa2_align.json"))
print(f"Alignment score: {result['alignment_score']:.3f}")
print(f"Top cortical regions: {result['top_regions']}")
# Expected output for video: top_regions includes 'visual_cortex' vertices 1000-8000
```

### Video Encoder Comparison Table

| Encoder | Architecture | Expected Visual R² | Motion Sensitivity |
|---------|-------------|-------------------|-------------------|
| V-JEPA2 (ViT-G) | Masked video prediction | High (>0.35) | High |
| VideoMAE-v2 (ViT-H) | Masked video prediction | High (>0.30) | High |
| CLIP ViT-L/14 | Contrastive image-text | Moderate (0.20-0.28) | Low |
| DINO ViT-B/16 | Self-supervised image | Moderate (0.15-0.22) | Low |
| Random CNN baseline | — | Near-zero | None |

## Workflow C: Arcan Integration

Use alignment scores stored in Lago to configure Arcan's model routing at task dispatch time.

### Step 1 — Cache Scores in Lago

After running `align_encoder.py`, push scores into Lago's alignment table:

```python
import json, datetime
import lago  # Life/Lago Python client

scores = {}
for path in ["llama32_align.json", "mistral7b_align.json"]:
    d = json.load(open(path))
    scores[d["encoder"]] = {
        "modality": d["modality"],
        "alignment_score": d["alignment_score"],
        "top_regions": d["top_regions"],
        "evaluated_at": datetime.datetime.utcnow().isoformat(),
    }

lago.write("broomva.arcan.encoder_alignment", scores)
```

### Step 2 — Declare Routing Weights in Arcan Config

Add alignment-driven routing to `~/.config/arcan/routing.toml`:

```toml
[routing.text]
strategy = "neuro_alignment"
alignment_table = "broomva.arcan.encoder_alignment"
modality = "text"
fallback = "meta-llama/Llama-3.2-3B"
min_score = 0.15          # reject encoders below this threshold

[routing.video]
strategy = "neuro_alignment"
alignment_table = "broomva.arcan.encoder_alignment"
modality = "video"
fallback = "facebook/vjepa2-vitg-fpc64-256"
min_score = 0.20

[routing.audio]
strategy = "neuro_alignment"
alignment_table = "broomva.arcan.encoder_alignment"
modality = "audio"
fallback = "facebook/w2v-bert-2.0"
min_score = 0.10
```

### Step 3 — Routing Logic (Pseudocode)

```python
# arcan/src/routing/neuro_alignment.py

def select_encoder(task: Task, alignment_table: dict) -> str:
    """Return the highest-alignment encoder for this task's modality."""
    modality = task.modality  # "text", "video", or "audio"
    candidates = {
        enc: data["alignment_score"]
        for enc, data in alignment_table.items()
        if data["modality"] == modality
           and data["alignment_score"] >= MIN_SCORE[modality]
    }
    if not candidates:
        return FALLBACK[modality]
    return max(candidates, key=candidates.get)

# Called at every task dispatch:
encoder = select_encoder(task, lago.read("broomva.arcan.encoder_alignment"))
result = arcan.run(task, encoder=encoder)
```

### Step 4 — Re-Evaluation Triggers

| Trigger | Action |
|---------|--------|
| New model release | Run `align_encoder.py`, update Lago table |
| Fine-tune completes | Re-run alignment; validate score did not degrade |
| Score staleness > 30 days | Scheduled re-evaluation via Autonomic |
| Alignment score drops > 0.05 | Alert via Autonomic + rollback to previous encoder |

```bash
# Autonomic watchdog (add to autonomic/config/watches.toml):
# [watch.encoder_alignment]
# table = "broomva.arcan.encoder_alignment"
# check = "alignment_score"
# threshold_drop = 0.05
# action = "rollback_and_alert"
```

## Alignment Score Interpretation

| R² Range | Label | Interpretation | Action |
|----------|-------|----------------|--------|
| > 0.40 | Excellent | Encoder matches cortical representations at TRIBE v2 baseline level | Use as primary encoder |
| 0.25 – 0.40 | Good | Meaningful alignment; encoder captures most modality-relevant features | Use; monitor over time |
| 0.10 – 0.25 | Moderate | Partial alignment; encoder may miss higher-level semantic features | Use only if no better option |
| < 0.10 | Poor | Near-random; encoder does not capture brain-relevant information | Do not use for this modality |

**Important caveats:**
- Scores are population-average predictions from TRIBE v2's training cohort. Individual subject variability can shift scores ±0.05.
- TRIBE v2 operates on 5-second temporal windows. Encoders that produce token-level representations need temporal pooling before probing.
- The linear ridge regression probe (see `scripts/align_encoder.py`) measures linear decodability, not representational isomorphism. High R² means the encoder's representations are linearly predictive of cortical activity, which is the standard encoding model benchmark in computational neuroscience.
- License constraint: TRIBE v2 is CC BY-NC 4.0. Alignment scores derived from it cannot be used in commercial products without a separate agreement with Meta.

## Reference Files

- [references/encoder-alignment.md](references/encoder-alignment.md) — Methodology, known baseline scores, modality-to-region mapping, limitations
- [references/arcan-integration.md](references/arcan-integration.md) — Full integration guide, TOML config schema, Lago caching, re-evaluation workflow
