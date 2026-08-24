# Changelog

All notable changes to the `talkback` skill are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning is per-skill within the `broomva/skills` monorepo; releases are tagged
`talkback-vX.Y.Z`.

## [Unreleased]

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
