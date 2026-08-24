# Changelog

All notable changes to the `talkback` skill are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning is per-skill within the `broomva/skills` monorepo; releases are tagged
`talkback-vX.Y.Z`.

## [Unreleased]

## [0.1.0] — 2026-08-23

Initial release.

### Added

- `talkback.py` — speak text aloud from any project directory, with a pluggable
  backend: `say` (default, free, unlimited), `elevenlabs` (`--good`, metered and
  quota-guarded), `omnivoice` (local, unlimited).
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
  a turn, detaches playback so the turn does not wait on audio, and is hardwired
  to the free backend so it can never spend a metered quota. Prefers an explicit
  `<!-- talkback: ... -->` marker over a raw readback.

### Notes

- The `@elevenlabs/cli` package is **not** used at runtime and cannot perform
  synthesis — its surface is `auth · agents · tools · tests · components`, which
  manages hosted ConvAI agent projects. It is useful here only for `auth login`.
- The `omnivoice` backend is implemented but **unverified**: the local backend was
  unreachable when this shipped. It degrades to `say` rather than failing.
