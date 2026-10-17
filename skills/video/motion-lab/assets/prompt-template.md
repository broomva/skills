# Directed motion prompt — fill every line before you send it

Each line removes one decision the model would otherwise make for you. The model's
own decisions are the generic look. Write GOAL first, then TIME: every other number
hangs off the frame count.

```text
GOAL:    what the viewer should feel or do, in one sentence
OUTPUT:  one self-contained HTML file (or: a Remotion composition / a HyperFrames
         project), W x H, engine and pinned version (three@0.160.0)
TIME:    seconds x fps = total frames. Loop: yes or no. BPM if there is music.
LOOK:    palette in hex, one accent, typeface + weight + size + tracking
MODEL:   (3D only) dimensions in units, materials with roughness/metalness/clearcoat
CAMERA:  (3D only) field of view, path in degrees and distances, easing per move
MOTION:  easing as cubic-bezier, springs as damping ratio, durations in frames
SHOTS:   frame ranges; one hero move per shot; how each shot hands off
         (a hard cut on the beat by default; a match cut or a mask wipe only on purpose)
BANNED:  the defaults you never want to see, by name
QA:      stills at named frames, a contact sheet, fix, then the full render
```

Then paste the render contract from SKILL.md under it.

## A filled example (2D title card)

```text
GOAL:    the word "Launch" lands with weight, then holds still to be read.
OUTPUT:  one self-contained HTML file, plain CSS + Canvas, 1080x1080.
TIME:    4 s loop at 24 fps = 96 frames. 120 BPM: 1 beat = 12 frames.
LOOK:    #FFFFFF background, #0F0F0F ink, accent #D97757 only on the underline.
         Geist 800, 120 px, tracking -0.04em.
MOTION:  letters enter on cubic-bezier(0.16, 1, 0.3, 1), 14 frames each, 2 frames apart.
         Underline springs in at damping ratio 0.8. Exits on cubic-bezier(0.7, 0, 0.84, 0),
         40% shorter than entrances.
SHOTS:   0-33 letters rise. 34-75 hold still while it reads, 2% slow push.
         76-89 exit. 90-95 empty frame that flows into frame 0.
BANNED:  gradients, glow, particles, fade-and-slide-up, everything at once, centered sub-copy.
QA:      stills at 0, 24, 48, 72; a contact sheet of every 8th frame; frame 95 flows into 0.
```
