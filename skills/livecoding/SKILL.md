---
name: livecoding
version: 0.1.0
description: Algorave-grade livecoded music workflow — TidalCycles patterns (Haskell DSL driving SuperDirt over OSC) + Hydra-synth visuals (browser or VS Code Simple Browser via a local HTML page that loads hydra-synth from CDN). Wraps the boot ritual (SuperCollider → SuperDirt → Tidal → Hydra), a vibe-descriptor pattern generator (industrial, ambient, DnB, footwork, techno, algorave-glitch), and a reference tunnel-visuals page for the @lo.fi.sci.fi-projected aesthetic. Mac-first; ports to Linux with package-name swaps.
author: broomva
license: MIT
tags: [livecoding, tidalcycles, supercollider, superdirt, hydra, algorave, music, visuals, code-as-music]
trigger_keywords:
  - livecoding, livecode, algorave, tidalcycles, tidal cycles
  - supercollider, superdirt, sonic pi, strudel
  - hydra, hydra-synth, hydra visuals, projection visuals
  - make music, write a pattern, generate a tidal pattern
  - boot tidal, start tidal, livecoding session
  - generate visuals, tunnel visuals, kaleidoscope
  - switch_angel, polymatters, lo.fi.sci.fi
when_to_use: Any time the user wants to write code that emits music in real time, generate or mutate Tidal patterns, or set up Hydra visuals for a livecoding session. Also invoked when the user references algorave artists and asks to recreate the style. Default first action — walk Workflows/Boot.md prereq check before generating any patterns; the agent never dumps a pattern into the chat when the user's stack might not be running yet.
---

# Livecoding — TidalCycles + Hydra workflow

A skill for the algorave / livecoded-electronic-music workflow. You write code
in real time → patterns emit OSC messages → SuperDirt synthesizes the audio →
Hydra renders matching visuals. Same lineage as `#livecode #electronicmusic
#algorave`.

This is **code-as-music**, not AI-generated music. The aesthetic comes from
polyrhythmic + cyclic structure idiomatic to the tool, not from a generative
model. For AI-music generation (Suno / Udio / MusicGen), that's a separate
stack — out of scope here.

## When to invoke

| User intent | Workflow | Quick command |
|---|---|---|
| "Get me set up" / fresh install / "is everything working?" | [Boot](Workflows/Boot.md) | Walk prereq check + boot ritual |
| "Generate a pattern" / "make me a beat" / "give me an industrial pattern" | [StarterPattern](Workflows/StarterPattern.md) | Vibe descriptor → Tidal pattern |
| "Visuals" / "tunnel" / "kaleidoscope" / "open Hydra" | [HydraVisuals](Workflows/HydraVisuals.md) | Open the Hydra page; offer pattern mutations |

Default discipline: any livecoding-domain conversation opens with a state check
— is SuperCollider running? Is `SuperDirt.start;` evaluated? Is Tidal booted in
the editor? — before generating patterns. Dumping a pattern into a chat when
the user's stack isn't running just produces frustration.

## The stack

```
  Editor (VS Code + Tidal extension)     ← you write Haskell-ish patterns
        │
        ▼  OSC (UDP 57120)
   TidalCycles (Haskell, in ghci)        ← cycles + pattern combinators
        │
        ▼  OSC
   SuperDirt (SuperCollider quark)       ← sampler + synth router
        │
        ▼
   scsynth (SuperCollider server)        ← audio synthesis → speakers


   Browser / VS Code Simple Browser      ← visuals pane
        │
        ▼
   hydra-synth (WebGL)                   ← livecoded visuals, separate process
```

## Prereqs (Mac)

| Component | How to verify | Install |
|---|---|---|
| Homebrew | `brew --version` | <https://brew.sh> |
| SuperCollider | `ls /Applications/SuperCollider.app` | `brew install --cask supercollider` |
| SuperDirt | open SC → `Quarks.installed.do(\|q\| q.name.postln)` | In SC: `Quarks.install("SuperDirt", "v1.7.3");` |
| Haskell | `ghc --version && cabal --version` | `curl -sSf https://get-ghcup.haskell.org \| sh` |
| TidalCycles | `ghci -e 'import Sound.Tidal.Context'` | `cabal install tidal --lib` |
| VS Code | `ls /Applications/Visual\ Studio\ Code.app` | <https://code.visualstudio.com> |
| VS Code Tidal extension | `code --list-extensions \| grep tidal` | install `tidalcycles.vscode-tidalcycles` |

See [Boot workflow](Workflows/Boot.md) for the full sequence with troubleshooting.

## First sound (the boot ritual, short form)

1. **SuperCollider.app** → evaluate `SuperDirt.start;` (`Cmd-Return` on the line)
2. **VS Code** → open a `.tidal` file → command palette → `TidalCycles: Boot Tidal`
3. In the `.tidal` file:
   ```haskell
   d1 $ s "bd*4"
   ```
4. `Shift-Enter` on that line. Kick drum every quarter beat.
5. To stop: `hush` then `Shift-Enter`.

If you hear nothing → SuperDirt isn't running. Re-run `SuperDirt.start;` in SC.

## Visuals (short form)

Open `References/hydra-tunnel.html` in your browser (or VS Code's Simple Browser
pane next to your `.tidal` file). Starter pattern: industrial kaleidoscopic
tunnel. Edit in the floating editor → `Cmd-Enter` to re-eval. See the
[HydraVisuals workflow](Workflows/HydraVisuals.md) for audio-reactive setup
(via BlackHole virtual audio cable) and the full `@lo.fi.sci.fi`-aesthetic toolkit.

## Composes with

- **persist** (P12) — `persist iterate livecoding-session.md` for self-rebooting
  long sessions where the agent rotates through pattern mutations across hours
- **bookkeeping** (P6) — high-signal patterns/textures discovered in a session
  promote into `research/entities/concept/livecoding-*.md` via Nous gate ≥ 5/9

## Out of scope (for now)

- AI-generated music (Suno / Udio / MusicGen). Separate stack, separate skill.
- Foxdot, Sonic Pi. Siblings of Tidal, not yet covered.
- Strudel (`strudel.cc`) — browser-only Tidal sibling; obvious next add since
  patterns mostly port directly. Roadmap.
- Hardware MIDI / Eurorack integration. Workflow exists (SuperDirt → MIDI out)
  but isn't documented here.

## References

- [Workflows/Boot.md](Workflows/Boot.md) — full boot ritual with troubleshooting
- [Workflows/StarterPattern.md](Workflows/StarterPattern.md) — vibe→pattern generator
- [Workflows/HydraVisuals.md](Workflows/HydraVisuals.md) — Hydra setup + tunnel primitives
- [References/tidal-cheatsheet.md](References/tidal-cheatsheet.md) — Tidal mini-notation + effects + combinators
- [References/hydra-cheatsheet.md](References/hydra-cheatsheet.md) — Hydra source/transform/blend API
- [References/hydra-tunnel.html](References/hydra-tunnel.html) — self-contained Hydra page (CDN-loaded, no install)

## Provenance

Substance ported from `~/broomva/research/notes/2026-05-23-tidalcycles-mac-setup.md`
written 2026-05-23 in response to a user request to learn the
`@_switch_angel` / `@_polymatters` / `@lo.fi.sci.fi` algorave style. Validated against:

- SuperCollider 3.13+, SuperDirt 1.7.3
- TidalCycles 1.9+, GHC 9.6.6 LTS
- hydra-synth 1.4.0 (npm, CDN-served via unpkg)
- vercel-labs/skills CLI install semantics (verified 2026-05-23)
