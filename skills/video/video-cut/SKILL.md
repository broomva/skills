---
name: video-cut
category: video
primitive: null
description: |
  Edit raw footage into a finished cut by conversation, fully local. Drop clips in a
  folder, describe the video you want, get edit/final.mp4 back. Local-first raw-footage
  video editor — the editorial counterpart to the generative Remotion/launch-video skills.
  Uses a two-layer reading system (local faster_whisper word-level transcript + on-demand
  timeline_view composite) so the agent cuts with word-boundary precision without ever
  dumping video frames — llm-as-index applied to video. Swaps cloud ElevenLabs Scribe for
  local faster_whisper: free at any volume, nothing leaves the machine, no API key. Removes
  filler/dead-air, color-grades per segment, burns subtitles, composes overlay animations
  via Remotion, and self-evaluates the render before showing you.
  USE WHEN: edit this footage, cut these clips, make a video from this raw footage, remove
  filler words from video, trim this recording into a video, edit talking head, montage,
  tutorial cut, interview edit, turn these clips into a launch video.
  NOT FOR generating video from scratch (use launch-video / Remotion /
  cloned-voice-pitch-pipeline), audio-only cleanup (use AudioEditor), or static images
  (use Art).
  Triggers on: edit footage, cut clips, video-cut, raw footage to video, remove filler
  from video, trim video, talking-head edit.
license: MIT
author: broomva
required: false
tags:
  - video
  - video-editing
  - ffmpeg
  - faster-whisper
  - local-first
  - llm-as-index
compounding:
  - Remotion
  - launch-video
  - content-creation
  - cloned-voice-pitch-pipeline
---

# video-cut — local-first raw-footage video editor

