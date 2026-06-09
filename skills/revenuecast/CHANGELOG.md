# Changelog — revenuecast

## 0.2.0 — 2026-06-09

Renamed `kleos` → **`revenuecast`** (the `<output>cast` / Casting convention, BRO-1436)
and made the skill **fully self-contained** for the `broomva/skills` monorepo.

- Skill verb is now `/revenuecast`; the gate is `scripts/revenuecast_check.py`. "Kleos"
  is kept as the **method/playbook name** the skill operationalizes (κλέος — renown that
  propagates by being shown).
- **Bundled all references** so `npx skills add broomva/skills --skill revenuecast`
  delivers the complete package: `references/playbook.html` (L1), `l2-agentic-dev-wedge.html`
  (L2), `runtime-spec.html` + `runtime-status.md` (L3, DEFERRED). No separate app repo —
  the Rust runtime graduates to its own deploy repo only when actually built.
- Gate + 23 tests green under the new name; passes the skills.sh install parser.

## 0.1.0 — 2026-06-08

Initial release. The "show-then-sell-the-system" creator loop, made bstack-native.

- **SKILL.md** — composition skill: Brand-Lock → Show → Distribute → Hook → Sell → Moat.
- **references/design-canon.md** — single source of truth, grounded in research
  workflow `wf_d25abca6-6bf` and corrected by its P20 adversarial review (5.5/10 →
  REVISE; all three load-bearing corrections baked in: the SHOW is the scarce asset;
  no self-improvement incantation; wedge-first, not a 6-tier deck).
- **scripts/revenuecast_check.py** — deterministic gate over an engine-instance manifest:
  G1 identity · G2 ladder · G3 own-the-audience · G4 moat (no leakable prompts) ·
  G5 governance/compliance · G6 Ritual-vs-Substance · G7 KPI honesty.
- **tests/** — 23 unit tests pinning each gate.
- **templates/revenuecast.manifest.example.yaml** — the Layer-2 dogfood instance
  (agentic-dev wedge), authored to pass the gate.

Provenance: BRO-1429.
