# Changelog

All notable changes to this skill are documented here ([Keep a Changelog](https://keepachangelog.com/)).
This skill is an unversioned prototype (pre-release); the first tagged version will be 0.1.0.

## [Unreleased]

Initial prototype. Local-first raw-footage video editor (BRO-1579), compounding on
`browser-use/video-use`.

### Added
- **Two-layer reading** — `transcribe_local.py` (faster_whisper word-level, local) +
  on-demand `timeline_view.py` composite (filmstrip + waveform). Replaces cloud
  ElevenLabs Scribe with local ASR.
- **EDL render engine** (`render.py`) — per-segment extract + grade + 30ms fades →
  lossless `-c copy` concat → overlays (PTS-shifted) → subtitles burned LAST, in a
  single final pass. Mixed-resolution sources normalized to a common canvas. Silent
  sources get a synthesized `anullsrc` track so the concat stays uniform. `--preview`
  for fast 720p iteration.
- **Shared EDL library** (`edl.py`) — EDL load/validate, grade presets, output-timeline
  segment math (clamped padded ranges + offsets), and SRT generation with the caption
  output-timeline offset invariant. Single source of truth, imported by render + self_eval.
- **Self-eval loop** (`self_eval.py`) — inspects the render at each cut boundary
  (black/flash frame + audio-pop checks), boundaries computed via the shared `edl.py`
  math so they match the actual render.
- **pack_transcripts.py** — word transcripts → `takes_packed.md` (phrase breaks on
  silence ≥0.5s or speaker change).
- References: `edl-format.md`, `hard-rules.md`, `local-asr.md`.
- Tests: 12 pytest units (EDL/SRT math + packing) + `smoke_e2e.sh` E2E covering
  single-source, multi-resolution, silent-source, and absolute-output paths.

### Validated
- Hardened against a P20 cross-model adversarial review (7 findings fixed across 3 rounds:
  self_eval timeline alignment, absolute `-o`, mixed-resolution concat, silent-source
  audio/subtitle handling, degenerate-range dropping, `anullsrc` exact-length silent track,
  and per-seam AAC priming drift eliminated via a PCM intermediate).
- Addressed 16 CodeRabbit review comments (cache-key by transcription settings, UTF-8
  transcript I/O, CWD-independent source-path resolution, malformed-EDL + `chunk_words`
  validation, unmeasurable-frame self-eval safety, doc/pipeline consistency).

### Known limitations (follow-ups)
- Diarization (`--diarize`) is a no-op stub; pyannote pass is a separate ticket.
- Overlay engine wiring (Remotion/HyperFrames) is referenced but generated externally.
- No optional cloud-Scribe backend yet (local-only by design; flag is a follow-up).
