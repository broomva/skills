---
name: filmcraft
tier: D
category: video
description: >-
  Thin terminal-first video production router and delivery-gate runner uniting
  Broomva's modular video, motion, design, and audio skills without duplicating
  them. Dissects references (`scripts/video_ingest.py` / `ffprobe`), routes raw
  footage to `video-cut`, code-first motion and launch films to `motion-lab`
  (+ `liquid-midnight` or `liquid-dawn`), and sound design/QA to `soundcraft`,
  then runs unified visual + audio delivery gates (`filmcraft.py verify`) that
  fail closed when any sibling gate is missing. USE WHEN: starting an end-to-end
  video or launch film, deciding which video skills to chain, checking toolchain
  readiness (`doctor`), dissecting a reference video, or running visual + audio
  QA on an MP4. NOT FOR: audio-only work with no video deliverable (route to
  `soundcraft`), static UI design (`broomva-design`, `liquid-midnight`,
  `liquid-dawn`), or remote `bypassPermissions` daemons.
---

# filmcraft — terminal-first video production router

`filmcraft` is a thin composition and routing layer over Broomva's modular
video, motion, visual-system, and audio skills. It does not re-implement
transcription, frame rendering, color grading, or loudness measurement; it
routes an intent to the right ordered skill chain and enforces combined
visual + audio delivery gates on the rendered MP4.

## Routing table

| Need / Signal | Routed Owner | Concrete Mechanism |
|---|---|---|
| Reference dissection (URL, local ref clip, pacing/shot study) | Workspace `scripts/video_ingest.py` + `ffprobe` | Transcript + change-sampled contact sheet + stream/duration probe |
| Raw recorded footage (talking head, interview, screen capture, retakes) | `video-cut` | Local Whisper + `unheard.py` retake detector + typed `editPlan.json` / `edl.py` compiler + `render.py` |
| Code-first motion / launch films / explainers / loops | `motion-lab` | `motion_lint.py` + `render.mjs --serve --workers --webgl --verify` + `video_qa.py grade` (CIELAB & contact-sheet scans) |
| Visual direction (dark glass/metal keynote vs warm daylight) | `liquid-midnight` or `liquid-dawn` | Materialize one style system; never mix their tokens on one surface |
| Sound design & perceptual/delivery audio verification | `soundcraft` | `audio_qa.py check` / `sheet` / `pad-sidechain` + MIT `earshot` / `real-sound` craft rules |
| Audio-only request (podcast mix, SFX-only, WAV master, no video) | Rejected from `filmcraft` -> direct to `soundcraft` | `filmcraft.py route` returns `in_scope: false`, `lane: "audio_only"`, `skills: ["soundcraft"]` |

Full inter-skill input/output contracts live in
[`references/pipeline-contracts.md`](references/pipeline-contracts.md).

## 4-stage production pipeline

Every video deliverable moves through four explicit stages. Stage 1 is skipped
when there is no reference artifact; Stages 2-4 always run.

1. **Stage 1 — Ingest / Dissect (optional, when a reference exists)**
   Run `python3 scripts/video_ingest.py <ref> --outdir work/ingest --keep-video` and
   `ffprobe` on `video_path` from `work/ingest/manifest.json` to extract beat cadence, shot durations, aspect ratio, and audio
   structure as a contact sheet + transcript rather than dumping raw frames.
2. **Stage 2 — Spec & Route**
   Run `python3 scripts/filmcraft.py doctor --json` to verify toolchain and
   sibling skill readiness, then `python3 scripts/filmcraft.py route "<intent>"`
   to lock the ordered skill chain, style system (if any), and target duration.
3. **Stage 3 — Render / Compile**
   Execute the routed sibling skills in order:
   - Footage lane: `video-cut` (`transcribe_local.py` -> `unheard.py` ->
     `editPlan.json` / `edl.py` -> `render.py`).
   - Motion lane: materialize `liquid-midnight` or `liquid-dawn` if selected,
     lint with `motion-lab/scripts/motion_lint.py`, and render via
     `motion-lab/scripts/render.mjs --serve --workers --webgl --verify --mp4`.
   - Hybrid lane: assemble footage cut first in `video-cut`, render overlays in
     `motion-lab`, composite overlays before subtitles.
   - Sound lane: score, sidechain, and mux with `soundcraft` unless the brief
     explicitly requests a silent deliverable.
4. **Stage 4 — Visual + Audio Delivery Gates**
   Run `python3 scripts/filmcraft.py verify <output.mp4> --expected-dur <sec> --json`.
   This executes `motion-lab/scripts/video_qa.py grade` AND
   `soundcraft/scripts/audio_qa.py check` (unless `--skip-audio` is explicitly
   passed for a silent asset) and emits a single machine-readable receipt.

## CLI (`scripts/filmcraft.py`)

Pure Python 3.11+ standard library; zero third-party Python dependencies.

```bash
# 1. Check local binaries and sibling skills
python3 scripts/filmcraft.py doctor --json

# 2. Deterministically route an intent into an ordered skill chain
python3 scripts/filmcraft.py route "make a 45s liquid midnight launch film with sound" --json
python3 scripts/filmcraft.py route "trim retakes from raw talking-head interview" --has-footage --json
python3 scripts/filmcraft.py route "recreate this reference trailer as a 30s launch film" --has-reference --needs-audio --json

# 3. Run unified visual + audio delivery gates on a finished MP4
python3 scripts/filmcraft.py verify out/launch.mp4 --expected-dur 45 --beats 0,12,24 --json
```

### Exit codes

| Command | Exit `0` | Exit `1` | Exit `2` |
|---|---|---|---|
| `doctor` | All required binaries (`ffmpeg`, `ffprobe`, `node`, `python3`) found | One or more required binaries missing | CLI usage error |
| `route` | Intent classified (check `in_scope` for audio-only/out-of-scope handoffs) | — | Empty/invalid CLI input |
| `verify` | All required gates **ran** and **passed** (and duration matched if given) | At least one required gate ran and **failed**, or duration mismatch | Target MP4 missing, or a required sibling gate script is absent (`skipped_missing_tool`) / errored |

`verify` fails closed by design (prove-the-negative): if
`motion-lab/scripts/video_qa.py` or `soundcraft/scripts/audio_qa.py` is missing,
`verify` records `"status": "skipped_missing_tool"` and exits `2` rather than
reporting a fake green.

## Licensing & security posture

- **Clean-room + open-source licenses only.** `filmcraft` and the sibling skills
  it routes to are clean-room implementations relying on MIT / Apache-2.0 code
  patterns and libraries (MIT `earshot` / `real-sound` craft rules, Playwright,
  local Whisper, Apache-2.0 HyperFrames patterns) plus system FFmpeg (LGPL by
  default, or GPL when GPL components are enabled in the local build). Never
  vendor or copy proprietary Gorg templates, closed-source presets, or
  restricted assets.
- **Local-first, zero unsafe daemons.** All commands execute locally inside the
  caller's workspace with standard user permissions. Never replicate or stand up
  remote `bypassPermissions` daemons, unauthenticated render webhooks, or
  background shells that skip host approval gates.

## Tests

```bash
python3 -m pytest tests/ -q
python3 tests/mutation_proof.py
```
