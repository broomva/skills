# Vertical layout contract (9:16)

Every 9:16 asset content-engine produces (Reels, TikTok, Shorts, Stories) is checked
against this contract before it is distributed. The numbers live in
`layout/vertical-9x16.json`. The Remotion overlays read them from there, and
`scripts/check_vertical_layout.py` enforces them. This page explains the numbers and
the checks. If this page and the JSON ever disagree, the JSON is right, and
`tests/test_check_vertical_layout.py` fails until this page is fixed.

## Source

The `reels-organic` profile was measured from Jun Yuh's Reel
[`Ddz3gW_x_tZ`](https://www.instagram.com/reel/Ddz3gW_x_tZ/) (@jun_yuh, uploaded
2026-09-28, 14.1 s, 1080x1920). The Reel draws its own layout guides over a talking
head, one guide per spoken line. Transcript by whisper.cpp; timings are from its SRT:

| t (s) | Said | Drawn | Rule |
|---|---|---|---|
| 0.0-2.2 | "This is where your eyes go, this is where your caption goes," | yellow pill over the eyes; yellow pill in the lower middle | VL6, VL5 |
| 2.2-3.6 | "and that's where you tie the hook." | yellow "Title hook" pill at the top | VL4 |
| 3.6-5.8 | "This is your safe zone, this is your danger zone," | green box; red everywhere outside it | VL2 |
| 5.8-8.1 | "and this is where you should avoid at all costs." | red block on the right from mid-height down, red band along the bottom | VL3 |
| 8.1-10.2 | "You're going to punch in for the eye line the same," | tighter crop, white dashed line across the eyes | VL7 |
| 10.2-12.6 | "and if you have a busy background, add a stroke to your text." | the caption gains a black outline | VL9 |

How it was measured (2026-09-29): frames were sampled at 2 fps. The zone edges come
from pixel differences between each guide's colour and a frame without guides, so they
are the Reel's own drawn geometry. Eye, caption and title positions come from macOS
Vision on every sample (see `scripts/vision_probe.swift`):

- **Eyes:** y 701-747 px in the wide shot (median 728) and 756-801 px after the punch-in
  (median 770). The punch-in moves the eye line 42-43 px, not 0.
- **Captions:** one word at a time, text boxes between y 1318 and 1426, centred.
- **Title hook text:** y 233-323. It straddles the safe zone's top edge (277), which is
  why title-band text is exempt from VL2.

`tests/test_check_vertical_layout.py::test_contract_reproduces_the_measured_reel_pixels`
pins these pixels. Changing a fraction in the JSON is a re-measurement, not a tweak.

## Zones

Output of `python3 scripts/check_vertical_layout.py zones` (profile `reels-organic`, the default):

| Zone (1080x1920) | x px | y px | x % | y % |
|---|---|---|---|---|
| Safe zone | 143-938 | 277-1643 | 13.2-86.8 | 14.4-85.6 |
| Avoid: right action rail | 872-1080 | 922-1920 | 80.7-100.0 | 48.0-100.0 |
| Avoid: bottom username/caption band | 0-1080 | 1686-1920 | 0.0-100.0 | 87.8-100.0 |
| Title hook band | 143-938 | 121-436 | 13.2-86.8 | 6.3-22.7 |
| Caption band | 143-938 | 1288-1463 | 13.2-86.8 | 67.1-76.2 |
| Eye-line band | 0-1080 | 634-864 | 0.0-100.0 | 33.0-45.0 |

The action rail lies partly inside the safe zone (x 872-938, y 922-1643). Anything
there passes VL2 and fails VL3, which is deliberate: the Reel marks that corner "avoid
at all costs".

### Paid placements: `meta-ads-9x16`

Meta's Ads Guide for Instagram Reels (fetched 2026-09-29) says to leave at least 14% of
the top, 35% of the bottom and 6% of each side free of text. That puts the organic
caption band (67-76%) inside Meta's bottom 35%. For an ad, use
`--profile meta-ads-9x16`: captions then have to sit above 65%, and there are no title
or caption bands. The eye line and legibility rules carry over from the organic profile;
Meta does not specify them.

Output of `python3 scripts/check_vertical_layout.py --profile meta-ads-9x16 zones`:

