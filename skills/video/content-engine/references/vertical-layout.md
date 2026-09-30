# Vertical layout contract (9:16)

Every 9:16 asset content-engine produces (Reels, TikTok, Shorts, Stories) must be
checked against this contract before it is distributed. The numbers live in
`layout/vertical-9x16.json`. The Remotion overlays read them from there, and
`scripts/check_vertical_layout.py` enforces them. This page explains the numbers and
the checks. If this page and the JSON disagree, the JSON is right. Two tests guard
against drift. `test_doc_embeds_the_generated_zone_tables` keeps each zone table below
identical, row for row, to the checker's output. `test_skill_docs_quote_only_contract_pixels`
fails when a pixel value in the gate sections of the skill docs cannot be derived from
the JSON. It checks the value, not which zone the value belongs to.

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
pins the measured zone edges: the safe zone, the rail and the bottom band. Changing a
fraction in the JSON is a re-measurement, not a tweak.

## Zones

Output of `python3 scripts/check_vertical_layout.py zones` (profile `reels-organic`, the default):

| Zone (1080x1920) | x px | y px | x % | y % |
|---|---|---|---|---|
| Safe zone | 143-938 | 277-1643 | 13.2-86.8 | 14.4-85.6 |
| Avoid: right action rail | 872-1080 | 922-1920 | 80.7-100.0 | 48.0-100.0 |
| Avoid: bottom username/caption band | 0-1080 | 1686-1920 | 0.0-100.0 | 87.8-100.0 |
| Title hook band | 143-938 | 121-436 | 13.2-86.8 | 6.3-22.7 |
| Caption band | 220-860 | 1288-1463 | 20.4-79.6 | 67.1-76.2 |
| Eye-line band | 0-1080 | 634-864 | 0.0-100.0 | 33.0-45.0 |

The action rail lies partly inside the safe zone (x 872-938, y 922-1643). Anything
there passes VL2 and fails VL3, which is deliberate: the Reel marks that corner "avoid
at all costs". The caption band therefore does not use the full safe width. It is
x 220-860: symmetric about the centre, ending 12 px short of the rail so that a
caption touching the band's edge cannot touch the rail, and leaving 640 px for a
caption. `test_caption_band_clears_the_action_rail` checks this on rounded pixels.

### Paid placements: `meta-ads-9x16`

Meta's Ads Guide for Instagram Reels (fetched 2026-09-29) says to leave at least 14% of
the top, 35% of the bottom and 6% of each side free of text. That puts the organic
caption band (67-76%) inside Meta's bottom 35%. Check an ad with
`--profile meta-ads-9x16`. Under it, text has to stay between 14% and 65% of the
height; there are no title or caption bands and no eye line (Meta specifies neither).
The legibility rule carries over from the organic profile.

**The Remotion `ContentEngineReel` composition draws the organic layout, so it fails this
profile.** Its captions sit at 72%, below Meta's 65% line. There is no ads composition
yet. Until one exists, an ad needs its captions placed above 65% by hand, and it must
then pass this profile.

Output of `python3 scripts/check_vertical_layout.py --profile meta-ads-9x16 zones`:

| Zone (1080x1920) | x px | y px | x % | y % |
|---|---|---|---|---|
| Safe zone | 65-1015 | 269-1248 | 6.0-94.0 | 14.0-65.0 |

## Rules

