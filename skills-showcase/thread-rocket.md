# X Thread — Rocket Simulation + EGRI + Skills Showcase

## 1/7 — Hook (attach video: skills-showcase.mp4)

We turned an open-source rocket simulator into a headless optimization engine.

144 EGRI trials in 5 minutes. Zero GUI. Pure physics as evaluator.

Here's what we learned about mutation surfaces and why trial count doesn't matter.

🧵

## 2/7 — The Setup

OpenRocket is a model rocket simulator with 6DOF physics.

We stripped out the Swing GUI, kept the core engine, and built:

→ `rocket-sim` CLI (info, run, sweep, events — all JSON)
→ EGRI optimization harness (problem-spec, evaluator, ledger)
→ Published agent skill (`npx skills add broomva/openrocket-sim`)

From clone to first simulation: 10 minutes.

## 3/7 — Why Physics Sims Are Perfect EGRI Evaluators

EGRI's core law: never grant more mutation freedom than your evaluator can reliably judge.

Physics simulation satisfies this completely:
• Deterministic — same inputs, same outputs, always
• Fast — ~2s per trial, 144 trials in 5 min
• Trusted — it's physics, not a heuristic
• Structured — typed scalars (altitude, velocity, Mach)

This unlocks auto-promote mode. No human gate needed.

## 4/7 — The Surprising Result

We swept 4 launch parameters × 144 combinations:
- Rod length: 0.5–2.0m
- Rod angle: 0–10°
- Launch altitude: 0–2000m ASL
- Wind speed: 0–5 m/s

Result: ZERO promotions. Every candidate hit ~50.5m ± 0.6m.

The evaluator wasn't wrong. The mutation surface was.

## 5/7 — Mutation Surface > Trial Count

For a model rocket with an A8-3 motor:
• Motor selection → ~95% of max altitude
• Aerodynamic design → ~4%
• Launch parameters → ~1%

We were optimizing the 1% variable. 144 trials confirmed what one physics insight predicts: you can't out-iterate a bad mutation surface.

This is a general principle. Before asking "how many trials?" ask "what am I allowed to change?"

## 6/7 — The Agent Skill

Anyone can now install this:

```
npx skills add broomva/openrocket-sim
```

It gives Claude Code:
• Headless simulation API docs
• CLI tool usage patterns
• EGRI integration (problem-spec, evaluator, harness)
• 8 compounding strategies

Full blog post: broomva.tech/writing/rocket-sim-egri-optimization

## 7/7 — What's Next

Expanding the mutation surface:
1. Motor selection sweep (A8 → C6 → D12)
2. Component geometry (fin span, nose cone, body tube)
3. Multi-objective Pareto (altitude vs. recovery safety)
4. LLM-guided design exploration

The evaluator is ready. The mutation surface is the bottleneck.

What domain would you wire into an EGRI loop?
