# video-cut

**Local-first raw-footage video editor — edit by conversation, fully on your machine.**

Drop raw clips in a folder, describe the cut you want, get `edit/final.mp4` back. The
*editorial* counterpart to the generative video skills (`launch-video`, `Remotion`,
`cloned-voice-pitch-pipeline`). Compounds on
[`browser-use/video-use`](https://github.com/browser-use/video-use) — same two-layer
reading architecture, but **local `faster_whisper` instead of cloud ElevenLabs Scribe**:
free at any volume, nothing leaves the machine, no API key.

## How it works — two-layer reading (never dump frames)

1. **Transcript layer** — `transcribe_local.py` (faster_whisper, word-level, local) →
   `takes_packed.md`. The routing projection the editor reads.
2. **Visual layer (on-demand)** — `timeline_view.py` renders a filmstrip + waveform PNG
   for one range, only at decision points.

This is the `llm-as-index` pattern applied to video: raw frames are the substrate you
never dump; the transcript routes; `timeline_view` is the on-demand expansion.

## Pipeline

```
transcribe (local) → pack → reason → EDL → render (ffmpeg) → self-eval (≤3) → final.mp4
```

The **EDL** (`edl.json`) is the declarative cut IR — ranges + grade + overlays + subtitles.

## Install

```bash
npx skills add broomva/skills --skill video-cut
uv pip install -r requirements.txt      # faster-whisper
# system deps: ffmpeg + ffprobe (brew install ffmpeg)
```

## Quickstart

```bash
cd /path/to/your/clips
python3 scripts/transcribe_local.py clip.mp4 --edit-dir ./edit
python3 scripts/pack_transcripts.py --edit-dir ./edit
# author edit/edl.json (see references/edl-format.md), then:
python3 scripts/render.py edit/edl.json --preview     # fast 720p preview
python3 scripts/render.py edit/edl.json               # full quality
python3 scripts/self_eval.py edit/edl.json edit/final.mp4
```

Or just run it inside an agent session and say *"edit these clips into a launch video."*

## Tests

```bash
python3 -m pytest -q          # unit: EDL/SRT math + transcript packing
bash tests/smoke_e2e.sh       # end-to-end (synthesizes a clip, runs the full pipeline)
```

The smoke test is fully local (uses `say`/`espeak`/sine for audio, ffmpeg `testsrc` for
video) and covers single-source, multi-resolution, silent-source, and absolute-output
paths.

## Docs

- `SKILL.md` — the agent-facing skill definition + workflow
- `references/edl-format.md` — EDL & transcript JSON contracts (frozen v1)
- `references/hard-rules.md` — ffmpeg production-correctness invariants
- `references/local-asr.md` — why faster_whisper, the local-first differentiator

## License

MIT.
