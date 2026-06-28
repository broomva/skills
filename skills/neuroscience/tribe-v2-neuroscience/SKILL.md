---
name: tribe-v2-neuroscience
category: neuroscience
description: >
  In-silico neuroscience experiments using Meta's TRIBE v2 (TRansformer for In-silico Brain
  Experiments). Predicts fMRI cortical responses to video, audio, and text without brain scanners.
  Use when: (1) Designing and running virtual neuroscience experiments, (2) Predicting brain
  responses to stimuli, (3) Replicating classic neuroscience paradigms computationally,
  (4) Mapping which stimuli activate specific cortical regions (visual, auditory, language, DMN),
  (5) Testing hypotheses about neural processing before expensive fMRI studies,
  (6) Generating synthetic fMRI data for research, (7) Any task involving brain response
  prediction, cortical mapping, or computational neuroscience using TRIBE v2.
---

# TRIBE v2 Neuroscience

In-silico neuroscience using Meta FAIR's TRIBE v2 — predict fMRI cortical responses to video, audio, or text using a single pretrained transformer. Run experiments on any hardware, without a scanner.

## What TRIBE v2 Is

**TRansformer for In-silico Brain Experiments** (v2) is a brain encoding model released by Meta FAIR on March 26, 2026. It is **not** a language model — it predicts fMRI BOLD responses on the fsaverage5 cortical surface (~20,000 vertices per hemisphere) given multimodal sensory input.

Architecture:

```
Video  → V-JEPA2 (video encoder)
Audio  → Wav2Vec-BERT 2.0 (audio encoder)
Text   → LLaMA 3.2-3B (text encoder)
         ↓
   Unified Transformer
         ↓
   fsaverage5 mesh (~20k vertices)
   (n_timesteps × n_vertices)
```

Key properties:
- **70x** resolution improvement over TRIBE v1
- **2-3x** accuracy improvement, zero-shot generalization to new subjects
- **5-second temporal offset** built in — accounts for hemodynamic lag
- **Log-linear scaling** with fMRI training data (like LLMs with tokens)
- **License**: CC BY-NC 4.0 (non-commercial research only)
- **HuggingFace**: `facebook/tribev2`
- **Demo**: https://aidemos.atmeta.com/tribev2

---

## Quick Start

### 1. Install TRIBE v2

```bash
# Requires Python 3.11+
git clone https://github.com/facebookresearch/tribev2
cd tribev2
pip install -e .
```

### 2. Load the Model

```python
from tribev2 import TribeModel

model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./cache")
```

The first load downloads model weights (~7GB). Subsequent loads use the cache.

### 3. Run Your First Prediction

```python
# Video input (returns DataFrame of events)
df = model.get_events_dataframe(video_path="stimulus.mp4")

# Text input
df = model.get_events_dataframe(text_path="transcript.txt")

# Audio input
df = model.get_events_dataframe(audio_path="audio.wav")

# Predict cortical responses
preds, segments = model.predict(events=df)

# Output shape: (n_timesteps, n_vertices)
# n_vertices ≈ 20,484 on fsaverage5
print(preds.shape)   # e.g., (142, 20484)
print(segments)      # list of segment boundaries in seconds
```

---

## Workflow A: Single Stimulus Prediction

**Trigger**: You have one video, audio clip, or transcript and want to know which brain regions activate.

```python
from tribev2 import TribeModel
import numpy as np
import pandas as pd

# Load model
model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./cache")

# Load stimulus (choose one modality)
df = model.get_events_dataframe(video_path="face_stimulus.mp4")
# df = model.get_events_dataframe(audio_path="speech.wav")
# df = model.get_events_dataframe(text_path="story.txt")

# Predict
preds, segments = model.predict(events=df)
# preds: numpy array (n_timesteps, n_vertices)

# Find peak activation timestep
peak_t = np.argmax(preds.mean(axis=1))
peak_activations = preds[peak_t, :]

# Top-10 most activated vertices at peak
top_verts = np.argsort(peak_activations)[-10:][::-1]
print(f"Peak timestep: {peak_t} (~{peak_t * 1.5:.1f}s)")
print(f"Top vertices: {top_verts}")
print(f"Peak activation values: {peak_activations[top_verts]}")

# Regional mean activations (using known fsaverage5 ranges)
REGIONS = {
    "V1_left":  (0, 1500),
    "FFA_right": (9900, 10400),
    "A1_left":  (3500, 4200),
    "Broca_left": (6200, 6800),
    "DMN_mPFC": (14000, 15000),
}

for region, (v_start, v_end) in REGIONS.items():
    region_mean = preds[:, v_start:v_end].mean()
    print(f"  {region}: mean activation = {region_mean:.4f}")
```

Use the [Cortical Atlas](references/brain-regions.md) to interpret which vertices correspond to which regions.

---

## Workflow B: Virtual Experiment

**Trigger**: You want to compare brain responses across multiple stimuli — e.g., faces vs. objects vs. scenes.

