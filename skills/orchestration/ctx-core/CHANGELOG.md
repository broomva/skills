# Changelog: ctx-core

## [0.1.0] - 2026-09-29

Phase 1 of the shared context core (broomva/workspace#825): the read-only
shared board.

- `ctx.py`: scope resolution from `~/.config/ctx/scopes.yaml` (keyed by the
  realpath of the git common dir); an append-only `events.jsonl` per scope
  under an `fcntl` lock that is never waited on for more than 150 ms; a
  `board.json` folded on every write and byte-identical to `ctx board
  --rebuild`; a redaction pass (tokens, Bearer headers, key=value secrets, crm/
  and secret-shaped paths) that runs before any clipping.
- `ctx board [--json] [--rebuild]`, `ctx doctor`, `ctx doctor --unscoped`.
- `ctx_hook.py` for SessionStart (register, then a factual brief of at most
  4,000 chars), Stop (the ARC-STATUS line) and StopFailure (a `died` status).
  A 120 ms self-deadline, exit 0 always, no output on any failure. Shipped
  unregistered; SKILL.md carries the owner's snippet.
- From #825 round 4: SessionStart renders from the cached board and never
  parses the log; nothing reads `CLAUDE_CODE_ENTRYPOINT`.
