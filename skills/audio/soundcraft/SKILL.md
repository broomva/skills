---
name: soundcraft
tier: D
category: audio
description: >-
  Design and verify sound for short films, product demos, motion graphics and
  launch videos. Use for real-recording Foley, music ducking and voice clarity,
  loudness and true-peak checks, clipping or early stem cutoffs, A/V duration
  mismatches, or a visual inspection sheet for a rendered mix. Includes a local
  FFmpeg QA CLI and optional perceptual triage with earshot.
---

# Soundcraft

Build the mix around the scene's audible events. Prefer licensed, close-miked recordings over synthesized placeholders when the picture suggests a real object. Keep one coherent material palette across the film. As a starting point, leave about 85% of cuts without a dedicated effect. Keep a beat of air before the main drop, aim for the strongest one-second RMS window at 30–60% of runtime, and reserve the logo for a quiet resolution. For cue design, provenance and audition notes, use [Real-sound craft](references/real-sound-craft.md).

## Check the delivered render

Run from this skill's directory with Python 3.10+, `ffmpeg` and `ffprobe` on PATH. For `sheet`, use an FFmpeg build with `drawtext` and an available default font.

```sh
python3 scripts/audio_qa.py check film.mp4 --json
python3 scripts/audio_qa.py check film.mp4 --expected-dur 48 \
  --voice voice.wav --bed ducked-bed.wav --stem ducked-bed.wav \
  --stem foley.wav --check-peak-window --json
python3 scripts/audio_qa.py sheet film.mp4 --out film-sheet.png
python3 scripts/audio_qa.py pad-sidechain bed.wav padded-bed.wav --pad-s 1.0
```

- **Mix**. Defaults are −14 ±0.8 LUFS integrated, ≤−0.9 dBTP, ≥3.5 LU loudness range, and at most three decoded 16-bit samples with magnitude ≥32,735 across all channels. The absolute DC mean in every channel must be ≤0.01 full scale and the whole-file RMS must exceed −60 dBFS.
- **Timing**. Compare decoded audio length to video stream length and check their reported start times, both within 50 ms by default. On audio-only files, supply `--expected-dur` to compare against an edit length. The same option also checks the audio length in video. The optional late-peak gate fails above 88% of runtime. Review the 30–60% craft target separately, and use the filmstrip and waveform to check event-level sync.
- **Voice and stems**. Export voice and ducked bed on the same time origin with their actual levels. Measure 20 ms frames where the voice exceeds both −42 dBFS and its 20th-percentile noise floor by more than 12 dB. Every active frame needs bed coverage. Require voice-over-bed median ≥4.2 dB and 15th percentile ≥1.2 dB. Each supplied stem must peak below 0.999. With `--expected-dur`, any stem more than 0.25 s short fails too.
- **Fix a truncated bed upstream**. Pad a work copy before `sidechaincompress`, then re-render and check the ducked output stem. Give the sidechain key a silence margin beyond the edit too so its final packet can be processed. Trim the resulting mix to the intended timeline.
- **Read the receipt**. Exit 0 means all enabled gates passed. Exit 1 means a gate failed. Exit 2 means invalid arguments, unusable media or unavailable tooling. Keep the JSON and use the sheet to inspect gaps, frequency balance and cue placement after corrections.

For optional local CPU tagging or perceptual comparisons, use [Earshot integration](references/earshot-integration.md). Treat CLAP and `p_real` as clues and guard against Goodharting them. If assets were synthesized, say so explicitly. Record whether a person auditioned the delivered mix.

## Attribution

Original implementation and documentation. The craft and optional perceptual workflow draw on [earshot](https://github.com/Leonxlnx/earshot) and [real-sound](https://github.com/Leonxlnx/earshot/tree/main/skills/real-sound), MIT License, Copyright (c) 2026 Leon Lin. [Upstream license](https://github.com/Leonxlnx/earshot/blob/main/LICENSE).
