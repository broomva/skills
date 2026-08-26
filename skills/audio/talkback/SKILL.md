---
name: talkback
category: audio
version: 0.3.0
description: >-
  Speak an explanation out loud while working in any project — tiered
  text-to-speech with a pluggable backend (ElevenLabs by default and
  quota-guarded, macOS `say` via `--fast` for free instant local speech, local
  OmniVoice as an unlimited private tier). Markdown-aware, so code fences, URLs
  and deep paths collapse to short spoken placeholders instead of being dictated
  character by character, while snake_case identifiers survive intact so the
  listener can still search for them. Every utterance is saved to disk for later
  replay. Also carries a **talk mode** toggle: turn it on and the agent speaks a
  readback at the end of every turn, for as long as that session lasts. Talk
  mode is off by default and scoped to the single session that enabled it, so
  parallel agents in other worktrees stay silent. Use when the user asks to hear
  something rather than read it — an explanation of a change, a walkthrough of
  what just happened, a summary they want while looking away from the screen —
  or when they want the session narrated as it goes.
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
  - talk mode, talk mode on, talk mode off, turn on talk mode
  - keep talking, narrate everything, continuous talkback, talk to me
  - stop talking, be quiet, mute, silence, stop the voice
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

**On demand by default.** It speaks when asked — the user says "explain that out
loud", or the script is run directly. It does not narrate on its own until
someone turns **talk mode** on, and talk mode belongs to one session at a time.

## Use it