```python
from tribev2 import TribeModel
import numpy as np
import pandas as pd
from pathlib import Path

model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./cache")

# Define your stimulus set
stimuli = {
    "faces":   "stimuli/faces.mp4",
    "scenes":  "stimuli/scenes.mp4",
    "objects": "stimuli/objects.mp4",
    "baseline": "stimuli/scrambled.mp4",
}

# Define regions of interest (vertex ranges on fsaverage5)
ROIS = {
    "FFA_right": (9900, 10400),    # Fusiform Face Area
    "PPA_right": (10400, 11000),   # Parahippocampal Place Area
    "LOC_right": (8800, 9500),     # Lateral Occipital Complex
    "EBA_right": (9500, 9900),     # Extrastriate Body Area
}

results = []

for condition, path in stimuli.items():
    df = model.get_events_dataframe(video_path=path)
    preds, _ = model.predict(events=df)
    
    for roi_name, (v_start, v_end) in ROIS.items():
        roi_activation = preds[:, v_start:v_end].mean()
        results.append({
            "condition": condition,
            "roi": roi_name,
            "mean_activation": roi_activation,
            "peak_activation": preds[:, v_start:v_end].max(),
        })

# Analyze
df_results = pd.DataFrame(results)
pivot = df_results.pivot(index="condition", columns="roi", values="mean_activation")
print(pivot)

# Expected result for face selectivity:
# FFA_right should be highest for "faces" condition
# PPA_right should be highest for "scenes" condition
```

Use `scripts/run_experiment.py` to automate this over a directory of stimuli.

---

## Workflow C: Paradigm Replication

**Trigger**: You want to replicate a classic neuroscience finding in-silico before running a real fMRI study.

Example: Replicating face selectivity in the Fusiform Face Area (Kanwisher 1997).

```python
from tribev2 import TribeModel
import numpy as np

model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./cache")

# Kanwisher 1997: faces >> objects in FFA
# FFA is right-lateralized, ~vertices 9900-10400 (fsaverage5)
FFA_RIGHT = (9900, 10400)
FFA_LEFT  = (1100, 1600)   # smaller response expected

face_df   = model.get_events_dataframe(video_path="faces_stimulus.mp4")
object_df = model.get_events_dataframe(video_path="objects_stimulus.mp4")

face_preds,   _ = model.predict(events=face_df)
object_preds, _ = model.predict(events=object_df)

# Compute selectivity index
def roi_mean(preds, vertex_range):
    v_start, v_end = vertex_range
    return preds[:, v_start:v_end].mean()

face_ffa_r   = roi_mean(face_preds, FFA_RIGHT)
object_ffa_r = roi_mean(object_preds, FFA_RIGHT)
face_ffa_l   = roi_mean(face_preds, FFA_LEFT)

selectivity_index = (face_ffa_r - object_ffa_r) / (face_ffa_r + object_ffa_r + 1e-8)

print(f"FFA-right (faces):   {face_ffa_r:.4f}")
print(f"FFA-right (objects): {object_ffa_r:.4f}")
print(f"FFA-left  (faces):   {face_ffa_l:.4f}")
print(f"Selectivity index:   {selectivity_index:.4f}")

# Positive selectivity_index = FFA prefers faces
# Right > Left = expected right lateralization
# This replicates Kanwisher 1997 in-silico
```

See [paradigm-library.md](references/paradigm-library.md) for 8 fully documented paradigms with expected results and vertex ranges.

---

## Workflow D: Hypothesis Testing

**Trigger**: You have a hypothesis like "visual cortex responds to motion but not to static images" and want to test it computationally.

### Step 1: Define your hypothesis formally

```
H0: mean_activation(MT_right, motion_video) == mean_activation(MT_right, static_image_video)
H1: mean_activation(MT_right, motion_video) > mean_activation(MT_right, static_image_video)
Region: MT/V5 right hemisphere, vertices 7800-8200 (approx fsaverage5)
```

### Step 2: Generate contrasting stimuli

The stimuli must differ **only** on the dimension you're testing. For motion vs. static:
- Motion: videos with global optic flow (dot fields, moving gratings)
- Static: same scene photographed repeatedly (no temporal change)

### Step 3: Run predictions and compute the contrast

```python
from tribev2 import TribeModel
import numpy as np
from scipy import stats

model = TribeModel.from_pretrained("facebook/tribev2", cache_folder="./cache")

MT_RIGHT = (7800, 8200)

# Multiple clips per condition for effect size estimation
motion_clips  = ["motion_01.mp4", "motion_02.mp4", "motion_03.mp4"]
static_clips  = ["static_01.mp4", "static_02.mp4", "static_03.mp4"]

def get_roi_activation(clips, roi):
    activations = []
    for clip in clips:
        df = model.get_events_dataframe(video_path=clip)
        preds, _ = model.predict(events=df)
        v_start, v_end = roi
        activations.append(preds[:, v_start:v_end].mean())
    return np.array(activations)

motion_acts = get_roi_activation(motion_clips, MT_RIGHT)
static_acts = get_roi_activation(static_clips, MT_RIGHT)

# One-tailed t-test
t_stat, p_val = stats.ttest_ind(motion_acts, static_acts, alternative='greater')
effect_size   = (motion_acts.mean() - static_acts.mean()) / np.std(np.concatenate([motion_acts, static_acts]))

print(f"Motion MT activation:  {motion_acts.mean():.4f} ± {motion_acts.std():.4f}")
print(f"Static MT activation:  {static_acts.mean():.4f} ± {static_acts.std():.4f}")
print(f"t = {t_stat:.3f}, p = {p_val:.4f}")
print(f"Cohen's d = {effect_size:.3f}")
print(f"H1 supported: {p_val < 0.05 and t_stat > 0}")
```

