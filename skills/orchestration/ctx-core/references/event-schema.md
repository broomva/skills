# ctx event schema (v1)

`~/.local/state/ctx/<scope-id>/events.jsonl`. Each line is one JSON object
with sorted keys and no insignificant whitespace, and ends with `\n`. Lines are
only ever appended, under `fcntl.flock` on `events.lock` in the same
directory. Only `ctx.py` writes the file. A session with Bash *can* write it
too, because the store is coordination data, not a security boundary.

## Event

| Field | Type | Always | Meaning |
|---|---|---|---|
| `v` | int | yes | Schema version, `1` |
| `type` | string | yes | `session.start`, `session.stop` or `session.died`. Only `session.died` is terminal; Stop fires at the end of every turn, so `session.stop` is a heartbeat |
| `ts` | string | yes | UTC, `YYYY-MM-DDTHH:MM:SS.mmmZ`, fixed width, so it sorts lexically |
| `session_id` | string | yes | Claude Code's `session_id`: `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}` |
| `paseo_agent_id` | string | only if set | `PASEO_AGENT_ID` from the hook's environment; the key is absent otherwise |
| `cwd` | string | yes | Realpath of the session's cwd |
| `repo` | string | yes | Realpath of `git rev-parse --git-common-dir`, the scope key; worktrees share it |
| `branch` | string or null | yes | The branch name, `<branch>` from `ref: refs/heads/<branch>` in the worktree's own `HEAD`; `detached@<sha12>` when detached; null when unknown |
| `payload` | object | yes | Per type, below |

Every string passes the redaction pass before the write, then is clipped to
400 chars. Redaction always comes first, so a clip can never leave a partial
token behind.

### Payloads

| Type | Written by | Payload keys |
|---|---|---|
| `session.start` | SessionStart hook | `source` (`startup`, `resume`, `clear`, `compact`, `fork`), `model`, `agent_type`; `fleet_role` when `FLEET_ROLE` is set |
| `session.stop` | Stop hook | `arc_status` (the word after `ARC-STATUS:`) and `arc_line` (the whole line), taken from the **last** `ARC-STATUS:` line of `last_assistant_message`. The payload is `{}` when there is none, and the event is then a heartbeat |
| `session.died` | StopFailure hook | `error_type`, the error class (e.g. `rate_limit`, `billing_error`, `server_error`, `unknown`); `error`, the redacted error text (Claude Code 2.1.280 sends it as `error_details`); `arc_status`/`arc_line` if the partial message carried one. Phase 1 keeps one died event: the died/failed split and reset-time extraction are phase 2 |

A reader skips any `type` it does not know and counts it in
`ignored_events`, so later phases can add types (mail, claims, holds) without
breaking a phase-1 board. It skips a line that is not valid v1 JSON and counts
it in `skipped_lines`. A torn tail with no newline is left for the next fold.
The next append starts on a fresh line.

## board.json

A fold of the log, in log order, maintained under the append lock by the
writer that appends. It is serialised with `json.dumps(sort_keys=True,
indent=2)` and a trailing newline, so the same log always gives the same
bytes. Nothing in it reads a clock.

| Field | Meaning |
|---|---|
| `v`, `scope` | Schema version and scope id |
| `events`, `skipped_lines`, `ignored_events` | Counts over the folded lines |
| `last_ts` | The largest `ts` folded |
| `log_offset` | Bytes of the log folded, always at a line boundary |
| `log_tail` | crc32 of the 64 log bytes before `log_offset`. A write whose tail does not match (a replaced or truncated log) refolds from byte 0 |
| `sessions` | `session_id` → row |

A row holds:
- `first_ts`, `last_ts`, `last_event`;
- `state` (`started`, `stopped` or `died`, from the latest event);
- `cwd`, `repo`, `branch`;
- `starts`, `stops`, `started_ts`;
- `paseo_agent_id`, `fleet_role`;
- `arc_status`, `arc_line`, `arc_ts`;
- `died_ts`, `died_reason` (the error class), `died_error` (the redacted
  error text, e.g. a usage-limit message, for readers of the board such as
  fleet-reconcile).

The latest fields move only for an event whose `ts` is at least the row's.
That way two writers whose appends landed out of timestamp order still leave
the true latest state.

The two paths:
- **On write:** fold `log[log_offset:]`. A hook folds at most 64 KiB, so its
  cost never grows with the log.
- **`ctx board --rebuild`:** fold `log[0:]` from an empty board. Folding
  `0..k` and then `k..n` is folding `0..n`, so both paths give byte-identical
  boards.

SessionStart reads `board.json` and never the log. A missing board with a log
over 64 KiB means no brief until the next `ctx board`.
