---
name: talkback
category: audio
version: 0.2.0
description: >-
  Speak an explanation out loud while working in any project — tiered
  text-to-speech with a pluggable backend (ElevenLabs by default and
  quota-guarded, macOS `say` via `--fast` for free instant local speech, local
  OmniVoice as an unlimited private tier). Markdown-aware, so code fences, URLs
  and deep paths collapse to short spoken placeholders instead of being dictated
  character by character, while snake_case identifiers survive intact so the
  listener can still search for them. Every utterance is saved to disk for later
  replay. Includes an optional Stop hook that speaks a short readback when a
  turn ends — off by default, and when on it speaks only on turns the agent
  explicitly marked, so acknowledgements never become audio. Use when the user asks to hear something rather than
  read it — an explanation of a change, a walkthrough of what just happened, a
  summary they want while looking away from the screen.
author: broomva
license: MIT
tags: [tts, voice, audio, elevenlabs, accessibility, narration, explain, say]
trigger_keywords:
  - talkback, talk back, /talkback
  - explain this to me in voice, explain out loud, say that out loud
  - read that to me, read this aloud, speak that, voice this
  - tell me what you did, narrate that, walk me through it out loud
  - i want to hear it, say it, out loud, audio explanation
  - text to speech, tts, elevenlabs, voice quota
when_to_use: >
  The user wants to LISTEN rather than read — typically because they are away
  from the screen, resting their eyes, or want a walkthrough while doing
  something else. Default to the ElevenLabs voice — the plan affords it. Use
  `--fast` for throwaway lines or when network latency matters. Speak a
  written-for-the-ear summary, never a read-aloud of raw markdown; the listener
  cannot scroll back, so lead with the conclusion.
---

# talkback — hear it instead of reading it

Speaks text aloud from any project directory, saves the audio, and never
silently spends a metered quota.

**This is an on-demand tool.** It speaks when asked — the user says "explain that
out loud", or the script is run directly. It does not narrate on its own. The
turn-end hook at the bottom is an optional extra that ships off; ignore it unless
the user asks for automatic readbacks.

## Use it

```bash
S=~/.claude/skills/talkback/scripts

$S/talkback.py "Here is what changed and why it matters."   # ElevenLabs (default)
$S/talkback.py --fast "Throwaway line."                      # local, instant, free
$S/talkback.py --quota                                       # what's left
$S/talkback.py --voices                                      # list voices
$S/talkback.py --dry-run "..."                               # see spoken text, synthesise nothing
```

Text can also be piped: `git log -1 --format=%B | $S/talkback.py`.

## How the agent should use it

When the user asks to hear an explanation, **write for the ear, then speak it.**
Do not pipe raw markdown or a diff into the tool. Compose two to five sentences
of plain spoken prose — what changed, why, what it means for them — and pass
that. The listener cannot scroll back, so lead with the conclusion.

Default to the good voice — the plan comfortably affords it. Reach for `--fast`
when the text is throwaway or you want zero network latency. State which backend
was used if it fell back.

## Backends

| Backend | Cost | Quality | Notes |
|---|---|---|---|
| `elevenlabs` (**default**) | metered | best | quota-guarded, auto-falls back to `say` |
| `say` (`--fast`) | free, unlimited | fair | macOS native, ~instant, no network |
| `omnivoice` | free, unlimited | good | local + private; needs the backend up. **Unverified** — see below |

`--strict` turns any fallback into a hard failure (exit 1) instead, for scripts
that must not silently degrade.

### Quota

The account is Creator tier: **130,958 characters/month**. A two-minute spoken
explanation is roughly 1,500 characters, so that is about 87 of them a month —
enough that the good voice can be the default rather than a treat.

Verify at point of use, never from memory — `talkback.py --quota` reads it live.
The tier has changed once already, and a number in a doc is stale the moment the
plan moves.

Before synthesising, the tool reads the live quota and keeps a 250-character
reserve, so one long explanation can never drain the balance completely. If the
request would not fit, it warns on stderr and uses `say` instead.

Credentials resolve in order: `$ELEVENLABS_API_KEY` → `~/.elevenlabs/api_key`
(written by `elevenlabs auth login`) → `ELEVENLABS_API_KEY` in
`~/broomva/.env.local`. Two distinct keys exist on this machine and they resolve
to the **same** account, so checking one is checking both.

