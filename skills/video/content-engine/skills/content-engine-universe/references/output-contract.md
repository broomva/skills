# The output contract

A world is one folder. During the grill it grows round by round; `world_check.py check` holds
what exists to the rules. At the end, `--complete` requires the whole set.

## Files

| File | Required at the end | Template |
|---|---|---|
| `owner-taste.md` | yes (in the world, or passed as `--taste`) | `templates/owner-taste.md` |
| `decisions.md` | yes | `templates/decisions.md` |
| `bible.md` | yes | `templates/bible.md` |
| `canon.yaml` | yes | `templates/canon.yaml` |
| `evidence.md` | when anything predates the grill | `templates/evidence.md` |
| `characters/<slug>.md` | at least one | `templates/character.md` |
| `locations/<slug>.md` | at least one | `templates/location.md` |
| `props/<slug>.md` | when the world has props | `templates/prop.md` |
| `styles/look.md` | yes | `templates/style-lock.md` |
| `sound.md` | yes | `templates/sound.md` |
| `timeline.md` | yes | `templates/timeline.md` |
| `accounts.md` | yes | `templates/accounts.md` |
| `asset-manifest.md` | yes | `templates/asset-manifest.md` |

## Pasted blocks

Text that a prompt or a post pastes lives in fenced blocks whose info word names its role. The
checker reads them; people read the prose around them.

| Info word | In | Becomes |
|---|---|---|
| `fixed-dna` | characters | `entry.json` `dna` |
| `wardrobe <name>` | characters | `entry.json` `wardrobe` (the default first) |
| `description` | locations, props | `entry.json` `description` |
| `lighting` | locations | `entry.json` `lighting` |
| `state <name>` | locations, props | `entry.json` `states[<name>]` |
| `prompt <role>` | styles/look.md | the render, framing and texture lines of every shot prompt |
| `caption` | accounts, formats | caption text that is posted |

A character's skene `description` is its `fixed-dna` followed by its default `wardrobe`. A prompt
that paraphrases a library block breaks consistency: change the block, then paste it again.

## Mapping to skene's library

skene keeps every asset as a folder with an `entry.json` (`skene-studio/FORMATS.md`, "The
library"). Each manifest row becomes one:

| Manifest kind | skene folder | Fields from the world | Lock needs |
|---|---|---|---|
| `character` | `cast/<slug>/` | `dna` ← `fixed-dna`; `wardrobe` ← `wardrobe default`; `notes` ← the sheet's rules | 5–20 stills |
| `ensemble` | `cast/<slug>/` | `description` ← the ensemble's `fixed-dna` | — |
| `location` | `locations/<slug>/` | `description`, `lighting`, `states` | plates per state |
| `prop` | `props/<slug>/` | `description`, `states`, `colors`, `hero` | — |
| `style` | `styles/<slug>/` | the render line and the NO list | — |
| `sound` | `sound/<slug>/` | the sound's description from `sound.md` | — |

A slot then names the entry (`character: wick`, `location: the-square@sandstorm`), and skene pastes
its text at run time.

**Stills and sheets.** skene locks a character's identity on 5 to 20 stills (W10). A single 16:9
multi-view sheet is a research technique for producing those stills consistently; it is not a skene
format and never replaces them. The manifest plans both: a `multi-view sheet` column and a `stills`
column.

## Mapping to content-engine's templates

| content-engine field | Where the world settles it |
|---|---|
| brand-dna tagline, voice, values, audience, red lines | `bible.md` (premise, tone, what the world is not) |
| visual-dna-framework LORE (character, world, symbols) | `bible.md` + `canon.yaml` |
| consistency model A (master brand) or B (brand family) | `accounts.md` frontmatter |
| palette (roles in hex), lighting, camera, texture, render style | `styles/look.md` |
| grade | `styles/look.md` "Grade" |
| character-sheet identity, wardrobe, environments, motion directives | `characters/<slug>.md` (species-aware) |
| product Fixed-DNA slots (form, material, colour, proportions, marks) | non-human character and prop identity rows |
| scene-brief mood, lighting key/fill/rim/practicals, time and place, props | `locations/<slug>.md` |
| audio layer stack, genre, voice type, SFX, sound logo | `sound.md` |
| campaign theme, arc, character roles; calendar pacing | `timeline.md`, `accounts.md` |

## The Fixed-DNA cap

The cap is the owner's choice, set once per world as `dna_cap` in `canon.yaml` (default 600) and
overridable with `--dna-cap`. skene sets no limit; a cap keeps the block verbatim-stable and leaves
room in a prompt for the variable context. The character template's cut-priority order says what
goes first when a block is over.

## Canon

`canon.yaml` holds every fact with an id, a statement, a tier, a status and a source. Default
tiers, hardest first: `foundation` (premise, rules, map; only an owner answer changes it), `world`
(places, cast, looks, formats; owner-approved), `episode` (what happened in a post; agents may
append, checked against the tiers above), `apocrypha` (not canon). A world may declare its own
under `tiers:`.

## What the prompt formula drops

skene's first example production names one or two style references in each shot prompt's
`Style:` line. This contract drops that slot on purpose: references stay in the bible, and the
render line names a technique.