| ID | Rule | Checked by | Fails when |
|---|---|---|---|
| VL1 | Canvas is 9:16, at least 1080 wide | ffprobe | Not 9:16 (±1%): FAIL, and every other rule is N/A. 9:16 but narrower than 1080: WARN. |
| VL2 | Overlay text stays inside the safe zone. Title-band text is exempt. | text boxes | Any overlay box leaves the zone. |
| VL3 | No overlay text and no face touches an avoid zone | text + face boxes | Any overlay text box overlapping the action rail or the bottom band FAILs, and so does a shot whose median face overlaps it or whose face overlaps it in more than 34% of samples. Small (scene-sized) text there WARNs, because a handle or a "link in bio" that small looks the same as text inside the footage. |
| VL4 | Top text (centre above 25% of height) sits in the title hook band | text boxes | A top box leaves the band. With `--expect-title`, finding no title also fails. |
| VL5 | Captions sit in the caption band, centred | text boxes | Text centred in the band's rows must fit inside the band, with the median centre within ±54 px. With `--expect-captions`, an empty band FAILs. That catches captions moved wholly out of the band (to the top, across the eyes) and captions OCR can read in none of the samples. It does not catch captions only partly out of the band, captions readable in only some samples, or captions elsewhere while other text sits in the band. |
| VL6 | Eyes sit in the eye-line band (33-45%) | face landmarks | For any shot, the median eye line is outside the band, or more than 34% of its samples are. |
| VL7 | The eye line holds across punch-ins | face landmarks | WARN, never FAIL, when the median eye line moves more than 3% of the height (58 px) across a face-scale change of 12% or more that persists. Face geometry cannot tell a punch-in from a cut between two framings (two centred speakers look like a punch-in), so the reader decides: a punch-in is scaled about the eye line; a cut is fine. |
| VL8 | The face stays inside the safe zone | face boxes | A shot's median face box leaves the zone, or its face does in more than 34% of samples. |
| VL9 | Text over a busy background has a stroke | declared (spec mode) / measured (video, image) | Declared: an element marked `"background": "busy"` without `"stroke": true` FAILs. Measured: WARN when under 60% of the ring 2-4 px around light glyphs reaches 3:1 contrast with the glyph fill. |

"Overlay text" means text boxes at least 1.5% of the height tall (29 px at 1920).
tesseract draws its box around the ink only, so a lowercase word set at 64 px with no
tall letters ("one", "see") gets a 36 px box. That is why the threshold is not 2%.
Smaller text is treated as part of the scene (book spines, signs, UI inside the
footage). VL2 counts it, and VL3 WARNs when it sits in an avoid zone.

**Which rule applies to a piece of text.** In spec mode the declared `role` decides. In
video and image mode, position decides:

- centre in the top 25% of the height: title (VL4)
- centre within the caption band's rows (y 1288-1463): caption (VL5)
- anything else: plain overlay (VL2 and VL3 only)

**Why roles are declared, not inferred.** OCR cannot tell a caption from a label, a CTA
or a title card. An earlier round of this gate inferred roles from behaviour: captions
replace each other, a title stays. It failed on legitimate layouts:
- rotating chapter titles read as captions and FAILed;
- one repeated word read as a title;
- a larger static label hid the captions under it;
- image mode has no time axis at all.

So the gate no longer guesses. A pipeline that burned captions in passes
`--expect-captions`, and the gate then requires text in the caption band.

**What that catches:**
- captions moved wholly somewhere else (at the top, across the eyes), with no other text
  in the band;
- captions OCR can read in none of the samples.

**What it does not catch:**
- A caption set that is only partly out of the band, for example some words across the
  eyes and some in the band. Measurement cannot tell a stray caption from a label.
- Captions moved elsewhere while other text (a CTA, a label) sits in the band: that text
  satisfies the expectation.
- Captions readable in only some samples. VL5 counts the readable ones, and VL9 can only
  measure the ones it read, so white unstroked captions over partly busy footage can
  PASS both.
- A caption outside the band when the flag is not passed. It is plain overlay text,
  held to VL2 and VL3 only.

Look at the guide sheet for all four. The report's `declared` field, and the `declared:`
line under the table header, record which flags were passed, so a verdict produced
without them is visible as such. `--expect-title` does the same for the title band.

## Running the gate

```bash
S=~/.claude/skills/content-engine/scripts   # or the skill dir in the repo

# A rendered or stitched video. Pass --expect-* for text you burned in.
python3 $S/check_vertical_layout.py video final.mp4 --expect-captions --expect-title

# 9:16 stills of one size (a Remotion `still`, a cover); a 1:1 carousel fails VL1
python3 $S/check_vertical_layout.py image cover.png

# The overlay geometry a pipeline intends to draw, before rendering anything
python3 $S/check_vertical_layout.py spec overlays.json

# Paint the zones on six frames and look at them
python3 $S/check_vertical_layout.py guide final.mp4 --out guide.png
```

