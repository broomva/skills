# Heretic as an Evaluator-Governed Recursive Improvement (EGRI) loop

Heretic is a clean, small instance of the `autoany`/EGRI pattern — worth noting
because it makes the algorithm legible and ties into the RCS / control-theory work.

## The mapping

| EGRI / autoany role | Heretic component |
|---------------------|-------------------|
| **Mutable artifact** | The ablation parameters per component (`direction_index`, and the kernel shape `max_weight`, `max_weight_position`, `min_weight`, `min_weight_distance`) applied to `attn.o_proj` + `mlp.down_proj`. |
| **Immutable evaluator** | A fixed two-term objective it cannot game: **refusal count** on harmful eval prompts (`mlabonne/harmful_behaviors`) + **KL divergence** of first-token distributions on harmless prompts (`mlabonne/harmless_alpaca`). |
| **Harness / search** | Optuna **TPE** sampler over the parameter surface (`--n-trials`). |
| **Promotion policy** | The **Pareto front** of (refusals, KL); the operator selects a trial from the frontier. |
| **Safety / stability constraint** | The KL term is an explicit drift penalty — structurally the same move as an RCS stability margin keeping a controller from over-correcting. Heretic's own note: KL > 0.5 ≈ "significant damage". |

## Why the second term matters

Naïve abliteration drives refusals to zero but also wrecks reasoning, formatting,
and instruction-following. The KL leash is what makes it a *governed* optimization
rather than a destructive one. Observed: Qwen3-0.6B reached refusals 6/8 → 1/8 at
KL **0.0026** — a near-zero-damage decensoring, i.e. the Pareto knee sits at high
compliance *and* high fidelity simultaneously.

## Reading for the RCS lens

This is a single-level controlled system: the **plant** is the model's refusal
behavior, the **control law** is the orthogonalization kernel, the **observer** is
the refusal/KL evaluator, and the **shield** is the KL ceiling. It is *not*
recursive (the evaluator is fixed, not itself improved) — which is exactly why it's
stable and bounded. A recursive variant (evolving the evaluator/prompt sets) would
need the L2/L3 stop-gradient discipline from the dream-cycle work to stay safe.

See also: `skills/autoany/` (EGRI framework), `research/rcs/`.
