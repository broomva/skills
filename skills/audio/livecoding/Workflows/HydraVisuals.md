# HydraVisuals — open and mutate the visuals pane

Hydra is the visual companion to Tidal in the algorave stack. Visuals are
livecoded in a tiny editor floating over a full-window WebGL canvas.

## The page

`References/hydra-tunnel.html` is a **self-contained** Hydra page. It loads
`hydra-synth@1.4.0` from `unpkg.com` (no install) and embeds a floating editor
over a fullscreen canvas. Starter pattern: industrial kaleidoscopic tunnel —
gestures at the `@lo.fi.sci.fi` projected look.

## Opening it (Mac)

The skill install path is the parent of this workflow file. Pick the right
approach for the user's situation:

**Option A — system browser** (simplest, opens fullscreen in default browser):

```bash
open $(dirname "$(dirname "$0")")/References/hydra-tunnel.html
# Or just: open <path-to-skill>/References/hydra-tunnel.html
```

**Option B — VS Code Simple Browser** (in-editor pane next to `.tidal`):

1. `Cmd-Shift-P` → `Simple Browser: Show`
2. Paste `file://<full-path-to-skill>/References/hydra-tunnel.html`
3. Drag the resulting tab to the right pane

**Option C — local server** (fallback if Simple Browser refuses `file://`):

```bash
cd <skill-install-dir>/References && python3 -m http.server 8765
```

Then in Simple Browser point at `http://localhost:8765/hydra-tunnel.html`.

## Keybinds (inside the page editor)

- `Cmd-Enter` / `Ctrl-Enter` → re-evaluate the entire pattern
- `Esc` or `Cmd-.` → `hush` (clear)

## Tunnel-aesthetic primitives (the `@lo.fi.sci.fi` toolkit)

| Primitive | Effect |
|---|---|
| `kaleid(n)` | n-fold radial symmetry — the kaleidoscope wedge |
| `repeat(x, y)` | Tile source x× horizontally, y× vertically |
| `scrollY(0, () => -time * k)` | Forward motion through the tunnel (negative k = into the screen) |
| `modulate(src, amt)` | Warp source by another signal's brightness |
| `rotate(0, speed)` | Continuous rotation |
| `colorama(amt)` | Hue-cycle over time |
| `luma(threshold)` | Threshold by brightness → wireframe / line-art look |
| `invert()` | Color invert |
| `posterize(steps)` | Quantize colors → blocky retro |
| `contrast(n)` | Punch the dynamic range |

**Order matters.** `scrollY` BEFORE `kaleid` warps a moving source through a
kaleidoscope; AFTER `kaleid` scrolls the whole kaleidoscope output.

## Three variations included in the starter file

Commented inline — paste over the main block to try:

1. **Aggressive vortex**
   ```javascript
   shape(4, 0.5, 0.001)
     .repeat(20, 10)
     .scrollY(0, () => -time * 0.15)
     .modulate(noise(3, 0.5))
     .scale(2).colorama(0.5).out()
   ```
2. **Wireframe lattice**
   ```javascript
   osc(20, 0.05, 0.5)
     .kaleid(() => 4 + Math.sin(time * 0.3) * 3)
     .modulate(o0, 0.1)
     .rotate(0, 0.05)
     .luma(0.3).invert().out()
   ```
3. **Audio-reactive (drives `kaleid` from bass)**
   ```javascript
   a.setBins(4)
   osc(10, 0.1, 1)
     .kaleid(() => a.fft[0] * 8 + 4)
     .modulate(noise(3)).out()
   ```

## Audio-reactive setup (Tidal → Hydra sync)

By default `detectAudio: false` in `hydra-tunnel.html` to avoid the mic permission
prompt. To sync visuals to your Tidal output (not ambient room sound):

1. Install virtual audio cable:
   ```bash
   brew install --cask blackhole-2ch
   ```
2. macOS **Audio MIDI Setup** → create a Multi-Output Device that includes both
   your speakers AND BlackHole 2ch
3. Set SuperCollider's output device to that Multi-Output Device
4. Edit `hydra-tunnel.html` → `detectAudio: true`, save, refresh the page
5. Set system mic input to BlackHole 2ch (System Settings → Sound → Input)
6. In the Hydra editor: `a.show()` to confirm bins appear in the corner, then
   drive visuals from `a.fft[0..3]`

## Vibe-matched visuals (when invoked alongside StarterPattern)

If the user just ran StarterPattern and asked for matching visuals, pick:

| Pattern vibe | Matching Hydra preset |
|---|---|
| Industrial | The default tunnel (already loaded) |
| Ambient drone | Slow-rotating `voronoi(5, 0.1, 0.3).colorama(0.05)` with `.scale(2)` |
| DnB | Aggressive vortex with audio-reactive `kaleid` |
| Footwork | Wireframe lattice — sharp, geometric, monochrome |
| Techno | Slow `shape(6, 0.5, 0.5).repeat(2, 2).rotate(0, 0.02)` — minimal evolving |
| Algorave-glitch | `osc(40).modulate(noise(5)).pixelate(20, 20).invert()` — chunky pixel |
| Dub | `gradient().modulate(o0, 0.7).blend(noise(3), 0.3)` — smoky, slow-evolving |

## Agent invocation pattern

When invoked:

1. Find the install path of this skill (it's the parent of this file's parent dir)
2. Walk the user through one of the three open options (A/B/C above) based on what they're using
3. If they ask for a specific vibe, present the matching preset from the table
4. If they want audio-reactive sync, walk the BlackHole steps (it's a 5-min setup with one caveat: routing must include the speakers too, or audio goes silent)
