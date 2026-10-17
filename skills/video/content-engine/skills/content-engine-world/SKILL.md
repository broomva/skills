---
name: content-engine-world
description: "World-building pre-production for a skene production: a /grill-me over a design tree that takes an owner from nothing to a documented world (bible, canon, cast, locations, props, look, sound, formats, timeline and an asset manifest skene can make). Distils the owner's taste first, opens with a divergent round of 4-6 world seeds before any convergent question, proposes ideas proactively, asks through the Maestro asks ledger, and writes the files as it goes; world_check.py gates the result. Generates nothing and spends nothing. Triggers on: 'build a world', 'world-building', 'universe bible', 'series bible', 'pre-production', 'create the universe', 'grill me on the world', 'cast and canon', 'content-engine world'. Not for compiling an existing brand from assets (content-engine-dna), generating shots (content-engine-cinema), or a single character sheet for a world that already exists (use the template directly)."
version: 0.1.0
author: broomva
tags:
  - world-building
  - pre-production
  - grill
  - canon
  - skene
  - content-engine
compounding:
  - grilling
  - content-engine-dna
  - content-engine-cinema
  - content-engine-loop
---

# content-engine-world — world-building pre-production

Build a fictional world with its owner, from scratch, and write it down so that a production can
run on skene. The engine is `/grill-me`: rounds over a design tree, each round asking the whole
frontier at once. The leaves of the tree are the fields skene's library and content-engine's
templates need. Every asset, every recurring format and every rule traces back to an answer the
owner gave, recorded verbatim.

```
DISTIL TASTE → ROUND 0 (diverge: seeds) → ROUNDS 1..N (converge: the tree) → CHECK → HAND TO SKENE
                     ↑ documents are written after every round, not at the end ↑
```

## The rule this skill exists to enforce

**Assets on disk are evidence, never defaults.** The first attempt at this process anchored on five
random test generations it found on disk, and its first questions were convergent, about those
assets. The owner withdrew the whole round. So:

- Round 0 pitches 4–6 genuinely different worlds before any convergent question. At least one is a
  stretch, and one goes deliberately against the owner's taste.
- Whatever already exists (test renders, an earlier project, a spec's proposal) goes into
  `evidence.md` and canon tier `apocrypha`. It enters the world only when a round adopts it by name.
- `world_check.py` fails a world whose round 0 is missing, too small or has no stretch seed (W13), and
  a canon fact locked on evidence alone (W04).

## When to invoke

- An owner wants a new fictional world, universe, series or cast for short-form or episodic content.
- A production on skene needs its pre-production layer: library entries with `dna`, `wardrobe`,
  `description`, `lighting` and `states`.
- An existing world needs a new frontier grilled (a new altitude, season or account): run the tree
  from that node, and keep round 0's rule for any new seed.

## Hard rules

1. **No paid generation.** No skene runs, no Higgsfield, treg or other generate tools. Images come
   later, through skene's metered asks, each approved by the owner. The manifest estimates; it never spends.
2. **No real likeness.** Every character declares `likeness: original` (W07). Canon uses owned IP
   only. Parody of other people's IP, if the owner allows it at all, is a separate, non-canon lane.
3. **Taste references never reach a prompt or a post.** Films, artists and makers the owner admires
   live in `owner-taste.md` and the style lock's "Style references (bible only)". A pasted block
   (`fixed-dna`, `wardrobe`, `description`, `lighting`, `state`, `prompt`, `caption`, any
   `*.prompt.md`) that names one fails W11. The render line names a technique, never a studio.
4. **Every post is disclosed as AI-made**, and every cross-account crossover as fiction. Each account
   declares its disclosure (W16).
5. **Facts are yours, decisions are the owner's.** Dispatch subagents to verify facts; never ask the
   owner something you could look up. Never decide for them something only they can answer.

## The method (details: `references/method.md`)

### 1. Before the first question: distil the owner

Read everything that describes them (persona notes, memory, their own productions, their design
system, answered asks) and write `owner-taste.md` from `templates/owner-taste.md`: id'd tables of
loves (`T`), aesthetic principles (`A`), wants for this production (`G`) and anti-tastes (`X`), each
row with a source. Then list what is already decided (never re-ask it) and what is merely proposed.
A rule found in a spec or a note counts as decided only when an answered ask backs it.

### 2. Round 0 is divergent

Pitch 4–6 seeds. Each gets a premise, a hook, why it fits (taste ids), why it suits short-form, a
cost from real price anchors, and its main risk. One seed stretches past the obvious; one goes
against the owner's taste. Ask **each seed as its own question** (Build on it / Keep as an
ingredient / Drop it) so the owner can mix them, and ask the **shape question** (one world or many)
in the same round. Owners tend to decide the shape first.

### 3. Then the grill

Work the design tree in rounds. Each round asks the whole frontier at once, about 8 questions, each
numbered with a recommendation and a one-line reason tied to a taste id or a verified fact. A
question that depends on another open question waits for the next round. Each round may close with
**Proposals**: ideas the owner did not ask for (a character, a place, a recurring bit, a hidden
detail, a cross-account mechanic), including one against the grain.

Tree order, roughly: seed and premise → tone, genre, rating, audience → world rules (physics, magic
or technology, who lives there, time) → setting and geography → factions → cast (want, flaw, voice,
look, relationships) → visual DNA (render style, palette roles, light rule, camera, grade, texture)
→ sound → language → channels, formats and hooks → timeline and arcs → the cross-account nexus →
names and handles → canon governance → the asset manifest.