`video` and `image` write `<input>.layout-report.json` and `<input>.layout-guide.png`
next to the input (`--report`, `--guide`, `--no-report` and `--no-guide` change that).
In the table output (the default), the last line is `VERDICT: PASS|FAIL (n PASS, n FAIL, ...)`,
so `tail -1` reads it; the `report:` and `guide:` paths print just above it. With
`--json`, read the `verdict` field instead.

For a raw generated clip, before any text is added, the rules that matter are VL1 and
VL6-VL8. VL2-VL5 and VL9 then describe text inside the footage (signage, a label), not
an overlay. A FAIL there means text in the footage sits where overlays would go: reframe
or regenerate the clip, or record why it does not matter next to the report (see the
FAIL policy under "Statuses").

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

`role` is `title`, `caption` or anything else (`watermark`, `cta`, `logo`), matched
case-insensitively. Roles other than title and caption are held to VL2 and VL3 only.
`background` is `busy` or `calm`, and `stroke` is `true` or `false`.

Any of the following exits 2 with the reason, and is never a verdict:
- an unknown key (a typo such as `"element"`)
- a malformed box or canvas
- a shot with `eye_y` but no `face_box`
- a spec that declares nothing

### Statuses

| Status | Meaning | Fails the run |
|---|---|---|
| PASS | Measured and inside the contract | no |
| FAIL | Measured and outside it | **yes** |
| WARN | Measured and borderline (legibility proxy, a sub-1080 canvas) | no |
| SKIP | The input has nothing this rule applies to (no text, no face, no punch-in) | no |
| N/A | The profile does not define the rule, or the canvas is not 9:16 | no |
| UNCHECKED | The detector cannot measure the rule here (tesseract has no face detector) | only with `--strict` |
| WAIVED | A FAIL the caller judged not to apply, via `--waive RULE="reason"`; the reason is in the report | no |

Exit code 0 means no FAIL, 1 means FAIL, 2 means a usage or tool error (no ffmpeg, no
detector, unreadable input, a report that cannot be written). An exit of 2 is not a
verdict.

**FAIL policy.** A FAIL is fixed and the gate re-run. When the rule does not apply to
the asset (text inside the footage, a b-roll face, a tesseract misread confirmed on the
guide sheet), re-run with `--waive RULE="reason"`: the FAIL shows as WAIVED, the run
passes, and the report keeps each waiver and its reason beside `input_sha256`. A waiver
for one render therefore does not carry over to the next one. A `--waive` that matches
no FAIL is noted in the output.

The report records `input_sha256` and `contract_sha256`. A report describes the bytes it
was run on: re-run after any re-render, and compare the sha before relying on a report
found beside a file.

Read SKIP and UNCHECKED as "not checked", never as "passed". Each UNCHECKED rule has to
be closed by looking at the guide sheet, and each SKIP has to be one you expected. For
example, a raw generated clip usually has no text, so VL2-VL5 SKIP; a b-roll has no
face, so VL6-VL8 SKIP. A verdict of PASS where nothing but VL1 was judged verifies only
the canvas.

## Detectors and their limits

| Detector | Where | Text | Faces |
|---|---|---|---|
| `vision` | macOS (`swiftc`); `vision_probe.swift`, compiled once into `~/.cache/content-engine/` | yes | yes (eye landmarks) |
| `tesseract` | anywhere tesseract is installed (CI) | yes, on calm backgrounds | no, so VL6-VL8 are UNCHECKED |

`--detector auto` (the default) prefers Vision. When Vision is unavailable, the report
says why in a `note:` line and in `detector_note`. That covers a `swiftc` build that
fails, which used to fall back to tesseract silently. Gate final assets with Vision.
Phone footage stored as 1920x1080 with a rotation flag is measured as the upright
1080x1920 the viewer sees.

Known limits, each measured while building this gate:

- **OCR cannot tell missing text from unreadable text.** White text on a busy background
  without a stroke was invisible to both detectors, so every text rule came back SKIP.
  That is exactly the case VL9 exists for. This is why `--expect-captions` and
  `--expect-title` exist: a pipeline that burned text in must pass them, and then "none
  found" is a FAIL.
