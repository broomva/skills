---
name: "{World} look"
slug: look
kind: style
render_style: "{e.g. stylized feature animation; see content-engine-cinema style-library §27}"
canon: ["{canon fact ids}"]
status: draft
---

# {World}: style lock (`styles/look.md`)

> The style lock is written, because content-engine's library has no preset for
> most stylized looks. Every phrase is a parameter that can be pasted: models
> read parameters, not feelings. Fenced `prompt` blocks are pasted; everything
> else is for people.

## The render line

One line, pasted into every image prompt after the character and location
blocks. It names a technique, never a studio, film or artist.

```prompt render
{render technique}, {material response}, {shading model}, {proportion language}, {texture}
```

Blend, if any: {primary style} 70%, {secondary} 30% (content-engine's blend
rule).

## Palette roles

Two or three colours plus neutrals. No pure #FFFFFF or #000000.

| Role | Hex | Where it appears | Never |
|---|---|---|---|
| Primary | #{…} | {…} | {…} |
| Secondary | #{…} | {…} | {…} |
| Accent | #{…} | {the one thing that carries it} | {…} |
| Neutral light | #{…} | {…} | |
| Neutral dark | #{…} | {…} | |

## The light rule

One sentence anyone can check by eye, then the table.

**{The rule, e.g. "warm outside, cool inside; the two never blend to grey"}**

| Light | Colour temperature | Where | Prompt words |
|---|---|---|---|
| {…} | {…} K | {…} | {…} |

## Camera package

| Shot type | Lens (or virtual lens) | Aperture / depth | Use |
|---|---|---|---|
| Wide | {…} | {…} | {…} |
| Medium | {…} | {…} | {…} |
| Close-up | {…} | {…} | {…} |
| Insert | {…} | {…} | {…} |

Movement: {one camera move per shot, always with an endpoint}.

## The vertical frame

Content-engine's layout contract (`layout/vertical-9x16.json`) holds the zones;
quote it, do not copy numbers. The prompt sentence for framing:

```prompt framing
{vertical 9:16; eyes at the upper-third line; the lower right quarter and the bottom eighth hold only empty background}
```

## Grade

{LUT or grade description; grade the hero image first}

## Texture

```prompt texture
{surface and grain words}
```

## The NO list

What breaks the look. Phrased so it can become a shot's `Constraints:` line.

- {…}

## The prompt formula

Each shot prompt fills every slot in this order (content-engine's
SHOT + LENS + LIGHT + TEXTURE + COMPOSITION + STYLE):

1. `Shot:` type, angle, depth.
2. `Character:` the character's `fixed-dna` and `wardrobe`, verbatim.
3. `Action:` the variable context.
4. `Lens:` from the camera package.
5. `Light:` the named setup and kelvins.
6. `Location:` and `Lighting:` verbatim, plus a `state` sentence.
7. `Prop:` verbatim.
8. `Render:` the render line above.
9. `Texture:` the texture line.
10. `Composition:` the framing sentence.
11. `Evoking:` one phrase of emotional intent.
12. `Constraints:` the NO list for this shot.

There is no `Style:` slot naming a reference. That departs from earlier
skene examples on purpose: references stay in this file.

## Style references (bible only)

Never pasted into a prompt or a post; `world_check.py` fails a pasted block that
names one (W11). Bold the maker, italicise the work:

- **{Maker}** — *{Work}* ({year}): {what to take, as parameters}
