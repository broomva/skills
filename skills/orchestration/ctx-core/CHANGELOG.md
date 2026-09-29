# Changelog: ctx-core

## [0.1.0] - 2026-09-29

Phase 1 of the shared context core (broomva/workspace#825, round 7): the
read-only shared board.

- `ctx.py`:
  - Scope resolution from `~/.config/ctx/scopes.yaml`, keyed by the realpath of
    the git common dir. The repo is read from `.git`, `gitdir` and `commondir`
    the way git does, with no process spawned, and tested to agree with `git
    rev-parse`.
  - An append-only `events.jsonl` per scope. The `fcntl` lock is never waited
    on for more than 40 ms in a hook (StopFailure: the rest of its budget); the
    CLI retries for up to 2 s.
  - A `board.json` folded on every write, byte-identical to `ctx board
    --rebuild`.
  - A redaction pass (a denylist) that runs before any clipping.
- `ctx board [--json] [--rebuild]`, `ctx doctor` and `ctx doctor --unscoped`.
  `doctor` tells an idle scope from a dead hook using transcripts, reads the
  deadline-miss log, and reports a broken config from any directory.
- `ctx_hook.py` for three hooks:
  - SessionStart: register, then a factual brief of at most 4,000 chars,
    linear in the number of rows, with every field on one line.
  - Stop: the ARC-STATUS line.
  - StopFailure: a `died` status, read from both the payload Claude Code 2.1.280
    sends and the documented one.

  An 80 ms self-deadline (run as `python3 -I -S`). A hook never parses a board.json over 2 MiB, which
  is what keeps that deadline hard. Exit 0 always, no output on any failure,
  and a machine-wide miss log (rotated at 1 MiB) for deadline misses and
  skipped appends. Shipped unregistered; SKILL.md carries the owner's snippet.
- From #825:
  - Round 4: SessionStart renders from the cached board and never parses the
    log, and nothing reads `CLAUDE_CODE_ENTRYPOINT`.
  - Round 7: no retention in phase 1, and compaction moves to phase 2.
