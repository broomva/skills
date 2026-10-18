# Where content-engine's defaults bend for a world

Content-engine was written around a photoreal human influencer with paid verification. A
stylized, non-human world built in a grill that generates nothing departs from it in eight places:
the seven conflicts a read of content-engine found (2026-10-16), and one gap. Each has a
resolution here, and the additive changes to content-engine are listed at the end.

| # | Conflict | Where in content-engine | Resolution in this modality |
|---|---|---|---|
| 1 | **Human-only identity fields**: age, ethnicity, skin tone, face embeddings | `templates/character-sheet.md` Identity and Consistency Anchors | The character template's species rows (subject, species, body plan, anthropomorphism, silhouette, surface, colour, face, marks), modelled on the product Fixed-DNA slots. content-engine's character sheet gains a "Species and body" section beside the human one |
| 2 | **A photoreal default**: "Ultra-realistic … no stylization"; the negative prompt bans "cartoon, anime, illustration" | `dna/references/character-sheets.md` identity-lock example; `templates/brand-dna.md` negative prompt | The style lock sets the render style; Fixed DNA holds identity only, with no render words. Drop the photoreal negatives when the world is stylized |
| 3 | **Reference volume**: 5–12 images per character | `dna/references/character-sheets.md` Step 1 | skene's lock count rules: 5–20 stills per character, planned in the manifest. The multi-view sheet is optional, a technique for making them |
| 4 | **Paid verification**: 5 test generations | `dna/references/character-sheets.md` Step 6 | The grill generates nothing. Verification moves to skene's metered asks; the sheet lists the traits to check first |
| 5 | **No cap on Fixed DNA** | `dna/references/character-sheets.md` "Character DNA = Master Prompt" | `dna_cap` per world (default 600, the owner's choice), checked by W05, with a cut-priority order |
| 6 | **Mismatched defaults and types**: the storyboard defaults to 16:9 and 8 s shots; the type enums disagree (`style-guide` vs `style-preset`) | `templates/storyboard.md`; template frontmatter | The world states its own frame and shot length in `accounts.md` per format and in the style lock's framing line. It uses skene's library kinds (character, ensemble, location, prop, sound, style) as its only type vocabulary |
| 7 | **No filled-in examples**: `knowledge/compiled/` holds only `.gitkeep`; the only examples are fictional humans inside the docs | `knowledge/compiled/` | `examples/lantern-market/`: a small fictional world, non-human cast, that passes `--complete` |
| 8 | **No stylized-3D style preset** (the gap): the closest are Neo 3D and Rubberhose | `cinema/references/style-library.md` | A new entry, §27 Stylized Feature Animation, and the style lock's own render line |

## Rules that change world-building answers

- **"1 account = 1 character"** (`dna/references/character-sheets.md`). An ensemble or shared-world
  account records its exception in `accounts.md`, with the answer that allowed it, and the world
  states its consistency model (A master brand, B brand family).
- **Fixed DNA is pasted verbatim forever; the outfit is variable context.** Where a world uses
  "one silhouette" as identity, the default wardrobe is identity too: changing it needs an answer.
- **Multi-character shots: generate each character separately, then composite.** Plan crossovers
  with that cost.
- **An image-to-video prompt describes motion only, in 20–40 words; one shot, one camera move.**
  The character template's motion directives are written to fit.
- **The 9:16 face gate skips frames where it finds no face**, so animal and creature faces may go
  unchecked by the layout gate. Note it in the style lock's framing section and check those frames
  by eye.

## What changed in content-engine (additive)

- `skills/content-engine-cinema/references/style-library.md`: §27 Stylized Feature Animation.
- `templates/character-sheet.md`: a "Species and body" section and a capped Fixed-DNA block, beside
  the human fields, which become optional for non-human characters.
- `skills/content-engine-dna/references/character-sheets.md`: a note that the photoreal identity
  lock is a default for human characters, pointing here for stylized and non-human casts.
