# BitNet Model Catalog

## Official Microsoft Models

| Model ID | Params | Format | Use Case |
|----------|--------|--------|----------|
| `microsoft/BitNet-b1.58-2B-4T-gguf` | 2B | GGUF | CPU inference via bitnet.cpp |
| `microsoft/bitnet-b1.58-2B-4T` | 2B | Packed 1.58-bit | HF Transformers (no speed benefit) |
| `microsoft/bitnet-b1.58-2B-4T-bf16` | 2B | BF16 | Fine-tuning / continued training |

## Community Models

| Model ID | Params | Memory Est. | Notes |
|----------|--------|-------------|-------|
| `1bitLLM/bitnet_b1_58-large` | 0.7B | ~0.15 GB | Smallest, fast prototyping |
| `1bitLLM/bitnet_b1_58-3B` | 3.3B | ~0.7 GB | Good balance of size/quality |
| `HF1BitLLM/Llama3-8B-1.58-100B-tokens` | 8B | ~1.6 GB | Best quality, LLaMA 3 base |
| Falcon3 family (tiiuae) | 1B-10B | 0.2-2 GB | TII UAE, multiple sizes |
| Falcon-E family (tiiuae) | 1B-3B | 0.2-0.6 GB | Edge-optimized Falcon |

## Quality Benchmarks (BitNet 2B)

| Benchmark | BitNet 2B | Qwen2.5 1.5B | LLaMA 3.2 1B |
|-----------|-----------|--------------|--------------|
| ARC-Challenge | **49.91** | 46.33 | 38.40 |
| GSM8K | **58.38** | 55.50 | 28.05 |
| WinoGrande | **71.90** | 65.59 | 63.22 |
| MMLU | 53.17 | **55.23** | 45.25 |

## Scaling Projections

| Params | FP16 Memory | BitNet Memory | Reduction |
|--------|-------------|---------------|-----------|
| 2B | 4 GB | 0.4 GB | 10x |
| 7B | 14 GB | 1.4 GB | 10x |
| 13B | 26 GB | 2.6 GB | 10x |
| 70B | 140 GB | 14 GB | 10x |
| 100B | 200 GB | 20 GB | 10x |

## Fine-Tuning Resources

- [tiiuae/onebitllms](https://github.com/tiiuae/onebitllms) — training and fine-tuning toolkit
- [HuggingFace: Fine-tuning to 1.58 bits](https://huggingface.co/blog/1_58_llm_extreme_quantization)
- Use the BF16 checkpoint (`bitnet-b1.58-2B-4T-bf16`) as starting point
