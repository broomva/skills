# EGRI + Colab Integration Patterns

## Problem Spec Template

```yaml
objective:
  metric: eval_loss           # or accuracy, f1, perplexity, custom
  direction: minimize         # or maximize

hard_constraints:
  max_vram_gb: 16             # T4=16, V100=16, A100=40/80
  max_runtime_hours: 12       # Colab session limit
  max_cost_usd: 0             # Subscription-based, no per-run cost

mutable_artifacts:
  - train.py
  - config.yaml

immutable_artifacts:
  - prepare_data.py
  - evaluate.py

execution_backend:
  type: colab-ssh
  host: ${COLAB_HOST}
  port: ${COLAB_PORT}
  workdir: /content/experiment

budget:
  max_trials: 20
  max_wall_time: 8h

promotion_policy: keep-if-improves
autonomy_mode: sandbox
```

## Execution Harness

For each EGRI trial:

```bash
# 1. Upload mutated artifact
scp -P $COLAB_PORT ./trial_N/train.py root@$COLAB_HOST:/content/experiment/train.py
scp -P $COLAB_PORT ./trial_N/config.yaml root@$COLAB_HOST:/content/experiment/config.yaml

# 2. Execute on Colab
ssh -p $COLAB_PORT root@$COLAB_HOST "cd /content/experiment && python train.py --config config.yaml 2>&1 | tee train.log"

# 3. Run evaluator on Colab
ssh -p $COLAB_PORT root@$COLAB_HOST "cd /content/experiment && python evaluate.py --checkpoint best_model/ 2>&1"

# 4. Download results
scp -P $COLAB_PORT root@$COLAB_HOST:/content/experiment/results.json ./trial_N/results.json

# 5. Score locally (evaluator stays immutable on local machine)
python score_trial.py --results ./trial_N/results.json
```

## Hyperparameter Sweep

```bash
# Generate sweep configs locally
python generate_sweep.py --param lr:1e-5,3e-5,1e-4 --param batch:4,8,16 > configs.json

# Execute each config on Colab
for config in $(cat configs.json | jq -c '.[]'); do
  echo "$config" > /tmp/config.yaml
  scp -P $COLAB_PORT /tmp/config.yaml root@$COLAB_HOST:/content/experiment/config.yaml
  ssh -p $COLAB_PORT root@$COLAB_HOST "cd /content/experiment && python train.py --config config.yaml"
  scp -P $COLAB_PORT root@$COLAB_HOST:/content/experiment/metrics.json \
    "./sweep/$(echo $config | md5sum | cut -c1-8).json"
done
```

## QLoRA Fine-Tuning Template

Standard QLoRA setup for Colab T4/V100 (16GB VRAM):

```python
# train.py — mutable artifact
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig
import yaml, sys

with open(sys.argv[2] if len(sys.argv) > 2 else "config.yaml") as f:
    cfg = yaml.safe_load(f)

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype="bfloat16",
)

model = AutoModelForCausalLM.from_pretrained(
    cfg["model_name"], quantization_config=bnb_config, device_map="auto"
)
model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=cfg.get("lora_r", 16),
    lora_alpha=cfg.get("lora_alpha", 32),
    target_modules=cfg.get("target_modules", ["q_proj", "v_proj"]),
    lora_dropout=cfg.get("lora_dropout", 0.05),
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)

tokenizer = AutoTokenizer.from_pretrained(cfg["model_name"])
tokenizer.pad_token = tokenizer.eos_token

training_args = SFTConfig(
    output_dir="./output",
    num_train_epochs=cfg.get("epochs", 3),
    per_device_train_batch_size=cfg.get("batch_size", 4),
    learning_rate=cfg.get("lr", 2e-4),
    logging_steps=10,
    save_strategy="epoch",
    bf16=True,
    gradient_checkpointing=True,
    max_seq_length=cfg.get("max_seq_length", 2048),
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=...,  # Load from cfg["dataset"]
    tokenizer=tokenizer,
)
trainer.train()
trainer.save_model("./best_model")
```

```yaml
# config.yaml — mutable artifact (EGRI mutates this)
model_name: "meta-llama/Llama-3.2-3B"
dataset: "/content/data/train.jsonl"
epochs: 3
batch_size: 4
lr: 2e-4
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
max_seq_length: 2048
target_modules: ["q_proj", "v_proj", "k_proj", "o_proj"]
```

## Session Recovery

When Colab session dies mid-EGRI-loop:

1. Log which trial was running (trial N, started at T)
2. Re-launch Colab (Phase 1 browser automation)
3. Re-upload immutable artifacts + last good checkpoint
4. Resume from trial N with `--resume` flag
5. Continue EGRI loop from where it left off

The ledger (append-only JSON) on the local machine preserves all completed trial results.
