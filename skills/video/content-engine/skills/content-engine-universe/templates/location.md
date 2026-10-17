---
name: "{The place}"
slug: "{slug}"
kind: location
canon: ["{canon fact ids}"]
accounts: ["{account}"]
status: draft
---

# {The place}: location sheet

> The fenced blocks are what skene pastes: `description`, `lighting`, and one
> `state <name>` block per named state (`entry.json` `states`). A slot names a
> state as `{slug}@{state name}`.

## Description

Concrete nouns, materials, scale and era. No light and no mood here: those go
in `lighting` and the states.

```description
{The place}: {what it is}, {layout}, {materials}, {the three to five objects that make it recognisable}.
```

## Lighting

The light rule for this place, in sources and colour temperatures, so it can be
pasted (content-engine's scene-brief key, fill, rim and practicals).

```lighting
{key source and kelvin}; {fill}; {rim or practicals}; {contrast and what stays black}.
```

| Role | Source | Colour temperature | Prompt words |
|---|---|---|---|
| Key | {…} | {…} K | {…} |
| Fill | {…} | {…} K | {…} |
| Rim / practicals | {…} | {…} K | {…} |

## States

At least one. Each is a change of time, condition or era that a shot can name.

```state {day-to-day}
{what is different in this state}
```

```state {extraordinary}
{what is different in this state}
```

## Scene-brief fields (content-engine `templates/scene-brief.md`)

- **Mood:** {two or three words, then as parameters}
- **Time and place:** {when, where in the world}
- **Key props:** {props/ slugs}
- **Props to avoid:** {what breaks the place}
- **Camera:** {default lens and height for this place}
- **Vertical framing:** {where depth runs in a 9:16 frame}

## What happens here

| Format or beat | State | Characters |
|---|---|---|
| {format} | {state} | {slugs} |
