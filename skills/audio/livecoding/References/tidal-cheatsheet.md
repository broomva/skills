# TidalCycles cheatsheet

Quick reference. Not exhaustive — see <https://tidalcycles.org/docs/> for the full pattern API.

## Boot + tempo

```haskell
-- cps = BPM / 60 / beats_per_cycle (beats_per_cycle usually 4)
setcps (130/60/4)

-- Stop all channels
hush

-- Stop a specific channel
d1 silence

-- Or just edit `d1 $ ...` to `d1 $ silence` and Shift-Enter
```

## Channels

- `d1` through `d16` — independent layers
- `p "name"` — named channel (useful for hand-tracking and templates)

## Pattern mini-notation

```haskell
"bd cp"            -- two events evenly spaced across a cycle
"bd*4"             -- bd repeated 4 times
"bd/4"             -- bd plays once every 4 cycles
"bd ~"             -- bd then rest
"[bd cp] sn"       -- group: bd+cp in first half, sn in second
"bd(3,8)"          -- Euclidean: 3 hits across 8 steps
"bd(3,8,2)"        -- Euclidean with rotation offset 2
"bd:2"             -- second sample in 'bd' bank (0-indexed)
"bd!3"             -- bd repeated 3 times in current slot
"<bd cp sn>"       -- alternate per cycle (1st cycle bd, 2nd cp, 3rd sn, ...)
"bd | cp | sn"     -- random choice per event
"{bd cp sn, hh hh}" -- polyrhythm: both rhythms in same time
```

## Effects (apply with `#`)

| Effect | Typical range | Purpose |
|---|---|---|
| `gain x` | 0..2 | Volume (1 = unity) |
| `pan x` | 0..1 | Stereo (0=L, 0.5=center, 1=R) |
| `speed x` | -N..N | Sample playback rate (also pitches; negative = reverse) |
| `note x` | -inf..inf | Pitch in semitones (for synths) |
| `cutoff x` | 0..20000 | Lowpass cutoff Hz |
| `hcutoff x` | 0..20000 | Highpass cutoff Hz |
| `resonance x` | 0..1 | Filter Q |
| `room x` | 0..1 | Reverb mix |
| `size x` | 0..1 | Reverb size |
| `delay x` | 0..1 | Delay mix |
| `delaytime x` | 0..N | Delay time (cycles) |
| `delayfeedback x` | 0..1 | Delay feedback |
| `crush x` | 1..16 | Bitcrush (lower = harder) |
| `shape x` | 0..1 | Soft-clip distortion |
| `attack x` | 0..N | Amp envelope attack (cycles) |
| `release x` | 0..N | Amp envelope release (cycles) |

## Pattern combinators

```haskell
fast 2 $ s "bd*4"              -- 2× density
slow 2 $ s "bd*4"              -- 2× sparser
rev $ s "bd cp sn"             -- reverse
jux rev $ s "bd cp sn"         -- reverse on right channel only (wide stereo)
every 4 (# speed 2) $ ...      -- every 4th cycle, double speed
every 3 rev $ ...              -- reverse every 3rd cycle
chunk 4 rev $ ...              -- one of 4 chunks gets reversed, rotating
degradeBy 0.3 $ ...            -- randomly drop 30% of events
sometimes (# crush 4) $ ...    -- ~50% chance per event
sometimesBy 0.3 (# crush 4) $ ... -- 30% chance
striate 4 $ s "vox"            -- chop sample into 4 pieces, interleave across cycle
chop 8 $ s "breaks:0"          -- chop into 8 slices, play in order
loopFirst $ ...                -- repeat first cycle forever (lock pattern)
ply 3 $ ...                    -- repeat each event 3 times in its slot
```

## Continuous signals

```haskell
sine                  -- sine wave 0..1
saw                   -- ramp 0..1
square                -- square wave 0..1
tri                   -- triangle 0..1
rand                  -- white noise 0..1 (new per event)
irand 8               -- integer random 0..7
choose [1, 3, 5]      -- random choice from list
range 200 2000 $ sine -- scale to range
slow 4 sine           -- slower

-- Use anywhere a number is expected:
# cutoff (range 300 4000 $ slow 8 sine)
# pan (range 0.2 0.8 $ rand)
# speed (choose [1, 0.5, 2])
```

## Stacking layers

```haskell
d1 $ stack [
    s "bd*4",
    s "~ cp ~ cp",
    fast 2 $ s "hh*4"
  ]

-- Stack with per-layer effects:
d1 $ stack [
    s "bd*4" # gain 1.0,
    s "~ cp ~ cp" # room 0.5,
    fast 2 $ s "hh*4" # pan (range 0.2 0.8 rand)
  ]
```

## Common sample banks (Dirt-Samples)

| Bank | Contents |
|---|---|
| `bd` | Kick drums |
| `cp` | Claps |
| `sn` | Snares |
| `hh` | Closed hats |
| `oh` | Open hats |
| `perc` | Various percussion |
| `bass` | Basslines/sub |
| `breaks` | Drum break loops (Amen etc.) |
| `vox` | Vocal samples |
| `alphabet` | Spoken letters A-Z |
| `808bd` `808hh` `808sn` | 808 emulations |
| `industrial` | Industrial textures |
| `metal` | Metallic hits |
| `wind` | Wind/ambient textures |

Full list: `ls ~/Library/Application\ Support/SuperCollider/downloaded-quarks/Dirt-Samples/`.

## Useful keyboard shortcuts (VS Code Tidal extension)

| Action | Keybind |
|---|---|
| Evaluate current block | `Shift-Enter` |
| Evaluate current line | `Cmd-Enter` |
| Hush all | `Cmd-.` or type `hush` and Shift-Enter |
| Boot Tidal | Command palette → `TidalCycles: Boot Tidal` |
