# Contributing to swapit

## Scope

**In scope:** the household-toxics knowledge graph (hazards, item-classes, alternatives), the
exposure-risk model, the inventory/swap state machine, the report/dashboard, and the (M3)
anonymized commons.

**Out of scope:** medical/clinical advice, legal/regulatory compliance opinions, and anything
that would put private inventory data into a shareable surface (see the privacy invariant).

## The privacy invariant (do not break)

Realm-2 inventory (items, rooms, quantities, brands, photos, purchase info, location) **never**
crosses the sync boundary. Only Realm-1 generic facts are shareable. The boundary is defined by
`state.PRIVATE_FIELDS`; the M3 anonymizer is an allowlist serializer and is covered by a fuzz
test that fails if any private field name appears in a contribution payload. Any PR touching
`anonymize.py`, `sync.py`, or the contribution path must keep that test green.

## Adding knowledge

Seed data lives in `seed/{hazards,item-classes,alternatives}.jsonl` (one JSON object per line).

**Grounding discipline (binding):**
- Every record carries ≥ 1 `source` citing an authoritative body on its canonical domain
  (NIEHS, ATSDR/CDC, EPA, FDA, ECHA/EU REACH, CA OEHHA, WHO, EWG). No bare claims.
- Do not invent deep-link URLs you can't confirm — use the org's stable landing page or `null`.
- Keep `confidence ≤ 0.85` and `verified: false` until a record is freshly source-checked.
- Cross-references must resolve: `item_class.hazards[].hazard_id`, `alternative.replaces[]`,
  and `alternative.avoids_hazards[]` must point at existing ids.

Run `python3 scripts/swapit.py selfheal` — it must report **0 errors** (and ideally 0 warnings).
Every item-class should have at least one alternative (a swap path).

## Development

```bash
python3 -m pytest tests/ -q          # all tests must pass
python3 scripts/swapit.py selfheal   # 0 errors
```

Conventions: stdlib-only runtime (no new third-party deps without discussion), Python ≥ 3.10,
type hints, small cohesive modules. Use Conventional Commits (`feat:`, `fix:`, `docs:`,
subject ≤ 72 chars). Update `CHANGELOG.md` under `[Unreleased]`.

## Reporting issues

Open an issue with: the mode you ran, the exact command, expected vs actual, and (for knowledge
corrections) a citation to an authoritative source.
