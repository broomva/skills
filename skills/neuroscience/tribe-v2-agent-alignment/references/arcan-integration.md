# Arcan Integration — Neuro-Informed Model Routing

How to wire TRIBE v2 alignment scores into the Life/Arcan model routing layer for biologically-informed encoder selection at task dispatch time.

---

## 1. Overview

Arcan is the AI orchestration layer in the Life monorepo (`core/life/arcan/`). It receives tasks from aiOS, selects the appropriate model/encoder, calls tools, and returns results. Today, routing decisions are driven by:
- Task type (generation, embedding, classification)
- Cost budget
- Latency SLA
- Model capability flags (context window, multimodal support)

TRIBE v2 alignment scores add a fifth dimension: **biological plausibility** — does this encoder represent the stimulus the way a human brain would? Encoders with higher language cortex alignment tend to generalize better to novel linguistic inputs, while high visual cortex alignment predicts better zero-shot scene understanding.

The integration flow:

```
New model released
      |
      v
run align_encoder.py  --> alignment_score JSON
      |
      v
lago.write("arcan.encoder_alignment")
      |
      v
Arcan routing reads alignment table at task dispatch
      |
      v
Route to highest-alignment encoder meeting cost/latency constraints
```

Alignment scores are computed offline (not per-request) and cached in Lago. The routing decision adds negligible latency (a single Lago table read, typically < 1ms local).

---

## 2. Configuration Format

Declare alignment-aware routing in Arcan's routing configuration file (`~/.config/arcan/routing.toml` or `core/life/arcan/config/routing.toml`):

```toml
# routing.toml — Arcan model routing configuration

[routing.defaults]
cost_budget = "medium"          # low / medium / high
latency_sla_ms = 2000
enable_neuro_alignment = true   # set false to disable alignment-based routing

# Text task routing
[routing.text]
strategy = "neuro_alignment"
alignment_table = "broomva.arcan.encoder_alignment"
modality = "text"
fallback_model = "meta-llama/Llama-3.2-3B"
min_alignment_score = 0.15     # reject models below this R^2

# Video task routing
[routing.video]
strategy = "neuro_alignment"
alignment_table = "broomva.arcan.encoder_alignment"
modality = "video"
fallback_model = "facebook/vjepa2-vitg-fpc64-256"
min_alignment_score = 0.20

# Audio task routing
[routing.audio]
strategy = "neuro_alignment"
alignment_table = "broomva.arcan.encoder_alignment"
modality = "audio"
fallback_model = "facebook/w2v-bert-2.0"
min_alignment_score = 0.10

# Model registry: declare all available encoders with their metadata
[models.text]
"meta-llama/Llama-3.2-3B"      = { cost = "low",    latency = "medium", context = 131072 }
"mistralai/Mistral-7B-v0.1"    = { cost = "medium",  latency = "medium", context = 32768  }
"bert-base-uncased"             = { cost = "low",    latency = "low",    context = 512    }

[models.video]
"facebook/vjepa2-vitg-fpc64-256"   = { cost = "high",   latency = "high",   fps = 64 }
"openai/clip-vit-large-patch14"    = { cost = "medium",  latency = "medium", fps = 1  }
"MCG-NJU/videomae-huge"            = { cost = "high",   latency = "high",   fps = 16 }

[models.audio]
"facebook/w2v-bert-2.0"            = { cost = "medium", latency = "medium" }
"facebook/wav2vec2-large-960h"     = { cost = "medium", latency = "medium" }
```

### YAML Alternative

If your Arcan config uses YAML:

```yaml
routing:
  defaults:
    cost_budget: medium
    latency_sla_ms: 2000
    enable_neuro_alignment: true

  text:
    strategy: neuro_alignment
    alignment_table: broomva.arcan.encoder_alignment
    modality: text
    fallback_model: meta-llama/Llama-3.2-3B
    min_alignment_score: 0.15

  video:
    strategy: neuro_alignment
    alignment_table: broomva.arcan.encoder_alignment
    modality: video
    fallback_model: facebook/vjepa2-vitg-fpc64-256
    min_alignment_score: 0.20

  audio:
    strategy: neuro_alignment
    alignment_table: broomva.arcan.encoder_alignment
    modality: audio
    fallback_model: facebook/w2v-bert-2.0
    min_alignment_score: 0.10
```