- **tesseract reads texture as words and splits stroked words.** On busy footage it
  returned dozens of junk tokens. On the source Reel it read "nd" out of "background"
  and "St" out of "stroke". Single-glyph tokens under 85% confidence are dropped, and
  caption centring is judged on the median box. Confirm a tesseract FAIL on the guide
  sheet or with Vision before acting on it or waiving it (see the FAIL policy).
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
- **Small overlays are only WARNed.** A watermark or handle under 1.5% of the height is
  classed as scene text. content-engine's pre-contract 16 px watermark sat bottom-right,
  on the action rail. Video mode now WARNs on that (VL3) but cannot FAIL it, because
  small text on the rail may be part of the footage. Declare small overlays in a `spec`
  file to get a FAIL.
- **Punch-ins under 12% and cuts without a face are not seen.** VL7 needs a lasting
  face-scale change of 12% or more. A 1.1x punch-in SKIPs.
- **Fades read as low contrast.** VL9 measures whatever frame it samples, so a title
  card fading in or out WARNs (0.53-0.59 on content-engine's own reel render). Confirm a
  VL9 WARN on the guide sheet before restyling.
- **Position decides roles in a final render.** Text centred in the caption band's rows
  is judged as a caption, and text centred in the top 25% as a title. A lower-third
  name tag, a product label or a sign in the footage that sits in those rows is judged
  the same way, and may FAIL VL4 or VL5. Keep such text out of those rows, or waive the
  FAIL with `--waive` and that reason (see the FAIL policy).
- **The eye line needs a face.** Faceless content (product shots, b-roll) SKIPs VL6-VL8.
  Place key subjects inside the safe zone by eye, using the guide sheet.
- **Only the largest face is judged.** VL3, VL6 and VL8 follow the largest face in each
  sample. A second person (a guest, a duet) on the rail is not checked. The largest face
  is judged at any size, so a small face in b-roll or a full-body shot can FAIL VL6:
  `--waive VL6="..."` when the shot is not a talking head. A shot whose face has no eye
  landmarks is left out of VL6 and VL7, and the VL6 detail counts it.
- **Short overlays can fall between samples.** Video mode samples 2 frames per second
  (`--fps`), capped at 120 samples (`--max-frames`; a 3-minute video is sampled at 0.67
  fps). An overlay on screen for less than the sampling interval may never be seen. Raise
  `--fps` for short flashes. The guide sheet shows six frames; `guide --frames N` shows
  more.
- **meta-ads-9x16 has no avoid zones.** Small text anywhere passes VL3 under it, and with
  no bands, any overlay text satisfies `--expect-*`.

## Producing assets that pass

- **Framing (generation prompts):** subject centred, eyes about 38-40% from the top,
  head and shoulders inside the middle 74% of the width, with headroom. Put the
  constraint in the prompt, e.g. "vertical 9:16 medium close-up, subject centred, eyes
  about 40% from the top, clear space above the head and below the chest for text". (The
  upper-third line is at 33%, the edge of the band; aim a little lower.)
  Then run the gate on the raw clip: VL6-VL8 apply even before any text exists.
- **Punch-ins:** scale about the eye line, not the frame centre. ffmpeg keeps y = 39% fixed with
  `crop=iw/1.2:ih/1.2:(iw-ow)/2:ih*0.39-oh*0.39,scale=1080:1920`. In CSS or Remotion, use
  `transform: scale(1.2)` with `transform-origin: 50% 39%`.
- **Captions:** one word or a short chunk at a time, centred on y ≈ 1376 (71.7%), and at
  most 640 px wide (x 220-860), counting any pop-in scale. Use white bold at 64-80 px with a 4-6 px black stroke
  (`-webkit-text-stroke` plus `paint-order: stroke fill`; in ffmpeg `drawtext`,
  `borderw=6:bordercolor=black`). Shrink long words to fit rather than let them run
  onto the rail. The Remotion overlay does this with `fitFontSize`.
- **Title hook:** at most two lines, centred on y ≈ 278 (14.5%), within the safe width
  of 795 px.
- **Logos, watermarks, CTAs:** inside the safe zone, left of x = 872 anywhere below
  y = 922, and outside the title and caption bands' rows (text centred in those rows is
  judged as a title or a caption). The Remotion watermark sits at the safe zone's
  bottom-left, below the caption band, for this reason.
