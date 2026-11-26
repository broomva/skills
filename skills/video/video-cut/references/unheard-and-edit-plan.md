# UNHEARD Detection & Typed `editPlan.json` (v1)

Two clean-room production reliability primitives in `video-cut` that close the two most
common failure modes of autonomous video editing:

1. **Dropped retakes / missed ASR speech (`scripts/unheard.py`)** — Whisper/VAD models
   regularly drop quiet false starts, rapid retakes, or off-mic interjections. Reading
   only the transcript hides them until a human listens to the render.
2. **Ad-hoc FFmpeg command drift (`scripts/edit_plan.py`)** — letting an LLM hand-write
   raw FFmpeg filtergraphs mixes editorial choices with syntax bugs (unsafe caption
   placement, out-of-bounds punch-in crops, and FFmpeg `sidechaincompress` early music
   truncation).

Both scripts use **pure Python stdlib + `ffmpeg`/`ffprobe`** (zero extra pip packages).

---

## 1. `scripts/unheard.py` — Word-Aligned `UNHEARD` Detector

### How it works

1. **PCM Decode**: Reads uncompressed 16-bit PCM `.wav` directly via Python `wave`;
   decodes any other audio/video container to 16 kHz mono 16-bit PCM via `ffmpeg`.
2. **20 ms RMS Envelope**: Computes per-frame loudness in dBFS (`20 * log10(rms / 32768)`).
3. **Adaptive Speech Floor**: Estimates `noise_floor_db` at the 10th percentile of frame
   levels and activates speech above `max(noise_floor_db + 12.0, -42.0)` (or an explicit
   `--speech-db`). Merges intra-word pauses `<= 0.15s` (`--merge-pause-s`).
4. **Word-Span Subtraction**: Loads transcript JSON in any supported layout:
   - `transcribe_local.py` output (`words: [{start, end, word}]`, `segments: [...]`)
   - Segment-only or nested-word JSON (`segments: [{start, end, text, words?: [...]}]`)
   - Multi-clip `clips` dict or list (`clips: {<name>: {words, segments}}`, auto-matched
     by media filename stem or explicit `--clip`)
   Pads every word span by `--margin-s` (default `0.12s`) and subtracts it from active
   speech.
5. **UNHEARD Flagging**: Any uncovered active-speech stretch `>= --min-gap-s` (default
   `0.6s`) is emitted as an `UNHEARD` region:

```json
{
  "start": 12.4,
  "end": 14.15,
  "duration": 1.75,
  "peak_db": -14.1,
  "mean_db": -18.2,
  "context_before": "and that's why we built",
  "context_after": "so let's look at the demo",
  "suggested_action": "inspect_possible_retake_or_dropped_speech"
}
```

Short breaths (`< 0.6s`, e.g. `0.25s`) and covered words (within `±0.12s` ASR timing
jitter) are ignored.

### CLI

```bash
# Detect UNHEARD regions as JSON and write an inline-annotated transcript
python3 scripts/unheard.py detect clip.mp4 \
  --transcript edit/transcripts/clip.json \
  --min-gap-s 0.6 --margin-s 0.12 --json \
  --annotate-out edit/takes_annotated.txt

# Annotate directly (or reuse a saved detect --json file via --unheard)
python3 scripts/unheard.py annotate clip.mp4 \
  --transcript edit/transcripts/clip.json \
  -o edit/takes_annotated.txt
```

Annotated output interleaves `[UNHEARD ...]` markers chronologically between spoken lines:

```text
[000.50s-001.50s] First take
[UNHEARD 3.20s-4.20s (1.00s, -21.0 dBFS)]
[004.80s-005.50s] Final line
```

Inspect flagged regions with `timeline_view.py <video> <start> <end>` before locking cuts.

---

## 2. `scripts/edit_plan.py` — Typed `editPlan.json` v1 Validator & FFmpeg Compiler

Separates **editorial intent** (`editPlan.json`) from **deterministic FFmpeg execution**.
The agent authors and validates `editPlan.json`; `edit_plan.py` compiles an exact,
reproducible `ffmpeg` `filter_complex` command.

