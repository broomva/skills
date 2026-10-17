---
type: world-asset-manifest
world: "{world_slug}"
spent_usd: 0          # the grill spends nothing; production happens in skene
priced_from: "{skene .skene/prices.json or a dated price page}"
status: draft
---

# {World}: asset manifest

> Every skene library entry to make. A row becomes `<kind>/<slug>/entry.json` in
> the skene project: `dna` and `wardrobe` (characters) or `description`,
> `lighting` and `states` (locations) come verbatim from the sheet's fenced
> blocks. Nothing here is generated or spent; estimates only.

## Entries

`kind` is a skene library kind: character, ensemble, location, prop, sound or
style (W08). Each has a sheet in the world folder (W09). A character needs 5 to
20 stills for skene to lock its identity (W10). The multi-view sheet is an
optional research technique for generating those stills; it never replaces them.

| kind | slug | name | sheet | multi-view sheet | stills | est. usd | canon |
|---|---|---|---|---|---|---|---|
| character | {slug} | {Name} | characters/{slug}.md | yes / no | 8 | {…} | {id} |
| ensemble | {slug} | {Name} | characters/{slug}.md | no | — | {…} | {id} |
| location | {slug} | {Name} | locations/{slug}.md | — | {plates} | {…} | {id} |
| prop | {slug} | {Name} | props/{slug}.md | — | {…} | {…} | {id} |
| style | look | {World} look | styles/look.md | — | {mood stills} | {…} | {id} |
| sound | {slug} | {Name} | sound.md | — | — | {…} | {id} |

## Order of production

1. The style lock's test stills (cheapest; every later still depends on it).
2. Hero portraits, one per character, then the remaining stills to reach the
   lock count.
3. Location plates per state.
4. Props.

## Estimate

| Item | Unit price | Count | Total |
|---|---|---|---|
| {…} | {…} | {…} | {…} |
| **Total** | | | **{…}** |

Every run in skene is the owner's to approve, through its metered asks.