| Zone (1080x1920) | x px | y px | x % | y % |
|---|---|---|---|---|
| Safe zone | 65-1015 | 269-1248 | 6.0-94.0 | 14.0-65.0 |
| Eye-line band | 0-1080 | 634-864 | 0.0-100.0 | 33.0-45.0 |

## Rules

| ID | Rule | Checked by | Fails when |
|---|---|---|---|
| VL1 | Canvas is 9:16, at least 1080 wide | ffprobe | Not 9:16 (±1%): FAIL, and every other rule is N/A. 9:16 but narrower than 1080: WARN. |
| VL2 | Overlay text stays inside the safe zone. Title-band text is exempt. | text boxes | Any overlay box leaves the zone. |
| VL3 | No overlay text and no face touches an avoid zone | text + face boxes | Any overlap with the action rail or the bottom band. |
| VL4 | Top text (centre above 25% of height) sits in the title hook band | text boxes | A top box leaves the band. With `--expect-title`, finding no title also fails. |
| VL5 | Captions (centre below 60% of height) sit in the caption band, centred | text boxes | A box leaves the band, or the median caption centre is more than ±54 px off. Word-by-word text parked at the top counts as captions and fails here. With `--expect-captions`, finding no captions also fails. |
| VL6 | Eyes sit in the eye-line band (33-45%) | face landmarks | A shot's median eye line is outside the band. |
| VL7 | The eye line holds across punch-ins | face landmarks | Consecutive shots' median eye lines differ by more than 3% of height (58 px). A new shot is a face-scale change of 12% or more that persists. |
| VL8 | The face stays inside the safe zone | face boxes | A shot's median face box leaves the zone. |
| VL9 | Text over a busy background has a stroke | declared (spec mode) / measured (video, image) | Declared: an element marked `"background": "busy"` without `"stroke": true` FAILs. Measured: WARN when under 60% of the ring 2-4 px around light glyphs reaches 3:1 contrast with the glyph fill. |

"Overlay text" means text boxes at least 2% of the height tall (38 px at 1920). Smaller
text is treated as part of the scene (book spines, signs, UI inside the footage), and
the report counts it. It is never silently dropped.

## Running the gate

```bash
S=~/.claude/skills/content-engine/scripts   # or the skill dir in the repo

# A rendered or stitched video. Pass --expect-* for text you burned in.
python3 $S/check_vertical_layout.py video final.mp4 --expect-captions --expect-title

# Stills (a Remotion `still`, a thumbnail, carousel frames of one size)
python3 $S/check_vertical_layout.py image cover.png

# The overlay geometry a pipeline intends to draw, before rendering anything
python3 $S/check_vertical_layout.py spec overlays.json

# Paint the zones on six frames and look at them
python3 $S/check_vertical_layout.py guide final.mp4 --out guide.png
```

`video` and `image` write `<input>.layout-report.json` and `<input>.layout-guide.png`
next to the input (`--report`, `--guide`, `--no-report` and `--no-guide` change that).
The last output line is `VERDICT: PASS|FAIL (n PASS, n FAIL, ...)`.

A spec file lists boxes in pixels:

```json
{
  "canvas": [1080, 1920],
  "elements": [
    {"role": "title", "label": "hook", "box": [312, 233, 765, 323]},
    {"role": "caption", "label": "word", "box": [440, 1345, 640, 1405], "stroke": true, "background": "busy"},
    {"role": "watermark", "label": "brand", "box": [143, 1580, 330, 1640]}
  ],
  "shots": [{"eye_y": 730, "face_box": [334, 616, 690, 972]}]
}
```

`role` is `title`, `caption` or anything else (`watermark`, `cta`, `logo`). Roles other
than title and caption are held to VL2 and VL3 only.

### Statuses

| Status | Meaning | Fails the run |
|---|---|---|
| PASS | Measured and inside the contract | no |
| FAIL | Measured and outside it | **yes** |
| WARN | Measured and borderline (legibility proxy, a sub-1080 canvas) | no |
| SKIP | The input has nothing this rule applies to (no text, no face, no punch-in) | no |
| N/A | The profile does not define the rule, or the canvas is not 9:16 | no |
| UNCHECKED | The detector cannot measure the rule here (tesseract has no face detector) | only with `--strict` |

