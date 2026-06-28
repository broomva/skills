# Heretic — troubleshooting (dogfood-validated 2026-05-30, M4 Pro / macOS 26.5)

Every row below was hit and resolved during the dogfood that produced this skill.
Evidence: `/tmp/dogfood-heretic/heretic-run{1..8}.log`.

## Blocker → cause → fix

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 1 | `ValueError: Either a revision or a version must be specified` at `import heretic.main` (via `transformers/integrations/hub_kernels.py:89`) | **Universal**: `transformers 5.9.x` ↔ `kernels 0.15.x` incompatibility. `kernels` is an optional accelerator transformers tries to register at import. | `pip uninstall -y kernels kernels-data`. (Alternative: pin a compatible `kernels` version once known.) |
| 2 | `module 'jinja2' has no attribute 'pass_eval_context'` → `Failed to load model with all configured dtypes` | **Base-env only**: an ancient `jinja2 2.11.3` (pre-3.0) was pinned by a legacy package. Chat-template rendering needs Jinja2 ≥ 3.0. | `pip install -U 'jinja2>=3.1'`. A clean venv never has this. |
| 3 | `LLVM ERROR: Failed to infer result type(s): "mps.matmul"(tensor<1x16x1x128xbf16>, tensor<1x8x128x31xbf16>)` then hard abort | **Platform**: PyTorch-MPS bug on **grouped-query-attention** shapes (n_q_heads ≠ n_kv_heads — Qwen3, Llama-3, Mistral, …). Hard Metal-compiler abort, not catchable. | Force `--device-map cpu` (+ `PYTORCH_ENABLE_MPS_FALLBACK=1`). MPS is effectively unusable for GQA models until PyTorch fixes it. |
| 4 | Run times out before reaching trials / during batch-size probe | **Performance**: CPU only ~50–110 tok/s; no CUDA → `bitsandbytes` (CUDA-only) inert. The default `--max-batch-size` probe alone can exhaust a short budget. | Pin `--batch-size N --max-batch-size N` to skip the probe; shrink prompt sets; or use a GPU. For real (4–12B) models, use a GPU. |
| 5 | `OSError: [Errno 22] Invalid argument` / `KeyError: '0 is not registered'` at the end (or start) of a run | **TTY**: the save/upload/chat menu and the resume menu use `questionary`/`prompt_toolkit`, which need a real terminal. Piped or `/dev/null` stdin crashes — *after* optimization completes, so the model is lost. | Run `heretic` in an interactive terminal. Never pipe stdin if you want to save. |
| 6 | At startup: "You have already processed this model… continue the previous run?" then a TTY crash | A prior interrupted run left a checkpoint in `--study-checkpoint-dir`. | Pass a fresh `--study-checkpoint-dir`, or delete the old checkpoint, or answer the menu in a TTY. |

## The core architectural fact

**Ollama cannot be Heretic's backend.** Heretic mutates raw HF transformer weights
(reads residual-stream activations to compute difference-of-means "refusal
directions", then orthogonalizes `attn.o_proj` + `mlp.down_proj` against them). That
requires PyTorch + `transformers` + full weights. Ollama is **inference-only** over
GGUF/llama.cpp — no activation access, no weight editing. They sit at different
layers. The only connection is **downstream**:

```
Heretic (HF safetensors)
   → convert_hf_to_gguf.py   (llama.cpp)
   → llama-quantize Q4_K_M
   → ollama create -f Modelfile
   → ollama run
```

## Performance reference (validated)

| Path | Hardware | Result |
|------|----------|--------|
| Full abliteration, Qwen3-0.6B, 1 trial | M4 Pro **CPU** | refusals **6/8 → 1/8**, KL **0.0026**, `Optimization finished!` |
| Forward pass throughput | M4 Pro CPU | 50–110 tok/s (batch 1→64) |
| MPS forward pass | M4 Pro Metal | ✗ LLVM abort (row 3) |
| Real model (README baseline) | RTX 3090 | Llama-3.1-8B ≈ 45 min |
| Serve pre-abliterated GGUF | M4 Pro (Ollama) | instant; capability preserved, false-refusals removed |

**Lesson:** on Apple Silicon, treat this as **serve-only** (pull a pre-abliterated
GGUF) unless you have a GPU. Run Heretic itself on CUDA — locally or via
`broomva/remote-gpu`.
