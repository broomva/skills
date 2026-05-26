# livecoding

> Algorave-grade livecoded music workflow for AI agents — **TidalCycles** patterns + **Hydra-synth** visuals.

Code-as-music. You write Haskell-ish patterns in an editor, they emit OSC into SuperDirt, which produces audio in real time. Visuals are livecoded in parallel via Hydra in a browser pane. Same workflow as the algorave scene (`#livecode #electronicmusic`).

## Install

```bash
npx skills add broomva/livecoding
```

Or scoped to Claude Code globally:

```bash
npx skills add broomva/livecoding -g -a claude-code -y
```

## What it does

When you ask an agent (with this skill installed) to livecode music, the agent:

1. **Checks your stack** — Homebrew, SuperCollider, SuperDirt, Haskell, Cabal, TidalCycles, VS Code, the Tidal extension. Reports gaps with install commands.
2. **Walks the boot ritual** — SuperCollider → `SuperDirt.start;` → VS Code `TidalCycles: Boot Tidal` → first sound.
3. **Generates patterns from vibe descriptors** — "industrial polyrhythmic", "ambient drone", "DnB break", "footwork", "techno". Maps each to a TidalCycles `stack [...]` of layers with appropriate mutations.
4. **Wires Hydra visuals** — opens the self-contained `hydra-tunnel.html` page (loads `hydra-synth` from `unpkg`) as a side pane in VS Code or your browser. Offers tunnel/vortex/lattice variations.
5. **Sets up audio-reactive visuals** (optional) — walks the BlackHole virtual-audio-cable setup so Hydra's `a.fft[]` syncs to your Tidal output, not ambient room sound.

## Workflows

| File | When to invoke |
|---|---|
| `Workflows/Boot.md` | "Get me set up", "is my stack working", "boot tidal" |
| `Workflows/StarterPattern.md` | "Generate a pattern", "make me a beat", "industrial pattern" |
| `Workflows/HydraVisuals.md` | "Open visuals", "tunnel", "kaleidoscope", "Hydra" |

## References

| File | Purpose |
|---|---|
| `References/tidal-cheatsheet.md` | Mini-notation, effects, combinators |
| `References/hydra-cheatsheet.md` | Hydra sources/transforms/blend/audio API |
| `References/hydra-tunnel.html` | Self-contained Hydra page — CDN-loaded, zero install |

## Prereqs

Mac-first. SuperCollider + Haskell + a code editor. No Tidal-side install is more involved than `cabal install tidal --lib` once you have GHC. Full prereq matrix in `SKILL.md`.

## License

MIT. Substance derived from the public TidalCycles and Hydra documentation, plus the algorave-scene conventions documented at <https://tidalcycles.org> and <https://hydra.ojack.xyz>.