```bash
S=~/.claude/skills/talkback/scripts

$S/talkback.py "Here is what changed and why it matters."   # ElevenLabs (default)
$S/talkback.py --fast "Throwaway line."                      # local, instant, free
$S/talkback.py --quota                                       # what's left
$S/talkback.py --voices                                      # list voices
$S/talkback.py --dry-run "..."                               # see spoken text, synthesise nothing

$S/talkback-hook.py --on                                     # talk mode ON, this session only
$S/talkback-hook.py --off                                    # stop talking
$S/talkback-hook.py --status                                 # who is talking, is the hook wired
$S/talkback-hook.py --outputs                                # audio outputs on this host
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

### The ladder

`elevenlabs → omnivoice → say`, best first. A rung that cannot take the job —
no key, quota spent to the reserve, local server down, synthesis error — hands
off to the next one down, so the voice degrades instead of the audio going
missing. `TALKBACK_CHAIN` reorders it.

Asking for a rung explicitly starts the ladder **there and only descends**:
`--fast` means "local now" and never climbs back up to a metered backend. Every
fallback prints the reason on stderr and the chosen backend lands in the ledger,
so a degraded run is never silent about being degraded.

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
  underscore inside `backend_chain` is left alone, because eating it turns a
  symbol the listener could search for into one they cannot

## Saved audio

Every utterance lands in `~/.talkback/audio/` as mp3 (converted via ffmpeg when
present) with a timestamped, slugged filename, and is appended to
`~/.talkback/ledger.jsonl`. Use `--no-save` to discard, `--out-dir` to redirect.

## Talk mode — narrate the session as it goes

Talk mode makes the agent speak a short readback at the end of **every turn**,
for as long as the session lasts. It ships **off**, it is turned on by hand, and
it belongs to **one session**.

```bash
$S/talkback-hook.py --on                    # continuous, THIS session only
$S/talkback-hook.py --on marker             # only turns carrying a marker
$S/talkback-hook.py --on --backend elevenlabs   # the good voice, metered
$S/talkback-hook.py --on --output "AirPods Pro"  # which speaker this session uses
$S/talkback-hook.py --off                   # stop talking (this session)
$S/talkback-hook.py --off --all             # kill switch, everywhere
$S/talkback-hook.py --status                # mode, backend, who else is talking
$S/talkback-hook.py --sessions              # every session currently talking
```

### Why session-scoped

The `Stop` hook is registered once, globally and permanently — a toggle you
cannot flip during a session is not a toggle. So the hook fires in *every*
session, and the **flag** is what scopes it: talk mode is a property of a
session, not of the machine.

The flag is `~/.talkback/sessions/<session-id>`; a session that never opted in
has none, so the hook exits 0 without a sound. That is what keeps six parallel
agents in six worktrees silent while the one session you are watching talks. The
pre-0.3.0 design had a single machine-wide flag, which is why it was never
turned on: enabling it made every agent on the box audible at once.

The session id is read from `CLAUDE_CODE_SESSION_ID`, falling back to the newest
transcript for the working directory; `--session <id>` sets it explicitly. On
the hook side it comes from the payload's `session_id`, falling back to the
transcript filename stem.

### Modes

| Mode | Speaks when |
|---|---|
| `always` (**session default**) | every turn over `TALKBACK_HOOK_MIN_CHARS` (80); a marker still wins when present |
| `marker` | only when the agent left a `<!-- talkback: … -->` marker |
| `off` | never — written by `--off` when a global flag would otherwise re-enable the session |

Readbacks take the **whole ladder** — ElevenLabs first, descending only when a
rung is unusable. A talk-mode session therefore spends quota; the reserve guard
stands, so the balance runs down to the reserve and the session keeps talking on
the next rung rather than going quiet. `--on --backend say` pins it low.

`always` is the session default because that is what talk mode is *for*: you
asked to hear the session, so short acknowledgements are the only thing worth
suppressing. `marker` is there for a long unattended arc where you want the
milestones and not the narration.

### The marker

To opt a single turn in — in `marker` mode, or to speak a written-for-the-ear
summary instead of the message's opening lines — end the message with:

```html
<!-- talkback: Refactored the auth layer, three call sites, tests green. -->
```

In `always` mode a markerless turn falls back to the opening sentences of the
message, capped at 320 characters (`TALKBACK_HOOK_CHARS`) and trimmed to a
sentence boundary.

### Which speaker

Audio comes out of the **machine running Claude Code**. A session you are
driving from a phone, a tablet or another laptop still sounds on the host, so
the lever that matters is choosing which of the *host's* outputs it lands on —
AirPods paired to the Mac, an AirPlay speaker, a display, the built-in speakers.

```bash
$S/talkback-hook.py --outputs             # what this host can play through
$S/talkback-hook.py --on --output "AirPods Pro"
$S/talkback.py -d "MacBook Pro Speakers" "one-off line on a chosen device"
```

The output is stored **per session**, so two sessions on one host can come out
of two different speakers. `TALKBACK_OUTPUT` overrides. An unset output means
the system default.

A device is named the way `say -a '?'` names it. Routing to a named device goes
through ffmpeg's `audiotoolbox` muxer, because `afplay` cannot target one; if
ffmpeg is missing or the name does not resolve, it warns on stderr and plays on
the default device rather than failing the readback.

### Lifecycle

- `SessionEnd` deletes the session's flag, so talk mode never outlives the
  session that asked for it. `/clear` ends a session too — re-enable after one.
- Sessions that die without a `SessionEnd` (a killed terminal, a crashed
  harness) are reaped by an idle TTL, `TALKBACK_SESSION_TTL_HOURS` (24). Every
  spoken turn touches the flag, so this is an idle timeout and not a cap on how
  long a session may talk.
- A new readback **interrupts** one still playing rather than talking over it —
  turns end faster than audio plays, and the newest summary is the one worth
  hearing. `TALKBACK_BARGE_IN=0` to queue nothing and let them overlap instead.

### The global flag, if you really want it

```bash
$S/talkback-hook.py --on --global      # every session on the machine speaks
```

Deliberately a separate gesture, and it defaults to `marker`. A session can
still mute itself over it (`--off` writes an `off` flag rather than deleting
one, so the session does not fall back to the global setting), and
`--off --all` clears everything.

### Safety properties

- **Silent unless a flag exists** — an unconfigured machine, and every session
  that did not opt in, make no sound.
- **Always exits 0**, so it can never block a turn from completing. It survives
  malformed stdin, `{}`, a missing transcript, and a backend that throws.
- **No identity, no audio** — a payload carrying neither a session id nor a
  transcript path is not spoken for, because isolation could not be guaranteed.
- **Session keys are validated** before becoming a path, so a `../` in a payload
  cannot point the flag lookup outside `~/.talkback/sessions/`.
- **Detaches playback**, so no turn waits on audio.
- **Defaults to the free backend** even when a metered one is affordable: it
  fires unattended, on every turn, for audio nobody asked for.

### Registering it

```bash
$S/talkback-hook.py --install --dry-run   # show what would change
$S/talkback-hook.py --install             # register Stop + SessionEnd
$S/talkback-hook.py --uninstall           # remove them again
```

`--install` edits `~/.claude/settings.json` idempotently, backing it up first,
and adds:

```json
{
  "hooks": {
    "Stop":       [ { "hooks": [ { "type": "command", "command": ".../talkback-hook.py" } ] } ],
    "SessionEnd": [ { "hooks": [ { "type": "command", "command": ".../talkback-hook.py" } ] } ]
  }
}
```

Claude Code reads hooks at session start, so a fresh install takes effect in the
**next** session. Registration alone makes no sound; `--on` is still required,
and it is required again in every session.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `TALKBACK_BACKEND` | `elevenlabs` | default backend |
| `TALKBACK_SAY_VOICE` | `Samantha` | macOS voice name |
| `TALKBACK_ELEVEN_VOICE` | River | ElevenLabs voice id |
| `TALKBACK_HOOK_CHARS` | `320` | readback cap |
| `TALKBACK_CHAIN` | `elevenlabs,omnivoice,say` | the quality ladder, best first |
| `TALKBACK_HOOK_BACKEND` | `elevenlabs` | top rung for talk-mode readbacks |
| `TALKBACK_OUTPUT` | *(unset)* | audio output device, overriding the session's |
| `TALKBACK_HOOK_MODE` | *(unset)* | overrides the stored mode: `marker` or `always` |
| `TALKBACK_HOOK_MIN_CHARS` | `80` | floor below which `always` mode stays silent |
| `TALKBACK_SESSION_TTL_HOURS` | `24` | idle timeout that reaps a dead session's flag |
| `TALKBACK_BARGE_IN` | `1` | a new readback cuts off one still playing |
| `TALKBACK_HOME` | `~/.talkback` | state + audio directory |
| `OMNIVOICE_API_URL` | `http://localhost:3900` | local backend |
