# Changelog

All notable changes to the `talkback` skill are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning is per-skill within the `broomva/skills` monorepo; releases are tagged
`talkback-vX.Y.Z`.

## [Unreleased]

## [0.3.0] — 2026-08-26

**Talk mode is a property of a session, not of the machine.** The 0.2.0 hook was
gated on one global flag, so turning it on made every Claude Code session on the
box audible at once — every parallel agent, every worktree. That is why it was
never turned on.

### Added

- **Talk mode**, scoped to the session that enables it:
  `talkback-hook.py --on` / `--off` / `--status` / `--sessions`. The flag lives
  at `~/.talkback/sessions/<session-id>`; a session that never opted in makes no
  sound, which is what lets the hook be registered globally and permanently
  while only one session talks. A toggle you cannot flip mid-session is not a
  toggle, so the hook must already be there — the flag is what scopes it.
- `--install` / `--uninstall` register the hook in `~/.claude/settings.json`
  idempotently, backing the file up first.
- A **`SessionEnd`** handler that drops the session's flag, plus an idle TTL
  (`TALKBACK_SESSION_TTL_HOURS`, 24) for sessions that die without one. Every
  spoken turn touches the flag, so the TTL is an idle timeout and not a cap on
  how long a session may talk.
- **Barge-in**: a new readback interrupts one still playing instead of speaking
  over it (`TALKBACK_BARGE_IN=0` to disable). Turns end faster than audio plays.
- Per-session backend, `--on --backend elevenlabs`.
- **Per-session audio output.** `--outputs` lists the host's output devices,
  `--on --output "AirPods Pro"` pins one to a session, and `talkback.py
  -d <device>` routes a one-off line. Two sessions on one host can come out of
  two speakers. Routing goes through ffmpeg's `audiotoolbox` muxer, because
  `afplay` cannot target a device; an unresolvable name warns and plays on the
  default rather than failing the readback. Audio still sounds on the machine
  running Claude Code — a session driven from another device does not move it.
- A test suite (54 cases), including the isolation predicate in **both**
  polarities: an opted-in session speaks, and a concurrent session under the
  identical setup stays silent. A one-sided test passes just as happily against
  a hook that never speaks at all.

### Changed

- **Readbacks speak the whole turn by default.** `full` replaces `always` as the
  session default (`always` still reads as `full`), joined by `brief` — the old
  capped excerpt — and the existing `marker`. A capped excerpt is a preview of
  the answer, not the answer: you would still have to read the screen, which is
  the thing talk mode exists to avoid. `full` also has no length floor, so a
  short result still gets spoken. `TALKBACK_FULL_MAX_CHARS` puts a ceiling on
  it, off by default. In `full`, a marker becomes the headline spoken ahead of
  the body rather than replacing it.
- `TALKBACK_ON_OVERLAP=queue` serializes playback so a long full readback is
  never cut off by the next turn; `interrupt` (the default) keeps the previous
  barge-in behaviour.
- **Backends now form a ladder** — `elevenlabs → omnivoice → say` — instead of a
  single fall-back-to-`say`. A rung that cannot take the job hands off to the
  next one down, so the voice degrades rather than the audio going missing, and
  asking for a rung explicitly starts there and only descends (`--fast` never
  climbs back to a metered backend). `TALKBACK_CHAIN` reorders it.
- Talk-mode readbacks default to the **top** of that ladder rather than to
  `say`. The ElevenLabs reserve guard still stands, so a chatty session runs the
  balance down to the reserve and then keeps talking on the next rung.
- `--on` now means **this session**, and defaults to `always` (continuous) —
  that is what talk mode is for. The machine-wide flag moved behind an explicit
  `--on --global` and keeps `marker` as its default.
- `--off` writes an `off` flag rather than deleting one when a global flag is
  set, so "stop talking" stops the talking instead of falling back to the global
  setting.
- Session keys are validated before becoming a path, so a `../` in a hook
  payload cannot point the flag lookup outside `~/.talkback/sessions/`.

### Removed

- `ENABLED_FLAG` in `talkback.py`, dead since 0.1.0 and now actively misleading.

### Compatibility

- A pre-0.3.0 global flag still works and still speaks in every session; it now
  reports as `global` in `--status`, and `--off --all` clears it.
- A flag file containing a bare mode word (the 0.2.0 format) still reads as that
  mode.


## [0.2.0] — 2026-08-23

**talkback is an on-demand tool.** You invoke it — by asking for something out
loud, or by running the script. The turn-end hook is an optional extra that
ships **off**, and enabling it now takes a deliberate second step.

### Changed

- The Stop hook gained a **mode**, stored as the body of the flag file
  (`~/.talkback/hook-enabled`), with `--on [marker|always]` to set it:
  - **`marker`** (new default) — speaks **only** on turns where the agent left a
    `<!-- talkback: … -->` marker. Silent otherwise.
  - **`always`** — the 0.1.0 behaviour, now floored at
    `TALKBACK_HOOK_MIN_CHARS` (80) so acknowledgements stay silent.
- `--status` reports the active mode and backend.

  The `Stop` event fires on **every** turn, one-line answers included. As shipped
  in 0.1.0, enabling the hook meant narrating all of them, which buries the
  signal it was meant to carry. The marker is authored rather than extracted, so
  gating on it means the hook speaks a real summary exactly when a turn earned
  one — and stays quiet the rest of the time.

### Compatibility

- An empty flag file (the 0.1.0 format) reads as `marker`, so an existing
  install becomes quieter, never louder.
- `TALKBACK_HOOK_MODE` overrides the stored mode.

## [0.1.0] — 2026-08-23

Initial release.

### Added

- `talkback.py` — speak text aloud from any project directory, with a pluggable
  backend: `elevenlabs` (default, quota-guarded), `say` (`--fast`, free, unlimited,
  no network), `omnivoice` (local, unlimited).
- Live ElevenLabs quota check before every metered call, holding a 250-character
  reserve so one long explanation cannot drain the balance. Falls back to `say`
  with a warning, or fails hard under `--strict`.
- Markdown-aware speech preparation: code fences and URLs collapse to spoken
  placeholders, headings and bullets become sentence breaks, deep paths shorten
  to their basename (`--keep-paths` to opt out), and emphasis is stripped only
  where it delimits a span so `snake_case` identifiers stay intact.
- Audio persisted to `~/.talkback/audio/` as mp3, with an append-only ledger at
  `~/.talkback/ledger.jsonl`.
- `talkback-hook.py` — optional Stop hook speaking a short readback at turn end.
  Off unless `~/.talkback/hook-enabled` exists, always exits 0 so it cannot block
  a turn, detaches playback so the turn does not wait on audio, and defaults to the
  free backend (`TALKBACK_HOOK_BACKEND` to override) — a readback fires every turn,
  unattended, for audio nobody asked for. Prefers an explicit
  `<!-- talkback: ... -->` marker over a raw readback.

### Notes

- Quota is read live (`--quota`), never carried in code or docs. This skill was
  first built against a free-tier account capped at 10,000 characters/month, which
  made `say` the only sane default; the account moved to Creator (130,958/month)
  before release and the default flipped to ElevenLabs. A tier written into a doc
  is stale the moment the plan moves.
- The `@elevenlabs/cli` package is **not** used at runtime and cannot perform
  synthesis — its surface is `auth · agents · tools · tests · components`, which
  manages hosted ConvAI agent projects. It is useful here only for `auth login`.
- The `omnivoice` backend is implemented but **unverified**: the local backend was
  unreachable when this shipped. It degrades to `say` rather than failing.