Exit code 0 means no FAIL, 1 means FAIL, 2 means a usage or tool error (no ffmpeg, no
detector, unreadable input). An exit of 2 is not a verdict.

Read SKIP and UNCHECKED as "not checked", never as "passed". Each UNCHECKED rule has to
be closed by looking at the guide sheet, and each SKIP has to be one you expected. For
example, a raw generated clip has no text, so VL2-VL5 SKIP.

## Detectors and their limits

| Detector | Where | Text | Faces |
|---|---|---|---|
| `vision` | macOS (`swiftc`); `vision_probe.swift`, compiled once into `~/.cache/content-engine/` | yes | yes (eye landmarks) |
| `tesseract` | anywhere tesseract is installed (CI) | yes, on calm backgrounds | no, so VL6-VL8 are UNCHECKED |

`--detector auto` (the default) prefers Vision. Gate final assets with Vision.

Known limits, each measured while building this gate:

- **OCR cannot tell missing text from unreadable text.** White text on a busy background
  without a stroke was invisible to both detectors, so every text rule came back SKIP.
  That is exactly the case VL9 exists for. This is why `--expect-captions` and
  `--expect-title` exist: a pipeline that burned text in must pass them, and then "none
  found" is a FAIL.
- **tesseract reads texture as words and splits stroked words.** On busy footage it
  returned dozens of junk tokens. On the source Reel it read "nd" out of "background"
  and "St" out of "stroke". Single-glyph tokens under 85% confidence are dropped, and
  caption centring is judged on the median box. Treat any tesseract FAIL as a lead, and
  confirm it on the guide sheet or with Vision.
- **VL9 is a proxy.** Calibration on 1080x1920 fixtures, white bold 96 px text over
  pixel noise, Vision:

  | Background noise | No stroke | 6 px stroke |
  |---|---|---|
  | 90-200 | 0.54 (WARN) | 1.00 (PASS) |
  | 120-220 | 0.26 (WARN) | 0.62 (PASS) |
  | 140-230 | 0.07 (WARN) | 0.48 (WARN) |

  On the source Reel it WARNs on its own white-on-yellow "Title hook" pill (0.00) and on
  "danger" drawn over its red guide (0.48). Both are teaching overlays, and both are
  genuinely low contrast.
- **Small overlays are invisible to video mode.** A watermark or handle under 2% of the
  height is classed as scene text. content-engine's pre-contract 16 px watermark sat
  bottom-right, on the action rail, and video mode never saw it. Check small overlays
  with `spec` (declare their boxes) or on the guide sheet.
- **Fades read as low contrast.** VL9 measures whatever frame it samples, so a title
  card fading in or out WARNs (0.53-0.59 on content-engine's own reel render). Confirm a
  VL9 WARN on the guide sheet before restyling.
- **The eye line needs a face.** Faceless content (product shots, b-roll) SKIPs VL6-VL8.
  Place key subjects inside the safe zone by eye, using the guide sheet.

## Producing assets that pass

- **Framing (generation prompts):** subject centred, eyes about 38-40% from the top,
  head and shoulders inside the middle 74% of the width, with headroom. Put the
  constraint in the prompt, e.g. "vertical 9:16 medium close-up, subject centred, eyes
  on the upper-third line, clear space above the head and below the chest for text".
  Then run the gate on the raw clip: VL6-VL8 apply even before any text exists.
- **Punch-ins:** scale about the eye line, not the frame centre. ffmpeg keeps y = 39% fixed with
  `crop=iw/1.2:ih/1.2:(iw-ow)/2:ih*0.39-oh*0.39,scale=1080:1920`. In CSS or Remotion, use
  `transform: scale(1.2)` with `transform-origin: 50% 39%`.
- **Captions:** one word or a short chunk at a time, centred on y ≈ 1376 (71.7%). Use
  white bold at 64-80 px with a 4-6 px black stroke (`-webkit-text-stroke` plus
  `paint-order: stroke fill`; in ffmpeg `drawtext`, `borderw=6:bordercolor=black`).
- **Title hook:** at most two lines, centred on y ≈ 278 (14.5%), within the safe width
  of 795 px.
- **Logos, watermarks, CTAs:** inside the safe zone, left of x = 872 anywhere below
  y = 922. The Remotion watermark sits at the safe zone's bottom-left for this reason.