---

## 3. Routing Logic

The neuro-alignment routing strategy implemented in Arcan:

```python
# core/life/arcan/src/routing/neuro_alignment.py

from dataclasses import dataclass
from typing import Optional
import lago  # Life/Lago Python client

MIN_SCORE = {"text": 0.15, "video": 0.20, "audio": 0.10}
FALLBACK_MODEL = {
    "text": "meta-llama/Llama-3.2-3B",
    "video": "facebook/vjepa2-vitg-fpc64-256",
    "audio": "facebook/w2v-bert-2.0",
}


@dataclass
class Task:
    modality: str               # "text", "video", "audio"
    cost_budget: str            # "low", "medium", "high"
    latency_sla_ms: int
    requires_language: bool = False
    requires_motion: bool = False


def select_encoder(task: Task, alignment_table: dict, model_registry: dict) -> str:
    """
    Select the highest-alignment encoder that fits within cost/latency constraints.
    Falls back to the configured fallback model if no alignment data is available.
    """
    modality = task.modality
    min_score = MIN_SCORE.get(modality, 0.0)
    available_models = model_registry.get(modality, {})

    # Filter: must have alignment data and meet minimum score
    candidates = []
    for model_id, meta in available_models.items():
        if model_id not in alignment_table:
            continue
        score = alignment_table[model_id].get("alignment_score", 0.0)
        if score < min_score:
            continue
        # Filter by cost budget
        model_cost = meta.get("cost", "high")
        if not _cost_fits(model_cost, task.cost_budget):
            continue
        # Filter by latency
        model_latency_ms = meta.get("latency_ms", 5000)
        if model_latency_ms > task.latency_sla_ms:
            continue
        candidates.append((model_id, score))

    if not candidates:
        return FALLBACK_MODEL.get(modality, "meta-llama/Llama-3.2-3B")

    # Sort by alignment score descending; pick the top candidate
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected, score = candidates[0]
    return selected


def _cost_fits(model_cost: str, budget: str) -> bool:
    """Return True if model cost tier fits within the task budget."""
    tiers = {"low": 0, "medium": 1, "high": 2}
    return tiers.get(model_cost, 2) <= tiers.get(budget, 1)


# Called at task dispatch time in Arcan's main routing loop:
def route_task(task: Task) -> str:
    alignment_table = lago.read("broomva.arcan.encoder_alignment")
    model_registry = lago.read("broomva.arcan.model_registry")
    return select_encoder(task, alignment_table, model_registry)
```

### Decision Tree

```
Task arrives at Arcan dispatcher
├── Determine modality (text / video / audio)
├── Read alignment_table from Lago cache
│   └── If cache_age > 30 days: trigger async re-evaluation, use stale data
├── Filter candidates by min_alignment_score
├── Filter candidates by cost_budget and latency_sla
├── Sort remaining by alignment_score descending
├── Return top candidate
└── If no candidates: return FALLBACK_MODEL[modality]
```

---

## 4. Score Caching in Lago

Alignment scores are stable until a new model version is released or fine-tuning occurs. Cache them in Lago's `broomva.arcan.encoder_alignment` table:

