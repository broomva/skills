# CaP-X Agentic Robotics

Agent skill for [CaP-X](https://capgym.github.io/) — LLM-driven robot manipulation via code generation.

Built on research from NVIDIA, UC Berkeley, Stanford, and CMU ([arXiv:2603.22435](https://arxiv.org/abs/2603.22435)).

## What This Skill Does

Equips AI coding agents with the knowledge to set up, run, and extend the CaP-X framework:

- **CaP-Gym** — 187 manipulation tasks across RoboSuite, LIBERO-PRO, and BEHAVIOR
- **CaP-Bench** — Benchmark 12 frontier LLMs/VLMs across 8 evaluation tiers
- **CaP-Agent0** — Training-free agentic harness (visual differencing, auto-synthesized skill libraries, parallel reasoning)
- **CaP-RL** — GRPO post-training that takes a 7B model from 25% to 80% success in 50 iterations
- **Sim-to-real transfer** — Zero-shot transfer to Franka Panda, R1Pro humanoid, AgiBot G1

## Install

```bash
npx skills add broomva/capx-agentic-robotics -g -y
```

## Structure

```
capx-agentic-robotics/
├── SKILL.md                          # Core skill (setup, architecture, workflows)
├── references/
│   ├── api-spec.md                   # Perception + control API specification
│   ├── capbench-results.md           # 12-model benchmark results, 8 tiers
│   └── caprl-training.md             # GRPO training guide with recipes
└── scripts/
    ├── setup-perception.sh           # Start all perception microservices
    └── run-benchmark.sh              # CaP-Bench evaluation sweep
```

## Prerequisites

- CUDA-capable GPU (perception services + training)
- Python 3.10+ (3.12 recommended for RL/LIBERO)
- [CaP-X](https://github.com/capgym/cap-x) cloned and installed

## Related

- [CaP-X](https://github.com/capgym/cap-x) — Source framework (MIT)
- [Voyager](https://arxiv.org/abs/2305.16291) — Predecessor: skill libraries + self-reflection in Minecraft
- [ORCA Hand](https://github.com/broomva/orcahand) — 17-DOF tendon-driven robotic hand skill

## License

[MIT](LICENSE)
