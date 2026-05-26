# StarterPattern — vibe-descriptor → Tidal pattern

Translate a vibe descriptor ("industrial polyrhythmic", "ambient drone",
"drum-and-bass break", "footwork", "techno") into a TidalCycles starter pattern
the user runs in their booted session and mutates live.

## Inputs to capture

1. **Vibe / genre tag** — e.g. "industrial", "ambient", "DnB", "footwork", "techno", "algorave-glitch"
2. **BPM hint** — if given. If not, infer from the genre:
   - ambient: 60-80
   - techno: 125-135
   - industrial: 130-140
   - DnB: 165-175
   - footwork: 155-165
   - algorave-glitch: 130-145 (variable)
3. **Target intensity** — sparse / medium / dense
4. **Sample palette** — default `bd cp hh sn`, or named sub-banks (`bd:2`, `808bd:0`, `industrial:3`)

## Base template (compose all layers from this)

```haskell
-- BPM: cps = BPM / 60 / beats_per_cycle (beats_per_cycle is usually 4)
setcps (130/60/4)

-- d1: drum spine
d1 $ stack [
    s "bd*4",                          -- four-on-floor
    s "~ cp ~ cp",                     -- offbeat clap
    fast 2 $ s "hh*4"                  -- 8th-note hats
  ]

-- d2: bass
d2 $ s "supersaw" # note "c2 ~ ~ eb2 ~ ~ g2 ~"
  # cutoff (range 200 2000 $ slow 4 sine)
  # resonance 0.4
  # gain 0.8

-- d3: pad/texture
d3 $ slow 2 $ s "supersaw" # note "c4'maj7"
  # cutoff 800 # gain 0.5
  # room 0.5 # size 0.7

-- Stop:
-- hush
```

## Vibe-to-mutation map

| Vibe | Mutations to apply |
|---|---|
| **Industrial** | `setcps (135/60/4)`; add `# crush 4` to drums; `# room 0.6 # size 0.8` everywhere; sample bank `808bd` or `industrial`; bass uses `# shape 0.6` for distortion |
| **Ambient drone** | `setcps (65/60/4)`; remove `d1` drums entirely; `slow 8` on pad; `# cutoff 400 # resonance 0.6`; `# attack 2 # release 6`; long reverb `# room 0.9 # size 0.95` |
| **DnB (Amen-flavored)** | `setcps (172/60/4)`; `d1 $ s "bd ~ ~ ~ ~ ~ sn ~"`; chopped breaks `d2 $ chop 8 $ s "breaks:0"`; long sub `d3 $ s "sub:0" # note "c1"` slow 8 |
| **Footwork** | `setcps (160/60/4)`; `d1 $ s "bd(5,8)"` Euclidean; vox stabs `d2 $ s "vox*16" # speed (range 0.8 1.4 rand) # gain 0.7`; minimal kick + clap |
| **Techno (Berlin)** | `setcps (130/60/4)`; four-on-floor + offbeat hats; long sub bass `d3 $ slow 4 $ s "bass:0"`; minimal but evolving filter `# cutoff (range 300 3500 $ slow 16 sine)` |
| **Algorave-glitch** | `setcps (135/60/4)`; heavy `jux rev`; `degradeBy 0.3 $ ...` on most layers; random speed `# speed (range 0.7 1.5 rand)`; `# crush 4`; aggressive `every 4 (chunk 4 rev)` |
| **Dub** | `setcps (75/60/4)`; sparse `d1 $ s "bd ~ ~ ~"`; `# delay 0.6 # delaytime 0.375 # delayfeedback 0.7` on every layer; `# room 0.8` for space |

## Mutation operators (composable, apply to any layer)

| Operator | Effect |
|---|---|
| `fast n $ ...` | n× density |
| `slow n $ ...` | n× sparser |
| `rev $ ...` | reverse |
| `jux rev $ ...` | reverse on right channel only — wide stereo |
| `every n f $ ...` | apply `f` every n cycles |
| `chunk n f $ ...` | apply `f` to one of n chunks, rotating each cycle |
| `degradeBy 0.3 $ ...` | randomly drop 30% of events |
| `sometimes f $ ...` | apply `f` ~50% of the time |
| `striate 4 $ ...` | chop sample into 4 pieces, interleave |
| `# crush 4` | bitcrush (lower = more crushed) |
| `# shape 0.6` | soft-clip distortion |
| `# delay 0.4 # delaytime 0.375 # delayfeedback 0.6` | dub-style echoes |
| `# room 0.6 # size 0.8` | reverb |
| `# pan (range 0.2 0.8 rand)` | random stereo pan per event |

## Agent invocation pattern

When invoked:

1. **Capture** vibe + BPM hint + intensity from the user message
2. **Confirm** the stack is booted (`d1 $ silence` would error if not — but cheaper: ask "is Tidal booted?" or assume yes if the user is mid-session)
3. **Compose**: start from the base template, apply the vibe-map mutations, adjust BPM
4. **Output** as a single fenced `haskell` block with comments on each `d1/d2/d3/d4` explaining what that layer does
5. **Suggest** 2-3 live mutations the user can try by editing a single line and pressing `Shift-Enter` (e.g. "swap `# crush 4` → `# crush 2` for harder bitcrush")
6. **Offer**: "Want a Hydra visual that syncs to this?" → routes to HydraVisuals workflow with a visual matched to the vibe

## Example agent output

User: *"Give me an industrial polyrhythmic pattern at 138 BPM"*

```haskell
-- 138 BPM industrial polyrhythmic
setcps (138/60/4)

-- d1: drum spine, bitcrushed kicks + offbeat claps + euclidean ride
d1 $ stack [
    s "bd*4" # crush 4 # shape 0.4,
    s "~ cp ~ cp" # room 0.4 # size 0.6,
    fast 1.5 $ s "hh(7,16)" # gain (range 0.4 0.8 $ slow 4 sine)
  ] # room 0.5 # size 0.7

-- d2: industrial bass — distorted, dark
d2 $ s "supersaw" # note "c1 ~ ~ eb1 ~ ~ g1 ~"
  # cutoff (range 150 1800 $ slow 6 sine)
  # resonance 0.5
  # shape 0.6
  # gain 0.9

-- d3: metallic texture — chopped + warped
d3 $ slow 2 $ chop 8 $ s "metal:0"
  # speed (range 0.8 1.2 $ rand)
  # gain 0.6
  # delay 0.4 # delaytime 0.1875 # delayfeedback 0.5
```

Live mutations to try (one line at a time, `Shift-Enter`):
- swap `s "bd*4"` → `s "bd(5,8)"` for more polyrhythmic kick
- `# crush 4` → `# crush 2` for harder bitcrush
- add `# pan (range 0.2 0.8 rand)` to d2 for stereo dispersion
