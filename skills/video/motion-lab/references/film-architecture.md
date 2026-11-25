# Architecture for a code-first film

Keep timing and creative direction in `spec.json`. Author the picture as
`template.html` with local modules, fonts, artwork and shaders in the same
directory. The renderer produces PNGs and a silent MP4. Video QA inspects the
decoded picture before the sound pass.

## 1. Specify the film

Use integer frame ranges with an exclusive end. A spec can use this structure
for a six-second film at 24 fps.

```json
{
  "canvas": { "width": 1920, "height": 1080, "fps": 24, "frames": 144 },
  "shots": [
    { "startFrame": 0, "endFrame": 72, "action": "Reveal the title over 12 frames" },
    { "startFrame": 72, "endFrame": 144, "action": "Hold the product, then fade the caption" }
  ],
  "heroFrames": [0, 12, 72, 143],
  "contrastBeats": [12, 72],
  "soundCues": [{ "frame": 12, "cue": "title arrival" }]
}
```

Give every shot one main action and specify the reading hold, easing, palette
and caption placement. Use `liquid-midnight` for materials, foreground and
background contrast and type direction when that look fits. Put the values
the composition uses into the spec so it can be reviewed or rerendered later.

## 2. Draw the picture

Translate the spec into scene data for `template.html`. Bundle the data into a
local JavaScript module or embed it as inert JSON, then expose
`window.renderAt(t)` from the composition. The renderer supplies seconds and
captures frame `i` at `i / fps`. Every frame must be callable directly on a
fresh page. Position animations, update uniforms and set the picture from
`t`. Gate the live preview behind the absence of `?t=`.

Use all four sides in `clip-path: inset()`. For an SVG path normalized with
`pathLength="1"`, set `stroke-dashoffset` as an SVG attribute. Give each
animated transform a single driver. Lint the template and any JavaScript modules
you authored.

```bash
python3 scripts/motion_lint.py film/template.html film/scene.mjs
node scripts/render.mjs film/template.html --seconds 6 --fps 24 --width 1920 --height 1080 \
  --serve --workers 2 --webgl --verify --mp4 --out out
```

`--serve` serves local assets from the real directory of `template.html` over
ephemeral loopback HTTP. Keep that directory limited to render inputs.
`--workers` assigns disjoint frame indices to independent pages in one browser.
Choose a worker count the machine can support at the requested resolution.
`--webgl` requests Chromium's ANGLE and WebGL flags. Verify on the rendering
machine. `--verify` compares the first, middle and last PNG with a fresh page.
Use `--verify-all` for a reverse-order check of every PNG.

## 3. Review the decoded picture

```bash
python3 scripts/video_qa.py scan out/anim.mp4 --out out/scan
python3 scripts/video_qa.py hero out/anim.mp4 --frames 0,12,72,143 --out out/hero.jpg
python3 scripts/video_qa.py grade out/anim.mp4 --beats 12,72 --json > out/grade.json
```

`scan` includes every decoded video frame with its zero-based index and
presentation timestamp relative to the first frame. The default grid fits up to
216 tiles per page. A frames directory can also be scanned using the
renderer manifest's FPS, `--fps`, or 24 FPS when neither is present.
`hero` keeps the requested order and uses larger tiles for checking composition
and legibility at shot beats. The sheets preserve the entire picture with
letterboxing as needed.

`grade` checks `yuv420p`, positive average FPS and consistent, positive, even
dimensions. It always measures first and last frame luma. It grades the first,
midpoint and last frames by default, or the supplied zero-based beat indices.
Lightness, the two Lab color axes and per-pixel chroma are averaged over the
decoded frame. It also reports the population standard deviation and the
nearest-rank fifth percentile of lightness. The conversion interprets decoded
RGB as SDR sRGB with a D65 reference white. See the color model in
[CSS Color 4](https://www.w3.org/TR/css-color-4/#color-conversion-code).

A beat fails by default when its fifth percentile exceeds 38 or its lightness
deviation falls below 1. Choose beat indices and thresholds to match the film's
palette. For example, a deliberately bright title card may need a higher
`--max-dark-p5`. Read the hero frames and log any threshold change alongside
the grade. Exit 0 passes, 1 indicates failed gates, and 2 indicates invalid
input or unavailable tooling.

## 4. Finish with soundcraft

Give `soundcraft` the locked picture, FPS, cue frames and audio stems. Convert
frame cues with `frame / fps` before placing audio, then mux the final mix
against the locked picture and run the audio delivery checks on the muxed
file. Keep the spec, render manifest, selected QA sheets and grade JSON with
the delivery so another reviewer can reproduce the frame references.