### 4. Ask through the decision layer

When the owner answers on a phone (Maestro), put each round in an asks ledger
(`.control/asks/<arc>.yaml`, per `DECISION-LAYER.md`): one ask per question, 2–4 options, exactly one
recommended, headlines of 100 characters or fewer ending in "?". Stamp and validate it
(`scripts/ask_ledger.py stamp|validate`). Post the same round in the session. **The ledger file is the
source of truth for answers**; relayed messages can trail it by a round.

### 5. Document as you go

After every round, before the next one goes out: copy the answers verbatim into `decisions.md`,
update `canon.yaml`, `bible.md` and every file the round touched, add a `### Method notes` bullet on
what worked and what did not in the process, and run the checker.

### 6. Check, then hand to skene

```bash
python3 scripts/world_check.py check <world>             # during the grill: what exists must hold
python3 scripts/world_check.py check <world> --complete  # at the end: the whole contract
python3 scripts/world_check.py leak <public dir> --taste <owner-taste.md>   # only if a taste line must stay private
```

Done when the frontier is empty, `--complete` passes and the owner says the world is complete.
Then write a human-read summary (self-contained HTML) and land the world in the owner's repo.

## The output contract (details: `references/output-contract.md`)

| File | Template | Holds | skene / content-engine target |
|---|---|---|---|
| `owner-taste.md` | owner-taste.md | the distilled owner, cited | — (bible only) |
| `decisions.md` | decisions.md | every round, recommendation and verbatim answer, method notes | — |
| `bible.md` | bible.md | premise, tone, rules, themes, what the world is not | brand-dna LORE |
| `canon.yaml` | canon.yaml | every fact: id, statement, tier, status, source; `dna_cap` | — |
| `evidence.md` | evidence.md | assets and policies found, not decided | — |
| `characters/<slug>.md` | character.md | species-aware identity, `fixed-dna` ≤ cap, `wardrobe` blocks, personality | `cast/<slug>/entry.json` `dna`, `wardrobe` |
| `locations/<slug>.md` | location.md | `description`, `lighting`, `state <name>` blocks | `locations/<slug>/entry.json` |
| `props/<slug>.md` | prop.md | `description`, states | `props/<slug>/entry.json` |
| `styles/look.md` | style-lock.md | render line, palette, light rule, camera, grade, NO list, prompt formula | `styles/look/entry.json` |
| `sound.md` | sound.md | music, sound logo, SFX, how characters speak | `sound/<slug>/` |
| `timeline.md` | timeline.md | dated canon events, season arcs | — |
| `accounts.md` | accounts.md | accounts, disclosure, formats, graded mechanics, the nexus | content-engine-loop calendar |
| `asset-manifest.md` | asset-manifest.md | every library entry: kind, slug, sheet, stills (5–20), estimate | skene library |

The Fixed-DNA cap is the owner's choice, not a skene limit (skene sets none): `dna_cap` in
canon.yaml, default 600, overridable with `--dna-cap`. The character template gives the cut-priority
order for a block over the cap.

## Checks (`scripts/world_check.py`)

| Code | Fails when |
|---|---|
| W01 | a canon id is used twice |
| W02 | a canon fact has no statement, or an unknown tier or status |
| W03 | a source cites a decision that is not in decisions.md, or none at all |
| W04 | a locked fact rests on a pending answer or on evidence alone; a hard tier rests on evidence |
| W05 | a character has no single `fixed-dna` block, it exceeds the cap, or it does not open with the name |
| W06 | a character has no `wardrobe` block |
| W07 | a character does not declare `likeness: original` |
| W08 | a manifest entry's kind is not a skene library kind |
| W09 | a manifest entry has no sheet, or a sheet has no manifest entry |
| W10 | a character plans fewer than 5 or more than 20 stills |
| W11 | a taste reference appears in a pasted block or a prompt file |
| W12 | a seed or question has no answer, or a paraphrased one |
| W13 | round 0 is missing, has fewer than 4 or more than 6 seeds, no stretch seed, or comes after a later round |
| W14 | an answered round has no method notes |
| W15 | a location lacks `description`, `lighting` or a named `state` |
| W16 | an account declares no disclosure |
| W17 | a decision id is used twice |
| W18 | (`--complete`) a contract file is missing |
| W19 | a short-form mechanic has no evidence grade (measured, reported, heuristic, proposal) |

Tests: `python -m pytest tests/test_world_check.py` from content-engine's root.

## Where content-engine's defaults bend (details: `references/content-engine-conflicts.md`)

Content-engine was written for a photoreal human influencer. A stylized, non-human, unpaid world
departs from it in eight places: human-only identity fields, the photoreal default, the reference
volume, paid verification, an uncapped Fixed DNA, mismatched defaults and types, no filled-in
examples, and no stylized-3D style preset. Each has a resolution. The one-character-per-account
rule becomes a recorded exception per account.

## Files

```
content-engine-world/
├── SKILL.md
├── CHANGELOG.md
├── references/
│   ├── method.md                    the method in full, with the ask shapes
│   ├── output-contract.md           every file and its fields; the mapping to skene's library
│   ├── content-engine-conflicts.md  the eight departures and their resolutions
│   └── lessons.md                   what each live round taught, with its round
├── templates/                       one per output file
├── examples/lantern-market/         a small fictional world that passes --complete
└── scripts/world_check.py           the gate
```
