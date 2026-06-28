# swapit

[![version](https://img.shields.io/badge/version-0.1.0-blue)](./CHANGELOG.md)
[![python](https://img.shields.io/badge/python-%E2%89%A53.10-blue)](./skill.json)
[![license](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

**Stateful, local-first household toxics inventory + swap engine.**

Find the items in your home that carry endocrine disruptors and persistent chemicals
(BPA/BPS, phthalates, PFAS/PTFE, parabens, flame retardants, VOCs, microplastics), score
each by *real* exposure, and track the swap to a safer alternative — flagged → sourced →
swapped. Ships a grounded, cited knowledge graph of ~20 hazards, ~40 item-classes, and ~40
alternatives. Hands sourcing off to the [`procurer`](../procurer) skill.

> The skill's state is the source of truth — **the agent is the app.** Zero paid services,
> nothing leaves your device.

## Install

```bash
npx skills add broomva/swapit          # once published
# or, during development:
npx skills add /path/to/skills/swapit -l
```

Requires Python ≥ 3.10. No third-party runtime dependencies (stdlib only). `pytest` for dev.

## Quick start

```bash
python3 scripts/swapit.py init

python3 scripts/swapit.py add --name "Old Teflon pan" --class nonstick-cookware \
        --room kitchen --condition scratched --frequency daily --food-contact --heat

python3 scripts/swapit.py score                 # what to swap first
python3 scripts/swapit.py swap itm_xxxx --to cast-iron-skillet --status sourcing \
        --add-task "buy 10in skillet"
python3 scripts/swapit.py procure itm_xxxx      # hand off to the procurer skill
python3 scripts/swapit.py report --open         # shareable HTML report
```

Browse what the knowledge graph knows:

```bash
python3 scripts/swapit.py knowledge list --type item-class
python3 scripts/swapit.py knowledge search bpa
python3 scripts/swapit.py assess --class polycarbonate-bottle --frequency daily --food-contact
```

## How risk is scored

```
risk = severity × presence × evidence × exposure_relevance × frequency × condition
```

A scratched non-stick pan used daily at high heat ranks far above an unopened plastic bin
in the garage. The output is a *swap-first* ranking — fix the few items that drive most of
the exposure, not a guilt list of everything plastic.

## Privacy

Two realms, hard-separated:

- **Knowledge** (generic, cited facts) — shareable.
- **Inventory** (your items, rooms, quantities, brands, photos) — **private; never leaves the device.**

The networked, anonymized commons (M3) only ever transmits generic facts, opt-in, after a
reviewable `swapit sync --dry-run`.

## State

Lives at `~/.config/swapit/` (override with `$SWAPIT_HOME`). See [SKILL.md](./SKILL.md) for the
full data model, modes, and roadmap.

## Develop

```bash
python3 -m pytest tests/ -q
python3 scripts/swapit.py selfheal      # validate knowledge edges + inventory refs
```

## Disclaimer

Consumer guidance grounded in public-health sources (NIEHS, ATSDR, EPA, FDA, ECHA, OEHHA, WHO,
EWG). **Not** medical or legal advice. For acute exposure, contact poison control or a clinician.

## License

MIT © Carlos D. Escobar-Valbuena (broomva)