```python
# scripts/push_alignment_to_lago.py
# Run after align_encoder.py to update the Lago routing table.

import json
import datetime
import pathlib
import lago

RESULTS_DIR = pathlib.Path("./results")
TABLE_NAME = "broomva.arcan.encoder_alignment"


def push_results():
    current = {}
    try:
        current = lago.read(TABLE_NAME) or {}
    except Exception:
        pass  # Table may not exist yet

    for result_path in RESULTS_DIR.glob("*_align.json"):
        data = json.loads(result_path.read_text())
        encoder_id = data["encoder"]
        current[encoder_id] = {
            "alignment_score": data["alignment_score"],
            "modality": data["modality"],
            "interpretation": data["interpretation"],
            "roi_label": data["roi_label"],
            "top_regions": data["top_regions"],
            "evaluated_at": datetime.datetime.utcnow().isoformat(),
            "n_stimuli": data["n_stimuli"],
            "tribe_model": data["tribe_model"],
        }

    lago.write(TABLE_NAME, current)
    print("Pushed {} encoder alignment records to Lago.".format(len(current)))
    for enc, rec in sorted(current.items(), key=lambda x: -x[1]["alignment_score"]):
        print("  {:.3f}  {}  ({})".format(rec["alignment_score"], enc, rec["modality"]))


if __name__ == "__main__":
    push_results()
```

### Lago Table Schema

```
broomva.arcan.encoder_alignment
├── key: encoder_id (str)         -- HuggingFace model ID
├── alignment_score (float)       -- mean R^2 from ridge probe
├── modality (str)                -- text / video / audio
├── interpretation (str)          -- poor / moderate / good / excellent
├── roi_label (str)               -- language_cortex / visual_cortex / auditory_cortex
├── top_regions (list[dict])      -- top-5 vertices with highest alignment
├── evaluated_at (ISO timestamp)  -- when the score was computed
├── n_stimuli (int)               -- stimulus count used for evaluation
└── tribe_model (str)             -- "facebook/tribev2"
```

---

## 5. Re-Evaluation Triggers

| Trigger | Action | Automation |
|---------|--------|-----------|
| New model release (HuggingFace) | Run align_encoder.py for new model; push to Lago | Manual (prompted by BRO ticket) |
| Fine-tuning completes | Re-run alignment on fine-tuned checkpoint; compare to pre-tune score | CI hook in training pipeline |
| Score staleness > 30 days | Scheduled re-evaluation for all models in routing table | Autonomic watchdog |
| Alignment score drops > 0.05 vs previous | Alert + automatic rollback to previous best encoder | Autonomic watchdog |
| New modality added to task space | Run alignment for that modality's ROI | Manual |

### Autonomic Watchdog Configuration

Add to `core/life/autonomic/config/watches.toml`:

```toml
[watch.encoder_alignment_staleness]
description = "Re-evaluate alignment if any encoder score is stale"
table = "broomva.arcan.encoder_alignment"
check_field = "evaluated_at"
max_age_days = 30
action = "trigger_skill"
skill = "tribe-v2-agent-alignment"
command = "python scripts/align_encoder.py --encoder-type {modality} --encoder-model {encoder_id} --stimulus-dir ./stimuli/{modality} --output ./results/{encoder_id_safe}_align.json"

[watch.encoder_alignment_regression]
description = "Alert and rollback if alignment score drops significantly"
table = "broomva.arcan.encoder_alignment"
check_field = "alignment_score"
threshold_drop = 0.05
action = "rollback_and_alert"
alert_channel = "agent-logs"
rollback_table = "broomva.arcan.encoder_alignment_history"
```

---

## 6. End-to-End Workflow: New Model Integration

Full workflow when a new text encoder (e.g., LLaMA 3.3-8B) is released:

