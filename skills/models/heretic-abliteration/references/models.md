# Model catalog

## Run-it-yourself (Heretic input — HF models)

Heretic supports dense, MoE, and hybrid architectures (multimodal variants too);
pure state-space models are excluded by default. Pick by your hardware.

| Model | Params | Where it runs | Notes |
|-------|--------|---------------|-------|
| `Qwen/Qwen3-0.6B` | 0.6B | CPU (smoke only) | Used to validate this skill. GQA → no MPS. |
| `Qwen/Qwen3-4B-Instruct-2507` | 4B | GPU (≈20–30 min RTX 3090) | Heretic's own default example. |
| `meta-llama/Llama-3.1-8B-Instruct` | 8B | GPU (≈45 min RTX 3090) | README baseline. |
| `google/gemma-3-12b-it` | 12B | GPU | Heretic reports 3/100 refusals @ KL 0.16. |

Defaults: harmful prompts `mlabonne/harmful_behaviors`, harmless `mlabonne/harmless_alpaca`.
Quantization `BNB_4BIT` is **CUDA-only** (bitsandbytes); use `NONE` elsewhere.

## Serve-it-now (pre-abliterated GGUF — Ollama, no compute)

The fast path on Apple Silicon / no-GPU. Same class of model, zero processing.

| Ollama ref | Params | Pull |
|------------|--------|------|
| `huihui_ai/llama3.2-abliterate:1b` | 1B | validated in this skill |
| `huihui_ai/llama3.2-abliterate:3b` | 3B | better quality |
| `huihui_ai/qwen2.5-abliterate:7b` | 7B | general use |
| any HF GGUF | — | `ollama run hf.co/<user>/<repo>:<quant>` |

Search more at ollama.com for "abliterate"/"uncensored". Heretic's own outputs are
published to its Hugging Face org — convert to GGUF (`heretic-to-ollama.sh`) if no
GGUF is provided.

## Quant guidance (GGUF)

`Q4_K_M` is the default sweet spot (size/quality). `Q5_K_M` / `Q6_K` for more
fidelity; `Q8_0` near-lossless but large. `f16` is the unquantized intermediate.