### Schema (`version: 1`)

```json
{
  "version": 1,
  "canvas": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "safe_area": "9:16-reels"
  },
  "clips": [
    {
      "id": "hook",
      "source": "/abs/path/clip1.mp4",
      "in_s": 0.4,
      "out_s": 2.0,
      "punch_in": {"scale": 1.35, "anchor_x": 0.5, "anchor_y": 0.35},
      "grade": {"brightness": 0.02, "contrast": 1.06, "saturation": 1.1},
      "gain_db": 0.0
    }
  ],
  "audio": {
    "music": {
      "source": "/abs/path/music.wav",
      "gain_db": -16.0,
      "duck_db": -10.0,
      "pad_tail_s": 0.75
    },
    "target_lufs": -14.0
  },
  "captions": {
    "enabled": true,
    "safe_zone_check": true,
    "entries": [
      {"start_s": 0.1, "end_s": 1.4, "text": "Hook line one", "y_frac": 0.72}
    ]
  }
}
```

### Safe-Area Presets

| Preset | `top` | `bottom` | `left` | `right` | Safe `y_frac` range |
|---|---:|---:|---:|---:|---|
| `9:16-reels` | `0.14` | `0.22` | `0.06` | `0.14` | `[0.14, 0.78]` |
| `16:9-youtube` | `0.06` | `0.12` | `0.05` | `0.05` | `[0.06, 0.88]` |
| `1:1-square` | `0.08` | `0.12` | `0.06` | `0.06` | `[0.08, 0.88]` |
| Custom `{top, bottom, left, right}` | `[0, 0.5)` | `[0, 0.5)` | `[0, 0.5)` | `[0, 0.5)` | `[top, 1 - bottom]` |

### Validation Gates (`validate_plan(plan, check_files=False)`)

Returns `{"valid": bool, "errors": [...], "warnings": [...]}` and rejects:

- Missing/unsupported `version` (must be integer `1`).
- Odd or non-positive canvas `width`/`height` (`yuv420p` requires even dimensions) or invalid `fps`.
- Empty `clips`, duplicate clip `id`s, negative `in_s`, or inverted/zero-length `in_s >= out_s`.
- Out-of-range `punch_in`: `scale` outside `[1.0, 2.0]` or `anchor_x`/`anchor_y` outside `[0.0, 1.0]`.
- Captions placed inside unsafe top/bottom/left/right margins when `captions.enabled` and
  `safe_zone_check` (default `true`) are active.
- Sidechain ducking (`audio.music.duck_db != 0`) with missing `pad_tail_s` or `pad_tail_s < 0.5`
  — prevents FFmpeg's `sidechaincompress` filter from prematurely truncating the music bed
  when the voice sidechain terminates.

### Deterministic Compilation Guarantees

- Exact per-clip `trim`/`atrim` + `setpts=PTS-STARTPTS`/`asetpts=PTS-STARTPTS`.
- Punch-in `crop` centered on `(anchor_x, anchor_y)` with `max(0, min(iw-ow, ...))` clamping
  so the crop box never exceeds source bounds, followed by `scale` + `pad` + `setsar=1`.
- Captions burned **last** in the video filter chain.
- Music bed looped safely (`-stream_loop -1`), padded by `pad_tail_s` alongside the voice
  sidechain before `sidechaincompress`, then trimmed cleanly to exact total duration.
- Output always encoded as `libx264` (`-pix_fmt yuv420p`) + `aac` 48 kHz stereo with
  `-movflags +faststart`.

### CLI

```bash
python3 scripts/edit_plan.py validate edit/editPlan.json --check-files
python3 scripts/edit_plan.py compile  edit/editPlan.json -o edit/final.mp4
python3 scripts/edit_plan.py render   edit/editPlan.json -o edit/final.mp4 --dry-run
python3 scripts/edit_plan.py render   edit/editPlan.json -o edit/final.mp4
```
