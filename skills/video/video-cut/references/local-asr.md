# Local ASR — the local-first differentiator

video-use depends on **cloud ElevenLabs Scribe** for word-level timestamps + diarization.
video-cut swaps it for **local `faster_whisper`** — the same wedge OmniVoice has vs
ElevenLabs: free at any volume, nothing leaves the machine, no API key.

## Why faster_whisper

- Produces **word-level** timestamps (`word_timestamps=True`) — required for word-boundary
  cuts (Hard Rule 4). Phrase-level ASR is an explicit anti-pattern.
- Runs locally on CPU or GPU (CTranslate2 backend; Apple Silicon via CPU int8 is fast
  enough for editing-length clips). No network, no per-character billing.
- Verbatim — does not normalize fillers (umm/uh), which the editor needs to *find and cut*.

## API shape (used by `transcribe_local.py`)

```python
from faster_whisper import WhisperModel
model = WhisperModel("base", device="auto", compute_type="int8")
segments, info = model.transcribe(audio_path, word_timestamps=True, vad_filter=True)
for seg in segments:
    for w in seg.words:
        # w.word, w.start, w.end, w.probability
        ...
```

- `device="auto"` picks CUDA when present, else CPU. `compute_type="int8"` is the portable
  default; `float16` on CUDA.
- `vad_filter=True` trims long silences before ASR (faster, cleaner gaps).
- Model sizes: `tiny`/`base` for fast iteration & tests; `small`/`medium` for final quality.
  Default `base`.

## Caching (Hard Rule 7)

`transcribe_local.py` hashes the source bytes (sha256) and writes `source_hash` into the
transcript JSON. On re-run, if a cached JSON exists with a matching hash, transcription is
skipped. Pass `--force` to override.

## Diarization (v0: off)

`--diarize` is reserved for a pyannote-based speaker labeling pass (follow-up ticket). In
v0, `speaker` is `null` and packs render as `S0`. The contract already carries the field so
enabling diarization later is non-breaking.

## Relationship to AudioEditor

PAI **AudioEditor** uses `insanely-fast-whisper` for *audio-only* cleanup. video-cut uses
`faster_whisper` for the *video* transcript layer. Both are local, word-level — the same
local-first ASR philosophy, applied to different stages. A future consolidation could share
one ASR backend; for now they're independent to avoid coupling to a third-party skill.
