# skillify

**Skillify-as-a-verb** — distill a working session (or a pointed-at chat
history) into a permanent, *tested*, registered skill at the end of a workflow.

The bstack-native composition of Garry Tan's 10-step "skillify it": you build
something ad-hoc in conversation, it works, you say *"skillify it"*, and the
prototype becomes permanent infrastructure — SKILL.md + deterministic code +
tests + resolver-eval + registry entry + filed knowledge — instead of a
screenshot in a chat log.

> **A feature that doesn't pass all ten is not a skill. It's just code that
> happens to work today.**

## Install

```bash
npx skills add broomva/skills --skill skillify
```

Then in an agent session, at the end of a workflow that worked:

> skillify it

## The gate

`skillify` is a **composition skill** (it fires existing primitives; it
reimplements nothing) with one deterministic core — the *doctor* that makes the
rule machine-checkable:

```bash
python3 scripts/skillify_check.py <skill_dir> \
    [--roles-dir roles] [--registry AGENTS.md] [--entities-dir research/entities] [--strict]

python3 scripts/skillify_check.py --survey skills/     # the same gate over a whole roster
```

It runs the 10-step checklist and exits non-zero if a required step is missing:

| # | Step | Required? |
|---|------|-----------|
| 1 | SKILL.md contract (name + description) | ✅ |
| 2 | **Tier + its core** (see below) | ✅ |
| 3 | Unit tests | ✅ whenever code ships |
| 4 | Integration tests | recommended |
| 5 | LLM evals (trigger surface) | recommended |
| 6 | Resolver trigger | `--strict` |
| 7 | Resolver eval (`role-x.py eval`) | `--strict`, and ✅ for tier L with `--roles-dir` |
| 8 | check-resolvable + DRY (`bstack skills audit`) | external |
| 9 | E2E smoke test | recommended |
| 10 | Brain filing / KG provenance | recommended |

### Tiers

Step 2 used to ask *"is there a deterministic core?"* and treat *no* as either a
failure or, via `latent_only: true`, a blanket exemption — a testability question
deciding an expressibility question. It now asks what **kind** of thing the skill is.

| Tier | What it is | Step 2 passes when |
|---|---|---|
| **D** — deterministic | there is a pure function in here | `scripts/` present and syntax-valid |
| **J** — judgment | a well-posed question whose valid answers vary | `evals/admission.md` with a recorded outcome + a rubric + held-out cases + a judge config naming a model distinct from the model under eval + `judge.agreement_floor` **with** `judge.agreement_measured` |
| **L** — lens | it changes what you attend to, not what you do | a routing eval asserting BOTH polarities |

Declare it in frontmatter (`tier: D`). Only **D** is inferred, from shipped code;
**J and L must be declared.** Inference decides *which* gate applies, never *whether*
one does — a skill the gate cannot classify still fails.

`latent_only: true` is deprecated: it still means "not tier D", but it no longer
exempts a skill from everything else. It contradicts a deterministic **core**, not
merely the presence of files under `scripts/` — a lens may ship a test and a package
marker.

**The agreement floor is deliberately unset**, and **the judge is an unbuilt seam** —
the gate checks that a tier-J skill's artifacts are present, well-formed and
cross-model, and reports the judge *run* as a SKIP, never a PASS.

## Composes

- [`broomva/role-x`](https://github.com/broomva/role-x) — resolver + `role-x.py eval` (resolver-eval, step 7)
- `bstack skills audit --require-tests` — registry-wide script-test gate (steps 3/4)
- `CreateSkill` — scaffolding (step 1)
- `broomva/cross-review` (P20) — adversarial gate (step 7-review)
- `bookkeeping` (P6) — filing (step 10)
- the `look-back` lens — extraction

## Distinct from

- **`/checkit`** — ingests an *external* artifact (URL/repo/paper). skillify
  distills *your own session* into a skill.
- **`look-back`** — *discovers* what's worth packaging. skillify *packages* it.

## Development

```bash
pip install -r tests/requirements-dev.txt
python -m pytest tests/ -v
python3 scripts/skillify_check.py .   # dogfood: skillify passes its own gate
```

MIT © 2026 Carlos D. Escobar-Valbuena
