# The motion numbers

Motion designers talk in curves and frames, so give the model curves and frames.
Compute instead of estimating: `scripts/motion_math.py` covers the arithmetic below.

## Easing

| Name | cubic-bezier | Use it for |
|---|---|---|
| ease-out-expo | 0.16, 1, 0.3, 1 | text and logo reveals |
| ease-out-quint | 0.22, 1, 0.36, 1 | premium entrances |
| ease-in-out-quart | 0.76, 0, 0.24, 1 | moves and camera pushes |
| ease-in-expo | 0.7, 0, 0.84, 0 | fast exits |
| ease-out-back | 0.34, 1.56, 0.64, 1 | a playful pop with overshoot |

Enter with ease-out, exit with ease-in and make exits 40–50% shorter, move across
the screen with ease-in-out. Linear only for rotation, progress bars and the phase
of a loop. Camera moves get the softest curves; objects get the snappier ones.

## Springs

One number translates between libraries: the damping ratio
zeta = damping / (2 sqrt(stiffness x mass)).

| zeta | Feel |
|---|---|
| 1.0 | never bounces (UI, text) |
| 0.7–0.85 | premium product motion |
| 0.4–0.6 | playful, characters |
| under 0.3 | cartoon |

Position and size may bounce; opacity and colour never do.
`motion_math.py damping --stiffness K --damping C [--mass M]` gives zeta;
`--zeta Z` gives the damping for a target ratio.

## Durations and stagger

| Thing | Duration |
|---|---|
| UI feedback | 100–200 ms (100 ms feels instant) |
| UI moves | 200–500 ms |
| hero reveal | 600–900 ms |
| letters | 1 frame apart |
| words | 60–120 ms apart |
| list items | 40–80 ms apart |

Start the next element when the previous one is 30–50% done: fully sequential looks
robotic, all at once looks cheap. For video, say it in frames: at 24 fps one frame is
about 42 ms, so 400 ms is 10 frames (`motion_math.py ms --ms 400 --fps 24`).

## Beat grid

Frames per beat = fps x 60 / BPM. At 120 BPM and 24 fps that is 12 frames. At 128 BPM
and 30 fps it is 14.0625, so compute every beat from time and round each one: adding
a rounded 14 again and again is 2 frames off after 32 beats
(`motion_math.py beats --fps 30 --bpm 128 --count 32`). Cut on the beat; change the
layout on the bar (every 4 beats).

A music loop only closes when the loop holds a whole number of beats
(`motion_math.py frames --seconds 6 --fps 60 --bpm 120`).

## Holds and loops

- On-screen text holds at least 0.3 s per word + 0.5 s (`motion_math.py hold --words N`).
  During a hold, a slow 2% push keeps the frame alive.
- Render frames 0 to N-1, never N: frame N is frame 0 again.
- Drive every loop from phase = frame / N with whole-number cycles. For organic drift,
  sample noise along a circle so it returns to its start.
- Make frame 0 a finished composition: it is on screen while a GIF loads.

## Camera, parallax, legibility

- Field of view 30–50 degrees to start. Parallax speeds 1.0 / 0.5 / 0.2 (fore / mid / back).
- Exaggerate key poses 10–30% past what feels right: the feed shrinks everything.
- Text keeps 4.5:1 contrast on every frame; never flash more than 3 times per second (WCAG).

## Sound

Mix music and effects, normalise to −14 LUFS with peaks at −1 dBTP, and put each sound
1 frame after its picture, never before (light beats sound). AAC encoding can lift the
true peak: limit the master lower (about −2 dBTP) and re-measure the decoded MP4.

```bash
ffmpeg -i out/anim.mp4 -i music.wav -i sfx.wav -filter_complex \
  "[1:a][2:a]amix=inputs=2:duration=first,loudnorm=I=-14:TP=-1:LRA=11[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart out/final.mp4
```

## Export for X

| Spec | GIF | Video |
|---|---|---|
| size | 15 MB | 140 s without Premium |
| frame size | up to 1280 x 1080 | 1920 x 1080 for 16:9 |
| frames | at most 350 (14.5 s at 24 fps) | up to 60 fps |
| format | one palette, loop forever | H.264 High, yuv420p, AAC |

```bash
# MP4 for a post
ffmpeg -framerate 24 -i out/frames/%04d.png -c:v libx264 -profile:v high -pix_fmt yuv420p \
  -crf 18 -movflags +faststart out/anim.mp4

# GIF: one palette for the whole clip, 1200 px wide
ffmpeg -framerate 24 -i out/frames/%04d.png -vf "scale=1200:-1:flags=lanczos,split[a][b];\
[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  -loop 0 out/anim.gif

# measure the GIF's real timing (a per-frame rounding encoder runs 4% fast at 24 fps)
python3 scripts/motion_math.py gif-check out/anim.gif --fps 24

# watch the seam: three loops back to back
ffmpeg -stream_loop 2 -i out/anim.mp4 -c copy out/loop_check.mp4
```

Source: numbers as published in Florence (@flxrnc), "Opus 5.5 Motion Lab" (2026-09-30),
which cites easings.net, Material 3, Nielsen Norman Group, WCAG and X's media docs. The
X limits were not re-checked at source; the beat, spring and GIF arithmetic is computed
and tested in `scripts/motion_math.py`.
