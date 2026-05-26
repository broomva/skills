# CaP-Bench Results

Benchmark results from the CaP-X paper (arXiv:2603.22435). Zero-Shot Pass@1, 100 trials per configuration.

## 7 Core RoboSuite Tasks

Tasks: Cube Lift, Cube Stack, Spill Wipe, Peg Insertion, Cube Re-stack, Two-Arm Lift, Two-Arm Handover

### Tier S1 — Single-turn, Noiseless, High-level API

Best overall: Gemini-3-Pro and GPT-5.2 trade top spots across tasks.

### Tier S2 — Single-turn, Noisy Perception, High-level API

Performance drops 10-25% vs S1 due to perception noise. SAM3 segmentation errors dominate failure modes.

### Tier S3 — Single-turn, Noisy, Low-level API

Sharp degradation (30-50% drop). Without high-level abstractions, models struggle with IK parameterization and grasp sequencing.

### Tier M4 — Multi-turn, Noisy, Low-level, VDM

CaP-Agent0 configuration. Recovery from M3 via visual differencing and skill libraries. Approaches S2 performance on 4/7 tasks.

## Model Rankings (aggregated across tiers)

| Rank | Model | Strength |
|------|-------|----------|
| 1 | Gemini-3-Pro | Strongest spatial reasoning, best at low-level tiers |
| 2 | GPT-5.2 | Best code generation quality, strong high-level |
| 3 | Claude Opus 4.5 | Most reliable multi-turn reasoning, fewest hallucinated APIs |
| 4 | o4-mini | Strong efficiency/performance ratio |
| 5 | Qwen3-235B | Best open-source, competitive with closed on S1-S2 |
| 6 | GPT-5.1 | Solid all-rounder |
| 7 | o1 | Deliberative reasoning helps on complex tasks |
| 8 | Kimi K2 | Strong on perception-heavy tasks |
| 9 | DeepSeek-V3.1 | Good code quality, weaker spatial reasoning |
| 10 | GPT-OSS-120B | Best fully-open model |
| 11 | Claude Haiku 4.5 | Fast, good for rapid iteration |
| 12 | GPT-OSS-20B | Baseline open-source |

## CaP-Agent0 vs Human Expert Code

| Task | Human Expert | CaP-Agent0 (M4) | Delta |
|------|-------------|-----------------|-------|
| Cube Lift | 93% | 96% | +3% |
| Cube Stack | 73% | 78% | +5% |
| Spill Wipe | 100% | 97% | -3% |
| Peg Insertion | 84% | 71% | -13% |
| Cube Re-stack | 67% | 69% | +2% |
| Two-Arm Lift | 88% | 82% | -6% |
| Two-Arm Handover | 76% | 74% | -2% |

CaP-Agent0 exceeds human on 3 tasks, within 6% on 2 more. Peg Insertion is hardest — requires sub-mm precision.

## CaP-Agent0 vs VLA Policies (LIBERO-PRO)

On 30 LIBERO-PRO tasks:

| Method | Training? | Avg Success |
|--------|-----------|-------------|
| OpenVLA | Yes (fine-tuned) | 62% |
| pi_0 | Yes (pre-trained) | 71% |
| pi_0.5 | Yes (pre-trained) | 74% |
| CaP-Agent0 | **No** | **73%** |

Training-free CaP-Agent0 matches trained VLA policies.

## CaP-RL Results

| Task | Qwen-7B Base | +CaP-RL (50 iter) | Human Expert |
|------|-------------|-------------------|-------------|
| Cube Lift (sim) | 25% | 80% | 93% |
| Cube Stack (sim) | 4% | 44% | 73% |
| Spill Wipe (sim) | 30% | 93% | 100% |
| Cube Lift (real) | 24% | 84% | 92% |
| Cube Stack (real) | 12% | 76% | 84% |

Key: RL-trained 7B model nearly matches human expert on real hardware for simpler tasks.

## Key Insights

1. **Abstraction matters**: Performance drops 30-50% when moving from high-level to low-level APIs
2. **Multi-turn recovers**: VDM + skill library closes ~60% of the S2-to-S3 gap
3. **Ensemble helps**: 3-model ensemble outperforms best single model by 8-15%
4. **RL scales**: 50 iterations sufficient for dramatic improvement on a 7B model
5. **Sim-to-real gap is small**: Abstract API reasoning transfers with <10% degradation
6. **Open-source competitive**: Qwen3-235B within 15% of best closed models on most tiers
