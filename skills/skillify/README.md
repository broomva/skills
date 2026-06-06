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
```

It runs the 10-step checklist and exits non-zero if a required step is missing:

| # | Step | Required? |
|---|------|-----------|
| 1 | SKILL.md contract (name + description) | ✅ |
| 2 | Deterministic code (`scripts/`) | ✅ unless `latent_only: true` |
| 3 | Unit tests | ✅ when code present |
| 4 | Integration tests | recommended |
| 5 | LLM evals | recommended |
| 6 | Resolver trigger | `--strict` |
| 7 | Resolver eval (`role-x.py eval`) | `--strict` |
| 8 | check-resolvable + DRY (`bstack skills audit`) | external |
| 9 | E2E smoke test | recommended |
| 10 | Brain filing / KG provenance | recommended |

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
