# EDL & transcript JSON contracts (frozen v1)

These are the load-bearing data contracts. All scripts read/write exactly these shapes.

## Transcript JSON — `edit/transcripts/<name>.json`

Produced by `transcribe_local.py`. One file per source clip.

```json
{
  "source": "/abs/path/clip.mp4",
  "source_hash": "sha256-hex-of-source-bytes",
  "duration": 43.0,
  "language": "en",
  "model": "faster-whisper:base",
  "words": [
    {"word": "Ninety", "start": 2.52, "end": 2.81, "prob": 0.98, "speaker": null}
  ],
  "segments": [
    {"start": 2.52, "end": 5.36, "text": "Ninety percent of what a web agent does is wasted."}
  ]
}
```

- `words[]` is the canonical layer — verbatim, word-level. `speaker` is `null` when
  diarization is off (v0 default).
- `source_hash` drives cache invalidation: skip re-transcription iff a cached JSON exists
  whose `source_hash` matches the current source bytes.
- `prob` is the word confidence (faster_whisper `word.probability`).

## Packed transcript — `edit/takes_packed.md`

Produced by `pack_transcripts.py`. The primary human/LLM reading artifact.

```markdown
## clip  (duration: 43.0s, 8 phrases)
  [002.52-005.36] S0 Ninety percent of what a web agent does is completely wasted.
  [006.08-006.74] S0 We fixed this.
```

- One `##` block per source (label = filename stem).
- Each line: `  [SSS.ss-EEE.ss] <speaker> <text>` — zero-padded to 3 integer digits.
- **Phrase boundary rule**: start a new phrase when the gap between consecutive words is
  ≥ `0.5 s` OR the speaker changes. `speaker` renders as `S0` when null.

## EDL — `edit/edl.json` (version 1)

Authored by the agent; consumed by `render.py` and `self_eval.py`.

```json
{
  "version": 1,
  "sources": {"clip": "/abs/path/clip.mp4"},
  "ranges": [
    {"source": "clip", "start": 2.42, "end": 6.85,
     "beat": "HOOK", "quote": "Ninety percent ... wasted",
     "reason": "strongest opening line", "grade": "warm_cinematic"}
  ],
  "grade": "neutral_punch",
  "fade_ms": 30,
  "pad_ms": 60,
  "overlays": [
    {"file": "edit/animations/slot_1/render.mov", "start_in_output": 0.0, "duration": 5.0}
  ],
  "subtitles": {"mode": "burn", "style": "bold-overlay", "chunk_words": 2},
  "output": "edit/final.mp4"
}
```

Field semantics:
- `sources` — label → absolute path. `ranges[].source` references a label.
- `ranges[]` — ordered output sequence. `start`/`end` are seconds in the *source*. `beat`,
  `quote`, `reason` are advisory (carried into `project.md`). `grade` (optional) overrides
  the top-level `grade` for that segment.
- `grade` — default grade preset for ranges that don't specify one. One of
  `warm_cinematic | neutral_punch | none`, or `{"filter": "<raw ffmpeg vf>"}` for custom.
- `fade_ms` — audio fade in/out per segment (default 30).
- `pad_ms` — symmetric cut padding added to each range (default 60), clamped to source bounds.
- `overlays[]` — `start_in_output` is seconds on the *output* timeline; the overlay's
  frame 0 is shifted there via `setpts`. Optional; `[]` = none.
- `subtitles` — `{"mode": "none"}` to disable, or `{"mode": "burn", "style": ..., "chunk_words": N}`.
  Styles: `bold-overlay` (2-word UPPERCASE, Helvetica Bold, MarginV=35) and
  `natural-sentence` (4–7 words, sentence case, MarginV=70). Subtitles are built from the
  transcript words inside each range, mapped to the output timeline (offset math below).

## Output-timeline offset math (the caption invariant)

For output range `i` with source span `[s_i, e_i]`, the cumulative output offset is
`offset_i = Σ_{j<i} (e_j - s_j)` (after padding is applied). For a transcript word `w`
falling inside range `i`:

```
out_start = w.start - s_i + offset_i
out_end   = w.end   - s_i + offset_i
```

Words are chunked into groups of `chunk_words`; a chunk's SRT timing runs from the first
word's `out_start` to the last word's `out_end`. This logic lives in `scripts/edl.py`
(`build_srt`, `range_offsets`) and is unit-tested.