```bash
# Step 1: Pull the new model (or it will be downloaded by align_encoder.py)
huggingface-cli download meta-llama/Llama-3.3-8B --local-dir ./models/llama-3.3-8b

# Step 2: Run cortical alignment benchmark
python scripts/align_encoder.py \
  --encoder-type text \
  --encoder-model meta-llama/Llama-3.3-8B \
  --stimulus-dir ./stimuli/text \
  --output ./results/llama33_align.json \
  --cv-splits 5

# Step 3: Inspect the result
python -c "
import json
r = json.load(open('./results/llama33_align.json'))
print('Encoder:', r['encoder'])
print('Alignment score:', r['alignment_score'], '(' + r['interpretation'] + ')')
print('Top regions:', r['top_regions'][:2])
"

# Step 4: Compare to current best encoder
python -c "
import json, glob
scores = {}
for p in glob.glob('./results/*_align.json'):
    d = json.load(open(p))
    if d['modality'] == 'text':
        scores[d['encoder']] = d['alignment_score']
for enc, s in sorted(scores.items(), key=lambda x: -x[1]):
    print(f'{s:.3f}  {enc}')
"

# Step 5: Push to Lago
python scripts/push_alignment_to_lago.py

# Step 6: Arcan will automatically pick up the new scores on next task dispatch.
# Verify by checking the routing decision for a test task:
arcan route --task-type language_understanding --modality text --dry-run
# Expected output: Selected encoder: meta-llama/Llama-3.3-8B (score: 0.XXX)

# Step 7: Monitor for regressions via Autonomic (automatically watches alignment table)
arcan status --watch encoder_alignment
```

### Rollback Procedure

If alignment regression is detected after switching to a new model:

```bash
# View alignment history
lago query "SELECT encoder, alignment_score, evaluated_at FROM broomva.arcan.encoder_alignment_history ORDER BY evaluated_at DESC LIMIT 20"

# Manual rollback: restore previous best encoder to routing table
python -c "
import lago
history = lago.read('broomva.arcan.encoder_alignment_history')
current = lago.read('broomva.arcan.encoder_alignment')

# Find the previous best text encoder
prev_best = max(
    ((enc, rec) for enc, rec in history.items() if rec['modality'] == 'text'),
    key=lambda x: x[1]['alignment_score']
)
current[prev_best[0]] = prev_best[1]
lago.write('broomva.arcan.encoder_alignment', current)
print('Rolled back to:', prev_best[0], 'score:', prev_best[1]['alignment_score'])
"
```

---

## 7. Integration Testing

Before deploying alignment-driven routing to production, verify the integration:

```python
# tests/test_arcan_alignment_routing.py

import pytest
from core.life.arcan.routing.neuro_alignment import select_encoder, Task

MOCK_ALIGNMENT_TABLE = {
    "meta-llama/Llama-3.2-3B": {"alignment_score": 0.40, "modality": "text"},
    "bert-base-uncased":        {"alignment_score": 0.18, "modality": "text"},
    "facebook/vjepa2-vitg":     {"alignment_score": 0.38, "modality": "video"},
    "openai/clip-vit-l14":      {"alignment_score": 0.24, "modality": "video"},
}

MOCK_MODEL_REGISTRY = {
    "text": {
        "meta-llama/Llama-3.2-3B": {"cost": "low",    "latency_ms": 500},
        "bert-base-uncased":        {"cost": "low",    "latency_ms": 100},
    },
    "video": {
        "facebook/vjepa2-vitg":    {"cost": "high",   "latency_ms": 3000},
        "openai/clip-vit-l14":     {"cost": "medium", "latency_ms": 500},
    },
}


def test_selects_highest_alignment_text_encoder():
    task = Task(modality="text", cost_budget="medium", latency_sla_ms=2000)
    result = select_encoder(task, MOCK_ALIGNMENT_TABLE, MOCK_MODEL_REGISTRY)
    assert result == "meta-llama/Llama-3.2-3B"


def test_falls_back_on_latency_constraint():
    task = Task(modality="video", cost_budget="medium", latency_sla_ms=1000)
    # vjepa2 latency_ms=3000 exceeds SLA; should select clip
    result = select_encoder(task, MOCK_ALIGNMENT_TABLE, MOCK_MODEL_REGISTRY)
    assert result == "openai/clip-vit-l14"


def test_falls_back_when_no_alignment_data():
    task = Task(modality="audio", cost_budget="medium", latency_sla_ms=2000)
    result = select_encoder(task, {}, {})
    assert result == "facebook/w2v-bert-2.0"  # hardcoded fallback
```

Run with: `cargo test -p arcan` (Rust) or `pytest tests/test_arcan_alignment_routing.py` (Python bindings).