Creator tier also unlocks **instant and professional voice cloning** (30 voice
slots, 1 professional). `--voices` lists what the account can currently use.

> The `@elevenlabs/cli` package is **not** used at runtime and cannot do this —
> its whole surface is `auth · agents · tools · tests · components`, which
> manages hosted ConvAI agent projects. It has no synthesis command. The CLI is
> useful here only for `auth login`, which writes the key file.

### OmniVoice tier is unverified

The `omnivoice` backend is implemented against the documented shape but was
**never exercised** — the local backend was down when this shipped. It degrades
cleanly (falls back to `say`, or fails under `--strict`). To bring it up, see
the `omnivoice` skill; the repo is already at `~/broomva/external/OmniVoice-Studio`.

## Spoken-text handling

Agent prose is not written to be heard, so the text is prepared first:

- code fences → `(code omitted)`; URLs → `(link)`
- headings and bullets become sentence breaks, so lists do not run together
- deep paths shorten to the basename (`src/lib/engine.py` → `engine.py`); pass
  `--keep-paths` to hear them in full
- markdown emphasis is stripped **only where it delimits a span** — a bare
  underscore inside `resolve_backend` is left alone, because eating it turns a
  symbol the listener could search for into one they cannot

## Saved audio

Every utterance lands in `~/.talkback/audio/` as mp3 (converted via ffmpeg when
present) with a timestamped, slugged filename, and is appended to
`~/.talkback/ledger.jsonl`. Use `--no-save` to discard, `--out-dir` to redirect.

## Optional: speak a readback when a turn ends

The `Stop` hook fires **every time the agent finishes a turn** — including
one-line answers. Narrating all of those is worse than narrating none, so the
hook is off by default and, when on, speaks only on turns that earn it.

```bash
$S/talkback-hook.py --on            # enable, marker mode (default)
$S/talkback-hook.py --on always     # enable, every substantial turn
$S/talkback-hook.py --off           # kill switch
$S/talkback-hook.py --status        # shows mode + backend
```

### Modes

| Mode | Speaks when |
|---|---|
| `marker` (**default**) | the agent left a `<!-- talkback: … -->` marker — and only then |
| `always` | every turn over `TALKBACK_HOOK_MIN_CHARS` (80), marker preferred when present |

`marker` is the default because the marker is **authored, not extracted**: the
agent writes it deliberately when a turn did something worth hearing, so the
hook stays silent through acknowledgements and speaks a real summary rather than
whatever preamble the message happened to open with.

The mode is stored as the body of the flag file, so it survives restarts. An
empty flag file (the pre-0.2.0 format) reads as `marker`.
`TALKBACK_HOOK_MODE` overrides.

### The marker

To opt a turn in, end the message with:

```html
<!-- talkback: Refactored the auth layer, three call sites, tests green. -->
```

In `always` mode a markerless turn falls back to the opening sentences of the
message, capped at 320 characters (`TALKBACK_HOOK_CHARS`) and trimmed to a
sentence boundary.

### Safety properties

- **Off unless the flag file exists** — an unconfigured machine is silent.
- **Always exits 0**, so it can never block a turn from completing. It survives
  malformed stdin, `{}`, and a missing transcript.
- **Detaches playback**, so no turn waits on audio (measured at 0s).
- **Defaults to the free backend** even when a metered one is affordable: it
  fires unattended, for audio nobody asked for. `TALKBACK_HOOK_BACKEND` overrides.

### Registering it

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command",
        "command": "~/.claude/skills/talkback/scripts/talkback-hook.py" } ] }
    ]
  }
}
```

Goes in `~/.claude/settings.json`. Registration alone does nothing until
`--on`; both are required.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `TALKBACK_BACKEND` | `elevenlabs` | default backend |
| `TALKBACK_SAY_VOICE` | `Samantha` | macOS voice name |
| `TALKBACK_ELEVEN_VOICE` | River | ElevenLabs voice id |
| `TALKBACK_HOOK_CHARS` | `320` | readback cap |
| `TALKBACK_HOOK_BACKEND` | `say` | backend for the Stop-hook readback |
| `TALKBACK_HOOK_MODE` | `marker` | `marker` or `always` |
| `TALKBACK_HOOK_MIN_CHARS` | `80` | floor below which `always` mode stays silent |
| `TALKBACK_HOME` | `~/.talkback` | state + audio directory |
| `OMNIVOICE_API_URL` | `http://localhost:3900` | local backend |
