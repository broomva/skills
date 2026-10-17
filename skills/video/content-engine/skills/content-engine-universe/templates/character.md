---
name: "{Name}"
slug: "{slug}"
kind: character          # character | ensemble (skene library kinds)
subject: animal          # human | animal | creature | object | machine
species: "{species or type, e.g. 'spectacled bear', 'paper golem'}"
body_plan: "{biped | quadruped | winged | serpentine | wheeled | other}"
anthropomorphism: 2      # 0 naturalistic · 1 expressive face · 2 biped posture, paws as hands · 3 full biped, human hands
likeness: original       # required; never a real person, never another studio's character
accounts: ["{account}"]
canon: ["{canon fact ids}"]
voice: "{none | sounds only | spoken: language, register}"
status: draft            # draft until the owner locks it; skene's lock is separate
---

# {Name}: character sheet

> This sheet is the human-readable identity. The fenced `fixed-dna` and
> `wardrobe` blocks are the strings skene pastes (`entry.json` `dna` and
> `wardrobe`; `description` is the two joined). If this prose and those blocks
> disagree, the blocks win.

## Identity

Fill the rows that apply to the subject. Human-only rows (age, heritage, skin
tone, face embedding) are optional and blank for a non-human character; the
species rows replace them. They follow content-engine's product Fixed-DNA slots
(form, material, colour, proportions, marks).

| Field | Human | Non-human | Value |
|---|---|---|---|
| Kind and scale | age range, build, height | species, adult or young, size against a named object | {…} |
| Silhouette | build, posture | body plan, head-to-body ratio, what reads in a black fill | {…} |
| Surface | skin tone and texture | fur, feathers, scales, shell or material, with finish | {…} |
| Colour | hair, eyes | primary and secondary colour, as words and hex | {…} |
| Face | face shape, nose, mouth, eyes | eyes (size, colour, placement), muzzle/beak/snout, ears | {…} |
| Signature mark | scar, mole | the one mark checked first in every close-up | {…} |
| Secondary marks | — | patches, stripes, chips, tags | {…} |

**Personality in frame:** {how they hold still, how they move}

## Fixed DNA

At most **{dna_cap}** characters (the world's `dna_cap` in canon.yaml, default
600; the owner's choice, not a skene limit). It opens with the name and a
colon, holds identity only, and stays verbatim-stable once locked. Render
style lives in `styles/look.md`, never here; wardrobe lives below.

```fixed-dna
{Name}: {kind and scale}; {silhouette and proportions}; {surface and colour}; {face}; {signature mark}; {secondary marks}.
```

### Cut priority (when the block is over the cap)

Cut from the top of this list down, and stop as soon as it fits:

1. Words that belong elsewhere: wardrobe (move it below), pose, expression,
   light, camera, render style (move it to the style lock).
2. Adjectives that eliminate no ambiguity ("beautiful", "cute", "detailed").
3. Restatements: two words for one fact.
4. Secondary marks beyond the two most visible.
5. Fine texture detail (fur direction, pore-level skin).

Never cut, in order of protection: the name and kind; the silhouette and
proportions; the primary colours; the signature mark; the face.

## Wardrobe

One block per outfit. The default comes first. A character who wears nothing
still gets a block saying so. Where the world uses "one silhouette" as
identity, the default outfit is part of the identity and changing it needs an
owner answer.

```wardrobe default
{what they wear in nearly every post}
```

```wardrobe {variant name}
{a named alternate, and when it is worn}
```

**Wardrobe anti-patterns:** {logos, text, colours the style lock forbids}

## Personality

- **Want:** {what they pursue}
- **Flaw:** {what gets in the way}
- **Voice:** {how they sound; for a silent character, how they read without words}
- **Catchphrases or signature bits:** {a gesture, a sound, a line}
- **Never:** {what they never do}

## Relationships

| With | Relationship | Canon id |
|---|---|---|
| {name} | {one line} | {id} |

## Accounts

| Account | Role there | Formats |
|---|---|---|
| {account} | {lead, guest, cameo} | {format names from accounts.md} |

## Motion directives

How the character moves, in parameters (an image-to-video prompt describes
motion only): gait, idle motion, speed, what never moves.

1. {directive}
2. {directive}
3. {directive}

## Reference plan (for skene; nothing is generated in the grill)

- **Hero portrait prompt:** neutral background, frontal, the Fixed DNA plus the
  default wardrobe, the style lock's render line.
- **Stills to lock:** {5–20}; the angles and expressions they cover.
- **Multi-view sheet (optional research technique):** {yes/no}; one 16:9 sheet
  of turnaround views. It helps generation, but skene's lock still needs the
  5–20 stills.
- **Verification:** moves to skene's metered asks. List the traits to check
  first: {signature mark, silhouette, colours}.
