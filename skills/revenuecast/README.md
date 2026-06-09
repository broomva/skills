# revenuecast

**Turn a real-world capability into a self-demonstrating, high-throughput gen-AI
revenue engine.** `/skillify` makes a *workflow* permanent; **`/revenuecast` makes a
*capability* monetizable** — the loop where the output IS the advertisement and you
sell the reproducible method.

The bstack-native composition of the 2026 "show-then-sell-the-system" creator loop
(realosias, aivideoskool, GenHQ), corrected by deep research + a cross-model
adversarial review. Composes `content-engine` (the factory) + the monetization,
distribution, and governance layers above it. **Reimplements nothing.**

## Quickstart

```bash
# 1. copy the manifest template (it doubles as the L2 dogfood instance)
cp skills/revenuecast/templates/revenuecast.manifest.example.yaml revenuecast.manifest.yaml

# 2. edit: swap capability / brand / moat / offer ladder for your niche

# 3. gate it against the design canon
python3 skills/revenuecast/scripts/revenuecast_check.py revenuecast.manifest.yaml
#   --strict  promotes the KPI-honesty gate to required
#   --json    machine-readable

# 4. run the tests
python3 -m pytest skills/revenuecast/tests/ -q
```

## What the gate enforces

A capability that doesn't pass all gates is not a revenue engine — it's content that
happens to exist today. Required gates (G1–G6):

- **G1 Identity** — capability + brand name + a one-line gloss (κλέος needs decoding).
- **G2 Ladder** — free + paid + **recurring** (the durable spine; +89% LTV).
- **G3 Own-the-audience** — an owned channel (platform reach is rented).
- **G4 Moat** — a defensible layer, **never** leakable prompts/templates.
- **G5 Governance** — disclosure-labeling + likeness-firewall + earnings-substantiation
  + spend-cap + ≥3-platform diversification (FTC v. Air AI / EU AI Act Art.50 / NO FAKES).
- **G6 Substance** — no "self-improving" claim without a **built + measured** mechanism
  (the Ritual-vs-Substance rule, machine-checked).
- **G7 KPI honesty** *(advisory; required under `--strict`)* — benchmark numbers must be
  quarantined into a `kpis.imported` block.

## Files

| Path | Role |
|---|---|
| `SKILL.md` | the skill contract + pipeline + composition map |
| `references/design-canon.md` | the single source of truth (read first) |
| `scripts/revenuecast_check.py` | the deterministic gate |
| `tests/test_revenuecast_check.py` | unit tests (23, pinning each gate) |
| `templates/revenuecast.manifest.example.yaml` | a passing manifest = the L2 instance |

Provenance: BRO-1429 · research workflow `wf_d25abca6-6bf` (2026-06-08).
