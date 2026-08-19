# unslop

**Remove the "vibecoded" / AI-slop look from an arbitrary frontend codebase at the root, autonomously,
and prove the result clears a crafted floor.**

Twenty-six of the thirty tells people list ("30 reasons your site looks vibecoded", Aug 2026) are
LLM-default *surface* choices a prompt removes; four are **absence of substance** (no real demo, no
loading states, no TOS, no privacy policy) that only the real product removes. `unslop` treats those
two halves differently: it fixes the surface at the *root* (the one file that declares each default),
and it keeps the substance checks red until a human makes them true.

> Fix the class, not the example — and prove it on the rendered result.

## Install

```bash
npx skills add broomva/skills --skill unslop
```

The mechanical detector is composed from the [impeccable](https://impeccable.style) skill
(`npx skills add pbakaus/impeccable`, or `npx impeccable detect`); without it the survey reports
`unavailable` and the gate WARNs — it never pretends classes A–C were checked.

## Use

```bash
# 1. survey — full-repo inventory, roots, substance, detector findings
python3 scripts/unslop_survey.py ./my-app --detect --json .unslop/survey.json --md .unslop/survey.md

# 2. …fix at the root, render at 1280 + 390 into .unslop/evidence/ (see references/arc.md)…

# 3. gate — exit 0 iff the crafted floor is clear
python3 scripts/unslop_gate.py ./my-app --detect --evidence .unslop/evidence --waivers .unslop/waivers.json
```

Waivers need a reason (≥20 chars): `{"waivers":[{"check":"fonts.deliberate","value":"inter","reason":"…"}]}`.

## What's in the box

| Path | What |
|---|---|
| `SKILL.md` | The contract, the one rule, the composition map |
| `scripts/unslop_survey.py` | Inventory + root-cause attribution + substance tells + detector composition (stdlib) |
| `scripts/unslop_gate.py` | The crafted floor as PASS/WARN/FAIL with waivers, strict mode, render evidence |
| `references/arc.md` | The nine-step autonomous arc and what each step composes |
| `references/crafted-floor.md` | The operational definition of "crafted", every rule [M]/[J]-tagged and sourced |
| `references/tells.md` | The dated, regenerable list of current LLM defaults (reel → class → check) |
| `references/root-cause-playbook.md` | Where each default lives and the one edit that fixes it |
| `tests/` | pytest — both polarities, waivers, strict, evidence, CLI |

## Provenance

BRO-2184 · origin: `/checkit` on an Instagram reel → `research/entities/pattern/vibecoded-tells.md` →
research synthesis across 60+ sources → this skill, built with `/skillify`.
