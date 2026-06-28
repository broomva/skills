# Hard Rules — ffmpeg specifics

Production-correctness invariants inherited from `browser-use/video-use`, with the exact
ffmpeg mechanisms used in `render.py`. These are non-negotiable.

## 1. Per-segment extract → lossless concat (audio-drift-free)

Each EDL range is extracted **and processed once** (grade + 30 ms fades + canvas
normalization baked in), encoded to a uniform codec into an **`.mkv`** intermediate with
**lossless `pcm_s16le`** audio, then joined with the concat demuxer using `-c copy`:

```bash
# per segment i (encode pass 1 — the only place segment VIDEO is re-encoded):
ffmpeg -ss <s> -t <dur> -i <src> \
       -vf "<grade>,scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2,setsar=1" \
       -af "afade=t=in:st=0:d=0.03,afade=t=out:st=<dur-0.03>:d=0.03" \
       -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -fps_mode cfr -r 30 \
       -c:a pcm_s16le -ar 48000 -ac 2 clips_graded/seg_i.mkv

# concat (no encode — sample-exact, because PCM has no encoder priming):
ffmpeg -f concat -safe 0 -i concat.txt -c copy concatenated.mkv
```

**Why PCM, not AAC, for segments:** AAC's ~1024-sample encoder priming delay would be baked
into every segment and accumulate as ~21 ms of A/V drift **per cut seam** under `-c copy`.
PCM has no priming, so the concat is sample-exact; AAC is encoded **exactly once** in the
final pass. Uniform encode params + a common canvas across all segments are what make the
`-c copy` concat valid.

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

If there are no overlays and no subtitles (and not `--preview`), `final.mp4` is the concat
copied through with **video `-c:v copy`** (lossless) and the PCM track encoded to **AAC
once** (`-c:a aac`). Subtitles are **always** the last filter (Hard Rule 1).

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

## 7. Output isolation (with an explicit-output escape hatch)

By default every intermediate lives under `<videos_dir>/edit/`; `render.py` creates that
tree. The final output target:
- **no `-o`** → `edit/<basename of edl["output"]>`. Only the *filename* of `edl["output"]`
  is used — subdirectories in that field are not recreated.
- **`-o <path>`** → written **exactly** to that path, which may be anywhere on disk (e.g. an
  export outside `edit/`). The path printed on success is the real file location.

## Self-eval checks (`self_eval.py`)

At each cut boundary (the cumulative output offsets) ± a small window, plus head/tail/mid:
- extract a frame → flag near-black/near-duplicate frames (visual discontinuity/flash)
- sample the audio envelope → flag samples above a pop threshold past the 30 ms fade
- (if subtitles burned) confirm the subtitle region isn't fully occluded by an overlay
Report JSON: `{boundary_s, checks:{...}, ok:bool}`. **Cap at 3 correction passes**; if issues
persist, flag rather than loop.