Drop raw clips in a folder → describe the cut → get `edit/final.mp4`. Fully local. The
**editorial** counterpart to our **generative** video skills (`launch-video`, `Remotion`,
`cloned-voice-pitch-pipeline`). Compounds on [`browser-use/video-use`](https://github.com/browser-use/video-use):
same two-layer reading architecture, but local ASR instead of cloud ElevenLabs Scribe.

## Core principle — two-layer reading (never dump frames)

The agent reads video through two cheap layers, not by watching frames:

1. **Transcript layer** — `transcribe_local.py` runs `faster_whisper` with word-level
   timestamps (local, MPS/CPU). Packed into `takes_packed.md` (~tens of KB) — the primary
   reading artifact. This is the *routing projection*.
2. **Visual layer (on-demand)** — `timeline_view.py <video> <start> <end>` renders a
   filmstrip + waveform + word-label PNG **only at decision points** (ambiguous pauses,
   retake comparisons, cut-point checks). Never a scan — the *body-grep* expansion.

This is `research/entities/pattern/llm-as-index-architecture.md` applied to the video
modality: raw frames = the substrate you never dump; transcript = the projection that
routes; `timeline_view` = on-demand expansion. (See `references/local-asr.md`.)

## Pipeline

```
Transcribe (local) → Pack → LLM reasons (proposes plain-English strategy, waits) →
EDL → Render (ffmpeg) → Self-eval (≤3 correction loops) → final.mp4
```

The **EDL** (`edl.json`) is the declarative cut IR — cut ranges + grade + overlays +
subtitles in one file. Decouples *decision* (the agent) from *render* (ffmpeg). Full
schema in `references/edl-format.md`.

## Hard Rules (non-negotiable production correctness)

These are inherited from video-use's hard-won list. See `references/hard-rules.md` for the
ffmpeg specifics. Summary:

1. **Subtitles applied LAST** in the filter chain, after every overlay.
2. **Per-segment extract → lossless concat** (`-c copy`). Never double-encode.
3. **30 ms audio fades** (`afade`) at every cut — no audible pops.
4. **Snap cuts to word boundaries** — never cut inside a word; use transcript timestamps.
5. **Cut padding 30–200 ms** absorbs ASR drift.
6. **Word-level verbatim ASR only** — never phrase-mode or normalized fillers.
7. **Cache transcripts per source** (by content hash) — never re-transcribe unchanged input.
8. **Caption output-timeline offsets** — `out = word.start - range.start + range_offset`.
9. **Output isolation** — all session files go to `<videos_dir>/edit/`, never elsewhere.
10. **Strategy approval** — confirm a plain-English plan before touching the cut.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/transcribe_local.py <video> [--model base] [--diarize]` | Local faster_whisper word-level transcript → `edit/transcripts/<name>.json` (cached by source hash) |
| `scripts/pack_transcripts.py --edit-dir <dir>` | All `transcripts/*.json` → `edit/takes_packed.md` (phrase-level; breaks on silence ≥0.5 s or speaker change) |
| `scripts/timeline_view.py <video> <start> <end> [-o out.png]` | Filmstrip + waveform + word-label PNG for one range → `edit/verify/` |
| `scripts/render.py <edl.json> [-o out.mp4] [--preview]` | EDL → ffmpeg: per-segment extract+grade+fades → lossless concat → overlays → subtitles (LAST) |
| `scripts/self_eval.py <edl.json> <rendered.mp4>` | Inspect render at each cut boundary; report discontinuities/pops/hidden-subs as JSON |
| `scripts/edl.py` | Shared lib: EDL load/validate, SRT generation, output-timeline offset math (imported by render/self_eval/tests) |

## Directory layout (created under `<videos_dir>/edit/`)

```
<videos_dir>/
├── <source clips>
└── edit/
    ├── project.md                 # session memory (Strategy / Decisions / Outstanding)
    ├── takes_packed.md            # phrase-level transcript (primary LLM input)
    ├── edl.json                   # cut decisions + grade + overlays + subtitles
    ├── transcripts/<name>.json    # cached word-level transcript
    ├── clips_graded/seg_NNN.mp4   # per-segment extracts (grade + 30ms fades)
    ├── animations/slot_<id>/      # per-overlay source + render (Remotion/HyperFrames/PIL)
    ├── master.srt                 # output-timeline subtitles
    ├── verify/                    # timeline_view PNGs + self-eval frames
    ├── preview.mp4
    └── final.mp4
```

## Workflow

1. **Inventory** — `ffprobe` sources; `transcribe_local.py` each (or batch); `pack_transcripts.py`.
2. **Pre-scan** — read `takes_packed.md`; flag filler/false-starts/retakes.
3. **Converse** — shape, content type, pacing, grade, subtitle style, overlays.
4. **Propose strategy** — 4–8 sentences; wait for confirmation (Hard Rule 10).
5. **Build EDL** — author `edl.json`; spawn parallel overlay sub-agents if needed (Remotion etc.).
6. **Render** — `render.py edl.json --preview` first.
7. **Self-eval** — `self_eval.py` before showing the user; correct, ≤3 passes.
8. **Iterate** — natural-language feedback → re-render; append to `project.md`.

## Composition map

| Need | Skill |
|---|---|
| Overlay animations (kinetic type, UI, charts) | **Remotion** (PAI) / HyperFrames / PIL |
| Cinematic generated launch video | **launch-video** (broomva) — generative, Liquid Glass |
| AI-generated B-roll / frames | **content-creation** (Imagen/Veo) |
| Audio-only cleanup | **AudioEditor** (PAI) |
| Narrated pitch from text + cloned voice | **cloned-voice-pitch-pipeline** (OmniVoice → Remotion) |
| Local word-level ASR backbone | `faster_whisper` (this skill) |

video-cut **edits**; the others **generate**. They share the EDL as a future common IR
(overlays produced by Remotion are referenced as EDL `overlays[]`).

## Requirements

`ffmpeg` + `ffprobe` (required), `faster_whisper` (required, local ASR), `yt-dlp` (optional,
for `--download`). Install: `uv pip install -r requirements.txt`. See `references/local-asr.md`.

## Anti-patterns (from video-use, confirmed)

- Dumping frames to the model (the 45M-token mistake) — use the two-layer reading.
- Phrase-level transcription (loses sub-second gaps) — word-level verbatim only.
- Burning subtitles before overlay composition — subtitles LAST.
- Single filtergraph that re-encodes everything twice — extract→lossless-concat→one final pass.
- Hard audio cuts at boundaries — 30 ms fades.
- Editing before strategy confirmation.
- Re-transcribing cached sources.
