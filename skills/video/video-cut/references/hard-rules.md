# Hard Rules — ffmpeg specifics

Production-correctness invariants inherited from `browser-use/video-use`, with the exact
ffmpeg mechanisms used in `render.py`. These are non-negotiable.

## 1. Per-segment extract → lossless concat (no double-encode)

Each EDL range is extracted **and processed once** (grade + fades baked in), encoded to a
uniform codec, then joined with the concat demuxer using `-c copy` (no re-encode):

```
# per segment i (encode pass 1, only place segments are re-encoded):
ffmpeg -ss <s> -to <e> -i <src> -vf "<grade>" -af "afade=t=in:st=0:d=0.03,afade=t=out:st=<dur-0.03>:d=0.03" \
       -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -c:a aac -ar 48000 clips_graded/seg_i.mp4

# concat (no encode):
ffmpeg -f concat -safe 0 -i concat.txt -c copy concatenated.mp4
```

Uniform encode params across segments are what make `-c copy` concat valid.

## 2. Audio fades — 30 ms at every cut

`afade=t=in:st=0:d=0.03` + `afade=t=out:st=<dur-0.03>:d=0.03` per segment. `<dur>` is the
padded range duration. Prevents clicks/pops at boundaries.

## 3. Overlays — PTS-shifted, then subtitles LAST, in ONE final pass

After the lossless concat, a single final ffmpeg pass (encode pass 2) applies overlays then
subtitles, so the chain is encoded only once more:

```
# overlay frame 0 shifted to its output start; subtitles filter applied AFTER overlay:
-filter_complex "[1:v]setpts=PTS-STARTPTS+<start_in_output>/TB[ov];[0:v][ov]overlay=...[v1];[v1]subtitles=master.srt[vout]"
```

If there are no overlays and no subtitles, `final.mp4` is the concat output renamed (zero
second encode). Subtitles are **always** the last filter (Hard Rule 1).

## 4. Snap cuts to word boundaries + padding

EDL `start`/`end` should land on transcript word boundaries. `render.py` applies symmetric
`pad_ms` (default 60, range 30–200) and clamps to `[0, source_duration]`. Padding absorbs
ASR drift; it never extends past the source.

## 5. Grade presets (ffmpeg `-vf`)

| preset | filter |
|---|---|
| `warm_cinematic` | `eq=contrast=1.06:brightness=0.02:saturation=1.12,colorbalance=rm=0.06:gm=0.0:bm=-0.04` |
| `neutral_punch` | `eq=contrast=1.08:saturation=1.05` |
| `none` | (no `-vf`) |
| custom | `{"filter": "<raw vf>"}` in the EDL |

Mental model: grade is baked per-segment during extract (pass 1), never as a separate pass.

## 6. Preview mode

`--preview` scales to 720p height (`scale=-2:720`), `-preset ultrafast -crf 28`, and writes
`edit/preview.mp4`. Use for the fast iterate loop; full quality only on final.

## 7. Output isolation

Every artifact lives under `<videos_dir>/edit/`. `render.py` creates the tree and never
writes outside it. The EDL's `output` path is interpreted relative to the videos dir.

## Self-eval checks (`self_eval.py`)

At each cut boundary (the cumulative output offsets) ± a small window, plus head/tail/mid:
- extract a frame → flag near-black/near-duplicate frames (visual discontinuity/flash)
- sample the audio envelope → flag samples above a pop threshold past the 30 ms fade
- (if subtitles burned) confirm the subtitle region isn't fully occluded by an overlay
Report JSON: `{boundary_s, checks:{...}, ok:bool}`. **Cap at 3 correction passes**; if issues
persist, flag rather than loop.