### Step 4: Interpret and decide whether to proceed to real fMRI

If the in-silico result supports H1 with d > 0.5, the effect size is large enough to power a real study. Use TRIBE v2 output to:
- Estimate required sample size (TRIBE v2 predictions correlate with real fMRI at r~0.6-0.8)
- Identify best ROIs to measure in-scanner
- Pre-register your analysis plan

---

## Output Interpretation

### Shape: `(n_timesteps, n_vertices)`

```python
preds, segments = model.predict(events=df)

# preds.shape[0] = number of TRs (fMRI volumes)
#   Each TR ≈ 1.5 seconds (typical fMRI repetition time)
#   Total duration covered = n_timesteps × 1.5s

# preds.shape[1] = 20,484 vertices (fsaverage5 surface)
#   Vertices 0–10,241      = Left hemisphere
#   Vertices 10,242–20,483 = Right hemisphere
```

### What the values mean

TRIBE v2 outputs **z-scored BOLD signal predictions** in arbitrary units:
- `0.0` = mean response for this brain region (no activation above baseline)
- `> 0` = above-average activation
- `< 0` = below-average (suppression or deactivation)
- Typical range: `[-3.0, 3.0]`

### The 5-second temporal offset

TRIBE v2 automatically applies a +5s hemodynamic lag. The prediction at timestep `t` reflects neural processing that occurred at `t - 5s` in the stimulus. You do not need to manually shift; the model handles this.

### Vertex-to-region mapping

fsaverage5 has 10,242 vertices per hemisphere. Key landmarks:

```
Left hemisphere (vertices 0–10,241):
  V1/V2 primary visual:    0–1,500
  V3/V4 ventral stream:   1,500–3,000
  MT/V5 motion:           2,800–3,200
  A1 primary auditory:    3,500–4,200
  Broca's area (44/45):   6,200–6,800
  VWFA (word form):       7,100–7,500

Right hemisphere (vertices 10,242–20,483):
  V1/V2 primary visual:  10,242–11,742
  FFA (face area):        9,900–10,400  ← note: RH vertex numbers
  PPA (place area):      10,400–11,000
  A1 primary auditory:   13,742–14,442
```

See [references/brain-regions.md](references/brain-regions.md) for the full atlas with all regions, hemispheres, and vertex ranges.

### Segments

```python
preds, segments = model.predict(events=df)
# segments: list of (start_sec, end_sec) tuples
# Corresponds to natural scene/speech boundaries the model detected
# Useful for aligning predictions to stimulus timing
```

---

## Using the Companion Scripts

### Single Prediction

```bash
python scripts/predict_brain.py \
  --input stimulus.mp4 \
  --modality video \
  --output results/predictions.csv \
  --cache-dir ./model-cache
```

Output CSV columns: `timestep`, `vertex_id`, `predicted_activation`

Also prints top-5 vertices at peak timestep to stdout.

### Batch Experiment

```bash
python scripts/run_experiment.py \
  --stimuli-dir stimuli/faces/ \
  --modality video \
  --output-dir results/face_experiment/ \
  --region FFA_right
```

Output CSV: `stimulus_file`, `region`, `mean_activation`, `peak_timestep`

---

## Common Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| `preds.shape[1]` != 20484 | Wrong surface resolution | Verify `facebook/tribev2` loaded, not v1 |
| All activations near 0 | Stimulus too short | Use clips > 10 seconds; TRIBE v2 needs sufficient temporal context |
| Right-hemisphere FFA vertex range seems off | Vertex indexing | RH vertices start at 10,242; FFA_right is still ~9,900-10,400 in the combined array |
| Memory error on GPU | Long video, full batch | Pass `--chunk-duration 30` to process in 30s windows |
| `get_events_dataframe` fails on audio | Wrong sample rate | Convert to 16kHz mono WAV first: `ffmpeg -i input.mp4 -ar 16000 -ac 1 audio.wav` |

---

## Detailed References

- **[references/brain-regions.md](references/brain-regions.md)** — Full cortical atlas: every region, hemisphere, fsaverage5 vertex range, and what activates it
- **[references/paradigm-library.md](references/paradigm-library.md)** — 8 classic paradigms with TRIBE v2 replication protocols and expected results
- **[scripts/predict_brain.py](scripts/predict_brain.py)** — CLI for single-stimulus prediction with CSV output
- **[scripts/run_experiment.py](scripts/run_experiment.py)** — Batch multi-stimulus experiment runner with region-averaged output
