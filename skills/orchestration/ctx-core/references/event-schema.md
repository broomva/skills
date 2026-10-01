# ctx event schema (v1)

`~/.local/state/ctx/<scope-id>/events.jsonl`. Each line is one JSON object
with sorted keys and no insignificant whitespace, and ends with `\n`. Lines are
only ever appended, one per lock hold, under `fcntl.flock` on `events.lock` in
the same directory. Only `ctx.py` writes the file. A session with Bash *can*
write it too, because the store is coordination data, not a security boundary.

**Structured fields only.** No free text from a session is stored: no message
text, error text, model, source or role. Every string passes one guard
(`guard_ok`), which rejects:
- `crm/`, `Bearer `, `ghp_`, `gho_`, `github_pat_`, `sk-`, `xox` or `AKIA`,
  matched case-insensitively at the start of a token;
- a run of 32 or more ASCII letters and digits.

The same schema is enforced on read. A line with an unknown key, a free-text
payload, or a guard-failing field is skipped by the fold, and counted in
`skipped_lines`.

## Event

| Field | Type | Always | Meaning |
|---|---|---|---|
| `v` | int | yes | Schema version, `1` |
| `type` | string | yes | `session.start`, `session.stop` or `session.died`. Only `session.died` is terminal; Stop fires at the end of every turn, so `session.stop` is a heartbeat |
| `ts` | string | yes | UTC, `YYYY-MM-DDTHH:MM:SS.mmmZ`, fixed width, so it sorts lexically |
| `session_id` | string | yes | Claude Code's `session_id`: `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}` |
| `paseo_agent_id` | string | only if set | `PASEO_AGENT_ID`, when it is id-shaped (same pattern) and passes the guard; the key is absent otherwise |
| `cwd` | string | yes | Realpath of the session's cwd, flattened to one line. A cwd that fails the guard means no event at all |
| `repo` | string | yes | Realpath of the git common dir (the scope key; worktrees share it), flattened |
| `branch` | string or null | yes | The branch name, `<branch>` from `ref: refs/heads/<branch>` in the worktree's own `HEAD`; `detached@<sha12>` when detached; null when unknown, not a valid refname, or guard-failing |
| `payload` | object | yes | Per type, below; no other keys |

### Payloads

| Type | Written by | Payload |
|---|---|---|
| `session.start` | SessionStart hook | `{}` |
| `session.stop` | Stop hook | `{}`, or `arc_status` plus an optional `arc_line`. They come from the **last** line of `last_assistant_message` that matches exactly `^ARC-STATUS: [A-Z]+`: at the start of the line, one space, then capitals. `arc_status` is that word when it is `MERGED`, `CLOSED`, `DONE` or `BLOCKED`, otherwise `OTHER`. `arc_line` is the line's first 120 characters, present only when the whole line passes the guard |
| `session.died` | StopFailure hook | `{"error": <class>}`: Claude Code's error class (`rate_limit`, `overloaded`, `billing_error`, `server_error`, …), read from `error` (what 2.1.280 sends) or `error_type` (the documented name). It must match `^[a-z][a-z0-9_]{0,39}$`, otherwise it is `unknown`. `error_details` is never read |

A reader skips any `type` it does not know and counts it in `ignored_events`,
so later phases can add types without breaking a phase-1 board. A torn tail
with no newline is left for the next fold, and the next append starts on a
fresh line.

## board.json (a cache)

The log folded, in log order, up to `log_offset`. It is serialised as compact
JSON with sorted keys and a trailing newline, so the same log always gives the
same bytes. Nothing in it reads a clock.

| Field | Meaning |
|---|---|
| `v`, `scope` | Schema version and scope id |
| `events`, `skipped_lines`, `ignored_events` | Counts over the folded lines |
| `last_ts` | The largest `ts` folded |
| `log_offset` | Bytes of the log folded, always at a line boundary |
| `log_tail` | crc32 of the 64 log bytes before `log_offset`. A reader whose tail does not match (a replaced or truncated log) discards the cache and folds from byte 0 |
| `sessions` | `session_id` → row |

A row holds:
- `session_id`, `first_ts`, `last_ts`, `last_event`;
- `state` (`started`, `stopped` or `died`, from the latest event);
- `cwd`, `repo`, `branch`;
- `starts`, `stops`, `started_ts`;
- `paseo_agent_id`, `agent_ts`;
- `arc_status`, `arc_line`, `arc_ts`;
- `died_ts`, `died_error` (the error class).

The latest fields move only for an event whose `ts` is at least the row's, so
two writers whose appends landed out of timestamp order still leave the true
latest state.

**Live:** an event within the last 6 h and no `session.died` since the
session's last other event. In code that is `state != "died"` with `last_ts`
in the window.

**Who writes it.** Never a hook under the lock, and never Stop or StopFailure.
- SessionStart folds at most 64 KiB past the cache, and writes the advanced
  cache back (an atomic replace, with no lock) once it has folded 16 KiB or run
  out of cap.
- `ctx board` folds the whole tail and writes it back.
- `ctx board --rebuild` folds from byte 0.

Folding `0..k` and then `k..n` is folding `0..n`, so cache plus tail and a full
rebuild are byte-identical. A hook does not parse a board.json over 2 MiB
(about 2,900–3,800 sessions). There is no retention in phase 1; SKILL.md gives
the recovery path.
